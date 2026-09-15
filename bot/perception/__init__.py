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
from .combine import CombineContextDetector
from .daily_quests import (
    DAILY_QUESTS_LOADING_CALIBRATION,
    DAILY_QUESTS_LOADING_CONFIDENCE_THRESHOLD,
    DAILY_QUESTS_LOADING_HSV_LOWER,
    DAILY_QUESTS_LOADING_HSV_UPPER,
    DAILY_QUESTS_LOADING_REGION,
    DAILY_QUESTS_PROGRESS_REWARD_CALIBRATION,
    DAILY_QUESTS_PROGRESS_REWARD_CONFIDENCE_THRESHOLD,
    DAILY_QUESTS_PROGRESS_REWARD_HSV_LOWER,
    DAILY_QUESTS_PROGRESS_REWARD_HSV_UPPER,
    DAILY_QUESTS_PROGRESS_REWARD_REGION,
    DAILY_QUESTS_ROWS_BRIGHT_VALUE,
    DAILY_QUESTS_ROWS_CALIBRATION,
    DAILY_QUESTS_ROWS_CONFIDENCE_THRESHOLD,
    DAILY_QUESTS_ROWS_REGION,
    DailyQuestsLoadingDetector,
    DailyQuestsLoadingReading,
    DailyQuestsProgressRewardDetector,
    DailyQuestsProgressRewardReading,
    DailyQuestsRowsDetector,
    DailyQuestsRowsReading,
)
from .guild import (
    GUILD_ATTENDANCE_ACTIVE_CALIBRATION,
    GUILD_ATTENDANCE_COMPLETED_CALIBRATION,
    GUILD_ATTENDANCE_CONFIDENCE_THRESHOLD,
    GUILD_ATTENDANCE_REGION,
    GuildAttendanceDetector,
    GuildAttendanceReading,
)
from .local_cv import LocalCvDetection, LocalCvDetector
from .mailbox import (
    MAILBOX_CLAIM_PROCESSING_CALIBRATION,
    MAILBOX_CLAIM_PROCESSING_CONFIDENCE_THRESHOLD,
    MAILBOX_CLAIM_PROCESSING_HSV_LOWER,
    MAILBOX_CLAIM_PROCESSING_HSV_UPPER,
    MAILBOX_CLAIM_PROCESSING_REGION,
    MailboxClaimProcessingDetector,
    MailboxClaimProcessingReading,
)
from .pet_summon import (
    PET_EPIC_AVAILABILITY_CONFIDENCE_THRESHOLD,
    PET_EPIC_AVAILABILITY_REGION,
    PET_EPIC_AVAILABLE_CALIBRATION,
    PET_EPIC_UNAVAILABLE_CALIBRATION,
    PetEpicAvailabilityDetector,
    PetEpicAvailabilityReading,
)
from .pet_combine import (
    PET_LOW_TIER_MAX_BLUE_FOR_NORMAL,
    PET_LOW_TIER_MAX_GREEN_FOR_RARE,
    PET_LOW_TIER_NORMAL,
    PET_LOW_TIER_NORMAL_CALIBRATION,
    PET_LOW_TIER_RARE,
    PET_LOW_TIER_RARE_CALIBRATION,
    PET_LOW_TIER_SLOT_REGIONS,
    PET_MASS_EVOLVE_TIER_MARGIN,
    PetCombineResultDetector,
    PetLowTierCandidateDetector,
    PetLowTierSlotReading,
    PetMassEvolveConfirmationDetector,
    PetMassEvolveConfirmationReading,
)
from .socket import (
    SOCKET_ENHANCE_ANIMATION_CALIBRATION,
    SOCKET_ENHANCE_ANIMATION_CONFIDENCE_THRESHOLD,
    SOCKET_ENHANCE_ANIMATION_MAX_CENTER_MEAN,
    SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION,
    SOCKET_INCOMPATIBLE_OPAL_ASSET,
    SOCKET_INCOMPATIBLE_OPAL_SELECTED_ASSET,
    SOCKET_INCOMPATIBLE_OPAL_VARIANT_ASSETS,
    SOCKET_INCOMPATIBLE_OPAL_CALIBRATION,
    SOCKET_INCOMPATIBLE_OPAL_CONFIDENCE_THRESHOLD,
    SOCKET_INCOMPATIBLE_OPAL_OBSERVATION,
    SOCKET_OPAL_SLOT_COUNT,
    SOCKET_OPAL_SLOT_REGIONS,
    SocketEnhanceAnimationDetector,
    SocketEnhanceAnimationReading,
    SocketIncompatibleOpalDetector,
    SocketIncompatibleOpalReading,
)
from .specs import (
    BATTLE_MODE_SELECT_HEADER_SPEC,
    BLACK_MARKET_TITLE_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    DAILY_QUESTS_ROW_CLAIM_SPEC,
    DAILY_QUESTS_TAB_ACTIVE_SPEC,
    DAILY_QUESTS_TITLE_SPEC,
    COMBINE_ALL_TITLE_SPEC,
    COMBINE_ANIMATION_TAPPABLE_SPEC,
    COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC,
    COMBINE_ETHEREAL_MASS_PROMPT_SPEC,
    COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC,
    COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC,
    COMBINE_FUSE_ACTIVE_SPEC,
    COMBINE_FUSE_TAB_SPEC,
    COMBINE_ROW_BOTTOM_INDICATOR_SPEC,
    COMBINE_ROWS_INDICATOR_SPEC,
    COMBINE_ROWS_UPPER_INDICATOR_SPEC,
    COMBINE_TRANSMUTE_ACTIVE_SPEC,
    DEFAULT_LOCAL_CV_SPECS,
    EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC,
    FRIENDS_ALL_BUTTON_SPEC,
    FRIENDS_SEND_STAMINA_DAILY_SPEC,
    FRIENDS_TITLE_SPEC,
    GUILD_ATTENDANCE_DAILY_SPEC,
    GUILD_MESSAGE_TAB_SPEC,
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    INVENTORY_FULL_OK_BUTTON_SPEC,
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC,
    MAILBOX_ROW_CLAIM_SPEC,
    MAILBOX_ROW_DELETE_SPEC,
    MAILBOX_TITLE_SPEC,
    PET_COMBINE_ACTIVE_SPEC,
    PET_COMBINE_ALL_CONFIRM_SPEC,
    PET_COMBINE_EVOLVE_PROMPT_SPEC,
    PET_COMBINE_NO_MATERIAL_SPEC,
    PET_COMBINE_RESULT_TAPPABLE_SPEC,
    PET_EPIC_INSUFFICIENT_FRAGMENTS_SPEC,
    PET_EPIC_RUNES_FULL_SPEC,
    PET_EPIC_SELECTOR_SPEC,
    PET_INVENTORY_FULL_PROMPT_SPEC,
    PET_MASS_EVOLVE_NORMAL_CONFIRM_SPEC,
    PET_MASS_EVOLVE_RARE_CONFIRM_SPEC,
    PET_MASS_EVOLVE_SELECTION_SPEC,
    PET_PREMIUM_GOLD_SELECTOR_SPEC,
    PET_PREMIUM_GOLD_SPEC,
    PET_PREMIUM_TICKET_SELECTOR_SPEC,
    PET_PREMIUM_TICKET_SPEC,
    PET_SUMMON_ACTIVE_SPEC,
    PET_SUMMON_DAILY_SPEC,
    PET_SUMMON_RESULT_BANNER_SPEC,
    PET_SUMMON_RESULT_PARCHMENT_SPEC,
    PETS_MANAGE_ACTIVE_SPEC,
    PETS_SHELL_SUMMON_PACKAGE_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
    SOCKET_ENHANCE_ALL_TITLE_SPEC,
    SOCKET_EQUIPMENT_HOME_ACTIVE_SPEC,
    SOCKET_INVENTORY_FULL_PROMPT_SPEC,
    METEOR_INVENTORY_FULL_PROMPT_SPEC,
    SOCKET_NO_MATERIAL_PROMPT_SPEC,
    SOCKET_SELL_BULK_BUTTON_SPEC,
    SOCKET_TAB_SPEC,
    WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC,
    WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC,
    WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC,
    WORLD_BOSS_SAPPHIRES_USED_SPEC,
    WORLD_BOSS_SELECT_BOSS_HEADER_SPEC,
    WORLD_BOSS_DAILY_SPEC,
    LinearGapCalibration,
    LocalCvSpec,
)


