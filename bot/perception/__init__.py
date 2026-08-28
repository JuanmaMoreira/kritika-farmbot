"""Current production perception slice and its explicit composition helper."""

from __future__ import annotations

from pathlib import Path

from .black_market import (
    BLACK_MARKET_GOLD_ASSET,
    BLACK_MARKET_GOLD_CALIBRATION,
    BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD,
    BLACK_MARKET_GOLD_OBSERVATION,
    BLACK_MARKET_GOLD_SLOT_REGIONS,
    BLACK_MARKET_GRID_COLUMNS,
    BLACK_MARKET_GRID_ROWS,
    BLACK_MARKET_SLOT_COUNT,
    BLACK_MARKET_PURCHASED_ASSETS,
    BLACK_MARKET_PURCHASED_CALIBRATION,
    BLACK_MARKET_PURCHASED_CONFIDENCE_THRESHOLD,
    BLACK_MARKET_PURCHASED_OBSERVATION,
    BLACK_MARKET_PURCHASED_SLOT_REGIONS,
    BlackMarketGoldDetector,
    BlackMarketGoldReading,
    BlackMarketPurchasedDetector,
    BlackMarketPurchasedReading,
)
from .engine import PerceptionDetector, PerceptionEngine
from .local_cv import LocalCvDetection, LocalCvDetector
from .specs import (
    BATTLE_MODE_SELECT_HEADER_SPEC,
    BLACK_MARKET_TITLE_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    DEFAULT_LOCAL_CV_SPECS,
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    INVENTORY_FULL_OK_BUTTON_SPEC,
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
    WORLD_BOSS_BAG_FULL_PROMPT_SPEC,
    WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC,
    WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC,
    WORLD_BOSS_INVENTORY_FULL_PROMPT_SPEC,
    WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC,
    WORLD_BOSS_SAPPHIRES_USED_SPEC,
    WORLD_BOSS_SELECT_BOSS_HEADER_SPEC,
    LinearGapCalibration,
    LocalCvSpec,
)


def build_default_perception(
    asset_root: str | Path | None = None,
) -> PerceptionEngine:
    """Build a fresh engine containing the approved production detectors."""

    root = (
        Path(asset_root)
        if asset_root is not None
        else Path(__file__).resolve().parents[2]
    )
    return PerceptionEngine(
        detectors=(
            *(
                LocalCvDetector(spec, asset_root=root)
                for spec in DEFAULT_LOCAL_CV_SPECS
            ),
            BlackMarketGoldDetector(asset_root=root),
            BlackMarketPurchasedDetector(asset_root=root),
        )
    )


__all__ = (
    "BLACK_MARKET_GOLD_ASSET",
    "BLACK_MARKET_GOLD_CALIBRATION",
    "BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD",
    "BLACK_MARKET_GOLD_OBSERVATION",
    "BLACK_MARKET_GOLD_SLOT_REGIONS",
    "BLACK_MARKET_GRID_COLUMNS",
    "BLACK_MARKET_GRID_ROWS",
    "BLACK_MARKET_SLOT_COUNT",
    "BLACK_MARKET_PURCHASED_ASSETS",
    "BLACK_MARKET_PURCHASED_CALIBRATION",
    "BLACK_MARKET_PURCHASED_CONFIDENCE_THRESHOLD",
    "BLACK_MARKET_PURCHASED_OBSERVATION",
    "BLACK_MARKET_PURCHASED_SLOT_REGIONS",
    "BLACK_MARKET_TITLE_SPEC",
    "BATTLE_MODE_SELECT_HEADER_SPEC",
    "BlackMarketGoldDetector",
    "BlackMarketGoldReading",
    "BlackMarketPurchasedDetector",
    "BlackMarketPurchasedReading",
    "CHARACTER_SELECT_HEADER_SPEC",
    "DEFAULT_LOCAL_CV_SPECS",
    "INSUFFICIENT_GOLD_PROMPT_SPEC",
    "INVENTORY_FULL_OK_BUTTON_SPEC",
    "PURCHASE_CONFIRMATION_PROMPT_SPEC",
    "QUICK_MENU_LOBBY_TILE_SPEC",
    "WORLD_BOSS_BAG_FULL_PROMPT_SPEC",
    "WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC",
    "WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC",
    "WORLD_BOSS_INVENTORY_FULL_PROMPT_SPEC",
    "WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC",
    "WORLD_BOSS_SAPPHIRES_USED_SPEC",
    "WORLD_BOSS_SELECT_BOSS_HEADER_SPEC",
    "LinearGapCalibration",
    "LOBBY_TRADING_CENTER_LABEL_SPEC",
    "LocalCvDetection",
    "LocalCvDetector",
    "LocalCvSpec",
    "PerceptionDetector",
    "PerceptionEngine",
    "build_default_perception",
)
