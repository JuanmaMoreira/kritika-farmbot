from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeObserver, RuntimeSnapshot, RuntimeWaitTimeout
from bot.state import ResolutionStatus, ResolvedState
from bot.temporal_observation import (
    FrameHarvest,
    TemporalObserver,
    TemporalWindowStatus,
    harvest_frame_window,
)


def snapshot(sequence, context="screen.world_boss_battle", overlays=(), status=None):
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    timestamp = sequence * 0.1
    if status is None:
        status = ResolutionStatus.RESOLVED if context else ResolutionStatus.UNKNOWN
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


def test_collects_only_fresh_ordered_frames_from_runtime_observer():
    observer = Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect = [snapshot(11), snapshot(12), snapshot(13)]
    temporal = TemporalObserver(observer, clock=lambda: 0.0)

    result = temporal.collect(
        after_sequence=10,
        context="screen.world_boss_battle",
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.COMPLETE
    assert [item.sequence for item in result.snapshots] == [11, 12, 13]
    cursors = [
        call.kwargs["after_sequence"]
        for call in observer.wait_until.call_args_list
    ]
    assert cursors == [10, 11, 12]


def test_context_mismatch_stops_window_immediately():
    observer = Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect = [snapshot(11), snapshot(12, "screen.lobby")]
    temporal = TemporalObserver(observer, clock=lambda: 0.0)

    result = temporal.collect(
        after_sequence=10,
        context="screen.world_boss_battle",
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.CONTEXT_MISMATCH
    assert result.last_sequence == 12
    assert observer.wait_until.call_count == 2


def test_transient_unknown_is_skipped_within_the_bounded_window():
    observer = Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect = [
        snapshot(11),
        snapshot(12, context=None),
        snapshot(13),
        snapshot(14),
    ]
    temporal = TemporalObserver(observer, clock=lambda: 0.0)

    result = temporal.collect(
        after_sequence=10,
        context="screen.world_boss_battle",
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.COMPLETE
    assert [item.sequence for item in result.snapshots] == [11, 13, 14]
    assert [
        call.kwargs["after_sequence"] for call in observer.wait_until.call_args_list
    ] == [10, 11, 12, 13]


def test_interrupt_overlay_wins_even_when_base_is_temporarily_unknown():
    observer = Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect = [
        snapshot(11, context=None, overlays=("overlay.world_boss_raid_complete",)),
    ]
    temporal = TemporalObserver(observer, clock=lambda: 0.0)

    result = temporal.collect(
        after_sequence=10,
        context="screen.world_boss_battle",
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
        interrupt_overlays=frozenset(("overlay.world_boss_raid_complete",)),
    )

    assert result.status is TemporalWindowStatus.INTERRUPTED
    assert result.last_sequence == 11
    assert "overlay.world_boss_raid_complete" in result.detail


def test_timeout_is_bounded_and_preserves_partial_window():
    observer = Mock(spec=RuntimeObserver)
    observer.wait_until.side_effect = [
        snapshot(11),
        RuntimeWaitTimeout(after_sequence=11, timeout=1.0, last_snapshot=None),
    ]
    temporal = TemporalObserver(observer, clock=lambda: 0.0)

    result = temporal.collect(
        after_sequence=10,
        context="screen.world_boss_battle",
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.TIMEOUT
    assert result.last_sequence == 11
    assert "frames_collected=1/3" in result.detail
    assert "last_sequence=11" in result.detail
    assert "timeout=2.000" in result.detail


def test_four_second_budget_collects_ten_frames_under_observed_processing_latency():
    class FakeClock:
        current = 0.0

        def __call__(self):
            return self.current

    fake = FakeClock()
    observer = Mock(spec=RuntimeObserver)

    def next_snapshot(*args, **kwargs):
        sequence = observer.wait_until.call_count + 10
        fake.current += 0.3
        return snapshot(sequence)

    observer.wait_until.side_effect = next_snapshot
    temporal = TemporalObserver(observer, clock=fake)

    result = temporal.collect(
        after_sequence=10,
        context="screen.world_boss_battle",
        frame_count=10,
        sample_interval=0.1,
        timeout=4.0,
    )

    assert result.status is TemporalWindowStatus.COMPLETE
    assert len(result.snapshots) == 10
    assert round(fake.current, 3) == 3.0


def test_twelve_second_budget_collects_ten_frames_at_one_second_each():
    class FakeClock:
        current = 0.0

        def __call__(self):
            return self.current

    fake = FakeClock()
    observer = Mock(spec=RuntimeObserver)

    def next_snapshot(*args, **kwargs):
        sequence = observer.wait_until.call_count + 30
        fake.current += 1.0
        return snapshot(sequence)

    observer.wait_until.side_effect = next_snapshot
    temporal = TemporalObserver(observer, clock=fake)

    result = temporal.collect(
        after_sequence=30,
        context="screen.world_boss_battle",
        frame_count=10,
        sample_interval=0.1,
        timeout=12.0,
    )

    assert result.status is TemporalWindowStatus.COMPLETE
    assert len(result.snapshots) == 10
    assert fake.current == pytest.approx(10.0)


def test_elapsed_deadline_diagnostic_reports_partial_collection():
    class FakeClock:
        current = 0.0

        def __call__(self):
            return self.current

    fake = FakeClock()
    observer = Mock(spec=RuntimeObserver)

    def next_snapshot(*args, **kwargs):
        sequence = observer.wait_until.call_count + 20
        fake.current += 0.7
        return snapshot(sequence)

    observer.wait_until.side_effect = next_snapshot
    result = TemporalObserver(observer, clock=fake).collect(
        after_sequence=20,
        context="screen.world_boss_battle",
        frame_count=10,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.TIMEOUT
    assert len(result.snapshots) == 3
    assert "temporal observation deadline expired" in result.detail
    assert "frames_collected=3/10" in result.detail
    assert "last_sequence=23" in result.detail
    assert "elapsed=2.100" in result.detail


def raw_frame(sequence, timestamp):
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    return FrameSnapshot(image, timestamp, sequence)


class ScriptedSource:
    """Frame source that replays scripted frames, then stalls on the last."""

    def __init__(self, frames, error=None):
        self._frames = list(frames)
        self._error = error
        self._last = None
        self.calls = 0

    def get_frame(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._frames:
            self._last = self._frames.pop(0)
        if self._last is None:
            raise AssertionError("source has no frame to replay")
        return self._last


class FakeClock:
    def __init__(self):
        self.current = 0.0

    def __call__(self):
        return self.current

    def sleep(self, duration):
        self.current += duration


def test_harvest_collects_spaced_fresh_frames():
    source = ScriptedSource(
        [raw_frame(sequence, timestamp) for sequence, timestamp in
         ((11, 1.0), (12, 1.2), (13, 1.4))]
    )

    result = harvest_frame_window(
        source,
        after_sequence=10,
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert isinstance(result, FrameHarvest)
    assert result.status is TemporalWindowStatus.COMPLETE
    assert [item.sequence for item in result.frames] == [11, 12, 13]
    assert result.detail is None


def test_harvest_ignores_duplicate_and_stale_sequences():
    # A stalled decoder replays the same (or an older) sequence: those
    # deliveries must never count toward frame_count nor move the spacing
    # baseline, or fabricated ~0 diffs would bias motion classifiers to OFF.
    source = ScriptedSource([
        raw_frame(11, 1.00),
        raw_frame(11, 1.50),  # duplicate: skipped, cursor stays 11
        raw_frame(10, 2.00),  # stale: skipped
        raw_frame(12, 1.04),  # fresh but too close to 11: skipped
        raw_frame(13, 1.30),  # gap from 11 is fine: accepted
    ])

    result = harvest_frame_window(
        source,
        after_sequence=10,
        frame_count=2,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.COMPLETE
    assert [item.sequence for item in result.frames] == [11, 13]


def test_harvest_timeout_reports_partial_collection():
    fake = FakeClock()
    source = ScriptedSource([raw_frame(11, 0.0), raw_frame(12, 0.2)])

    result = harvest_frame_window(
        source,
        after_sequence=10,
        frame_count=5,
        sample_interval=0.1,
        timeout=0.5,
        clock=fake,
        sleeper=fake.sleep,
    )

    assert result.status is TemporalWindowStatus.TIMEOUT
    assert [item.sequence for item in result.frames] == [11, 12]
    assert "frame harvest deadline expired" in result.detail
    assert "frames_collected=2/5" in result.detail
    assert source.calls < 1000


def test_harvest_cancel_is_bounded():
    source = ScriptedSource([raw_frame(11, 0.0)])

    result = harvest_frame_window(
        source,
        after_sequence=10,
        frame_count=5,
        sample_interval=0.1,
        timeout=30.0,
        cancel_requested=lambda: True,
    )

    assert result.status is TemporalWindowStatus.CANCELLED
    assert [item.sequence for item in result.frames] == []


def test_harvest_source_failure_reports_failure():
    source = ScriptedSource([], error=RuntimeError("capture failed"))

    result = harvest_frame_window(
        source,
        after_sequence=10,
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.FAILURE
    assert result.frames == ()
    assert "capture failed" in result.detail


def test_harvest_rejects_non_snapshot_delivery():
    source = ScriptedSource([object()])

    result = harvest_frame_window(
        source,
        after_sequence=10,
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )

    assert result.status is TemporalWindowStatus.FAILURE
    assert result.frames == ()


@pytest.mark.parametrize(
    "kwargs",
    (
        {"frame_count": 1},
        {"sample_interval": -0.1},
        {"timeout": 0.0},
        {"poll_interval": 0.0},
        {"after_sequence": -1},
    ),
)
def test_harvest_rejects_invalid_bounds(kwargs):
    source = ScriptedSource([raw_frame(11, 0.0)])
    params = dict(
        after_sequence=10,
        frame_count=3,
        sample_interval=0.1,
        timeout=2.0,
    )
    params.update(kwargs)

    with pytest.raises(ValueError):
        harvest_frame_window(source, **params)


def test_harvest_rejects_source_without_get_frame():
    with pytest.raises(ValueError):
        harvest_frame_window(
            object(),
            after_sequence=10,
            frame_count=3,
            sample_interval=0.1,
            timeout=2.0,
        )
