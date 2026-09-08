from dataclasses import FrozenInstanceError, replace

import pytest

from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.rotation import RotationOutcome, RotationResult
from bot.session import CharacterContext, SessionCharacterResult, SessionResult, SessionStatus
from bot.session_report import ReportStatus, build_session_report, render_session_report
from bot.send_stamina_flow import SendStaminaFlowResult, SEND_STAMINA_DAILY_PENDING
from bot.summon_pet_daily_flow import SummonPetDailyFlowResult


def flow(*kinds, status=FlowStatus.COMPLETED, **kwargs):
    return FlowResult(status, tuple(FlowEvent(kind) for kind in kinds), **kwargs)


def character(index=1, *flows, completed=True, advance=None):
    return SessionCharacterResult(index, CharacterContext(), flows or (flow(),),
                                  advance_result=advance, completed=completed)


def session(*characters, status=SessionStatus.COMPLETED, names=("send_stamina",), **kwargs):
    return SessionResult(
        status, sum(c.completed for c in characters), sum(c.completed for c in characters),
        characters, expected_character_count=kwargs.pop("expected", len(characters)),
        flow_names=names, duration=5398.9, **kwargs,
    )


def test_complete_report_and_reproducible_text():
    raw = session(character(1, flow("send_stamina.noop")), character(2))
    report = build_session_report(raw)
    assert report.status is ReportStatus.COMPLETE
    assert report.counts.complete == 2
    assert report.flows_completed == report.advances_completed == 2
    assert report.data_gaps == ()
    assert len(report.characters) == 2
    assert render_session_report(report) == (
        "Session completed — 2/2\nDuration: 01:29:58\nFlows completed: 2\n"
        "Advances / rotation: 2\n\nCharacters:\n2 complete\n"
        "0 business / Daily incomplete\n0 technical failure\n0 cancelled\n\n"
        "2 characters had no issues."
    )
    assert build_session_report(raw) == report


@pytest.mark.parametrize(("name", "kind"), [
    ("black_market", "low_gold"), ("black_market", "inventory_full"),
    ("send_stamina", SEND_STAMINA_DAILY_PENDING),
    ("send_stamina", "send_stamina.all_no_effect"),
    ("summon_pet_daily", "summon_pet_daily.insufficient_gold"),
    ("summon_pet_daily", "summon_pet_daily.space_relief_unavailable"),
    ("summon_pet_daily", "summon_pet_daily.manual_resolution"),
    ("mailbox", "mailbox.claims_leftover"), ("mailbox", "mailbox.claim_all_no_effect"),
    ("world_boss", "world_boss.insufficient_sapphires"),
    ("world_boss", "world_boss.inventory_full"), ("world_boss", "world_boss.bag_full"),
    ("world_boss", "world_boss.meteor_full"),
])
def test_current_business_outcomes_are_not_technical_failures(name, kind):
    report = build_session_report(session(character(1, flow(kind)), names=(name,)))
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE
    assert report.counts.business_incomplete == 1
    assert report.counts.technical_failure == 0
    assert report.flows_completed == 1  # Technical contract completed normally.
    assert report.failure is None
    assert report.characters[0].flows[0].reasons
    assert "Evidence reference" not in render_session_report(report)


@pytest.mark.parametrize("name", ["send_stamina", "summon_pet_daily", "guild_check_in",
                                 "daily_quests", "mailbox"])
def test_noop_is_complete(name):
    report = build_session_report(session(character(1, flow(f"{name}.noop")), names=(name,)))
    assert report.status is ReportStatus.COMPLETE
    assert report.characters[0].flows[0].no_op


def test_previous_world_boss_rewards_do_not_prevent_success():
    report = build_session_report(session(character(1, flow("world_boss.previous_rewards")),
                                          names=("world_boss",)))
    assert report.status is ReportStatus.COMPLETE


