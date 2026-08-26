"""Typed semantic action intents for the first runtime vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

from bot.geometry import RelativePoint, relative_point_to_pixel


_BLACK_MARKET_SLOT_COUNT = 10


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
class OpenQuickMenu:
    """Request opening Quick Menu from Lobby."""


@dataclass(frozen=True)
class OpenCharacterSelect:
    """Request the Character tile inside an already-open Quick Menu."""


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


SemanticAction = (
    OpenBlackMarket
    | CloseBlackMarket
    | SelectBlackMarketSlot
    | AcceptPurchaseConfirmation
    | RejectInsufficientGold
    | OpenQuickMenu
    | OpenCharacterSelect
    | Swipe
    | SelectLastVisibleCharacter
    | ConfirmCharacterSelection
)


__all__ = (
    "AcceptPurchaseConfirmation",
    "CloseBlackMarket",
    "ConfirmCharacterSelection",
    "OpenBlackMarket",
    "OpenCharacterSelect",
    "OpenQuickMenu",
    "RejectInsufficientGold",
    "Swipe",
    "SelectLastVisibleCharacter",
    "SelectBlackMarketSlot",
    "SemanticAction",
)
