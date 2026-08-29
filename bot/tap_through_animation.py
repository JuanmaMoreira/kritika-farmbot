"""Bounded observe/tap primitive for already-started skippable animations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Integral, Real
import time
from typing import Callable

from bot.event_log import EventSink
from bot.runtime_observer import (
    RuntimeSnapshot,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)


class TapThroughOutcome(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    MAX_TAPS = "max_taps"
    INCOMPATIBLE_STATE = "incompatible_state"
    FAILED = "failed"


@dataclass(frozen=True)
class TapThroughPolicy:
    tap_interval: float = 0.5
    timeout: float = 12.0
    max_taps: int = 20

    def __post_init__(self) -> None:
        interval = _positive_finite(self.tap_interval, "tap_interval")
        timeout = _positive_finite(self.timeout, "timeout")
        taps = self.max_taps
        if isinstance(taps, bool) or not isinstance(taps, Integral) or taps <= 0:
            raise ValueError("max_taps must be a positive integer")
        object.__setattr__(self, "tap_interval", interval)
        object.__setattr__(self, "timeout", timeout)
        object.__setattr__(self, "max_taps", int(taps))


@dataclass(frozen=True)
class TapThroughResult:
    outcome: TapThroughOutcome
    tap_count: int
    final_snapshot: RuntimeSnapshot
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome is TapThroughOutcome.COMPLETED


class TapThroughAnimation:
    """Alternate fresh observations and guarded taps until completion."""

    def __init__(
        self,
        observer,
        actions,
        events: EventSink | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(getattr(observer, "wait_until", None)):
            raise ValueError("observer must provide wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if events is not None and not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if not callable(clock) or not callable(sleeper):
            raise ValueError("clock and sleeper must be callable")
        self.observer = observer
        self.actions = actions
        self.events = events
        self.clock = clock
        self.sleeper = sleeper

    def run(
        self,
        initial: RuntimeSnapshot,
        *,
        action,
        expected: Callable[[RuntimeSnapshot], bool],
        tappable: Callable[[RuntimeSnapshot], bool],
        transient: Callable[[RuntimeSnapshot], bool],
        cancel_requested: Callable[[], bool] = lambda: False,
        policy: TapThroughPolicy | None = None,
    ) -> TapThroughResult:
        if not isinstance(initial, RuntimeSnapshot):
            raise ValueError("initial must be a RuntimeSnapshot")
        for name, predicate in (
            ("expected", expected),
            ("tappable", tappable),
            ("transient", transient),
            ("cancel_requested", cancel_requested),
        ):
            if not callable(predicate):
                raise ValueError(f"{name} must be callable")
        policy = policy or TapThroughPolicy()
        if not isinstance(policy, TapThroughPolicy):
            raise ValueError("policy must be a TapThroughPolicy")

        started = self.clock()
        deadline = started + policy.timeout
        current = initial
        tap_count = 0
        self._record("tap_through.started", sequence=current.sequence)

        while True:
            if cancel_requested():
                return self._finish(
                    TapThroughOutcome.CANCELLED, tap_count, current
                )
            if expected(current):
                return self._finish(
                    TapThroughOutcome.COMPLETED, tap_count, current
                )
            if tappable(current):
                if tap_count >= policy.max_taps:
                    return self._finish(
                        TapThroughOutcome.MAX_TAPS,
                        tap_count,
                        current,
                        "maximum guarded taps reached",
                    )
                try:
                    self.actions.execute(action, current.geometry)
                except Exception as error:
                    return self._finish(
                        TapThroughOutcome.FAILED,
                        tap_count,
                        current,
                        f"{type(error).__name__}: {error}",
                    )
                tap_count += 1
                self._record(
                    "tap_through.tap",
                    sequence=current.sequence,
                    tap_count=tap_count,
                )
                remaining = deadline - self.clock()
                if remaining <= 0:
                    return self._finish(
                        TapThroughOutcome.TIMEOUT, tap_count, current
                    )
                self.sleeper(min(policy.tap_interval, remaining))
            elif not transient(current):
                return self._finish(
                    TapThroughOutcome.INCOMPATIBLE_STATE,
                    tap_count,
                    current,
                    "fresh snapshot is neither completion, tappable nor transient",
                )

            remaining = deadline - self.clock()
            if remaining <= 0:
                return self._finish(
                    TapThroughOutcome.TIMEOUT, tap_count, current
                )
            try:
                current = self.observer.wait_until(
                    lambda _: True,
                    after_sequence=current.sequence,
                    timeout=remaining,
                    cancel_requested=cancel_requested,
                )
            except RuntimeWaitCancelled:
                return self._finish(
                    TapThroughOutcome.CANCELLED, tap_count, current
                )
            except RuntimeWaitTimeout:
                return self._finish(
                    TapThroughOutcome.TIMEOUT, tap_count, current
                )
            except Exception as error:
                return self._finish(
                    TapThroughOutcome.FAILED,
                    tap_count,
                    current,
                    f"{type(error).__name__}: {error}",
                )

    def _finish(self, outcome, tap_count, snapshot, error=None):
        self._record(
            "tap_through.finished",
            outcome=outcome.value,
            tap_count=tap_count,
            sequence=snapshot.sequence,
            error=error,
        )
        return TapThroughResult(outcome, tap_count, snapshot, error)

    def _record(self, event: str, **fields: object) -> None:
        if self.events is None:
            return
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _positive_finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


__all__ = (
    "TapThroughAnimation",
    "TapThroughOutcome",
    "TapThroughPolicy",
    "TapThroughResult",
)
