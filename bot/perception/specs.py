"""Immutable configuration for the currently approved local CV detectors."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

from bot.catalog import (
    LANDMARK_DAILY_QUESTS_ROW_CLAIM_BUTTON,
    LANDMARK_DAILY_QUESTS_TAB_ACTIVE,
    LANDMARK_DAILY_QUESTS_TITLE,
    LANDMARK_FRIENDS_ALL_BUTTON,
    LANDMARK_FRIENDS_TITLE,
    LANDMARK_GUILD_MESSAGE_TAB,
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    INDICATOR_COMBINE_ROW_BOTTOM,
    INDICATOR_COMBINE_ROWS,
    INDICATOR_COMBINE_ROWS_UPPER,
    INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE,
    INDICATOR_PET_PREMIUM_GOLD,
    INDICATOR_PET_PREMIUM_TICKET,
    INDICATOR_PET_SUMMON_DAILY_ACTIVE,
    INDICATOR_WORLD_BOSS_DAILY_ACTIVE,
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE,
    LANDMARK_MAILBOX_ROW_CLAIM_BUTTON,
    LANDMARK_MAILBOX_ROW_DELETE_BUTTON,
    LANDMARK_MAILBOX_TITLE,
    LANDMARK_PETS_MANAGE_ACTIVE,
    LANDMARK_PETS_SHELL_SUMMON_PACKAGE,
    LANDMARK_PET_COMBINE_ACTIVE,
    LANDMARK_PET_COMBINE_EVOLVE_PROMPT,
    LANDMARK_PET_EPIC_INSUFFICIENT_FRAGMENTS,
    LANDMARK_PET_EPIC_SELECTOR,
    LANDMARK_PET_INVENTORY_FULL_PROMPT,
    LANDMARK_PET_PREMIUM_GOLD_SELECTOR,
    LANDMARK_PET_PREMIUM_TICKET_SELECTOR,
    LANDMARK_PET_SUMMON_ACTIVE,
    LANDMARK_PET_SUMMON_RESULT_BANNER,
    LANDMARK_PET_SUMMON_RESULT_PARCHMENT,
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
    LANDMARK_COMBINE_FUSE_TAB,
    LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
    LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT,
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


# The current full title frame replaces the text-only crop after the Socket
# Enhance success screen exposed a false Black Market base resolution. Its
# swords and panel separate all 18 historical/current positives from the
# expanded cross-context corpus, including the dark animation stages.
BLACK_MARKET_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_BLACK_MARKET_TITLE,
    asset_path=Path(
        "assets/ui/landmarks/black-market-title-frame-current.png"
    ),
    region=(0.37, 0.04, 0.62, 0.18),
    calibration=LinearGapCalibration(
        negative_anchor=0.566973090171814,
        positive_anchor=0.6773226857185364,
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
        # Premium summon result banners are the closest confirmed negative.
        negative_anchor=0.410758376121521,
        positive_anchor=0.43373382091522217,
    ),
)

# Current Quest panel title. The popup renders above Lobby/chat, and the title
# remains unchanged across claimable, settled, progress-reward and no-op
# evidence. Calibration includes the expanded cross-context corpus.
DAILY_QUESTS_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_DAILY_QUESTS_TITLE,
    asset_path=Path("assets/ui/landmarks/daily-quests-title-current.png"),
    region=(0.43, 0.04, 0.57, 0.17),
    calibration=LinearGapCalibration(
        negative_anchor=0.5704289078712463,
        positive_anchor=0.9863162040710449,
    ),
)

# The orange selected Daily Quests tab excludes the transient N badge. It is
# present in all acquired stable Daily states, including Claim All no-op.
DAILY_QUESTS_TAB_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_DAILY_QUESTS_TAB_ACTIVE,
    asset_path=Path(
        "assets/ui/landmarks/daily-quests-tab-active-current.png"
    ),
    region=(0.17, 0.15, 0.34, 0.31),
    calibration=LinearGapCalibration(
        negative_anchor=0.3563847839832306,
        positive_anchor=0.9862149953842163,
    ),
)

# Position-specific turquoise Claim action from Daily Quest rows only. The
# search region deliberately starts below the independent progress reward, so
# its active and disabled Claim renderings are confirmed negatives.
DAILY_QUESTS_ROW_CLAIM_SPEC = LocalCvSpec(
    name=LANDMARK_DAILY_QUESTS_ROW_CLAIM_BUTTON,
    asset_path=Path(
        "assets/ui/landmarks/daily-quests-row-claim-current.png"
    ),
    region=(0.66, 0.34, 0.78, 0.75),
    calibration=LinearGapCalibration(
        negative_anchor=0.7896780371665955,
        positive_anchor=0.9804643988609314,
    ),
)

# Full current Friends title frame. The popup renders above Lobby and the
# dynamic chat layer, so this upper landmark remains observable without using
# the transient processing bubble after All. These specs use a 1e-7 numerical
# guard above the measured maximum negative so an anchor-equal score emits no
# floating-point residue as presence evidence.
FRIENDS_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_FRIENDS_TITLE,
    asset_path=Path("assets/ui/landmarks/friends-title-current.png"),
    region=(0.38, 0.02, 0.62, 0.16),
    calibration=LinearGapCalibration(
        negative_anchor=0.7385951,
        positive_anchor=0.989769101142883,
    ),
)

# The button crop excludes the Daily badge at its upper-left edge. It remains
# identical before and after the business action and is therefore structural,
# not completion evidence.
FRIENDS_ALL_BUTTON_SPEC = LocalCvSpec(
    name=LANDMARK_FRIENDS_ALL_BUTTON,
    asset_path=Path("assets/ui/landmarks/friends-all-button-current.png"),
    region=(0.72, 0.80, 0.84, 0.96),
    calibration=LinearGapCalibration(
        negative_anchor=0.7735992,
        positive_anchor=0.970031499862671,
    ),
)

# Friends, Guild and Battle Mode Select use the same Daily mission icon.
# Separate position-specific specs prevent an unrelated activity badge from
# becoming business eligibility for another context.
FRIENDS_SEND_STAMINA_DAILY_SPEC = LocalCvSpec(
    name=INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    asset_path=Path("assets/ui/indicators/daily-mission-badge-current.png"),
    region=(0.695, 0.81, 0.745, 0.905),
    calibration=LinearGapCalibration(
        negative_anchor=0.6545846,
        positive_anchor=0.984439730644226,
    ),
)

GUILD_ATTENDANCE_DAILY_SPEC = LocalCvSpec(
    name=INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE,
    asset_path=Path("assets/ui/indicators/daily-mission-badge-current.png"),
    region=(0.38, 0.34, 0.425, 0.435),
    calibration=LinearGapCalibration(
        negative_anchor=0.6131251,
        positive_anchor=0.922698438167572,
    ),
)

# Stable Guild Message tab on the joined-guild shell. It sits well below the
# transient check-in bubble and outside the upper dynamic chat band. The
# current corpus contains 16 Guild positives (including Quick Menu over Guild)
# and 307 cross-context negatives with a 0.613817 raw separation gap.
GUILD_MESSAGE_TAB_SPEC = LocalCvSpec(
    name=LANDMARK_GUILD_MESSAGE_TAB,
    asset_path=Path("assets/ui/landmarks/guild-message-tab-current.png"),
    region=(0.47, 0.53, 0.64, 0.69),
    calibration=LinearGapCalibration(
        negative_anchor=0.345723956823349,
        positive_anchor=0.9595406651496887,
    ),
)

# Current Mailbox title, stable across Account/Character tabs, Claim All
# processing bubbles, read mail and residual unclaimable rewards.
MAILBOX_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_MAILBOX_TITLE,
    asset_path=Path("assets/ui/landmarks/mailbox-title-current.png"),
    region=(0.43, 0.09, 0.58, 0.23),
    calibration=LinearGapCalibration(
        negative_anchor=0.6245492696762085,
        positive_anchor=0.9794498682022095,
    ),
)

# Orange selected Character Mail tab. Transient reward bubbles can occlude it;
# those frames intentionally keep only screen.mailbox plus raw processing
# activity instead of pretending the mode remains observable.
MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_MAILBOX_CHARACTER_MAIL_ACTIVE,
    asset_path=Path(
        "assets/ui/landmarks/mailbox-character-mail-active-current.png"
    ),
    region=(0.28, 0.15, 0.48, 0.34),
    calibration=LinearGapCalibration(
        negative_anchor=0.5357502698898315,
        positive_anchor=0.9879775047302246,
    ),
)

# Red per-row Claim is global visual evidence inside Mailbox; catalog policy
# combines it with Character Mail active before deriving a productive status.
MAILBOX_ROW_CLAIM_SPEC = LocalCvSpec(
    name=LANDMARK_MAILBOX_ROW_CLAIM_BUTTON,
    asset_path=Path("assets/ui/landmarks/mailbox-row-claim-current.png"),
    region=(0.68, 0.30, 0.81, 0.75),
    calibration=LinearGapCalibration(
        negative_anchor=0.7149763703346252,
        positive_anchor=0.9837077856063843,
    ),
)

# Turquoise per-row Delete identifies mail that was read/claimed. Its weakest
# confirmed positive is a deliberately retained dim processing frame; the gap
# remains separated from Account Mail Claim buttons and other contexts.
MAILBOX_ROW_DELETE_SPEC = LocalCvSpec(
    name=LANDMARK_MAILBOX_ROW_DELETE_BUTTON,
    asset_path=Path("assets/ui/landmarks/mailbox-row-delete-current.png"),
    region=(0.68, 0.30, 0.81, 0.75),
    calibration=LinearGapCalibration(
        negative_anchor=0.7161568403244019,
        positive_anchor=0.7981032729148865,
    ),
)

# The fixed World Boss entry title identifies the Survival selector without
# using its upper header, which the dynamic game chat can occlude. Current and
# historical native renderings cover 17 confirmed positives and remain
# separated from the expanded 154-frame cross-context negative corpus.
BATTLE_MODE_SELECT_HEADER_SPEC = LocalCvSpec(
    name=LANDMARK_BATTLE_MODE_SELECT_HEADER,
    asset_path=Path(
        "assets/ui/landmarks/battle-mode-world-boss-current.png"
    ),
    variant_asset_paths=(
        Path("assets/ui/landmarks/battle-mode-world-boss-historical.png"),
    ),
    region=(0.16, 0.58, 0.32, 0.68),
    calibration=LinearGapCalibration(
        negative_anchor=0.39035069942474365,
        positive_anchor=0.9919484853744507,
    ),
)

WORLD_BOSS_DAILY_SPEC = LocalCvSpec(
    name=INDICATOR_WORLD_BOSS_DAILY_ACTIVE,
    asset_path=Path("assets/ui/indicators/daily-mission-badge-current.png"),
    region=(0.15, 0.54, 0.20, 0.64),
    calibration=LinearGapCalibration(
        negative_anchor=0.6143493,
        positive_anchor=0.972343325614929,
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

# Human-confirmed Socket-cap guard reached from World Boss. The literal and
# semantic namespace are global to the Socket inventory; the underlying caller
# remains independently resolved as screen.world_boss.
SOCKET_INVENTORY_FULL_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_SOCKET_INVENTORY_FULL_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/socket-inventory-full-prompt-current.png"
    ),
    region=(0.31, 0.38, 0.69, 0.54),
    calibration=LinearGapCalibration(
        negative_anchor=0.5793697237968445,
        positive_anchor=0.9941959977149963,
    ),
)

# Persistent left-side Socket tab, outside the human-confirmed dynamic chat
# overlay zone over the upper-right heading. Variants cover selected/unselected
# and normal/dimmed renderings across Socket, Equipment Home and modal states.
SOCKET_TAB_SPEC = LocalCvSpec(
    name=LANDMARK_SOCKET_TAB,
    asset_path=Path("assets/ui/landmarks/socket-tab-selected-current.png"),
    variant_asset_paths=(
        Path("assets/ui/landmarks/socket-tab-selected-dimmed-current.png"),
        Path("assets/ui/landmarks/socket-tab-equipment-current.png"),
        Path("assets/ui/landmarks/socket-tab-equipment-dimmed-current.png"),
        Path("assets/ui/landmarks/socket-tab-enhance-dimmed-current.png"),
    ),
    region=(0.16, 0.11, 0.26, 0.24),
    calibration=LinearGapCalibration(
        negative_anchor=0.7131282687187195,
        positive_anchor=0.9773702621459961,
    ),
)

# Literal modal title; cost and both payment buttons are deliberately excluded.
# Future policy may target GOLD only, but this observation never authorizes a
# payment action and cannot distinguish buttons by coordinate.
SOCKET_ENHANCE_ALL_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_SOCKET_ENHANCE_ALL_TITLE,
    asset_path=Path(
        "assets/ui/landmarks/socket-enhance-all-title-current.png"
    ),
    region=(0.40, 0.12, 0.60, 0.25),
    calibration=LinearGapCalibration(
        negative_anchor=0.5010461211204529,
        positive_anchor=0.9996619820594788,
    ),
)

# Stable message used as the unambiguous Enhance All NO_EFFECT signal.
SOCKET_NO_MATERIAL_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_SOCKET_NO_MATERIAL_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/socket-no-material-prompt-current.png"
    ),
    region=(0.38, 0.35, 0.62, 0.55),
    calibration=LinearGapCalibration(
        negative_anchor=0.5095562934875488,
        positive_anchor=0.999983012676239,
    ),
)

# Sell (Bulk) is a stable structural landmark for the destructive confirmation
# modal. It does not authorize sale; level==0 must be a separate confirmed fact.
SOCKET_SELL_BULK_BUTTON_SPEC = LocalCvSpec(
    name=LANDMARK_SOCKET_SELL_BULK_BUTTON,
    asset_path=Path(
        "assets/ui/landmarks/socket-sell-bulk-button-current.png"
    ),
    region=(0.32, 0.53, 0.48, 0.72),
    calibration=LinearGapCalibration(
        negative_anchor=0.462656170129776,
        positive_anchor=0.9993649125099182,
    ),
)

# Active Equipment Home tab gates the visible incompatible-opal grid. It is an
# observation rather than a separate base context because Socket remains the
# containing screen.
SOCKET_EQUIPMENT_HOME_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    asset_path=Path(
        "assets/ui/landmarks/socket-equipment-home-active-current.png"
    ),
    region=(0.23, 0.12, 0.38, 0.24),
    calibration=LinearGapCalibration(
        negative_anchor=0.4660988748073578,
        positive_anchor=0.9939724802970886,
    ),
)

# Global Equipment Full prompt, first acquired from World Boss and later
# reconfirmed while promoting its Combine branch. The caller remains a separate
# base observation; popup semantics do not imply navigation or cleanup policy.
EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/world-boss-bag-full-prompt-current.png"
    ),
    variant_asset_paths=(
        Path(
            "assets/ui/landmarks/equipment-inventory-full-prompt-current.png"
        ),
    ),
    region=(0.28, 0.32, 0.72, 0.62),
    calibration=LinearGapCalibration(
        negative_anchor=0.3778718113899231,
        positive_anchor=0.9870349764823914,
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

# The left Fuse tab persists throughout the acquired Combine states and sits
# left of the observed dynamic chat band. Variants cover selected/unselected
# plus both dimmed confirmation-modal renderings.
COMBINE_FUSE_TAB_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_FUSE_TAB,
    asset_path=Path("assets/ui/landmarks/combine-fuse-tab-selected-current.png"),
    variant_asset_paths=(
        Path("assets/ui/landmarks/combine-fuse-tab-unselected-current.png"),
        Path("assets/ui/landmarks/combine-fuse-tab-selected-dimmed-current.png"),
        Path("assets/ui/landmarks/combine-fuse-tab-unselected-dimmed-current.png"),
    ),
    region=(0.16, 0.13, 0.29, 0.25),
    calibration=LinearGapCalibration(
        negative_anchor=0.7059454321861267,
        positive_anchor=0.9540939927101135,
    ),
)

COMBINE_FUSE_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_FUSE_ACTIVE,
    asset_path=Path("assets/ui/landmarks/combine-fuse-tab-selected-current.png"),
    variant_asset_paths=(
        Path("assets/ui/landmarks/combine-fuse-tab-selected-dimmed-current.png"),
    ),
    region=(0.16, 0.13, 0.29, 0.25),
    calibration=LinearGapCalibration(
        negative_anchor=0.6654080152511597,
        positive_anchor=0.956794261932373,
    ),
)

COMBINE_TRANSMUTE_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
    asset_path=Path("assets/ui/landmarks/combine-transmute-active-current.png"),
    variant_asset_paths=(
        Path("assets/ui/landmarks/combine-transmute-active-dimmed-current.png"),
    ),
    region=(0.23, 0.13, 0.38, 0.25),
    calibration=LinearGapCalibration(
        negative_anchor=0.5096800327301025,
        positive_anchor=0.9519771337509155,
    ),
)

# One literal N rendering is searched in three deliberately different strips.
# Resolver conjunction with the active tab assigns Transmute/Fuse meaning;
# the bottom strip is the independent Ethereal guard/postcondition.
COMBINE_ROWS_INDICATOR_SPEC = LocalCvSpec(
    name=INDICATOR_COMBINE_ROWS,
    asset_path=Path("assets/ui/landmarks/combine-new-indicator-current.png"),
    region=(0.19, 0.55, 0.24, 0.96),
    calibration=LinearGapCalibration(
        negative_anchor=0.49021828174591064,
        positive_anchor=0.9251843690872192,
    ),
)

COMBINE_ROWS_UPPER_INDICATOR_SPEC = LocalCvSpec(
    name=INDICATOR_COMBINE_ROWS_UPPER,
    asset_path=Path("assets/ui/landmarks/combine-new-indicator-current.png"),
    region=(0.19, 0.55, 0.24, 0.84),
    calibration=LinearGapCalibration(
        negative_anchor=0.47429946064949036,
        positive_anchor=0.917724609375,
    ),
)

COMBINE_ROW_BOTTOM_INDICATOR_SPEC = LocalCvSpec(
    name=INDICATOR_COMBINE_ROW_BOTTOM,
    asset_path=Path("assets/ui/landmarks/combine-new-indicator-current.png"),
    region=(0.19, 0.84, 0.24, 0.96),
    calibration=LinearGapCalibration(
        negative_anchor=0.4776187241077423,
        positive_anchor=0.9251841902732849,
    ),
)

COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE,
    asset_path=Path(
        "assets/ui/landmarks/combine-awakened-transmute-title-current.png"
    ),
    region=(0.25, 0.20, 0.45, 0.34),
    calibration=LinearGapCalibration(
        negative_anchor=0.8416112065315247,
        positive_anchor=0.9864535927772522,
    ),
)

COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE,
    asset_path=Path(
        "assets/ui/landmarks/combine-ethereal-random-part-title-current.png"
    ),
    region=(0.25, 0.20, 0.45, 0.34),
    calibration=LinearGapCalibration(
        negative_anchor=0.7984787821769714,
        positive_anchor=0.8355317711830139,
    ),
)

COMBINE_ALL_TITLE_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_ALL_TITLE,
    asset_path=Path(
        "assets/ui/landmarks/combine-all-identical-title-current.png"
    ),
    variant_asset_paths=(
        Path("assets/ui/landmarks/combine-all-higher-title-current.png"),
    ),
    region=(0.34, 0.18, 0.66, 0.32),
    calibration=LinearGapCalibration(
        negative_anchor=0.46529796719551086,
        positive_anchor=0.9927960634231567,
    ),
)

COMBINE_ETHEREAL_MASS_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/combine-ethereal-mass-confirm-prompt-current.png"
    ),
    region=(0.35, 0.35, 0.65, 0.58),
    calibration=LinearGapCalibration(
        negative_anchor=0.4805524945259094,
        positive_anchor=0.9861894249916077,
    ),
)

COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/combine-ethereal-no-material-prompt-current.png"
    ),
    region=(0.32, 0.35, 0.68, 0.58),
    calibration=LinearGapCalibration(
        negative_anchor=0.5516853928565979,
        positive_anchor=0.9879307746887207,
    ),
)

# Transmute, Ethereal Mass Combine and Fuse share one acquired tappable emblem.
# Variants describe operation backgrounds, not separate gameplay semantics.
COMBINE_ANIMATION_TAPPABLE_SPEC = LocalCvSpec(
    name=ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    asset_path=Path(
        "assets/ui/landmarks/combine-animation-transmute-current.png"
    ),
    variant_asset_paths=(
        Path("assets/ui/landmarks/combine-animation-ethereal-current.png"),
        Path("assets/ui/landmarks/combine-animation-fuse-current.png"),
    ),
    region=(0.40, 0.55, 0.60, 0.94),
    calibration=LinearGapCalibration(
        negative_anchor=0.7061792016029358,
        positive_anchor=0.9999794363975525,
    ),
)

# Pets uses a shared top-shell control rather than the centered ``Pets`` title,
# which live chat messages can occlude.  Active tabs then identify the exact
# destination without relying on pet identity, inventory count or character.
PETS_SHELL_SUMMON_PACKAGE_SPEC = LocalCvSpec(
    name=LANDMARK_PETS_SHELL_SUMMON_PACKAGE,
    asset_path=Path(
        "assets/ui/landmarks/pet-shell-summon-package-current.png"
    ),
    region=(0.55, 0.01, 0.76, 0.12),
    calibration=LinearGapCalibration(
        negative_anchor=0.5397682785987854,
        positive_anchor=0.9736979603767395,
    ),
)

PETS_MANAGE_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_PETS_MANAGE_ACTIVE,
    asset_path=Path("assets/ui/landmarks/pets-manage-active-current.png"),
    region=(0.23, 0.12, 0.35, 0.24),
    calibration=LinearGapCalibration(
        negative_anchor=0.4655766785144806,
        positive_anchor=0.9806886911392212,
    ),
)

PET_SUMMON_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_PET_SUMMON_ACTIVE,
    asset_path=Path("assets/ui/landmarks/pet-summon-active-current.png"),
    region=(0.15, 0.12, 0.27, 0.24),
    calibration=LinearGapCalibration(
        negative_anchor=0.5615880489349365,
        positive_anchor=0.838320791721344,
    ),
)

PET_COMBINE_ACTIVE_SPEC = LocalCvSpec(
    name=LANDMARK_PET_COMBINE_ACTIVE,
    asset_path=Path("assets/ui/landmarks/pet-combine-active-current.png"),
    region=(0.30, 0.12, 0.43, 0.24),
    calibration=LinearGapCalibration(
        negative_anchor=0.3940369188785553,
        positive_anchor=0.9823662638664246,
    ),
)

PET_COMBINE_EVOLVE_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_PET_COMBINE_EVOLVE_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/pet-combine-evolve-prompt-current.png"
    ),
    region=(0.20, 0.20, 0.46, 0.34),
    calibration=LinearGapCalibration(
        negative_anchor=0.49720194935798645,
        positive_anchor=0.9909647107124329,
    ),
)

# The green Daily badge is the same current-season rendering already shared
# by Friends, Guild and World Boss.  Its Pets ROI is left of the chat overlay
# and remains visible from both Manage and Summon.
PET_SUMMON_DAILY_SPEC = LocalCvSpec(
    name=INDICATOR_PET_SUMMON_DAILY_ACTIVE,
    asset_path=Path("assets/ui/indicators/daily-mission-badge-current.png"),
    region=(0.15, 0.08, 0.21, 0.20),
    calibration=LinearGapCalibration(
        negative_anchor=0.6557286381721497,
        positive_anchor=0.97370445728302,
    ),
)

PET_PREMIUM_TICKET_SPEC = LocalCvSpec(
    name=INDICATOR_PET_PREMIUM_TICKET,
    asset_path=Path("assets/ui/landmarks/pet-premium-ticket-current.png"),
    region=(0.32, 0.78, 0.42, 0.95),
    calibration=LinearGapCalibration(
        negative_anchor=0.47573623061180115,
        positive_anchor=0.9745630621910095,
    ),
)

PET_PREMIUM_GOLD_SPEC = LocalCvSpec(
    name=INDICATOR_PET_PREMIUM_GOLD,
    asset_path=Path("assets/ui/landmarks/pet-premium-gold-current.png"),
    region=(0.32, 0.78, 0.42, 0.95),
    calibration=LinearGapCalibration(
        negative_anchor=0.6196065545082092,
        positive_anchor=0.9882810115814209,
    ),
)

PET_EPIC_SELECTOR_SPEC = LocalCvSpec(
    name=LANDMARK_PET_EPIC_SELECTOR,
    asset_path=Path("assets/ui/landmarks/pet-epic-selector-current.png"),
    region=(0.48, 0.52, 0.72, 0.84),
    calibration=LinearGapCalibration(
        negative_anchor=0.7997300624847412,
        positive_anchor=0.9999725818634033,
    ),
)

PET_PREMIUM_TICKET_SELECTOR_SPEC = LocalCvSpec(
    name=LANDMARK_PET_PREMIUM_TICKET_SELECTOR,
    asset_path=Path(
        "assets/ui/landmarks/pet-premium-ticket-selector-current.png"
    ),
    region=(0.30, 0.52, 0.56, 0.84),
    calibration=LinearGapCalibration(
        negative_anchor=0.8574437499046326,
        positive_anchor=0.9999744892120361,
    ),
)

PET_PREMIUM_GOLD_SELECTOR_SPEC = LocalCvSpec(
    name=LANDMARK_PET_PREMIUM_GOLD_SELECTOR,
    asset_path=Path(
        "assets/ui/landmarks/pet-premium-gold-selector-current.png"
    ),
    region=(0.48, 0.52, 0.70, 0.84),
    calibration=LinearGapCalibration(
        negative_anchor=0.8085889220237732,
        positive_anchor=0.9958579540252686,
    ),
)

PET_EPIC_INSUFFICIENT_FRAGMENTS_SPEC = LocalCvSpec(
    name=LANDMARK_PET_EPIC_INSUFFICIENT_FRAGMENTS,
    asset_path=Path(
        "assets/ui/landmarks/pet-epic-insufficient-fragments-current.png"
    ),
    region=(0.30, 0.53, 0.70, 0.82),
    calibration=LinearGapCalibration(
        negative_anchor=0.2740575671195984,
        positive_anchor=0.9999713897705078,
    ),
)

# Result identity, rarity and stats vary.  The stable gold banner curl and
# parchment edge are independent structural signals and must agree.
PET_SUMMON_RESULT_BANNER_SPEC = LocalCvSpec(
    name=LANDMARK_PET_SUMMON_RESULT_BANNER,
    asset_path=Path(
        "assets/ui/landmarks/pet-summon-result-banner-current.png"
    ),
    region=(0.28, 0.01, 0.48, 0.22),
    calibration=LinearGapCalibration(
        negative_anchor=0.7271584272384644,
        positive_anchor=0.9185329079627991,
    ),
)

PET_SUMMON_RESULT_PARCHMENT_SPEC = LocalCvSpec(
    name=LANDMARK_PET_SUMMON_RESULT_PARCHMENT,
    asset_path=Path(
        "assets/ui/landmarks/pet-summon-result-parchment-current.png"
    ),
    region=(0.32, 0.60, 0.48, 0.98),
    calibration=LinearGapCalibration(
        negative_anchor=0.754900336265564,
        positive_anchor=0.9997232556343079,
    ),
)

PET_INVENTORY_FULL_PROMPT_SPEC = LocalCvSpec(
    name=LANDMARK_PET_INVENTORY_FULL_PROMPT,
    asset_path=Path(
        "assets/ui/landmarks/pet-inventory-full-prompt-current.png"
    ),
    region=(0.32, 0.32, 0.69, 0.63),
    calibration=LinearGapCalibration(
        negative_anchor=0.5635122060775757,
        positive_anchor=0.9883360266685486,
    ),
)

DEFAULT_LOCAL_CV_SPECS = (
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    DAILY_QUESTS_TITLE_SPEC,
    DAILY_QUESTS_TAB_ACTIVE_SPEC,
    DAILY_QUESTS_ROW_CLAIM_SPEC,
    FRIENDS_TITLE_SPEC,
    FRIENDS_ALL_BUTTON_SPEC,
    FRIENDS_SEND_STAMINA_DAILY_SPEC,
    GUILD_MESSAGE_TAB_SPEC,
    GUILD_ATTENDANCE_DAILY_SPEC,
    MAILBOX_TITLE_SPEC,
    MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC,
    MAILBOX_ROW_CLAIM_SPEC,
    MAILBOX_ROW_DELETE_SPEC,
    BATTLE_MODE_SELECT_HEADER_SPEC,
    WORLD_BOSS_DAILY_SPEC,
    BLACK_MARKET_TITLE_SPEC,
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    INVENTORY_FULL_OK_BUTTON_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
    SOCKET_TAB_SPEC,
    SOCKET_ENHANCE_ALL_TITLE_SPEC,
    SOCKET_EQUIPMENT_HOME_ACTIVE_SPEC,
    SOCKET_INVENTORY_FULL_PROMPT_SPEC,
    SOCKET_NO_MATERIAL_PROMPT_SPEC,
    SOCKET_SELL_BULK_BUTTON_SPEC,
    WORLD_BOSS_SELECT_BOSS_HEADER_SPEC,
    WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC,
    WORLD_BOSS_SAPPHIRES_USED_SPEC,
    WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC,
    WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC,
    EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC,
    COMBINE_FUSE_TAB_SPEC,
    COMBINE_FUSE_ACTIVE_SPEC,
    COMBINE_TRANSMUTE_ACTIVE_SPEC,
    COMBINE_ROWS_INDICATOR_SPEC,
    COMBINE_ROWS_UPPER_INDICATOR_SPEC,
    COMBINE_ROW_BOTTOM_INDICATOR_SPEC,
    COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC,
    COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC,
    COMBINE_ALL_TITLE_SPEC,
    COMBINE_ETHEREAL_MASS_PROMPT_SPEC,
    COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC,
    COMBINE_ANIMATION_TAPPABLE_SPEC,
    PETS_SHELL_SUMMON_PACKAGE_SPEC,
    PETS_MANAGE_ACTIVE_SPEC,
    PET_SUMMON_ACTIVE_SPEC,
    PET_COMBINE_ACTIVE_SPEC,
    PET_COMBINE_EVOLVE_PROMPT_SPEC,
    PET_SUMMON_DAILY_SPEC,
    PET_PREMIUM_TICKET_SPEC,
    PET_PREMIUM_GOLD_SPEC,
    PET_EPIC_SELECTOR_SPEC,
    PET_PREMIUM_TICKET_SELECTOR_SPEC,
    PET_PREMIUM_GOLD_SELECTOR_SPEC,
    PET_EPIC_INSUFFICIENT_FRAGMENTS_SPEC,
    PET_SUMMON_RESULT_BANNER_SPEC,
    PET_SUMMON_RESULT_PARCHMENT_SPEC,
    PET_INVENTORY_FULL_PROMPT_SPEC,
)
