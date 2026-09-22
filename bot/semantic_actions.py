"""Typed semantic action intents for the first runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral

from bot.geometry import RelativePoint, relative_point_to_pixel
from bot.craft_semantics import CraftFamily
from bot.monster_wave_actions import MonsterWaveAction


_BLACK_MARKET_SLOT_COUNT = 10
_SOCKET_OPAL_SLOT_COUNT = 16
_EQUIPMENT_INVENTORY_SLOT_COUNT = 16


@dataclass(frozen=True)
class OpenBlackMarket:
    """Request the direct Lobby -> Black Market action."""


@dataclass(frozen=True)
class CloseBlackMarket:
    """Request the Black Market -> Lobby close action."""


@dataclass(frozen=True)
class OpenQuests:
    """Request Lobby -> Quests, which restores the last visited tab."""


@dataclass(frozen=True)
class SelectDailyQuests:
    """Request the Daily Quests tab from an already-confirmed Quests shell."""


@dataclass(frozen=True)
class ClaimAllDailyQuests:
    """Request Claim All for already-confirmed claimable Daily Quest rows."""


@dataclass(frozen=True)
class ClaimDailyQuestsProgressReward:
    """Claim the independently observed 30-Karat Daily progress reward."""


@dataclass(frozen=True)
class CloseDailyQuests:
    """Request the Daily Quests -> Lobby close action."""


@dataclass(frozen=True)
class OpenFriends:
    """Request the direct Lobby -> Friends action."""


@dataclass(frozen=True)
class SendStaminaToAllFriends:
    """Request All after the Friends Send Stamina Daily was confirmed active."""


@dataclass(frozen=True)
class CloseFriends:
    """Request the Friends -> Lobby close action."""


@dataclass(frozen=True)
class OpenPets:
    """Request the direct Lobby -> Pets action."""


@dataclass(frozen=True)
class SelectPetSummon:
    """Request the Summon tab from an already-confirmed Pets surface."""


@dataclass(frozen=True)
class SelectPetCombine:
    """Request the Combine tab from an already-confirmed Pets surface."""


@dataclass(frozen=True)
class ClosePets:
    """Request the Pets -> Lobby back action."""


@dataclass(frozen=True)
class OpenEpicPetSummon:
    """Open the Epic summon selector after availability was observed."""


@dataclass(frozen=True)
class OpenPremiumPetSummon:
    """Open Premium without deciding whether the game consumes ticket or GOLD."""


@dataclass(frozen=True)
class OpenSingleEpicPet:
    """Request exactly 1 (Open) from the Epic selector."""


@dataclass(frozen=True)
class OpenTenEpicPets:
    """Request exactly one 10 (Open) batch from the Epic selector."""


@dataclass(frozen=True)
class OpenSinglePremiumPet:
    """Request exactly 1 (Open) from either Premium selector."""


@dataclass(frozen=True)
class ClosePetSummonResult:
    """Dismiss one already-confirmed stable pet summon result."""


@dataclass(frozen=True)
class AcceptPetInventoryFull:
    """Take the safe Yes route from Pet Full to Pet Combine."""


@dataclass(frozen=True)
class RejectPetInventoryFull:
    """Take No from Pet Full and return to Pet Summon."""


@dataclass(frozen=True)
class OpenPetCombineAll:
    """Request Combine All on the Pet Combine surface."""


@dataclass(frozen=True)
class ConfirmPetCombineAll:
    """Confirm the already-observed Pet Combine All popup."""


@dataclass(frozen=True)
class AcknowledgePetCombineNoMaterial:
    """Acknowledge the non-destructive Pet Combine no-material popup."""


@dataclass(frozen=True)
class RejectPetEpicRunesFull:
    """Choose No on the Epic-runes capacity prompt."""


@dataclass(frozen=True)
class SelectPetLowTierCandidate:
    """Select the center supplied by one safe candidate observation."""

    target: RelativePoint

    def __post_init__(self) -> None:
        relative_point_to_pixel(self.target, 1, 1)


@dataclass(frozen=True)
class OpenPetMassEvolve:
    """Request Mass Evolve after a safe candidate entered selection mode."""


@dataclass(frozen=True)
class ConfirmPetMassEvolve:
    """Confirm a tier-verified Normal or Rare Mass Evolve popup."""


@dataclass(frozen=True)
class CancelPetMassEvolveSelection:
    """Leave Mass Evolve selection before changing Pets tabs."""


@dataclass(frozen=True)
class NextPetCombinePage:
    """Advance one visible Pet Combine grid page inside a bounded search."""


@dataclass(frozen=True)
class OpenMailbox:
    """Request the Lobby -> Mailbox action."""


@dataclass(frozen=True)
class OpenGuild:
    """Request the direct Lobby -> Guild action."""


@dataclass(frozen=True)
class SelectCharacterMail:
    """Request the Character Mail tab inside Mailbox."""


@dataclass(frozen=True)
class ClaimAllCharacterMail:
    """Request Claim All for already-confirmed Character Mail claims."""


@dataclass(frozen=True)
class DeleteReadCharacterMail:
    """Request deletion of already-confirmed read Character Mail."""


@dataclass(frozen=True)
class CloseMailbox:
    """Request the Mailbox -> Lobby close action."""


@dataclass(frozen=True)
class SelectBlackMarketSlot:
    """Request selection of one row-major Black Market offer slot."""

    slot_index: int

    def __post_init__(self) -> None:
        value = self.slot_index
        if (
            isinstance(value, bool)
            or not isinstance(value, Integral)
            or not 0 <= value < _BLACK_MARKET_SLOT_COUNT
        ):
            raise ValueError(
                f"slot_index must be an integer in [0, {_BLACK_MARKET_SLOT_COUNT - 1}]"
            )
        object.__setattr__(self, "slot_index", int(value))


@dataclass(frozen=True)
class AcceptPurchaseConfirmation:
    """Request the Yes action on Purchase Confirmation."""


@dataclass(frozen=True)
class RejectInsufficientGold:
    """Request the No action on Insufficient Gold."""


@dataclass(frozen=True)
class AcknowledgeInventoryFull:
    """Request the common OK action on an Inventory Full popup."""


class QuickMenuLayout(str, Enum):
    LOBBY = "lobby"
    SHIFTED = "shifted"


@dataclass(frozen=True)
class OpenQuickMenu:
    """Request opening Quick Menu from a capability-approved context."""


@dataclass(frozen=True)
class SelectQuickMenuLobby:
    """Request the Lobby tile inside an already-confirmed Quick Menu."""


@dataclass(frozen=True)
class SelectQuickMenuGuild:
    """Request the Guild tile inside an already-confirmed Quick Menu."""

    layout: QuickMenuLayout = QuickMenuLayout.LOBBY

    def __post_init__(self) -> None:
        if not isinstance(self.layout, QuickMenuLayout):
            raise ValueError("layout must be QuickMenuLayout")


@dataclass(frozen=True)
class SelectQuickMenuTrading:
    """Request the HIL-verified shifted Trading tile in Quick Menu."""


@dataclass(frozen=True)
class SelectQuickMenuCraft:
    """Request Craft from the HIL-verified shifted Quick Menu layout."""


@dataclass(frozen=True)
class OpenHeroCraft:
    """Open one visible Hero family card; subtype selection stays default."""

    family: CraftFamily

    def __post_init__(self) -> None:
        if not isinstance(self.family, CraftFamily):
            raise ValueError("family must be CraftFamily")


@dataclass(frozen=True)
class SelectCraftMax:
    """Select the acquired Craft >> quantity control once."""


@dataclass(frozen=True)
class ConfirmCraftMaterial:
    """Use the verified material button; never a Karat spend button."""


@dataclass(frozen=True)
class CancelCraft:
    """Cancel the currently verified Craft selector."""


@dataclass(frozen=True)
class RejectCraftPremium:
    """Choose No on the explicitly observed Karat boundary."""


@dataclass(frozen=True)
class DismissCraftResult:
    """Dismiss Craft result through the acquired non-interactive side area."""


@dataclass(frozen=True)
class OpenCharacterSelect:
    """Request the Character tile inside an already-open Quick Menu."""

    layout: QuickMenuLayout = QuickMenuLayout.LOBBY

    def __post_init__(self) -> None:
        if not isinstance(self.layout, QuickMenuLayout):
            raise ValueError("layout must be QuickMenuLayout")


@dataclass(frozen=True)
class CheckInGuildAttendance:
    """Request the active Attendance action on an already-confirmed Guild screen."""


@dataclass(frozen=True)
class Swipe:
    """Request one normalized physical swipe without scroll policy."""

    start: RelativePoint
    end: RelativePoint
    duration_ms: int

    def __post_init__(self) -> None:
        relative_point_to_pixel(self.start, 1, 1)
        relative_point_to_pixel(self.end, 1, 1)
        duration = self.duration_ms
        if (
            isinstance(duration, bool)
            or not isinstance(duration, Integral)
            or duration <= 0
        ):
            raise ValueError("duration_ms must be a positive integer")
        object.__setattr__(self, "duration_ms", int(duration))


@dataclass(frozen=True)
class SelectLastVisibleCharacter:
    """Request the last occupied card in the end-of-list layout."""


@dataclass(frozen=True)
class SelectCharacterCard:
    """Select the card center derived from a located grid sentinel."""

    center: RelativePoint

    def __post_init__(self) -> None:
        relative_point_to_pixel(self.center, 1, 1)


@dataclass(frozen=True)
class ConfirmCharacterSelection:
    """Request the Select button after choosing a character card."""


@dataclass(frozen=True)
class ToggleAutoBattle:
    """Request one toggle tap after Auto Battle was confirmed OFF."""


@dataclass(frozen=True)
class OpenBattleModeSelect:
    """Request Lobby -> Survival/Battle Mode Select."""


@dataclass(frozen=True)
class OpenWorldBossSelector:
    """Request the World Boss tile from Battle Mode Select."""


@dataclass(frozen=True)
class SelectAvailableWorldBoss:
    """Request the available boss from the Select Boss overlay."""


@dataclass(frozen=True)
class AcknowledgeWorldBossPreviousRewards:
    """Request OK on the optional Previous Rewards popup."""


@dataclass(frozen=True)
class StartWorldBossBattle:
    """Request one World Boss participation from the clean main screen."""


@dataclass(frozen=True)
class ContinueAfterWorldBossRaid:
    """Request the safe tap-anywhere action after Raid Complete."""


@dataclass(frozen=True)
class ExitWorldBoss:
    """Request Back from World Boss to Battle Mode Select (human-confirmed)."""


@dataclass(frozen=True)
class AcceptSocketInventoryFull:
    """Request Yes on the global Socket inventory-full guard."""


@dataclass(frozen=True)
class RejectSocketInventoryFull:
    """Request No on the global Socket inventory-full guard."""


@dataclass(frozen=True)
class RejectMeteorInventoryFull:
    """Request No on the global Meteorite inventory-full guard."""


@dataclass(frozen=True)
class OpenSocketEnhanceAll:
    """Request the Socket Enhance All modal."""


@dataclass(frozen=True)
class SelectSocketEnhanceGold:
    """Request the GOLD option; no KARATS action exists by design."""


@dataclass(frozen=True)
class AcknowledgeSocketNoMaterial:
    """Request OK on Socket's no-material popup."""


