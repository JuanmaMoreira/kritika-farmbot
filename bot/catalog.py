"""Minimal production semantic vocabulary and rules for Kritika."""

from __future__ import annotations

from bot.resolver import ContextResolver, ContextRule

SEMANTIC_CONFIDENCE_THRESHOLD = 0.80

SCREEN_LOBBY = "screen.lobby"
SCREEN_CHARACTER_SELECT = "screen.character_select"
SCREEN_BATTLE_MODE_SELECT = "screen.battle_mode_select"
SCREEN_BLACK_MARKET = "screen.black_market"
POPUP_PURCHASE_CONFIRMATION = "popup.purchase_confirmation"

LANDMARK_GOLD_CURRENCY_ICON = "landmark.gold_currency_icon"
LANDMARK_CHARACTER_SELECT_HEADER = "landmark.character_select_header"
LANDMARK_MONSTER_WAVE_ENTRY_TITLE = "landmark.monster_wave_entry_title"
LANDMARK_BLACK_MARKET_TITLE = "landmark.black_market_title"
LANDMARK_PURCHASE_CONFIRMATION_PROMPT = (
    "landmark.purchase_confirmation_prompt"
)

SEMANTIC_OBSERVATION_NAMES = (
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_GOLD_CURRENCY_ICON,
    LANDMARK_MONSTER_WAVE_ENTRY_TITLE,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
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
        name=SCREEN_BATTLE_MODE_SELECT,
        requires=(LANDMARK_MONSTER_WAVE_ENTRY_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
)

OVERLAY_RULES = (
    ContextRule(
        name=POPUP_PURCHASE_CONFIRMATION,
        requires=(LANDMARK_PURCHASE_CONFIRMATION_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
)


def build_default_resolver() -> ContextResolver:
    """Build a fresh resolver for the current minimal Kritika catalog."""

    return ContextResolver(
        base_rules=BASE_CONTEXT_RULES,
        overlay_rules=OVERLAY_RULES,
    )
