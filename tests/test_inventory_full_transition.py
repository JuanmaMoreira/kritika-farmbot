import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import POPUP_INVENTORY_FULL, SCREEN_BLACK_MARKET
from bot.inventory_full_transition import acknowledge_inventory_full
from bot.observations import ObservationBatch
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import AcknowledgeInventoryFull
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionOutcome,
    VerifiedTransitionPolicy,
)


def _snapshot(sequence, *, base=SCREEN_BLACK_MARKET, overlays=(), status=None):
    status = status or (
        ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    )
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    timestamp = float(sequence)
    return RuntimeSnapshot(
        frame=FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence),
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=status,
            sequence=sequence,
            timestamp=timestamp,
            base_context=base,
            overlays=tuple(overlays),
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


def _inventory_full(sequence):
    return _snapshot(sequence, overlays=(POPUP_INVENTORY_FULL,))


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

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item

    def observe(self):
        return self.observes.pop(0)


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append((action, geometry))


def _run(waits, observes=()):
    observer = ScriptedObserver(waits, observes)
    actions = Actions()
    result = acknowledge_inventory_full(
        VerifiedTransition(observer, actions),
        _inventory_full(1),
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        ),
    )
    return result, actions


def test_inventory_full_ok_returns_to_black_market_on_first_attempt():
    result, actions = _run([_snapshot(2)])

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
    assert result.succeeded
    assert [action for action, _ in actions.calls] == [
        AcknowledgeInventoryFull()
    ]


def test_inventory_full_disappears_during_grace_without_second_tap():
    result, actions = _run(
        [
            _timeout(1, _inventory_full(2)),
            _snapshot(3),
        ]
    )

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
    assert len(actions.calls) == 1


def test_inventory_full_retries_only_when_fresh_guard_still_matches():
    result, actions = _run(
        [
            _timeout(1, _inventory_full(2)),
            _timeout(2, _inventory_full(3), timeout=2.0),
            _snapshot(5),
        ],
        observes=[_inventory_full(4)],
    )

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
    assert len(actions.calls) == 2


def test_inventory_full_rejects_retry_when_guard_no_longer_matches():
    result, actions = _run(
        [
            _timeout(1, _inventory_full(2)),
            _timeout(2, _snapshot(3, base=None), timeout=2.0),
        ],
        observes=[_snapshot(4, base=None)],
    )

    assert result.outcome is VerifiedTransitionOutcome.RETRY_GUARD_REJECTED
    assert len(actions.calls) == 1


def test_inventory_full_ok_attempts_are_bounded_and_failure_is_explicit():
    result, actions = _run(
        [
            _timeout(1, _inventory_full(2)),
            _timeout(2, _inventory_full(3), timeout=2.0),
            _timeout(4, _inventory_full(5)),
            _timeout(5, _inventory_full(6), timeout=2.0),
        ],
        observes=[_inventory_full(4), _inventory_full(7)],
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert not result.succeeded
    assert len(actions.calls) == 2
