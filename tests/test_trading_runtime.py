"""Verified Trading navigation prerequisite for C6b."""

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from bot.action_executor import (
    DEFAULT_TRADING_ACTION_TARGETS,
    ActionExecutor,
    FrameGeometry,
)
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception import (
    TradingRowsDetector,
    TradingTabsDetector,
    build_default_perception,
    build_trading_navigation_perception,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import (
    CloseTrading,
    OpenTrading,
    SelectTradingAvatarKeys,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center_semantics import (
    INDICATOR_TRADING_GENERAL_ACTIVE,
    INDICATOR_TRADING_KEYS_ACTIVE,
    INDICATOR_TRADING_KEYS_ROWS,
    LANDMARK_TRADING_CENTER_TITLE,
    SCREEN_TRADING,
)
from bot.trading_navigation_profile import TRADING_NAVIGATION_PROFILE
from bot.trading_runtime import TradingRuntime
from bot.verified_transition import VerifiedTransitionOutcome


GEOMETRY = FrameGeometry(width=2712, height=1220)


def _observation(name):
    return Observation(name, 0.95, ObservationSource.LOCAL_CV)


def _snapshot(sequence, *, base, names=(), overlays=(), status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((1220, 2712, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(
            sequence,
            float(sequence),
            tuple(_observation(name) for name in names),
        ),
        ResolvedState(
            status,
            sequence,
            float(sequence),
            base_context=base,
            overlays=tuple(overlays),
        ),
        RuntimeFacts(),
        GEOMETRY,
    )


def _lobby(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_LOBBY,
        names=("landmark.lobby_trading_center_label",),
    )


def _general(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_TRADING,
        names=(
            LANDMARK_TRADING_CENTER_TITLE,
            INDICATOR_TRADING_GENERAL_ACTIVE,
        ),
    )


def _keys(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_TRADING,
        names=(
            LANDMARK_TRADING_CENTER_TITLE,
            INDICATOR_TRADING_KEYS_ACTIVE,
            INDICATOR_TRADING_KEYS_ROWS,
        ),
    )


class FakeObserver:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)

    def observe(self):
        if not self.snapshots:
            raise RuntimeError("no snapshots")
        return self.snapshots.pop(0)

    def wait_until(
        self,
        condition,
        *,
        after_sequence=0,
        timeout=6.0,
        stable_for=0.0,
        abort_if=None,
        cancel_requested=None,
    ):
        for snapshot in list(self.snapshots):
            if snapshot.sequence <= after_sequence:
                continue
            if cancel_requested is not None and cancel_requested():
                from bot.runtime_observer import RuntimeWaitCancelled

                raise RuntimeWaitCancelled("cancelled")
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


class CancelOnCall:
    def __init__(self, call_number):
        self.call_number = call_number
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.calls >= self.call_number


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
    ):
        self.calls.append((name, action, before))
        if precondition is not None and not precondition(before):
            final = before
            outcome = VerifiedTransitionOutcome.PRECONDITION_REJECTED
            error = "precondition_rejected"
            succeeded = False
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
            error=error,
            failure=None,
            succeeded=succeeded,
        )


def _runtime(initial, posts, *, cancel_requested=lambda: False):
    adb = FakeAdb()
    actions = ActionExecutor(adb)
    transition = FakeTransition(actions, posts)
    runtime = TradingRuntime(
        FakeObserver(initial),
        transition,
        cancel_requested=cancel_requested,
    )
    return runtime, transition, adb


def test_entry_clean_lobby_uses_verified_action_and_fresh_trading():
    runtime, transition, adb = _runtime([_lobby(1)], [_general(2)])

    result = runtime.enter_from_lobby()

    assert result.status is FlowStatus.COMPLETED
    assert result.final_snapshot.sequence == 2
    assert isinstance(transition.calls[0][1], OpenTrading)
    assert adb.taps == [(662, 1089)]


def test_entry_incompatible_context_emits_zero_input():
    runtime, transition, adb = _runtime([_keys(1)], [])

    result = runtime.enter_from_lobby()

    assert result.status is FlowStatus.FAILED
    assert transition.calls == []
    assert adb.taps == []


def test_entry_no_effect_fails_without_retry():
    runtime, transition, adb = _runtime([_lobby(1)], [_lobby(2)])

    result = runtime.enter_from_lobby()

    assert result.status is FlowStatus.FAILED
    assert len(transition.calls) == 1
    assert len(adb.taps) == 1


def test_entry_stale_trading_postcondition_fails():
    runtime, _, adb = _runtime([_lobby(3)], [_general(3)])

    result = runtime.enter_from_lobby()

    assert result.status is FlowStatus.FAILED
    assert len(adb.taps) == 1


def test_entry_cancellation_before_input_propagates():
    runtime, transition, adb = _runtime(
        [_lobby(1)], [_general(2)], cancel_requested=lambda: True
    )

    result = runtime.enter_from_lobby()

    assert result.status is FlowStatus.CANCELLED
    assert transition.calls == []
    assert adb.taps == []


def test_entry_cancellation_after_action_propagates():
    runtime, transition, adb = _runtime(
        [_lobby(1)], [_general(2)], cancel_requested=CancelOnCall(4)
    )

    result = runtime.enter_from_lobby()

    assert result.status is FlowStatus.CANCELLED
    assert len(transition.calls) == 1
    assert len(adb.taps) == 1


def test_leave_trading_uses_specific_close_and_fresh_lobby():
    runtime, transition, adb = _runtime([_keys(4)], [_lobby(5)])

    result = runtime.leave_to_lobby()

    assert result.status is FlowStatus.COMPLETED
    assert result.final_snapshot.sequence == 5
    assert isinstance(transition.calls[0][1], CloseTrading)
    assert adb.taps == [(2108, 170)]


def test_leave_stale_lobby_postcondition_fails():
    runtime, _, adb = _runtime([_keys(5)], [_lobby(5)])

    result = runtime.leave_to_lobby()

    assert result.status is FlowStatus.FAILED
    assert len(adb.taps) == 1


def test_leave_incompatible_context_emits_zero_input():
    runtime, transition, adb = _runtime([_lobby(1)], [])

    result = runtime.leave_to_lobby()

    assert result.status is FlowStatus.FAILED
    assert transition.calls == []
    assert adb.taps == []


def test_leave_cancellation_before_input_propagates():
    runtime, transition, adb = _runtime(
        [_keys(1)], [_lobby(2)], cancel_requested=lambda: True
    )

    result = runtime.leave_to_lobby()

    assert result.status is FlowStatus.CANCELLED
    assert transition.calls == []
    assert adb.taps == []


def test_leave_cancellation_after_action_propagates():
    runtime, transition, adb = _runtime(
        [_keys(1)], [_lobby(2)], cancel_requested=CancelOnCall(4)
    )

    result = runtime.leave_to_lobby()

    assert result.status is FlowStatus.CANCELLED
    assert len(transition.calls) == 1
    assert len(adb.taps) == 1


def test_select_avatar_keys_requires_fresh_verified_section():
    runtime, transition, adb = _runtime([_general(6)], [_keys(7)])

    result = runtime.ensure_avatar_keys()

    assert result.status is FlowStatus.COMPLETED
    assert result.final_snapshot.sequence == 7
    assert isinstance(transition.calls[0][1], SelectTradingAvatarKeys)
    assert adb.taps == [(1317, 293)]


def test_avatar_keys_is_idempotent_without_unnecessary_input():
    runtime, transition, adb = _runtime([_keys(8)], [])

    result = runtime.ensure_avatar_keys()

    assert result.status is FlowStatus.COMPLETED
    assert result.final_snapshot.sequence == 8
    assert transition.calls == []
    assert adb.taps == []


def test_avatar_keys_stale_confirmation_fails():
    runtime, _, adb = _runtime([_general(9)], [_keys(9)])

    result = runtime.ensure_avatar_keys()

    assert result.status is FlowStatus.FAILED
    assert len(adb.taps) == 1


def test_avatar_keys_no_effect_fails_without_retry():
    runtime, transition, adb = _runtime([_general(10)], [_general(11)])

    result = runtime.ensure_avatar_keys()

    assert result.status is FlowStatus.FAILED
    assert len(transition.calls) == 1
    assert len(adb.taps) == 1


def test_avatar_keys_cancellation_after_action_propagates():
    runtime, transition, adb = _runtime(
        [_general(12)], [_keys(13)], cancel_requested=CancelOnCall(4)
    )

    result = runtime.ensure_avatar_keys()

    assert result.status is FlowStatus.CANCELLED
    assert len(transition.calls) == 1
    assert len(adb.taps) == 1


def test_public_apis_compose_trading_lobby_trading_keys():
    runtime, transition, adb = _runtime(
        [_keys(20), _lobby(21), _general(22)],
        [_lobby(21), _general(22), _keys(23)],
    )

    left = runtime.leave_to_lobby()
    entered = runtime.enter_from_lobby()
    restored = runtime.ensure_avatar_keys()

    assert [left.status, entered.status, restored.status] == [
        FlowStatus.COMPLETED,
        FlowStatus.COMPLETED,
        FlowStatus.COMPLETED,
    ]
    assert restored.final_snapshot.sequence == 23
    assert [type(call[1]) for call in transition.calls] == [
        CloseTrading,
        OpenTrading,
        SelectTradingAvatarKeys,
    ]
    assert len(adb.taps) == 3


def test_profile_points_are_current_hil_points_inside_current_bboxes():
    profile = TRADING_NAVIGATION_PROFILE
    assert profile.entry_point == (0.244284661, 0.893032787)
    assert profile.avatar_keys_point == (0.485803835, 0.240573770)
    assert profile.close_point == (0.777470501, 0.139754098)
    for point_name, bbox_name in (
        ("entry_point", "entry_bbox"),
        ("avatar_keys_point", "avatar_keys_bbox"),
        ("close_point", "close_bbox"),
    ):
        x, y = getattr(profile, point_name)
        x0, y0, x1, y1 = getattr(profile, bbox_name)
        assert x0 < x < x1 and y0 < y < y1


def test_executor_defaults_mirror_navigation_profile():
    targets = DEFAULT_TRADING_ACTION_TARGETS
    assert targets.open_trading == TRADING_NAVIGATION_PROFILE.entry_point
    assert (
        targets.select_avatar_keys
        == TRADING_NAVIGATION_PROFILE.avatar_keys_point
    )
    assert targets.close_trading == TRADING_NAVIGATION_PROFILE.close_point


def test_navigation_perception_is_opt_in_global_plus_trading_details():
    root = Path(__file__).resolve().parents[1]
    global_engine = build_default_perception(root)
    engine = build_trading_navigation_perception(root)

    assert engine.detectors[: len(global_engine.detectors)]
    assert len(engine.detectors) == len(global_engine.detectors) + 2
    assert isinstance(engine.detectors[-2], TradingTabsDetector)
    assert isinstance(engine.detectors[-1], TradingRowsDetector)


def test_runtime_has_no_scroll_trade_or_c6_policy_surface():
    source = inspect.getsource(__import__("bot.trading_runtime", fromlist=["*"]))
    imports = "\n".join(
        line for line in source.splitlines()
        if line.startswith("from ") or line.startswith("import ")
    )
    assert "treasure" not in imports.lower()
    for forbidden in (
        "execute_key_trade",
        "decide_next_keys_operation",
        "directed_list_scroll",
        "Swipe(",
        "OUTPUT_FULL",
    ):
        assert forbidden not in source
