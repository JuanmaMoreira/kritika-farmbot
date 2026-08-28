"""Translate typed actions to normalized physical Android input."""

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
    AcknowledgeInventoryFull,
    CloseBlackMarket,
    ConfirmCharacterSelection,
    OpenBlackMarket,
    OpenCharacterSelect,
    OpenQuickMenu,
    RejectInsufficientGold,
    SelectLastVisibleCharacter,
    SelectBlackMarketSlot,
    SemanticAction,
    Swipe,
    ToggleAutoBattle,
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
    acknowledge_inventory_full: RelativePoint = (0.5006, 0.6270)

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
            self.acknowledge_inventory_full,
        )
        for point in points:
            # Reuse the production point validator without fixing a resolution.
            relative_point_to_pixel(point, 1, 1)
        object.__setattr__(self, "slots", slots)


DEFAULT_BLACK_MARKET_ACTION_TARGETS = BlackMarketActionTargets()


@dataclass(frozen=True)
class RotationActionTargets:
    """Normalized targets measured from the current 2712x1224 layout.

    The character card target describes the first column of the final visible
    row. It is a layout rule and is intentionally independent of the configured
    number of characters.
    """

    # Shared live-confirmed hit target inside the player header. It opens and
    # closes Quick Menu from both Lobby and World Boss at the current geometry.
    open_quick_menu: RelativePoint = (0.1940, 0.0564)
    open_character_select: RelativePoint = (0.0704, 0.7835)
    last_visible_character: RelativePoint = (0.5500, 0.7300)
    confirm_character_selection: RelativePoint = (0.6855, 0.9101)

    def __post_init__(self) -> None:
        for point in (
            self.open_quick_menu,
            self.open_character_select,
            self.last_visible_character,
            self.confirm_character_selection,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_ROTATION_ACTION_TARGETS = RotationActionTargets()


@dataclass(frozen=True)
class BattleActionTargets:
    """Normalized targets acquired from the live World Boss battle layout."""

    toggle_auto_battle: RelativePoint = (0.8625, 0.0480)

    def __post_init__(self) -> None:
        relative_point_to_pixel(self.toggle_auto_battle, 1, 1)


DEFAULT_BATTLE_ACTION_TARGETS = BattleActionTargets()


@dataclass(frozen=True)
class ActionExecution:
    """Diagnostic receipt for one physical action already sent to ADB."""

    action: SemanticAction
    normalized_target: RelativePoint
    pixel_target: PixelPoint


@dataclass(frozen=True)
class SwipeExecution:
    """Diagnostic receipt for one physical swipe already sent to ADB."""

    action: Swipe
    normalized_start: RelativePoint
    normalized_end: RelativePoint
    pixel_start: PixelPoint
    pixel_end: PixelPoint
    duration_ms: int


class ActionExecutor:
    """Resolve one intent to physical input without recognizing game state."""

    def __init__(
        self,
        adb: AdbClient,
        *,
        targets: BlackMarketActionTargets = DEFAULT_BLACK_MARKET_ACTION_TARGETS,
        rotation_targets: RotationActionTargets = DEFAULT_ROTATION_ACTION_TARGETS,
        battle_targets: BattleActionTargets = DEFAULT_BATTLE_ACTION_TARGETS,
    ) -> None:
        if not callable(getattr(adb, "tap", None)):
            raise ValueError("adb must provide tap(x, y)")
        if not isinstance(targets, BlackMarketActionTargets):
            raise ValueError("targets must be BlackMarketActionTargets")
        if not isinstance(rotation_targets, RotationActionTargets):
            raise ValueError("rotation_targets must be RotationActionTargets")
        if not isinstance(battle_targets, BattleActionTargets):
            raise ValueError("battle_targets must be BattleActionTargets")
        self.adb = adb
        self.targets = targets
        self.rotation_targets = rotation_targets
        self.battle_targets = battle_targets

    def execute(
        self, action: SemanticAction, geometry: FrameGeometry
    ) -> ActionExecution | SwipeExecution:
        """Translate one semantic action to exactly one ADB input command."""

        if not isinstance(geometry, FrameGeometry):
            raise ValueError("geometry must be FrameGeometry")
        if isinstance(action, Swipe):
            return self._execute_swipe(action, geometry)
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
        if isinstance(action, AcknowledgeInventoryFull):
            return self.targets.acknowledge_inventory_full
        if isinstance(action, OpenQuickMenu):
            return self.rotation_targets.open_quick_menu
        if isinstance(action, OpenCharacterSelect):
            return self.rotation_targets.open_character_select
        if isinstance(action, SelectLastVisibleCharacter):
            return self.rotation_targets.last_visible_character
        if isinstance(action, ConfirmCharacterSelection):
            return self.rotation_targets.confirm_character_selection
        if isinstance(action, ToggleAutoBattle):
            return self.battle_targets.toggle_auto_battle
        raise ValueError("unsupported semantic action")

    def _execute_swipe(
        self,
        action: Swipe,
        geometry: FrameGeometry,
    ) -> SwipeExecution:
        swipe = getattr(self.adb, "swipe", None)
        if not callable(swipe):
            raise ValueError("adb must provide swipe(x1, y1, x2, y2, duration_ms)")
        start = action.start
        end = action.end
        pixel_start = relative_point_to_pixel(start, geometry.width, geometry.height)
        pixel_end = relative_point_to_pixel(end, geometry.width, geometry.height)
        duration = action.duration_ms
        swipe(*pixel_start, *pixel_end, duration)
        return SwipeExecution(
            action=action,
            normalized_start=start,
            normalized_end=end,
            pixel_start=pixel_start,
            pixel_end=pixel_end,
            duration_ms=duration,
        )


__all__ = (
    "ActionExecution",
    "ActionExecutor",
    "BlackMarketActionTargets",
    "BattleActionTargets",
    "DEFAULT_BATTLE_ACTION_TARGETS",
    "DEFAULT_BLACK_MARKET_ACTION_TARGETS",
    "DEFAULT_ROTATION_ACTION_TARGETS",
    "FrameGeometry",
    "RotationActionTargets",
    "SwipeExecution",
)
