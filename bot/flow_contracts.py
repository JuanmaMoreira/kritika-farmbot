"""Small reusable contracts for composable gameplay flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from bot.component_contracts import ComponentContract
from bot.event_log import record_best_effort
from bot.failure_cause import FailureCause


class FlowScope(str, Enum):
    PER_CHARACTER = "per_character"


class FlowStatus(str, Enum):
    COMPLETED = "completed"
    SKIPPED_NOT_ELIGIBLE = "skipped_not_eligible"
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
    fields: Mapping[str, object] = field(default_factory=dict, kw_only=True)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc), kw_only=True, compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
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
    failure: FailureCause | None = field(default=None, kw_only=True)
    skip_reason: str | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if self.status is FlowStatus.SKIPPED_NOT_ELIGIBLE:
            if not isinstance(self.skip_reason, str) or not self.skip_reason.strip():
                raise ValueError("an eligibility skip requires a reason")
            if self.error is not None or self.failure is not None or self.events:
                raise ValueError("an eligibility skip cannot contain flow outcomes")
        elif self.skip_reason is not None:
            raise ValueError("only an eligibility skip can contain skip_reason")
        if self.error is not None and self.failure is None:
            object.__setattr__(self, "failure", FailureCause.from_error(self.error))
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


def publish_flow_events(sink, flow_name: str, events: tuple[FlowEvent, ...], **context):
    """Runner-owned publication of business outcomes; results retain their data."""
    for event in events:
        name = event.kind if event.kind.startswith(f"{flow_name}.") else f"{flow_name}.{event.kind}"
        record_best_effort(
            sink, name, **{
                **event.fields, **context, "flow": flow_name,
                "detail": event.detail, "event_role": "business",
                "created_at": event.created_at.isoformat(),
            },
        )


__all__ = (
    "FlowContract",
    "FlowEvent",
    "FlowResult",
    "FlowScope",
    "FlowStatus",
    "PerCharacterFlow",
)
