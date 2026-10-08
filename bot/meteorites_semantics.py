"""Meteorites Phase A facts. Geometry follows USER_GT and curated live frames.

No shared preparation, anchor loop or character policy lives here. Slot 0 is
Flare; 1..10 are the normal equip order, not the row-major visual order.
"""
from dataclasses import dataclass
from enum import Enum

SCREEN_METEORITES = "screen.meteorites"
METEORITES_MAIN = "landmark.meteorites_main"
METEORITES_DETAIL = "landmark.meteorites_detail"
OVERLAY_METEORITES_DETAIL = "overlay.meteorites_detail"
METEORITES_LOADING = "activity.meteorites_loading"

SET_POINTS = ((.215, .282), (.268, .282), (.320, .282))
SLOT_POINTS = ((.348, .604), (.306, .404), (.386, .404), (.467, .404),
               (.448, .604), (.467, .802), (.386, .802), (.306, .802),
               (.227, .802), (.249, .604), (.227, .404))
BAG_POINTS = tuple((x, y) for y in (.372, .512, .654, .793)
                   for x in (.580, .647, .715, .783))


class SlotState(str, Enum):
    EMPTY = "empty"
    OCCUPIED = "occupied"
    UNKNOWN = "unknown"


class MeteoriteAction(str, Enum):
    EQUIP = "equip"
    UNEQUIP = "unequip"


@dataclass(frozen=True)
class MeteoritesBag:
    sequence: int
    observed_at: float
    active_set: int | None
    page: int | None
    total_pages: int | None
    slots: tuple[SlotState, ...]
    loading: bool = False
    overlay: bool = False

    @property
    def ready(self):
        return (self.active_set in (1, 2, 3) and self.page is not None
                and len(self.slots) == 11 and SlotState.UNKNOWN not in self.slots
                and not self.loading and not self.overlay)

    def equip_slot(self, flare: bool):
        if not self.ready:
            return None
        if flare:
            return 0 if self.slots[0] is SlotState.EMPTY else None
        return next((i for i in range(1, 11) if self.slots[i] is SlotState.EMPTY), None)


@dataclass(frozen=True)
class MeteoriteItem:
    flare: bool
    tier: str
    level: int
    action: MeteoriteAction
    sequence: int
    observed_at: float

    @property
    def key(self):
        return self.flare, self.tier, self.level, self.action


def bag_location(absolute_index: int):
    if type(absolute_index) is not int or absolute_index < 1:
        raise ValueError("Bag index is positive and one-based")
    return (absolute_index - 1) // 16 + 1, (absolute_index - 1) % 16
