"""Cooperative cancellation and monotonic budgets, without input authority."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import math
import time
from typing import Callable


class RuntimeWaitCancelled(RuntimeError):
    """An operation observed an explicit cancellation request."""


class OperationBudgetExpired(TimeoutError):
    """A total or phase budget was exhausted; never authorizes another input."""


@dataclass
class OperationControl:
    """One intention's shared deadline and cumulative phase allowances.

    Times and acquisition timestamps must use the same monotonic clock domain.
    Limits are cooperative: synchronous work already in flight cannot be undone.
    Nested phases consume both allowances (e.g. observation inside recovery).
    """

    cancel_requested: Callable[[], bool] | None = None
    deadline: float | None = None
    observation_timeout: float | None = None
    dispatch_timeout: float | None = None
    recovery_timeout: float | None = None
    clock: Callable[[], float] = time.monotonic
    parent: "OperationControl | None" = field(default=None, repr=False)
    _spent: dict = field(default_factory=dict, init=False, repr=False)
    _active: dict = field(default_factory=dict, init=False, repr=False)
    _cancelled: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if self.cancel_requested is not None and not callable(self.cancel_requested):
            raise ValueError("cancel_requested must be callable or None")
        for name in ("deadline", "observation_timeout", "dispatch_timeout", "recovery_timeout"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and non-negative or None")

    def remaining(self):
        now = self.clock()
        limits = [self.deadline - now] if self.deadline is not None else []
        if self.parent is not None:
            limits.append(self.parent.remaining())
        for phase, started in self._active.items():
            allowance = getattr(self, f"{phase}_timeout")
            if allowance is not None:
                limits.append(allowance - self._spent.get(phase, 0) - (now - started))
        return min(limits, default=math.inf)

    def check(self):
        if self.parent is not None:
            self.parent.check()
        self._cancelled = self._cancelled or bool(self.cancel_requested and self.cancel_requested())
        if self._cancelled:
            raise RuntimeWaitCancelled("operation cancelled")
        exhausted = any(
            getattr(self, f"{phase}_timeout") is not None
            and spent >= getattr(self, f"{phase}_timeout")
            for phase, spent in self._spent.items()
        )
        if exhausted or self.remaining() <= 0:
            raise OperationBudgetExpired("operation budget exhausted")

    @contextmanager
    def phase(self, name):
        if self.parent is not None:
            with self.parent.phase(name), self._phase(name):
                yield
        else:
            with self._phase(name):
                yield

    @contextmanager
    def _phase(self, name):
        outer = name not in self._active
        if outer:
            self._active[name] = self.clock()
        try:
            self.check()
            yield
            self.check()
        finally:
            if outer:
                self._spent[name] = self._spent.get(name, 0) + self.clock() - self._active.pop(name)


_control = ContextVar("operation_control", default=None)


def current_control():
    return _control.get()


def check_operation():
    control = current_control()
    if control is not None:
        control.check()


@contextmanager
def control_scope(control):
    token = _control.set(control)
    try:
        yield
    finally:
        _control.reset(token)


@contextmanager
def operation_phase(name):
    control = current_control()
    if control is None:
        yield
    else:
        with control.phase(name):
            yield