@dataclass(frozen=True)
class CloseSocketEnhanceAll:
    """Request Close on the Enhance All modal."""


@dataclass(frozen=True)
class OpenSocketEquipmentHome:
    """Request the acquired Equipment Home submenu."""


@dataclass(frozen=True)
class SelectSocketOpalSlot:
    """Request one visible row-major Socket opal slot."""

    slot_index: int

    def __post_init__(self) -> None:
        value = self.slot_index
        if (
            isinstance(value, bool)
            or not isinstance(value, Integral)
            or not 0 <= value < _SOCKET_OPAL_SLOT_COUNT
        ):
            raise ValueError(
                f"slot_index must be an integer in [0, {_SOCKET_OPAL_SLOT_COUNT - 1}]"
            )
        object.__setattr__(self, "slot_index", int(value))


@dataclass(frozen=True)
class OpenSocketSell:
    """Request Sell for the already selected Socket item."""


@dataclass(frozen=True)
class SellSocketInBulk:
    """Request the only productively authorized Socket sale action."""


@dataclass(frozen=True)
class CancelSocketSell:
    """Request non-destructive cancellation of the Socket Sell popup."""


@dataclass(frozen=True)
class TapSocketEnhanceAnimation:
    """Request one tap in the acquired safe animation region."""


@dataclass(frozen=True)
class ExitSocket:
    """Request the live-verified Socket Back action."""


