"""Reusable productive composition for CLI and the future GUI."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TextIO
from uuid import uuid4

from bot.action_executor import ActionExecutor
from bot.auto_battle import AutoBattleDetector, AutoBattleEnsurer
from bot.obstruction_recovery import PortalObstructionRecovery
from bot.portal_notification import PortalNotificationProbe
from bot.catalog import (
    MENU_QUICK,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
    build_default_resolver,
)
from bot.config import RuntimeConfig
from bot.character_identity import LobbyNameRecognizer
from bot.character_state import (CharacterStateStore, CharacterStateEvents, ResetScheduler,
                                 establish_character_state, character_state_scope, current_character_state, DEFAULT_DB_PATH)
from bot.character_data import CharacterDataCollector, QuickMenuResourceReader, ResourceSnapshotMode
from bot.world_boss_state import WorldBossEligibilityPolicy, WorldBossEligibilityMode, WorldBossStateReader
from bot.ocr import RapidOcrEngine
from bot.event_log import RuntimeEventConsumer, RuntimeEventStream, build_runtime_event_stream
from bot.event_context import event_scope, operation_scope
from bot.flow_contracts import publish_flow_events, run_flow_with_optional_seed
from bot.failure_cause import FailureCause
from bot.failure_evidence import FailureEvidence, publish_failure
from bot.equipment_combine_relief import EquipmentCombineRelief
from bot.flow_contracts import FlowResult, FlowStatus, PerCharacterFlow
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowDefinition, FlowRegistry, scoped_observer_for, scoped_transition_for
from bot.perception import (
    GUILD_NAVIGATE_SCOPE,
    PETS_MANAGE_NAVIGATE_SCOPE,
    QUICK_MENU_TO_LOBBY_SCOPE,
    ROTATION_CHARACTER_SELECTION_SCOPE,
    ROTATION_TO_LOBBY_SCOPE,
    WORLD_BOSS_ELIGIBILITY_SCOPE,
    build_default_perception,
)
from bot.pet_summon_space_relief import PetSummonSpaceRelief
from bot.preconditions import MinimalPreconditionEnsurer
from bot.quick_menu import (
    quick_menu_accessible, quick_menu_matches_origin,
    is_clean_quick_menu_base, open_quick_menu_destination, DEFAULT_QUICK_MENU_POLICY,
    select_quick_menu_guild_action,
)
from bot.rotation import StandardRotation
from bot.runtime import build_adb_client, build_frame_source, build_runtime_fact_reader
from bot.runtime_observer import RuntimeObserver, RuntimeSnapshot, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import (
    OpenGuild,
    OpenPets,
    SelectQuickMenuLobby,
)
from bot.session import CharacterContext, SessionPlan, SessionResult, SessionRunner, SessionStatus
from bot.socket_inventory_relief import SocketInventoryRelief
from bot.state import ResolutionStatus
from bot.tap_through_animation import TapThroughAnimation
from bot.verified_transition import (
    VerifiedTransition, VerifiedTransitionPolicy,
)
from bot.world_boss_eligibility import WorldBossDailyEligibility
from bot.world_boss_flow import WorldBossFlow
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_productive import ProductiveMonsterWaveFlow
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.monster_wave_activity import clean_mw
from bot.battle_mode_zone import BattleModeZone


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CLEAN_CONTEXTS = DEFAULT_QUICK_MENU_POLICY.accessible_from
_CLEAN_CONTEXT_TIMEOUT = 5.0
_CLEAN_CONTEXT_STABLE_FOR = 0.25


class CancellationToken:
    """Thread-safe cancellation boundary suitable for signals and GUI callbacks."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def request(self) -> None:
        self._requested.set()

    def is_requested(self) -> bool:
        return self._requested.is_set()


@dataclass(frozen=True)
class FlowsOnceResult:
    """One ordered attempt on the current character, with no advance."""

    status: FlowStatus
    flow_results: tuple[FlowResult, ...]
    error: str | None = None
    failure: FailureCause | None = None

    @property
    def flows_completed(self) -> int:
        return sum(result.status is FlowStatus.COMPLETED for result in self.flow_results)

    @property
    def business_event_count(self) -> int:
        return sum(len(result.events) for result in self.flow_results)


