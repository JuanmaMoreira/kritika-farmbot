"""Directed known-list scroll primitive: direction, bounds, progress, safety."""

from pathlib import Path

import pytest

from bot.directed_list_scroll import (
    DirectedScrollOutcome,
    KnownListScrollProfile,
    PlannedGesture,
    ScrollDirection,
    TargetUnknownError,
    UnreadableViewportError,
    ViewportReading,
    advance_toward_target,
    plan_directed_gesture,
    range_progressed,
    scroll_to_target,
)

CATALOG = ("a", "b", "c", "d", "e", "f", "g", "h")


def _profile(**overrides):
    base = {
        "row_pitch": 0.10,
        "visible_rows": 4,
        "lane_x": 0.50,
        "top_y": 0.20,
        "bottom_y": 0.80,
    }
    base.update(overrides)
    return KnownListScrollProfile(**base)


def _reading(visible, sequence, target_y=None, readable=True, guard_ok=True):
    return ViewportReading(
        visible_ids=tuple(visible),
        sequence=sequence,
        target_row_y=target_y,
        readable=readable,
        guard_ok=guard_ok,
    )


class ScriptedObserver:
    def __init__(self, readings):
        self._readings = list(readings)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._readings.pop(0)


class GestureRecorder:
    def __init__(self):
        self.gestures = []

    def __call__(self, gesture):
        assert isinstance(gesture, PlannedGesture)
        self.gestures.append(gesture)


# Direction


def test_target_after_visible_range_plans_forward():
    gesture = plan_directed_gesture(
        catalog=CATALOG, target="g", visible_ids=("a", "b", "c"), profile=_profile()
    )
    assert gesture.direction is ScrollDirection.FORWARD


def test_target_before_visible_range_plans_backward():
    gesture = plan_directed_gesture(
        catalog=CATALOG, target="b", visible_ids=("f", "g", "h"), profile=_profile()
    )
    assert gesture.direction is ScrollDirection.BACKWARD


def test_advance_forward_reports_progressed_with_one_gesture():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("d", "e", "f"), 2)]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.PROGRESSED
    assert len(emit.gestures) == 1
    assert emit.gestures[0].direction is ScrollDirection.FORWARD


def test_advance_backward_reports_progressed_with_one_gesture():
    observe = ScriptedObserver(
        [_reading(("f", "g", "h"), 1), _reading(("b", "c", "d"), 2)]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="a",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.PROGRESSED
    assert emit.gestures[0].direction is ScrollDirection.BACKWARD


# Distance / bound


def test_near_target_uses_proportional_unclamped_delta():
    gesture = plan_directed_gesture(
        catalog=CATALOG, target="d", visible_ids=("a", "b", "c"), profile=_profile()
    )
    assert gesture.rows == 1
    assert gesture.delta == pytest.approx(0.10)


def test_far_target_clamps_to_overlap_safe_bound():
    profile = _profile()
    gesture = plan_directed_gesture(
        catalog=CATALOG, target="h", visible_ids=("a", "b", "c"), profile=profile
    )
    assert gesture.rows == 5
    assert gesture.delta == pytest.approx(profile.max_delta)
    assert gesture.delta == pytest.approx((4 - 1) * 0.10 * 0.95)


def test_delta_never_exceeds_overlap_safe_bound():
    profile = _profile()
    for target, visible in (
        ("h", ("a", "b")),
        ("h", ("a", "b", "c")),
        ("a", ("g", "h")),
        ("a", ("f", "g", "h")),
        ("e", ("a", "b", "c")),
    ):
        gesture = plan_directed_gesture(
            catalog=CATALOG, target=target, visible_ids=visible, profile=profile
        )
        assert gesture.delta <= profile.max_delta + 1e-9


def test_forward_gesture_uses_safe_lane_and_vertical_limits():
    profile = _profile()
    gesture = plan_directed_gesture(
        catalog=CATALOG, target="h", visible_ids=("a", "b", "c"), profile=profile
    )
    assert gesture.lane_x == pytest.approx(0.50)
    assert gesture.start_y == pytest.approx(0.80)
    assert gesture.end_y == pytest.approx(0.80 - gesture.delta)
    assert gesture.end_y < gesture.start_y


def test_backward_gesture_moves_down_from_top_limit():
    profile = _profile()
    gesture = plan_directed_gesture(
        catalog=CATALOG, target="a", visible_ids=("f", "g", "h"), profile=profile
    )
    assert gesture.start_y == pytest.approx(0.20)
    assert gesture.end_y == pytest.approx(0.20 + gesture.delta)
    assert gesture.end_y > gesture.start_y


# Progress


def test_driver_iterates_while_range_advances_toward_target():
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1),
            _reading(("c", "d", "e"), 2),
            _reading(("c", "d", "e"), 3),
            _reading(("e", "f", "g"), 4),
            _reading(("e", "f", "g", "h"), 5, target_y=0.70),
            _reading(("e", "f", "g", "h"), 6, target_y=0.70),
        ]
    )
    emit = GestureRecorder()
    result = scroll_to_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        max_gestures=5,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert len(emit.gestures) == 2
    assert all(g.direction is ScrollDirection.FORWARD for g in emit.gestures)