def test_mixed_characters_and_final_outcome_reason_deduplication():
    pending = flow("send_stamina.all_executed", "send_stamina.all_no_effect",
                   "send_stamina.daily_pending", "send_stamina.daily_pending")
    report = build_session_report(session(character(1), character(2, pending), character(3)))
    assert report.counts.complete == 2
    assert report.counts.business_incomplete == 1
    assert len(report.characters[1].flows[0].reasons) == 1
    assert "no eligible friends" not in render_session_report(report)


def test_unavailable_pet_relief_does_not_invent_no_material_causality():
    report = build_session_report(session(character(1, flow(
        "summon_pet_daily.space_relief_unavailable", "summon_pet_daily.manual_resolution",
    )), names=("summon_pet_daily",)))
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE
    assert "pet space relief unavailable" in render_session_report(report)
    assert "no material" not in render_session_report(report)


@pytest.mark.parametrize("result_type", [SendStaminaFlowResult, SummonPetDailyFlowResult])
def test_typed_pending_flag_survives_partial_legacy_events(result_type):
    report = build_session_report(session(character(1, result_type(
        FlowStatus.COMPLETED, daily_pending=True,
    ))))
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE
    assert report.characters[0].flows[0].reasons[0].message == "Daily remains pending"


@pytest.mark.parametrize("evidence", [None, "file:///removed%20bundle/failure.json"])
def test_failure_preserves_cause_and_optional_reference_without_io(evidence, monkeypatch):
    cause = FailureCause("state_wait_timeout", "sequence=123 poll_count=500 UNKNOWN",
                         exception_type="RuntimeWaitTimeout", step="runtime_wait",
                         sequence=123, evidence_ref=evidence)
    raw = session(character(1, flow(status=FlowStatus.FAILED, failure=cause), completed=False),
                  status=SessionStatus.FAILED, failure=cause, failure_character_index=1,
                  failure_flow="send_stamina", expected=28)
    monkeypatch.setattr("pathlib.Path.exists", lambda *a: pytest.fail("builder must not inspect evidence"))
    report = build_session_report(raw)
    assert report.failure is cause
    assert report.characters[0].failure is cause
    assert report.characters[0].flows[0].failure is cause
    assert report.status is ReportStatus.TECHNICAL_FAILURE
    assert report.counts.technical_failure == 1
    text = render_session_report(report)
    assert "state_wait_timeout" in text
    for noise in ("sequence", "poll_count", "UNKNOWN", "runtime_wait"):
        assert noise not in text
    if evidence:
        assert text.count(evidence) == 1
    else:
        assert "Evidence reference" not in text


def test_cancellation_after_complete_and_business_incomplete_characters():
    raw = session(character(1), character(2, flow(SEND_STAMINA_DAILY_PENDING)),
                  character(3, flow(status=FlowStatus.CANCELLED, failure=FailureCause(
                      "cancelled", "stop", evidence_ref="must-not-render",
                  )), completed=False), status=SessionStatus.CANCELLED, expected=28)
    report = build_session_report(raw)
    assert report.status is ReportStatus.CANCELLED
    assert (report.counts.complete, report.counts.business_incomplete, report.counts.cancelled) == (1, 1, 1)
    assert report.counts.technical_failure == 0
    assert "must-not-render" not in render_session_report(report)


def test_cancel_before_first_character_does_not_invent_a_character():
    report = build_session_report(session(status=SessionStatus.CANCELLED, expected=28))
    assert report.status is ReportStatus.CANCELLED
    assert report.characters == ()
    assert report.counts.cancelled == 0


def test_cancel_between_flows_or_before_rotation():
    report = build_session_report(session(character(completed=False), status=SessionStatus.CANCELLED))
    assert report.characters[0].status is ReportStatus.CANCELLED
    assert report.flows_completed == 1
    assert report.advances_completed == 0


