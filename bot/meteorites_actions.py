"""Phase A inputs. Only the acquired Lobby Quick Menu layout is enabled."""
from dataclasses import dataclass
from bot.meteorites_semantics import BAG_POINTS, SLOT_POINTS, SET_POINTS


@dataclass(frozen=True)
class OpenMeteorites: pass

@dataclass(frozen=True)
class SelectQuickMenuMeteorites: pass

@dataclass(frozen=True)
class SelectMeteoritesSet:
    number: int
    def __post_init__(self):
        if type(self.number) is not int or self.number not in (1,2,3):
            raise ValueError('set must be 1..3')

@dataclass(frozen=True)
class SelectMeteoritesBagCell:
    cell: int
    def __post_init__(self):
        if type(self.cell) is not int or not 0<=self.cell<16:
            raise ValueError('Bag cell must be 0..15')

@dataclass(frozen=True)
class SelectMeteoritesSlot:
    slot: int
    def __post_init__(self):
        if type(self.slot) is not int or not 0<=self.slot<11:
            raise ValueError('set slot must be 0..10')

@dataclass(frozen=True)
class NextMeteoritesPage: pass

@dataclass(frozen=True)
class PreviousMeteoritesPage: pass

@dataclass(frozen=True)
class EquipMeteorite: pass

@dataclass(frozen=True)
class UnequipMeteorite: pass

@dataclass(frozen=True)
class CloseMeteoriteDetail: pass

@dataclass(frozen=True)
class ExitMeteorites: pass

METEORITES_TARGETS = {
    OpenMeteorites:(.925,.755), SelectQuickMenuMeteorites:(.076,.496),
    NextMeteoritesPage:(.730,.910), PreviousMeteoritesPage:(.630,.910),
    EquipMeteorite:(.220,.310), UnequipMeteorite:(.220,.310),
    CloseMeteoriteDetail:(.890,.300), ExitMeteorites:(.802,.073),
}

def meteorites_target(action):
    if isinstance(action,SelectMeteoritesSet): return SET_POINTS[action.number-1]
    if isinstance(action,SelectMeteoritesBagCell): return BAG_POINTS[action.cell]
    if isinstance(action,SelectMeteoritesSlot): return SLOT_POINTS[action.slot]
    return METEORITES_TARGETS.get(type(action))
