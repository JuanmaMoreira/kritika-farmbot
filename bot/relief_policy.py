"""Routine-owned permissions; callers retain evidence and return navigation."""
from dataclasses import dataclass, field, replace
from enum import Enum

from bot.craft_semantics import CraftFamily
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_semantics import EquipmentType


class ReliefCapability(str, Enum):
    SOCKET = 'socket'
    EQUIPMENT = 'equipment'
    CRAFTING_MATERIAL = 'crafting_material'
    TREASURE = 'treasure'


@dataclass(frozen=True)
class SocketReliefPolicy:
    enhance_all: bool = True
    sell_incompatible: bool = True

    def __post_init__(self):
        if type(self.enhance_all) is not bool or type(self.sell_incompatible) is not bool:
            raise ValueError('Socket permissions must be bool')


@dataclass(frozen=True)
class ReliefPolicy:
    socket: SocketReliefPolicy = SocketReliefPolicy()
    equipment_sell: EquipmentSellPolicy = EquipmentSellPolicy()
    # Preserve the established drain of all eligible families on a paid visit.
    craft_categories: frozenset[CraftFamily] = frozenset(CraftFamily)
    treasure_gold_keys: bool = True

    def __post_init__(self):
        if not isinstance(self.socket, SocketReliefPolicy) or not isinstance(self.equipment_sell, EquipmentSellPolicy):
            raise ValueError('invalid relief policy')
        if any(type(v) is not CraftFamily for v in self.craft_categories):
            raise ValueError('unknown Craft category')
        object.__setattr__(self, 'craft_categories', frozenset(self.craft_categories))
        if type(self.treasure_gold_keys) is not bool:
            raise ValueError('Treasure permission must be bool')

    @classmethod
    def safe(cls):
        return cls(SocketReliefPolicy(False, False), EquipmentSellPolicy(frozenset(), False), frozenset(), False)

    def to_dict(self):
        return {
            'socket': {'enhance_all': self.socket.enhance_all, 'sell_incompatible': self.socket.sell_incompatible},
            'equipment_sell': {'ethereal_types': sorted(t.value for t in self.equipment_sell.ethereal_types),
                               'ethereal_enhance': self.equipment_sell.ethereal_enhance},
            'crafting_material': {'categories': sorted(f.value for f in self.craft_categories)},
            'treasure': {'gold_keys': self.treasure_gold_keys},
        }

    @classmethod
    def from_dict(cls, raw):
        # No Platinum permission until its operation and physical GT exist.
        if not isinstance(raw, dict) or set(raw) != {'socket', 'equipment_sell', 'crafting_material', 'treasure'}:
            raise ValueError('unsupported relief configuration')
        if set(raw['socket']) != {'enhance_all', 'sell_incompatible'} or set(raw['equipment_sell']) != {'ethereal_types', 'ethereal_enhance'}:
            raise ValueError('invalid relief fields')
        if set(raw['crafting_material']) != {'categories'} or set(raw['treasure']) != {'gold_keys'}:
            raise ValueError('unimplemented relief permission')
        if not isinstance(raw['equipment_sell']['ethereal_types'], list) or not isinstance(raw['crafting_material']['categories'], list):
            raise ValueError('relief categories must be arrays')
        return cls(SocketReliefPolicy(**raw['socket']),
                   EquipmentSellPolicy(frozenset(EquipmentType(t) for t in raw['equipment_sell']['ethereal_types']), raw['equipment_sell']['ethereal_enhance']),
                   frozenset(CraftFamily(f) for f in raw['crafting_material']['categories']), raw['treasure']['gold_keys'])


@dataclass(frozen=True)
class ReliefCoordinator:
    policy: ReliefPolicy = field(default_factory=ReliefPolicy)

    def handle(self, capability, operation, *args, **kwargs):
        """Delegate once; never infer pressure, freshness, navigation or retries."""
        capability = ReliefCapability(capability)
        if capability is ReliefCapability.SOCKET:
            kwargs['policy'] = self.policy.socket
        elif capability is ReliefCapability.EQUIPMENT:
            request, *rest = args
            if request.sell_plan is not None:
                request = replace(request, sell_plan=replace(request.sell_plan, request=self.policy.equipment_sell))
            args = (request, *rest)
        elif capability is ReliefCapability.CRAFTING_MATERIAL:
            kwargs['families'] = self.policy.craft_categories
        elif not self.policy.treasure_gold_keys:
            raise ValueError('treasure_relief_disabled')
        return operation(*args, **kwargs)

    def socket_operation(self, operation):
        return _SocketOperation(self, operation)


@dataclass(frozen=True)
class _SocketOperation:
    coordinator: ReliefCoordinator
    operation: object

    def run(self, *args, **kwargs):
        return self.coordinator.handle(ReliefCapability.SOCKET, self.operation.run, *args, **kwargs)


def coordinator_for(dependencies):
    current = getattr(dependencies, 'reliefs', None)
    if current is not None:
        return current
    # Legacy standalone APIs keep their existing application defaults.
    sell = getattr(getattr(dependencies, 'config', None), 'equipment_sell', EquipmentSellPolicy())
    return ReliefCoordinator(replace(ReliefPolicy(), equipment_sell=sell))
