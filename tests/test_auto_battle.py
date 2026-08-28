from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.auto_battle import (
    AUTO_BATTLE_SETTING,
    AutoBattleCalibration,
    AutoBattleDetector,
    AutoBattleEnsurer,
    AutoBattleState,
    EnsureAutoBattleStatus,
    DEFAULT_AUTO_BATTLE_CALIBRATION,
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


def snapshot(sequence, image=None, context=SCREEN_WORLD_BOSS_BATTLE, overlays=()):
    image = np.zeros((40, 80, 3), dtype=np.uint8) if image is None else image
    timestamp = float(sequence)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp),
        ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            timestamp,
            base_context=context,
            overlays=overlays,
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def detector_for(frames, *, off=3.0, on=7.0):
    observer = Mock(spec=RuntimeObserver)
    temporal = Mock()
    temporal.collect.return_value = TemporalWindow(
        TemporalWindowStatus.COMPLETE,
        tuple(snapshot(index + 1, frame) for index, frame in enumerate(frames)),
    )
    calibration = AutoBattleCalibration(
        roi=(0.0, 0.0, 1.0, 1.0),
        border_fraction=0.2,
        off_threshold=off,
        on_threshold=on,
        frame_count=len(frames),
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


@pytest.mark.parametrize(
    ("frames", "expected"),
    (
        ([changing_border(0) for _ in range(5)], AutoBattleState.OFF),
        ([changing_border(value) for value in (0, 255, 0, 255, 0)], AutoBattleState.ON),
        ([changing_border(value) for value in (0, 5, 0, 5, 0)], AutoBattleState.UNKNOWN),
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
    assert calibration.sample_interval == 0.1


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


def test_temporal_detector_forwards_request_sequence_as_freshness_baseline():
    detector = detector_for([changing_border(0), changing_border(0)])

    detector.observe(after_sequence=99)

    assert detector.temporal.collect.call_args.kwargs["after_sequence"] == 99


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


def ensurer_for(readings, guards=()):
    observer = Mock(spec=RuntimeObserver)
    observer.observe.side_effect = list(guards)
    detector = Mock(spec=AutoBattleDetector)
    detector.observe.side_effect = list(readings)
    detector.observer = observer
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
