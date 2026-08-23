"""Minimal production semantic vocabulary and rules for Kritika."""

from __future__ import annotations

from bot.resolver import ContextResolver, ContextRule

SEMANTIC_CONFIDENCE_THRESHOLD = 0.80

SCREEN_LOBBY = "screen.lobby"
SCREEN_CHARACTER_SELECT = "screen.character_select"
SCREEN_SURVIVAL = "screen.survival"
SCREEN_BLACK_MARKET = "screen.black_market"
POPUP_BLACK_MARKET_PURCHASE_CONFIRMATION = (
    "popup.black_market_purchase_confirmation"
)

LANDMARK_LOBBY_HEADER = "landmark.lobby_header"
LANDMARK_CHARACTER_SELECT_HEADER = "landmark.character_select_header"
LANDMARK_SURVIVAL_TITLE = "landmark.survival_title"
LANDMARK_BLACK_MARKET_TITLE = "landmark.black_market_title"
LANDMARK_BLACK_MARKET_PURCHASE_DIALOG = (
    "landmark.black_market_purchase_dialog"
)

SEMANTIC_OBSERVATION_NAMES = (
    LANDMARK_BLACK_MARKET_PURCHASE_DIALOG,
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_LOBBY_HEADER,
    LANDMARK_SURVIVAL_TITLE,
)

BASE_CONTEXT_RULES = (
    ContextRule(
        name=SCREEN_BLACK_MARKET,
        requires=(LANDMARK_BLACK_MARKET_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_CHARACTER_SELECT,
        requires=(LANDMARK_CHARACTER_SELECT_HEADER,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_LOBBY,
        requires=(LANDMARK_LOBBY_HEADER,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_SURVIVAL,
        requires=(LANDMARK_SURVIVAL_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
)

OVERLAY_RULES = (
    ContextRule(
        name=POPUP_BLACK_MARKET_PURCHASE_CONFIRMATION,
        requires=(LANDMARK_BLACK_MARKET_PURCHASE_DIALOG,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
)


def build_default_resolver() -> ContextResolver:
    """Build a fresh resolver for the current minimal Kritika catalog."""

    return ContextResolver(
        base_rules=BASE_CONTEXT_RULES,
        overlay_rules=OVERLAY_RULES,
    )
