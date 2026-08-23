"""Immutable configuration for the currently approved local CV detectors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

from bot.catalog import (
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
)
from bot.geometry import RelativeRegion, normalize_relative_region
from bot.observations import validate_semantic_name


@dataclass(frozen=True)
class LinearGapCalibration:
    """Normalize a raw score inside a provisional empirical separation gap.

    This mapping is not a probability or a statistical calibration. It only
    expresses where a score lies between the highest confirmed negative and
    the lowest confirmed positive in the reviewed Phase 2D dataset.
    """

    negative_anchor: float
    positive_anchor: float

    def __post_init__(self) -> None:
        negative = _finite_real(self.negative_anchor, "negative_anchor")
        positive = _finite_real(self.positive_anchor, "positive_anchor")
        if negative >= positive:
            raise ValueError("negative_anchor must be less than positive_anchor")
        object.__setattr__(self, "negative_anchor", negative)
        object.__setattr__(self, "positive_anchor", positive)

    def confidence(self, raw_match_score: Real) -> float:
        """Return the score's clamped linear position in the empirical gap."""

        score = _finite_real(raw_match_score, "raw_match_score")
        normalized = (score - self.negative_anchor) / (
            self.positive_anchor - self.negative_anchor
        )
        return min(1.0, max(0.0, normalized))


@dataclass(frozen=True)
class LocalCvSpec:
    """Template, search region and calibration for one semantic landmark."""

    name: str
    asset_path: Path
    region: RelativeRegion
    calibration: LinearGapCalibration

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        path = Path(self.asset_path)
        if path == Path("."):
            raise ValueError("asset_path must identify a template file")
        object.__setattr__(self, "asset_path", path)
        object.__setattr__(
            self, "region", normalize_relative_region(self.region)
        )
        if not isinstance(self.calibration, LinearGapCalibration):
            raise ValueError("calibration must be a LinearGapCalibration")


def _finite_real(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} must be a finite real number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite real number")
    return result


# Anchors reproduced on 2026-08-22 from the versioned human-confirmed manifest
# and all 173 local Phase 2D screencaps, using native-size templates and the
# exact normalized regions below. They remain provisional because the reviewed
# positive sets contain only six and three screenshots respectively.
BLACK_MARKET_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_BLACK_MARKET_TITLE,
    asset_path=Path("assets/ui/black-market-id.png"),
    region=(0.4395, 0.0997, 0.5579, 0.1495),
    calibration=LinearGapCalibration(
        negative_anchor=0.2230203002691269,
        positive_anchor=0.997641384601593,
    ),
)

PURCHASE_CONFIRMATION_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    asset_path=Path("assets/ui/black-market-purchase-confirmation-id.png"),
    region=(0.4624, 0.4828, 0.5376, 0.5294),
    calibration=LinearGapCalibration(
        negative_anchor=0.48758167028427124,
        positive_anchor=0.9959162473678589,
    ),
)

DEFAULT_LOCAL_CV_SPECS = (
    BLACK_MARKET_TITLE_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
)
