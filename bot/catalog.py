"""Minimal production semantic vocabulary and rules for Kritika."""

from __future__ import annotations

from bot.resolver import ContextResolver, ContextRule

SEMANTIC_CONFIDENCE_THRESHOLD = 0.80

SCREEN_LOBBY = "screen.lobby"
SCREEN_CHARACTER_SELECT = "screen.character_select"
SCREEN_BATTLE_MODE_SELECT = "screen.battle_mode_select"
SCREEN_BLACK_MARKET = "screen.black_market"
SCREEN_COMBINE = "screen.combine"
SCREEN_GUILD = "screen.guild"
SCREEN_MAILBOX = "screen.mailbox"
SCREEN_QUESTS = "screen.quests"
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
POPUP_EQUIPMENT_INVENTORY_FULL = "popup.equipment_inventory_full"
POPUP_COMBINE_ALL = "popup.combine_all"
POPUP_ETHEREAL_MASS_COMBINE = "popup.ethereal_mass_combine"
POPUP_ETHEREAL_NO_MATERIAL = "popup.ethereal_no_material"
OVERLAY_WORLD_BOSS_SELECT_BOSS = "overlay.world_boss_select_boss"
OVERLAY_WORLD_BOSS_RAID_COMPLETE = "overlay.world_boss_raid_complete"
MENU_QUICK = "menu.quick"
MODE_COMBINE_FUSE = "mode.combine_fuse"
MODE_COMBINE_TRANSMUTE = "mode.combine_transmute"
MODE_DAILY_QUESTS = "mode.daily_quests"
MODE_MAILBOX_CHARACTER_MAIL = "mode.mailbox_character_mail"
PANEL_COMBINE_AWAKENED_TRANSMUTE = "panel.combine_awakened_transmute"
PANEL_COMBINE_ETHEREAL_RANDOM_PART = "panel.combine_ethereal_random_part"
STATUS_COMBINE_ETHEREAL_AVAILABLE = "status.combine_ethereal_available"
STATUS_COMBINE_FUSE_AVAILABLE = "status.combine_fuse_available"
STATUS_COMBINE_TRANSMUTE_AVAILABLE = "status.combine_transmute_available"
STATUS_DAILY_QUESTS_CLAIMABLE = "status.daily_quests_claimable"
STATUS_GUILD_ATTENDANCE_ACTIVE = "status.guild_attendance_active"
STATUS_GUILD_ATTENDANCE_COMPLETED = "status.guild_attendance_completed"
STATUS_MAILBOX_CLAIMABLE = "status.mailbox_claimable"
STATUS_MAILBOX_READ_MAIL_PRESENT = "status.mailbox_read_mail_present"

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
LANDMARK_SOCKET_TAB = "landmark.socket_tab"
LANDMARK_SOCKET_INVENTORY_FULL_PROMPT = "landmark.socket_inventory_full_prompt"
LANDMARK_SOCKET_ENHANCE_ALL_TITLE = "landmark.socket_enhance_all_title"
LANDMARK_SOCKET_NO_MATERIAL_PROMPT = "landmark.socket_no_material_prompt"
LANDMARK_SOCKET_SELL_BULK_BUTTON = "landmark.socket_sell_bulk_button"
LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE = (
    "landmark.socket_equipment_home_active"
)
LANDMARK_WORLD_BOSS_SAPPHIRES_USED = "landmark.world_boss_sapphires_used"
LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE = (
    "landmark.world_boss_battle_current_damage"
)
LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE = (
    "landmark.world_boss_raid_complete_title"
)
LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT = (
    "landmark.equipment_inventory_full_prompt"
)
LANDMARK_COMBINE_FUSE_TAB = "landmark.combine_fuse_tab"
LANDMARK_COMBINE_CONTEXT = "landmark.combine_context"
LANDMARK_COMBINE_FUSE_ACTIVE = "landmark.combine_fuse_active"
LANDMARK_COMBINE_TRANSMUTE_ACTIVE = "landmark.combine_transmute_active"
INDICATOR_COMBINE_ROWS = "indicator.combine_rows"
INDICATOR_COMBINE_ROWS_UPPER = "indicator.combine_rows_upper"
INDICATOR_COMBINE_ROW_BOTTOM = "indicator.combine_row_bottom"
LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE = (
    "landmark.combine_awakened_transmute_title"
)
LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE = (
    "landmark.combine_ethereal_random_part_title"
)
LANDMARK_COMBINE_ALL_TITLE = "landmark.combine_all_title"
LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT = (
    "landmark.combine_ethereal_mass_prompt"
)
LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT = (
    "landmark.combine_ethereal_no_material_prompt"
)
ACTIVITY_COMBINE_ANIMATION_TAPPABLE = (
    "activity.combine_animation_tappable"
)
LANDMARK_DAILY_QUESTS_TITLE = "landmark.daily_quests_title"
LANDMARK_DAILY_QUESTS_TAB_ACTIVE = "landmark.daily_quests_tab_active"
LANDMARK_DAILY_QUESTS_ROW_CLAIM_BUTTON = (
    "landmark.daily_quests_row_claim_button"
)
LANDMARK_GUILD_MESSAGE_TAB = "landmark.guild_message_tab"
INDICATOR_GUILD_ATTENDANCE_ACTIVE = "indicator.guild_attendance_active"
INDICATOR_GUILD_ATTENDANCE_COMPLETED = (
    "indicator.guild_attendance_completed"
)
LANDMARK_MAILBOX_TITLE = "landmark.mailbox_title"
LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE = (
    "landmark.mailbox_character_mail_active"
)
LANDMARK_MAILBOX_ROW_CLAIM_BUTTON = "landmark.mailbox_row_claim_button"
LANDMARK_MAILBOX_ROW_DELETE_BUTTON = "landmark.mailbox_row_delete_button"
ACTIVITY_MAILBOX_CLAIM_PROCESSING = "activity.mailbox_claim_processing"

