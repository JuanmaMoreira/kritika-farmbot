from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.auto_battle import (
    AUTO_BATTLE_SETTING,
    AUTO_BATTLE_VISIBLE_GREEN_MIN,
    AutoBattleCalibration,
    AutoBattleDetector,
    AutoBattleEnsurer,
    AutoBattleState,
    EnsureAutoBattleStatus,
    DEFAULT_AUTO_BATTLE_CALIBRATION,
    QUICK_AUTO_BATTLE_TIMEOUT,
    control_green_fractions,
)
from bot.catalog import OVERLAY_WORLD_BOSS_RAID_COMPLETE, SCREEN_WORLD_BOSS_BATTLE
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch, ObservationSource
from bot.runtime_facts import (
    FactQuality,
    FactReadResult,
    FactReadStatus,
    RuntimeFact,
    TemporalFactEvidence,
)
from bot.runtime_observer import RuntimeFacts, RuntimeObserver, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.temporal_observation import TemporalWindow, TemporalWindowStatus


def snapshot(sequence, image=None, context=SCREEN_WORLD_BOSS_BATTLE, overlays=(),
             status=ResolutionStatus.RESOLVED):
    image = np.full((40, 80, 3), (0, 180, 0), dtype=np.uint8) if image is None else image
    timestamp = float(sequence)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=context,
            overlays=overlays,
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def detector_for(
    frames, *, off=3.0, on=7.0, frame_count=None, minimum_frame_count=None
):
    observer = Mock(spec=RuntimeObserver)
    temporal = Mock()
    temporal.collect.return_value = TemporalWindow(
        TemporalWindowStatus.COMPLETE,
        tuple(snapshot(index + 1, frame) for index, frame in enumerate(frames)),
    )
    target_count = len(frames) if frame_count is None else frame_count
    minimum_count = (
        target_count if minimum_frame_count is None else minimum_frame_count
    )
    calibration = AutoBattleCalibration(
        roi=(0.0, 0.0, 1.0, 1.0),
        border_fraction=0.2,
        off_threshold=off,
        on_threshold=on,
        frame_count=target_count,
        minimum_frame_count=minimum_count,
        sample_interval=0.1,
        timeout=2.0,
    )
    return AutoBattleDetector(observer, calibration=calibration, temporal=temporal)


def changing_border(value):
    frame = np.zeros((40, 80, 3), dtype=np.uint8)
    frame[:8, :] = value
    frame[-8:, :] = value
    frame[:, :16] = value
    frame[:, -16:] = value
    return frame


def solid_green_pill():
    """Static frame with a visible control: motion-OFF, gate passes."""
    return np.full((40, 80, 3), (0, 180, 0), dtype=np.uint8)


@pytest.mark.parametrize(
    ("frames", "expected"),
    (
        ([solid_green_pill() for _ in range(5)], AutoBattleState.OFF),
        ([changing_border(value) for value in (0, 255, 0, 255, 0)], AutoBattleState.ON),
        ([changing_border(value) for value in (0, 5, 0, 5, 0)], AutoBattleState.UNKNOWN),
        # Static but control hidden (black ROI): stillness without the pill
        # on screen is not OFF evidence, so the gate abstains as UNKNOWN.
        ([changing_border(0) for _ in range(5)], AutoBattleState.UNKNOWN),
    ),
)
def test_temporal_detector_classifies_static_animated_and_gap(frames, expected):
    result = detector_for(frames).observe(after_sequence=0)

    assert result.status is FactReadStatus.CONFIRMED
    assert result.fact.value is expected
    assert result.fact.name == AUTO_BATTLE_SETTING
    assert result.fact.quality is FactQuality.TEMPORAL
    assert result.fact.source is ObservationSource.LOCAL_CV
    assert len(result.fact.evidence) == 5
    assert result.fact.evidence[-1].sequence == 5


def test_product_calibration_preserves_live_roi_threshold_gap_and_window():
    calibration = DEFAULT_AUTO_BATTLE_CALIBRATION

    assert calibration.roi == (0.835, 0.018, 0.89, 0.078)
    assert calibration.off_threshold == 2.0
    assert calibration.on_threshold == 5.0
    assert calibration.frame_count == 10
    assert calibration.minimum_frame_count == 9
    assert calibration.sample_interval == 0.1
    assert calibration.timeout == 12.0


