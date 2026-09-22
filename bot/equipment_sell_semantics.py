"""Fail-closed semantic facts for standalone Equipment selling.

This module contains no navigation, input, relief composition or economic
policy.  Facts describe only what was positively observed on the current
Equipment Inventory surface.  A destructive operation requires consensus
facts built from at least two strictly newer samples.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from numbers import Integral, Real
from typing import TypeVar


class EquipmentType(str, Enum):
    WEAPON = "weapon"
    HELMET = "helmet"
    CHEST = "chest"
    PANTS = "pants"
    GLOVES = "gloves"
    BOOTS = "boots"
    EARRING = "earring"
    NECKLACE = "necklace"
    RING = "ring"
    UNKNOWN = "unknown"


CONFIGURABLE_EQUIPMENT_TYPES = frozenset(
    {
        EquipmentType.WEAPON,
        EquipmentType.HELMET,
        EquipmentType.CHEST,
        EquipmentType.PANTS,
        EquipmentType.GLOVES,
        EquipmentType.BOOTS,
    }
)
PROTECTED_ACCESSORY_TYPES = frozenset(
    {EquipmentType.EARRING, EquipmentType.NECKLACE, EquipmentType.RING}
)


class EquipmentGrade(str, Enum):
    POOR = "poor"
    NORMAL = "normal"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    ETHEREAL = "ethereal"
    ETHEREAL_PLUS = "ethereal+"
    UNKNOWN = "unknown"


DISPOSABLE_GRADES = frozenset(
    {
        EquipmentGrade.POOR,
        EquipmentGrade.NORMAL,
        EquipmentGrade.RARE,
        EquipmentGrade.EPIC,
        EquipmentGrade.LEGENDARY,
        EquipmentGrade.ETHEREAL,
    }
)
PROTECTED_GRADES = frozenset({EquipmentGrade.ETHEREAL_PLUS})

LOW_BULK_GRADES = frozenset(DISPOSABLE_GRADES - {EquipmentGrade.ETHEREAL})


class EquipmentBulkGroup(str, Enum):
    EQUIPMENT_GRADE = "equipment_grade"
    ENHANCE_GRADE = "enhance_grade"
    TYPE_GRADE = "type_grade"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EquipmentInventoryFact:
    item_count: int
    capacity: int
    page: int
    total_pages: int
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        for name in ("item_count", "capacity", "page", "total_pages", "sequence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} must be an integer")
        if self.item_count < 0 or self.capacity <= 0:
            raise ValueError("Item Count values must be non-negative/positive")
        if self.page <= 0 or self.total_pages <= 0 or self.page > self.total_pages:
            raise ValueError("invalid Equipment Inventory page")
        _validate_common_fact(self)

    @property
    def confirmed(self) -> bool:
        return _confirmed(self.sample_sequences, self.sequence) and not self.contradictory


@dataclass(frozen=True)
class EquipmentItemFact:
    name: str
    grade: EquipmentGrade
    equipment_type: EquipmentType
    enhance: bool
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise ValueError("name must be a string")
        object.__setattr__(self, "name", " ".join(self.name.split()))
        if not isinstance(self.grade, EquipmentGrade):
            raise ValueError("grade must be EquipmentGrade")
        if not isinstance(self.equipment_type, EquipmentType):
            raise ValueError("equipment_type must be EquipmentType")
        if not isinstance(self.enhance, bool):
            raise ValueError("enhance must be bool")
        _validate_common_fact(self)

    @property
    def complete(self) -> bool:
        return (
            bool(self.name)
            and self.grade is not EquipmentGrade.UNKNOWN
            and self.equipment_type is not EquipmentType.UNKNOWN
            and not self.contradictory
        )

    @property
    def confirmed(self) -> bool:
        return (
            self.complete
            and _confirmed(self.sample_sequences, self.sequence)
        )


@dataclass(frozen=True)
class EquipmentSellConfirmationFact:
    item_name: str
    group: EquipmentBulkGroup
    group_type: EquipmentType | None
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...] = ()
    evidence: tuple[str, ...] = ()
    contradictory: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.item_name, str):
            raise ValueError("item_name must be a string")
        object.__setattr__(self, "item_name", " ".join(self.item_name.split()))
        if not isinstance(self.group, EquipmentBulkGroup):
            raise ValueError("group must be EquipmentBulkGroup")
        if self.group_type is not None and not isinstance(
            self.group_type, EquipmentType
        ):
            raise ValueError("group_type must be EquipmentType or None")
        _validate_common_fact(self)

    @property
    def complete(self) -> bool:
        if not self.item_name or self.group is EquipmentBulkGroup.UNKNOWN:
            return False
        if self.group is EquipmentBulkGroup.TYPE_GRADE:
            return self.group_type not in (None, EquipmentType.UNKNOWN)
        return self.group_type is None

    @property
    def confirmed(self) -> bool:
        return (
            self.complete
            and not self.contradictory
            and _confirmed(self.sample_sequences, self.sequence)
        )


FactT = TypeVar(
    "FactT", EquipmentInventoryFact, EquipmentItemFact, EquipmentSellConfirmationFact
)


def consensus_facts(
    samples: tuple[FactT, ...] | list[FactT],
    *,
    required: int = 2,
    max_samples: int = 4,
) -> FactT | None:
    """Return the newest agreeing fact after bounded consecutive consensus."""

    items = tuple(samples)
    if isinstance(required, bool) or not isinstance(required, Integral) or required < 2:
        raise ValueError("required must be at least two")
    if (
        isinstance(max_samples, bool)
        or not isinstance(max_samples, Integral)
        or max_samples < required
    ):
        raise ValueError("max_samples must cover required")
    streak: list[FactT] = []
    for sample in items[: int(max_samples)]:
        if not isinstance(
            sample,
            (EquipmentInventoryFact, EquipmentItemFact, EquipmentSellConfirmationFact),
        ):
            raise ValueError("samples contain an unsupported fact")
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


def _fact_value(fact: FactT) -> tuple[object, ...]:
    if isinstance(fact, EquipmentInventoryFact):
        return (fact.item_count, fact.capacity, fact.page, fact.total_pages)
    if isinstance(fact, EquipmentItemFact):
        return (fact.name.casefold(), fact.grade, fact.equipment_type, fact.enhance)
    return (fact.item_name.casefold(), fact.group, fact.group_type)


def _validate_common_fact(fact) -> None:
    if isinstance(fact.sequence, bool) or not isinstance(fact.sequence, Integral):
        raise ValueError("sequence must be an integer")
    if fact.sequence < 0:
        raise ValueError("sequence must be non-negative")
    if isinstance(fact.observed_at, bool) or not isinstance(fact.observed_at, Real):
        raise ValueError("observed_at must be a real number")
    object.__setattr__(fact, "observed_at", float(fact.observed_at))
    sequences = tuple(fact.sample_sequences)
    if any(
        isinstance(value, bool) or not isinstance(value, Integral) or value < 0
        for value in sequences
    ):
        raise ValueError("sample_sequences must contain non-negative integers")
    if any(right <= left for left, right in zip(sequences, sequences[1:])):
        raise ValueError("sample_sequences must be strictly increasing")
    object.__setattr__(fact, "sample_sequences", tuple(int(v) for v in sequences))
    evidence = tuple(fact.evidence)
    if any(not isinstance(value, str) for value in evidence):
        raise ValueError("evidence must contain strings")
    object.__setattr__(fact, "evidence", evidence)
    if not isinstance(fact.contradictory, bool):
        raise ValueError("contradictory must be bool")


def _confirmed(sequences: tuple[int, ...], sequence: int) -> bool:
    return len(sequences) >= 2 and sequences[-1] == sequence


__all__ = (
    "CONFIGURABLE_EQUIPMENT_TYPES",
    "DISPOSABLE_GRADES",
    "EquipmentBulkGroup",
    "EquipmentGrade",
    "EquipmentInventoryFact",
    "EquipmentItemFact",
    "EquipmentSellConfirmationFact",
    "EquipmentType",
    "LOW_BULK_GRADES",
    "PROTECTED_ACCESSORY_TYPES",
    "PROTECTED_GRADES",
    "consensus_facts",
)