@dataclass
class ProductiveRuntime:
    config: RuntimeConfig
    observer: RuntimeObserver
    actions: ActionExecutor
    facts: object
    auto_battle: AutoBattleEnsurer
    socket_relief: SocketInventoryRelief
    equipment_combine_relief: EquipmentCombineRelief
    pet_summon_space_relief: PetSummonSpaceRelief
    events: RuntimeEventStream
    cancel_token: CancellationToken
    registry: FlowRegistry = DEFAULT_FLOW_REGISTRY
    # Stateless recognition backend shared by sequential occurrence bindings.
    # Readers keep their own facts/cursors/configs; no result cache is shared.
    ocr_engine: object | None = field(default=None, kw_only=True, repr=False)
    routine_continue_on_unavailable: bool = field(default=True, kw_only=True)
    character_store: object | None = field(default=None, kw_only=True, repr=False)
    resource_snapshot_mode: str = field(default=ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION.value, kw_only=True)
    _identity_snapshot: RuntimeSnapshot | None = field(default=None, init=False, repr=False)
    _identity_active: bool = field(default=False, init=False, repr=False)

    @property
    def cancel_requested(self):
        return self.cancel_token.is_requested

    def build_flow(self, definition: FlowDefinition) -> PerCharacterFlow:
        flow = definition.build(self)
        if isinstance(flow, WorldBossFlow):
            reader = WorldBossStateReader(self.ocr_engine) if self.ocr_engine is not None else None
            flow.eligibility_policy = WorldBossEligibilityPolicy(reader=reader,events=self.events,store=self.character_store)
            flow.activity.eligibility_policy = flow.eligibility_policy
        return flow

    def build_flows(
        self, definitions: tuple[FlowDefinition, ...]
    ) -> tuple[PerCharacterFlow, ...]:
        return tuple(self.build_flow(definition) for definition in definitions)

    def build_preconditions(self) -> MinimalPreconditionEnsurer:
        return MinimalPreconditionEnsurer(
            lambda: self._clean_context_entry(),
            navigate_to_lobby=self._navigate_to_lobby,
            navigate_to_battle_mode=self._navigate_to_battle_mode,
            navigate_to_pets_manage=self._navigate_to_pets_manage,
            navigate_lobby_to_guild=self._navigate_lobby_to_guild,
            navigate_to_guild=self._navigate_to_guild,
        )

    def build_portal_probe(self) -> PortalNotificationProbe:
        """On-demand probe using the calibrated Heaven/Hell/Guild assets."""

        return PortalNotificationProbe()

    def build_obstruction_recovery(self) -> PortalObstructionRecovery:
        """Single shared portal cleanup helper for every verifying seam."""

        return PortalObstructionRecovery(
            self.observer,
            self.actions,
            self.build_portal_probe(),
            events=self.events,
            cancel_requested=self.cancel_requested,
        )

    def _shared_obstruction_recovery(self):
        """Shared recovery, or None when doubles lack the action boundary.

        Production observer/actions always satisfy the interface; legacy test
        doubles with ``actions=object()`` fall back silently to the previous
        behavior without portal recovery instead of failing construction or
        emitting new observable events.
        """

        try:
            return self.build_obstruction_recovery()
        except ValueError:
            return None

    def build_verified_transition(self) -> VerifiedTransition:
        """VerifiedTransition already wired to the shared portal recovery."""

        return VerifiedTransition(
            self.observer,
            self.actions,
            self.events,
            self._shared_obstruction_recovery(),
        )

    def build_rotation(self, character_count: int) -> StandardRotation:
        main_transition = self.build_verified_transition()
        collector = (CharacterDataCollector(QuickMenuResourceReader(self.ocr_engine,events=self.events),
            events=self.events,mode=self.resource_snapshot_mode,
            failure_directory=PROJECT_ROOT/'artifacts/character-state-unreadable')
            if getattr(self,'character_store',None) is not None and getattr(self,'ocr_engine',None) is not None else None)
        return StandardRotation(
            self.observer,
            self.actions,
            self.events,
            character_count=character_count,
            verified_transition=main_transition,
            quick_menu_ready=collector.before_rotation if collector else None,
            post_swipe_observer=scoped_observer_for(
                self,
                self.observer,
                scope=ROTATION_CHARACTER_SELECTION_SCOPE,
                active_event="rotation.post_swipe_scope_active",
                unavailable_event="rotation.post_swipe_scope_unavailable",
            ),
            selection_transition=scoped_transition_for(
                self,
                main_transition,
                scope=ROTATION_CHARACTER_SELECTION_SCOPE,
                active_event="rotation.character_selection_scope_active",
                unavailable_event=(
                    "rotation.character_selection_scope_unavailable"
                ),
            ),
            confirmation_transition=scoped_transition_for(
                self,
                main_transition,
                scope=ROTATION_TO_LOBBY_SCOPE,
                active_event="rotation.lobby_return_scope_active",
                unavailable_event="rotation.lobby_return_scope_unavailable",
            ),
        )

    def run_flow(self, definition: FlowDefinition) -> FlowResult:
        with event_scope(character_index=1, flow=definition.id, session_id=None), operation_scope(definition.id), character_state_scope():
            self._identity_active = True
            try:
                return self._run_flow(definition)
            except BaseException as error:
                failure = publish_failure(
                    self.events,
                    "flow.failed", component=definition.id,
                    error=f"{type(error).__name__}: {error}",
                    failure=FailureCause.from_error(error, kind="exception"),
                )
                try:
                    error.failure = failure
                except Exception:
                    pass
                raise
            finally:
                self._identity_active = False
                self._identity_snapshot = None

    def _run_flow(self, definition: FlowDefinition) -> FlowResult:
        flow = self.build_flow(definition)
        preconditions = self.build_preconditions()
        self.events.record("flow.started", component=flow.name, flow=flow.name)
        if self.cancel_requested():
            result = FlowResult(FlowStatus.CANCELLED)
        else:
            ensured = preconditions.ensure(flow.contract.precondition)
            if not ensured.succeeded:
                result = FlowResult(
                    FlowStatus.FAILED,
                    error=f"flow_precondition_failed: {ensured.error or 'unknown'}",
                )
            else:
                if self.character_store is not None:
                    self._resolve_character_identity(getattr(ensured,'snapshot',None))
                try:
                    # Nothing runs between ensure and flow start on this
                    # path, so the verified snapshot is still the latest
                    # validated evidence. Opted-in flows consume it as
                    # their initial snapshot; the rest run normally.
                    # Ensurers without snapshot evidence (legacy doubles)
                    # behave exactly as before via getattr.
                    seed = getattr(ensured, "snapshot", None)
                    result = run_flow_with_optional_seed(flow, seed)
                except RuntimeWaitCancelled:
                    result = FlowResult(FlowStatus.CANCELLED)
                if (
                    result.status is FlowStatus.COMPLETED
                    and not preconditions.current_satisfies_any(
                        flow.contract.successful_postconditions
                    )
                ):
                    result = FlowResult(
                        FlowStatus.FAILED,
                        events=result.events,
                        error="flow_completed_outside_successful_postconditions",
                    )
        event = {
            FlowStatus.RESOURCE_BOARD_PENDING: "flow.resource_board_pending",
            FlowStatus.MANUAL_RESOLUTION: "flow.manual_resolution",
            FlowStatus.COMPLETED: "flow.completed",
            FlowStatus.CANCELLED: "flow.cancelled",
            FlowStatus.FAILED: "flow.failed",
        }[result.status]
        failure = publish_failure(
            self.events,
            event,
            result.failure,
            component=flow.name,
            flow=flow.name,
            error=result.error,
            business_event_count=len(result.events),
        )
        publish_flow_events(self.events, flow.name, result.events, character_index=1, character_name=None)
        return replace(result, failure=failure)

    def run_routine(self, routine, *, character_count: int | None = None):
        """Resolve ordinary steps through the single registry and existing runners."""
        from bot.routines import RoutineSpec, config_overrides
        if not isinstance(routine, RoutineSpec):
            raise ValueError("routine must be RoutineSpec")
        available = {d.id for d in self.registry.definitions}
        for position, step in enumerate(routine.steps):
            if step.enabled and step.flow_id not in available:
                self.events.record("routine.step.unavailable", flow=step.flow_id,
                                   step_position=position, routine=routine.name)
        steps = routine.active_steps(self.registry)
        for step in steps:
            config_overrides(step.config)
        definitions = self.registry.select(tuple(s.flow_id for s in steps))
        positions = tuple(i for i, step in enumerate(routine.steps) if step.enabled and step.flow_id in available)
        with event_scope(routine_id=routine.id, routine_name=routine.name):
            self.events.record("routine.started", step_count=len(steps))
            previous = self.resource_snapshot_mode
            self.resource_snapshot_mode = routine.resource_snapshot_mode
            try:
                if character_count is None:
                    return self.run_flows_once(definitions, routine_steps=steps, routine_positions=positions)
                return self.run_session(definitions, character_count=character_count,
                                        routine_steps=steps, routine_positions=positions)
            finally:
                self.resource_snapshot_mode = previous

    def _step_runtime(self, step):
        from bot.routines import config_overrides
        overrides = config_overrides(step.config)
        if not overrides and self.routine_continue_on_unavailable == step.continue_on_unavailable:
            return self
        return replace(self, config=replace(self.config, **overrides),
                       routine_continue_on_unavailable=step.continue_on_unavailable)

    def run_flows_once(self, definitions: tuple[FlowDefinition, ...], *, routine_steps=None, routine_positions=()) -> FlowsOnceResult:
        """Use the same ordered handoff owner, without Rotation or Daily policy."""
        if not definitions:
            raise ValueError("at least one flow is required")
        if routine_steps is not None and len(routine_steps) != len(definitions):
            raise ValueError("one routine step is required per definition")
        try:
            result = self.run_session(definitions, character_count=1,
                routine_steps=routine_steps, routine_positions=routine_positions, rotate=False)
            status = FlowStatus(result.status.value)
            flows = tuple(r for c in result.character_results for r in c.flow_results)
            if flows and flows[-1].status is FlowStatus.RESOURCE_BOARD_PENDING:
                status = FlowStatus.RESOURCE_BOARD_PENDING
            return FlowsOnceResult(status, flows, result.failure_cause, result.failure)
        except RuntimeWaitCancelled:
            return FlowsOnceResult(FlowStatus.CANCELLED, ())
        except Exception as error:
            return FlowsOnceResult(FlowStatus.FAILED, (), str(error), getattr(error, 'failure', None))

    def run_session(
        self,
        definitions: tuple[FlowDefinition, ...],
        *,
        character_count: int,
        routine_steps=None,
        routine_positions=(),
        rotate=True,
        character_data_only=False,
    ) -> SessionResult:
        if character_data_only and (definitions or routine_steps or not rotate):
            raise ValueError('Character Data Sweep cannot execute gameplay flows')
        if routine_steps is not None and len(routine_steps) != len(definitions):
            raise ValueError("one routine step is required per definition")
        flows = (tuple(self._step_runtime(step).build_flow(definition)
                       for definition, step in zip(definitions, routine_steps))
                 if routine_steps else self.build_flows(definitions))
        policies = []
        for position, flow in enumerate(flows):
            if isinstance(flow, WorldBossFlow):
                value = (routine_steps[position].config.get('world_boss',{}).get('eligibility') if routine_steps else None)
                mode = value or (WorldBossEligibilityMode.DAILY_QUEST if rotate else WorldBossEligibilityMode.GENERAL)
                if getattr(flow,'eligibility_policy',None) is not None:
                    flow.eligibility_policy.mode = WorldBossEligibilityMode(mode)
                policies.append(WorldBossEligibilityMode(mode))
            else:
                policies.append(None)
        zone = next((flow.zone for flow in flows if isinstance(flow, (WorldBossFlow, MonsterWaveFlow, ProductiveMonsterWaveFlow))), None)
        flows = tuple(flow.prepared(zone)
                      if isinstance(flow, (WorldBossFlow, MonsterWaveFlow, ProductiveMonsterWaveFlow)) else flow
                      for flow in flows)
        rotation = self.build_rotation(character_count)
        saved_ids = set()
        failed_snapshots = 0
        if character_data_only:
            collect = rotation.quick_menu_ready
            if collect is None:
                raise ValueError('Character Data Sweep requires the persistent collector')
            def collect_sweep(snapshot, *, origin):
                nonlocal failed_snapshots
                scope = current_character_state()
                cid = scope[1] if scope else None
                saved = cid not in saved_ids and collect(snapshot,origin=origin) is True
                if saved:
                    saved_ids.add(cid)
                else:
                    failed_snapshots += 1
                self.events.record('character_data_sweep.snapshot',character_id=cid,
                    status='saved' if saved else 'acquisition_failure',source_sequence=snapshot.sequence)
            rotation.quick_menu_ready = collect_sweep
        plan = SessionPlan.standard(
            flows=flows,
            rotate=rotate,
            rotation_strategy=rotation,
            character_count=character_count,
            character_data_only=character_data_only,
            step_positions=tuple(routine_positions),
            controlled_unavailable=tuple(
                definition.controlled_unavailable_events if step.continue_on_unavailable else frozenset()
                for definition, step in zip(definitions, routine_steps or ())
            ),
            eligibility=tuple(
                self.build_world_boss_daily_eligibility() if policy is WorldBossEligibilityMode.DAILY_QUEST else
                None
                for policy in policies
            ),
        )
        recognizer: LobbyNameRecognizer | None = None

        def character_context_factory(index: int) -> CharacterContext:
            nonlocal recognizer
            snapshot, self._identity_snapshot = self._identity_snapshot, None
            if recognizer is None:
                # Construction is inside SessionRunner's non-fatal seam too.
                recognizer = LobbyNameRecognizer(self.ocr_engine or RapidOcrEngine())
            return self._resolve_character_identity(snapshot, recognizer=recognizer)

        self._identity_snapshot = None
        self._identity_active = True
        try:
            result = SessionRunner(
                plan,
                preconditions=self.build_preconditions(),
                events=self.events,
                cancel_requested=self.cancel_requested,
                character_context_factory=character_context_factory,
            ).run()
            if character_data_only:
                failures = failed_snapshots
                if result.status is SessionStatus.COMPLETED:
                    failures = max(failures,character_count-len(saved_ids))
                status = (SessionStatus.MANUAL_RESOLUTION if failures and result.status is SessionStatus.COMPLETED else result.status)
                result = replace(result,status=status,snapshots_updated=len(saved_ids),acquisition_failures=failures)
                self.events.record('character_data_sweep.completed',status=result.status.value,
                    characters_processed=result.characters_processed,identities_resolved=result.identities_resolved,
                    snapshots_updated=result.snapshots_updated,rotations=result.advances_completed,
                    acquisition_failures=failures,duration=result.duration)
            return result
        finally:
            self._identity_snapshot = None
            self._identity_active = False

    def run_character_data_sweep(self):
        """Explicit full roster data refresh; no registry gameplay definitions."""
        from bot.character_identity import CHARACTER_IDS
        previous = self.resource_snapshot_mode
        self.resource_snapshot_mode = ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION.value
        try:
            self.events.record('character_data_sweep.started',character_count=len(CHARACTER_IDS))
            return self.run_session((),character_count=len(CHARACTER_IDS),character_data_only=True)
        finally:
            self.resource_snapshot_mode = previous

    def _resolve_character_identity(self, snapshot, *, recognizer=None):
        identity = (recognizer or LobbyNameRecognizer(self.ocr_engine or RapidOcrEngine())).recognize(snapshot)
        establish_character_state(self.character_store,identity.character_id if identity else None)
        if identity is None:
            self.events.record('character.identity_unknown',reason='insufficient_evidence')
            return CharacterContext()
        self.events.record('character.identity_resolved',character_id=identity.character_id,
            canonical_name=identity.personal_name,display_name=identity.class_name,method=identity.method)
        return CharacterContext(identity.class_name,identity.confidence,identity.character_id)

    def build_world_boss_daily_eligibility(self) -> WorldBossDailyEligibility:
        """Only the daily session composition installs this check; registry is general."""
        observer = scoped_observer_for(
            self, self.observer,
            scope=WORLD_BOSS_ELIGIBILITY_SCOPE,
            active_event="world_boss.eligibility_scope_active",
            unavailable_event="world_boss.eligibility_scope_unavailable",
        )
        return WorldBossDailyEligibility(
            observer,
            cancel_requested=self.cancel_requested,
        )

    def _current_clean_context(self) -> str | None:
        context, _ = self._clean_context_entry()
        return context

    def _clean_context_entry(self) -> tuple[str | None, object | None]:
        """Observe one clean-context entry as a context/snapshot pair.

        The snapshot is the exact observation the context was derived
        from: the immediate clean frame, or the settled frame of the
        bounded wait. Recovery and timeout paths carry no reusable
        evidence and report ``None``.
        """

        self._identity_snapshot = None
        try:
            initial = self.observer.observe()
            if _is_clean_known_context(initial):
                if self._identity_active:
                    self._identity_snapshot = initial
                return initial.state.base_context, initial
            settled = self.observer.wait_until(
                _is_clean_known_context,
                after_sequence=initial.sequence,
                timeout=_CLEAN_CONTEXT_TIMEOUT,
                stable_for=_CLEAN_CONTEXT_STABLE_FOR,
                cancel_requested=self.cancel_requested,
            )
            if self._identity_active:
                self._identity_snapshot = settled
            return settled.state.base_context, settled
        except RuntimeWaitTimeout as error:
            recovered = self._recover_clean_context(error.last_snapshot)
            if recovered is not None:
                return recovered, None
            latest = error.last_snapshot
            self.events.record(
                "runtime.context_probe_timeout",
                timeout=error.timeout,
                after_sequence=error.after_sequence,
                last_sequence=latest.sequence if latest is not None else None,
                resolution_status=(
                    latest.state.status.value if latest is not None else None
                ),
                base_context=(
                    latest.state.base_context if latest is not None else None
                ),
                overlays=(
                    sorted(latest.state.overlays) if latest is not None else []
                ),
            )
            return None, None
        except RuntimeWaitCancelled:
            return None, None

    def _recover_clean_context(self, last_snapshot) -> str | None:
        """Reuse the shared portal recovery for context normalization.

        Single bounded attempt: probe the timed-out snapshot, dismiss on
        CONFIRMED only, then re-evaluate the original clean-context condition
        with one more bounded wait. Returns the base context or None.
        """

        if last_snapshot is None:
            return None
        recovery = self._shared_obstruction_recovery()
        if recovery is None:
            return None
        try:
            recovered = recovery.attempt(
                last_snapshot, _is_clean_known_context
            )
        except Exception:
            return None
        if recovered is None:
            return None
        try:
            settled = self.observer.wait_until(
                _is_clean_known_context,
                after_sequence=recovered.sequence,
                timeout=_CLEAN_CONTEXT_TIMEOUT,
                stable_for=_CLEAN_CONTEXT_STABLE_FOR,
                cancel_requested=self.cancel_requested,
            )
            return settled.state.base_context
        except (RuntimeWaitTimeout, RuntimeWaitCancelled):
            return None
        except Exception:
            return None

    @staticmethod
    def _navigation_succeeded(result) -> bool:
        if result.status is FlowStatus.CANCELLED:
            raise RuntimeWaitCancelled()
        if not result.succeeded:
            error = RuntimeError(result.error or 'navigation_failed')
            error.failure = result.failure
            raise error
        return True

    def _navigate_to_battle_mode(self) -> bool:
        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_BATTLE_MODE_SELECT):
            return True
        if not (_is_clean_base(initial, SCREEN_LOBBY) or clean_mw(initial)):
            origin = initial.state.base_context
            if (not _is_clean_known_context(initial) or not quick_menu_accessible(origin)
                    or not self._navigate_to_lobby()):
                return False
        return self._navigation_succeeded(BattleModeZone(self.observer, self.build_verified_transition(),
                              cancel_requested=self.cancel_requested).ensure_hub())

    def _navigate_to_lobby(self) -> bool:
        """Normalize an acquired origin to Lobby with its verified direct route."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_LOBBY):
            return True
        if _is_clean_base(initial, SCREEN_BATTLE_MODE_SELECT):
            return self._navigation_succeeded(BattleModeZone(self.observer, self.build_verified_transition(),
                                  cancel_requested=self.cancel_requested).leave())
        origin = initial.state.base_context
        if (
            origin is None
            or not quick_menu_accessible(origin)
            or not _is_clean_base(initial, origin)
        ):
            return False
        transition = self.build_verified_transition()
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        # Pets reached via Quick Menu need not have Lobby as Back parent.
        # The menu destination remains safe without guessing that history.
        lobby = self._quick_menu_to_lobby(initial, transition, policy)
        return lobby.succeeded and not self.cancel_requested()

    def _quick_menu_to_lobby(self, initial, transition, policy, *, prefix="precondition"):
        """Lobby specialization of the existing guarded Quick Menu router."""
        return self._quick_menu_to_destination(initial, transition, policy,
            destination=SCREEN_LOBBY, action=SelectQuickMenuLobby(),
            selection='lobby', scope=QUICK_MENU_TO_LOBBY_SCOPE, prefix=prefix)

    def _quick_menu_to_destination(self, initial, transition, policy, *,
                                   destination, action, selection, scope=None, prefix='precondition'):
        destination_transition = (scoped_transition_for(
            self, transition, scope=scope,
            active_event=f"{prefix}.{selection}_return_scope_active",
            unavailable_event=f"{prefix}.{selection}_return_scope_unavailable",
        ) if scope is not None else transition)
        origin = initial.state.base_context
        return open_quick_menu_destination(
            initial, transition, policy, action=action, selection=selection,
            source_guard=lambda snapshot: _is_clean_base(snapshot, origin),
            expected=lambda snapshot: _is_clean_base(snapshot, destination),
            destination_transition=destination_transition,
            cancel_requested=self.cancel_requested, prefix=prefix,
        )

    def _navigate_to_guild(self) -> bool:
        """Navigate a non-Lobby capable origin through Quick Menu to Guild."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_GUILD):
            return True
        origin = initial.state.base_context
        if (
            origin is None
            or origin == SCREEN_LOBBY
            or not quick_menu_accessible(origin)
            or not _is_clean_base(initial, origin)
        ):
            return False
        transition = self.build_verified_transition()
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        guild = self._quick_menu_to_destination(
            initial, transition, policy, destination=SCREEN_GUILD,
            action=select_quick_menu_guild_action(origin), selection='guild',
        )
        return guild.succeeded and not self.cancel_requested()

    def _navigate_to_pets_manage(self) -> bool:
        """Open Pets directly from Lobby or a compatible Quick Menu origin."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_PETS_MANAGE):
            return True
        if not _is_clean_base(initial, SCREEN_LOBBY):
            origin = initial.state.base_context
            if (
                origin is None
                or not quick_menu_accessible(origin)
                or not _is_clean_base(initial, origin)
            ):
                return False
            from bot.quick_menu import select_quick_menu_pets_action
            pets = self._quick_menu_to_destination(
                initial, self.build_verified_transition(),
                VerifiedTransitionPolicy(normal_timeout=6., grace_timeout=2., max_attempts=2),
                destination=SCREEN_PETS_MANAGE, action=select_quick_menu_pets_action(origin),
                selection='pets', scope=PETS_MANAGE_NAVIGATE_SCOPE,
            )
            return pets.succeeded and not self.cancel_requested()
        if not _is_clean_base(initial, SCREEN_LOBBY):
            return False

        transition = self.build_verified_transition()
        pets_transition = scoped_transition_for(
            self,
            transition,
            scope=PETS_MANAGE_NAVIGATE_SCOPE,
            active_event="precondition.pets_manage_navigate_scope_active",
            unavailable_event="precondition.pets_manage_navigate_scope_unavailable",
        )
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        pets = pets_transition.execute(
            "precondition.open_pets",
            OpenPets(),
            initial,
            expected=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_PETS_MANAGE
            ),
            precondition=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_LOBBY
            ),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_LOBBY
            ),
            abort_if=lambda snapshot: _has_incompatible_destination_state(
                snapshot, SCREEN_LOBBY, SCREEN_PETS_MANAGE
            ),
            stable_for=_CLEAN_CONTEXT_STABLE_FOR,
            policy=policy,
        )
        return pets.succeeded and not self.cancel_requested()

    def _navigate_lobby_to_guild(self) -> bool:
        """Use the acquired direct Lobby target and verify Guild."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_GUILD):
            return True
        if not _is_clean_base(initial, SCREEN_LOBBY):
            return False
        transition = self.build_verified_transition()
        guild_transition = scoped_transition_for(
            self,
            transition,
            scope=GUILD_NAVIGATE_SCOPE,
            active_event="precondition.guild_navigate_scope_active",
            unavailable_event="precondition.guild_navigate_scope_unavailable",
        )
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        guild = guild_transition.execute(
            "precondition.open_guild",
            OpenGuild(),
            initial,
            expected=lambda snapshot: _is_clean_base(snapshot, SCREEN_GUILD),
            precondition=lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_LOBBY
            ),
            abort_if=lambda snapshot: _has_incompatible_destination_state(
                snapshot, SCREEN_LOBBY, SCREEN_GUILD
            ),
            stable_for=_CLEAN_CONTEXT_STABLE_FOR,
            policy=policy,
        )
        return guild.succeeded and not self.cancel_requested()


