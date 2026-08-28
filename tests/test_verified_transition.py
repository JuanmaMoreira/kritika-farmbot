from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import OpenQuickMenu
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionOutcome,
    VerifiedTransitionPolicy,
)


BEFORE = "screen.before"
EXPECTED = "screen.expected"
OTHER = "screen.other"


def _snapshot(sequence, base):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    timestamp = float(sequence)
    return RuntimeSnapshot(
        frame=FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence),
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=ResolutionStatus.RESOLVED,
            sequence=sequence,
            timestamp=timestamp,
            base_context=base,
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


def _timeout(after_sequence, last_snapshot, timeout=6.0):
    return RuntimeWaitTimeout(
        after_sequence=after_sequence,
        timeout=timeout,
        last_snapshot=last_snapshot,
    )


class ScriptedObserver:
    def __init__(self, waits, observes=()):
        self.waits = list(waits)
        self.observes = list(observes)
        self.wait_calls = []
        self.observe_calls = 0

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        self.wait_calls.append((after_sequence, timeout, stable_for))
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item

    def observe(self):
        self.observe_calls += 1
        return self.observes.pop(0)


class Actions:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def execute(self, action, geometry):
        self.calls.append((action, geometry))
        if self.error is not None:
            raise self.error


class Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


def test_transition_emits_nominal_grace_retry_and_outcome_telemetry():
    before = _snapshot(1, BEFORE)
    retryable = _snapshot(4, BEFORE)
    expected = _snapshot(5, EXPECTED)
    observer = ScriptedObserver(
        [_timeout(1, before), _timeout(1, before), expected],
        observes=[retryable],
    )
    events = Events()
    transition = VerifiedTransition(observer, Actions(), events)

    result = transition.execute(
        "test.retry",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(normal_timeout=1, grace_timeout=1, max_attempts=2),
    )

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
    names = [name for name, _ in events.records]
    assert "transition.nominal_timeout" in names
    assert "transition.grace_started" in names
    assert "transition.retry" in names
    assert events.records[-1][1]["outcome"] == "success_after_retry"


def _run(
    observer,
    *,
    retryable=True,
    max_attempts=2,
    retry_guard_timeout=0.0,
):
    actions = Actions()
    operation = VerifiedTransition(observer, actions)
    before = _snapshot(1, BEFORE)
    result = operation.execute(
        "test.transition",
        OpenQuickMenu(),
        before,
        expected=lambda snapshot: snapshot.state.base_context == EXPECTED,
        precondition=lambda snapshot: snapshot.state.base_context == BEFORE,
        retryable_from=(
            (lambda snapshot: snapshot.state.base_context == BEFORE)
            if retryable
            else None
        ),
        abort_if=lambda snapshot: snapshot.state.status
        is ResolutionStatus.AMBIGUOUS,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            retry_guard_timeout=retry_guard_timeout,
            max_attempts=max_attempts,
        ),
    )
    return result, actions


def test_expected_state_inside_normal_window_uses_one_input():
    observer = ScriptedObserver([_snapshot(2, EXPECTED)])

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
    assert result.succeeded
    assert result.attempt_count == 1
    assert result.grace_wait_count == 0
    assert len(actions.calls) == 1
    assert observer.wait_calls == [(1, 6.0, 0.0)]
    assert observer.observe_calls == 0


def test_expected_state_during_grace_does_not_send_second_input():
    still_before = _snapshot(2, BEFORE)
    observer = ScriptedObserver(
        [
            _timeout(1, still_before),
            _snapshot(3, EXPECTED),
        ]
    )

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
    assert result.attempt_count == 1
    assert result.grace_wait_count == 1
    assert len(actions.calls) == 1
    assert observer.wait_calls == [(1, 6.0, 0.0), (2, 2.0, 0.0)]


def test_safe_retry_requires_fresh_retryable_state_then_succeeds():
    before_after_normal = _snapshot(2, BEFORE)
    before_after_grace = _snapshot(3, BEFORE)
    observer = ScriptedObserver(
        [
            _timeout(1, before_after_normal),
            _timeout(2, before_after_grace, timeout=2.0),
            _snapshot(5, EXPECTED),
        ],
        observes=[_snapshot(4, BEFORE)],
    )

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
    assert result.attempt_count == 2
    assert result.grace_wait_count == 1
    assert len(actions.calls) == 2
    assert observer.observe_calls == 1
    assert observer.wait_calls[-1] == (4, 6.0, 0.0)


def test_retry_guard_rejected_never_repeats_action():
    observer = ScriptedObserver(
        [
            _timeout(1, _snapshot(2, BEFORE)),
            _timeout(2, _snapshot(3, OTHER), timeout=2.0),
        ],
        observes=[_snapshot(4, OTHER)],
    )

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.RETRY_GUARD_REJECTED
    assert result.attempt_count == 1
    assert len(actions.calls) == 1


