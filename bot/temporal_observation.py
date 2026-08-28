"""Small bounded primitive for fresh multi-frame runtime observations."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable

from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)


class TemporalWindowStatus(str, Enum):
    COMPLETE = "complete"
    CONTEXT_MISMATCH = "context_mismatch"
    INTERRUPTED = "interrupted"
    INSUFFICIENT = "insufficient"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILURE = "failure"


@dataclass(frozen=True)
class TemporalWindow:
    status: TemporalWindowStatus
    snapshots: tuple[RuntimeSnapshot, ...] = ()
    detail: str | None = None

    @property
    def last_sequence(self) -> int | None:
        return self.snapshots[-1].sequence if self.snapshots else None

    @property
    def duration(self) -> float:
        if len(self.snapshots) < 2:
            return 0.0
        return self.snapshots[-1].timestamp - self.snapshots[0].timestamp


class TemporalObserver:
    """Acquire a fixed-size sequence through RuntimeObserver only."""

    def __init__(
        self,
        observer: RuntimeObserver,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(observer, RuntimeObserver):
            raise ValueError("observer must be a RuntimeObserver")
        self.observer = observer
        self._clock = clock

    def collect(
        self,
        *,
        after_sequence: int,
        context: str,
        frame_count: int,
        sample_interval: float,
        timeout: float,
        interrupt_overlays: frozenset[str] = frozenset(),
        cancel_requested: Callable[[], bool] | None = None,
    ) -> TemporalWindow:
        after = _sequence(after_sequence)
        count = _frame_count(frame_count)
        interval = _non_negative(sample_interval, "sample_interval")
        duration = _positive(timeout, "timeout")
        deadline = self._clock() + duration
        snapshots: list[RuntimeSnapshot] = []
        cursor = after
        try:
            while len(snapshots) < count:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return TemporalWindow(
                        TemporalWindowStatus.TIMEOUT,
                        tuple(snapshots),
                        "temporal observation deadline expired",
                    )
                snapshot = self.observer.wait_until(
                    lambda item: (
                        not snapshots
                        or item.timestamp - snapshots[-1].timestamp >= interval
                    ),
                    after_sequence=cursor,
                    timeout=remaining,
                    cancel_requested=cancel_requested,
                )
                cursor = snapshot.sequence
                snapshots.append(snapshot)
                if snapshot.state.base_context != context:
                    return TemporalWindow(
                        TemporalWindowStatus.CONTEXT_MISMATCH,
                        tuple(snapshots),
                        f"fresh frame is not {context}",
                    )
                interruption = interrupt_overlays.intersection(snapshot.state.overlays)
                if interruption:
                    return TemporalWindow(
                        TemporalWindowStatus.INTERRUPTED,
                        tuple(snapshots),
                        f"observation interrupted by {sorted(interruption)[0]}",
                    )
        except RuntimeWaitCancelled:
            return TemporalWindow(TemporalWindowStatus.CANCELLED, tuple(snapshots))
        except RuntimeWaitTimeout:
            return TemporalWindow(
                TemporalWindowStatus.TIMEOUT,
                tuple(snapshots),
                "no fresh frame arrived before the deadline",
            )
        except Exception as error:
            return TemporalWindow(
                TemporalWindowStatus.FAILURE, tuple(snapshots), str(error)
            )
        if len(snapshots) < 2:
            return TemporalWindow(
                TemporalWindowStatus.INSUFFICIENT,
                tuple(snapshots),
                "at least two fresh frames are required",
            )
        return TemporalWindow(TemporalWindowStatus.COMPLETE, tuple(snapshots))


def _sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("after_sequence must be a non-negative integer")
    return int(value)


def _frame_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 2:
        raise ValueError("frame_count must be an integer >= 2")
    return int(value)


def _positive(value: object, name: str) -> float:
    result = _non_negative(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


__all__ = ("TemporalObserver", "TemporalWindow", "TemporalWindowStatus")