from .monster_wave import MONSTER_WAVE_SPECS
from .scope import ScopeSpec, select_detectors


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
                for spec in (*DEFAULT_LOCAL_CV_SPECS, *MONSTER_WAVE_SPECS)
            ),
            BlackMarketGoldDetector(asset_root=root),
            BlackMarketPurchasedDetector(asset_root=root),
            SocketIncompatibleOpalDetector(asset_root=root),
            SocketEnhanceAnimationDetector(),
            CombineContextDetector(asset_root=root),
            DailyQuestsProgressRewardDetector(asset_root=root),
            DailyQuestsRowsDetector(asset_root=root),
            DailyQuestsLoadingDetector(asset_root=root),
            MailboxClaimProcessingDetector(asset_root=root),
            GuildAttendanceDetector(asset_root=root),
            PetEpicAvailabilityDetector(asset_root=root),
            PetCombineResultDetector(asset_root=root),
            PetLowTierCandidateDetector(asset_root=root),
            PetMassEvolveConfirmationDetector(asset_root=root),
        )
    )


# Experimental minimal subset for ``black_market.select_slot`` only.
# These are exactly the observations its expected/abort/precondition
# predicates consume: the Black Market base landmark, the three purchase
# branch popups and the GOLD/Purchased slot facts. Every other detector is
# irrelevant to distinguishing the select_slot outcomes.
BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES = frozenset(
    {
        BLACK_MARKET_TITLE_SPEC.name,
        PURCHASE_CONFIRMATION_PROMPT_SPEC.name,
        INSUFFICIENT_GOLD_PROMPT_SPEC.name,
        INVENTORY_FULL_OK_BUTTON_SPEC.name,
    }
)