@dataclass(frozen=True)
class OpenEquipmentCombine:
    """Request Combine on the global equipment inventory-full guard."""


@dataclass(frozen=True)
class SelectEquipmentInventorySlot:
    """Request one visible row-major Equipment inventory slot."""

    slot_index: int

    def __post_init__(self) -> None:
        value = self.slot_index
        if (
            isinstance(value, bool)
            or not isinstance(value, Integral)
            or not 0 <= value < _EQUIPMENT_INVENTORY_SLOT_COUNT
        ):
            raise ValueError(
                "slot_index must be an integer in "
                f"[0, {_EQUIPMENT_INVENTORY_SLOT_COUNT - 1}]"
            )
        object.__setattr__(self, "slot_index", int(value))


@dataclass(frozen=True)
class OpenEquipmentSell:
    """Request Sell for the already selected Equipment item."""


@dataclass(frozen=True)
class ConfirmEquipmentBulkSale:
    """Confirm the already-authorized Equipment bulk group sale."""


@dataclass(frozen=True)
class CancelEquipmentSale:
    """Cancel the Equipment Sell confirmation popup."""


@dataclass(frozen=True)
class SelectCombineTransmute:
    """Request the base Transmute tab."""


@dataclass(frozen=True)
class SelectCombineFuse:
    """Request the base Fuse tab."""


