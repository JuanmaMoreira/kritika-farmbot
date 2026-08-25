"""Immutable configuration for the currently approved local CV detectors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

from bot.catalog import (
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
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
    """Template variants, search region and calibration for one landmark.

    ``asset_path`` remains the primary rendering. ``variant_asset_paths`` is
    reserved for human-confirmed rendering variants of the same semantic
    signal; detector confidence is calibrated over the maximum raw match.
    """

    name: str
    asset_path: Path
    region: RelativeRegion
    calibration: LinearGapCalibration
    variant_asset_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        path = Path(self.asset_path)
        if path == Path("."):
            raise ValueError("asset_path must identify a template file")
        object.__setattr__(self, "asset_path", path)
        variants = tuple(Path(item) for item in self.variant_asset_paths)
        if any(item == Path(".") for item in variants):
            raise ValueError("variant_asset_paths must identify template files")
        if path in variants or len(set(variants)) != len(variants):
            raise ValueError("template asset paths must be unique")
        object.__setattr__(self, "variant_asset_paths", variants)
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


# Black Market retained the historical asset and crop after Phase 3F visual
# review. Current-season Workbench positives show a wider text rendering, but
# the existing template still separates all 11 confirmed positives from all
# 51 confirmed negatives. Only its empirical positive anchor changed.
BLACK_MARKET_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_BLACK_MARKET_TITLE,
    asset_path=Path("assets/ui/black-market-id.png"),
    region=(0.4395, 0.0997, 0.5579, 0.1495),
    calibration=LinearGapCalibration(
        negative_anchor=0.2230203002691269,
        positive_anchor=0.3996976613998413,
    ),
)

# Purchase Confirmation has two human-confirmed renderings of the same literal
# prompt. The Phase 3F search region admits both native-size templates while
# deliberately excluding the strongest known generic-confirmation confusion
# ("Still proceed?") farther to the right. No scaling is performed.
PURCHASE_CONFIRMATION_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    asset_path=Path("assets/ui/black-market-purchase-confirmation-id.png"),
    variant_asset_paths=(
        Path("assets/ui/landmarks/purchase-confirmation-prompt-current.png"),
    ),
    region=(
        1235 / 2712,
        590 / 1224,
        1460 / 2712,
        647 / 1224,
    ),
    calibration=LinearGapCalibration(
        negative_anchor=0.4875827729701996,
        positive_anchor=0.9959162473678589,
    ),
)

# Current-season rendering of the literal "Lobby" tile inside Quick Menu.
# The horizontal search span covers the two human-confirmed placements over
# Lobby and Inventory without encoding legacy per-context coordinate offsets.
# Calibration uses 18 confirmed positives and 77 confirmed negatives from the
# Phase 3H.2 corpus; it is an empirical gap, not a probability estimate.
QUICK_MENU_LOBBY_TILE_SPEC = LocalCvSpec(
    name=LANDMARK_QUICK_MENU_LOBBY_TILE,
    asset_path=Path("assets/ui/landmarks/quick-menu-lobby-tile.png"),
    region=(0.02, 0.10, 0.25, 0.32),
    calibration=LinearGapCalibration(
        negative_anchor=0.2981472909450531,
        positive_anchor=0.9826233983039856,
    ),
)

# Curated byte-for-byte from the Phase 3B.1 candidate generated from
# screencaps/semantic/lobby/20260823T025455_304538Z.png. The 235x70 template
# and search region were recalibrated over all 57 confirmed human labels.
# It is validated against the current corpus, not a controlled multi-season
# dataset. A season change requires new positives and repeated evaluation;
# no broader-strip or gold-anchor fallback is implied.
LOBBY_TRADING_CENTER_LABEL_SPEC = LocalCvSpec(
    name=LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    asset_path=Path(
        "assets/ui/landmarks/lobby-trading-center-label.png"
    ),
    region=(
        0.19095870206489673,
        0.905032679738562,
        0.29761061946902656,
        0.9822222222222222,
    ),
    calibration=LinearGapCalibration(
        negative_anchor=0.4657268226146698,
        positive_anchor=0.7198567986488342,
    ),
)

# Curated byte-for-byte from the Phase 3B candidate generated from
# screencaps/semantic/character_select/20260823T025343_820522Z.png. This
# 440x80 current rendering replaces the overlapping legacy template. Its
# template-based calibration remains reproducibly updateable as labels grow.
# Phase 3F Workbench Black Market frames raised its confirmed negative anchor
# without threatening the still-positive gap.
CHARACTER_SELECT_HEADER_SPEC = LocalCvSpec(
    name=LANDMARK_CHARACTER_SELECT_HEADER,
    asset_path=Path("assets/ui/landmarks/character-select-header.png"),
    region=(
        0.40297935103244836,
        0.02676470588235294,
        0.5852212389380531,
        0.11212418300653594,
    ),
    calibration=LinearGapCalibration(
        negative_anchor=0.2749116122722626,
        positive_anchor=0.43373382091522217,
    ),
)

DEFAULT_LOCAL_CV_SPECS = (
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    BLACK_MARKET_TITLE_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
)