def test_same_observation_after_gesture_stops_with_no_progress():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("a", "b", "c"), 2)]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "no_progress"
    assert len(emit.gestures) == 1
    assert observe.calls == 2


def test_motion_against_direction_stops_conservatively():
    observe = ScriptedObserver(
        [_reading(("d", "e", "f"), 1), _reading(("a", "b", "c"), 2)]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "wrong_direction"
    assert len(emit.gestures) == 1


def test_range_progressed_compares_leading_edge_only():
    assert (
        range_progressed(
            direction=ScrollDirection.FORWARD,
            pre_first=0,
            pre_last=2,
            post_first=0,
            post_last=3,
        )
        is True
    )
    assert (
        range_progressed(
            direction=ScrollDirection.FORWARD,
            pre_first=0,
            pre_last=2,
            post_first=0,
            post_last=2,
        )
        is False
    )
    assert (
        range_progressed(
            direction=ScrollDirection.BACKWARD,
            pre_first=5,
            pre_last=7,
            post_first=4,
            post_last=7,
        )
        is True
    )
    assert (
        range_progressed(
            direction=ScrollDirection.BACKWARD,
            pre_first=5,
            pre_last=7,
            post_first=5,
            post_last=7,
        )
        is False
    )


# Target visibility and stability


def test_visible_stable_target_needs_zero_gestures():
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1, target_y=0.50),
            _reading(("a", "b", "c"), 2, target_y=0.50),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="b",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert emit.gestures == []
    assert result.stable_row_y == pytest.approx(0.50)
    assert result.stable_sequence == 2


def test_target_after_gesture_is_progress_not_ready_without_consensus():
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1),
            _reading(("b", "c", "d"), 2, target_y=0.60),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="d",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    # Post-gesture observation shows the target once, but stability still
    # needs a second agreeing sample: progress only, not ready.
    assert result.outcome is DirectedScrollOutcome.PROGRESSED
    assert len(emit.gestures) == 1


def test_target_shown_once_then_lost_is_not_ready():
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1, target_y=0.50),
            _reading(("a", "c"), 2),
            _reading(("a", "c"), 3),
            _reading(("a", "c"), 4),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="b",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "target_unstable"
    assert emit.gestures == []


def test_target_row_shift_beyond_tolerance_is_not_ready():
    profile = _profile(row_tolerance=0.01)
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1, target_y=0.50),
            _reading(("a", "b", "c"), 2, target_y=0.70),
            _reading(("a", "b", "c"), 3, target_y=0.50),
            _reading(("a", "b", "c"), 4, target_y=0.90),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="b",
        profile=profile,
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "target_unstable"
    assert observe.calls == 4
    assert emit.gestures == []


def test_transient_shift_followed_by_stable_pair_is_ready():
    profile = _profile(row_tolerance=0.01)
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1, target_y=0.50),
            _reading(("a", "b", "c"), 2, target_y=0.70),
            _reading(("a", "b", "c"), 3, target_y=0.70),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="b",
        profile=profile,
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert result.stable_row_y == pytest.approx(0.70)
    assert emit.gestures == []


def test_plan_returns_none_when_target_already_visible():
    assert (
        plan_directed_gesture(
            catalog=CATALOG,
            target="b",
            visible_ids=("a", "b", "c"),
            profile=_profile(),
        )
        is None
    )


# Safety


def test_unreadable_before_gesture_emits_no_input():
    observe = ScriptedObserver([_reading(("a", "b", "c"), 1, readable=False)])
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.UNREADABLE
    assert emit.gestures == []


def test_lost_guard_before_gesture_emits_no_input():
    observe = ScriptedObserver([_reading(("a", "b", "c"), 1, guard_ok=False)])
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.GUARD_LOST
    assert emit.gestures == []


def test_unreadable_after_gesture_allows_no_second_gesture():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("c", "d", "e"), 2, readable=False)]
    )
    emit = GestureRecorder()
    result = scroll_to_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        max_gestures=4,
    )
    assert result.outcome is DirectedScrollOutcome.UNREADABLE
    assert len(emit.gestures) == 1


