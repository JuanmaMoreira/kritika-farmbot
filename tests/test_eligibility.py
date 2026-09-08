from types import SimpleNamespace

import pytest

from bot.catalog import SCREEN_LOBBY
from bot.eligibility import EligibilityResult, EligibilityStatus
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.preconditions import MinimalPreconditionEnsurer
from bot.session import CharacterContext, SessionPlan, SessionRunner, SessionStatus
from bot.session_report import ReportStatus, build_session_report, render_session_report
from test_session import Events, Flow, Rotation


def run_decision(decision, *, count=1, cancel_requested=lambda: False, return_context=SCREEN_LOBBY):
    trace = []
    calls = []
    flows = tuple(Flow(name, [FlowResult(FlowStatus.COMPLETED) for _ in range(count)], trace)
                  for name in ("black_market", "world_boss", "send_stamina"))

    def evaluate():
        calls.append("evaluate")
        if isinstance(decision, Exception):
            raise decision
        return decision

    check = SimpleNamespace(evaluate=evaluate)
    rotation = Rotation(count, trace)
    plan = SessionPlan(count, flows, rotation, eligibility=(None, check, None))
    events = Events()
    runner = SessionRunner(
        plan, events=events,
        preconditions=MinimalPreconditionEnsurer(
            lambda: return_context if calls else SCREEN_LOBBY),
        character_context_factory=lambda _: CharacterContext("Demon Blade", .96),
        cancel_requested=cancel_requested,
    )
    return runner.run(), trace, calls, events


@pytest.mark.parametrize("status", [EligibilityStatus.ELIGIBLE, EligibilityStatus.NOT_ELIGIBLE])
def test_routine_eligibility_preserves_order_rotation_identity_and_report(status):
    result, trace, calls, events = run_decision(EligibilityResult(status, "Daily badge"), count=2)
    skipped = status is EligibilityStatus.NOT_ELIGIBLE
    assert result.status is SessionStatus.COMPLETED
    assert result.advances_completed == 2
    expected = ["black_market.run", "send_stamina.run", "rotation.advance"]
    if not skipped:
        expected.insert(1, "world_boss.run")
    assert trace == expected * 2
    assert calls == ["evaluate"] * 2
    for character in result.character_results:
        assert character.character_context.name == "Demon Blade"
        assert character.flow_results[1].status is (
            FlowStatus.SKIPPED_NOT_ELIGIBLE if skipped else FlowStatus.COMPLETED)
    report = build_session_report(result)
    assert report.status is ReportStatus.COMPLETE
    assert report.counts.complete == 2
    assert report.counts.business_incomplete == report.counts.technical_failure == 0
    assert report.flows_completed == (4 if skipped else 6)
    before = list(events.records)
    assert render_session_report(report) == render_session_report(build_session_report(result))
    assert events.records == before
    wb_events = [name for name, fields in events.records if fields.get("flow") == "world_boss"]
    assert wb_events == (["flow.skipped_not_eligible"] * 2 if skipped
                         else ["flow.started", "flow.completed"] * 2)
    if skipped:
        assert "World Boss: skipped (not eligible): Daily badge" in render_session_report(report)
        assert not result.events


@pytest.mark.parametrize("decision", [
    EligibilityResult(EligibilityStatus.UNKNOWN, "unconfirmed"),
    EligibilityResult(EligibilityStatus.FAILED, "capture failed"),
    OSError("capture failed"), None, False,
])
def test_inconclusive_or_broken_check_aborts_without_flow_or_rotation(decision):
    result, trace, _, events = run_decision(decision)
    assert result.status is SessionStatus.FAILED
    assert trace == ["black_market.run"]
    assert result.failure_flow_position == 1
    assert result.failure_flow == "world_boss"
    assert result.failure is not None
    report = build_session_report(result)
    assert report.status is ReportStatus.TECHNICAL_FAILURE
    assert report.characters[0].flows[1].status is ReportStatus.TECHNICAL_FAILURE
    assert not any(name == "flow.skipped_not_eligible" for name, _ in events.records)


