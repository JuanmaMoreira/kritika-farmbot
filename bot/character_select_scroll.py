"""Deterministic visual comparison for the Character Select list viewport."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Sequence

import cv2
import numpy as np

from bot.capture import FrameSnapshot
from bot.geometry import (
    RelativeRegion,
    frame_dimensions,
    normalize_relative_region,
    relative_region_to_pixels,
)


class ScrollAttemptKind(str, Enum):
    NORMAL = "normal"
    BOUNCE_CANDIDATE = "bounce_candidate"
    INEFFECTIVE = "ineffective"


@dataclass(frozen=True)
class ScrollAttemptMeasurement:
    pre_sequence: int
    settled_sequence: int
    fresh_sample_count: int
    transient_peak_sequence: int
    max_transient_difference: float
    settled_difference: float


@dataclass(frozen=True)
class CharacterSelectScrollDetector:
    """Measure Character Select motion in a scrollable viewport crop.

    The crop contains only the three-column character grid. The animated
    character model, header, footer and Select button are deliberately outside
    it. Settled similarity alone is deliberately not bottom evidence; callers
    must also require observed transient movement from the same swipe.
    """

    region: RelativeRegion = (0.4900, 0.1900, 0.8500, 0.8050)
    thumbnail_width: int = 96
    thumbnail_height: int = 72
    unchanged_threshold: float = 0.0500

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "region", normalize_relative_region(self.region)
        )
        for name in ("thumbnail_width", "thumbnail_height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            object.__setattr__(self, name, int(value))
        threshold = self.unchanged_threshold
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, Real)
            or not 0.0 <= float(threshold) <= 1.0
        ):
            raise ValueError("unchanged_threshold must be a real number in [0, 1]")
        object.__setattr__(self, "unchanged_threshold", float(threshold))

    def difference(self, first: np.ndarray, second: np.ndarray) -> float:
        """Return normalized viewport MAD after grayscale downsampling."""

        left = self._thumbnail(first).astype(np.float32)
        right = self._thumbnail(second).astype(np.float32)
        return float(np.mean(np.abs(left - right)) / 255.0)

    def settled_similar(self, first: np.ndarray, second: np.ndarray) -> bool:
        return self.difference(first, second) <= self.unchanged_threshold

    def measure_transition(
        self,
        before: FrameSnapshot,
        samples: Sequence[FrameSnapshot],
        settled: FrameSnapshot,
    ) -> ScrollAttemptMeasurement:
        """Measure one A -> transient frames -> settled B swipe transition."""

        if not isinstance(before, FrameSnapshot):
            raise ValueError("before must be a FrameSnapshot")
        if not isinstance(settled, FrameSnapshot):
            raise ValueError("settled must be a FrameSnapshot")
        fresh_samples = tuple(samples)
        if not fresh_samples:
            raise ValueError("samples must contain fresh post-swipe frames")

        previous_sequence = before.sequence
        differences: list[tuple[int, float]] = []
        for sample in fresh_samples:
            if not isinstance(sample, FrameSnapshot):
                raise ValueError("samples must contain FrameSnapshot values")
            if sample.sequence <= previous_sequence:
                raise ValueError("samples must have strictly increasing fresh sequences")
            differences.append(
                (sample.sequence, self.difference(before.image, sample.image))
            )
            previous_sequence = sample.sequence
        if settled.sequence != fresh_samples[-1].sequence:
            raise ValueError("settled must be the final fresh sample")

        peak_sequence, peak_difference = max(
            differences, key=lambda item: item[1]
        )
        return ScrollAttemptMeasurement(
            pre_sequence=before.sequence,
            settled_sequence=settled.sequence,
            fresh_sample_count=len(fresh_samples),
            transient_peak_sequence=peak_sequence,
            max_transient_difference=peak_difference,
            settled_difference=self.difference(before.image, settled.image),
        )

    def classify(
        self,
        measurement: ScrollAttemptMeasurement,
        *,
        movement_threshold: float,
    ) -> ScrollAttemptKind:
        """Classify a measured attempt using an empirically supplied threshold."""

        if not isinstance(measurement, ScrollAttemptMeasurement):
            raise ValueError("measurement must be ScrollAttemptMeasurement")
        movement = _normalized_threshold(
            movement_threshold, "movement_threshold"
        )
        if measurement.max_transient_difference < movement:
            return ScrollAttemptKind.INEFFECTIVE
        if measurement.settled_difference <= self.unchanged_threshold:
            return ScrollAttemptKind.BOUNCE_CANDIDATE
        return ScrollAttemptKind.NORMAL

    def _thumbnail(self, frame: np.ndarray) -> np.ndarray:
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("frame must be a non-empty NumPy array")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must contain exactly three BGR channels")
        width, height = frame_dimensions(frame)
        x1, y1, x2, y2 = relative_region_to_pixels(
            self.region, width, height
        )
        gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        return cv2.resize(
            gray,
            (self.thumbnail_width, self.thumbnail_height),
            interpolation=cv2.INTER_AREA,
        )


def _normalized_threshold(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return float(value)


__all__ = (
    "CharacterSelectScrollDetector",
    "ScrollAttemptKind",
    "ScrollAttemptMeasurement",
)