SEMANTIC_OBSERVATION_NAMES = (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    ACTIVITY_MAILBOX_CLAIM_PROCESSING,
    INDICATOR_COMBINE_ROW_BOTTOM,
    INDICATOR_COMBINE_ROWS,
    INDICATOR_COMBINE_ROWS_UPPER,
    INDICATOR_GUILD_ATTENDANCE_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_COMPLETED,
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_DAILY_QUESTS_ROW_CLAIM_BUTTON,
    LANDMARK_DAILY_QUESTS_TAB_ACTIVE,
    LANDMARK_DAILY_QUESTS_TITLE,
    LANDMARK_GUILD_MESSAGE_TAB,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE,
    LANDMARK_MAILBOX_ROW_CLAIM_BUTTON,
    LANDMARK_MAILBOX_ROW_DELETE_BUTTON,
    LANDMARK_MAILBOX_TITLE,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
    LANDMARK_SOCKET_ENHANCE_ALL_TITLE,
    LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    LANDMARK_SOCKET_INVENTORY_FULL_PROMPT,
    LANDMARK_SOCKET_NO_MATERIAL_PROMPT,
    LANDMARK_SOCKET_SELL_BULK_BUTTON,
    LANDMARK_SOCKET_TAB,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    LANDMARK_COMBINE_ALL_TITLE,
    LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE,
    LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT,
    LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT,
    LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE,
    LANDMARK_COMBINE_FUSE_ACTIVE,
    LANDMARK_COMBINE_CONTEXT,
    LANDMARK_COMBINE_FUSE_TAB,
    LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
    LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT,
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
        name=SCREEN_GUILD,
        requires=(LANDMARK_GUILD_MESSAGE_TAB,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_MAILBOX,
        requires=(LANDMARK_MAILBOX_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_QUESTS,
        requires=(LANDMARK_DAILY_QUESTS_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_COMBINE,
        requires=(LANDMARK_COMBINE_CONTEXT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=SCREEN_SOCKET,
        requires=(LANDMARK_SOCKET_TAB,),
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
        name=STATUS_GUILD_ATTENDANCE_ACTIVE,
        requires=(
            LANDMARK_GUILD_MESSAGE_TAB,
            INDICATOR_GUILD_ATTENDANCE_ACTIVE,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_GUILD_ATTENDANCE_COMPLETED,
        requires=(
            LANDMARK_GUILD_MESSAGE_TAB,
            INDICATOR_GUILD_ATTENDANCE_COMPLETED,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=MODE_DAILY_QUESTS,
        requires=(LANDMARK_DAILY_QUESTS_TAB_ACTIVE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_DAILY_QUESTS_CLAIMABLE,
        requires=(
            LANDMARK_DAILY_QUESTS_TAB_ACTIVE,
            LANDMARK_DAILY_QUESTS_ROW_CLAIM_BUTTON,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=MODE_MAILBOX_CHARACTER_MAIL,
        requires=(LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_MAILBOX_CLAIMABLE,
        requires=(
            LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE,
            LANDMARK_MAILBOX_ROW_CLAIM_BUTTON,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_MAILBOX_READ_MAIL_PRESENT,
        requires=(
            LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE,
            LANDMARK_MAILBOX_ROW_DELETE_BUTTON,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_EQUIPMENT_INVENTORY_FULL,
        requires=(LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=MODE_COMBINE_FUSE,
        requires=(LANDMARK_COMBINE_FUSE_ACTIVE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=MODE_COMBINE_TRANSMUTE,
        requires=(LANDMARK_COMBINE_TRANSMUTE_ACTIVE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_COMBINE_TRANSMUTE_AVAILABLE,
        requires=(
            LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
            INDICATOR_COMBINE_ROWS_UPPER,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_COMBINE_ETHEREAL_AVAILABLE,
        requires=(
            LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
            INDICATOR_COMBINE_ROW_BOTTOM,
        ),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=STATUS_COMBINE_FUSE_AVAILABLE,
        requires=(LANDMARK_COMBINE_FUSE_ACTIVE, INDICATOR_COMBINE_ROWS),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=PANEL_COMBINE_AWAKENED_TRANSMUTE,
        requires=(LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=PANEL_COMBINE_ETHEREAL_RANDOM_PART,
        requires=(LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_COMBINE_ALL,
        requires=(LANDMARK_COMBINE_ALL_TITLE,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_ETHEREAL_MASS_COMBINE,
        requires=(LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
    ContextRule(
        name=POPUP_ETHEREAL_NO_MATERIAL,
        requires=(LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT,),
        min_confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
    ),
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