# Generic-scope declaration for ``black_market.select_slot``. Same subset
# as the legacy ``black_market_slot_perception`` builder, expressed as an
# explicit ScopeSpec (no semantic auto-derivation).
BLACK_MARKET_SLOT_SCOPE = ScopeSpec(
    name="slot",
    spec_names=BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES,
    specialized_types=(
        BlackMarketGoldDetector,
        BlackMarketPurchasedDetector,
    ),
)


# Experimental minimal subset for ``black_market.accept_purchase`` only.
# These are exactly the observations its expected/abort/precondition
# predicates consume: the Black Market base landmark, the purchase
# confirmation prompt, the GOLD/Purchased slot facts (the final snapshot
# feeds the next slot precondition, so GOLD must stay observable) and the
# two sibling popups referenced by the post-purchase abort predicate.
BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES = frozenset(
    {
        BLACK_MARKET_TITLE_SPEC.name,
        PURCHASE_CONFIRMATION_PROMPT_SPEC.name,
        INSUFFICIENT_GOLD_PROMPT_SPEC.name,
        INVENTORY_FULL_OK_BUTTON_SPEC.name,
    }
)


# Generic-scope declaration for ``black_market.accept_purchase``. Same
# subset as the legacy ``black_market_purchase_perception`` builder,
# expressed as an explicit ScopeSpec (no semantic auto-derivation).
BLACK_MARKET_PURCHASE_SCOPE = ScopeSpec(
    name="purchase",
    spec_names=BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES,
    specialized_types=(
        BlackMarketGoldDetector,
        BlackMarketPurchasedDetector,
    ),
)


# Experimental minimal subset for the Mailbox ``ClaimAll`` claim-processing
# phase only (onset + completion/fallback, Caso A: they share one coherent
# detector set and one abort predicate).
# These are exactly the observations the claim waits consume plus the
# observation the post-wait snapshot must still carry: the Mailbox base
# landmark, the Character Mail mode tab, the row-claim button (whose absence
# defines the settle condition and whose presence defines the no-effect
# branch), the row-delete button (the same final snapshot decides whether
# Delete Read runs next; omitting it would silently skip that step, same
# precedent as the Daily progress-reward indicator) and the claim-processing
# activity indicator.
MAILBOX_CLAIM_SCOPE_SPEC_NAMES = frozenset(
    {
        MAILBOX_TITLE_SPEC.name,
        MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC.name,
        MAILBOX_ROW_CLAIM_SPEC.name,
        MAILBOX_ROW_DELETE_SPEC.name,
    }
)


# Generic-scope declaration for the Mailbox ``ClaimAll`` claim-processing
# phase. Same subset as the legacy ``mailbox_claim_perception`` builder,
# expressed as an explicit ScopeSpec (no semantic auto-derivation). The
# row-delete observation stays included as snapshot carry for the Delete
# Read decision that follows claim completion.
MAILBOX_CLAIM_SCOPE = ScopeSpec(
    name="mailbox_claim",
    spec_names=MAILBOX_CLAIM_SCOPE_SPEC_NAMES,
    specialized_types=(MailboxClaimProcessingDetector,),
)

# Experimental minimal subset for the Daily Quests ``ClaimAll`` wait only.
# These are exactly the observations its expected/abort predicates consume
# plus the observation its post-wait snapshot must still carry: the Quests
# base landmark, the Daily mode tab, the row-claim button (whose absence
# defines the settle condition) and the progress-reward indicator. The
# indicator does not gate the settle predicate, but the flow reads the same
# final snapshot to decide whether the independent progress reward needs a
# second wait; omitting it would silently skip that reward.
DAILY_CLAIM_SCOPE_SPEC_NAMES = frozenset(
    {
        DAILY_QUESTS_TITLE_SPEC.name,
        DAILY_QUESTS_TAB_ACTIVE_SPEC.name,
        DAILY_QUESTS_ROW_CLAIM_SPEC.name,
    }
)