@dataclass(frozen=True)
class OpenCombineAll:
    """Request Combine All in the active base Combine mode."""


@dataclass(frozen=True)
class ConfirmCombineAll:
    """Confirm the active Combine All popup."""


@dataclass(frozen=True)
class OpenAwakenedTransmute:
    """Open the partially visible Awakened Transmute entry."""


@dataclass(frozen=True)
class OpenEtherealRandomPart:
    """Open Ethereal Random Part from Awakened Transmute."""


@dataclass(frozen=True)
class OpenEtherealMassCombine:
    """Request Mass Combine in Ethereal Random Part."""


@dataclass(frozen=True)
class ConfirmEtherealMassCombine:
    """Confirm the Ethereal Mass Combine operation."""


@dataclass(frozen=True)
class AcknowledgeEtherealNoMaterial:
    """Acknowledge the defensive Ethereal no-material popup."""


@dataclass(frozen=True)
class TapCombineAnimation:
    """Request one tap in the acquired Combine animation region."""


@dataclass(frozen=True)
class ExitCombine:
    """Request the live-verified Combine Back action."""


@dataclass(frozen=True)
class DismissPortalNotification:
    """Request the X dismiss of a transversal portal notification overlay."""


@dataclass(frozen=True)
class OpenTrading:
    """Request the direct Lobby -> Trading Center action."""


@dataclass(frozen=True)
class SelectTradingAvatarKeys:
    """Select Avatars & Keys from an already-confirmed Trading context."""


@dataclass(frozen=True)
class CloseTrading:
    """Request the Trading-specific X close action to Lobby."""


@dataclass(frozen=True)
class OpenTreasure:
    """Request the direct Lobby -> Treasure tile action."""


@dataclass(frozen=True)
class SelectGoldChest:
    """Request the Gold chest tile from an already-confirmed Treasure grid."""


@dataclass(frozen=True)
class ConfirmSingleGoldOpen:
    """Request exactly 1 (Open) from the Gold selector popup."""


@dataclass(frozen=True)
class ConfirmRepeatGoldOpen:
    """Request exactly one 10 (Open) batch from the Gold popup."""