@pytest.mark.parametrize("has_flow_result", [True, False])
def test_runner_failure_before_flow_or_after_its_postcondition(has_flow_result):
    cause = FailureCause("postcondition_rejected", "raw diagnostics")
    char = SessionCharacterResult(1, CharacterContext(), (flow(),) if has_flow_result else ())
    report = build_session_report(session(char, status=SessionStatus.FAILED,
                                          failure_character_index=1, failure_flow="send_stamina",
                                          failure=cause))
    assert report.counts.technical_failure == 1
    assert report.flows_completed == 0
    assert len(report.characters[0].flows) == 1
    assert report.characters[0].flows[0].status is ReportStatus.TECHNICAL_FAILURE


def test_rotation_failure_preserves_completed_flows_and_business_reasons():
    cause = FailureCause("rotation_failure", "failed", evidence_ref="file:///rotation/failure.json")
    char = character(1, flow(SEND_STAMINA_DAILY_PENDING), completed=False,
                     advance=RotationResult(RotationOutcome.ABORTED, failure=cause))
    report = build_session_report(session(char, status=SessionStatus.FAILED,
                                          failure_character_index=1, failure=cause))
    assert report.status is ReportStatus.TECHNICAL_FAILURE
    assert report.flows_completed == 1
    assert report.characters[0].flows[0].status is ReportStatus.BUSINESS_INCOMPLETE
    assert not report.characters[0].advance_completed
    assert render_session_report(report).count(cause.evidence_ref) == 1


def test_class_and_fallback_labels_preserve_execution_order():
    char = replace(character(2, flow(), flow()), character_context=CharacterContext("Kaiserin", .99))
    raw = session(char, character(1, flow(), flow()), names=("world_boss", "black_market"))
    report = build_session_report(raw)
    assert [c.label for c in report.characters] == ["Character 1", "Kaiserin"]
    assert [f.flow_id for f in report.characters[0].flows] == ["world_boss", "black_market"]
    assert "Kaiserin" not in render_session_report(report)
    assert "2 characters had no issues." in render_session_report(report)
    assert raw.character_results[0] is char


def test_compact_renderer_hides_clean_characters_and_flows():
    ok = character(1, flow("send_stamina.noop"), flow("send_stamina.noop"))
    mixed = SessionCharacterResult(
        2, CharacterContext(),
        (flow("send_stamina.noop"), flow(SEND_STAMINA_DAILY_PENDING)),
        advance_result=None, completed=True,
    )
    report = build_session_report(session(ok, mixed, names=("send_stamina", "send_stamina")))
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE
    assert (report.counts.complete, report.counts.business_incomplete) == (1, 1)
    text = render_session_report(report)
    assert "Character 1" not in text
    assert "Character 2" in text
    assert ": complete" not in text
    assert "business / Daily incomplete" in text
    assert "Daily still pending" in text
    assert "1 character had no issues." in text


def test_compact_renderer_shows_skip_only_with_other_issues():
    skipped = flow(status=FlowStatus.SKIPPED_NOT_ELIGIBLE, skip_reason="Daily badge")
    clean = character(1, flow("send_stamina.noop"), skipped)
    report = build_session_report(session(clean, names=("send_stamina", "world_boss")))
    assert report.characters[0].status is ReportStatus.COMPLETE
    assert "skipped (not eligible)" not in render_session_report(report)
    troubled = SessionCharacterResult(
        2, CharacterContext(), (skipped, flow(SEND_STAMINA_DAILY_PENDING)),
        advance_result=None, completed=True,
    )
    report = build_session_report(session(clean, troubled, names=("world_boss", "send_stamina")))
    text = render_session_report(report)
    assert "Character 2" in text
    assert "skipped (not eligible): Daily badge" in text
    assert "1 character had no issues." in text


def test_legacy_aggregate_only_does_not_fabricate_completion_or_details():
    report = build_session_report(SessionResult(SessionStatus.COMPLETED, 28, 28, ()))
    assert report.status is None
    assert report.execution_status is SessionStatus.COMPLETED
    assert report.characters_processed == 28
    assert report.counts.complete == 0
    assert report.duration is None
    assert report.data_gaps
    assert "28/?" in render_session_report(report)


