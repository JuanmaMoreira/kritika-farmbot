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
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_PREMIUM_TICKET_AVAILABLE,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.config import RuntimeConfig
from bot.character_identity import LobbyNameRecognizer
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
    ROTATION_CHARACTER_SELECTION_SCOPE,
    WORLD_BOSS_ELIGIBILITY_SCOPE,
    build_default_perception,
)
from bot.pet_summon_space_relief import PetSummonSpaceRelief
from bot.preconditions import MinimalPreconditionEnsurer
from bot.quick_menu import (
    QuickMenuHandoff, quick_menu_accessible, quick_menu_matches_origin,
    select_quick_menu_guild_action,
)
from bot.rotation import StandardRotation
from bot.runtime import build_adb_client, build_frame_source, build_runtime_fact_reader
from bot.runtime_observer import RuntimeObserver, RuntimeSnapshot, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import (
    ClosePets,
    OpenGuild,
    OpenPets,
    OpenQuickMenu,
    SelectQuickMenuLobby,
)
from bot.session import CharacterContext, SessionPlan, SessionResult, SessionRunner
from bot.socket_inventory_relief import SocketInventoryRelief
from bot.state import ResolutionStatus
from bot.tap_through_animation import TapThroughAnimation
from bot.verified_transition import (
    VerifiedTransition, VerifiedTransitionOutcome, VerifiedTransitionPolicy,
)
from bot.world_boss_eligibility import WorldBossDailyEligibility
from bot.world_boss_flow import WorldBossFlow
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_eligibility import MonsterWaveDailyEligibility
from bot.monster_wave_semantics import STATUS_MONSTER_WAVE_DAILY_ACTIVE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CLEAN_CONTEXTS = frozenset(
    {
        SCREEN_BATTLE_MODE_SELECT,
        SCREEN_GUILD,
        SCREEN_LOBBY,
        SCREEN_PET_SUMMON,
        SCREEN_PETS_MANAGE,
        SCREEN_WORLD_BOSS,
    }
)
_GUILD_ATTENDANCE_STATES = frozenset(
    {STATUS_GUILD_ATTENDANCE_ACTIVE, STATUS_GUILD_ATTENDANCE_COMPLETED}
)
_GUILD_COMPATIBLE_OVERLAYS = _GUILD_ATTENDANCE_STATES | {
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE
}
_PET_SUMMON_STATUSES = frozenset(
    {
        STATUS_PET_EPIC_AVAILABLE,
        STATUS_PET_EPIC_UNAVAILABLE,
        STATUS_PET_PREMIUM_GOLD,
        STATUS_PET_PREMIUM_TICKET_AVAILABLE,
        STATUS_PET_SUMMON_DAILY_ACTIVE,
    }
)
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
    _identity_snapshot: RuntimeSnapshot | None = field(default=None, init=False, repr=False)
    _identity_active: bool = field(default=False, init=False, repr=False)

    @property
    def cancel_requested(self):
        return self.cancel_token.is_requested

    def build_flow(self, definition: FlowDefinition) -> PerCharacterFlow:
        return definition.build(self)

    def build_flows(
        self, definitions: tuple[FlowDefinition, ...]
    ) -> tuple[PerCharacterFlow, ...]:
        return tuple(self.build_flow(definition) for definition in definitions)

    def build_preconditions(self) -> MinimalPreconditionEnsurer:
        return MinimalPreconditionEnsurer(
            lambda: self._clean_context_entry(),
            navigate_to_lobby=self._navigate_to_lobby,
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
        return StandardRotation(
            self.observer,
            self.actions,
            self.events,
            character_count=character_count,
            verified_transition=main_transition,
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
        )

    def run_flow(self, definition: FlowDefinition) -> FlowResult:
        with event_scope(character_index=1, flow=definition.id, session_id=None), operation_scope(definition.id):
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

    def run_flows_once(self, definitions: tuple[FlowDefinition, ...]) -> FlowsOnceResult:
        """Compose the standalone contract without session or Rotation policy."""
        if not definitions:
            raise ValueError("at least one flow is required")
        results = []
        for definition in definitions:
            if self.cancel_requested():
                return FlowsOnceResult(FlowStatus.CANCELLED, tuple(results))
            try:
                result = self.run_flow(definition)
            except RuntimeWaitCancelled:
                result = FlowResult(FlowStatus.CANCELLED)
            except Exception as error:
                # run_flow already published the terminal cause and evidence.
                result = FlowResult(
                    FlowStatus.FAILED, error=f"{type(error).__name__}: {error}",
                    failure=getattr(error, "failure", None),
                )
            results.append(result)
            if result.status is not FlowStatus.COMPLETED:
                return FlowsOnceResult(result.status, tuple(results), result.error, result.failure)
        return FlowsOnceResult(FlowStatus.COMPLETED, tuple(results))

    def run_session(
        self,
        definitions: tuple[FlowDefinition, ...],
        *,
        character_count: int,
    ) -> SessionResult:
        flows = self.build_flows(definitions)
        zone = next((flow.zone for flow in flows if isinstance(flow, (WorldBossFlow, MonsterWaveFlow))), None)
        flows = tuple(flow.prepared(zone, daily=True) if isinstance(flow, MonsterWaveFlow) else
                      flow.prepared(zone) if isinstance(flow, WorldBossFlow) else flow
                      for flow in flows)
        rotation = self.build_rotation(character_count)
        plan = SessionPlan.standard(
            flows=flows,
            rotation_strategy=rotation,
            character_count=character_count,
            eligibility=tuple(
                self.build_world_boss_daily_eligibility() if flow.name == "world_boss" else
                MonsterWaveDailyEligibility(self.observer, cancel_requested=self.cancel_requested)
                if flow.name == 'monster_wave' else None
                for flow in flows
            ),
        )
        recognizer: LobbyNameRecognizer | None = None

        def character_context_factory(index: int) -> CharacterContext:
            nonlocal recognizer
            snapshot, self._identity_snapshot = self._identity_snapshot, None
            if snapshot is None:
                return CharacterContext()
            if recognizer is None:
                # Construction is inside SessionRunner's non-fatal seam too.
                recognizer = LobbyNameRecognizer(RapidOcrEngine())
            identity = recognizer.recognize(snapshot)
            if identity is None:
                return CharacterContext()
            return CharacterContext(identity.class_name, identity.confidence)

        self._identity_snapshot = None
        self._identity_active = True
        try:
            return SessionRunner(
                plan,
                preconditions=self.build_preconditions(),
                events=self.events,
                cancel_requested=self.cancel_requested,
                character_context_factory=character_context_factory,
            ).run()
        finally:
            self._identity_snapshot = None
            self._identity_active = False

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

    def _navigate_to_lobby(self) -> bool:
        """Normalize an acquired origin to Lobby with its verified direct route."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_LOBBY):
            return True
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
        if origin in {SCREEN_PETS_MANAGE, SCREEN_PET_SUMMON}:
            lobby = transition.execute(
                "precondition.close_pets",
                ClosePets(),
                initial,
                expected=lambda snapshot: _is_clean_base(
                    snapshot, SCREEN_LOBBY
                ),
                precondition=lambda snapshot: _is_clean_base(
                    snapshot, origin
                ),
                retryable_from=lambda snapshot: _is_clean_base(
                    snapshot, origin
                ),
                abort_if=lambda snapshot: _has_incompatible_destination_state(
                    snapshot, origin, SCREEN_LOBBY
                ),
                stable_for=_CLEAN_CONTEXT_STABLE_FOR,
                policy=policy,
            )
            return lobby.succeeded and not self.cancel_requested()
        lobby = self._quick_menu_to_lobby(initial, transition, policy)
        return lobby.succeeded and not self.cancel_requested()

    def _quick_menu_to_lobby(self, initial, transition, policy, *, prefix="precondition"):
        """Shared acquired return; keep the original transitions for other callers."""
        origin = initial.state.base_context
        opened = transition.execute(
            f"{prefix}.open_quick_menu",
            OpenQuickMenu(),
            initial,
            expected=lambda snapshot: quick_menu_matches_origin(snapshot, origin),
            precondition=lambda snapshot: _is_clean_base(
                snapshot, origin
            ),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, origin
            ),
            abort_if=lambda snapshot: _has_incompatible_open_quick_menu_state(
                snapshot, origin
            ),
            policy=policy,
        )
        if not opened.succeeded or self.cancel_requested():
            return opened
        handoff = QuickMenuHandoff.from_open_result(
            opened, lambda snapshot: _is_clean_base(snapshot, origin),
        )
        if handoff is None:
            return replace(
                opened, outcome=VerifiedTransitionOutcome.PRECONDITION_REJECTED,
                error="quick_menu_origin_handoff_invalid",
            )
        lobby = transition.execute(
            f"{prefix}.select_lobby",
            SelectQuickMenuLobby(),
            opened.final_snapshot,
            expected=lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
            precondition=handoff.allows,
            retryable_from=handoff.allows,
            on_recovery=handoff.invalidate,
            abort_if=lambda snapshot: (
                handoff.observe(
                    snapshot, lambda item: _is_clean_base(item, SCREEN_LOBBY)
                )
                or _has_incompatible_destination_state(
                    snapshot, origin, SCREEN_LOBBY
                )
            ),
            stable_for=_CLEAN_CONTEXT_STABLE_FOR,
            policy=policy,
        )
        return lobby

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
        opened = transition.execute(
            "precondition.open_quick_menu",
            OpenQuickMenu(),
            initial,
            expected=lambda snapshot: quick_menu_matches_origin(snapshot, origin),
            precondition=lambda snapshot: _is_clean_base(snapshot, origin),
            retryable_from=lambda snapshot: _is_clean_base(snapshot, origin),
            abort_if=lambda snapshot: _has_incompatible_open_quick_menu_state(
                snapshot, origin
            ),
            policy=policy,
        )
        if not opened.succeeded or self.cancel_requested():
            return False
        handoff = QuickMenuHandoff.from_open_result(
            opened, lambda snapshot: _is_clean_base(snapshot, origin),
        )
        if handoff is None:
            return False
        guild = transition.execute(
            "precondition.select_guild",
            select_quick_menu_guild_action(handoff.origin),
            opened.final_snapshot,
            expected=lambda snapshot: _is_clean_base(snapshot, SCREEN_GUILD),
            precondition=handoff.allows,
            retryable_from=handoff.allows,
            on_recovery=handoff.invalidate,
            abort_if=lambda snapshot: (
                handoff.observe(
                    snapshot, lambda item: _is_clean_base(item, SCREEN_GUILD)
                )
                or _has_incompatible_destination_state(
                    snapshot, origin, SCREEN_GUILD
                )
            ),
            stable_for=_CLEAN_CONTEXT_STABLE_FOR,
            policy=policy,
        )
        return guild.succeeded and not self.cancel_requested()

    def _navigate_to_pets_manage(self) -> bool:
        """Normalize an acquired origin to Lobby, then open Pets on Manage."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_PETS_MANAGE):
            return True
        if not _is_clean_base(initial, SCREEN_LOBBY):
            origin = initial.state.base_context
            if (
                origin is None
                or not quick_menu_accessible(origin)
                or not _is_clean_base(initial, origin)
                or not self._navigate_to_lobby()
            ):
                return False
            initial = self.observer.observe()
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
    cancel_token: CancellationToken | None = None,
    registry: FlowRegistry = DEFAULT_FLOW_REGISTRY,
    event_consumers: tuple[RuntimeEventConsumer, ...] = (),
    console: TextIO | None = sys.stdout,
    evidence_root: str | Path = PROJECT_ROOT / "artifacts" / "failure_evidence",
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
        adb = build_adb_client(config)
        if adb.get_state() != "device":
            raise RuntimeError("ADB device is not ready")
        source = build_frame_source(
            config,
            adb_client=adb,
            video_bit_rate=8_000_000,
            max_fps=30,
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
            facts = build_runtime_fact_reader(observer, events=events)
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
                )
            finally:
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
    overlays = set(state.overlays)
    if base == SCREEN_GUILD:
        compatible_overlays = (
            len(overlays & _GUILD_ATTENDANCE_STATES) == 1
            and overlays <= _GUILD_COMPATIBLE_OVERLAYS
        )
    elif base == SCREEN_PETS_MANAGE:
        compatible_overlays = overlays <= {STATUS_PET_SUMMON_DAILY_ACTIVE}
    elif base == SCREEN_BATTLE_MODE_SELECT:
        compatible_overlays = overlays <= {STATUS_WORLD_BOSS_DAILY_ACTIVE, STATUS_MONSTER_WAVE_DAILY_ACTIVE}
    elif base == SCREEN_PET_SUMMON:
        epic = overlays & {
            STATUS_PET_EPIC_AVAILABLE,
            STATUS_PET_EPIC_UNAVAILABLE,
        }
        compatible_overlays = len(epic) == 1 and overlays <= _PET_SUMMON_STATUSES
    else:
        compatible_overlays = not overlays
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == base
        and compatible_overlays
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