# Generic-scope declaration for the Daily Quests ``ClaimAll`` wait. Same
# subset as the legacy ``daily_claim_perception`` builder, expressed as an
# explicit ScopeSpec (no semantic auto-derivation). The progress-reward
# indicator stays included as snapshot carry for the follow-up decision.
DAILY_CLAIM_SCOPE = ScopeSpec(
    name="claim",
    spec_names=DAILY_CLAIM_SCOPE_SPEC_NAMES,
    specialized_types=(DailyQuestsProgressRewardDetector,),
)


# Minimal subset for the Daily Quests ``OpenQuests`` navigation wait only.
# These are exactly the observations its readiness expected predicate
# consumes plus the observations its post-wait snapshot must still carry:
# the Quests base landmark, the Daily mode tab, the rows-populated
# indicator (whose absence withholds readiness), the loading activity
# (whose presence withholds readiness), the row-claim button (the same
# final snapshot decides claim versus legitimate noop) and the
# progress-reward indicator (the same snapshot decides whether the
# independent progress reward needs a second wait). Same fail-fast
# guarantees as the claim scope.
DAILY_OPEN_SCOPE_SPEC_NAMES = frozenset(
    {
        DAILY_QUESTS_TITLE_SPEC.name,
        DAILY_QUESTS_TAB_ACTIVE_SPEC.name,
        DAILY_QUESTS_ROW_CLAIM_SPEC.name,
    }
)


# Generic-scope declaration for the Daily Quests ``OpenQuests`` wait,
# expressed as an explicit ScopeSpec (no semantic auto-derivation).
DAILY_OPEN_SCOPE = ScopeSpec(
    name="open",
    spec_names=DAILY_OPEN_SCOPE_SPEC_NAMES,
    specialized_types=(
        DailyQuestsProgressRewardDetector,
        DailyQuestsRowsDetector,
        DailyQuestsLoadingDetector,
    ),
)


# Minimal subset for the Guild Attendance post-tap completion wait only.
# These are exactly the observations its expected/abort predicates consume:
# the Guild base landmark, the Daily badge indicator and the
# active/completed Attendance states. Both Attendance states come from the
# single ``GuildAttendanceDetector``. The final snapshot feeds no further
# decision (the flow only asserts completion), so no extra carry is needed.
GUILD_ATTENDANCE_SCOPE_SPEC_NAMES = frozenset(
    {
        GUILD_MESSAGE_TAB_SPEC.name,
        GUILD_ATTENDANCE_DAILY_SPEC.name,
    }
)


# Generic-scope declaration for the Guild Attendance completion wait,
# expressed as an explicit ScopeSpec (no semantic auto-derivation and no
# legacy builder: this is the first scope created directly on the generic
# infrastructure).
GUILD_ATTENDANCE_SCOPE = ScopeSpec(
    name="attendance",
    spec_names=GUILD_ATTENDANCE_SCOPE_SPEC_NAMES,
    specialized_types=(GuildAttendanceDetector,),
)


# Minimal subset for the Black Market ``open`` navigation wait only
# (Lobby -> clean Black Market, Caso navigation B1).
# These are exactly the observations its expected/retryable/abort
# predicates consume plus the facts its post-wait snapshot must still
# carry: the Black Market base landmark, the Lobby base landmark (the
# retryable_from predicate requires a clean Lobby, without it a flaky
# open would lose its second attempt), the three purchase-branch popups
# referenced by the navigation abort predicate, and the GOLD/Purchased
# slot facts (without them every open would spuriously trigger the
# empty-gold confirmation wait). Same fail-fast guarantees as the slot
# and purchase scopes.
BLACK_MARKET_OPEN_SCOPE_SPEC_NAMES = frozenset(
    {
        BLACK_MARKET_TITLE_SPEC.name,
        PURCHASE_CONFIRMATION_PROMPT_SPEC.name,
        INSUFFICIENT_GOLD_PROMPT_SPEC.name,
        INVENTORY_FULL_OK_BUTTON_SPEC.name,
        LOBBY_TRADING_CENTER_LABEL_SPEC.name,
    }
)


# Generic-scope declaration for the Black Market ``open`` wait, expressed
# as an explicit ScopeSpec (no semantic auto-derivation).
BLACK_MARKET_OPEN_SCOPE = ScopeSpec(
    name="open",
    spec_names=BLACK_MARKET_OPEN_SCOPE_SPEC_NAMES,
    specialized_types=(
        BlackMarketGoldDetector,
        BlackMarketPurchasedDetector,
    ),
)


