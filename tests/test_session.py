from dataclasses import dataclass

import pytest

from bot.flow_contracts import FlowEvent, FlowResult, FlowScope, FlowStatus
from bot.rotation import RotationOutcome, RotationResult
from bot.session import CharacterContext, SessionPlan, SessionRunner, SessionStatus


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
    lobby_values=None,
    cancel_requested=lambda: False,
    context_factory=None,
):
    events = Events()
    lobby_values = list(lobby_values or [])

    def lobby_available():
        if trace is not None:
            trace.append("lobby.check")
        return lobby_values.pop(0) if lobby_values else True

    runner = SessionRunner(
        SessionPlan(count, tuple(flows), rotation),
        lobby_available=lobby_available,
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
    assert trace == ["one.run", "lobby.check", "rotation.advance", "lobby.check"]


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
    assert ("black_market.low_gold", {"character_index": 1, "character_name": None}) in events.records
    assert ("black_market.inventory_full", {"character_index": 1, "character_name": None}) in events.records


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
    runner, _ = _runner(2, [flow], rotation, lobby_values=[False])

    result = runner.run()

    assert result.status is SessionStatus.FAILED
    assert result.failure_flow == "black_market"
    assert result.failure_cause == "flow_completed_without_lobby_postcondition"
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


def test_plan_rejects_non_per_character_flow_and_count_mismatch():
    trace = []
    flow = Flow("bad", [FlowResult(FlowStatus.COMPLETED)], trace)
    flow.scope = "session"

    with pytest.raises(ValueError, match="PER_CHARACTER"):
        SessionPlan(1, (flow,), Rotation(1, trace))

    good = Flow("good", [FlowResult(FlowStatus.COMPLETED)], trace)
    with pytest.raises(ValueError, match="must match"):
        SessionPlan(2, (good,), Rotation(1, trace))
