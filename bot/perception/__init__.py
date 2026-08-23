"""Current production perception slice and its explicit composition helper."""

from __future__ import annotations

from pathlib import Path

from .engine import PerceptionDetector, PerceptionEngine
from .local_cv import LocalCvDetection, LocalCvDetector
from .specs import (
    BLACK_MARKET_TITLE_SPEC,
    DEFAULT_LOCAL_CV_SPECS,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    LinearGapCalibration,
    LocalCvSpec,
)


def build_default_perception(
    asset_root: str | Path | None = None,
) -> PerceptionEngine:
    """Build a fresh engine containing only the two Phase 3A detectors."""

    root = (
        Path(asset_root)
        if asset_root is not None
        else Path(__file__).resolve().parents[2]
    )
    return PerceptionEngine(
        detectors=tuple(
            LocalCvDetector(spec, asset_root=root)
            for spec in DEFAULT_LOCAL_CV_SPECS
        )
    )


__all__ = (
    "BLACK_MARKET_TITLE_SPEC",
    "DEFAULT_LOCAL_CV_SPECS",
    "PURCHASE_CONFIRMATION_PROMPT_SPEC",
    "LinearGapCalibration",
    "LocalCvDetection",
    "LocalCvDetector",
    "LocalCvSpec",
    "PerceptionDetector",
    "PerceptionEngine",
    "build_default_perception",
)
