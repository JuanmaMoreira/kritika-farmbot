"""Backend-agnostic aggregation of observations for one frame snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

import numpy as np

from bot.capture import FrameSnapshot
from bot.observations import Observation, ObservationBatch


class PerceptionDetector(Protocol):
    """A detector that can emit zero, one or many semantic observations."""

    def detect(self, frame: np.ndarray) -> Iterable[Observation]: ...


@dataclass(frozen=True)
class PerceptionEngine:
    """Run explicitly injected detectors without retaining gameplay state."""

    detectors: tuple[PerceptionDetector, ...] = ()

    def __post_init__(self) -> None:
        detectors = tuple(self.detectors)
        if not all(callable(getattr(item, "detect", None)) for item in detectors):
            raise ValueError("detectors must provide detect(frame)")
        object.__setattr__(self, "detectors", detectors)

    def analyze(self, snapshot: FrameSnapshot) -> ObservationBatch:
        """Aggregate detector results in injection and emission order."""

        if not isinstance(snapshot, FrameSnapshot):
            raise ValueError("snapshot must be a FrameSnapshot")

        observations: list[Observation] = []
        for detector in self.detectors:
            emitted = tuple(detector.detect(snapshot.image))
            if not all(isinstance(item, Observation) for item in emitted):
                raise ValueError("detectors must emit only Observation instances")
            observations.extend(emitted)

        return ObservationBatch(
            sequence=snapshot.sequence,
            timestamp=snapshot.timestamp,
            observations=tuple(observations),
        )