def test_inconclusive_retry_state_can_settle_passively_before_safe_retry():
    unknown = _snapshot(4, OTHER)
    unknown = RuntimeSnapshot(
        frame=unknown.frame,
        observations=unknown.observations,
        state=ResolvedState(
            status=ResolutionStatus.UNKNOWN,
            sequence=4,
            timestamp=4.0,
        ),
        facts=unknown.facts,
        geometry=unknown.geometry,
    )
    observer = ScriptedObserver(
        [
            _timeout(1, _snapshot(2, BEFORE)),
            _timeout(2, _snapshot(3, BEFORE), timeout=2.0),
            _snapshot(5, BEFORE),
            _snapshot(6, EXPECTED),
        ],
        observes=[unknown],
    )

    result, actions = _run(observer, retry_guard_timeout=1.0)

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
    assert len(actions.calls) == 2
    assert observer.wait_calls == [
        (1, 6.0, 0.0),
        (2, 2.0, 0.0),
        (4, 1.0, 0.0),
        (5, 6.0, 0.0),
    ]


def test_second_failed_attempt_is_bounded_and_explicit():
    observer = ScriptedObserver(
        [
            _timeout(1, _snapshot(2, BEFORE)),
            _timeout(2, _snapshot(3, BEFORE), timeout=2.0),
            _timeout(4, _snapshot(5, BEFORE)),
            _timeout(5, _snapshot(6, BEFORE), timeout=2.0),
        ],
        observes=[_snapshot(4, BEFORE), _snapshot(7, BEFORE)],
    )

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert result.attempt_count == 2
    assert result.grace_wait_count == 2
    assert len(actions.calls) == 2
    assert len(observer.wait_calls) == 4


def test_non_retryable_action_never_sends_second_input():
    observer = ScriptedObserver(
        [
            _timeout(1, _snapshot(2, BEFORE)),
            _timeout(2, _snapshot(3, BEFORE), timeout=2.0),
        ],
        observes=[_snapshot(4, BEFORE)],
    )

    result, actions = _run(observer, retryable=False, max_attempts=2)

    assert result.outcome is VerifiedTransitionOutcome.TIMEOUT
    assert len(actions.calls) == 1


def test_stale_state_after_grace_is_never_used_to_retry():
    observer = ScriptedObserver(
        [
            _timeout(1, _snapshot(2, BEFORE)),
            _timeout(2, _snapshot(3, BEFORE), timeout=2.0),
        ],
        observes=[_snapshot(1, BEFORE)],
    )

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.TIMEOUT
    assert result.error == "retry_state_not_fresh"
    assert len(actions.calls) == 1


def test_unexpected_state_aborts_without_grace_or_retry():
    ambiguous = _snapshot(2, OTHER)
    ambiguous = RuntimeSnapshot(
        frame=ambiguous.frame,
        observations=ambiguous.observations,
        state=ResolvedState(
            status=ResolutionStatus.AMBIGUOUS,
            sequence=2,
            timestamp=2.0,
            base_candidates=(BEFORE, OTHER),
        ),
        facts=ambiguous.facts,
        geometry=ambiguous.geometry,
    )
    observer = ScriptedObserver([ambiguous])

    result, actions = _run(observer)

    assert result.outcome is VerifiedTransitionOutcome.UNEXPECTED_STATE
    assert result.grace_wait_count == 0
    assert len(actions.calls) == 1


def test_action_executor_failure_is_explicit_and_does_not_wait():
    observer = ScriptedObserver([])
    actions = Actions(error=OSError("input unavailable"))
    operation = VerifiedTransition(observer, actions)
    before = _snapshot(1, BEFORE)

    result = operation.execute(
        "test.failure",
        OpenQuickMenu(),
        before,
        expected=lambda snapshot: snapshot.state.base_context == EXPECTED,
        policy=VerifiedTransitionPolicy(max_attempts=2),
    )

    assert result.outcome is VerifiedTransitionOutcome.FAILED
    assert result.error == "OSError: input unavailable"
    assert result.attempt_count == 1
    assert len(actions.calls) == 1
    assert observer.wait_calls == []


@pytest.mark.parametrize(
    "kwargs",
    (
        {"normal_timeout": 0},
        {"grace_timeout": -1},
        {"retry_guard_timeout": -1},
        {"max_attempts": 0},
        {"max_attempts": True},
    ),
)
def test_policy_is_strictly_bounded(kwargs):
    with pytest.raises(ValueError):
        VerifiedTransitionPolicy(**kwargs)


def test_verified_transition_has_no_direct_adb_dependency():
    source = Path("bot/verified_transition.py").read_text(encoding="utf-8")

    assert "from bot.adb" not in source
    assert ".tap(" not in source
    assert ".swipe(" not in source
    assert "self.actions.execute(" in source
    assert "self.observer.wait_until(" in source
