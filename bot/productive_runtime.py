"""Reusable productive composition for CLI and the future GUI."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TextIO
from uuid import uuid4

from bot.action_executor import ActionExecutor
from bot.auto_battle import AutoBattleDetector, AutoBattleEnsurer
from bot.catalog import (
    MENU_QUICK,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_WORLD_BOSS,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    build_default_resolver,
)
from bot.config import RuntimeConfig
from bot.event_log import RuntimeEventConsumer, RuntimeEventStream, build_runtime_event_stream
from bot.equipment_combine_relief import EquipmentCombineRelief
from bot.flow_contracts import FlowResult, FlowStatus, PerCharacterFlow
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowDefinition, FlowRegistry
from bot.perception import build_default_perception
from bot.preconditions import MinimalPreconditionEnsurer
from bot.quick_menu import quick_menu_accessible, select_quick_menu_guild_action
from bot.rotation import StandardRotation
from bot.runtime import build_adb_client, build_frame_source, build_runtime_fact_reader
from bot.runtime_observer import RuntimeObserver, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import OpenGuild, OpenQuickMenu, SelectQuickMenuLobby
from bot.session import SessionPlan, SessionResult, SessionRunner
from bot.socket_inventory_relief import SocketInventoryRelief
from bot.state import ResolutionStatus
from bot.tap_through_animation import TapThroughAnimation
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CLEAN_CONTEXTS = frozenset({SCREEN_GUILD, SCREEN_LOBBY, SCREEN_WORLD_BOSS})
_GUILD_ATTENDANCE_STATES = frozenset(
    {STATUS_GUILD_ATTENDANCE_ACTIVE, STATUS_GUILD_ATTENDANCE_COMPLETED}
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


@dataclass
class ProductiveRuntime:
    config: RuntimeConfig
    observer: RuntimeObserver
    actions: ActionExecutor
    facts: object
    auto_battle: AutoBattleEnsurer
    socket_relief: SocketInventoryRelief
    equipment_combine_relief: EquipmentCombineRelief
    events: RuntimeEventStream
    cancel_token: CancellationToken
    registry: FlowRegistry = DEFAULT_FLOW_REGISTRY

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
            lambda: self._current_clean_context(),
            navigate_to_lobby=self._navigate_to_lobby,
            navigate_lobby_to_guild=self._navigate_lobby_to_guild,
            navigate_to_guild=self._navigate_to_guild,
        )

    def build_rotation(self, character_count: int) -> StandardRotation:
        return StandardRotation(
            self.observer,
            self.actions,
            self.events,
            character_count=character_count,
            verified_transition=VerifiedTransition(
                self.observer, self.actions, self.events
            ),
        )

    def run_flow(self, definition: FlowDefinition) -> FlowResult:
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
                    result = flow.run()
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
            FlowStatus.COMPLETED: "flow.completed",
            FlowStatus.CANCELLED: "flow.cancelled",
            FlowStatus.FAILED: "flow.failed",
        }[result.status]
        self.events.record(
            event,
            component=flow.name,
            flow=flow.name,
            error=result.error,
            business_event_count=len(result.events),
        )
        for business_event in result.events:
            event_name = (
                business_event.kind
                if business_event.kind.startswith(f"{flow.name}.")
                else f"{flow.name}.{business_event.kind}"
            )
            self.events.record(
                event_name,
                character_index=1,
                character_name=None,
                detail=business_event.detail,
            )
        return result

    def run_session(
        self,
        definitions: tuple[FlowDefinition, ...],
        *,
        character_count: int,
    ) -> SessionResult:
        flows = self.build_flows(definitions)
        rotation = self.build_rotation(character_count)
        plan = SessionPlan.standard(
            flows=flows,
            rotation_strategy=rotation,
            character_count=character_count,
        )
        return SessionRunner(
            plan,
            preconditions=self.build_preconditions(),
            events=self.events,
            cancel_requested=self.cancel_requested,
        ).run()

    def _current_clean_context(self) -> str | None:
        try:
            initial = self.observer.observe()
            if _is_clean_known_context(initial):
                return initial.state.base_context
            settled = self.observer.wait_until(
                _is_clean_known_context,
                after_sequence=initial.sequence,
                timeout=_CLEAN_CONTEXT_TIMEOUT,
                stable_for=_CLEAN_CONTEXT_STABLE_FOR,
                cancel_requested=self.cancel_requested,
            )
            return settled.state.base_context
        except RuntimeWaitTimeout as error:
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
            return None
        except RuntimeWaitCancelled:
            return None

    def _navigate_to_lobby(self) -> bool:
        """Normalize any acquired Quick Menu-capable origin to Lobby."""

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
        transition = VerifiedTransition(self.observer, self.actions, self.events)
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        opened = transition.execute(
            "precondition.open_quick_menu",
            OpenQuickMenu(),
            initial,
            expected=_has_quick_menu,
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
            return False
        lobby = transition.execute(
            "precondition.select_lobby",
            SelectQuickMenuLobby(),
            opened.final_snapshot,
            expected=lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
            precondition=_has_quick_menu,
            retryable_from=_has_quick_menu,
            abort_if=lambda snapshot: _has_incompatible_destination_state(
                snapshot, origin, SCREEN_LOBBY
            ),
            stable_for=_CLEAN_CONTEXT_STABLE_FOR,
            policy=policy,
        )
        return lobby.succeeded and not self.cancel_requested()

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
        transition = VerifiedTransition(self.observer, self.actions, self.events)
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        opened = transition.execute(
            "precondition.open_quick_menu",
            OpenQuickMenu(),
            initial,
            expected=_has_quick_menu,
            precondition=lambda snapshot: _is_clean_base(snapshot, origin),
            retryable_from=lambda snapshot: _is_clean_base(snapshot, origin),
            abort_if=lambda snapshot: _has_incompatible_open_quick_menu_state(
                snapshot, origin
            ),
            policy=policy,
        )
        if not opened.succeeded or self.cancel_requested():
            return False
        guild = transition.execute(
            "precondition.select_guild",
            select_quick_menu_guild_action(origin),
            opened.final_snapshot,
            expected=lambda snapshot: _is_clean_base(snapshot, SCREEN_GUILD),
            precondition=_has_quick_menu,
            retryable_from=_has_quick_menu,
            abort_if=lambda snapshot: _has_incompatible_destination_state(
                snapshot, origin, SCREEN_GUILD
            ),
            stable_for=_CLEAN_CONTEXT_STABLE_FOR,
            policy=policy,
        )
        return guild.succeeded and not self.cancel_requested()

    def _navigate_lobby_to_guild(self) -> bool:
        """Use the acquired direct Lobby target and verify Guild."""

        initial = self.observer.observe()
        if _is_clean_base(initial, SCREEN_GUILD):
            return True
        if not _is_clean_base(initial, SCREEN_LOBBY):
            return False
        transition = VerifiedTransition(self.observer, self.actions, self.events)
        policy = VerifiedTransitionPolicy(
            normal_timeout=6.0,
            grace_timeout=2.0,
            max_attempts=2,
        )
        guild = transition.execute(
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
) -> Iterator[ProductiveRuntime]:
    """Acquire every productive runtime dependency and guarantee source cleanup."""

    token = cancel_token or CancellationToken()
    events = build_runtime_event_stream(
        log_path,
        debug=debug,
        console=console,
        consumers=event_consumers,
    )
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
            )
            facts = build_runtime_fact_reader(observer, events=events)
            auto_battle = AutoBattleEnsurer(AutoBattleDetector(observer), actions)
            transition = VerifiedTransition(observer, actions, events)
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
            yield ProductiveRuntime(
                config,
                observer,
                actions,
                facts,
                auto_battle,
                socket_relief,
                equipment_combine_relief,
                events,
                token,
                registry,
            )
        events.record("runtime.completed")
    except BaseException as error:
        events.record(
            "runtime.failed",
            error=f"{type(error).__name__}: {error}",
        )
        raise
    finally:
        events.record("runtime.closed")


def default_log_path(kind: str, *, directory: str | Path = PROJECT_ROOT / "logs") -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session_id = uuid4().hex[:8]
    return Path(directory) / f"{timestamp}_{kind}_{session_id}.log"


def _is_clean_known_context(snapshot) -> bool:
    state = snapshot.state
    return state.base_context in _CLEAN_CONTEXTS and _is_clean_base(
        snapshot, state.base_context
    )


def _is_clean_base(snapshot, base: str) -> bool:
    state = snapshot.state
    overlays = set(state.overlays)
    compatible_overlays = (
        len(overlays) == 1 and overlays <= _GUILD_ATTENDANCE_STATES
        if base == SCREEN_GUILD
        else not overlays
    )
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
    if _has_quick_menu(snapshot) or _is_clean_base(snapshot, origin):
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
