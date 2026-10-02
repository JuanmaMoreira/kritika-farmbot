"""Fresh, context-bound facts for the standalone Craft capability.

Perception reports only current UI semantics.  It does not choose recipes,
navigate, spend currency, or compose inventory relief.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from numbers import Integral, Real
from typing import TypeVar


class CraftFamily(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    ACCESSORY = "accessory"


class CraftTier(str, Enum):
    EXPERT = "expert"
    ARTISAN = "artisan"
    HERO = "hero"
    UNKNOWN = "unknown"


class CraftItemType(str, Enum):
    WEAPON = "weapon"
    HELMET = "helmet"
    CHEST_ARMOR = "chest_armor"
    PANTS = "pants"
    GLOVES = "gloves"
    BOOTS = "boots"
    EARRINGS = "earrings"
    NECKLACE = "necklace"
    RING = "ring"
    UNKNOWN = "unknown"


class CraftCurrency(str, Enum):
    MATERIAL = "material"
    KARATS = "karats"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class QuickMenuCraftFact:
    lobby_label: str
    craft_label: str
    guild_label: str
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        for name in ("lobby_label", "craft_label", "guild_label"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            object.__setattr__(self, name, " ".join(value.split()))
        _validate_common(self)

    @property
    def complete(self) -> bool:
        return (
            self.lobby_label.casefold() == "lobby"
            and self.craft_label.casefold() == "craft"
            and self.guild_label.casefold() == "guild"
            and not self.contradictory
        )

    @property
    def confirmed(self) -> bool:
        return self.complete and _confirmed(self)


@dataclass(frozen=True)
class CraftContextFact:
    """Proven Craft presence plus best-effort family economics.

    Identity answers only "is this physically Craft" via the safe expert
    marker.  Title/rate stay auxiliary/diagnostic (chat/H&H-exposed) and
    every family material/capacity/cost is optional: a missing value never
    disproves Craft, it only blocks the operation that needs it.
    """

    title: str
    rate_label: str
    expert_label: str
    weapon_material: int | None
    armor_material: int | None
    accessory_material: int | None
    weapon_capacity: int | None
    armor_capacity: int | None
    accessory_capacity: int | None
    weapon_hero_cost: int | None
    armor_hero_cost: int | None
    accessory_hero_cost: int | None
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        for name in ("title", "rate_label", "expert_label"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string")
            object.__setattr__(self, name, " ".join(getattr(self, name).split()))
        for name in (
            "weapon_material", "armor_material", "accessory_material",
            "weapon_capacity", "armor_capacity", "accessory_capacity",
            "weapon_hero_cost", "armor_hero_cost", "accessory_hero_cost",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer or None")
        _validate_common(self)

    @property
    def complete(self) -> bool:
        return (
            self.expert_label.casefold() == "expert craft"
            and not self.contradictory
        )

    @property
    def confirmed(self) -> bool:
        return self.complete and _confirmed(self)

    def material_for(self, family: CraftFamily) -> int | None:
        if not isinstance(family, CraftFamily):
            raise ValueError("family must be CraftFamily")
        return {
            CraftFamily.WEAPON: self.weapon_material,
            CraftFamily.ARMOR: self.armor_material,
            CraftFamily.ACCESSORY: self.accessory_material,
        }[family]

    def hero_cost_for(self, family: CraftFamily) -> int | None:
        if not isinstance(family, CraftFamily):
            raise ValueError("family must be CraftFamily")
        return {
            CraftFamily.WEAPON: self.weapon_hero_cost,
            CraftFamily.ARMOR: self.armor_hero_cost,
            CraftFamily.ACCESSORY: self.accessory_hero_cost,
        }[family]


@dataclass(frozen=True)
class CraftRecipeFact:
    family: CraftFamily
    tier: CraftTier
    item_type: CraftItemType
    currency: CraftCurrency
    unit_cost: int
    quantity: int
    quantity_cap: int
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        for name, expected in (
            ("family", CraftFamily), ("tier", CraftTier),
            ("item_type", CraftItemType), ("currency", CraftCurrency),
        ):
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} must be {expected.__name__}")
        for name in ("unit_cost", "quantity", "quantity_cap"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.quantity > self.quantity_cap:
            raise ValueError("quantity cannot exceed quantity_cap")
        _validate_common(self)

    @property
    def complete(self) -> bool:
        return (
            self.tier is not CraftTier.UNKNOWN
            and self.item_type is not CraftItemType.UNKNOWN
            and self.currency is not CraftCurrency.UNKNOWN
            and not self.contradictory
        )

    @property
    def confirmed(self) -> bool:
        return self.complete and _confirmed(self)


@dataclass(frozen=True)
class CraftCurrencyBoundaryFact:
    missing_material: int
    karat_cost: int
    reject_label: str
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        for name in ("missing_material", "karat_cost"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.reject_label, str):
            raise ValueError("reject_label must be a string")
        object.__setattr__(self, "reject_label", " ".join(self.reject_label.split()))
        _validate_common(self)

    @property
    def confirmed(self) -> bool:
        return (
            self.reject_label.casefold() == "no"
            and not self.contradictory
            and _confirmed(self)
        )


@dataclass(frozen=True)
class CraftResultFact:
    marker: str
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.marker, str):
            raise ValueError("marker must be a string")
        object.__setattr__(self, "marker", " ".join(self.marker.split()))
        _validate_common(self)

    @property
    def confirmed(self) -> bool:
        return (
            bool(self.marker)
            and not self.contradictory
            and _confirmed(self)
        )


CraftFactT = TypeVar(
    "CraftFactT",
    QuickMenuCraftFact,
    CraftContextFact,
    CraftRecipeFact,
    CraftCurrencyBoundaryFact,
    CraftResultFact,
)


def consensus_craft_facts(
    samples: tuple[CraftFactT, ...] | list[CraftFactT],
    *,
    required: int = 2,
    max_samples: int = 4,
) -> CraftFactT | None:
    """Return the newest pair of consecutive, agreeing Craft observations."""

    if isinstance(required, bool) or not isinstance(required, Integral) or required < 2:
        raise ValueError("required must be at least two")
    if isinstance(max_samples, bool) or not isinstance(max_samples, Integral) or max_samples < required:
        raise ValueError("max_samples must cover required")
    streak: list[CraftFactT] = []
    for sample in tuple(samples)[: int(max_samples)]:
        if not isinstance(sample, (
            QuickMenuCraftFact, CraftContextFact, CraftRecipeFact,
            CraftCurrencyBoundaryFact, CraftResultFact,
        )):
            raise ValueError("samples contain an unsupported Craft fact")
        if sample.contradictory:
            streak = []
            continue
        if streak and (
            type(sample) is not type(streak[-1])
            or sample.sequence <= streak[-1].sequence
            or _fact_value(sample) != _fact_value(streak[-1])
        ):
            streak = [sample]
        else:
            streak.append(sample)
        if len(streak) >= required:
            return replace(
                sample,
                sample_sequences=tuple(item.sequence for item in streak),
                evidence=tuple(
                    evidence
                    for item in streak
                    for evidence in (item.evidence or (f"sample@{item.sequence}",))
                ),
            )
    return None


def _fact_value(fact) -> tuple[object, ...]:
    if isinstance(fact, QuickMenuCraftFact):
        return (fact.lobby_label.casefold(), fact.craft_label.casefold(), fact.guild_label.casefold())
    if isinstance(fact, CraftContextFact):
        # Consensus tracks identity only: auxiliary title/rate text and
        # best-effort economics must not veto an agreed Craft presence.
        # The merged fact keeps the newest sample's economics.
        return (fact.expert_label.casefold(),)
    if isinstance(fact, CraftRecipeFact):
        return (
            fact.family, fact.tier, fact.item_type, fact.currency,
            fact.unit_cost, fact.quantity, fact.quantity_cap,
        )
    if isinstance(fact, CraftCurrencyBoundaryFact):
        return (fact.missing_material, fact.karat_cost, fact.reject_label.casefold())
    return (fact.marker.casefold(),)


def _validate_common(fact) -> None:
    if isinstance(fact.sequence, bool) or not isinstance(fact.sequence, Integral) or fact.sequence < 0:
        raise ValueError("sequence must be a non-negative integer")
    if isinstance(fact.observed_at, bool) or not isinstance(fact.observed_at, Real):
        raise ValueError("observed_at must be a real number")
    object.__setattr__(fact, "observed_at", float(fact.observed_at))
    sequences = tuple(fact.sample_sequences)
    if any(isinstance(value, bool) or not isinstance(value, Integral) or value < 0 for value in sequences):
        raise ValueError("sample_sequences must contain non-negative integers")
    if any(right <= left for left, right in zip(sequences, sequences[1:])):
        raise ValueError("sample_sequences must be strictly increasing")
    object.__setattr__(fact, "sample_sequences", tuple(int(value) for value in sequences))
    evidence = tuple(fact.evidence)
    if any(not isinstance(value, str) for value in evidence):
        raise ValueError("evidence must contain strings")
    object.__setattr__(fact, "evidence", evidence)
    if not isinstance(fact.contradictory, bool):
        raise ValueError("contradictory must be bool")


def _confirmed(fact) -> bool:
    return len(fact.sample_sequences) >= 2 and fact.sample_sequences[-1] == fact.sequence


__all__ = (
    "CraftContextFact", "CraftCurrency", "CraftCurrencyBoundaryFact",
    "CraftFamily", "CraftItemType", "CraftRecipeFact", "CraftResultFact",
    "CraftTier", "QuickMenuCraftFact", "consensus_craft_facts",
)
