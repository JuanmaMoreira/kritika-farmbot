"""Reusable verified operation for bounded discrete UI transitions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import SemanticAction


class VerifiedTransitionOutcome(str, Enum):
    SUCCESS_FIRST_ATTEMPT = "success_first_attempt"
    SUCCESS_AFTER_GRACE = "success_after_grace"
    SUCCESS_AFTER_RETRY = "success_after_retry"
    PRECONDITION_REJECTED = "precondition_rejected"
    RETRY_GUARD_REJECTED = "retry_guard_rejected"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    UNEXPECTED_STATE = "unexpected_state"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass(frozen=True)
class VerifiedTransitionPolicy:
    """Small timing and attempt policy for one kind of transition."""

    normal_timeout: float = 6.0
    grace_timeout: float = 2.0
    retry_guard_timeout: float = 0.0
    max_attempts: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "normal_timeout",
            _positive_duration(self.normal_timeout, "normal_timeout"),
        )
        object.__setattr__(
            self,
            "grace_timeout",
            _positive_duration(self.grace_timeout, "grace_timeout"),
        )
        object.__setattr__(
            self,
            "retry_guard_timeout",
            _non_negative_duration(
                self.retry_guard_timeout, "retry_guard_timeout"
            ),
        )
        object.__setattr__(
            self,
            "max_attempts",
            _positive_integer(self.max_attempts, "max_attempts"),
        )


@dataclass(frozen=True)
class VerifiedTransitionResult:
    name: str
    outcome: VerifiedTransitionOutcome
    attempt_count: int
    grace_wait_count: int
    final_snapshot: RuntimeSnapshot
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.outcome, VerifiedTransitionOutcome):
            raise ValueError("outcome must be VerifiedTransitionOutcome")
        object.__setattr__(
            self,
            "attempt_count",
            _non_negative_integer(self.attempt_count, "attempt_count"),
        )
        object.__setattr__(
            self,
            "grace_wait_count",
            _non_negative_integer(self.grace_wait_count, "grace_wait_count"),
        )
        if not isinstance(self.final_snapshot, RuntimeSnapshot):
            raise ValueError("final_snapshot must be RuntimeSnapshot")

    @property
    def succeeded(self) -> bool:
        return self.outcome in {
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE,
            VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY,
        }


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class VerifiedTransition:
    """Execute an action and verify its postcondition with guarded retries."""

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute(intent, geometry)")
        self.observer: _Observer = observer
        self.actions = actions

    def execute(
        self,
        name: str,
        action: SemanticAction,
        before: RuntimeSnapshot,
        *,
        expected: Callable[[RuntimeSnapshot], bool],
        policy: VerifiedTransitionPolicy,
        precondition: Callable[[RuntimeSnapshot], bool] | None = None,
        retryable_from: Callable[[RuntimeSnapshot], bool] | None = None,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> VerifiedTransitionResult:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(before, RuntimeSnapshot):
            raise ValueError("before must be RuntimeSnapshot")
        if not isinstance(policy, VerifiedTransitionPolicy):
            raise ValueError("policy must be VerifiedTransitionPolicy")
        if not callable(expected):
            raise ValueError("expected must be callable")
        for predicate_name, predicate in (
            ("precondition", precondition),
            ("retryable_from", retryable_from),
            ("abort_if", abort_if),
        ):
            if predicate is not None and not callable(predicate):
                raise ValueError(f"{predicate_name} must be callable or None")
        stability = _non_negative_duration(stable_for, "stable_for")
        if precondition is not None and not precondition(before):
            return self._result(
                name,
                VerifiedTransitionOutcome.PRECONDITION_REJECTED,
                0,
                0,
                before,
                "precondition_rejected",
            )

        current = before
        grace_wait_count = 0
        for attempt in range(1, policy.max_attempts + 1):
            try:
                self.actions.execute(action, current.geometry)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                return self._result(
                    name,
                    VerifiedTransitionOutcome.FAILED,
                    attempt,
                    grace_wait_count,
                    current,
                    f"{type(error).__name__}: {error}",
                )

            normal = self._wait(
                expected,
                after_sequence=current.sequence,
                timeout=policy.normal_timeout,
                abort_if=abort_if,
                stable_for=stability,
            )
            if isinstance(normal, RuntimeSnapshot):
                outcome = (
                    VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
                    if attempt == 1
                    else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                )
                return self._result(
                    name,
                    outcome,
                    attempt,
                    grace_wait_count,
                    normal,
                )
            if isinstance(normal, RuntimeWaitAborted):
                return self._result(
                    name,
                    VerifiedTransitionOutcome.UNEXPECTED_STATE,
                    attempt,
                    grace_wait_count,
                    normal.snapshot,
                    str(normal),
                )

            grace_wait_count += 1
            grace_anchor = normal.last_snapshot or current
            grace = self._wait(
                expected,
                after_sequence=grace_anchor.sequence,
                timeout=policy.grace_timeout,
                abort_if=abort_if,
                stable_for=stability,
            )
            if isinstance(grace, RuntimeSnapshot):
                outcome = (
                    VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
                    if attempt == 1
                    else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                )
                return self._result(
                    name,
                    outcome,
                    attempt,
                    grace_wait_count,
                    grace,
                )
            if isinstance(grace, RuntimeWaitAborted):
                return self._result(
                    name,
                    VerifiedTransitionOutcome.UNEXPECTED_STATE,
                    attempt,
                    grace_wait_count,
                    grace.snapshot,
                    str(grace),
                )

            try:
                observed = self.observer.observe()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                return self._result(
                    name,
                    VerifiedTransitionOutcome.FAILED,
                    attempt,
                    grace_wait_count,
                    grace.last_snapshot or grace_anchor,
                    f"{type(error).__name__}: {error}",
                )
            if observed.sequence <= current.sequence:
                return self._result(
                    name,
                    VerifiedTransitionOutcome.TIMEOUT,
                    attempt,
                    grace_wait_count,
                    observed,
                    "retry_state_not_fresh",
                )
            if expected(observed):
                outcome = (
                    VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
                    if attempt == 1
                    else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                )
                return self._result(
                    name,
                    outcome,
                    attempt,
                    grace_wait_count,
                    observed,
                )
            if abort_if is not None and abort_if(observed):
                return self._result(
                    name,
                    VerifiedTransitionOutcome.UNEXPECTED_STATE,
                    attempt,
                    grace_wait_count,
                    observed,
                    "unexpected_state_after_grace",
                )
            if retryable_from is None:
                return self._result(
                    name,
                    VerifiedTransitionOutcome.TIMEOUT,
                    attempt,
                    grace_wait_count,
                    observed,
                    "expected_state_not_reached",
                )
            if not retryable_from(observed):
                if policy.retry_guard_timeout == 0:
                    return self._result(
                        name,
                        VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,
                        attempt,
                        grace_wait_count,
                        observed,
                        "retry_guard_rejected",
                    )
                guarded = self._wait(
                    lambda snapshot: (
                        expected(snapshot) or retryable_from(snapshot)
                    ),
                    after_sequence=observed.sequence,
                    timeout=policy.retry_guard_timeout,
                    abort_if=abort_if,
                    stable_for=0.0,
                )
                if isinstance(guarded, RuntimeSnapshot):
                    observed = guarded
                    if expected(observed):
                        outcome = (
                            VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE
                            if attempt == 1
                            else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY
                        )
                        return self._result(
                            name,
                            outcome,
                            attempt,
                            grace_wait_count,
                            observed,
                        )
                elif isinstance(guarded, RuntimeWaitAborted):
                    return self._result(
                        name,
                        VerifiedTransitionOutcome.UNEXPECTED_STATE,
                        attempt,
                        grace_wait_count,
                        guarded.snapshot,
                        str(guarded),
                    )
                else:
                    return self._result(
                        name,
                        VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,
                        attempt,
                        grace_wait_count,
                        guarded.last_snapshot or observed,
                        "retry_guard_rejected",
                    )
            if attempt >= policy.max_attempts:
                return self._result(
                    name,
                    VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED,
                    attempt,
                    grace_wait_count,
                    observed,
                    "attempts_exhausted",
                )
            current = observed

        raise AssertionError("bounded transition loop exited unexpectedly")

    def _wait(
        self,
        expected: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None,
        stable_for: float,
    ) -> RuntimeSnapshot | RuntimeWaitTimeout | RuntimeWaitAborted:
        try:
            return self.observer.wait_until(
                expected,
                after_sequence=after_sequence,
                timeout=timeout,
                abort_if=abort_if,
                stable_for=stable_for,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return error

    @staticmethod
    def _result(
        name: str,
        outcome: VerifiedTransitionOutcome,
        attempt_count: int,
        grace_wait_count: int,
        final_snapshot: RuntimeSnapshot,
        error: str | None = None,
    ) -> VerifiedTransitionResult:
        return VerifiedTransitionResult(
            name=name,
            outcome=outcome,
            attempt_count=attempt_count,
            grace_wait_count=grace_wait_count,
            final_snapshot=final_snapshot,
            error=error,
        )


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _positive_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _non_negative_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


__all__ = (
    "VerifiedTransition",
    "VerifiedTransitionOutcome",
    "VerifiedTransitionPolicy",
    "VerifiedTransitionResult",
)
