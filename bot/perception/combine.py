"""Derived base-context evidence for stable and animating Combine states."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from bot.catalog import LANDMARK_COMBINE_CONTEXT
from bot.observations import Observation, ObservationSource

from .local_cv import LocalCvDetector
from .specs import COMBINE_ANIMATION_TAPPABLE_SPEC, COMBINE_FUSE_TAB_SPEC


class CombineContextDetector:
    """Emit one Combine base landmark from its tab or shared animation signal."""

    evaluation_id = "landmark.combine_context"

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._tab = LocalCvDetector(COMBINE_FUSE_TAB_SPEC, asset_root=asset_root)
        self._animation = LocalCvDetector(
            COMBINE_ANIMATION_TAPPABLE_SPEC, asset_root=asset_root
        )
        self.asset_paths = tuple(
            dict.fromkeys((*self._tab.asset_paths, *self._animation.asset_paths))
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        evidence = (
            *self._tab.detect(frame),
            *self._animation.detect(frame),
        )
        if not evidence:
            return ()
        return (
            Observation(
                name=LANDMARK_COMBINE_CONTEXT,
                confidence=max(item.confidence for item in evidence),
                source=ObservationSource.LOCAL_CV,
            ),
        )


__all__ = ("CombineContextDetector",)
