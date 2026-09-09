"""Monster Wave observations; no gameplay policy or cross-frame state."""

SCREEN_MONSTER_WAVE = "screen.monster_wave"
STATUS_MONSTER_WAVE_DAILY_ACTIVE = "status.monster_wave_daily_active"
MW_SCREEN = "landmark.monster_wave_title"
MW_NEEDS_TICKETS = "indicator.monster_wave_needs_tickets"
MW_READY = "indicator.monster_wave_ready"
MW_TIMER = "indicator.monster_wave_time_remaining"
MW_SKIP_START = "landmark.monster_wave_skip_process"
MW_MAX = "indicator.monster_wave_max_selected"
MW_CONTROLS_CLEAR = "landmark.monster_wave_usage_unobstructed"
MW_TOOLTIP = "landmark.monster_wave_usage_tooltip"
MW_PURCHASE = "landmark.monster_wave_ticket_purchase"
MW_PURCHASE_FULL = "indicator.monster_wave_purchase_full"
MW_INSUFFICIENT = "landmark.monster_wave_insufficient_sapphires"
MW_BOARD = "landmark.monster_wave_inventory_board"
MW_CLEAR = "landmark.monster_wave_clear"
MW_DAILY = "indicator.monster_wave_daily_active"
MW_RANKING = "landmark.monster_wave_new_ranking"
MW_WEEKLY = "landmark.monster_wave_weekly_results"
POPUP_MW_PURCHASE = "popup.monster_wave_ticket_purchase"
POPUP_MW_INSUFFICIENT = "popup.monster_wave_insufficient_sapphires"
POPUP_MW_BOARD = "popup.monster_wave_inventory_board"
POPUP_MW_CLEAR = "popup.monster_wave_clear"
OVERLAY_MW_TOOLTIP = "overlay.monster_wave_usage_tooltip"
POPUP_MW_RANKING = "popup.monster_wave_new_ranking"
POPUP_MW_WEEKLY = "popup.monster_wave_weekly_results"

MW_OBSERVATIONS = (
    MW_SCREEN, MW_NEEDS_TICKETS, MW_READY, MW_TIMER, MW_SKIP_START,
    MW_MAX, MW_CONTROLS_CLEAR, MW_TOOLTIP, MW_PURCHASE, MW_PURCHASE_FULL,
    MW_INSUFFICIENT, MW_BOARD, MW_CLEAR, MW_DAILY, MW_RANKING, MW_WEEKLY,
)
MW_OVERLAY_LANDMARKS = (
    (POPUP_MW_PURCHASE, MW_PURCHASE), (POPUP_MW_INSUFFICIENT, MW_INSUFFICIENT),
    (POPUP_MW_BOARD, MW_BOARD), (POPUP_MW_CLEAR, MW_CLEAR),
    (OVERLAY_MW_TOOLTIP, MW_TOOLTIP), (POPUP_MW_RANKING, MW_RANKING),
    (POPUP_MW_WEEKLY, MW_WEEKLY),
)
