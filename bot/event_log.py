"""Structured runtime events with console, file, and subscriber sinks."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, TextIO

from bot.observations import validate_semantic_name


class EventSink(Protocol):
    def record(self, event: str, **fields: object) -> None: ...


class EventLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


@dataclass(frozen=True)
class RuntimeEvent:
    timestamp: datetime
    level: EventLevel
    component: str
    event: str
    fields: Mapping[str, object] = field(default_factory=dict)
    message: str | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            object.__setattr__(self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc))
        if not isinstance(self.level, EventLevel):
            raise ValueError("level must be EventLevel")
        object.__setattr__(self, "event", validate_semantic_name(self.event))
        if not isinstance(self.component, str) or not self.component.strip():
            raise ValueError("component must be a non-empty string")
        object.__setattr__(self, "component", self.component.strip())
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def payload(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "level": self.level.name,
            "component": self.component,
            "event": self.event,
            "message": self.message,
            **self.fields,
        }


RuntimeEventConsumer = Callable[[RuntimeEvent], None]


class ConsoleEventConsumer:
    """Human-readable rendering of structured events."""

    def __init__(
        self,
        *,
        minimum_level: EventLevel = EventLevel.INFO,
        stream: TextIO = sys.stdout,
    ) -> None:
        self.minimum_level = minimum_level
        self.stream = stream

    def __call__(self, item: RuntimeEvent) -> None:
        if item.level < self.minimum_level:
            return
        print(format_runtime_event(item), file=self.stream, flush=True)


class JsonLineEventConsumer:
    """Persist every structured event as one shareable JSON line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path == Path("."):
            raise ValueError("path must identify a log file")
        self._lock = threading.Lock()

    def __call__(self, item: RuntimeEvent) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item.payload(), sort_keys=True, default=str) + "\n")


class RuntimeEventStream:
    """Fan structured events out to console, persistence, and future GUI consumers."""

    def __init__(
        self,
        consumers: tuple[RuntimeEventConsumer, ...] = (),
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not callable(now):
            raise ValueError("now must be callable")
        self._now = now
        self._consumers = list(consumers)
        self._lock = threading.Lock()

    def subscribe(self, consumer: RuntimeEventConsumer) -> Callable[[], None]:
        if not callable(consumer):
            raise ValueError("consumer must be callable")
        with self._lock:
            self._consumers.append(consumer)

        def unsubscribe() -> None:
            with self._lock:
                if consumer in self._consumers:
                    self._consumers.remove(consumer)

        return unsubscribe

    def emit(
        self,
        level: EventLevel,
        component: str,
        event: str,
        *,
        message: str | None = None,
        **fields: object,
    ) -> RuntimeEvent:
        item = RuntimeEvent(self._now(), level, component, event, fields, message)
        with self._lock:
            consumers = tuple(self._consumers)
        for consumer in consumers:
            try:
                consumer(item)
            except Exception:
                # Observability must never alter gameplay policy or trigger input.
                continue
        return item

    def record(self, event: str, **fields: object) -> None:
        level_value = fields.pop("level", None)
        component_value = fields.pop("component", None)
        message = fields.pop("message", None)
        level, component = _event_metadata(event)
        if level_value is not None:
            level = _coerce_level(level_value)
        if component_value is not None:
            component = str(component_value)
        self.emit(level, component, event, message=message if isinstance(message, str) else None, **fields)


class JsonLineEventLog:
    """Append timestamp + event JSON records without import-time side effects."""

    def __init__(
        self,
        path: str | Path,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.path = Path(path)
        if self.path == Path("."):
            raise ValueError("path must identify a log file")
        self._now = now
        self._lock = threading.Lock()

    def record(self, event: str, **fields: object) -> None:
        name = validate_semantic_name(event)
        timestamp = self._now()
        if not isinstance(timestamp, datetime):
            raise ValueError("now() must return datetime")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        payload = dict(fields)
        payload.update({
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "event": name,
        })
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, sort_keys=True) + "\n")


def build_runtime_event_stream(
    path: str | Path,
    *,
    debug: bool = False,
    console: TextIO | None = sys.stdout,
    consumers: tuple[RuntimeEventConsumer, ...] = (),
) -> RuntimeEventStream:
    minimum = EventLevel.DEBUG if debug else EventLevel.INFO
    configured: list[RuntimeEventConsumer] = []
    if console is not None:
        configured.append(ConsoleEventConsumer(minimum_level=minimum, stream=console))
    configured.append(JsonLineEventConsumer(path))
    configured.extend(consumers)
    return RuntimeEventStream(tuple(configured))


def format_runtime_event(item: RuntimeEvent) -> str:
    """Render one structured event consistently for console and GUI views."""

    if not isinstance(item, RuntimeEvent):
        raise ValueError("item must be RuntimeEvent")
    timestamp = item.timestamp.astimezone().strftime("%H:%M:%S.%f")[:-3]
    level = "WARN" if item.level is EventLevel.WARNING else item.level.name
    fields = " ".join(
        f"{name}={_human_value(value)}" for name, value in item.fields.items()
        if value is not None
    )
    detail = item.message or item.event
    suffix = f" {fields}" if fields else ""
    return f"{timestamp} {level:<5} {item.component:<16} {detail}{suffix}"


def _event_metadata(event: str) -> tuple[EventLevel, str]:
    name = validate_semantic_name(event)
    if name.startswith("transition.") or ".transition" in name:
        return EventLevel.DEBUG, "transition"
    if name.startswith("controlled_wait.") or ".controlled_wait" in name or ".wait." in name:
        return EventLevel.DEBUG, "controlled_wait"
    if name.startswith("fact.") or name.endswith("_read"):
        return EventLevel.DEBUG, "facts"
    component = name.split(".", 1)[0]
    if name.endswith(".failed") or ".failure" in name or "unexpected_state" in name:
        return EventLevel.ERROR, component
    if any(marker in name for marker in ("inventory_full", "low_gold", "insufficient_sapphires", "timeout")):
        return EventLevel.WARNING, component
    return EventLevel.INFO, component


def _coerce_level(value: object) -> EventLevel:
    if isinstance(value, EventLevel):
        return value
    if isinstance(value, str):
        try:
            return EventLevel[value.upper()]
        except KeyError as error:
            raise ValueError(f"unknown event level: {value}") from error
    raise ValueError("level must be EventLevel or its name")


def _human_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


__all__ = (
    "ConsoleEventConsumer",
    "EventLevel",
    "EventSink",
    "JsonLineEventConsumer",
    "JsonLineEventLog",
    "RuntimeEvent",
    "RuntimeEventConsumer",
    "RuntimeEventStream",
    "build_runtime_event_stream",
    "format_runtime_event",
)