def test_evaluation_failure_preserves_evidence_reference():
    failure = FailureCause("capture", "failed", evidence_ref="file:///evidence/example")
    result, *_ = run_decision(EligibilityResult(EligibilityStatus.FAILED, "failed", failure))
    assert result.failure == failure
    assert build_session_report(result).characters[0].flows[1].failure == failure


def test_cancelled_evaluation_is_not_a_skip_or_failure():
    result, trace, _, events = run_decision(EligibilityResult(EligibilityStatus.CANCELLED, "cancelled"))
    assert result.status is SessionStatus.CANCELLED
    assert trace == ["black_market.run"]
    assert result.failure is None
    assert not any(name == "flow.skipped_not_eligible" for name, _ in events.records)


def test_skip_requires_verified_return_without_recovery_input():
    result, trace, *_ = run_decision(
        EligibilityResult(EligibilityStatus.NOT_ELIGIBLE, "absent"), return_context=None)
    assert result.status is SessionStatus.FAILED
    assert result.failure_cause == "eligibility_return_postcondition_failed"
    assert trace == ["black_market.run"]


def test_plan_checks_are_positional_and_optional():
    trace = []
    flow = Flow("world_boss", [FlowResult(FlowStatus.COMPLETED)], trace)
    plan = SessionPlan(1, (flow,), Rotation(1, trace))
    assert plan.eligibility == (None,)
    for checks in ((None, None), (False,)):
        with pytest.raises(ValueError, match="eligibility"):
            SessionPlan(1, (flow,), Rotation(1, trace), eligibility=checks)


def test_skip_has_no_business_outcomes_or_failure():
    for kwargs in ({}, {"skip_reason": "absent", "error": "failed"},
                   {"skip_reason": "absent", "failure": FailureCause("test", "failed")}):
        with pytest.raises(ValueError):
            FlowResult(FlowStatus.SKIPPED_NOT_ELIGIBLE, **kwargs)
    with pytest.raises(ValueError):
        FlowResult(FlowStatus.COMPLETED, skip_reason="absent")


def test_repeated_flow_skip_does_not_hide_failure_in_later_occurrence():
    trace = []
    flows = tuple(Flow("world_boss", [], trace) for _ in range(2))
    checks = tuple(SimpleNamespace(evaluate=lambda value=value: value) for value in (
        EligibilityResult(EligibilityStatus.NOT_ELIGIBLE, "absent"),
        EligibilityResult(EligibilityStatus.UNKNOWN, "unconfirmed"),
    ))
    result = SessionRunner(
        SessionPlan(1, flows, Rotation(1, trace), eligibility=checks), events=Events(),
        preconditions=MinimalPreconditionEnsurer(lambda: SCREEN_LOBBY),
    ).run()
    assert trace == []
    assert result.failure_flow_position == 1
    report = build_session_report(result)
    assert [f.status for f in report.characters[0].flows] == [
        ReportStatus.SKIPPED_NOT_ELIGIBLE, ReportStatus.TECHNICAL_FAILURE]


def test_cancel_during_final_eligibility_probe_does_not_become_technical_failure():
    trace, stopped = [], []
    preconditions = MinimalPreconditionEnsurer(lambda: SCREEN_LOBBY)

    def interrupted_probe(requirements):
        stopped.append(True)
        return False

    preconditions.current_satisfies_any = interrupted_probe
    check = SimpleNamespace(evaluate=lambda: EligibilityResult(EligibilityStatus.NOT_ELIGIBLE, "absent"))
    result = SessionRunner(
        SessionPlan(1, (Flow("world_boss", [], trace),), Rotation(1, trace), eligibility=(check,)),
        events=Events(), preconditions=preconditions, cancel_requested=lambda: bool(stopped),
    ).run()
    assert result.status is SessionStatus.CANCELLED
    assert result.failure is None
    assert not result.character_results[0].flow_results
    assert trace == []
