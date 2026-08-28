"""Threaded runtime controller used by the Tk frontend without importing Tk."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from bot.event_log import RuntimeEvent
from bot.flow_contracts import FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowRegistry
from bot.gui_model import GuiExecutionRequest, GuiRunMode
from bot.productive_runtime import CancellationToken, default_log_path, open_productive_runtime
from bot.session import SessionStatus


class GuiRunStatus(str, Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    STOPPING = "Stopping"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    FAILED = "Failed"


class GuiMessageKind(str, Enum):
    EVENT = "event"
    RESULT = "result"


@dataclass(frozen=True)
class GuiExecutionResult:
    status: GuiRunStatus
    duration: float
    log_path: Path
    characters_processed: int = 0
    flows_completed: int = 0
    advances_completed: int = 0
    business_event_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class GuiWorkerMessage:
    kind: GuiMessageKind
    event: RuntimeEvent | None = None
    result: GuiExecutionResult | None = None


class GuiRuntimeController:
    """Own at most one productive runtime worker and expose queue-only output."""

    def __init__(
        self,
        *,
        registry: FlowRegistry = DEFAULT_FLOW_REGISTRY,
        runtime_factory: Callable = open_productive_runtime,
        log_path_factory: Callable = default_log_path,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.runtime_factory = runtime_factory
        self.log_path_factory = log_path_factory
        self.clock = clock
        self.messages: queue.Queue[GuiWorkerMessage] = queue.Queue()
        self._lock = threading.Lock()
        self._active = False
        self._status = GuiRunStatus.IDLE
        self._token: CancellationToken | None = None
        self._thread: threading.Thread | None = None

    @property
    def status(self) -> GuiRunStatus:
        with self._lock:
            return self._status

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._active

    def start(self, request: GuiExecutionRequest) -> None:
        if not isinstance(request, GuiExecutionRequest):
            raise ValueError("request must be GuiExecutionRequest")
        definitions = self.registry.select(request.flow_ids)
        token = CancellationToken()
        with self._lock:
            if self._active:
                raise RuntimeError("a runtime execution is already active")
            self._active = True
            self._status = GuiRunStatus.RUNNING
            self._token = token
            worker = threading.Thread(
                target=self._worker,
                args=(request, definitions, token),
                name="kritika-runtime-worker",
                daemon=False,
            )
            self._thread = worker
        worker.start()

    def stop_safely(self) -> bool:
        with self._lock:
            if not self._active or self._token is None:
                return False
            self._status = GuiRunStatus.STOPPING
            token = self._token
        token.request()
        return True

    def drain(self, *, limit: int = 200) -> tuple[GuiWorkerMessage, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        items = []
        for _ in range(limit):
            try:
                items.append(self.messages.get_nowait())
            except queue.Empty:
                break
        return tuple(items)

    def wait(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _worker(self, request, definitions, token) -> None:
        started = self.clock()
        kind = "flow_" + definitions[0].id if request.mode is GuiRunMode.FLOW_ONCE else "session"
        log_path = self.log_path_factory(kind, directory=request.log_dir)
        try:
            with self.runtime_factory(
                dotenv_path=request.dotenv_path,
                log_path=log_path,
                debug=request.debug,
                cancel_token=token,
                registry=self.registry,
                event_consumers=(self._enqueue_event,),
                console=None,
            ) as runtime:
                if request.mode is GuiRunMode.FLOW_ONCE:
                    raw = runtime.run_flow(definitions[0])
                    result = GuiExecutionResult(
                        _flow_status(raw.status),
                        max(0.0, self.clock() - started),
                        log_path,
                        characters_processed=int(raw.status is FlowStatus.COMPLETED),
                        flows_completed=int(raw.status is FlowStatus.COMPLETED),
                        business_event_count=len(raw.events),
                        error=raw.error,
                    )
                else:
                    raw = runtime.run_session(
                        definitions,
                        character_count=request.character_count,
                    )
                    result = GuiExecutionResult(
                        _session_status(raw.status),
                        max(0.0, self.clock() - started),
                        log_path,
                        characters_processed=raw.characters_processed,
                        flows_completed=sum(
                            flow.status is FlowStatus.COMPLETED
                            for character in raw.character_results
                            for flow in character.flow_results
                        ),
                        advances_completed=raw.advances_completed,
                        business_event_count=len(raw.events),
                        error=raw.failure_cause,
                    )
        except Exception as error:
            result = GuiExecutionResult(
                GuiRunStatus.FAILED,
                max(0.0, self.clock() - started),
                log_path,
                error=f"{type(error).__name__}: {error}",
            )
        with self._lock:
            self._status = result.status
            self._active = False
            self._token = None
        self.messages.put(GuiWorkerMessage(GuiMessageKind.RESULT, result=result))

    def _enqueue_event(self, event: RuntimeEvent) -> None:
        self.messages.put(GuiWorkerMessage(GuiMessageKind.EVENT, event=event))


def _flow_status(status: FlowStatus) -> GuiRunStatus:
    return {
        FlowStatus.COMPLETED: GuiRunStatus.COMPLETED,
        FlowStatus.CANCELLED: GuiRunStatus.CANCELLED,
        FlowStatus.FAILED: GuiRunStatus.FAILED,
    }[status]


def _session_status(status: SessionStatus) -> GuiRunStatus:
    return {
        SessionStatus.COMPLETED: GuiRunStatus.COMPLETED,
        SessionStatus.CANCELLED: GuiRunStatus.CANCELLED,
        SessionStatus.FAILED: GuiRunStatus.FAILED,
    }[status]


__all__ = (
    "GuiExecutionResult",
    "GuiMessageKind",
    "GuiRunStatus",
    "GuiRuntimeController",
    "GuiWorkerMessage",
)
