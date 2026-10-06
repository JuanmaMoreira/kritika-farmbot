"""Explicit registry of productive flows shared by every frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from bot.stages_daily_flow import StagesDailyFlow
from bot.gold_farming_flow import GoldFarmingFlow
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
from bot.relief_policy import coordinator_for


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
    controlled_unavailable_events: frozenset[str] = frozenset()

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
        if not isinstance(self.controlled_unavailable_events, frozenset) or any(
            not isinstance(event, str) or not event.strip() for event in self.controlled_unavailable_events
        ):
            raise ValueError("controlled_unavailable_events must be a frozenset of event names")

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


def _open_transition_for(dependencies: FlowDependencies, main_transition):
    """Scoped transition for ``black_market.open`` (generic rehost)."""

    from bot.perception import BLACK_MARKET_OPEN_SCOPE

    return scoped_transition_for(
        dependencies,
        main_transition,
        scope=BLACK_MARKET_OPEN_SCOPE,
        active_event="black_market.open_scope_active",
        unavailable_event="black_market.open_scope_unavailable",
    )


def _build_black_market(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.perception import BLACK_MARKET_TO_LOBBY_SCOPE

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
        open_transition=_open_transition_for(dependencies, main_transition),
        close_transition=scoped_transition_for(
            dependencies,
            main_transition,
            scope=BLACK_MARKET_TO_LOBBY_SCOPE,
            active_event="black_market.lobby_return_scope_active",
            unavailable_event="black_market.lobby_return_scope_unavailable",
        ),
        confirmation_observer=_black_market_confirmation_observer_for(
            dependencies, dependencies.observer
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _black_market_confirmation_observer_for(
    dependencies: FlowDependencies, main_observer
):
    """Scoped observer for the Black Market empty-gold confirmation wait.

    The post-open read (clean Black Market plus GOLD facts, Caso read)
    shares the open navigation detector set: the base landmark, the three
    purchase-branch popups of its abort predicate and the GOLD/Purchased
    facts. Same fallback contract as every other scope: any wiring
    failure returns the main observer, preserving today's behavior
    exactly.
    """

    from bot.perception import BLACK_MARKET_OPEN_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=BLACK_MARKET_OPEN_SCOPE,
        active_event="black_market.gold_confirmation_scope_active",
        unavailable_event="black_market.gold_confirmation_scope_unavailable",
    )


def _build_world_boss(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.perception import QUICK_MENU_TO_LOBBY_SCOPE
    from bot.action_executor import ActionExecutor
    from bot.equipment_sell_reader import EquipmentSellReader
    from bot.equipment_sell_runtime import EquipmentSellRuntime

    source = getattr(dependencies.observer, "source", None)
    engine = getattr(dependencies, "ocr_engine", None)
    equipment_sell = None
    if (callable(getattr(source, "get_frame", None))
            and callable(getattr(engine, "recognize", None))
            and isinstance(dependencies.actions, ActionExecutor)):
        equipment_sell = EquipmentSellRuntime(source, EquipmentSellReader(engine), dependencies.actions,
            events=dependencies.events, cancel_requested=dependencies.cancel_requested, sample_timeout=6.0)

    main_transition = _verified_transition_for(dependencies)
    return WorldBossFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.facts,
        dependencies.auto_battle,
        dependencies.events,
        socket_relief=coordinator_for(dependencies).socket_operation(dependencies.socket_relief),
        equipment_combine_relief=dependencies.equipment_combine_relief,
        equipment_sell=equipment_sell,
        equipment_sell_policy=coordinator_for(dependencies).policy.equipment_sell,
        cancel_requested=dependencies.cancel_requested,
        verified_transition=main_transition,
        lobby_transition=scoped_transition_for(
            dependencies,
            main_transition,
            scope=QUICK_MENU_TO_LOBBY_SCOPE,
            active_event="battle_mode.lobby_return_scope_active",
            unavailable_event="battle_mode.lobby_return_scope_unavailable",
        ),
    )


def _build_monster_wave(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.perception import QUICK_MENU_TO_LOBBY_SCOPE

    main_transition = _verified_transition_for(dependencies)

    def _bare():
        return MonsterWaveFlow(
            dependencies.observer, dependencies.actions, dependencies.events,
            config=getattr(getattr(dependencies, 'config', None), 'monster_wave', MonsterWaveConfig()),
            facts=dependencies.facts,
            cancel_requested=dependencies.cancel_requested,
            verified_transition=main_transition,
            lobby_transition=scoped_transition_for(
                dependencies,
                main_transition,
                scope=QUICK_MENU_TO_LOBBY_SCOPE,
                active_event="battle_mode.lobby_return_scope_active",
                unavailable_event="battle_mode.lobby_return_scope_unavailable",
            ),
        )

    try:
        return _build_productive_monster_wave(dependencies, main_transition, _bare)
    except (AttributeError, TypeError, ValueError):
        return _bare()


def _build_productive_monster_wave(dependencies, main_transition, bare_factory):
    """L1 composition root: consume one RESOURCE_BOARD_PENDING productively.

    Reuses A1 acquisition, I2 planner, J/K core, CraftRuntime+C1, Keys
    runtime+C2b lazy budget, Materials runtime, Treasure runtime and
    ActionExecutor intents/readers. Only thin adapters below connect the
    existing owners; no direct ADB here. Any wiring failure falls back
    to the bare flow, preserving today's behavior exactly.
    """

    from bot.action_executor import ActionExecutor
    from bot.craft_reader import CraftReader
    from bot.craft_runtime import CraftRuntime
    from bot.equipment_sell_reader import EquipmentSellReader
    from bot.equipment_sell_runtime import EquipmentSellRuntime
    from bot.equipment_relief import EquipmentReliefComposer
    from bot.monster_wave_board_reader import MonsterWaveBoardReader
    from bot.monster_wave_productive import ProductiveMonsterWaveFlow
    from bot.monster_wave_resource_route import (
        MonsterWavePrerequisiteNavigationRuntime,
        MonsterWaveResourceRouteRuntime,
        MonsterWaveSnapshotRuntime,
    )
    from bot.monster_wave_standalone import MonsterWaveStandaloneNavigationRuntime
    from bot.monster_wave_standalone import MonsterWaveBoardAcquisitionRuntime
    from bot.ocr import RapidOcrEngine
    from bot.quick_menu_trading import QuickMenuTradingRuntime
    from bot.resource_route_planner import NonBoardResourceFacts, plan_resource_route
    from bot.trading_materials_runtime import TradingMaterialsRuntime
    from bot.trading_runtime import TradingRuntime
    from bot.treasure_runtime import TreasureRuntime
    from bot.keys_promotion_runtime import KeysPromotionRuntime
    from bot.perception import (
        MONSTER_WAVE_BOARD_ACQUISITION_SCOPE, build_trading_navigation_perception,
    )
    from bot.trading_key_facts_reader import (
        execute_productive_key_trade, read_fresh_key_facts,
    )
    from bot.trading_panel_reader import TradingPanelReader
    from bot.trading_row_facts import TradingRowReader
    from bot.verified_transition import VerifiedTransition

    observer = dependencies.observer
    actions = dependencies.actions
    events = dependencies.events
    cancel_requested = dependencies.cancel_requested
    if not callable(getattr(observer, "observe", None)) or not callable(
        getattr(observer, "wait_until", None)
    ):
        raise ValueError("observer must provide observe() and wait_until()")
    if not isinstance(actions, ActionExecutor):
        raise ValueError("actions must be an ActionExecutor")
    if not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")

    inner = bare_factory()
    # Repeated bindings share the runtime recognition backend, not reader state.
    engine = getattr(dependencies,"ocr_engine",None) or RapidOcrEngine()
    # Warm the OCR backend outside the acquisition window: A1 keeps the
    # 1.0 s spacing / 2.0 s final age / 3.0 s waits unchanged, and a cold
    # first board read (≈2 s) would otherwise exhaust the final age.
    try:
        import numpy as _np

        _warm = _np.zeros((32, 128, 3), dtype=_np.uint8)
        engine.recognize(_warm)
    except Exception:
        pass

    # A1 acquisition: two fresh frames after the pending barrier, no input.
    board_observer = scoped_observer_for(
        dependencies, observer,
        scope=MONSTER_WAVE_BOARD_ACQUISITION_SCOPE,
        active_event="monster_wave.board_acquisition_scope_active",
        unavailable_event="monster_wave.board_acquisition_scope_unavailable",
    )
    from bot.runtime_observer import RuntimeObserver
    from bot.monster_wave_board_perception import MonsterWaveBoardPerception
    if isinstance(board_observer, RuntimeObserver):
        board_observer = board_observer.scoped(MonsterWaveBoardPerception(board_observer.perception))
    boards = MonsterWaveBoardAcquisitionRuntime(
        board_observer, MonsterWaveBoardReader(engine),
        cancel_requested=cancel_requested,
    )
    snapshots = MonsterWaveSnapshotRuntime(
        observer, cancel_requested=cancel_requested,
    )
    standalone_navigation = MonsterWaveStandaloneNavigationRuntime(
        main_transition, snapshots, cancel_requested=cancel_requested,
    )

    # Craft standalone + C1 probe, owned by CraftRuntime.
    source = getattr(observer, "source", None)
    if not callable(getattr(source, "get_frame", None)):
        raise ValueError("observer source must provide get_frame()")
    craft_runtime = CraftRuntime(
        source, EquipmentSellReader(engine), CraftReader(engine), actions,
        cancel_requested=cancel_requested, events=events,
    )
    def _continue_mw_from_craft_lobby():
        from bot.flow_contracts import FlowStatus
        entered = inner.zone.enter()
        if entered.status is not FlowStatus.COMPLETED:
            return entered
        return inner.activity.reenter()

    prereq_navigation = MonsterWavePrerequisiteNavigationRuntime(
        observer, main_transition, craft_runtime,
        resume_mw_from_lobby=_continue_mw_from_craft_lobby,
        cancel_requested=cancel_requested,
    )

    # Trading / Treasure navigation owners (no policy).
    # The default observer stays on the MW hot path. During this bounded
    # Trading visit, the same source/resolver also sees active tabs and rows.
    from bot.perception import (
        TradingTabsDetector, TradingRowsDetector, TreasureContentDetector,
        PerceptionEngine, select_detectors,
    )
    from bot.perception.scope import ScopeSpec

    # Preserve the complete resolver vocabulary and MW caller signals while
    # excluding unrelated slot/candidate/animation readers measured on this
    # Trading hot path. Tabs and rows remain mandatory on every snapshot.
    trading_scope = ScopeSpec(
        name="monster_wave_trading",
        spec_names=MONSTER_WAVE_BOARD_ACQUISITION_SCOPE.spec_names,
        specialized_types=MONSTER_WAVE_BOARD_ACQUISITION_SCOPE.specialized_types
        + (TradingTabsDetector, TradingRowsDetector),
    )
    trading_observer = observer.scoped(select_detectors(
        build_trading_navigation_perception(), trading_scope))
    trading_transition = VerifiedTransition(
        trading_observer, actions, events,
        getattr(main_transition, "obstruction_recovery", None),
    )
    trading_runtime = TradingRuntime(
        trading_observer, trading_transition,
        cancel_requested=cancel_requested,
    )
    # Default perception carries Treasure chrome only. Gold/Karat evidence
    # belongs to this bounded visit, including its initial economic open.
    treasure_content = TreasureContentDetector()
    treasure_scope = ScopeSpec(
        name="monster_wave_treasure",
        spec_names=MONSTER_WAVE_BOARD_ACQUISITION_SCOPE.spec_names,
        specialized_types=MONSTER_WAVE_BOARD_ACQUISITION_SCOPE.specialized_types
        + (TreasureContentDetector,),
    )
    treasure_observer = observer.scoped(select_detectors(
        PerceptionEngine((*observer.perception.detectors, treasure_content)),
        treasure_scope,
    ))
    treasure_transition = VerifiedTransition(
        treasure_observer, actions, events,
        getattr(main_transition, "obstruction_recovery", None),
    )
    treasure_runtime = TreasureRuntime(
        treasure_observer, treasure_transition, cancel_requested=cancel_requested,
    )
    quick_menu_runtime = QuickMenuTradingRuntime(
        observer, main_transition, cancel_requested=cancel_requested,
    )

    # Keys uses the established Trading row/panel readers and C4 executor.
    key_row_reader = TradingRowReader(engine)
    key_panel_reader = TradingPanelReader(trading_observer, engine)

    def _read_key_facts(barrier):
        return read_fresh_key_facts(
            trading_observer, key_row_reader, after_sequence=barrier,
            cancel_requested=cancel_requested, events=events,
        )

    def _execute_key_trade(*, operation, snapshot, row_fact, quantity):
        return execute_productive_key_trade(
            operation=operation, snapshot=snapshot, row_fact=row_fact,
            quantity=quantity, observer=trading_observer, actions=actions,
            panel_reader=key_panel_reader, read_facts=_read_key_facts,
            cancel_requested=cancel_requested, events=events,
        )

    def _drain_gold_keys():
        # Called only after C6b's verified initial Gold open. Keep the existing
        # local Gold/Karat contract, immutable premium latch and finalizer.
        from time import monotonic
        from bot.tap_through_animation import TapThroughAnimation
        from bot.treasure_fast_drain import drain_gold_keys_fast
        from bot.event_log import record_best_effort
        scoped = treasure_observer
        latest = None
        cursor = 0
        dispatched_at = 0.0

        def observe_fresh():
            nonlocal latest, cursor
            latest = scoped.wait_until(
                lambda item: item.timestamp >= dispatched_at
                and 0 <= monotonic() - item.timestamp <= 2.0,
                after_sequence=cursor, timeout=6.0,
                cancel_requested=cancel_requested,
            )
            cursor = latest.sequence
            return latest

        def act(intent):
            nonlocal dispatched_at
            if latest is None or not 0 <= monotonic()-latest.timestamp <= 2.0:
                raise ValueError("gold_drain_dispatch_frame_stale")
            actions.execute(intent, latest.geometry, events=events,
                            source_sequence=latest.sequence)
            dispatched_at = monotonic()

        initial = observe_fresh()
        result = drain_gold_keys_fast(
            initial_snapshot=initial, observe=observe_fresh, tap=None, act=act,
            initial_open_verified=True, allow_karat_entry=True,
            measure_local=treasure_content.measure,
            tap_through=TapThroughAnimation(scoped, actions, events),
            cancel_requested=cancel_requested,
        )
        record_best_effort(events, "trading.gold_drain.result",
                          outcome=result.outcome.value, reason=result.reason,
                          inputs=result.inputs_emitted, dismiss_inputs=result.dismiss_inputs,
                          karat_boundary_seen=result.karat_boundary_seen,
                          elapsed_seconds=result.elapsed_s)
        return result

    def _acknowledge_gold_full(pending):
        from time import monotonic
        from bot.keys_promotion_runtime import acknowledge_gold_full_boundary
        from bot.event_log import record_best_effort
        latest = None
        dispatched_at = 0.0

        def read_panel():
            nonlocal latest
            found = None
            def ready(item):
                nonlocal found
                found = key_panel_reader.read_snapshot(item, after_sequence=pending.before_fact.sequence)
                return found is not None and found.shows_output_full
            latest = trading_observer.wait_until(
                ready, after_sequence=pending.before_fact.sequence, timeout=6.0,
                cancel_requested=cancel_requested,
            )
            return found

        def act(intent):
            nonlocal dispatched_at
            actions.execute(intent, latest.geometry, events=events,
                            source_sequence=latest.sequence)
            dispatched_at = monotonic()

        def read_keys_context(*, after_sequence):
            # Both complete numeric rows are required again; tabs behind the
            # alert alone cannot prove its dismissal.
            facts = _read_key_facts(after_sequence)
            if facts is None or facts.snapshot.timestamp < dispatched_at:
                return None
            return facts.snapshot

        result = acknowledge_gold_full_boundary(
            pending, read_panel=read_panel, act=act,
            read_keys_context=read_keys_context, cancel_requested=cancel_requested,
        )
        record_best_effort(events, "trading.gold_full.ack.result",
                          status=result.status.value, error=result.error,
                          sequence=getattr(result.final_snapshot,"sequence",None))
        return result

    keys_runtime = KeysPromotionRuntime(
        trading_runtime, treasure_runtime, quick_menu_runtime,
        read_key_facts=_read_key_facts,
        execute_key_trade=_execute_key_trade,
        drain_gold_keys=_drain_gold_keys,
        acknowledge_gold_full=_acknowledge_gold_full,
        reliefs=coordinator_for(dependencies),
        cancel_requested=cancel_requested,
    )

    from bot.trading_materials_productive import ProductiveMaterialsAdapter
    material_adapter = ProductiveMaterialsAdapter(
        trading_observer, actions, key_row_reader, key_panel_reader,
        cancel_requested=cancel_requested, events=events,
    )
    materials_runtime = TradingMaterialsRuntime(
        trading_runtime, locate_material=material_adapter.locate,
        read_material_fact=material_adapter.read,
        execute_material_trade=material_adapter.trade,
        cancel_requested=cancel_requested,
    )

    # J core: one immutable plan, once, no replan. Lazy Keys budget
    # (None) derives from FreshKeyFacts via make_budget when needed.
    # Equipment USER_GT supplies explicit per-type policy to the inventory owner.
    from bot.flow_contracts import FlowStatus
    from bot.equipment_sell_policy import EquipmentSellPolicy
    from bot.equipment_relief import EquipmentReliefSellPlan
    from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, SCREEN_LOBBY
    from bot.state import ResolutionStatus
    from bot.semantic_actions import (OpenEquipmentInventoryFromFull,
                                     SelectQuickMenuInventory, ExitEquipmentInventory)
    from bot.craft_runtime import CraftRouteOutcome
    from bot.craft_semantics import consensus_craft_facts
    from bot.monster_wave_activity import clean_mw
    from bot.monster_wave_resource_route import FreshMonsterWaveSnapshot
    inventory_runtime = EquipmentSellRuntime(
        source, EquipmentSellReader(engine), actions,
        cancel_requested=cancel_requested, events=events, sample_timeout=6.0,
    )
    equipment_relief = EquipmentReliefComposer(
        dependencies.equipment_combine_relief, inventory_runtime,
        reliefs=coordinator_for(dependencies),
    )
    policy = coordinator_for(dependencies).policy.equipment_sell

    def _enter_equipment_inventory(caller):
        before = observer.observe()
        if (before.state.status is not ResolutionStatus.AMBIGUOUS and
            set(before.state.overlays) == {POPUP_EQUIPMENT_INVENTORY_FULL}):
            actions.execute(OpenEquipmentInventoryFromFull(), before.geometry,
                            events=events, source_sequence=before.sequence)
        elif caller == "monster_wave":
            if not clean_mw(before):
                raise ValueError("inventory_relief_caller_not_mw")
            anchor = snapshots.acquire(after_sequence=before.sequence)
            if anchor.status is not FlowStatus.COMPLETED or anchor.fresh is None:
                raise ValueError("inventory_relief_mw_context_not_fresh")
            transitions, handoff, failed = prereq_navigation._open_mw_menu(anchor.fresh)
            if failed is not None or handoff is None:
                raise ValueError("inventory_relief_mw_menu_unverified")
            opened = transitions[-1].final_snapshot
            actions.execute(SelectQuickMenuInventory(), opened.geometry,
                            events=events, source_sequence=opened.sequence)
            handoff.invalidate()
        else:
            opened = craft_runtime.open_quick_menu_or_handoff()
            if opened.outcome is not CraftRouteOutcome.QUICK_MENU_OPEN:
                raise ValueError("inventory_relief_craft_menu_unverified")
            craft_runtime.sleeper(.35)
            ready = craft_runtime._read_consensus(
                craft_runtime.craft_reader, "quick_menu_sample",
                after_sequence=opened.quick_menu_fact.sequence,
                consensus=consensus_craft_facts,
            )
            if ready is None or not craft_runtime._fresh(ready):
                raise ValueError("inventory_relief_craft_menu_not_ready")
            craft_runtime._tap(SelectQuickMenuInventory())
        inventory_runtime._after_sequence = before.sequence
        inventory_runtime._not_before = inventory_runtime.clock()

    def _return_equipment_to_mw(result):
        inventory_runtime._tap(ExitEquipmentInventory())
        def returned(s):
            return (clean_mw(s) or (s.state.status is ResolutionStatus.RESOLVED
                    and s.state.base_context == SCREEN_LOBBY and not s.state.overlays))
        restored = observer.wait_until(
            returned, after_sequence=result.after.sequence, timeout=8, stable_for=.25,
            cancel_requested=cancel_requested,
        )
        if restored.state.base_context == SCREEN_LOBBY:
            resumed = _continue_mw_from_craft_lobby()
            if resumed.status is not FlowStatus.COMPLETED:
                raise ValueError("inventory_mw_normal_navigation_failed")
            restored = observer.wait_until(clean_mw, after_sequence=restored.sequence,
                                           timeout=8, stable_for=.25,
                                           cancel_requested=cancel_requested)
        return restored.sequence

    def _return_equipment_to_craft(result):
        inventory_runtime._tap(ExitEquipmentInventory())
        restored = craft_runtime.observe_context(after_sequence=result.after.sequence)
        if restored.outcome is not CraftRouteOutcome.ENTERED or restored.craft_fact is None:
            raise ValueError("inventory_craft_return_unverified")
        craft_runtime.note_inventory_return()
        return restored.craft_fact.sequence

    mw_sell_plan = EquipmentReliefSellPlan(
        policy, lambda _: _enter_equipment_inventory("monster_wave"), _return_equipment_to_mw)
    craft_sell_plan = EquipmentReliefSellPlan(
        policy, lambda _: _enter_equipment_inventory("craft"), _return_equipment_to_craft)
    route = MonsterWaveResourceRouteRuntime(
        prereq_navigation, snapshots, craft_runtime, keys_runtime,
        materials_runtime, keys_budget_remaining=None,
        equipment_relief=equipment_relief, equipment_sell_plan=craft_sell_plan,
        reliefs=coordinator_for(dependencies),
        cancel_requested=cancel_requested,
    )

    return ProductiveMonsterWaveFlow(
        inner, boards=boards, navigation=standalone_navigation, route=route,
        planner=plan_resource_route, non_board=NonBoardResourceFacts(),
        equipment_relief=equipment_relief, equipment_sell_plan=mw_sell_plan,
        socket_relief=coordinator_for(dependencies).socket_operation(dependencies.socket_relief),
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


def _daily_open_observer_for(dependencies: FlowDependencies, main_observer):
    """Scoped observer for the Daily Quests ``OpenQuests`` wait.

    The readiness expected predicate (chrome plus rows-populated without
    loading) and the claim/progress carry the post-wait snapshot must keep
    all run on this scope. Same fallback contract as the claim scope: any
    wiring failure returns the main observer, preserving today's behavior
    exactly.
    """

    from bot.perception import DAILY_OPEN_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=DAILY_OPEN_SCOPE,
        active_event="daily_quests.open_scope_active",
        unavailable_event="daily_quests.open_scope_unavailable",
    )


def _build_daily_quests(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.perception import DAILY_TO_LOBBY_SCOPE

    return DailyQuestsFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        claim_observer=_daily_claim_observer_for(
            dependencies, dependencies.observer
        ),
        open_observer=_daily_open_observer_for(
            dependencies, dependencies.observer
        ),
        lobby_observer=scoped_observer_for(
            dependencies,
            dependencies.observer,
            scope=DAILY_TO_LOBBY_SCOPE,
            active_event="daily_quests.lobby_return_scope_active",
            unavailable_event="daily_quests.lobby_return_scope_unavailable",
        ),
        verified_transition=_verified_transition_for(dependencies),
        cancel_requested=dependencies.cancel_requested,
    )


def _build_summon_pet_daily(dependencies: FlowDependencies) -> PerCharacterFlow:
    return SummonPetDailyFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        dependencies.pet_summon_space_relief,
        summon_observer=_summon_pet_observer_for(
            dependencies, dependencies.observer
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _summon_pet_observer_for(
    dependencies: FlowDependencies, main_observer
):
    """Scoped observer for the Summon Pet Daily normal-path waits.

    Navigation (Manage/Summon/Combine), the summon outcome and every
    dismissal share one pets-family detector set: the shell package all
    three bases require, the Manage/Summon/Combine landmarks, the
    Daily/Premium indicators, the Epic availability states, the selectors
    the outcome wait stays passive on, the Result landmarks, both outcome
    popups and the Quick Menu tile. The initial Manage observe stays
    global (discovery); the relief keeps its own observer. Same fallback
    contract as every other scope: any wiring failure returns the main
    observer, preserving today's behavior exactly.
    """

    from bot.perception import PET_SUMMON_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=PET_SUMMON_SCOPE,
        active_event="summon_pet_daily.summon_scope_active",
        unavailable_event="summon_pet_daily.summon_scope_unavailable",
    )


def _send_stamina_completion_observer_for(dependencies: FlowDependencies, main_observer):
    """Scoped observer for the Send Stamina completion waits.

    Both post-tap waits (completion + daily-active fallback, Caso A) run on
    the observer directly instead of a ``VerifiedTransition``, so the scope
    narrows the observer rather than a transition. Same fallback contract
    as Daily/Mailbox/Guild: any wiring failure returns the main observer,
    preserving today's behavior exactly. The initial ``observe()``
    (precondition/no-op check) and navigation stay global; the final Lobby
    wait uses its separate resolver-complete scope.
    """

    from bot.perception import SEND_STAMINA_COMPLETION_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=SEND_STAMINA_COMPLETION_SCOPE,
        active_event="send_stamina.completion_scope_active",
        unavailable_event="send_stamina.completion_scope_unavailable",
    )


def _build_send_stamina(dependencies: FlowDependencies) -> PerCharacterFlow:
    from bot.perception import FRIENDS_TO_LOBBY_SCOPE

    return SendStaminaFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        completion_observer=_send_stamina_completion_observer_for(
            dependencies, dependencies.observer
        ),
        lobby_observer=scoped_observer_for(
            dependencies,
            dependencies.observer,
            scope=FRIENDS_TO_LOBBY_SCOPE,
            active_event="send_stamina.lobby_return_scope_active",
            unavailable_event="send_stamina.lobby_return_scope_unavailable",
        ),
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
    from bot.perception import MAILBOX_TO_LOBBY_SCOPE

    return MailboxFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        claim_observer=_mailbox_claim_observer_for(
            dependencies, dependencies.observer
        ),
        lobby_observer=scoped_observer_for(
            dependencies,
            dependencies.observer,
            scope=MAILBOX_TO_LOBBY_SCOPE,
            active_event="mailbox.lobby_return_scope_active",
            unavailable_event="mailbox.lobby_return_scope_unavailable",
        ),
        verified_transition=_verified_transition_for(dependencies),
        cancel_requested=dependencies.cancel_requested,
    )


def _guild_attendance_observer_for(dependencies: FlowDependencies, main_observer):
    """Scoped observer for the Guild Attendance completion wait.

    The post-tap completion wait runs on the observer directly instead of
    a ``VerifiedTransition``, so the scope narrows the observer rather
    than a transition. Same fallback contract as Daily/Mailbox: any wiring
    failure returns the main observer, preserving today's behavior exactly.
    The initial ``observe()`` (precondition/no-op check) stays global.
    """

    from bot.perception import GUILD_ATTENDANCE_SCOPE

    return scoped_observer_for(
        dependencies,
        main_observer,
        scope=GUILD_ATTENDANCE_SCOPE,
        active_event="guild_check_in.attendance_scope_active",
        unavailable_event="guild_check_in.attendance_scope_unavailable",
    )


def _build_guild_check_in(dependencies: FlowDependencies) -> PerCharacterFlow:
    return GuildCheckInFlow(
        dependencies.observer,
        dependencies.actions,
        dependencies.events,
        completion_observer=_guild_attendance_observer_for(
            dependencies, dependencies.observer
        ),
        cancel_requested=dependencies.cancel_requested,
    )


def _build_stages_daily(dependencies):
    from bot.stages_wiring import build_stages_daily
    return build_stages_daily(dependencies, _build_monster_wave(dependencies))


def _build_gold_farming(dependencies):
    from bot.gold_farming_flow import GoldFarmingFlow
    from bot.stages_wiring import build_stages_daily, ensure_lobby_entry
    mw=_build_monster_wave(dependencies)
    stages=build_stages_daily(dependencies,mw)
    return GoldFarmingFlow(stages,mw,ensure_lobby=lambda:ensure_lobby_entry(dependencies),
        events=dependencies.events,cancel_requested=dependencies.cancel_requested,
        continue_on_unavailable=getattr(dependencies,"routine_continue_on_unavailable",True))


DEFAULT_FLOW_REGISTRY = FlowRegistry((
    FlowDefinition('stages_daily', 'Stages Ads', StagesDailyFlow.scope,
                   StagesDailyFlow.contract, _build_stages_daily,
                   controlled_unavailable_events=frozenset({'stages_daily.ads_unavailable'})),
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
    FlowDefinition('gold_farming', 'Gold Farming Cycle', StagesDailyFlow.scope,
                   GoldFarmingFlow.contract, _build_gold_farming),
))


__all__ = (
    "DEFAULT_FLOW_REGISTRY",
    "FlowDefinition",
    "FlowDependencies",
    "FlowRegistry",
)