def test_lost_guard_after_gesture_allows_no_second_gesture():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("c", "d", "e"), 2, guard_ok=False)]
    )
    emit = GestureRecorder()
    result = scroll_to_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        max_gestures=4,
    )
    assert result.outcome is DirectedScrollOutcome.GUARD_LOST
    assert len(emit.gestures) == 1


def test_unknown_target_fails_without_input_or_observation():
    observe = ScriptedObserver([])
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="zzz",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_UNKNOWN
    assert emit.gestures == []
    assert observe.calls == 0


@pytest.mark.parametrize("catalog", [(), ("a", "a", "b")])
def test_invalid_catalog_fails_explicitly_without_input(catalog):
    observe = ScriptedObserver([])
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=catalog,
        target="a",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_UNKNOWN
    assert emit.gestures == []
    assert observe.calls == 0


def test_pure_plan_rejects_invalid_input_explicitly():
    with pytest.raises(TargetUnknownError):
        plan_directed_gesture(
            catalog=CATALOG, target="zzz", visible_ids=("a",), profile=_profile()
        )
    with pytest.raises(TargetUnknownError):
        plan_directed_gesture(
            catalog=(), target="a", visible_ids=("a",), profile=_profile()
        )
    with pytest.raises(TargetUnknownError):
        plan_directed_gesture(
            catalog=("a", "a"), target="a", visible_ids=("a",), profile=_profile()
        )
    with pytest.raises(UnreadableViewportError):
        plan_directed_gesture(
            catalog=CATALOG, target="h", visible_ids=(), profile=_profile()
        )
    with pytest.raises(UnreadableViewportError):
        plan_directed_gesture(
            catalog=CATALOG, target="h", visible_ids=("a", "zzz"), profile=_profile()
        )
    with pytest.raises(UnreadableViewportError):
        plan_directed_gesture(
            catalog=CATALOG, target="h", visible_ids=("c", "b"), profile=_profile()
        )


def test_budget_exhausted_stops_without_extra_input():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("d", "e", "f"), 2)]
    )
    emit = GestureRecorder()
    result = scroll_to_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        max_gestures=1,
    )
    assert result.outcome is DirectedScrollOutcome.BUDGET_EXHAUSTED
    assert len(emit.gestures) == 1
    assert observe.calls == 2


def test_zero_remaining_budget_reports_exhausted_without_gesture():
    observe = ScriptedObserver([_reading(("a", "b", "c"), 1)])
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=0,
    )
    assert result.outcome is DirectedScrollOutcome.BUDGET_EXHAUSTED
    assert emit.gestures == []


def test_zero_budget_with_stable_target_is_still_ready():
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1, target_y=0.50),
            _reading(("a", "b", "c"), 2, target_y=0.50),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="b",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=0,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert emit.gestures == []


# Freshness


def test_stale_post_gesture_observation_proves_no_progress():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("d", "e", "f"), 1)]
    )
    emit = GestureRecorder()
    result = scroll_to_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        max_gestures=4,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "stale_observation"
    assert len(emit.gestures) == 1


def test_stale_consensus_sample_never_reports_ready():
    observe = ScriptedObserver(
        [
            _reading(("a", "b", "c"), 1, target_y=0.50),
            _reading(("a", "b", "c"), 1, target_y=0.50),
        ]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="b",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "stale_observation"
    assert emit.gestures == []


def test_stale_pre_observation_authorizes_no_gesture():
    observe = ScriptedObserver([_reading(("a", "b", "c"), 5)])
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
        after_sequence=5,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "stale_observation"
    assert emit.gestures == []


# Separation


def test_helper_only_emits_scroll_gestures_without_target_semantics():
    observe = ScriptedObserver(
        [_reading(("a", "b", "c"), 1), _reading(("d", "e", "f"), 2)]
    )
    emit = GestureRecorder()
    result = advance_toward_target(
        catalog=CATALOG,
        target="h",
        profile=_profile(),
        observe=observe,
        emit=emit,
        remaining_budget=3,
    )
    assert result.outcome is DirectedScrollOutcome.PROGRESSED
    (gesture,) = emit.gestures
    assert isinstance(gesture, PlannedGesture)
    assert "h" not in (
        gesture.direction.value,
        str(gesture.rows),
        str(gesture.delta),
        str(gesture.lane_x),
        str(gesture.start_y),
        str(gesture.end_y),
    )


def test_module_stays_consumer_agnostic():
    source = Path(__file__).resolve().parent.parent.joinpath(
        "bot", "directed_list_scroll.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "trading",
        "crafting",
        "keys",
        "bronze",
        "silver",
        "gold",
        "weapon",
        "armor",
        "accessory",
    ):
        assert forbidden not in source, forbidden
