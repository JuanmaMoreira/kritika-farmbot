"""Explicit registry of productive flows shared by every frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from bot.black_market_flow import BlackMarketFlow
from bot.daily_quests_flow import DailyQuestsFlow
from bot.flow_contracts import FlowContract, FlowScope, PerCharacterFlow
from bot.guild_check_in_flow import GuildCheckInFlow
from bot.mailbox_flow import MailboxFlow
from bot.send_stamina_flow import SendStaminaFlow
from bot.summon_pet_daily_flow import SummonPetDailyFlow
from bot.world_boss_flow import WorldBossFlow
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_config import MonsterWaveConfig


class FlowDependencies(Protocol):
    observer: object
    actions: object
    facts: object
    auto_battle: object
    socket_relief: object
    equipment_combine_relief: object
    pet_summon_space_relief: object
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


def _verified_transition_for(dependencies: FlowDependencies):
    """Shared verified transition, portal-aware when the runtime provides it."""

    builder = getattr(dependencies, "build_verified_transition", None)
    if callable(builder):
        return builder()
    from bot.verified_transition import VerifiedTransition

    return VerifiedTransition(
        dependencies.observer, dependencies.actions, dependencies.events
    )


def _scoped_subset_observer(dependencies: FlowDependencies, scope):
    """Shared core for generic scoped perception wiring.

    Returns a scoped observer sharing source/resolver/timing with the
    main observer, or None when scoping is unsupported. Raises
    ``AttributeError``/``TypeError``/``ValueError`` on configuration
    errors so callers can fall back to the main observer. Flow-agnostic:
    it never names flows, waits, timeouts or predicates.
    """

    from bot.perception import select_detectors

    observer = dependencies.observer
    scoped = getattr(observer, "scoped", None)
    perception = getattr(observer, "perception", None)
    if not callable(scoped) or perception is None:
        return None
    return scoped(select_detectors(perception, scope))


def scoped_observer_for(
    dependencies: FlowDependencies,
    main_observer,
    *,
    scope,
    active_event: str,
    unavailable_event: str,
):
    """Generic scoped observer wiring for one wait's detector subset.

    Success records ``active_event`` with the detector count; any
    construction/configuration failure records ``unavailable_event``
    and returns the main observer, preserving current behavior exactly.
    """

    from bot.event_log import record_best_effort

    try:
        scoped_observer = _scoped_subset_observer(dependencies, scope)
        if scoped_observer is None:
            return main_observer
        detector_count = len(scoped_observer.perception.detectors)
    except (AttributeError, TypeError, ValueError) as error:
        record_best_effort(
            dependencies.events,
            unavailable_event,
            error=f"{type(error).__name__}: {error}",
        )
        return main_observer
    record_best_effort(
        dependencies.events,
        active_event,
        detector_count=detector_count,
    )
    return scoped_observer


def scoped_transition_for(
    dependencies: FlowDependencies,
    main_transition,
    *,
    scope,
    active_event: str,
    unavailable_event: str,
):
    """Generic scoped transition wiring for one wait's detector subset.

    It reuses the main transition's actions, events and obstruction
    recovery; only the observer runs the requested detector subset.
    Any wiring failure falls back to the main transition, preserving
    current behavior exactly.
    """

    from bot.event_log import record_best_effort
    from bot.verified_transition import VerifiedTransition

    try:
        scoped_observer = _scoped_subset_observer(dependencies, scope)
        if scoped_observer is None:
            return main_transition
        transition = VerifiedTransition(
            scoped_observer,
            dependencies.actions,
            dependencies.events,
            getattr(main_transition, "obstruction_recovery", None),
        )
        detector_count = len(scoped_observer.perception.detectors)
    except (AttributeError, TypeError, ValueError) as error:
        record_best_effort(
            dependencies.events,
            unavailable_event,
            error=f"{type(error).__name__}: {error}",
        )
        return main_transition
    record_best_effort(
        dependencies.events,
        active_event,
        detector_count=detector_count,
    )
    return transition


def _slot_transition_for(dependencies: FlowDependencies, main_transition):
    """Scoped transition for ``black_market.select_slot`` (generic rehost)."""

    from bot.perception import BLACK_MARKET_SLOT_SCOPE

    return scoped_transition_for(
        dependencies,
        main_transition,
        scope=BLACK_MARKET_SLOT_SCOPE,
        active_event="black_market.slot_scope_active",
        unavailable_event="black_market.slot_scope_unavailable",
    )


def _purchase_transition_for(dependencies: FlowDependencies, main_transition):
    """Scoped transition for ``black_market.accept_purchase`` (generic rehost)."""

    from bot.perception import BLACK_MARKET_PURCHASE_SCOPE

    return scoped_transition_for(
        dependencies,
        main_transition,
        scope=BLACK_MARKET_PURCHASE_SCOPE,
        active_event="black_market.purchase_scope_active",
        unavailable_event="black_market.purchase_scope_unavailable",
    )


def _build_black_market(dependencies: FlowDependencies) -> PerCharacterFlow:
    main_transition = _verified_transition_for(dependencies)
    return BlackMarketFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        verified_transition=main_transition,
        slot_transition=_slot_transition_for(dependencies, main_transition),
        purchase_transition=_purchase_transition_for(
            dependencies, main_transition
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _build_world_boss(dependencies: FlowDependencies) -> PerCharacterFlow:
    return WorldBossFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.facts,
        dependencies.auto_battle,
        dependencies.events,
        socket_relief=dependencies.socket_relief,
        equipment_combine_relief=dependencies.equipment_combine_relief,
        cancel_requested=dependencies.cancel_requested,
        verified_transition=_verified_transition_for(dependencies),
    )


def _build_monster_wave(dependencies: FlowDependencies) -> PerCharacterFlow:
    return MonsterWaveFlow(
        dependencies.observer, dependencies.actions, dependencies.events,
        config=getattr(getattr(dependencies, 'config', None), 'monster_wave', MonsterWaveConfig()),
        facts=dependencies.facts,
        cancel_requested=dependencies.cancel_requested,
        verified_transition=_verified_transition_for(dependencies),
    )


def _daily_claim_observer_for(dependencies: FlowDependencies, main_observer):
    """Scoped observer for the Daily Quests ``ClaimAll`` wait (generic rehost).

    Unlike Black Market, this flow waits on the observer directly instead
    of a ``VerifiedTransition``, so the scope narrows the observer rather
    than a transition. Same fallback contract: any wiring failure returns
    the main observer, preserving today's behavior exactly.
    """

    from bot.perception import DAILY_CLAIM_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=DAILY_CLAIM_SCOPE,
        active_event="daily_quests.claim_scope_active",
        unavailable_event="daily_quests.claim_scope_unavailable",
    )


def _build_daily_quests(dependencies: FlowDependencies) -> PerCharacterFlow:
    return DailyQuestsFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        claim_observer=_daily_claim_observer_for(
            dependencies, dependencies.observer
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _build_summon_pet_daily(dependencies: FlowDependencies) -> PerCharacterFlow:
    return SummonPetDailyFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        dependencies.pet_summon_space_relief,
        cancel_requested=dependencies.cancel_requested,
    )


def _build_send_stamina(dependencies: FlowDependencies) -> PerCharacterFlow:
    return SendStaminaFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        cancel_requested=dependencies.cancel_requested,
    )


def _mailbox_claim_observer_for(dependencies: FlowDependencies, main_observer):
    """Scoped observer for the Mailbox ``ClaimAll`` waits (generic rehost).

    The claim-processing phase (onset + completion/fallback, Caso A) waits
    on the observer directly instead of a ``VerifiedTransition``, so the
    scope narrows the observer rather than a transition. Same fallback
    contract as Daily: any wiring failure returns the main observer,
    preserving today's behavior exactly.
    """

    from bot.perception import MAILBOX_CLAIM_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=MAILBOX_CLAIM_SCOPE,
        active_event="mailbox.claim_scope_active",
        unavailable_event="mailbox.claim_scope_unavailable",
    )


def _build_mailbox(dependencies: FlowDependencies) -> PerCharacterFlow:
    return MailboxFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        claim_observer=_mailbox_claim_observer_for(
            dependencies, dependencies.observer
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _build_guild_check_in(dependencies: FlowDependencies) -> PerCharacterFlow:
    return GuildCheckInFlow(
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
    FlowDefinition('monster_wave', 'Monster Wave', MonsterWaveFlow.scope,
                   MonsterWaveFlow.contract, _build_monster_wave),
    FlowDefinition(
        "send_stamina",
        "Send Stamina",
        SendStaminaFlow.scope,
        SendStaminaFlow.contract,
        _build_send_stamina,
    ),
    FlowDefinition(
        "summon_pet_daily",
        "Summon Pet Daily",
        SummonPetDailyFlow.scope,
        SummonPetDailyFlow.contract,
        _build_summon_pet_daily,
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
    FlowDefinition(
        "guild_check_in",
        "Guild Check-In",
        GuildCheckInFlow.scope,
        GuildCheckInFlow.contract,
        _build_guild_check_in,
    ),
))


__all__ = (
    "DEFAULT_FLOW_REGISTRY",
    "FlowDefinition",
    "FlowDependencies",
    "FlowRegistry",
)
