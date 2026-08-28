"""Shared thin CLI helpers for productive manual launchers."""

from __future__ import annotations

import signal
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from bot.flow_contracts import FlowResult
from bot.flow_registry import DEFAULT_FLOW_REGISTRY, FlowRegistry
from bot.productive_runtime import CancellationToken
from bot.session import SessionResult


EXIT_COMPLETED = 0
EXIT_FAILED = 1
EXIT_USAGE_OR_RUNTIME = 2
EXIT_CANCELLED = 130


def print_flows(registry: FlowRegistry = DEFAULT_FLOW_REGISTRY) -> None:
    for definition in registry.definitions:
        print(f"{definition.id:<16}{definition.display_name}")


@contextmanager
def cancellation_signals(token: CancellationToken) -> Iterator[None]:
    previous = signal.getsignal(signal.SIGINT)
    calls = 0

    def request_cancel(signum, frame):
        nonlocal calls
        calls += 1
        token.request()
        if calls > 1:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, request_cancel)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def flow_summary(result: FlowResult, log_path: Path) -> str:
    details = [f"result={result.status.value.upper()}"]
    if result.events:
        details.append("events=" + ",".join(item.kind for item in result.events))
    if result.error:
        details.append(f"error={result.error}")
    details.append(f"log={log_path}")
    return " ".join(details)


def session_summary(result: SessionResult, log_path: Path) -> str:
    details = [
        f"result={result.status.value.upper()}",
        f"characters={result.characters_processed}",
        f"advances={result.advances_completed}",
    ]
    if result.failure_character_index is not None:
        details.append(f"failure_character={result.failure_character_index}")
    if result.failure_flow:
        details.append(f"failure_flow={result.failure_flow}")
    if result.failure_cause:
        details.append(f"error={result.failure_cause}")
    details.append(f"log={log_path}")
    return " ".join(details)


def print_error(message: str) -> None:
    print(message, file=sys.stderr)


__all__ = (
    "EXIT_CANCELLED",
    "EXIT_COMPLETED",
    "EXIT_FAILED",
    "EXIT_USAGE_OR_RUNTIME",
    "cancellation_signals",
    "flow_summary",
    "print_error",
    "print_flows",
    "session_summary",
)
