from unittest.mock import Mock

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitTimeout
from bot.state import ResolutionStatus, ResolvedState
from bot.tap_through_animation import (
    TapThroughAnimation,
    TapThroughOutcome,
    TapThroughPolicy,
)


def snapshot(sequence, kind):
    image = np.zeros((20, 40, 3), dtype=np.uint8)
    if kind == "complete":
        status, base = ResolutionStatus.RESOLVED, "screen.done"
    elif kind == "incompatible":
        status, base = ResolutionStatus.RESOLVED, "screen.other"
    else:
        status, base = ResolutionStatus.UNKNOWN, None
    observations = ()
    if kind in {"tappable", "flash"}:
        observations = (
            Observation(
                f"activity.test.{kind}", 1.0, ObservationSource.SYSTEM
            ),
        )
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(status, sequence, float(sequence), base_context=base),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


class Observer:
    def __init__(self, values=(), timeout=False):
        self.values = list(values)
        self.timeout = timeout
        self.calls = []

    def wait_until(self, condition, **kwargs):
        self.calls.append(kwargs)
        if self.timeout:
            raise RuntimeWaitTimeout(
                after_sequence=kwargs["after_sequence"],
                timeout=kwargs["timeout"],
                last_snapshot=None,
            )
        value = self.values.pop(0)
        assert condition(value)
        return value


class Time:
    def __init__(self):
        self.value = 0.0

    def clock(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


def run(initial, following=(), *, timeout=False, max_taps=20, cancel=lambda: False):
    observer = Observer(following, timeout=timeout)
    actions = Mock()
    now = Time()
    primitive = TapThroughAnimation(
        observer, actions, clock=now.clock, sleeper=now.sleep
    )
    result = primitive.run(
        initial,
        action=object(),
        expected=lambda item: item.state.base_context == "screen.done",
        tappable=lambda item: bool(item.observations.find("activity.test.tappable")),
        transient=lambda item: item.state.status is ResolutionStatus.UNKNOWN,
        cancel_requested=cancel,
        policy=TapThroughPolicy(timeout=5, tap_interval=0.5, max_taps=max_taps),
    )
    return result, observer, actions


def test_expected_state_already_present_sends_zero_taps():
    result, observer, actions = run(snapshot(1, "complete"))

    assert result.outcome is TapThroughOutcome.COMPLETED
    assert result.tap_count == 0
    actions.execute.assert_not_called()
    assert observer.calls == []


def test_tappable_frame_taps_once_then_completes():
    result, _, actions = run(
        snapshot(1, "tappable"), [snapshot(2, "complete")]
    )

    assert result.outcome is TapThroughOutcome.COMPLETED
    assert result.tap_count == 1
    actions.execute.assert_called_once()


def test_two_or_three_guarded_taps_are_supported():
    for count in (2, 3):
        following = [snapshot(index + 2, "tappable") for index in range(count - 1)]
        following.append(snapshot(count + 1, "complete"))

        result, _, actions = run(snapshot(1, "tappable"), following)

        assert result.outcome is TapThroughOutcome.COMPLETED
        assert result.tap_count == count
        assert actions.execute.call_count == count


def test_flash_temporarily_suppresses_input_then_tappable_continues():
    result, _, actions = run(
        snapshot(1, "tappable"),
        [snapshot(2, "flash"), snapshot(3, "tappable"), snapshot(4, "complete")],
    )

    assert result.outcome is TapThroughOutcome.COMPLETED
    assert result.tap_count == 2
    assert actions.execute.call_count == 2


def test_generic_unknown_never_authorizes_a_tap():
    result, _, actions = run(
        snapshot(1, "unknown"), [snapshot(2, "complete")]
    )

    assert result.outcome is TapThroughOutcome.COMPLETED
    actions.execute.assert_not_called()


def test_timeout_and_max_taps_are_bounded():
    timeout, _, timeout_actions = run(snapshot(1, "flash"), timeout=True)
    maximum, _, maximum_actions = run(
        snapshot(1, "tappable"),
        [snapshot(2, "tappable")],
        max_taps=1,
    )

    assert timeout.outcome is TapThroughOutcome.TIMEOUT
    timeout_actions.execute.assert_not_called()
    assert maximum.outcome is TapThroughOutcome.MAX_TAPS
    assert maximum.tap_count == 1
    assert maximum_actions.execute.call_count == 1


def test_incompatible_state_fails_without_input():
    result, _, actions = run(snapshot(1, "incompatible"))

    assert result.outcome is TapThroughOutcome.INCOMPATIBLE_STATE
    actions.execute.assert_not_called()


def test_cancellation_stops_before_input_and_completion_stops_later_input():
    cancelled, _, cancelled_actions = run(
        snapshot(1, "tappable"), cancel=lambda: True
    )
    completed, observer, completed_actions = run(snapshot(1, "complete"))

    assert cancelled.outcome is TapThroughOutcome.CANCELLED
    cancelled_actions.execute.assert_not_called()
    assert completed.outcome is TapThroughOutcome.COMPLETED
    completed_actions.execute.assert_not_called()
    assert observer.values == []