# Minimal subset for the direct Lobby -> Guild navigation wait only
# (``precondition.open_guild``, Caso navigation B1).
# These are exactly the observations its expected/retryable/abort
# predicates consume: the Guild base landmark, the Daily badge indicator
# and the active/completed Attendance states (Guild clean allows them),
# the Lobby base landmark (retryable_from requires a clean Lobby), and
# the Quick Menu tile (the destination abort explicitly excuses a Quick
# Menu frame; without the tile that frame would abort instead of waiting).
# The final snapshot feeds no further semantic decision (the caller only
# checks success), so no extra carry is needed.
GUILD_NAVIGATE_SCOPE_SPEC_NAMES = frozenset(
    {
        GUILD_MESSAGE_TAB_SPEC.name,
        GUILD_ATTENDANCE_DAILY_SPEC.name,
        LOBBY_TRADING_CENTER_LABEL_SPEC.name,
        QUICK_MENU_LOBBY_TILE_SPEC.name,
    }
)


# Generic-scope declaration for the direct Lobby -> Guild navigation wait,
# expressed as an explicit ScopeSpec (no semantic auto-derivation).
GUILD_NAVIGATE_SCOPE = ScopeSpec(
    name="navigate",
    spec_names=GUILD_NAVIGATE_SCOPE_SPEC_NAMES,
    specialized_types=(GuildAttendanceDetector,),
)


# Minimal subset for ``rotation.select_predecessor_character`` only.
# The Character Select header resolves the clean source/expected/retry state.
# The Quick Menu tile preserves the only cross-context overlay that can cover
# a base screen; every other catalog overlay is tied to a foreign screen and
# safely degrades to UNKNOWN here, which authorizes neither success nor retry.
# The target-local yellow-border reader keeps consuming the raw snapshot frame
# outside the perception engine, so it is deliberately not a global detector.
ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES = frozenset(
    {
        CHARACTER_SELECT_HEADER_SPEC.name,
        QUICK_MENU_LOBBY_TILE_SPEC.name,
    }
)


ROTATION_CHARACTER_SELECTION_SCOPE = ScopeSpec(
    name="rotation_character_selection",
    spec_names=ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES,
)


# Minimal subset for the Send Stamina post-tap completion waits only
# (completion + daily-active fallback, Caso A: both waits share one coherent
# detector set and one abort predicate).
# These are exactly the observations their expected/abort predicates consume:
# the Friends base landmarks (title + all button) and the Daily badge
# indicator whose absence defines completion and whose presence defines the
# no-effect branch. No specialized detector exists for this flow. The final
# snapshot feeds no further semantic decision (CloseFriends only needs its
# geometry and the branch flag is already known), so no extra carry is needed
# (carry: none, same precedent as Guild).
SEND_STAMINA_COMPLETION_SCOPE_SPEC_NAMES = frozenset(
    {
        FRIENDS_TITLE_SPEC.name,
        FRIENDS_ALL_BUTTON_SPEC.name,
        FRIENDS_SEND_STAMINA_DAILY_SPEC.name,
    }
)


# Generic-scope declaration for the Send Stamina completion waits,
# expressed as an explicit ScopeSpec (no semantic auto-derivation and no
# legacy builder: this is the second scope created directly on the generic
# infrastructure).
SEND_STAMINA_COMPLETION_SCOPE = ScopeSpec(
    name="completion",
    spec_names=SEND_STAMINA_COMPLETION_SCOPE_SPEC_NAMES,
    specialized_types=(),
)


def _select_scope_detectors(
    source: PerceptionEngine,
    *,
    spec_names: frozenset,
    scope_label: str,
) -> tuple:
    if not isinstance(source, PerceptionEngine):
        raise ValueError("source must be a PerceptionEngine")
    selected = tuple(
        detector
        for detector in source.detectors
        if getattr(getattr(detector, "spec", None), "name", None)
        in spec_names
        or isinstance(
            detector,
            (BlackMarketGoldDetector, BlackMarketPurchasedDetector),
        )
    )
    present = {
        detector.spec.name
        for detector in selected
        if isinstance(detector, LocalCvDetector)
    }
    missing = set(spec_names) - present
    if missing:
        raise ValueError(
            f"{scope_label} scope is missing detectors: "
            + ", ".join(sorted(missing))
        )
    if not any(isinstance(item, BlackMarketGoldDetector) for item in selected):
        raise ValueError(f"{scope_label} scope is missing the GOLD detector")
    if not any(
        isinstance(item, BlackMarketPurchasedDetector) for item in selected
    ):
        raise ValueError(
            f"{scope_label} scope is missing the Purchased detector"
        )
    return selected


def black_market_slot_perception(
    source: PerceptionEngine,
) -> PerceptionEngine:
    """Select the detectors needed for ``black_market.select_slot`` outcomes.

    The subset preserves source order and reuses the same detector
    instances, so calibration, thresholds and assets are unchanged. Only
    the detector count per frame changes. Raises ``ValueError`` when the
    source engine lacks any required detector instead of running degraded.
    """

    return PerceptionEngine(
        detectors=_select_scope_detectors(
            source,
            spec_names=BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES,
            scope_label="slot",
        )
    )


