"""Small reusable contracts for composable gameplay flows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from bot.component_contracts import ComponentContract


class FlowScope(str, Enum):
    PER_CHARACTER = "per_character"


class FlowStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class FlowContract(ComponentContract):
    """Explicit precondition and allowed successful semantic states."""


@dataclass(frozen=True)
class FlowEvent:
    """Business event produced by a flow without controlling session policy."""

    kind: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("kind must be a non-empty string")
        object.__setattr__(self, "kind", self.kind.strip())
        if self.detail is not None:
            if not isinstance(self.detail, str) or not self.detail.strip():
                raise ValueError("detail must be None or a non-empty string")
            object.__setattr__(self, "detail", self.detail.strip())


@dataclass(frozen=True)
class FlowResult:
    """Technical status plus zero or more non-fatal business events."""

    status: FlowStatus
    events: tuple[FlowEvent, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        if not isinstance(self.status, FlowStatus):
            raise ValueError("status must be FlowStatus")
        if any(not isinstance(event, FlowEvent) for event in self.events):
            raise ValueError("events must contain only FlowEvent values")
        if self.error is not None and (
            not isinstance(self.error, str) or not self.error.strip()
        ):
            raise ValueError("error must be None or a non-empty string")
        if self.status is FlowStatus.COMPLETED and self.error is not None:
            raise ValueError("a completed flow cannot contain an error")

    @property
    def succeeded(self) -> bool:
        return self.status is FlowStatus.COMPLETED

    def event_count(self, kind: str) -> int:
        return sum(event.kind == kind for event in self.events)


@runtime_checkable
class PerCharacterFlow(Protocol):
    name: str
    scope: FlowScope
    contract: FlowContract

    def run(self) -> FlowResult: ...


__all__ = (
    "FlowContract",
    "FlowEvent",
    "FlowResult",
    "FlowScope",
    "FlowStatus",
    "PerCharacterFlow",
)