@pytest.mark.parametrize("minimum_frame_count", (True, 1, 9.0, 11))
def test_calibration_rejects_invalid_minimum_frame_count(minimum_frame_count):
    with pytest.raises(ValueError):
        AutoBattleCalibration(minimum_frame_count=minimum_frame_count)


@pytest.mark.parametrize(
    ("window_status", "expected"),
    (
        (TemporalWindowStatus.CONTEXT_MISMATCH, FactReadStatus.CONTEXT_MISMATCH),
        (TemporalWindowStatus.INTERRUPTED, FactReadStatus.CONTEXT_MISMATCH),
        (TemporalWindowStatus.INSUFFICIENT, FactReadStatus.UNREADABLE),
        (TemporalWindowStatus.TIMEOUT, FactReadStatus.TIMEOUT),
        (TemporalWindowStatus.FAILURE, FactReadStatus.FAILURE),
    ),
)
def test_temporal_detector_preserves_bounded_acquisition_failures(window_status, expected):
    detector = detector_for([changing_border(0), changing_border(0)])
    detector.temporal.collect.return_value = TemporalWindow(window_status, detail="stop")

    result = detector.observe(after_sequence=10)

    assert result.status is expected
    assert result.fact is None


@pytest.mark.parametrize(
    ("frames", "expected"),
    (
        ([solid_green_pill() for _ in range(9)], AutoBattleState.OFF),
        (
            [changing_border(value) for value in (0, 255, 0, 255, 0, 255, 0, 255, 0)],
            AutoBattleState.ON,
        ),
        # Nine static frames without the pill: classifiable motion, but the
        # visibility gate abstains instead of confirming OFF on a hidden
        # control.
        ([changing_border(0) for _ in range(9)], AutoBattleState.UNKNOWN),
    ),
)
def test_one_sample_short_timeout_preserves_classifiable_evidence(frames, expected):
    detector = detector_for(
        frames,
        frame_count=10,
        minimum_frame_count=9,
    )
    detector.temporal.collect.return_value = TemporalWindow(
        TemporalWindowStatus.TIMEOUT,
        tuple(snapshot(index + 1, frame) for index, frame in enumerate(frames)),
        "frames_collected=9/10",
    )

    result = detector.observe(after_sequence=0)

    assert result.status is FactReadStatus.CONFIRMED
    assert result.fact.value is expected
    assert len(result.evidence) == 9


def test_timeout_below_minimum_frame_count_remains_timeout():
    frames = [changing_border(0) for _ in range(8)]
    detector = detector_for(
        frames,
        frame_count=10,
        minimum_frame_count=9,
    )
    detector.temporal.collect.return_value = TemporalWindow(
        TemporalWindowStatus.TIMEOUT,
        tuple(snapshot(index + 1, frame) for index, frame in enumerate(frames)),
        "frames_collected=8/10",
    )

    result = detector.observe(after_sequence=0)

    assert result.status is FactReadStatus.TIMEOUT
    assert result.fact is None


def test_temporal_detector_forwards_request_sequence_as_freshness_baseline():
    detector = detector_for([changing_border(0), changing_border(0)])

    detector.observe(after_sequence=99)

    assert detector.temporal.collect.call_args.kwargs["after_sequence"] == 99


def test_product_detector_forwards_twelve_second_acquisition_budget():
    observer = Mock(spec=RuntimeObserver)
    temporal = Mock()
    temporal.collect.return_value = TemporalWindow(
        TemporalWindowStatus.TIMEOUT,
        detail="scripted timeout",
    )
    detector = AutoBattleDetector(observer, temporal=temporal)

    detector.observe(after_sequence=7)

    request = temporal.collect.call_args.kwargs
    assert request["frame_count"] == 10
    assert request["sample_interval"] == 0.1
    assert request["timeout"] == 12.0


def fact(state, sequence):
    evidence = TemporalFactEvidence(sequence, float(sequence), 0.0, (0.8, 0.0, 0.95, 0.1))
    return RuntimeFact(
        AUTO_BATTLE_SETTING,
        state,
        1.0,
        FactQuality.TEMPORAL,
        ObservationSource.LOCAL_CV,
        SCREEN_WORLD_BOSS_BATTLE,
        (evidence,),
    )


def reading(state, sequence):
    item = fact(state, sequence)
    return FactReadResult(FactReadStatus.CONFIRMED, fact=item, evidence=item.evidence)


