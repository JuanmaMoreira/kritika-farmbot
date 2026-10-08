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
    PROTECTED_GRADES,
)


@dataclass(frozen=True)
class EquipmentSellAuthorization:
    """Caller-owned allowlist; absence or uncertainty always denies.

    ``allowed_types`` accepts all nine established equipment types.  ``allowed_grades`` accepts only grades below
    Ethereal+.  Enhance is an explicit dimension rather than an implicit
    default.  Bulk remains separately opt-in and still requires a fresh
    popup group that proves the same bounded category.
    """

    allowed_types: frozenset[EquipmentType]
    allowed_grades: frozenset[EquipmentGrade]
    allowed_enhance_states: frozenset[bool]
    allowed_bulk_groups: frozenset[EquipmentBulkGroup] = frozenset()
    label: str = "caller"
    require_visual_guards: bool = False

    def __post_init__(self) -> None:
        if type(self.require_visual_guards) is not bool:
            raise ValueError("require_visual_guards must be bool")
        types = frozenset(self.allowed_types)
        grades = frozenset(self.allowed_grades)
        enhance_states = frozenset(self.allowed_enhance_states)
        bulk_groups = frozenset(self.allowed_bulk_groups)
        if not types or not types <= CONFIGURABLE_EQUIPMENT_TYPES:
            raise ValueError(
                "allowed_types must be a non-empty subset of the nine configurable types"
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
        if self.require_visual_guards and (item.sell_available is not True or item.grade_visual is not item.grade):
            return False
        if item.sell_available is False:
            return False
        if item.grade in PROTECTED_GRADES or item.grade is EquipmentGrade.UNKNOWN:
            return False
        if item.equipment_type is EquipmentType.UNKNOWN:
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
        if not confirmation_matches_item(confirmation, item):
            return False
        if item.grade in LOW_BULK_GRADES:
            expected = (
                EquipmentBulkGroup.ENHANCE_GRADE
                if item.enhance
                else EquipmentBulkGroup.EQUIPMENT_GRADE
            )
            return confirmation.group is expected and confirmation.group_type is None
        # Ethereal Enhance is its own configurable family, independently of type.
        if item.grade is EquipmentGrade.ETHEREAL and item.enhance:
            return (confirmation.group is EquipmentBulkGroup.ENHANCE_GRADE
                    and confirmation.group_type is None)
        return (
            item.grade is EquipmentGrade.ETHEREAL
            and not item.enhance
            and confirmation.group is EquipmentBulkGroup.TYPE_GRADE
            and confirmation.group_type is item.equipment_type
        )


DEFAULT_ETHEREAL_SELL_TYPES = frozenset({
    EquipmentType.HELMET, EquipmentType.CHEST, EquipmentType.PANTS,
    EquipmentType.GLOVES, EquipmentType.BOOTS,
})


@dataclass(frozen=True)
class EquipmentSellPolicy:
    """USER_GT policy: low tiers disposable; Ethereal configurable; E+ immutable."""

    ethereal_types: frozenset[EquipmentType] = DEFAULT_ETHEREAL_SELL_TYPES
    ethereal_enhance: bool = False

    def __post_init__(self):
        values = frozenset(self.ethereal_types)
        if not values <= CONFIGURABLE_EQUIPMENT_TYPES:
            raise ValueError("Ethereal types must belong to the nine known types")
        if type(self.ethereal_enhance) is not bool:
            raise ValueError("ethereal_enhance must be bool")
        object.__setattr__(self, "ethereal_types", values)

    def authorize(self, item: EquipmentItemFact | None) -> EquipmentSellAuthorization | None:
        if item is None or not item.confirmed or not item.complete or item.sell_available is not True:
            return None
        if item.grade_visual is not item.grade:
            return None
        if item.grade not in DISPOSABLE_GRADES:
            return None
        if item.grade is EquipmentGrade.ETHEREAL:
            if item.enhance:
                if not self.ethereal_enhance:
                    return None
            elif item.equipment_type not in self.ethereal_types:
                return None
        group = (EquipmentBulkGroup.ENHANCE_GRADE if item.enhance else
                 EquipmentBulkGroup.TYPE_GRADE if item.grade is EquipmentGrade.ETHEREAL else
                 EquipmentBulkGroup.EQUIPMENT_GRADE)
        return EquipmentSellAuthorization(
            frozenset({item.equipment_type}), frozenset({item.grade}),
            frozenset({item.enhance}), frozenset({group}), label="equipment_full_user_gt", require_visual_guards=True,
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
        and (
            confirmation.source_item_sequence == item.sequence
            if confirmation.source_item_sequence is not None
            else _normalize_name(confirmation.item_name) == _normalize_name(item.name)
        )
    )


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


__all__ = (
    "EquipmentSellAuthorization",
    "EquipmentSellPolicy",
    "DEFAULT_ETHEREAL_SELL_TYPES",
    "confirmation_matches_item",
)
