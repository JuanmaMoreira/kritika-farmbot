"""Translate semantic intents to normalized taps at the Android boundary."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

from bot.adb import AdbClient
from bot.geometry import (
    PixelPoint,
    RelativePoint,
    frame_dimensions,
    relative_point_to_pixel,
)
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    CloseBlackMarket,
    OpenBlackMarket,
    RejectInsufficientGold,
    SelectBlackMarketSlot,
    SemanticAction,
)


@dataclass(frozen=True)
class FrameGeometry:
    """Frame dimensions already derived from the actual captured ndarray."""

    width: int
    height: int

    def __post_init__(self) -> None:
        for name in ("width", "height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            object.__setattr__(self, name, int(value))

    @classmethod
    def from_frame(cls, frame: object) -> "FrameGeometry":
        """Build geometry from ``frame.shape`` without querying device metadata."""

        width, height = frame_dimensions(frame)
        return cls(width=width, height=height)


@dataclass(frozen=True)
class BlackMarketActionTargets:
    """Normalized targets validated for the current landscape layout."""

    open_black_market: RelativePoint = (0.1667, 0.8930)
    close_black_market: RelativePoint = (0.8097, 0.1324)
    slots: tuple[RelativePoint, ...] = (
        (0.4491, 0.3415),
        (0.7592, 0.3415),
        (0.4506, 0.4698),
        (0.7570, 0.4706),
        (0.4524, 0.5948),
        (0.7507, 0.6095),
        (0.4539, 0.7337),
        (0.7592, 0.7377),
        (0.4454, 0.8725),
        (0.7592, 0.8717),
    )
    accept_purchase: RelativePoint = (0.4347, 0.6340)
    reject_insufficient_gold: RelativePoint = (0.5690, 0.6307)

    def __post_init__(self) -> None:
        slots = tuple(self.slots)
        if len(slots) != 10:
            raise ValueError("slots must contain exactly ten row-major targets")
        points = (
            self.open_black_market,
            self.close_black_market,
            *slots,
            self.accept_purchase,
            self.reject_insufficient_gold,
        )
        for point in points:
            # Reuse the production point validator without fixing a resolution.
            relative_point_to_pixel(point, 1, 1)
        object.__setattr__(self, "slots", slots)


DEFAULT_BLACK_MARKET_ACTION_TARGETS = BlackMarketActionTargets()


@dataclass(frozen=True)
class ActionExecution:
    """Diagnostic receipt for one physical action already sent to ADB."""

    action: SemanticAction
    normalized_target: RelativePoint
    pixel_target: PixelPoint


class ActionExecutor:
    """Resolve an intent to one tap without recognizing or awaiting game state."""

    def __init__(
        self,
        adb: AdbClient,
        *,
        targets: BlackMarketActionTargets = DEFAULT_BLACK_MARKET_ACTION_TARGETS,
    ) -> None:
        if not callable(getattr(adb, "tap", None)):
            raise ValueError("adb must provide tap(x, y)")
        if not isinstance(targets, BlackMarketActionTargets):
            raise ValueError("targets must be BlackMarketActionTargets")
        self.adb = adb
        self.targets = targets

    def execute(
        self, action: SemanticAction, geometry: FrameGeometry
    ) -> ActionExecution:
        """Send exactly one normalized target as an ADB pixel tap."""

        if not isinstance(geometry, FrameGeometry):
            raise ValueError("geometry must be FrameGeometry")
        target = self._target_for(action)
        pixel = relative_point_to_pixel(target, geometry.width, geometry.height)
        self.adb.tap(*pixel)
        return ActionExecution(
            action=action,
            normalized_target=target,
            pixel_target=pixel,
        )

    def _target_for(self, action: SemanticAction) -> RelativePoint:
        if isinstance(action, OpenBlackMarket):
            return self.targets.open_black_market
        if isinstance(action, CloseBlackMarket):
            return self.targets.close_black_market
        if isinstance(action, SelectBlackMarketSlot):
            return self.targets.slots[action.slot_index]
        if isinstance(action, AcceptPurchaseConfirmation):
            return self.targets.accept_purchase
        if isinstance(action, RejectInsufficientGold):
            return self.targets.reject_insufficient_gold
        raise ValueError("unsupported semantic action")


__all__ = (
    "ActionExecution",
    "ActionExecutor",
    "BlackMarketActionTargets",
    "DEFAULT_BLACK_MARKET_ACTION_TARGETS",
    "FrameGeometry",
)