def black_market_purchase_perception(
    source: PerceptionEngine,
) -> PerceptionEngine:
    """Select the detectors needed for ``black_market.accept_purchase``.

    Same reuse and fail-fast guarantees as
    :func:`black_market_slot_perception`, scoped to the post-Yes
    verification predicates instead of the slot selection ones.
    """

    return PerceptionEngine(
        detectors=_select_scope_detectors(
            source,
            spec_names=BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES,
            scope_label="purchase",
        )
    )


def daily_claim_perception(
    source: PerceptionEngine,
) -> PerceptionEngine:
    """Select the detectors needed for the Daily Quests ``ClaimAll`` wait.

    The subset preserves source order and reuses the same detector
    instances, so calibration, thresholds and assets are unchanged. Only
    the detector count per frame changes. Raises ``ValueError`` when the
    source engine lacks any required detector instead of running degraded.

    The Black Market helper above cannot serve here: it pins the Black
    Market GOLD/Purchased specialized types, while this wait needs the
    Daily progress-reward indicator instead.
    """

    if not isinstance(source, PerceptionEngine):
        raise ValueError("source must be a PerceptionEngine")
    selected = tuple(
        detector
        for detector in source.detectors
        if getattr(getattr(detector, "spec", None), "name", None)
        in DAILY_CLAIM_SCOPE_SPEC_NAMES
        or isinstance(detector, DailyQuestsProgressRewardDetector)
    )
    present = {
        detector.spec.name
        for detector in selected
        if isinstance(detector, LocalCvDetector)
    }
    missing = set(DAILY_CLAIM_SCOPE_SPEC_NAMES) - present
    if missing:
        raise ValueError(
            "claim scope is missing detectors: "
            + ", ".join(sorted(missing))
        )
    if not any(
        isinstance(item, DailyQuestsProgressRewardDetector)
        for item in selected
    ):
        raise ValueError(
            "claim scope is missing the progress reward detector"
        )
    return PerceptionEngine(detectors=selected)


def mailbox_claim_perception(
    source: PerceptionEngine,
) -> PerceptionEngine:
    """Select the detectors needed for the Mailbox ``ClaimAll`` waits.

    Covers onset + completion/fallback as one coherent claim-processing
    phase (Caso A): all three waits share the same predicates over the
    same observations and the same abort predicate, so one subset serves
    them all. Same reuse and fail-fast guarantees as
    :func:`daily_claim_perception`, scoped to the Mailbox claim
    predicates plus the read-mail observation the post-wait snapshot
    must still carry for the Delete Read decision.
    """

    if not isinstance(source, PerceptionEngine):
        raise ValueError("source must be a PerceptionEngine")
    selected = tuple(
        detector
        for detector in source.detectors
        if getattr(getattr(detector, "spec", None), "name", None)
        in MAILBOX_CLAIM_SCOPE_SPEC_NAMES
        or isinstance(detector, MailboxClaimProcessingDetector)
    )
    present = {
        detector.spec.name
        for detector in selected
        if isinstance(detector, LocalCvDetector)
    }
    missing = set(MAILBOX_CLAIM_SCOPE_SPEC_NAMES) - present
    if missing:
        raise ValueError(
            "mailbox claim scope is missing detectors: "
            + ", ".join(sorted(missing))
        )
    if not any(
        isinstance(item, MailboxClaimProcessingDetector)
        for item in selected
    ):
        raise ValueError(
            "mailbox claim scope is missing the claim processing detector"
        )
    return PerceptionEngine(detectors=selected)


