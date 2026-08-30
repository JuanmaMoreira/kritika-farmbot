"""Explicit registry of productive flows shared by every frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from bot.black_market_flow import BlackMarketFlow
from bot.daily_quests_flow import DailyQuestsFlow
from bot.flow_contracts import FlowContract, FlowScope, PerCharacterFlow
from bot.mailbox_flow import MailboxFlow
from bot.world_boss_flow import WorldBossFlow


class FlowDependencies(Protocol):
    observer: object
    actions: object
    facts: object
    auto_battle: object
    socket_relief: object
    equipment_combine_relief: object
    events: object
    cancel_requested: Callable[[], bool]


FlowFactory = Callable[[FlowDependencies], PerCharacterFlow]


@dataclass(frozen=True)
class FlowDefinition:
    id: str
    display_name: str
    scope: FlowScope
    contract: FlowContract
    factory: FlowFactory

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("flow id must be a non-empty string")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must be a non-empty string")
        if not isinstance(self.scope, FlowScope):
            raise ValueError("scope must be FlowScope")
        if not isinstance(self.contract, FlowContract):
            raise ValueError("contract must be FlowContract")
        if not callable(self.factory):
            raise ValueError("factory must be callable")

    def build(self, dependencies: FlowDependencies) -> PerCharacterFlow:
        flow = self.factory(dependencies)
        if flow.name != self.id or flow.scope is not self.scope:
            raise RuntimeError(f"factory for {self.id} returned incompatible flow metadata")
        if flow.contract != self.contract:
            raise RuntimeError(f"factory for {self.id} returned an incompatible contract")
        return flow


class FlowRegistry:
    def __init__(self, definitions: tuple[FlowDefinition, ...]) -> None:
        values = tuple(definitions)
        if not values:
            raise ValueError("definitions must not be empty")
        mapping: dict[str, FlowDefinition] = {}
        for definition in values:
            if not isinstance(definition, FlowDefinition):
                raise ValueError("definitions must contain FlowDefinition values")
            if definition.id in mapping:
                raise ValueError(f"duplicate flow id: {definition.id}")
            mapping[definition.id] = definition
        self._definitions = values
        self._mapping = mapping

    @property
    def definitions(self) -> tuple[FlowDefinition, ...]:
        return self._definitions

    def get(self, flow_id: str) -> FlowDefinition:
        try:
            return self._mapping[flow_id]
        except KeyError as error:
            available = ", ".join(self._mapping)
            raise KeyError(f"unknown flow '{flow_id}'; available: {available}") from error

    def select(self, flow_ids: tuple[str, ...] | list[str]) -> tuple[FlowDefinition, ...]:
        values = tuple(flow_ids)
        if not values:
            raise ValueError("at least one flow id is required")
        return tuple(self.get(flow_id) for flow_id in values)


def _build_black_market(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.verified_transition import VerifiedTransition

    return BlackMarketFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        verified_transition=VerifiedTransition(
            dependencies.observer, dependencies.actions, dependencies.events
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _build_world_boss(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.verified_transition import VerifiedTransition

    return WorldBossFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.facts,
        dependencies.auto_battle,
        dependencies.events,
        socket_relief=dependencies.socket_relief,
        equipment_combine_relief=dependencies.equipment_combine_relief,
        cancel_requested=dependencies.cancel_requested,
        verified_transition=VerifiedTransition(
            dependencies.observer, dependencies.actions, dependencies.events
        ),
    )


def _build_daily_quests(dependencies: FlowDependencies) -> PerCharacterFlow:
    return DailyQuestsFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        cancel_requested=dependencies.cancel_requested,
    )


def _build_mailbox(dependencies: FlowDependencies) -> PerCharacterFlow:
    return MailboxFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        cancel_requested=dependencies.cancel_requested,
    )


DEFAULT_FLOW_REGISTRY = FlowRegistry((
    FlowDefinition(
        "black_market",
        "Black Market",
        BlackMarketFlow.scope,
        BlackMarketFlow.contract,
        _build_black_market,
    ),
    FlowDefinition(
        "world_boss",
        "World Boss",
        WorldBossFlow.scope,
        WorldBossFlow.contract,
        _build_world_boss,
    ),
    FlowDefinition(
        "daily_quests",
        "Daily Quests",
        DailyQuestsFlow.scope,
        DailyQuestsFlow.contract,
        _build_daily_quests,
    ),
    FlowDefinition(
        "mailbox",
        "Mailbox",
        MailboxFlow.scope,
        MailboxFlow.contract,
        _build_mailbox,
    ),
))


__all__ = (
    "DEFAULT_FLOW_REGISTRY",
    "FlowDefinition",
    "FlowDependencies",
    "FlowRegistry",
)