@contextmanager
def open_productive_runtime(
    *,
    dotenv_path: str | Path = PROJECT_ROOT / ".env",
    log_path: str | Path,
    debug: bool = False,
    equipment_sell_policy=None,
    cancel_token: CancellationToken | None = None,
    registry: FlowRegistry = DEFAULT_FLOW_REGISTRY,
    event_consumers: tuple[RuntimeEventConsumer, ...] = (),
    console: TextIO | None = sys.stdout,
    evidence_root: str | Path = PROJECT_ROOT / "artifacts" / "failure_evidence",
    character_state_path: str | Path = DEFAULT_DB_PATH,
) -> Iterator[ProductiveRuntime]:
    """Acquire every productive runtime dependency and guarantee source cleanup."""

    token = cancel_token or CancellationToken()
    events = build_runtime_event_stream(
        log_path,
        debug=debug,
        console=console,
        consumers=event_consumers,
    )
    evidence = FailureEvidence(Path(evidence_root))
    events.failure_evidence = evidence
    events.record("runtime.started", log_path=str(log_path), debug=debug)
    try:
        config = RuntimeConfig.from_env(dotenv_path=dotenv_path)
        if equipment_sell_policy is not None:
            from dataclasses import replace
            config = replace(config, equipment_sell=equipment_sell_policy)
        adb = build_adb_client(config)
        if adb.get_state() != "device":
            raise RuntimeError("ADB device is not ready")
        source = build_frame_source(
            config,
            adb_client=adb,
            video_bit_rate=8_000_000,
            # Repeated MW bindings warm several OCR pools. At 30 FPS their
            # CPU contention queued capture past Stages' freshness guard live.
            max_fps=10,
        )
        actions = ActionExecutor(adb)
        with source:
            observer = RuntimeObserver(
                source,
                build_default_perception(PROJECT_ROOT),
                build_default_resolver(),
                events=events,
                snapshot_consumer=evidence.observe,
            )
            ocr_engine = RapidOcrEngine()
            facts = build_runtime_fact_reader(observer, ocr_engine=ocr_engine, events=events)
            auto_battle = AutoBattleEnsurer(AutoBattleDetector(observer), actions)
            try:
                shared_recovery: object = PortalObstructionRecovery(
                    observer,
                    actions,
                    PortalNotificationProbe(),
                    events=events,
                    cancel_requested=token.is_requested,
                )
            except ValueError:
                shared_recovery = None
            transition = VerifiedTransition(
                observer, actions, events, shared_recovery
            )
            tap_through = TapThroughAnimation(observer, actions, events)
            socket_relief = SocketInventoryRelief(
                observer,
                actions,
                facts,
                events,
                verified_transition=transition,
                tap_through=tap_through,
            )
            equipment_combine_relief = EquipmentCombineRelief(
                observer,
                actions,
                events,
                verified_transition=transition,
                tap_through=tap_through,
            )
            pet_summon_space_relief = PetSummonSpaceRelief(
                observer,
                actions,
                events,
                tap_through=tap_through,
            )
            store = CharacterStateStore(character_state_path,events=events)
            scheduler = ResetScheduler(store)
            unsubscribe_state = events.subscribe(CharacterStateEvents())
            scheduler.start()
            try:
                yield ProductiveRuntime(
                    config,
                    observer,
                    actions,
                    facts,
                    auto_battle,
                    socket_relief,
                    equipment_combine_relief,
                    pet_summon_space_relief,
                    events,
                    token,
                    registry,
                    ocr_engine=ocr_engine,
                    character_store=store,
                )
            finally:
                unsubscribe_state()
                scheduler.close()
                store.close()
                observer.flush_analysis_metrics()
        events.record("runtime.completed")
    except BaseException as error:
        failure = getattr(error, "failure", None)
        if not isinstance(failure, FailureCause):
            failure = FailureCause.from_error(error, kind="exception")
        events.record(
            "runtime.failed",
            error=f"{type(error).__name__}: {error}",
            failure=failure.payload(),
        )
        raise
    finally:
        evidence.close()
        events.failure_evidence = None
        events.record("runtime.closed")