def test_legacy_failure_without_cause_remains_failure():
    report = build_session_report(SessionResult(SessionStatus.FAILED, 0, 0, ()))
    assert report.status is ReportStatus.TECHNICAL_FAILURE
    assert report.failure is None
    assert "cause unavailable" in render_session_report(report)


def test_legacy_error_string_is_not_parsed_and_stays_accessible():
    report = build_session_report(SessionResult(SessionStatus.FAILED, 0, 0, (),
                                               failure_cause="RuntimeWaitTimeout: sequence=3"))
    assert report.failure.type == "session_failure"
    assert report.failure.exception_type is None
    assert "sequence" not in render_session_report(report)


def test_unknown_business_event_is_unassessed_not_invented_failure_or_success():
    report = build_session_report(session(character(1, flow("future.new_outcome"))))
    assert report.status is None
    assert report.counts.unassessed == 1
    assert report.counts.technical_failure == 0


def test_partial_flow_plan_and_expected_characters_do_not_claim_complete():
    raw = session(character(1), names=("send_stamina", "mailbox"), expected=28)
    report = build_session_report(raw)
    assert report.status is None
    assert report.counts.unassessed == 1
    assert len(report.characters[0].flows) == 1


def test_raw_diagnostic_fields_details_and_error_do_not_become_business_reasons():
    raw_flow = flow("send_stamina.noop")
    raw_flow = replace(raw_flow, events=(FlowEvent("send_stamina.noop", "no eligible friends",
        fields={"sequence": 123, "retry": 9, "confidence": .5, "operation_id": "secret-noise"}),))
    report = build_session_report(session(character(1, raw_flow)))
    text = render_session_report(report)
    assert report.status is ReportStatus.COMPLETE
    for noise in ("sequence", "retry", "confidence", "operation_id", "secret-noise", "eligible friends"):
        assert noise not in text


def test_builder_and_renderer_are_immutable_and_do_not_change_input():
    raw = session(character(1, flow(SEND_STAMINA_DAILY_PENDING)))
    original = repr(raw)
    report = build_session_report(raw)
    text = render_session_report(report)
    assert text == render_session_report(build_session_report(raw))
    assert repr(raw) == original
    with pytest.raises(FrozenInstanceError):
        report.status = ReportStatus.COMPLETE


def test_labels_are_copied_and_legacy_metadata_only_fills_missing_values():
    raw = session(character(), names=("send_stamina",))
    labels = {"send_stamina": "Friends Daily"}
    report = build_session_report(raw, expected_character_count=28, flow_names=("wrong",), flow_labels=labels)
    labels["send_stamina"] = "changed"
    assert report.expected_character_count == 1
    assert report.characters[0].flows[0].label == "Friends Daily"
    legacy = SessionResult(SessionStatus.COMPLETED, 1, 1, (character(),))
    assert build_session_report(legacy).characters[0].flows[0].label == "Flow 1"
    assert build_session_report(legacy, flow_names=("send_stamina",)).characters[0].flows[0].flow_id == "send_stamina"


def test_repeated_flow_precondition_failure_does_not_relabel_previous_success():
    raw = session(character(1), status=SessionStatus.FAILED, names=("mailbox", "mailbox"),
                  failure_character_index=1, failure_flow="mailbox", failure_flow_position=1)
    report = build_session_report(raw)
    assert [f.status for f in report.characters[0].flows] == [
        ReportStatus.COMPLETE, ReportStatus.TECHNICAL_FAILURE,
    ]
    assert report.flows_completed == 1


def test_legacy_repeated_flow_failure_exposes_ambiguity_without_rewriting_successes():
    raw = session(character(1), status=SessionStatus.FAILED, names=("mailbox", "mailbox"),
                  failure_character_index=1, failure_flow="mailbox")
    report = build_session_report(raw)
    assert report.characters[0].flows[0].status is ReportStatus.COMPLETE
    assert any("occurrence unavailable" in gap for gap in report.data_gaps)
