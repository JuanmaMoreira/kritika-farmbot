"""Trading Center context, tab state and content readiness over snapshots.

Pure predicates in the Daily/MW idiom: no navigation, no input, no policy
beyond refusing to authorize motion on anything but positively demonstrated
content. Readiness is chrome plus a positive content signal on the same
snapshot; tab chrome alone (or a loading/transient frame) never authorizes
navigation or scroll. Entry actions and detectors arrive with HIL evidence;
this module only decides what observations mean.
"""

from __future__ import annotations

from enum import Enum

from bot.catalog import SEMANTIC_CONFIDENCE_THRESHOLD
from bot.state import ResolutionStatus
from bot.trading_center_semantics import (
    INDICATOR_TRADING_GENERAL_ACTIVE,
    INDICATOR_TRADING_KEYS_ACTIVE,
    INDICATOR_TRADING_KEYS_ROWS,
    INDICATOR_TRADING_MATERIAL_ROWS,
    SCREEN_TRADING,
)


class TradingTab(str, Enum):
    GENERAL = "general"
    KEYS = "keys"
    UNKNOWN = "unknown"
    CONTRADICTORY = "contradictory"


def has(snapshot, *names) -> bool:
    present = {
        observation.name
        for observation in snapshot.observations.observations
        if observation.confidence >= SEMANTIC_CONFIDENCE_THRESHOLD
    }
    return set(names) <= present


def is_trading_screen(snapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_TRADING
    )


def clean_trading(snapshot) -> bool:
    return is_trading_screen(snapshot) and not snapshot.state.overlays


def trading_tab(snapshot) -> TradingTab:
    """Resolve the active tab from exclusive tab-chrome evidence.

    Foreign contexts never report a usable tab. Both tab indicators at
    once is contradictory chrome: no input, never a guess.
    """
    if not is_trading_screen(snapshot):
        return TradingTab.UNKNOWN
    general = has(snapshot, INDICATOR_TRADING_GENERAL_ACTIVE)
    keys = has(snapshot, INDICATOR_TRADING_KEYS_ACTIVE)
    if general and keys:
        return TradingTab.CONTRADICTORY
    if general:
        return TradingTab.GENERAL
    if keys:
        return TradingTab.KEYS
    return TradingTab.UNKNOWN


def is_keys_content_ready(snapshot) -> bool:
    """Avatars & Keys tab with positively demonstrated key rows."""
    return (
        clean_trading(snapshot)
        and trading_tab(snapshot) is TradingTab.KEYS
        and has(snapshot, INDICATOR_TRADING_KEYS_ROWS)
    )


def is_materials_content_ready(snapshot) -> bool:
    """General tab with positively demonstrated material rows.

    Gate for the directed-scroll adapter: no scroll gesture may be planned
    before this predicate holds on a fresh snapshot.
    """
    return (
        clean_trading(snapshot)
        and trading_tab(snapshot) is TradingTab.GENERAL
        and has(snapshot, INDICATOR_TRADING_MATERIAL_ROWS)
    )


__all__ = (
    "TradingTab",
    "clean_trading",
    "has",
    "is_keys_content_ready",
    "is_materials_content_ready",
    "is_trading_screen",
    "trading_tab",
)