def default_log_path(kind: str, *, directory: str | Path = PROJECT_ROOT / "logs") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session_id = uuid4().hex[:8]
    return Path(directory) / f"{timestamp}_{kind}_{session_id}.jsonl"


def _is_clean_known_context(snapshot) -> bool:
    state = snapshot.state
    return state.base_context in _CLEAN_CONTEXTS and _is_clean_base(
        snapshot, state.base_context
    )


def _is_clean_base(snapshot, base: str) -> bool:
    state = snapshot.state
    if DEFAULT_QUICK_MENU_POLICY.allows(base):
        return state.base_context == base and is_clean_quick_menu_base(snapshot)
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == base
        and not state.overlays
    )


def _has_quick_menu(snapshot) -> bool:
    state = snapshot.state
    return (
        set(state.overlays) == {MENU_QUICK}
        and state.status in {ResolutionStatus.UNKNOWN, ResolutionStatus.RESOLVED}
    )


def _has_incompatible_open_quick_menu_state(snapshot, origin: str) -> bool:
    state = snapshot.state
    if quick_menu_matches_origin(snapshot, origin) or _is_clean_base(snapshot, origin):
        return False
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or state.status is ResolutionStatus.RESOLVED
    )


def _has_incompatible_destination_state(
    snapshot,
    origin: str,
    destination: str,
) -> bool:
    state = snapshot.state
    if (
        _has_quick_menu(snapshot)
        or _is_clean_base(snapshot, origin)
        or _is_clean_base(snapshot, destination)
    ):
        return False
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {origin, destination}
        )
    )


__all__ = (
    "CancellationToken",
    "ProductiveRuntime",
    "default_log_path",
    "open_productive_runtime",
)
