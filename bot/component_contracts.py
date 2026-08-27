"""Declarative state requirements shared by flows and orchestration components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bot.observations import validate_semantic_name


QUICK_MENU_ACCESSIBLE = "quick_menu_accessible"


class RequirementKind(str, Enum):
    EXACT_STATE = "exact_state"
    CAPABILITY = "capability"


@dataclass(frozen=True)
class ComponentRequirement:
    """One exact semantic state or one operational capability."""

    kind: RequirementKind
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RequirementKind):
            raise ValueError("kind must be RequirementKind")
        if self.kind is RequirementKind.EXACT_STATE:
            name = validate_semantic_name(self.name)
        else:
            if not isinstance(self.name, str) or not self.name.strip():
                raise ValueError("capability name must be a non-empty string")
            name = self.name.strip()
            if "." in name:
                raise ValueError("a capability is not a semantic screen name")
        object.__setattr__(self, "name", name)

    @classmethod
    def exact_state(cls, semantic_state: str) -> "ComponentRequirement":
        return cls(RequirementKind.EXACT_STATE, semantic_state)

    @classmethod
    def capability(cls, capability: str) -> "ComponentRequirement":
        return cls(RequirementKind.CAPABILITY, capability)


@dataclass(frozen=True)
class ComponentContract:
    """Precondition and exact states allowed after successful completion."""

    precondition: ComponentRequirement
    successful_postconditions: tuple[ComponentRequirement, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.precondition, ComponentRequirement):
            raise ValueError("precondition must be ComponentRequirement")
        postconditions = tuple(self.successful_postconditions)
        if not postconditions:
            raise ValueError("successful_postconditions must not be empty")
        if any(
            not isinstance(item, ComponentRequirement)
            or item.kind is not RequirementKind.EXACT_STATE
            for item in postconditions
        ):
            raise ValueError("successful_postconditions must be exact states")
        if len(set(postconditions)) != len(postconditions):
            raise ValueError("successful_postconditions must not contain duplicates")
        object.__setattr__(self, "successful_postconditions", postconditions)


QUICK_MENU_ACCESS_REQUIREMENT = ComponentRequirement.capability(
    QUICK_MENU_ACCESSIBLE
)


__all__ = (
    "ComponentContract",
    "ComponentRequirement",
    "QUICK_MENU_ACCESSIBLE",
    "QUICK_MENU_ACCESS_REQUIREMENT",
    "RequirementKind",
)
