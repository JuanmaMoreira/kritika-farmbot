from types import SimpleNamespace

import numpy as np

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import MENU_QUICK, SCREEN_LOBBY
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.quick_menu_trading import QuickMenuTradingRuntime
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import (
    OpenQuickMenu,
    SelectQuickMenuLobby,
    SelectQuickMenuTrading,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center_semantics import (
    LANDMARK_TRADING_CENTER_TITLE,
    SCREEN_TRADING,
)
from bot.treasure_center_semantics import (
    LANDMARK_TREASURE_TITLE,
    SCREEN_TREASURE,
)
from bot.verified_transition import VerifiedTransitionOutcome


GEOMETRY = FrameGeometry(width=2712, height=1220)


def _snapshot(sequence, *, base, names=(), overlays=(), status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((1220, 2712, 3), dtype=np.uint8)
    observations = tuple(
        Observation(name, 0.95, ObservationSource.LOCAL_CV) for name in names
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(
            status,
            sequence,
            float(sequence),
            base_context=base,
            overlays=frozenset(overlays),
        ),
        RuntimeFacts(),
        GEOMETRY,
    )


def _treasure(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        names=(LANDMARK_TREASURE_TITLE,),
    )


def _menu(sequence):
    return _snapshot(
        sequence,
        base=None,
        overlays=(MENU_QUICK,),
        status=ResolutionStatus.UNKNOWN,
    )


def _trading(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_TRADING,
        names=(LANDMARK_TRADING_CENTER_TITLE,),
    )


class FakeObserver:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)

    def observe(self):
        return self.snapshots.pop(0)

    def wait_until(self, condition, *, after_sequence=0, abort_if=None, **kwargs):
        for snapshot in list(self.snapshots):
            if snapshot.sequence <= after_sequence:
                continue
            if abort_if is not None and abort_if(snapshot):
                raise RuntimeError("aborted")
            if condition(snapshot):
                self.snapshots.remove(snapshot)
                return snapshot
        raise RuntimeError("timeout")


class FakeAdb:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))


class FakeTransition:
    def __init__(self, actions, posts):
        self.actions = actions
        self.posts = list(posts)
        self.calls = []

    def execute(
        self,
        name,
        action,
        before,
        *,
        expected,
        policy,
        precondition=None,
        retryable_from=None,
        abort_if=None,
        stable_for=0.0,
        on_recovery=None,
    ):
        self.calls.append((name, action, before, retryable_from, on_recovery))
        if precondition is not None and not precondition(before):
            final = before
            succeeded = False
            outcome = VerifiedTransitionOutcome.PRECONDITION_REJECTED
            error = "precondition_rejected"
        else:
            self.actions.execute(action, before.geometry)
            final = self.posts.pop(0)
            succeeded = expected(final)
            outcome = (
                VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
                if succeeded
                else VerifiedTransitionOutcome.TIMEOUT
            )
            error = None if succeeded else "postcondition_not_reached"
        return SimpleNamespace(
            name=name,
            outcome=outcome,
            attempt_count=1,
            grace_wait_count=0,
            final_snapshot=final,
            action_source_snapshot=before,
            recovery_after_action=False,
            error=error,
            failure=None,
            succeeded=succeeded,
        )


class CancelOnCall:
    def __init__(self, call_number):
        self.call_number = call_number
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls >= self.call_number


def _runtime(initial, posts, *, cancel_requested=lambda: False):
    adb = FakeAdb()
    actions = ActionExecutor(adb)
    transition = FakeTransition(actions, posts)
    runtime = QuickMenuTradingRuntime(
        FakeObserver(initial), transition, cancel_requested=cancel_requested
    )
    return runtime, transition, adb


def test_treasure_opens_menu_and_selects_trading_without_lobby_hop():
    runtime, transition, adb = _runtime([_treasure(10)], [_menu(11), _trading(12)])

    result = runtime.treasure_to_trading()

    assert result.status is FlowStatus.COMPLETED
    assert result.final_snapshot.sequence == 12
    assert [type(call[1]) for call in transition.calls] == [
        OpenQuickMenu,
        SelectQuickMenuTrading,
    ]
    assert not any(isinstance(call[1], SelectQuickMenuLobby) for call in transition.calls)
    assert len(adb.taps) == 2
    assert all(call[3] is None for call in transition.calls)


def test_stale_or_nontrading_destination_fails_after_one_tile_input():
    runtime, transition, adb = _runtime([_treasure(10)], [_menu(11), _treasure(11)])

    result = runtime.treasure_to_trading()

    assert result.status is FlowStatus.FAILED
    assert len(adb.taps) == 2
    assert len(transition.calls) == 2


def test_wrong_source_emits_no_input():
    runtime, transition, adb = _runtime(
        [_snapshot(10, base=SCREEN_LOBBY)], [_menu(11), _trading(12)]
    )

    result = runtime.treasure_to_trading()

    assert result.status is FlowStatus.FAILED
    assert not transition.calls
    assert not adb.taps


def test_trading_source_never_attempts_quick_menu():
    runtime, transition, adb = _runtime(
        [_trading(10)], [_menu(11), _trading(12)]
    )

    result = runtime.treasure_to_trading()

    assert result.status is FlowStatus.FAILED
    assert not transition.calls
    assert not adb.taps


def test_cancellation_after_menu_open_propagates_without_destination_tap():
    cancel = CancelOnCall(3)
    runtime, transition, adb = _runtime(
        [_treasure(10)], [_menu(11), _trading(12)], cancel_requested=cancel
    )

    result = runtime.treasure_to_trading()

    assert result.status is FlowStatus.CANCELLED
    assert [type(call[1]) for call in transition.calls] == [OpenQuickMenu]
    assert len(adb.taps) == 1
