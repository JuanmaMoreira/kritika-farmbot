"""Closed request and quantity policy for one standalone Craft action."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bot.craft_semantics import CraftFamily, CraftTier


class CraftQuantityMode(str, Enum):
    ONE = "one"
    MAX_AVAILABLE = "max_available"


@dataclass(frozen=True)
class CraftRequest:
    family: CraftFamily
    tier: CraftTier = CraftTier.HERO
    quantity_mode: CraftQuantityMode = CraftQuantityMode.ONE

    def __post_init__(self) -> None:
        if not isinstance(self.family, CraftFamily):
            raise ValueError("family must be CraftFamily")
        if not isinstance(self.tier, CraftTier):
            raise ValueError("tier must be CraftTier")
        if not isinstance(self.quantity_mode, CraftQuantityMode):
            raise ValueError("quantity_mode must be CraftQuantityMode")

    @property
    def supported(self) -> bool:
        return self.tier is CraftTier.HERO


def requested_quantity(
    request: CraftRequest,
    *,
    material: int,
    unit_cost: int,
    ui_cap: int,
) -> int | None:
    if not isinstance(request, CraftRequest) or not request.supported:
        return None
    if min(material, unit_cost, ui_cap) < 0 or unit_cost == 0 or ui_cap == 0:
        return None
    available = min(material // unit_cost, ui_cap)
    if available < 1:
        return None
    return 1 if request.quantity_mode is CraftQuantityMode.ONE else available


__all__ = ("CraftQuantityMode", "CraftRequest", "requested_quantity")
