from dataclasses import dataclass

import pytest

from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
)
from bot.component_contracts import (
    ComponentContract,
    ComponentRequirement,
    QUICK_MENU_ACCESS_REQUIREMENT,
)
from bot.flow_contracts import (
    FlowContract,
    FlowEvent,
    FlowResult,
    FlowScope,
    FlowStatus,
)
from bot.preconditions import MinimalPreconditionEnsurer
from bot.quick_menu import QuickMenuPolicy
from bot.rotation import RotationOutcome, RotationResult
from bot.session import CharacterContext, SessionPlan, SessionRunner, SessionStatus
from bot.world_boss_flow import WorldBossFlow


class Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


@dataclass
class Flow:
    name: str
    results: list[FlowResult]
    trace: list[str]
    contract: FlowContract = FlowContract(
        ComponentRequirement.exact_state(SCREEN_LOBBY),
        (ComponentRequirement.exact_state(SCREEN_LOBBY),),
    )
    scope = FlowScope.PER_CHARACTER

    def run(self):
        self.trace.append(f"{self.name}.run")
        return self.results.pop(0)


class Rotation:
    def __init__(self, character_count, trace, results=None):
        self.character_count = character_count
        self.trace = trace
        self.results = list(results or [])
        self.calls = 0
        self.contract = ComponentContract(
            QUICK_MENU_ACCESS_REQUIREMENT,
            (ComponentRequirement.exact_state(SCREEN_LOBBY),),
        )

    def advance(self):
        self.calls += 1
        self.trace.append("rotation.advance")
        if self.results:
            return self.results.pop(0)
        return RotationResult(RotationOutcome.SUCCESS)


def _runner(
    count,
    flows,
    rotation,
    *,
    trace=None,
    context_values=None,
    default_context=SCREEN_LOBBY,
    navigate_to_lobby=None,
    navigate_to_pets_manage=None,
    navigate_to_guild=None,
    quick_menu_policy=None,
    cancel_requested=lambda: False,
    context_factory=None,
):
    events = Events()
    context_values = list(context_values or [])

    def current_context():
        if trace is not None:
            trace.append("context.check")
        return context_values.pop(0) if context_values else default_context

    precondition_args = {}
    if quick_menu_policy is not None:
        precondition_args["quick_menu_policy"] = quick_menu_policy

    runner = SessionRunner(
        SessionPlan(count, tuple(flows), rotation),
        preconditions=MinimalPreconditionEnsurer(
            current_context,
            navigate_to_lobby=navigate_to_lobby,
            navigate_to_pets_manage=navigate_to_pets_manage,
            navigate_to_guild=navigate_to_guild,
            **precondition_args,
        ),
        events=events,
        cancel_requested=cancel_requested,
        character_context_factory=context_factory,
    )
    return runner, events


