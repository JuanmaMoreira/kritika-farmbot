"""Immutable configuration for the currently approved local CV detectors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

from bot.catalog import (
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
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
# the existing template separates all 18 confirmed positives from 128
# cross-context negatives in the current 146-entry production corpus. Both
# empirical anchors reflect that expanded global evaluation.
BLACK_MARKET_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_BLACK_MARKET_TITLE,
    asset_path=Path("assets/ui/black-market-id.png"),
    region=(0.4395, 0.0997, 0.5579, 0.1495),
    calibration=LinearGapCalibration(
        negative_anchor=0.301844984292984,
        positive_anchor=0.39833250641822815,
    ),
)

# Human-confirmed live literal shown directly after selecting a GOLD offer
# that cannot be afforded. The popup remains independent from Purchase
# Confirmation and returns to Black Market when the user chooses No. One
# positive is currently available, so the strong empirical gap is provisional.
INSUFFICIENT_GOLD_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    asset_path=Path("assets/ui/landmarks/insufficient-gold-prompt-current.png"),
    region=(
        1100 / 2712,
        500 / 1224,
        1620 / 2712,
        610 / 1224,
    ),
    calibration=LinearGapCalibration(
        negative_anchor=0.443979948759079,
        positive_anchor=0.9999777674674988,
    ),
)

# Current-season common OK button from a human-confirmed Black Market
# inventory-cap popup. The search region is position-specific, and the
# catalog additionally requires the Black Market title so generic OK dialogs
# elsewhere do not become popup.inventory_full. Six fresh frames score
# 0.983645380..0.999940693; the strongest reviewed non-inventory OK scores
# 0.894896746. Message text is deliberately outside the landmark.
INVENTORY_FULL_OK_BUTTON_SPEC = LocalCvSpec(
    name=LANDMARK_INVENTORY_FULL_OK_BUTTON,
    asset_path=Path(
        "assets/ui/landmarks/inventory-full-ok-button-current.png"
    ),
    region=(0.41, 0.54, 0.59, 0.70),
    calibration=LinearGapCalibration(
        negative_anchor=0.8948967456817627,
        positive_anchor=0.9836453795433044,
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
# Calibration uses 18 confirmed positives and remains clean against 128
# negatives in the expanded production corpus; it is an empirical gap, not a
# probability estimate.
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
# and search region were originally calibrated over 57 confirmed human labels.
# It is validated against the current corpus, not a controlled multi-season
# dataset. A season change requires new positives and repeated evaluation;
# no broader-strip or gold-anchor fallback is implied. Its negative anchor now
# reflects the expanded 146-entry production corpus.
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
        negative_anchor=0.47562649846076965,
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
        negative_anchor=0.2776434123516083,
        positive_anchor=0.43373382091522217,
    ),
)

# Current Survival selector header, deliberately distinct from the PvP
# "Select Mode" screen. Seventeen confirmed positives (including the earlier
# acquisition corpus) separate from 129 current/cross-context negatives.
BATTLE_MODE_SELECT_HEADER_SPEC = LocalCvSpec(
    name=LANDMARK_BATTLE_MODE_SELECT_HEADER,
    asset_path=Path("assets/ui/landmarks/battle-mode-select-header-current.png"),
    region=(0.36, 0.08, 0.64, 0.20),
    calibration=LinearGapCalibration(
        negative_anchor=0.43016597628593445,
        positive_anchor=0.7028394937515259,
    ),
)

# Select Boss preserves and dims Battle Mode Select underneath and Close
# restores it, so this header identifies an overlay rather than a base screen.
WORLD_BOSS_SELECT_BOSS_HEADER_SPEC = LocalCvSpec(
    name=LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    asset_path=Path(
        "assets/ui/landmarks/world-boss-select-boss-header-current.png"
    ),
    region=(0.33, 0.01, 0.67, 0.15),
    calibration=LinearGapCalibration(
        negative_anchor=0.28989267349243164,
        positive_anchor=0.9996430277824402,
    ),
)

# Stable sentence in the optional previous-season ranking popup. Boss number,
# boss identity, ranks, damage and rewards remain outside the landmark.
WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC = LocalCvSpec(
    name=LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    asset_path=Path(
        "assets/ui/landmarks/world-boss-previous-rewards-notice-current.png"
    ),
    region=(0.25, 0.78, 0.75, 0.91),
    calibration=LinearGapCalibration(
        negative_anchor=0.37060102820396423,
        positive_anchor=0.9992043375968933,
    ),
)

# The fixed cost label is structural World Boss UI. It excludes the rotating
# boss, current ranking, damage and resource values.
WORLD_BOSS_SAPPHIRES_USED_SPEC = LocalCvSpec(
    name=LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    asset_path=Path("assets/ui/landmarks/world-boss-sapphires-used-current.png"),
    region=(0.45, 0.74, 0.64, 0.88),
    calibration=LinearGapCalibration(
        negative_anchor=0.6100667715072632,
        positive_anchor=0.9983233213424683,
    ),
)

# World Boss battle-specific damage HUD. The crop excludes numeric damage;
# Raid Complete remains an overlay over the same productive battle base.
WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC = LocalCvSpec(
    name=LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    asset_path=Path(
        "assets/ui/landmarks/world-boss-battle-current-damage-current.png"
    ),
    region=(0.015, 0.22, 0.20, 0.43),
    calibration=LinearGapCalibration(
        negative_anchor=0.40120941400527954,
        positive_anchor=0.7584050297737122,
    ),
)

# Result title over the still-visible World Boss battle HUD. Reward quantity,
# damage, battle time and background action are deliberately excluded.
WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    asset_path=Path("assets/ui/landmarks/world-boss-raid-complete-current.png"),
    region=(0.32, 0.14, 0.68, 0.36),
    calibration=LinearGapCalibration(
        negative_anchor=0.4195970892906189,
        positive_anchor=0.9845049381256104,
    ),
)

DEFAULT_LOCAL_CV_SPECS = (
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    BATTLE_MODE_SELECT_HEADER_SPEC,
    BLACK_MARKET_TITLE_SPEC,
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    INVENTORY_FULL_OK_BUTTON_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
    WORLD_BOSS_SELECT_BOSS_HEADER_SPEC,
    WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC,
    WORLD_BOSS_SAPPHIRES_USED_SPEC,
    WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC,
    WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC,
)