def ensurer_for(readings, guards=(), fast=()):
    observer = Mock(spec=RuntimeObserver)
    observer.observe.side_effect = list(guards)
    detector = Mock(spec=AutoBattleDetector)
    detector.observe.side_effect = list(readings)
    detector.observe_fast.side_effect = list(fast)
    detector.observer = observer
    detector.calibration = DEFAULT_AUTO_BATTLE_CALIBRATION
    detector.control_visible.side_effect = lambda frame: (
        control_green_fractions((frame.image,))[0] >= AUTO_BATTLE_VISIBLE_GREEN_MIN
    )
    adb = Mock()
    actions = ActionExecutor(adb)
    return AutoBattleEnsurer(detector, actions), detector, observer, adb


def test_ensure_initial_on_sends_zero_taps():
    ensurer, _, _, adb = ensurer_for([reading(AutoBattleState.ON, 10)])

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_ensure_off_taps_then_requires_fresh_on():
    ensurer, detector, _, adb = ensurer_for(
        [reading(AutoBattleState.OFF, 10), reading(AutoBattleState.ON, 30)],
        [snapshot(11), snapshot(20)],
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 1
    adb.tap.assert_called_once()
    assert detector.observe.call_args_list[-1].kwargs["after_sequence"] == 20


def test_ensure_retries_only_after_fresh_confirmed_off_and_is_bounded():
    ensurer, _, _, adb = ensurer_for(
        [
            reading(AutoBattleState.OFF, 10),
            reading(AutoBattleState.OFF, 30),
            reading(AutoBattleState.ON, 50),
        ],
        [snapshot(11), snapshot(20), snapshot(31), snapshot(40)],
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 2
    assert adb.tap.call_count == 2


def test_unknown_reobserves_without_tap_then_accepts_on():
    ensurer, _, _, adb = ensurer_for(
        [reading(AutoBattleState.UNKNOWN, 10), reading(AutoBattleState.ON, 20)]
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_persistent_unknown_fails_without_input():
    ensurer, _, _, adb = ensurer_for(
        [reading(AutoBattleState.UNKNOWN, 10), reading(AutoBattleState.UNKNOWN, 20)]
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.FAILURE
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_unknown_after_tap_suppresses_later_retry_even_if_off_returns():
    ensurer, _, _, adb = ensurer_for(
        [
            reading(AutoBattleState.OFF, 10),
            reading(AutoBattleState.UNKNOWN, 30),
            reading(AutoBattleState.OFF, 40),
        ],
        [snapshot(11), snapshot(20)],
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.FAILURE
    assert result.tap_count == 1
    assert adb.tap.call_count == 1


@pytest.mark.parametrize(
    ("guard", "expected"),
    (
        (snapshot(11, context="screen.lobby"), EnsureAutoBattleStatus.CONTEXT_MISMATCH),
        (
            snapshot(11, overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,)),
            EnsureAutoBattleStatus.INTERRUPTED,
        ),
    ),
)
def test_context_change_or_raid_complete_prevents_tap(guard, expected):
    ensurer, _, _, adb = ensurer_for([reading(AutoBattleState.OFF, 10)], [guard])

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is expected
    assert result.tap_count == 0
    adb.tap.assert_not_called()


@pytest.mark.parametrize(
    ("post_tap", "expected"),
    (
        (snapshot(20, context="screen.lobby"), EnsureAutoBattleStatus.CONTEXT_MISMATCH),
        (
            snapshot(20, overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,)),
            EnsureAutoBattleStatus.INTERRUPTED,
        ),
    ),
)
def test_context_change_or_raid_complete_after_tap_prevents_retry(
    post_tap, expected
):
    ensurer, _, _, adb = ensurer_for(
        [reading(AutoBattleState.OFF, 10)],
        [snapshot(11), post_tap],
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is expected
    assert result.tap_count == 1
    assert adb.tap.call_count == 1


def test_maximum_taps_is_bounded():
    ensurer, _, _, adb = ensurer_for(
        [
            reading(AutoBattleState.OFF, 10),
            reading(AutoBattleState.OFF, 30),
            reading(AutoBattleState.OFF, 50),
        ],
        [snapshot(11), snapshot(20), snapshot(31), snapshot(40)],
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.FAILURE
    assert result.tap_count == 2
    assert adb.tap.call_count == 2


def test_observer_failure_before_tap_returns_failure_without_input():
    ensurer, _, observer, adb = ensurer_for([reading(AutoBattleState.OFF, 10)])
    observer.observe.side_effect = RuntimeError("capture failed")

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.FAILURE
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_observe_accepts_timeout_override_for_quick_budget():
    detector = detector_for([changing_border(0), changing_border(0)])

    detector.observe(after_sequence=4, timeout=3.0)

    assert detector.temporal.collect.call_args.kwargs["timeout"] == 3.0


@pytest.mark.parametrize(
    "timeout", (0.0, -1.0, float("nan"), float("inf"), True, "3")
)
def test_observe_rejects_non_positive_timeout_override(timeout):
    detector = detector_for([changing_border(0), changing_border(0)])

    with pytest.raises(ValueError):
        detector.observe(after_sequence=0, timeout=timeout)


def test_ensure_on_forwards_per_call_timeout_to_detector():
    ensurer, detector, _, _ = ensurer_for([reading(AutoBattleState.ON, 10)])

    result = ensurer.ensure_on(after_sequence=1, timeout=3.0)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert detector.observe.call_args.kwargs["timeout"] == 3.0


def test_ensure_on_defaults_keep_full_budget_and_retry_limits():
    ensurer, detector, _, _ = ensurer_for(
        [
            reading(AutoBattleState.OFF, 10),
            reading(AutoBattleState.OFF, 30),
            reading(AutoBattleState.ON, 50),
        ],
        [snapshot(11), snapshot(20), snapshot(31), snapshot(40)],
    )

    result = ensurer.ensure_on(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 2
    for call in detector.observe.call_args_list:
        assert call.kwargs["timeout"] is None


@pytest.mark.parametrize(
    "kwargs",
    ({"max_taps": 0}, {"max_unknown_observations": 0}, {"timeout": -1.0}),
)
def test_ensure_on_rejects_invalid_per_call_bounds(kwargs):
    ensurer, _, _, adb = ensurer_for([reading(AutoBattleState.ON, 10)])

    with pytest.raises(ValueError):
        ensurer.ensure_on(after_sequence=1, **kwargs)

    adb.tap.assert_not_called()


def test_quick_timeout_default_covers_healthy_windows_with_margin():
    # Curated healthy acquisitions complete 10 frames in 1.188-1.875 s, so
    # the default abandon budget keeps ~60% margin over the observed maximum.
    assert QUICK_AUTO_BATTLE_TIMEOUT == 3.0
    assert QUICK_AUTO_BATTLE_TIMEOUT > 1.875


def test_ensure_on_quick_confirmed_off_taps_once_with_short_budget():
    ensurer, detector, _, adb = ensurer_for(
        [],
        [snapshot(11), snapshot(20), snapshot(31)],
        fast=[reading(AutoBattleState.OFF, 10), reading(AutoBattleState.ON, 30)],
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 1
    assert adb.tap.call_count == 1
    assert [item.value for item in result.observations] == [
        AutoBattleState.OFF, AutoBattleState.ON,
    ]
    calls = detector.observe_fast.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["after_sequence"] == 1
    assert calls[1].kwargs["after_sequence"] == 20
    for call in calls:
        assert call.kwargs["timeout"] == QUICK_AUTO_BATTLE_TIMEOUT


def test_ensure_on_quick_on_sends_no_tap_with_single_window():
    ensurer, detector, observer, adb = ensurer_for(
        [], [snapshot(11)], fast=[reading(AutoBattleState.ON, 10)]
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.SUCCESS
    assert result.tap_count == 0
    assert len(detector.observe_fast.call_args_list) == 1
    assert observer.observe.call_count == 1
    adb.tap.assert_not_called()


def test_ensure_on_quick_unknown_abandons_without_retry_or_tap():
    ensurer, detector, _, adb = ensurer_for(
        [], [snapshot(11)], fast=[reading(AutoBattleState.UNKNOWN, 10)]
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.FAILURE
    assert result.tap_count == 0
    assert len(detector.observe_fast.call_args_list) == 1
    adb.tap.assert_not_called()


def test_ensure_on_quick_temporal_timeout_abandons_without_tap():
    timeout_reading = FactReadResult(
        FactReadStatus.TIMEOUT, detail="frames_collected=2/10"
    )
    ensurer, detector, observer, adb = ensurer_for([], [], fast=[timeout_reading])

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.TIMEOUT
    assert result.tap_count == 0
    assert result.observations == ()
    observer.observe.assert_not_called()
    adb.tap.assert_not_called()


def test_ensure_on_quick_post_tap_timeout_keeps_tap_count():
    ensurer, _, observer, adb = ensurer_for(
        [],
        [snapshot(11), snapshot(20)],
        fast=[
            reading(AutoBattleState.OFF, 10),
            FactReadResult(FactReadStatus.TIMEOUT, detail="frames_collected=2/10"),
        ],
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.TIMEOUT
    assert result.tap_count == 1
    assert adb.tap.call_count == 1
    assert [item.value for item in result.observations] == [AutoBattleState.OFF]
    assert observer.observe.call_count == 2


def test_ensure_on_quick_stops_after_one_tap_when_off_persists():
    ensurer, _, _, adb = ensurer_for(
        [],
        [snapshot(11), snapshot(20)],
        fast=[
            reading(AutoBattleState.OFF, 10),
            reading(AutoBattleState.OFF, 30),
        ],
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.TIMEOUT
    assert result.tap_count == 1
    assert adb.tap.call_count == 1
    assert [item.value for item in result.observations] == [
        AutoBattleState.OFF, AutoBattleState.OFF,
    ]


def test_ensure_on_quick_unconfirmed_context_abandons_without_tap():
    unknown = snapshot(11, context=None, status=ResolutionStatus.UNKNOWN)
    ensurer, _, observer, adb = ensurer_for(
        [], [unknown], fast=[reading(AutoBattleState.ON, 10)]
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.TIMEOUT
    assert result.tap_count == 0
    assert [item.value for item in result.observations] == [AutoBattleState.ON]
    adb.tap.assert_not_called()


@pytest.mark.parametrize(
    ("context", "expected"),
    (
        (
            snapshot(11, overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,)),
            EnsureAutoBattleStatus.INTERRUPTED,
        ),
        (
            snapshot(11, context="screen.lobby"),
            EnsureAutoBattleStatus.CONTEXT_MISMATCH,
        ),
    ),
)
def test_ensure_on_quick_context_confirmation_guards_without_tap(context, expected):
    ensurer, _, _, adb = ensurer_for(
        [], [context], fast=[reading(AutoBattleState.ON, 10)]
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is expected
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_ensure_on_quick_off_with_hidden_context_sends_no_tap():
    unknown = snapshot(11, context=None, status=ResolutionStatus.UNKNOWN)
    ensurer, _, _, adb = ensurer_for(
        [], [unknown], fast=[reading(AutoBattleState.OFF, 10)]
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    # Motion said OFF but the battle context is unconfirmed: abstain, since
    # the tap guard cannot be satisfied on an UNKNOWN frame.
    assert result.status is EnsureAutoBattleStatus.TIMEOUT
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_ensure_on_quick_post_tap_raid_reports_interrupted():
    raid = snapshot(31, overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,))
    ensurer, _, _, adb = ensurer_for(
        [],
        [snapshot(11), snapshot(20), raid],
        fast=[reading(AutoBattleState.OFF, 10), reading(AutoBattleState.ON, 30)],
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.INTERRUPTED
    assert result.tap_count == 1
    assert adb.tap.call_count == 1


def test_ensure_on_quick_post_tap_unconfirmed_context_continues():
    unknown = snapshot(31, context=None, status=ResolutionStatus.UNKNOWN)
    ensurer, _, _, adb = ensurer_for(
        [],
        [snapshot(11), snapshot(20), unknown],
        fast=[reading(AutoBattleState.OFF, 10), reading(AutoBattleState.ON, 30)],
    )

    result = ensurer.ensure_on_quick(after_sequence=1)

    assert result.status is EnsureAutoBattleStatus.TIMEOUT
    assert result.tap_count == 1
    assert adb.tap.call_count == 1


@pytest.mark.parametrize("raid", (False, True))
def test_quick_immediate_post_tap_unknown_is_auxiliary_or_raid_interrupt(raid):
    after = snapshot(20, context=None, status=ResolutionStatus.UNKNOWN,
                     overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,) if raid else ())
    ensurer, _, _, adb = ensurer_for(
        [], [snapshot(11), after], fast=[reading(AutoBattleState.OFF, 10)],
    )
    result = ensurer.ensure_on_quick(after_sequence=1)
    expected = EnsureAutoBattleStatus.INTERRUPTED if raid else EnsureAutoBattleStatus.TIMEOUT
    assert result.status is expected
    assert result.tap_count == 1
    assert adb.tap.call_count == 1


def test_quick_stale_context_cannot_authorize_auto_tap():
    ensurer, _, _, adb = ensurer_for(
        [], [snapshot(10), snapshot(20)], fast=[reading(AutoBattleState.OFF, 10)],
    )
    result = ensurer.ensure_on_quick(after_sequence=1)
    assert result.tap_count == 0
    adb.tap.assert_not_called()


def test_quick_post_tap_harvest_cancellation_is_preserved():
    ensurer, _, _, adb = ensurer_for(
        [], [snapshot(11), snapshot(20)],
        fast=[reading(AutoBattleState.OFF, 10), FactReadResult(FactReadStatus.CANCELLED)],
    )
    result = ensurer.ensure_on_quick(after_sequence=1)
    assert result.status is EnsureAutoBattleStatus.CANCELLED
    assert adb.tap.call_count == 1


def test_quick_visible_off_window_cannot_tap_if_control_disappears_before_input():
    hidden = snapshot(11, image=np.zeros((40, 80, 3), dtype=np.uint8))
    ensurer, _, _, adb = ensurer_for(
        [], [hidden, snapshot(20)],
        fast=[reading(AutoBattleState.OFF, 10), reading(AutoBattleState.ON, 30)],
    )
    result = ensurer.ensure_on_quick(after_sequence=1)
    assert result.tap_count == 0
    adb.tap.assert_not_called()


@pytest.mark.parametrize("quick_timeout", (0.0, -2.0, float("nan"), True))
def test_ensure_on_quick_rejects_non_positive_budget(quick_timeout):
    ensurer, _, _, adb = ensurer_for([reading(AutoBattleState.ON, 10)])

    with pytest.raises(ValueError):
        ensurer.ensure_on_quick(after_sequence=1, quick_timeout=quick_timeout)

    adb.tap.assert_not_called()


def test_visibility_gate_uses_median_across_window():
    visible = solid_green_pill()
    hidden = np.zeros((40, 80, 3), dtype=np.uint8)
    calibration = AutoBattleCalibration(
        roi=(0.0, 0.0, 1.0, 1.0),
        border_fraction=0.2,
        frame_count=5,
        minimum_frame_count=5,
        sample_interval=0.1,
        timeout=2.0,
    )

    mostly_visible = control_green_fractions(
        (visible, visible, visible, hidden, hidden), calibration
    )
    mostly_hidden = control_green_fractions(
        (visible, visible, hidden, hidden, hidden), calibration
    )

    assert float(np.median(mostly_visible)) >= AUTO_BATTLE_VISIBLE_GREEN_MIN
    assert float(np.median(mostly_hidden)) < AUTO_BATTLE_VISIBLE_GREEN_MIN


def test_visibility_gate_rejects_empty_frames():
    with pytest.raises(ValueError):
        control_green_fractions(())


def _read_corpus_frame(path):
    import cv2

    frame = cv2.imread(str(path))
    assert frame is not None, f"corpus frame missing: {path}"
    return frame


def test_visibility_gate_separates_curated_corpus():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    battle = root / "screencaps" / "semantic" / "world_boss" / "battle"
    visible_names = [
        "20260827T231550_882542Z_01.png",
        "20260827T231552_579070Z_07.png",
        "20260827T231554_331762Z_13.png",
        "20260827T231556_425071Z_20.png",
        "20260827T231618_388239Z_01.png",
        "20260827T231620_241961Z_08.png",
    ]
    hidden_names = [
        "20260827T231621_842286Z_14.png",
        "20260827T231623_262677Z_20.png",
    ]
    visible = [
        control_green_fractions((_read_corpus_frame(battle / name),))[0]
        for name in visible_names
    ]
    hidden = [
        control_green_fractions((_read_corpus_frame(battle / name),))[0]
        for name in hidden_names
    ]

    assert min(visible) >= 0.40
    assert all(value == 0.0 for value in hidden)
    # The gate threshold keeps >2x margin below the observed visible minimum.
    assert AUTO_BATTLE_VISIBLE_GREEN_MIN == 0.20
    assert AUTO_BATTLE_VISIBLE_GREEN_MIN * 2 <= min(visible)


def test_visibility_gate_separates_live_off_on_corpus():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    live = root / "artifacts" / "world-boss-live"
    off_dir = live / "wb-auto-off-visible"
    on_dir = live / "wb-auto-on-visible"
    if not off_dir.is_dir() or not on_dir.is_dir():
        pytest.skip("live acquisition raw already consolidated")
    off = [
        control_green_fractions((_read_corpus_frame(path),))[0]
        for path in sorted(off_dir.glob("*.png"))
    ]
    on = [
        control_green_fractions((_read_corpus_frame(path),))[0]
        for path in sorted(on_dir.glob("*.png"))
    ]

    assert len(off) == 10 and len(on) == 10
    assert min(off + on) >= AUTO_BATTLE_VISIBLE_GREEN_MIN * 2


def green_frame(sequence, timestamp):
    return FrameSnapshot(solid_green_pill(), timestamp, sequence)


class ScriptedFrameSource:
    """Frame source replaying scripted frames, then stalling on the last."""

    def __init__(self, frames):
        self._frames = list(frames)
        self._last = None

    def get_frame(self):
        if self._frames:
            self._last = self._frames.pop(0)
        assert self._last is not None
        return self._last


def fast_detector(frames):
    observer = Mock(spec=RuntimeObserver)
    observer.source = ScriptedFrameSource(list(frames))
    return AutoBattleDetector(observer)


def test_observe_fast_classifies_harvest_with_identical_rule():
    frames = [green_frame(sequence, sequence * 0.5) for sequence in range(1, 11)]

    result = fast_detector(frames).observe_fast(after_sequence=0, timeout=5.0)

    assert result.status is FactReadStatus.CONFIRMED
    assert result.fact.value is AutoBattleState.OFF
    assert len(result.evidence) == 10


def test_observe_fast_timeout_without_enough_fresh_frames():
    frames = [green_frame(11, 0.0), green_frame(12, 0.2)]

    result = fast_detector(frames).observe_fast(after_sequence=10, timeout=0.3)

    assert result.status is FactReadStatus.TIMEOUT
    assert result.fact is None
    assert "frames_collected=2/10" in result.detail


def test_observe_fast_rejects_non_positive_timeout():
    detector = fast_detector([green_frame(11, 0.0)])

    with pytest.raises(ValueError):
        detector.observe_fast(after_sequence=10, timeout=0.0)


def test_classify_frames_enforces_minimum_window():
    detector = fast_detector([])

    result = detector.classify_frames(
        tuple(green_frame(sequence, sequence) for sequence in (1, 2, 3))
    )

    assert result.status is FactReadStatus.UNREADABLE
    assert result.fact is None


def test_classify_frames_matches_observe_on_identical_frames():
    frames = [green_frame(sequence, sequence * 0.5) for sequence in range(1, 11)]
    snapshots = tuple(
        RuntimeSnapshot(
            frame,
            ObservationBatch(frame.sequence, frame.timestamp),
            ResolvedState(
                ResolutionStatus.RESOLVED,
                frame.sequence,
                frame.timestamp,
                base_context=SCREEN_WORLD_BOSS_BATTLE,
                overlays=(),
            ),
            RuntimeFacts(),
            FrameGeometry.from_frame(frame.image),
        )
        for frame in frames
    )
    observer = Mock(spec=RuntimeObserver)
    temporal = Mock()
    temporal.collect.return_value = TemporalWindow(
        TemporalWindowStatus.COMPLETE, snapshots
    )
    detector = AutoBattleDetector(observer, temporal=temporal)

    via_observe = detector.observe(after_sequence=0)
    via_classify = detector.classify_frames(tuple(frames))

    assert via_observe.status is via_classify.status is FactReadStatus.CONFIRMED
    assert via_observe.fact.value is via_classify.fact.value is AutoBattleState.OFF
    assert via_observe.fact.confidence == via_classify.fact.confidence
    assert [item.sequence for item in via_classify.evidence] == list(range(1, 11))


def test_auto_battle_boundaries_use_runtime_observer_action_executor_and_no_ocr_or_adb():
    import inspect
    import bot.auto_battle as module

    source = inspect.getsource(module)
    assert "RuntimeObserver" in source
    assert "ActionExecutor" in source
    assert "RuntimeFact" in source
    assert "ToggleAutoBattle" in source
    assert "Ocr" not in source
    assert "AdbClient" not in source
