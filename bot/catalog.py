"""Minimal production semantic vocabulary and rules for Kritika."""

from __future__ import annotations

from bot.resolver import ContextResolver, ContextRule

SEMANTIC_CONFIDENCE_THRESHOLD = 0.80

SCREEN_LOBBY = "screen.lobby"
SCREEN_CHARACTER_SELECT = "screen.character_select"
SCREEN_BATTLE_MODE_SELECT = "screen.battle_mode_select"
SCREEN_BLACK_MARKET = "screen.black_market"
SCREEN_SOCKET = "screen.socket"
SCREEN_WORLD_BOSS = "screen.world_boss"
SCREEN_WORLD_BOSS_BATTLE = "screen.world_boss_battle"
POPUP_PURCHASE_CONFIRMATION = "popup.purchase_confirmation"
POPUP_INSUFFICIENT_GOLD = "popup.insufficient_gold"
POPUP_INVENTORY_FULL = "popup.inventory_full"
POPUP_WORLD_BOSS_PREVIOUS_REWARDS = "popup.world_boss_previous_rewards"
POPUP_SOCKET_INVENTORY_FULL = "popup.socket_inventory_full"
POPUP_SOCKET_ENHANCE_ALL = "popup.socket_enhance_all"
POPUP_SOCKET_NO_MATERIAL = "popup.socket_no_material"
POPUP_SOCKET_SELL = "popup.socket_sell"
POPUP_WORLD_BOSS_BAG_FULL = "popup.world_boss_bag_full"
OVERLAY_WORLD_BOSS_SELECT_BOSS = "overlay.world_boss_select_boss"
OVERLAY_WORLD_BOSS_RAID_COMPLETE = "overlay.world_boss_raid_complete"
MENU_QUICK = "menu.quick"

LANDMARK_LOBBY_TRADING_CENTER_LABEL = (
    "landmark.lobby_trading_center_label"
)
LANDMARK_CHARACTER_SELECT_HEADER = "landmark.character_select_header"
LANDMARK_MONSTER_WAVE_ENTRY_TITLE = "landmark.monster_wave_entry_title"
LANDMARK_BATTLE_MODE_SELECT_HEADER = "landmark.battle_mode_select_header"
LANDMARK_BLACK_MARKET_TITLE = "landmark.black_market_title"
LANDMARK_PURCHASE_CONFIRMATION_PROMPT = (
    "landmark.purchase_confirmation_prompt"
)
LANDMARK_INSUFFICIENT_GOLD_PROMPT = "landmark.insufficient_gold_prompt"
LANDMARK_INVENTORY_FULL_OK_BUTTON = "landmark.inventory_full_ok_button"
LANDMARK_QUICK_MENU_LOBBY_TILE = "landmark.quick_menu_lobby_tile"
LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER = (
    "landmark.world_boss_select_boss_header"
)
LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE = (
    "landmark.world_boss_previous_rewards_notice"
)
LANDMARK_SOCKET_TITLE = "landmark.socket_title"
LANDMARK_SOCKET_INVENTORY_FULL_PROMPT = "landmark.socket_inventory_full_prompt"
LANDMARK_SOCKET_ENHANCE_ALL_TITLE = "landmark.socket_enhance_all_title"
LANDMARK_SOCKET_NO_MATERIAL_PROMPT = "landmark.socket_no_material_prompt"
LANDMARK_SOCKET_SELL_BULK_BUTTON = "landmark.socket_sell_bulk_button"
LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE = (
    "landmark.socket_equipment_home_active"
)
LANDMARK_WORLD_BOSS_BAG_FULL_PROMPT = "landmark.world_boss_bag_full_prompt"
LANDMARK_WORLD_BOSS_SAPPHIRES_USED = "landmark.world_boss_sapphires_used"
LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE = (
    "landmark.world_boss_battle_current_damage"
)
LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE = (
    "landmark.world_boss_raid_complete_title"
)

SEMANTIC_OBSERVATION_NAMES = (
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
    LANDMARK_SOCKET_ENHANCE_ALL_TITLE,
    LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    LANDMARK_SOCKET_INVENTORY_FULL_PROMPT,
    LANDMARK_SOCKET_NO_MATERIAL_PROMPT,
    LANDMARK_SOCKET_SELL_BULK_BUTTON,
    LANDMARK_SOCKET_TITLE,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_BAG_FULL_PROMPT,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
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
        requires=(LANDMARK_LOBBY_TRADING_CENTER_LABEL,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_SOCKET,
        requires=(LANDMARK_SOCKET_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_BATTLE_MODE_SELECT,
        requires=(LANDMARK_BATTLE_MODE_SELECT_HEADER,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_WORLD_BOSS,
        requires=(LANDMARK_WORLD_BOSS_SAPPHIRES_USED,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_WORLD_BOSS_BATTLE,
        requires=(LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
)

OVERLAY_RULES = (
    ContextRule(
        name=OVERLAY_WORLD_BOSS_SELECT_BOSS,
        requires=(LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
        requires=(LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_SOCKET_INVENTORY_FULL,
        requires=(LANDMARK_SOCKET_INVENTORY_FULL_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_SOCKET_ENHANCE_ALL,
        requires=(LANDMARK_SOCKET_ENHANCE_ALL_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_SOCKET_NO_MATERIAL,
        requires=(LANDMARK_SOCKET_NO_MATERIAL_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_SOCKET_SELL,
        requires=(LANDMARK_SOCKET_SELL_BULK_BUTTON,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_WORLD_BOSS_BAG_FULL,
        requires=(
            LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
            LANDMARK_WORLD_BOSS_BAG_FULL_PROMPT,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=OVERLAY_WORLD_BOSS_RAID_COMPLETE,
        requires=(LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_INVENTORY_FULL,
        requires=(
            LANDMARK_BLACK_MARKET_TITLE,
            LANDMARK_INVENTORY_FULL_OK_BUTTON,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_INSUFFICIENT_GOLD,
        requires=(LANDMARK_INSUFFICIENT_GOLD_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_PURCHASE_CONFIRMATION,
        requires=(LANDMARK_PURCHASE_CONFIRMATION_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=MENU_QUICK,
        requires=(LANDMARK_QUICK_MENU_LOBBY_TILE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
)


def build_default_resolver() -> ContextResolver:
    """Build a fresh resolver for the current minimal Kritika catalog."""

    return ContextResolver(
        base_rules=BASE_CONTEXT_RULES,
        overlay_rules=OVERLAY_RULES,
    )
