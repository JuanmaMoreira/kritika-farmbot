"""Small persistent event log for early runtime outcomes."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from bot.observations import validate_semantic_name


class EventSink(Protocol):
    def record(self, event: str) -> None: ...


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

    def record(self, event: str) -> None:
        name = validate_semantic_name(event)
        timestamp = self._now()
        if not isinstance(timestamp, datetime):
            raise ValueError("now() must return datetime")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        payload = {
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "event": name,
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, sort_keys=True) + "\n")


__all__ = ("EventSink", "JsonLineEventLog")