def test_one_character_one_flow_one_advance_and_default_context():
    trace = []
    flow = Flow("one", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(1, [flow], rotation, trace=trace)

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert result.characters_processed == 1
    assert result.advances_completed == 1
    assert result.character_results[0].index == 1
    assert result.character_results[0].character_context == CharacterContext()
    assert result.character_results[0].character_context.name is None
    assert result.character_results[0].completed
    assert result.expected_character_count == 1
    assert result.flow_names == ("one",)
    assert result.duration >= 0
    assert trace == [
        "context.check",
        "one.run",
        "context.check",
        "context.check",
        "rotation.advance",
        "context.check",
    ]


def test_configurable_n_runs_every_flow_and_advance_exactly_n_times():
    trace = []
    count = 4
    first = Flow(
        "first", [FlowResult(FlowStatus.COMPLETED) for _ in range(count)], trace
    )
    second = Flow(
        "second", [FlowResult(FlowStatus.COMPLETED) for _ in range(count)], trace
    )
    rotation = Rotation(count, trace)
    runner, _ = _runner(count, [first, second], rotation)

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert rotation.calls == count
    assert trace == [
        item
        for _ in range(count)
        for item in ("first.run", "second.run", "rotation.advance")
    ]
    assert [item.index for item in result.character_results] == [1, 2, 3, 4]


def test_daily_quests_and_mailbox_are_final_flows_before_rotation():
    trace = []
    prior = Flow("world_boss", [FlowResult(FlowStatus.COMPLETED)], trace)
    daily = Flow("daily_quests", [FlowResult(FlowStatus.COMPLETED)], trace)
    mailbox = Flow("mailbox", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(1, [prior, daily, mailbox], rotation)

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert trace == [
        "world_boss.run",
        "daily_quests.run",
        "mailbox.run",
        "rotation.advance",
    ]


def test_business_events_are_aggregated_logged_and_do_not_abort():
    trace = []
    flow = Flow(
        "black_market",
        [
            FlowResult(
                FlowStatus.COMPLETED,
                events=(FlowEvent("low_gold"), FlowEvent("inventory_full")),
            )
        ],
        trace,
    )
    rotation = Rotation(1, trace)
    runner, events = _runner(1, [flow], rotation)

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert result.low_gold_count == 1
    assert result.inventory_full_count == 1
    assert rotation.calls == 1
    for name in ("black_market.low_gold", "black_market.inventory_full"):
        records = [fields for event, fields in events.records if event == name]
        assert len(records) == 1
        expected = {
            "character_index": 1, "character_name": None,
            "flow": "black_market", "detail": None, "event_role": "business",
        }
        assert expected.items() <= records[0].items()
        assert records[0]["created_at"]


def test_already_qualified_business_event_is_not_double_prefixed():
    trace = []
    flow = Flow(
        "world_boss",
        [
            FlowResult(
                FlowStatus.COMPLETED,
                events=(FlowEvent("world_boss.insufficient_sapphires"),),
            )
        ],
        trace,
    )
    runner, events = _runner(1, [flow], Rotation(1, trace))

    runner.run()

    names = [name for name, _ in events.records]
    assert "world_boss.insufficient_sapphires" in names
    assert "world_boss.world_boss.insufficient_sapphires" not in names


def test_flow_failure_aborts_without_advance_or_next_character():
    trace = []
    flow = Flow(
        "black_market",
        [FlowResult(FlowStatus.FAILED, error="technical")],
        trace,
    )
    rotation = Rotation(3, trace)
    runner, _ = _runner(3, [flow], rotation)

    result = runner.run()

    assert result.status is SessionStatus.FAILED
    assert result.failure_character_index == 1
    assert result.failure_flow == "black_market"
    assert result.failure_cause == "technical"
    assert result.characters_processed == 0
    assert result.advances_completed == 0
    assert trace == ["black_market.run"]


def test_partial_progress_is_preserved_when_later_character_fails():
    trace = []
    flow = Flow(
        "black_market",
        [
            FlowResult(FlowStatus.COMPLETED),
            FlowResult(FlowStatus.FAILED, error="lost_lobby"),
        ],
        trace,
    )
    rotation = Rotation(3, trace)
    runner, _ = _runner(3, [flow], rotation)

    result = runner.run()

    assert result.status is SessionStatus.FAILED
    assert result.characters_processed == 1
    assert result.advances_completed == 1
    assert len(result.character_results) == 2
    assert result.character_results[0].completed
    assert not result.character_results[1].completed


def test_completed_flow_without_lobby_is_composition_failure():
    trace = []
    flow = Flow("black_market", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(2, trace)
    runner, _ = _runner(
        2,
        [flow],
        rotation,
        context_values=[SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT],
    )

    result = runner.run()

    assert result.status is SessionStatus.FAILED
    assert result.failure_flow == "black_market"
    assert result.failure_cause == "flow_completed_outside_successful_postconditions"
    assert rotation.calls == 0


def test_rotation_failure_aborts_before_next_character():
    trace = []
    flow = Flow("black_market", [FlowResult(FlowStatus.COMPLETED)] * 2, trace)
    rotation = Rotation(
        2,
        trace,
        [RotationResult(RotationOutcome.ABORTED, error="selection_failed")],
    )
    runner, _ = _runner(2, [flow], rotation)

    result = runner.run()

    assert result.status is SessionStatus.FAILED
    assert result.failure_flow is None
    assert result.failure_cause == "selection_failed"
    assert result.advances_completed == 0
    assert trace == ["black_market.run", "rotation.advance"]


def test_cancel_before_first_flow_is_not_failure():
    trace = []
    flow = Flow("black_market", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(1, [flow], rotation, cancel_requested=lambda: True)

    result = runner.run()

    assert result.status is SessionStatus.CANCELLED
    assert result.character_results == ()
    assert rotation.calls == 0


def test_cancel_between_flow_and_advance_preserves_flow_result():
    trace = []
    checks = iter((False, False, True))
    flow = Flow("black_market", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(
        1,
        [flow],
        rotation,
        cancel_requested=lambda: next(checks),
    )

    result = runner.run()

    assert result.status is SessionStatus.CANCELLED
    assert len(result.character_results[0].flow_results) == 1
    assert not result.character_results[0].completed
    assert rotation.calls == 0


def test_flow_cancelled_result_propagates_as_session_cancellation():
    trace = []
    flow = Flow("world_boss", [FlowResult(FlowStatus.CANCELLED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(1, [flow], rotation)

    result = runner.run()

    assert result.status is SessionStatus.CANCELLED
    assert result.failure_cause is None
    assert rotation.calls == 0


def test_character_context_factory_runs_once_per_processed_character():
    trace = []
    requested = []
    flow = Flow("black_market", [FlowResult(FlowStatus.COMPLETED)] * 2, trace)
    rotation = Rotation(2, trace)

    def context_factory(index):
        requested.append(index)
        return CharacterContext(name=None)

    runner, _ = _runner(2, [flow], rotation, context_factory=context_factory)

    result = runner.run()

    assert requested == [1, 2]
    assert all(item.character_context.name is None for item in result.character_results)


@pytest.mark.parametrize("fails", [False, True])
def test_identity_after_first_ensure_is_nonfatal_and_preserves_gameplay_and_events(fails):
    def execute(factory_enabled):
        trace, requested = [], []
        flows = [Flow(name, [FlowResult(FlowStatus.COMPLETED, (FlowEvent("low_gold"),))] * 2, trace)
                 for name in ("black_market", "other")]
        rotation = Rotation(2, trace)

        def factory(index):
            assert trace[-1] == "context.check"
            requested.append(index)
            if fails:
                raise RuntimeError("recognizer failed")
            return CharacterContext("Kaiserin" if index == 1 else "Blade Dancer", .99)

        runner, events = _runner(2, flows, rotation, trace=trace,
                                 context_factory=factory if factory_enabled else None)
        result = runner.run()
        return result, trace, requested, events.records

    baseline, baseline_trace, _, baseline_events = execute(False)
    result, trace, requested, events = execute(True)
    assert requested == [1, 2]
    assert trace == baseline_trace
    assert [event for event, _ in events] == [event for event, _ in baseline_events]
    assert result.status == baseline.status == SessionStatus.COMPLETED
    assert result.advances_completed == baseline.advances_completed == 2
    labels = [c.character_context.name for c in result.character_results]
    assert labels == ([None, None] if fails else ["Kaiserin", "Blade Dancer"])
    starts = [fields for event, fields in events if event == "session.character.started"]
    assert all(fields["character_name"] is None for fields in starts)
    for event, fields in events:
        if event in {"flow.started", "black_market.low_gold", "session.character.completed"}:
            assert fields["character_name"] == labels[fields["character_index"] - 1]


def test_failed_first_precondition_still_gets_optional_context_once_without_running_flow():
    requested = []
    trace = []
    flow = Flow("one", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    def factory(index):
        requested.append(index)
        return CharacterContext()
    runner, _ = _runner(1, [flow], rotation, default_context=None, context_factory=factory)
    result = runner.run()
    assert result.status is SessionStatus.FAILED
    assert requested == [1]
    assert trace == []
    assert rotation.calls == 0


def test_plan_rejects_non_per_character_flow_and_count_mismatch():
    trace = []
    flow = Flow("bad", [FlowResult(FlowStatus.COMPLETED)], trace)
    flow.scope = "session"

    with pytest.raises(ValueError, match="PER_CHARACTER"):
        SessionPlan(1, (flow,), Rotation(1, trace))

    good = Flow("good", [FlowResult(FlowStatus.COMPLETED)], trace)
    with pytest.raises(ValueError, match="must match"):
        SessionPlan(2, (good,), Rotation(1, trace))


def test_session_does_not_normalize_lobby_when_rotation_only_needs_capability():
    trace = []
    capable_policy = QuickMenuPolicy(
        frozenset({SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT})
    )
    flow = Flow(
        "multi_exit",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        FlowContract(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
            (
                ComponentRequirement.exact_state(SCREEN_LOBBY),
                ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),
            ),
        ),
    )
    rotation = Rotation(1, trace)
    navigation_calls = []
    runner, _ = _runner(
        1,
        [flow],
        rotation,
        context_values=[
            SCREEN_LOBBY,
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_LOBBY,
        ],
        navigate_to_lobby=lambda: navigation_calls.append(True) or True,
        quick_menu_policy=capable_policy,
    )

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert navigation_calls == []
    assert rotation.calls == 1


@pytest.mark.parametrize("successful_context", [SCREEN_LOBBY, "screen.world_boss"])
def test_session_accepts_both_declared_world_boss_success_postconditions(
    successful_context,
):
    trace = []
    flow = Flow(
        "world_boss",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        WorldBossFlow.contract,
    )
    rotation = Rotation(1, trace)
    runner, _ = _runner(
        1,
        [flow],
        rotation,
        context_values=[
            SCREEN_LOBBY,
            successful_context,
            successful_context,
            SCREEN_LOBBY,
        ],
    )

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert rotation.calls == 1


def test_session_normalizes_through_quick_menu_for_next_exact_lobby_flow():
    trace = []
    capable_policy = QuickMenuPolicy(
        frozenset({SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT})
    )
    first = Flow(
        "multi_exit",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        FlowContract(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
            (ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),),
        ),
    )
    second = Flow(
        "lobby_only",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
    )
    rotation = Rotation(1, trace)
    navigation_calls = []
    runner, _ = _runner(
        1,
        [first, second],
        rotation,
        context_values=[
            SCREEN_LOBBY,
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_LOBBY,
            SCREEN_LOBBY,
            SCREEN_LOBBY,
            SCREEN_LOBBY,
            SCREEN_LOBBY,
        ],
        navigate_to_lobby=lambda: navigation_calls.append("quick_menu_to_lobby") or True,
        quick_menu_policy=capable_policy,
    )

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert navigation_calls == ["quick_menu_to_lobby"]
    assert trace.count("lobby_only.run") == 1


@pytest.mark.parametrize("pet_exit", [SCREEN_PETS_MANAGE, SCREEN_PET_SUMMON])
def test_session_chains_pet_exit_directly_to_guild_without_lobby(pet_exit):
    trace = []
    pet = Flow(
        "summon_pet_daily",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        FlowContract(
            ComponentRequirement.exact_state(SCREEN_PETS_MANAGE),
            (
                ComponentRequirement.exact_state(SCREEN_PETS_MANAGE),
                ComponentRequirement.exact_state(SCREEN_PET_SUMMON),
            ),
        ),
    )
    guild = Flow(
        "guild_check_in",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        FlowContract(
            ComponentRequirement.exact_state(SCREEN_GUILD),
            (ComponentRequirement.exact_state(SCREEN_GUILD),),
        ),
    )
    rotation = Rotation(1, trace)
    navigation_calls = []
    runner, _ = _runner(
        1,
        [pet, guild],
        rotation,
        context_values=[
            SCREEN_PETS_MANAGE,
            pet_exit,
            pet_exit,
            SCREEN_GUILD,
            SCREEN_GUILD,
            SCREEN_GUILD,
            SCREEN_LOBBY,
        ],
        navigate_to_lobby=lambda: navigation_calls.append("lobby") or True,
        navigate_to_guild=lambda: navigation_calls.append("guild") or True,
    )

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert navigation_calls == ["guild"]
    assert trace[:2] == ["summon_pet_daily.run", "guild_check_in.run"]


def test_session_aborts_when_required_lobby_normalization_fails():
    trace = []
    capable_policy = QuickMenuPolicy(
        frozenset({SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT})
    )
    first = Flow(
        "multi_exit",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        FlowContract(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
            (ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),),
        ),
    )
    second = Flow("lobby_only", [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(
        1,
        [first, second],
        rotation,
        context_values=[
            SCREEN_LOBBY,
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_BATTLE_MODE_SELECT,
        ],
        navigate_to_lobby=lambda: False,
        quick_menu_policy=capable_policy,
    )

    result = runner.run()

    assert result.status is SessionStatus.FAILED
    assert result.failure_flow == "lobby_only"
    assert result.failure_cause.startswith("flow_precondition_failed")
    assert "lobby_only.run" not in trace
    assert rotation.calls == 0


def test_session_daily_quests_only_uses_lobby_precondition_not_pets():
    """
    Regression: isolated daily_quests session should use screen.lobby precondition,
    never emit precondition.open_pets transition.
    """
    from bot.daily_quests_flow import DailyQuestsFlow

    trace = []
    # Track which transitions are executed
    transitions_executed = []

    daily = Flow(
        "daily_quests",
        [FlowResult(FlowStatus.COMPLETED)],
        trace,
        contract=DailyQuestsFlow.contract,
    )
    rotation = Rotation(1, trace)

    navigate_to_pets_called = []
    def mock_navigate_to_pets():
        navigate_to_pets_called.append(True)
        transitions_executed.append("precondition.open_pets")
        return True

    navigate_to_lobby_called = []
    def mock_navigate_to_lobby():
        navigate_to_lobby_called.append(True)
        transitions_executed.append("precondition.open_lobby")
        return True

    runner, events = _runner(
        1,
        [daily],
        rotation,
        trace=trace,
        navigate_to_lobby=mock_navigate_to_lobby,
        navigate_to_pets_manage=mock_navigate_to_pets,
        context_values=[SCREEN_LOBBY],  # Start in Lobby
    )

    result = runner.run()

    assert result.status is SessionStatus.COMPLETED
    assert result.characters_processed == 1
    assert result.advances_completed == 1
    # Flow should run
    assert "daily_quests.run" in trace
    # Should NOT call navigate_to_pets_manage (no precondition.open_pets)
    assert len(navigate_to_pets_called) == 0
    # Should not execute precondition.open_pets transition
    assert "precondition.open_pets" not in transitions_executed
    # The key assertion: no pets_manage navigation for daily_quests
    assert all("pets" not in t for t in transitions_executed)


@pytest.mark.parametrize("flow_status", [FlowStatus.COMPLETED, FlowStatus.FAILED, FlowStatus.CANCELLED])
def test_report_projection_preserves_runner_actions_policy_and_single_publication(flow_status, monkeypatch):
    from bot.session_report import build_session_report, render_session_report

    clock = iter((20.0, 25.0))
    monkeypatch.setattr("bot.session.perf_counter", lambda: next(clock))
    trace = []
    flow = Flow("send_stamina", [FlowResult(
        flow_status, (FlowEvent("send_stamina.daily_pending"),),
        error="failure" if flow_status is FlowStatus.FAILED else None,
    )], trace)
    rotation = Rotation(1, trace)
    runner, events = _runner(1, [flow], rotation)
    result = runner.run()
    before_trace, before_events = list(trace), list(events.records)
    for _ in range(2):
        render_session_report(build_session_report(result))
    assert trace == before_trace
    assert events.records == before_events
    assert rotation.calls == int(flow_status is FlowStatus.COMPLETED)
    assert len([name for name, _ in events.records if name == "send_stamina.daily_pending"]) == 1
    assert result.duration == 5.0
    assert result.flow_names == ("send_stamina",)
    assert result.expected_character_count == 1


def test_report_identifies_second_occurrence_of_repeated_flow():
    from bot.session_report import ReportStatus, build_session_report

    trace = []
    first = Flow("mailbox", [FlowResult(FlowStatus.COMPLETED)], trace)
    second = Flow("mailbox", [FlowResult(FlowStatus.FAILED, error="failed")], trace)
    runner, _ = _runner(1, [first, second], Rotation(1, trace))
    raw = runner.run()
    report = build_session_report(raw)
    assert raw.failure_flow_position == 1
    assert [f.status for f in report.characters[0].flows] == [
        ReportStatus.COMPLETE, ReportStatus.TECHNICAL_FAILURE,
    ]
    assert report.flows_completed == 1