@dataclass(frozen=True)
class DismissTreasureResult:
    """Dismiss one already-confirmed stable Treasure result."""


@dataclass(frozen=True)
class ExitTreasure:
    """Request Back from Treasure to Lobby."""


@dataclass(frozen=True)
class DismissWorldBossBagFull:
    """Request Close on the World Boss Start bag-full guard."""


SemanticAction = (
    MonsterWaveAction
    | OpenBlackMarket
    | CloseBlackMarket
    | OpenQuests
    | SelectDailyQuests
    | ClaimAllDailyQuests
    | ClaimDailyQuestsProgressReward
    | CloseDailyQuests
    | OpenFriends
    | SendStaminaToAllFriends
    | CloseFriends
    | OpenPets
    | SelectPetSummon
    | SelectPetCombine
    | ClosePets
    | OpenEpicPetSummon
    | OpenPremiumPetSummon
    | OpenSingleEpicPet
    | OpenTenEpicPets
    | OpenSinglePremiumPet
    | ClosePetSummonResult
    | AcceptPetInventoryFull
    | RejectPetInventoryFull
    | OpenPetCombineAll
    | ConfirmPetCombineAll
    | AcknowledgePetCombineNoMaterial
    | RejectPetEpicRunesFull
    | SelectPetLowTierCandidate
    | OpenPetMassEvolve
    | ConfirmPetMassEvolve
    | CancelPetMassEvolveSelection
    | NextPetCombinePage
    | OpenMailbox
    | SelectCharacterMail
    | ClaimAllCharacterMail
    | DeleteReadCharacterMail
    | CloseMailbox
    | OpenGuild
    | SelectBlackMarketSlot
    | AcceptPurchaseConfirmation
    | RejectInsufficientGold
    | AcknowledgeInventoryFull
    | OpenQuickMenu
    | SelectQuickMenuLobby
    | SelectQuickMenuGuild
    | SelectQuickMenuTrading
    | SelectQuickMenuCraft
    | OpenHeroCraft
    | SelectCraftMax
    | ConfirmCraftMaterial
    | CancelCraft
    | RejectCraftPremium
    | DismissCraftResult
    | OpenCharacterSelect
    | CheckInGuildAttendance
    | Swipe
    | SelectLastVisibleCharacter
    | SelectCharacterCard
    | ConfirmCharacterSelection
    | ToggleAutoBattle
    | OpenBattleModeSelect
    | OpenWorldBossSelector
    | SelectAvailableWorldBoss
    | AcknowledgeWorldBossPreviousRewards
    | StartWorldBossBattle
    | ContinueAfterWorldBossRaid
    | ExitWorldBoss
    | AcceptSocketInventoryFull
    | RejectSocketInventoryFull
    | RejectMeteorInventoryFull
    | OpenSocketEnhanceAll
    | SelectSocketEnhanceGold
    | AcknowledgeSocketNoMaterial
    | CloseSocketEnhanceAll
    | OpenSocketEquipmentHome
    | SelectSocketOpalSlot
    | OpenSocketSell
    | SellSocketInBulk
    | CancelSocketSell
    | TapSocketEnhanceAnimation
    | ExitSocket
    | OpenEquipmentCombine
    | SelectEquipmentInventorySlot
    | OpenEquipmentSell
    | ConfirmEquipmentBulkSale
    | CancelEquipmentSale
    | SelectCombineTransmute
    | SelectCombineFuse
    | OpenCombineAll
    | ConfirmCombineAll
    | OpenAwakenedTransmute
    | OpenEtherealRandomPart
    | OpenEtherealMassCombine
    | ConfirmEtherealMassCombine
    | AcknowledgeEtherealNoMaterial
    | TapCombineAnimation
    | ExitCombine
    | DismissWorldBossBagFull
    | DismissPortalNotification
    | OpenTrading
    | SelectTradingAvatarKeys
    | CloseTrading
    | OpenTreasure
    | SelectGoldChest
    | ConfirmSingleGoldOpen
    | ConfirmRepeatGoldOpen
    | DismissTreasureResult
    | ExitTreasure
)


