from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.observed_scroll import (
    ObservedScroll,
    ObservedScrollConfig,
    ObservedScrollOutcome,
    ScrollAttemptKind,
    ViewportMotionDetector,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitTimeout
from bot.semantic_actions import Swipe
from bot.state import ResolutionStatus, ResolvedState


PROGRESS_SWIPE = Swipe(start=(0.8, 0.8), end=(0.8, 0.025), duration_ms=190)
CONFIRMATION_SWIPE = Swipe(start=(0.68, 0.76), end=(0.68, 0.24), duration_ms=200)


def _frame(fill):
    return np.full((100, 200, 3), fill, dtype=np.uint8)


def _snapshot(sequence, fill=0):
    image = _frame(fill)
    timestamp = float(sequence)
    return RuntimeSnapshot(
        frame=FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence),
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=ResolutionStatus.RESOLVED,
            sequence=sequence,
            timestamp=timestamp,
            base_context="screen.generic_scroll",
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


class ScriptedObserver:
    def __init__(self, waits):
        self.waits = list(waits)
        self.calls = []

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        self.calls.append((after_sequence, timeout, stable_for))
        item_or_items = self.waits.pop(0)
        if isinstance(item_or_items, BaseException):
            raise item_or_items
        items = item_or_items if isinstance(item_or_items, list) else [item_or_items]
        matched = False
        for item in items:
            assert item.sequence > after_sequence
            assert abort_if is None or not abort_if(item)
            matched = condition(item)
        assert matched
        return items[-1]


class Actions:
    def __init__(self, error=None):
        self.actions = []
        self.error = error

    def execute(self, action, geometry):
        self.actions.append(action)
        if self.error is not None:
            raise self.error


class InlineExecutor:
    def __init__(self):
        self.exited = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        return False

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as error:
            future.set_exception(error)
        return future


def _detector(**kwargs):
    return ViewportMotionDetector(region=(0.0, 0.0, 1.0, 1.0), **kwargs)


def _config(**kwargs):
    values = {
        "progress_swipe": PROGRESS_SWIPE,
        "confirmation_swipe": CONFIRMATION_SWIPE,
        "movement_threshold": 0.05,
        "max_attempts": 3,
        "settle_for": 0.75,
    }
    values.update(kwargs)
    return ObservedScrollConfig(**values)


def _run(before, waits, *, config=None, actions=None, tracker=None):
    observer = ScriptedObserver(waits)
    actions = Actions() if actions is None else actions
    tracker = InlineExecutor() if tracker is None else tracker
    operation = ObservedScroll(
        observer,
        actions,
        swipe_executor_factory=lambda: tracker,
    )
    result = operation.scroll_to_edge(
        before,
        detector=_detector(),
        config=_config() if config is None else config,
        is_compatible=lambda snapshot: snapshot.state.base_context
        == "screen.generic_scroll",
        abort_if=lambda snapshot: snapshot.state.status
        is ResolutionStatus.AMBIGUOUS,
    )
    return result, observer, actions, tracker


def test_progress_then_effective_bounce_confirms_edge_using_action_executor():
    result, observer, actions, tracker = _run(
        _snapshot(1, 0),
        [
            _snapshot(2, 180),
            [_snapshot(3, 220), _snapshot(4, 180)],
        ],
    )

    assert result.outcome is ObservedScrollOutcome.EDGE_REACHED
    assert result.edge_reached
    assert result.attempt_kinds == (
        ScrollAttemptKind.PROGRESS,
        ScrollAttemptKind.EDGE_CANDIDATE,
    )
    assert result.effective_gesture_count == 2
    assert result.confirmation_count == 1
    assert actions.actions == [PROGRESS_SWIPE, CONFIRMATION_SWIPE]
    assert observer.calls == [(1, 6.0, 0.75), (2, 6.0, 0.75)]
    assert tracker.exited


def test_no_transient_movement_aborts_as_ineffective_and_never_confirms_edge():
    before = _snapshot(10, 40)
    result, _, actions, _ = _run(
        before,
        [_snapshot(11, 40)],
        config=_config(max_attempts=2),
    )

    assert result.outcome is ObservedScrollOutcome.INEFFECTIVE_GESTURE
    assert result.attempt_kinds == (ScrollAttemptKind.INEFFECTIVE,)
    assert result.effective_gesture_count == 0
    assert result.confirmation_count == 0
    assert actions.actions == [PROGRESS_SWIPE]


def test_max_attempts_stops_repeated_progress_without_edge():
    result, _, actions, _ = _run(
        _snapshot(15, 0),
        [_snapshot(16, 100), _snapshot(17, 180)],
        config=_config(max_attempts=2),
    )

    assert result.outcome is ObservedScrollOutcome.LIMIT_REACHED
    assert result.attempt_kinds == (
        ScrollAttemptKind.PROGRESS,
        ScrollAttemptKind.PROGRESS,
    )
    assert actions.actions == [PROGRESS_SWIPE, CONFIRMATION_SWIPE]


def test_required_confirmations_are_consecutive_and_bounded():
    before = _snapshot(20, 60)
    result, _, _, _ = _run(
        before,
        [
            [_snapshot(21, 220), _snapshot(22, 60)],
            [_snapshot(23, 220), _snapshot(24, 60)],
        ],
        config=_config(required_confirmations=2, max_attempts=2),
    )

    assert result.edge_reached
    assert result.confirmation_count == 2
    assert result.attempt_kinds == (
        ScrollAttemptKind.EDGE_CANDIDATE,
        ScrollAttemptKind.EDGE_CANDIDATE,
    )


def test_third_swipe_is_used_only_when_confirmation_still_makes_progress():
    result, _, actions, _ = _run(
        _snapshot(25, 0),
        [
            _snapshot(26, 100),
            _snapshot(27, 180),
            [_snapshot(28, 220), _snapshot(29, 180)],
        ],
        config=_config(max_attempts=3),
    )

    assert result.edge_reached
    assert result.attempt_kinds == (
        ScrollAttemptKind.PROGRESS,
        ScrollAttemptKind.PROGRESS,
        ScrollAttemptKind.EDGE_CANDIDATE,
    )
    assert actions.actions == [
        PROGRESS_SWIPE,
        CONFIRMATION_SWIPE,
        CONFIRMATION_SWIPE,
    ]


def test_timeout_is_explicit_and_executor_is_closed():
    before = _snapshot(30, 0)
    timeout = RuntimeWaitTimeout(
        after_sequence=30,
        timeout=6.0,
        last_snapshot=_snapshot(31, 0),
    )
    tracker = InlineExecutor()

    result, _, _, tracker = _run(before, [timeout], tracker=tracker)

    assert result.outcome is ObservedScrollOutcome.TIMEOUT
    assert not result.edge_reached
    assert result.error.startswith("RuntimeWaitTimeout")
    assert tracker.exited


def test_action_failure_is_explicit_and_never_confirms_edge():
    result, _, _, _ = _run(
        _snapshot(40, 0),
        [_snapshot(41, 0)],
        actions=Actions(error=OSError("input failed")),
    )

    assert result.outcome is ObservedScrollOutcome.FAILED
    assert result.effective_gesture_count == 0
    assert not result.edge_reached


def test_transition_rejects_stale_or_reused_frames():
    detector = _detector()
    before = _snapshot(50, 0).frame
    stale = _snapshot(50, 0).frame

    with pytest.raises(ValueError, match="strictly increasing fresh"):
        detector.measure_transition(before, [stale], stale)


def test_observed_scroll_has_no_character_select_or_direct_adb_dependency():
    source = Path("bot/observed_scroll.py").read_text(encoding="utf-8")

    assert "CharacterSelect" not in source
    assert "from bot.adb" not in source
    assert ".swipe(" not in source
    assert ".tap(" not in source
