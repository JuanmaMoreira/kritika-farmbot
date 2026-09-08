"""Execution bindings for adjacent activities sharing one verified zone visit."""

from dataclasses import dataclass
from typing import Callable, Protocol

from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowContract, FlowResult, FlowScope


class PreparedZone(Protocol):
    entry_requirement: ComponentRequirement
    hub_requirement: ComponentRequirement

    def enter(self) -> FlowResult: ...
    def leave(self) -> FlowResult: ...


@dataclass(frozen=True)
class PreparedActivity:
    """One selected position; no scheduling, resource accounting or gameplay.

    A precheck is observed only before opening a visit, at its entry. Its result
    is pending evidence for this position, not a gate on zone entry. The runner
    consumes it only after eligibility allows execution (or if no check exists).
    NOT_ELIGIBLE discards it; technical eligibility failures take precedence.
    Cancellation still stops immediately. None means no terminal precheck outcome.
    The callable must verify its own fresh hub entry and return to that hub.
    Sharing uses zone object identity, only across consecutive selected positions.
    """

    name: str
    zone: PreparedZone
    execute: Callable[[], FlowResult]
    precheck: Callable[[], FlowResult | None] | None = None
    scope = FlowScope.PER_CHARACTER

    @property
    def contract(self) -> FlowContract:
        return FlowContract(self.zone.hub_requirement, (self.zone.hub_requirement,))

    def run(self) -> FlowResult:
        return self.execute()
