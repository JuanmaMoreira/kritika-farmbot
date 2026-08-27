"""Bounded, cancellable waits for long-running in-game activity."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Callable


class ControlledWaitOutcome(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass(frozen=True)
class ControlledWaitResult:
    outcome: ControlledWaitOutcome
    elapsed: float
    poll_count: int
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome is ControlledWaitOutcome.COMPLETED


class ControlledWait:
    """Wait without busy-looping, using a monotonic duration or deadline."""

    def __init__(
        self,
        *,
        check_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.check_interval = _positive_duration(
            check_interval, "check_interval"
        )
        if not callable(clock):
            raise ValueError("clock must be callable")
        if not callable(sleeper):
            raise ValueError("sleeper must be callable")
        self._clock = clock
        self._sleeper = sleeper

    def wait(
        self,
        *,
        expected_duration: float | None = None,
        deadline: float | None = None,
        completion_condition: Callable[[], bool] | None = None,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> ControlledWaitResult:
        """Wait until duration/deadline, an optional condition, or cancellation.

        With no completion condition, reaching the bound is successful elapsed
        activity. With a condition, reaching the bound without it is a timeout.
        ``deadline`` is expressed on the injected monotonic clock.
        """

        if (expected_duration is None) == (deadline is None):
            raise ValueError("provide exactly one of expected_duration or deadline")
        if completion_condition is not None and not callable(completion_condition):
            raise ValueError("completion_condition must be callable or None")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")

        started = self._clock()
        bound = (
            started + _non_negative_duration(expected_duration, "expected_duration")
            if expected_duration is not None
            else _finite_time(deadline, "deadline")
        )
        polls = 0

        while True:
            try:
                if cancel_requested() is True:
                    return self._result(
                        ControlledWaitOutcome.CANCELLED, started, polls
                    )
                if completion_condition is not None:
                    polls += 1
                    if completion_condition() is True:
                        return self._result(
                            ControlledWaitOutcome.COMPLETED, started, polls
                        )
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                return self._result(
                    ControlledWaitOutcome.FAILED,
                    started,
                    polls,
                    f"{type(error).__name__}: {error}",
                )

            now = self._clock()
            remaining = bound - now
            if remaining <= 0:
                outcome = (
                    ControlledWaitOutcome.COMPLETED
                    if completion_condition is None
                    else ControlledWaitOutcome.TIMEOUT
                )
                return self._result(outcome, started, polls)
            self._sleeper(min(self.check_interval, remaining))

    def _result(
        self,
        outcome: ControlledWaitOutcome,
        started: float,
        polls: int,
        error: str | None = None,
    ) -> ControlledWaitResult:
        return ControlledWaitResult(
            outcome,
            elapsed=max(0.0, self._clock() - started),
            poll_count=polls,
            error=error,
        )


def _positive_duration(value: object, name: str) -> float:
    result = _finite_time(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _non_negative_duration(value: object, name: str) -> float:
    result = _finite_time(value, name)
    if result < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


def _finite_time(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


__all__ = (
    "ControlledWait",
    "ControlledWaitOutcome",
    "ControlledWaitResult",
)