__all__ = (
    "AcceptPurchaseConfirmation",
    "AcceptSocketInventoryFull",
    "AcknowledgeEtherealNoMaterial",
    "AcknowledgeSocketNoMaterial",
    "AcknowledgeWorldBossPreviousRewards",
    "AcknowledgeInventoryFull",
    "AcknowledgePetCombineNoMaterial",
    "AcceptPetInventoryFull",
    "CloseBlackMarket",
    "ClaimAllCharacterMail",
    "ClaimAllDailyQuests",
    "ClaimDailyQuestsProgressReward",
    "CheckInGuildAttendance",
    "CloseDailyQuests",
    "CloseFriends",
    "CloseMailbox",
    "ClosePets",
    "ClosePetSummonResult",
    "ConfirmCharacterSelection",
    "ContinueAfterWorldBossRaid",
    "ExitWorldBoss",
    "CancelSocketSell",
    "CancelEquipmentSale",
    "CloseSocketEnhanceAll",
    "ConfirmCombineAll",
    "ConfirmEquipmentBulkSale",
    "ConfirmEtherealMassCombine",
    "ConfirmPetCombineAll",
    "ConfirmPetMassEvolve",
    "CancelPetMassEvolveSelection",
    "DismissWorldBossBagFull",
    "DeleteReadCharacterMail",
    "DismissPortalNotification",
    "OpenTrading",
    "SelectTradingAvatarKeys",
    "CloseTrading",
    "OpenBlackMarket",
    "OpenGuild",
    "OpenFriends",
    "OpenQuests",
    "OpenMailbox",
    "OpenPets",
    "OpenEpicPetSummon",
    "OpenPremiumPetSummon",
    "OpenSingleEpicPet",
    "OpenTenEpicPets",
    "OpenSinglePremiumPet",
    "OpenPetCombineAll",
    "OpenPetMassEvolve",
    "OpenBattleModeSelect",
    "OpenTreasure",
    "SelectGoldChest",
    "ConfirmSingleGoldOpen",
    "ConfirmRepeatGoldOpen",
    "DismissTreasureResult",
    "ExitTreasure",
    "OpenCharacterSelect",
    "OpenQuickMenu",
    "OpenSocketEnhanceAll",
    "OpenSocketEquipmentHome",
    "OpenSocketSell",
    "QuickMenuLayout",
    "OpenWorldBossSelector",
    "RejectInsufficientGold",
    "RejectSocketInventoryFull",
    "RejectMeteorInventoryFull",
    "RejectPetEpicRunesFull",
    "RejectPetInventoryFull",
    "SelectSocketEnhanceGold",
    "SelectSocketOpalSlot",
    "SellSocketInBulk",
    "Swipe",
    "SelectLastVisibleCharacter",
    "SelectCharacterCard",
    "SelectCharacterMail",
    "SelectDailyQuests",
    "SelectPetCombine",
    "SelectPetLowTierCandidate",
    "SelectPetSummon",
    "SelectQuickMenuLobby",
    "SelectQuickMenuGuild",
    "SelectQuickMenuTrading",
    "SelectQuickMenuCraft",
    "OpenHeroCraft",
    "SelectCraftMax",
    "ConfirmCraftMaterial",
    "CancelCraft",
    "RejectCraftPremium",
    "DismissCraftResult",
    "SendStaminaToAllFriends",
    "SelectAvailableWorldBoss",
    "SelectBlackMarketSlot",
    "SemanticAction",
    "ToggleAutoBattle",
    "TapSocketEnhanceAnimation",
    "ExitSocket",
    "ExitCombine",
    "OpenAwakenedTransmute",
    "OpenCombineAll",
    "OpenEquipmentCombine",
    "OpenEquipmentSell",
    "OpenEtherealMassCombine",
    "OpenEtherealRandomPart",
    "SelectCombineFuse",
    "SelectCombineTransmute",
    "SelectEquipmentInventorySlot",
    "StartWorldBossBattle",
    "TapCombineAnimation",
    "NextPetCombinePage",
)