__all__ = (
    "BLACK_MARKET_GOLD_ASSET",
    "BLACK_MARKET_GOLD_CALIBRATION",
    "BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD",
    "BLACK_MARKET_GOLD_OBSERVATION",
    "BLACK_MARKET_GOLD_SLOT_REGIONS",
    "BLACK_MARKET_GRID_COLUMNS",
    "BLACK_MARKET_GRID_ROWS",
    "BLACK_MARKET_SLOT_COUNT",
    "BLACK_MARKET_SLOT_SCOPE",
    "BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES",
    "BLACK_MARKET_PURCHASE_SCOPE",
    "BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES",
    "BLACK_MARKET_OPEN_SCOPE",
    "BLACK_MARKET_OPEN_SCOPE_SPEC_NAMES",
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
    "DAILY_QUESTS_ROW_CLAIM_SPEC",
    "DAILY_QUESTS_TAB_ACTIVE_SPEC",
    "DAILY_QUESTS_TITLE_SPEC",
    "COMBINE_ALL_TITLE_SPEC",
    "COMBINE_ANIMATION_TAPPABLE_SPEC",
    "COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC",
    "COMBINE_ETHEREAL_MASS_PROMPT_SPEC",
    "COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC",
    "COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC",
    "COMBINE_FUSE_ACTIVE_SPEC",
    "COMBINE_FUSE_TAB_SPEC",
    "COMBINE_ROW_BOTTOM_INDICATOR_SPEC",
    "COMBINE_ROWS_INDICATOR_SPEC",
    "COMBINE_ROWS_UPPER_INDICATOR_SPEC",
    "COMBINE_TRANSMUTE_ACTIVE_SPEC",
    "CombineContextDetector",
    "DAILY_CLAIM_SCOPE",
    "DAILY_CLAIM_SCOPE_SPEC_NAMES",
    "DAILY_OPEN_SCOPE",
    "DAILY_OPEN_SCOPE_SPEC_NAMES",
    "DAILY_QUESTS_LOADING_CALIBRATION",
    "DAILY_QUESTS_LOADING_CONFIDENCE_THRESHOLD",
    "DAILY_QUESTS_LOADING_HSV_LOWER",
    "DAILY_QUESTS_LOADING_HSV_UPPER",
    "DAILY_QUESTS_LOADING_REGION",
    "DAILY_QUESTS_PROGRESS_REWARD_CALIBRATION",
    "DAILY_QUESTS_PROGRESS_REWARD_CONFIDENCE_THRESHOLD",
    "DAILY_QUESTS_PROGRESS_REWARD_HSV_LOWER",
    "DAILY_QUESTS_PROGRESS_REWARD_HSV_UPPER",
    "DAILY_QUESTS_PROGRESS_REWARD_REGION",
    "DAILY_QUESTS_ROWS_BRIGHT_VALUE",
    "DAILY_QUESTS_ROWS_CALIBRATION",
    "DAILY_QUESTS_ROWS_CONFIDENCE_THRESHOLD",
    "DAILY_QUESTS_ROWS_REGION",
    "DailyQuestsLoadingDetector",
    "DailyQuestsLoadingReading",
    "DailyQuestsProgressRewardDetector",
    "DailyQuestsProgressRewardReading",
    "DailyQuestsRowsDetector",
    "DailyQuestsRowsReading",
    "DEFAULT_LOCAL_CV_SPECS",
    "EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC",
    "FRIENDS_ALL_BUTTON_SPEC",
    "FRIENDS_SEND_STAMINA_DAILY_SPEC",
    "FRIENDS_TITLE_SPEC",
    "GUILD_ATTENDANCE_ACTIVE_CALIBRATION",
    "GUILD_ATTENDANCE_COMPLETED_CALIBRATION",
    "GUILD_ATTENDANCE_CONFIDENCE_THRESHOLD",
    "GUILD_ATTENDANCE_REGION",
    "GUILD_ATTENDANCE_SCOPE",
    "GUILD_ATTENDANCE_SCOPE_SPEC_NAMES",
    "GUILD_NAVIGATE_SCOPE",
    "GUILD_NAVIGATE_SCOPE_SPEC_NAMES",
    "GUILD_MESSAGE_TAB_SPEC",
    "GUILD_ATTENDANCE_DAILY_SPEC",
    "GuildAttendanceDetector",
    "GuildAttendanceReading",
    "INSUFFICIENT_GOLD_PROMPT_SPEC",
    "INVENTORY_FULL_OK_BUTTON_SPEC",
    "PET_COMBINE_ACTIVE_SPEC",
    "PET_COMBINE_ALL_CONFIRM_SPEC",
    "PET_COMBINE_EVOLVE_PROMPT_SPEC",
    "PET_COMBINE_NO_MATERIAL_SPEC",
    "PET_COMBINE_RESULT_TAPPABLE_SPEC",
    "PET_EPIC_AVAILABILITY_CONFIDENCE_THRESHOLD",
    "PET_EPIC_AVAILABILITY_REGION",
    "PET_EPIC_AVAILABLE_CALIBRATION",
    "PET_EPIC_INSUFFICIENT_FRAGMENTS_SPEC",
    "PET_EPIC_RUNES_FULL_SPEC",
    "PET_EPIC_SELECTOR_SPEC",
    "PET_EPIC_UNAVAILABLE_CALIBRATION",
    "PET_INVENTORY_FULL_PROMPT_SPEC",
    "PET_LOW_TIER_MAX_BLUE_FOR_NORMAL",
    "PET_LOW_TIER_MAX_GREEN_FOR_RARE",
    "PET_LOW_TIER_NORMAL",
    "PET_LOW_TIER_NORMAL_CALIBRATION",
    "PET_LOW_TIER_RARE",
    "PET_LOW_TIER_RARE_CALIBRATION",
    "PET_LOW_TIER_SLOT_REGIONS",
    "PET_MASS_EVOLVE_NORMAL_CONFIRM_SPEC",
    "PET_MASS_EVOLVE_RARE_CONFIRM_SPEC",
    "PET_MASS_EVOLVE_SELECTION_SPEC",
    "PET_MASS_EVOLVE_TIER_MARGIN",
    "PET_PREMIUM_GOLD_SELECTOR_SPEC",
    "PET_PREMIUM_GOLD_SPEC",
    "PET_PREMIUM_TICKET_SELECTOR_SPEC",
    "PET_PREMIUM_TICKET_SPEC",
    "PET_SUMMON_ACTIVE_SPEC",
    "PET_SUMMON_DAILY_SPEC",
    "PET_SUMMON_RESULT_BANNER_SPEC",
    "PET_SUMMON_RESULT_PARCHMENT_SPEC",
    "PETS_MANAGE_ACTIVE_SPEC",
    "PETS_SHELL_SUMMON_PACKAGE_SPEC",
    "PetEpicAvailabilityDetector",
    "PetEpicAvailabilityReading",
    "PetCombineResultDetector",
    "PetLowTierCandidateDetector",
    "PetLowTierSlotReading",
    "PetMassEvolveConfirmationDetector",
    "PetMassEvolveConfirmationReading",
    "PURCHASE_CONFIRMATION_PROMPT_SPEC",
    "QUICK_MENU_LOBBY_TILE_SPEC",
    "ROTATION_CHARACTER_SELECTION_SCOPE",
    "ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES",
    "SOCKET_ENHANCE_ALL_TITLE_SPEC",
    "SOCKET_ENHANCE_ANIMATION_CALIBRATION",
    "SOCKET_ENHANCE_ANIMATION_CONFIDENCE_THRESHOLD",
    "SOCKET_ENHANCE_ANIMATION_MAX_CENTER_MEAN",
    "SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION",
    "SOCKET_EQUIPMENT_HOME_ACTIVE_SPEC",
    "SOCKET_INCOMPATIBLE_OPAL_ASSET",
    "SOCKET_INCOMPATIBLE_OPAL_SELECTED_ASSET",
    "SOCKET_INCOMPATIBLE_OPAL_VARIANT_ASSETS",
    "SOCKET_INCOMPATIBLE_OPAL_CALIBRATION",
    "SOCKET_INCOMPATIBLE_OPAL_CONFIDENCE_THRESHOLD",
    "SOCKET_INCOMPATIBLE_OPAL_OBSERVATION",
    "SOCKET_INVENTORY_FULL_PROMPT_SPEC",
    "METEOR_INVENTORY_FULL_PROMPT_SPEC",
    "SOCKET_NO_MATERIAL_PROMPT_SPEC",
    "SOCKET_OPAL_SLOT_COUNT",
    "SOCKET_OPAL_SLOT_REGIONS",
    "SOCKET_SELL_BULK_BUTTON_SPEC",
    "SOCKET_TAB_SPEC",
    "SEND_STAMINA_COMPLETION_SCOPE",
    "SEND_STAMINA_COMPLETION_SCOPE_SPEC_NAMES",
    "SocketEnhanceAnimationDetector",
    "SocketEnhanceAnimationReading",
    "SocketIncompatibleOpalDetector",
    "SocketIncompatibleOpalReading",
    "select_detectors",
    "WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC",
    "WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC",
    "WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC",
    "WORLD_BOSS_SAPPHIRES_USED_SPEC",
    "WORLD_BOSS_SELECT_BOSS_HEADER_SPEC",
    "WORLD_BOSS_DAILY_SPEC",
    "LinearGapCalibration",
    "LOBBY_TRADING_CENTER_LABEL_SPEC",
    "MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC",
    "MAILBOX_CLAIM_SCOPE",
    "MAILBOX_CLAIM_SCOPE_SPEC_NAMES",
    "MAILBOX_CLAIM_PROCESSING_CALIBRATION",
    "MAILBOX_CLAIM_PROCESSING_CONFIDENCE_THRESHOLD",
    "MAILBOX_CLAIM_PROCESSING_HSV_LOWER",
    "MAILBOX_CLAIM_PROCESSING_HSV_UPPER",
    "MAILBOX_CLAIM_PROCESSING_REGION",
    "MAILBOX_ROW_CLAIM_SPEC",
    "MAILBOX_ROW_DELETE_SPEC",
    "MAILBOX_TITLE_SPEC",
    "MailboxClaimProcessingDetector",
    "MailboxClaimProcessingReading",
    "ScopeSpec",
    "LocalCvDetection",
    "LocalCvDetector",
    "LocalCvSpec",
    "PerceptionDetector",
    "PerceptionEngine",
    "black_market_purchase_perception",
    "black_market_slot_perception",
    "build_default_perception",
    "daily_claim_perception",
    "mailbox_claim_perception",
)
