"""Explicit caller authorization for irreversible Equipment sales."""

from __future__ import annotations

from dataclasses import dataclass

from bot.equipment_sell_semantics import (
    CONFIGURABLE_EQUIPMENT_TYPES,
    DISPOSABLE_GRADES,
    EquipmentBulkGroup,
    EquipmentGrade,
    EquipmentItemFact,
    EquipmentSellConfirmationFact,
    EquipmentType,
    LOW_BULK_GRADES,
    PROTECTED_ACCESSORY_TYPES,
    PROTECTED_GRADES,
)


@dataclass(frozen=True)
class EquipmentSellAuthorization:
    """Caller-owned allowlist; absence or uncertainty always denies.

    ``allowed_types`` accepts exactly the six established configurable
    non-accessory types.  ``allowed_grades`` accepts only grades below
    Ethereal+.  Enhance is an explicit dimension rather than an implicit
    default.  Bulk remains separately opt-in and still requires a fresh
    popup group that proves the same bounded category.
    """

    allowed_types: frozenset[EquipmentType]
    allowed_grades: frozenset[EquipmentGrade]
    allowed_enhance_states: frozenset[bool]
    allowed_bulk_groups: frozenset[EquipmentBulkGroup] = frozenset()
    label: str = "caller"

    def __post_init__(self) -> None:
        types = frozenset(self.allowed_types)
        grades = frozenset(self.allowed_grades)
        enhance_states = frozenset(self.allowed_enhance_states)
        bulk_groups = frozenset(self.allowed_bulk_groups)
        if not types or not types <= CONFIGURABLE_EQUIPMENT_TYPES:
            raise ValueError(
                "allowed_types must be a non-empty subset of the six configurable types"
            )
        if not grades or not grades <= DISPOSABLE_GRADES:
            raise ValueError("allowed_grades must be a non-empty below-Ethereal+ subset")
        if not enhance_states or any(type(value) is not bool for value in enhance_states):
            raise ValueError("allowed_enhance_states must explicitly contain bool values")
        if (
            not bulk_groups
            or any(type(value) is not EquipmentBulkGroup for value in bulk_groups)
            or EquipmentBulkGroup.UNKNOWN in bulk_groups
        ):
            raise ValueError("allowed_bulk_groups must explicitly contain known groups")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("label must be a non-empty string")
        object.__setattr__(self, "allowed_types", types)
        object.__setattr__(self, "allowed_grades", grades)
        object.__setattr__(self, "allowed_enhance_states", enhance_states)
        object.__setattr__(self, "allowed_bulk_groups", bulk_groups)
        object.__setattr__(self, "label", self.label.strip())

    def allows(self, item: EquipmentItemFact | None) -> bool:
        if not isinstance(item, EquipmentItemFact):
            return False
        if not item.confirmed or not item.complete:
            return False
        if item.grade in PROTECTED_GRADES or item.grade is EquipmentGrade.UNKNOWN:
            return False
        if (
            item.equipment_type in PROTECTED_ACCESSORY_TYPES
            or item.equipment_type is EquipmentType.UNKNOWN
        ):
            return False
        return (
            item.equipment_type in self.allowed_types
            and item.grade in self.allowed_grades
            and item.enhance in self.allowed_enhance_states
        )

    def allows_bulk(
        self,
        item: EquipmentItemFact | None,
        confirmation: EquipmentSellConfirmationFact | None,
    ) -> bool:
        if not self.allows(item):
            return False
        if not isinstance(confirmation, EquipmentSellConfirmationFact):
            return False
        if not confirmation.confirmed or confirmation.group not in self.allowed_bulk_groups:
            return False
        assert item is not None
        if _normalize_name(confirmation.item_name) != _normalize_name(item.name):
            return False
        if item.grade in LOW_BULK_GRADES:
            expected = (
                EquipmentBulkGroup.ENHANCE_GRADE
                if item.enhance
                else EquipmentBulkGroup.EQUIPMENT_GRADE
            )
            return confirmation.group is expected and confirmation.group_type is None
        # Current domain rule: Ethereal bulk is type-scoped.  Candidate types
        # remain restricted to the six non-accessories, and the popup must name
        # that exact type, so accessories cannot be mixed into the group.
        return (
            item.grade is EquipmentGrade.ETHEREAL
            and not item.enhance
            and confirmation.group is EquipmentBulkGroup.TYPE_GRADE
            and confirmation.group_type is item.equipment_type
        )


def confirmation_matches_item(
    confirmation: EquipmentSellConfirmationFact | None,
    item: EquipmentItemFact | None,
) -> bool:
    return (
        isinstance(confirmation, EquipmentSellConfirmationFact)
        and confirmation.confirmed
        and isinstance(item, EquipmentItemFact)
        and item.confirmed
        and _normalize_name(confirmation.item_name) == _normalize_name(item.name)
    )


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


__all__ = (
    "EquipmentSellAuthorization",
    "confirmation_matches_item",
)
