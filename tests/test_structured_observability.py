"""Hardware-free correlation, cardinality and fail-safe integration contracts."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier

import pytest

from bot.event_context import event_context, event_scope, operation_scope
from bot.event_log import JsonLineEventConsumer, RuntimeEventStream
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus, publish_flow_events
from bot.runtime_observer import RuntimeObserver, RuntimeWaitAborted, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.resolver import ContextResolver
from bot.semantic_actions import OpenQuickMenu
from bot.session import SessionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy
from test_runtime_observer import Clock, Perception, Source
from test_verified_transition import Actions, BEFORE, EXPECTED, ScriptedObserver, _snapshot, _timeout
from test_session import Flow, Rotation, _runner


def broken(*args, **kwargs):
    raise OSError("sink unavailable")


def test_context_is_nested_restored_and_isolated_between_workers():
    records = []
    stream = RuntimeEventStream((records.append,), run_id="test-run")
    barrier = Barrier(2)

    def worker(index):
        with event_scope(session_id=f"session-{index}", character_index=index, flow="daily_quests"):
            with operation_scope("outer") as outer:
                barrier.wait(timeout=5)
                with operation_scope("inner"):
                    stream.record("transition.started")
                assert event_context()["operation_id"] == outer["operation_id"]
        assert all(value is None for value in event_context().values())

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, (1, 2)))
    assert {r.fields["session_id"] for r in records} == {"session-1", "session-2"}
    for record in records:
        assert record.fields["run_id"] == "test-run"
        assert record.fields["parent_operation_id"] != record.fields["operation_id"]
        assert record.fields["session_id"] == f"session-{record.fields['character_index']}"
    with pytest.raises(RuntimeError), event_scope(flow="temporary"):
        raise RuntimeError("exit")
    assert event_context()["flow"] is None


def test_sink_failures_and_bad_diagnostic_clock_do_not_stop_other_consumers(tmp_path):
    records = []
    path = tmp_path / "events.jsonl"
    stream = RuntimeEventStream((broken, JsonLineEventConsumer(tmp_path), records.append, JsonLineEventConsumer(path)))
    stream.record("runtime.started")
    stream.record("runtime.completed")
    payloads = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == len(payloads) == 2
    assert [p["event_sequence"] for p in payloads] == [1, 2]
    assert len({p["run_id"] for p in payloads}) == 1
    RuntimeEventStream(now=broken).record("runtime.started")


class CostedPerception(Perception):
    def __init__(self, clock, fail=False):
        super().__init__()
        self.clock = clock
        self.fail = fail

    def analyze(self, frame):
        self.clock.value += 0.01
        if self.fail:
            raise ValueError("perception failed")
        return super().analyze(frame)


def observer_with_metrics(sequences, *, fail=False, sink=None):
    clock = Clock()
    records = []
    stream = RuntimeEventStream((records.append,))
    observer = RuntimeObserver(
        Source(sequences), CostedPerception(clock, fail), ContextResolver(),
        clock=clock, metrics_clock=clock, sleeper=clock.sleep,
        poll_interval=0.1, events=sink or stream,
    )
    return observer, records, clock


def test_wait_counts_stale_polls_and_preserves_analyze_cost_without_frame_events():
    observer, records, _ = observer_with_metrics([5, 5, 6])
    with event_scope(flow="mailbox", character_index=3), operation_scope("claim") as parent:
        result = observer.wait_until(lambda s: True, after_sequence=5, timeout=1)
    assert result.sequence == 6
    assert [r.event for r in records] == ["perception.analyze_summary", "runtime_wait.completed"]
    summary, wait = [r.fields for r in records]
    assert summary["analyze_count"] == 3
    assert summary["analyze_elapsed"] == pytest.approx(0.03)
    assert summary["analyze_max_elapsed"] == pytest.approx(0.01)
    assert wait["poll_count"] == 3 and wait["fresh_count"] == 1
    assert wait["elapsed"] == pytest.approx(0.23)
    assert wait["parent_operation_id"] == parent["operation_id"]
    assert summary["operation_id"] == wait["operation_id"]
    assert wait["flow"] == "mailbox" and wait["character_index"] == 3


@pytest.mark.parametrize("outcome,error_type", [
    ("timeout", RuntimeWaitTimeout), ("aborted", RuntimeWaitAborted),
    ("cancelled", RuntimeWaitCancelled), ("failed", ValueError),
])
def test_wait_terminal_metrics_and_exception_contract(outcome, error_type):
    observer, records, _ = observer_with_metrics([1, 2, 3, 4], fail=outcome == "failed")
    with pytest.raises(error_type) as caught:
        observer.wait_until(
            lambda s: False, after_sequence=0, timeout=0.2,
            abort_if=lambda s: outcome == "aborted",
            cancel_requested=lambda: outcome == "cancelled",
        )
    terminals = [r for r in records if r.event == "runtime_wait.completed"]
    assert len(terminals) == 1
    fields = terminals[0].fields
    assert fields["outcome"] == outcome
    assert fields["failure"]["exception_type"] == error_type.__name__
    assert fields["failure"]["evidence_ref"] is None
    if outcome != "failed":
        assert caught.value.poll_count == fields["poll_count"]
        assert caught.value.elapsed == fields["elapsed"]
    assert event_context()["operation_id"] is None


def test_perception_batch_is_bounded_and_preserves_original_context_on_flush():
    observer, records, _ = observer_with_metrics([1])
    with event_scope(flow="first", character_index=1):
        for _ in range(130):
            observer.observe()
    with event_scope(flow="second", character_index=2):
        observer.observe()
    observer.flush_analysis_metrics()
    observer.flush_analysis_metrics()
    assert [r.fields["analyze_count"] for r in records] == [64, 64, 2, 1]
    assert [r.fields["flow"] for r in records] == ["first", "first", "first", "second"]
    assert all(r.fields["run_id"] for r in records)
    assert sum(r.fields["analyze_elapsed"] for r in records) == pytest.approx(1.31)


def test_metrics_failures_preserve_wait_outcome_and_policy_clock_calls():
    class BadSink:
        record = staticmethod(broken)

    observer, _, _ = observer_with_metrics([1, 2, 3], sink=BadSink())
    observer._metrics_clock = broken
    assert observer.wait_until(lambda s: s.sequence == 3, after_sequence=0, timeout=1).sequence == 3
    assert observer.source.index == 3


def test_transition_has_single_correlated_terminal_with_retry_counts_and_elapsed():
    before, after = _snapshot(1, BEFORE), _snapshot(5, EXPECTED)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE)), after],
        [_snapshot(4, BEFORE)],
    )
    actions = Actions()
    records = []
    ticks = iter([2.0, 5.5])
    transition = VerifiedTransition(observer, actions, RuntimeEventStream((records.append,)), metrics_clock=lambda: next(ticks))
    result = transition.execute(
        "test.open", OpenQuickMenu(), before, expected=lambda s: s.state.base_context == EXPECTED,
        retryable_from=lambda s: s.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(max_attempts=2),
    )
    assert result.succeeded and result.attempt_count == len(actions.calls) == 2
    assert result.elapsed == 3.5
    terminals = [r for r in records if r.event == "transition.completed"]
    assert len(terminals) == 1
    assert terminals[0].fields["operation_id"] == result.operation_id
    assert terminals[0].fields["before_sequence"] == 1
    assert terminals[0].fields["final_sequence"] == 5
    assert {r.fields["operation_id"] for r in records} == {result.operation_id}


def test_transition_exception_preserves_string_and_structured_origin():
    records = []
    with event_scope(flow="black_market"):
        result = VerifiedTransition(
            ScriptedObserver([]), Actions(error=OSError("input failed")), RuntimeEventStream((records.append,)),
        ).execute("test.open", OpenQuickMenu(), _snapshot(7, BEFORE), expected=lambda s: True, policy=VerifiedTransitionPolicy())
    assert result.error == "OSError: input failed"
    assert result.failure.exception_type == "OSError"
    assert result.failure.sequence == 7
    assert result.failure.flow == "black_market"
    assert result.failure.step == "test.open"
    assert records[-1].fields["failure"] == result.failure.payload()


def test_transition_raised_cancel_has_terminal_without_changing_propagation():
    records = []
    error = RuntimeWaitCancelled("stop")
    transition = VerifiedTransition(ScriptedObserver([error]), Actions(), RuntimeEventStream((records.append,)))
    with pytest.raises(RuntimeWaitCancelled) as caught:
        transition.execute("test.open", OpenQuickMenu(), _snapshot(1, BEFORE), expected=lambda s: True, policy=VerifiedTransitionPolicy())
    assert caught.value is error
    assert records[-1].fields["outcome"] == "cancelled"
    assert records[-1].fields["attempt"] == 1
    assert event_context()["operation_id"] is None


def test_business_metadata_published_once_and_legacy_result_shape_is_compatible():
    records = []
    stream = RuntimeEventStream((records.append,))
    created = datetime(2026, 9, 7, tzinfo=timezone.utc)
    result = FlowResult(FlowStatus.COMPLETED, (FlowEvent(
        "low_gold", fields={"sequence": 7, "sapphires": 4}, created_at=created,
    ),))
    publish_flow_events(stream, "black_market", result.events)
    assert len(records) == 1
    assert records[0].event == "black_market.low_gold"
    assert records[0].fields["event_role"] == "business"
    assert records[0].fields["sapphires"] == 4
    assert records[0].fields["created_at"] == created.isoformat()
    assert result.events[0].created_at == created
    assert result.event_count("low_gold") == 1
    failure = FailureCause.from_error(ValueError("bad"), kind="exception", step="open", sequence=7)
    failed = FlowResult(FlowStatus.FAILED, (), "legacy string", failure=failure)
    assert failed.error == "legacy string" and failed.failure == failure
    assert replace(failed.failure, evidence_ref="future-reference").evidence_ref == "future-reference"


def test_session_propagates_context_to_nested_components_and_resets_rotation_flow():
    records = []
    stream = RuntimeEventStream((records.append,), run_id="run")

    class NestedFlow(Flow):
        def run(self):
            stream.record("nested.observed")
            return FlowResult(FlowStatus.COMPLETED, (FlowEvent("claimed"),))

    class NestedRotation(Rotation):
        def advance(self):
            stream.record("rotation.observed")
            return super().advance()

    runner, _ = _runner(2, [NestedFlow("daily_quests", [], [])], NestedRotation(2, []))
    runner.events = stream
    result = runner.run()
    assert result.status is SessionStatus.COMPLETED
    assert result.run_id == "run" and result.session_id
    assert all(r.fields["session_id"] == result.session_id for r in records)
    nested = [r.fields for r in records if r.event == "nested.observed"]
    assert [r["character_index"] for r in nested] == [1, 2]
    assert all(r["flow"] == "daily_quests" and r["operation_id"] for r in nested)
    assert all(r.fields["flow"] is None for r in records if r.event == "rotation.observed")
    assert len([r for r in records if r.event == "daily_quests.claimed"]) == 2
    assert runner.run().session_id != result.session_id
    assert all(value is None for value in event_context().values())


def test_session_keeps_exception_cause_from_flow_result():
    class FailedFlow(Flow):
        def run(self):
            raise OSError("flow error")

    runner, events = _runner(1, [FailedFlow("daily_quests", [], [])], Rotation(1, []))
    result = runner.run()
    assert result.failure_cause == "OSError: flow error"
    assert result.failure.exception_type == "OSError"
    assert result.failure.flow == "daily_quests"
    assert dict(events.records)["session.failed"]["failure"] == result.failure.payload()


@pytest.mark.parametrize("flow_module,class_name", [
    ("daily_quests_flow", "DailyQuestsFlow"), ("mailbox_flow", "MailboxFlow"),
    ("guild_check_in_flow", "GuildCheckInFlow"), ("send_stamina_flow", "SendStaminaFlow"),
])
def test_flow_outcome_helpers_leave_publication_to_runner(flow_module, class_name):
    from importlib import import_module

    records = []
    stream = RuntimeEventStream((records.append,))
    cls = getattr(import_module(f"bot.{flow_module}"), class_name)
    flow = object.__new__(cls)
    flow.events = stream
    outcomes = []
    flow._append_event(outcomes, f"{flow.name}.claimed")
    assert records == []
    publish_flow_events(stream, flow.name, tuple(outcomes))
    assert len(records) == 1 and records[0].fields["event_role"] == "business"


@pytest.mark.parametrize("error", [OSError("later failure"), RuntimeWaitCancelled("stop")])
def test_world_boss_preserves_pending_outcomes_when_execution_raises(error):
    from bot.world_boss_flow import WorldBossFlow

    flow = object.__new__(WorldBossFlow)
    business = FlowEvent("world_boss.previous_rewards")

    def run_pending(events):
        events.append(business)
        raise error

    flow._run = run_pending
    result = flow.run()
    assert result.events == (business,)
    assert result.status is (FlowStatus.CANCELLED if isinstance(error, RuntimeWaitCancelled) else FlowStatus.FAILED)
