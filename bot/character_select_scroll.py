"""Deterministic visual comparison for the Character Select list viewport."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import cv2
import numpy as np

from bot.geometry import (
    RelativeRegion,
    frame_dimensions,
    normalize_relative_region,
    relative_region_to_pixels,
)


@dataclass(frozen=True)
class CharacterSelectScrollDetector:
    """Detect a repeated end-of-list swipe from a settled viewport crop.

    The crop contains only the three-column character grid. The animated
    character model, header, footer and Select button are deliberately outside
    it. A low normalized mean absolute difference means the content returned
    to the same settled position after the swipe.
    """

    region: RelativeRegion = (0.4900, 0.1900, 0.8500, 0.8050)
    thumbnail_width: int = 96
    thumbnail_height: int = 72
    unchanged_threshold: float = 0.0300

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

    def reached_end(self, first: np.ndarray, second: np.ndarray) -> bool:
        return self.difference(first, second) <= self.unchanged_threshold

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


__all__ = ("CharacterSelectScrollDetector",)
