"""Typed semantic action intents for the first runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral

from bot.geometry import RelativePoint, relative_point_to_pixel


_BLACK_MARKET_SLOT_COUNT = 10
_SOCKET_OPAL_SLOT_COUNT = 16


@dataclass(frozen=True)
class OpenBlackMarket:
    """Request the direct Lobby -> Black Market action."""


@dataclass(frozen=True)
class CloseBlackMarket:
    """Request the Black Market -> Lobby close action."""


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
class OpenCharacterSelect:
    """Request the Character tile inside an already-open Quick Menu."""

    layout: QuickMenuLayout = QuickMenuLayout.LOBBY

    def __post_init__(self) -> None:
        if not isinstance(self.layout, QuickMenuLayout):
            raise ValueError("layout must be QuickMenuLayout")


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
class AcceptSocketInventoryFull:
    """Request Yes on the global Socket inventory-full guard."""


@dataclass(frozen=True)
class RejectSocketInventoryFull:
    """Request No on the global Socket inventory-full guard."""


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
class DismissWorldBossBagFull:
    """Request Close on the World Boss Start bag-full guard."""


SemanticAction = (
    OpenBlackMarket
    | CloseBlackMarket
    | SelectBlackMarketSlot
    | AcceptPurchaseConfirmation
    | RejectInsufficientGold
    | AcknowledgeInventoryFull
    | OpenQuickMenu
    | OpenCharacterSelect
    | Swipe
    | SelectLastVisibleCharacter
    | ConfirmCharacterSelection
    | ToggleAutoBattle
    | OpenBattleModeSelect
    | OpenWorldBossSelector
    | SelectAvailableWorldBoss
    | AcknowledgeWorldBossPreviousRewards
    | StartWorldBossBattle
    | ContinueAfterWorldBossRaid
    | AcceptSocketInventoryFull
    | RejectSocketInventoryFull
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
    | DismissWorldBossBagFull
)


__all__ = (
    "AcceptPurchaseConfirmation",
    "AcceptSocketInventoryFull",
    "AcknowledgeSocketNoMaterial",
    "AcknowledgeWorldBossPreviousRewards",
    "AcknowledgeInventoryFull",
    "CloseBlackMarket",
    "ConfirmCharacterSelection",
    "ContinueAfterWorldBossRaid",
    "CancelSocketSell",
    "CloseSocketEnhanceAll",
    "DismissWorldBossBagFull",
    "OpenBlackMarket",
    "OpenBattleModeSelect",
    "OpenCharacterSelect",
    "OpenQuickMenu",
    "OpenSocketEnhanceAll",
    "OpenSocketEquipmentHome",
    "OpenSocketSell",
    "QuickMenuLayout",
    "OpenWorldBossSelector",
    "RejectInsufficientGold",
    "RejectSocketInventoryFull",
    "SelectSocketEnhanceGold",
    "SelectSocketOpalSlot",
    "SellSocketInBulk",
    "Swipe",
    "SelectLastVisibleCharacter",
    "SelectAvailableWorldBoss",
    "SelectBlackMarketSlot",
    "SemanticAction",
    "ToggleAutoBattle",
    "TapSocketEnhanceAnimation",
    "ExitSocket",
    "StartWorldBossBattle",
)
