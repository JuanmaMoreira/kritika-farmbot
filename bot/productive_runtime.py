"""Reusable productive composition for CLI and the future GUI."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from bot.action_executor import ActionExecutor
from bot.auto_battle import AutoBattleDetector, AutoBattleEnsurer
from bot.catalog import SCREEN_LOBBY, SCREEN_WORLD_BOSS, build_default_resolver
from bot.config import RuntimeConfig
from bot.event_log import RuntimeEventStream, build_runtime_event_stream
from bot.flow_contracts import FlowResult, FlowStatus, PerCharacterFlow
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowDefinition, FlowRegistry
from bot.perception import build_default_perception
from bot.preconditions import MinimalPreconditionEnsurer
from bot.rotation import StandardRotation
from bot.runtime import build_adb_client, build_frame_source, build_runtime_fact_reader
from bot.runtime_observer import RuntimeObserver, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.session import SessionPlan, SessionResult, SessionRunner
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CLEAN_CONTEXTS = frozenset({SCREEN_LOBBY, SCREEN_WORLD_BOSS})


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
        return MinimalPreconditionEnsurer(lambda: self._current_clean_context())

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
                timeout=2.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            return settled.state.base_context
        except (RuntimeWaitTimeout, RuntimeWaitCancelled):
            return None


@contextmanager
def open_productive_runtime(
    *,
    dotenv_path: str | Path = PROJECT_ROOT / ".env",
    log_path: str | Path,
    debug: bool = False,
    cancel_token: CancellationToken | None = None,
    registry: FlowRegistry = DEFAULT_FLOW_REGISTRY,
) -> Iterator[ProductiveRuntime]:
    """Acquire every productive runtime dependency and guarantee source cleanup."""

    token = cancel_token or CancellationToken()
    events = build_runtime_event_stream(log_path, debug=debug)
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
            yield ProductiveRuntime(
                config,
                observer,
                actions,
                facts,
                auto_battle,
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
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context in _CLEAN_CONTEXTS
        and not state.overlays
    )


__all__ = (
    "CancellationToken",
    "ProductiveRuntime",
    "default_log_path",
    "open_productive_runtime",
)
