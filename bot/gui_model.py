"""Small Tk-independent models for the operational GUI."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from bot.config import DEFAULT_CHARACTER_COUNT
from bot.event_log import EventLevel, RuntimeEvent
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowRegistry
from bot.productive_runtime import PROJECT_ROOT


@dataclass(frozen=True)
class GuiFlowOption:
    id: str
    display_name: str
    enabled: bool


class FlowSelectionModel:
    """Ordered enabled/disabled projection of the productive FlowRegistry."""

    def __init__(self, registry: FlowRegistry = DEFAULT_FLOW_REGISTRY) -> None:
        self.registry = registry
        self._order = [item.id for item in registry.definitions]
        self._enabled = set(self._order)

    @property
    def options(self) -> tuple[GuiFlowOption, ...]:
        return tuple(
            GuiFlowOption(
                flow_id,
                self.registry.get(flow_id).display_name,
                flow_id in self._enabled,
            )
            for flow_id in self._order
        )

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(flow_id for flow_id in self._order if flow_id in self._enabled)

    def set_enabled(self, flow_id: str, enabled: bool) -> None:
        self.registry.get(flow_id)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be bool")
        if enabled:
            self._enabled.add(flow_id)
        else:
            self._enabled.discard(flow_id)

    def toggle(self, flow_id: str) -> None:
        self.set_enabled(flow_id, flow_id not in self._enabled)

    def move_up(self, flow_id: str) -> bool:
        return self._move(flow_id, -1)

    def move_down(self, flow_id: str) -> bool:
        return self._move(flow_id, 1)

    def _move(self, flow_id: str, delta: int) -> bool:
        self.registry.get(flow_id)
        index = self._order.index(flow_id)
        target = index + delta
        if target < 0 or target >= len(self._order):
            return False
        self._order[index], self._order[target] = self._order[target], self._order[index]
        return True


class GuiRunMode(str, Enum):
    FLOW_ONCE = "flow_once"
    SESSION = "session"


class SessionElapsedTimer:
    """Monotonic presentation state for the productive Run Session timer."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._started_at: float | None = None
        self._elapsed = 0.0

    @property
    def running(self) -> bool:
        return self._started_at is not None

    @property
    def text(self) -> str:
        total_seconds = int(max(0.0, self._elapsed))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def start(self) -> str:
        self._started_at = self.clock()
        self._elapsed = 0.0
        return self.text

    def update(self) -> str:
        if self._started_at is not None:
            self._elapsed = max(0.0, self.clock() - self._started_at)
        return self.text

    def finish(self, duration: float) -> str:
        self._elapsed = max(0.0, float(duration))
        self._started_at = None
        return self.text


@dataclass(frozen=True)
class GuiExecutionRequest:
    mode: GuiRunMode
    flow_ids: tuple[str, ...]
    character_count: int = DEFAULT_CHARACTER_COUNT
    debug: bool = False
    dotenv_path: Path = PROJECT_ROOT / ".env"
    log_dir: Path = PROJECT_ROOT / "logs"

    @classmethod
    def flow_once(
        cls,
        flow_ids,
        *,
        debug: bool = False,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
    ) -> "GuiExecutionRequest":
        values = tuple(flow_ids)
        if len(values) != 1:
            raise ValueError("Run Flow Once requires exactly one active flow")
        return cls(GuiRunMode.FLOW_ONCE, values, 1, debug, Path(dotenv_path), Path(log_dir))

    @classmethod
    def session(
        cls,
        flow_ids,
        character_count: int,
        *,
        debug: bool = False,
        dotenv_path: Path = PROJECT_ROOT / ".env",
        log_dir: Path = PROJECT_ROOT / "logs",
    ) -> "GuiExecutionRequest":
        values = tuple(flow_ids)
        if not values:
            raise ValueError("Run Session requires at least one active flow")
        if isinstance(character_count, bool) or not isinstance(character_count, int) or character_count <= 0:
            raise ValueError("Characters must be a positive integer")
        return cls(
            GuiRunMode.SESSION,
            values,
            character_count,
            debug,
            Path(dotenv_path),
            Path(log_dir),
        )


@dataclass
class GuiProgress:
    character: str = "-"
    flow: str = "-"
    state: str = "-"
    flows_completed: int = 0

    def apply(self, event: RuntimeEvent, registry: FlowRegistry = DEFAULT_FLOW_REGISTRY) -> None:
        name = event.event
        fields = event.fields
        if name == "session.character.started":
            self.character = f"{fields.get('character_index', '-')} / {fields.get('character_count', '-')}"
            self.state = "Running"
        elif name == "flow.started":
            flow_id = fields.get("flow")
            try:
                self.flow = registry.get(str(flow_id)).display_name
            except KeyError:
                self.flow = str(flow_id or "-")
            self.state = "Running flow"
        elif name == "flow.completed":
            self.flows_completed += 1
        elif name == "rotation.started":
            self.flow = "-"
            self.state = "Rotation"
        elif name in {"world_boss.wait.started", "controlled_wait.started"}:
            self.state = "Waiting"
        elif name == "session.completed":
            self.state = "Completed"


def event_visible(event: RuntimeEvent, *, debug: bool) -> bool:
    return debug or event.level >= EventLevel.INFO


__all__ = (
    "FlowSelectionModel",
    "GuiExecutionRequest",
    "GuiFlowOption",
    "GuiProgress",
    "GuiRunMode",
    "SessionElapsedTimer",
    "event_visible",
)
