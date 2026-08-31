"""Productive Guild Attendance check-in flow."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.catalog import (
    SCREEN_GUILD,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
)
from bot.component_contracts import ComponentRequirement
from bot.event_log import EventSink
from bot.flow_contracts import FlowContract, FlowEvent, FlowResult, FlowScope, FlowStatus
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import CheckInGuildAttendance
from bot.state import ResolutionStatus


GUILD_CHECK_IN_NOOP = "guild_check_in.noop"
GUILD_CHECK_IN_TAP_EXECUTED = "guild_check_in.tap_executed"
GUILD_CHECK_IN_COMPLETED = "guild_check_in.attendance_completed"

_ATTENDANCE_STATES = frozenset(
    {
        STATUS_GUILD_ATTENDANCE_ACTIVE,
        STATUS_GUILD_ATTENDANCE_COMPLETED,
    }
)


@dataclass(frozen=True)
class GuildCheckInFlowResult(FlowResult):
    no_op: bool = False
    tap_executed: bool = False
    attendance_completed: bool = False


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class GuildCheckInFlow:
    """Check in once when Attendance is active and remain in Guild."""

    name = "guild_check_in"
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(
        precondition=ComponentRequirement.exact_state(SCREEN_GUILD),
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_GUILD),
        ),
    )

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink,
        *,
        completion_timeout: float = 10.0,
        completion_stable_for: float = 0.75,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.cancel_requested = cancel_requested
        self.completion_timeout = _positive_duration(
            completion_timeout, "completion_timeout"
        )
        self.completion_stable_for = _non_negative_duration(
            completion_stable_for, "completion_stable_for"
        )

    def run(self) -> GuildCheckInFlowResult:
        events: list[FlowEvent] = []
        tap_executed = False
        try:
            if self._cancelled():
                return self._cancel(events, tap_executed=False)
            initial = self.observer.observe()
            if _is_attendance_completed(initial):
                self._append_event(events, GUILD_CHECK_IN_NOOP)
                return GuildCheckInFlowResult(
                    FlowStatus.COMPLETED,
                    tuple(events),
                    no_op=True,
                    attendance_completed=True,
                )
            if not _is_attendance_active(initial):
                return self._failed(
                    events,
                    "precondition_guild_attendance_state_failed",
                    tap_executed=False,
                )

            if self._cancelled():
                return self._cancel(events, tap_executed=False)
            self.actions.execute(CheckInGuildAttendance(), initial.geometry)
            tap_executed = True
            self._append_event(events, GUILD_CHECK_IN_TAP_EXECUTED)
            completed = self.observer.wait_until(
                _is_attendance_completed,
                after_sequence=initial.sequence,
                timeout=self.completion_timeout,
                abort_if=_has_incompatible_attendance_transition,
                cancel_requested=self.cancel_requested,
                stable_for=self.completion_stable_for,
            )
            assert _is_attendance_completed(completed)
            self._append_event(events, GUILD_CHECK_IN_COMPLETED)
            return GuildCheckInFlowResult(
                FlowStatus.COMPLETED,
                tuple(events),
                tap_executed=True,
                attendance_completed=True,
            )
        except RuntimeWaitCancelled:
            return self._cancel(events, tap_executed=tap_executed)
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._failed(
                events,
                f"attendance_completion_failed: {error}",
                tap_executed=tap_executed,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(
                events,
                f"{type(error).__name__}: {error}",
                tap_executed=tap_executed,
            )

    def _append_event(self, events: list[FlowEvent], kind: str) -> None:
        events.append(FlowEvent(kind))
        self._record(kind)

    def _cancel(
        self,
        events: list[FlowEvent],
        *,
        tap_executed: bool,
    ) -> GuildCheckInFlowResult:
        self._record("guild_check_in.cancelled")
        return GuildCheckInFlowResult(
            FlowStatus.CANCELLED,
            tuple(events),
            tap_executed=tap_executed,
        )

    def _failed(
        self,
        events: list[FlowEvent],
        error: str,
        *,
        tap_executed: bool,
    ) -> GuildCheckInFlowResult:
        self._record("guild_check_in.failed", error=error)
        return GuildCheckInFlowResult(
            FlowStatus.FAILED,
            tuple(events),
            error,
            tap_executed=tap_executed,
        )

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass

    def _cancelled(self) -> bool:
        try:
            return self.cancel_requested() is True
        except Exception:
            return False


def _is_attendance_active(snapshot: RuntimeSnapshot) -> bool:
    return _is_guild_with_attendance(snapshot, STATUS_GUILD_ATTENDANCE_ACTIVE)


def _is_attendance_completed(snapshot: RuntimeSnapshot) -> bool:
    return _is_guild_with_attendance(snapshot, STATUS_GUILD_ATTENDANCE_COMPLETED)


def _is_guild_with_attendance(snapshot: RuntimeSnapshot, status: str) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_GUILD
        and set(state.overlays) == {status}
    )


def _has_incompatible_attendance_transition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    overlays = set(state.overlays)
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(overlays - _ATTENDANCE_STATES)
        or _ATTENDANCE_STATES <= overlays
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_GUILD
        )
    )


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
    "GUILD_CHECK_IN_COMPLETED",
    "GUILD_CHECK_IN_NOOP",
    "GUILD_CHECK_IN_TAP_EXECUTED",
    "GuildCheckInFlow",
    "GuildCheckInFlowResult",
)
