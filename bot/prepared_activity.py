"""Execution bindings for adjacent activities sharing one verified zone visit."""

from dataclasses import dataclass, field
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

    A precheck observes the selected verified entry (including a reused hub). Its result
    is pending evidence when Eligibility is installed. Without it, a terminal
    result may finish at the verified entry without opening a visit. The runner
    consumes it only after eligibility allows execution (or if no check exists).
    NOT_ELIGIBLE discards it; technical eligibility failures take precedence.
    Cancellation still stops immediately. None means no terminal precheck outcome.
    The callable verifies fresh hub entry and its declared final surfaces.
    Session defers the next entry to Navigation; it does not close every visit.
    Reuse depends on a fresh verified hub, not on a business flow name or cached visit.
    """

    name: str
    zone: PreparedZone
    execute: Callable[[], FlowResult]
    precheck: Callable[[], FlowResult | None] | None = None
    # Unlike pending eligibility evidence, entry_readiness may terminate a
    # resource-driven activity at the verified entry without opening the zone.
    # It is only used where no Eligibility owner exists; returns fresh no-work,
    # failure/cancellation, or None to enter. No accounting or cache in runner.
    entry_readiness: Callable[[], FlowResult | None] | None = None
    # Explicit reusable final surfaces; empty preserves the existing hub contract.
    exit_postconditions: tuple[ComponentRequirement, ...] = field(default=(), kw_only=True)
    # Pure owner proof only: no capture/navigation/gameplay/resource consumption.
    # None is unknown/possibly useful. COMPLETED proves no work at this position.
    # Entry readiness and Eligibility are deliberately not called as lookahead.
    routing_no_work: Callable[[], FlowResult | None] | None = field(default=None, kw_only=True)
    scope = FlowScope.PER_CHARACTER

    @property
    def contract(self) -> FlowContract:
        return FlowContract(self.zone.hub_requirement, self.exit_postconditions or (self.zone.hub_requirement,))

    def run(self) -> FlowResult:
        return self.execute()
