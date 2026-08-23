from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.observations import Observation, ObservationSource
from bot.perception.engine import PerceptionEngine


class FakeDetector:
    def __init__(self, *observations):
        self.observations = observations
        self.frames = []

    def detect(self, frame):
        self.frames.append(frame)
        return self.observations


def observation(name, confidence=0.9):
    return Observation(name, confidence, ObservationSource.SYSTEM)


def snapshot(sequence=7, timestamp=42.5):
    return FrameSnapshot(
        image=np.zeros((10, 20, 3), dtype=np.uint8),
        timestamp=timestamp,
        sequence=sequence,
    )


def test_engine_with_zero_detectors_returns_empty_batch_and_preserves_identity():
    batch = PerceptionEngine().analyze(snapshot(sequence=31, timestamp=125.75))

    assert batch.sequence == 31
    assert batch.timestamp == 125.75
    assert batch.observations == ()


def test_engine_aggregates_one_detector_and_passes_explicit_frame():
    detector = FakeDetector(observation("landmark.first"))
    frame_snapshot = snapshot()

    batch = PerceptionEngine((detector,)).analyze(frame_snapshot)

    assert batch.observations == detector.observations
    assert detector.frames == [frame_snapshot.image]


def test_engine_aggregates_multiple_detectors_in_deterministic_order():
    first = FakeDetector(
        observation("landmark.first"), observation("landmark.second")
    )
    second = FakeDetector(observation("landmark.third"))

    batch = PerceptionEngine((first, second)).analyze(snapshot())

    assert tuple(item.name for item in batch.observations) == (
        "landmark.first",
        "landmark.second",
        "landmark.third",
    )


def test_engine_is_immutable_repeatable_and_has_no_gameplay_state():
    detector = FakeDetector(observation("landmark.first"))
    engine = PerceptionEngine([detector])
    frame_snapshot = snapshot()

    first = engine.analyze(frame_snapshot)
    second = engine.analyze(frame_snapshot)

    assert first == second
    assert engine.detectors == (detector,)
    assert not hasattr(engine, "current_context")
    assert not hasattr(engine, "history")
    with pytest.raises(FrozenInstanceError):
        engine.detectors = ()


def test_engine_rejects_invalid_detector_contract():
    with pytest.raises(ValueError, match="detect"):
        PerceptionEngine((object(),))


def test_engine_rejects_non_observation_emissions():
    engine = PerceptionEngine((FakeDetector("not evidence"),))

    with pytest.raises(ValueError, match="Observation"):
        engine.analyze(snapshot())


def test_engine_requires_a_frame_snapshot():
    with pytest.raises(ValueError, match="FrameSnapshot"):
        PerceptionEngine().analyze(object())
