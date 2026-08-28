from unittest.mock import Mock

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeObserver, RuntimeSnapshot, RuntimeWaitTimeout
from bot.state import ResolutionStatus, ResolvedState
from bot.temporal_observation import TemporalObserver, TemporalWindowStatus


def snapshot(sequence, context="screen.world_boss_battle", overlays=()):
    image = np.zeros((10, 20, 3), dtype=np.uint8)
    timestamp = sequence * 0.1
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
