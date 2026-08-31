"""Productive Lobby-to-Lobby Friends Send Stamina Daily flow."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.catalog import (
    SCREEN_FRIENDS,
    SCREEN_LOBBY,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
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
from bot.semantic_actions import (
    CloseFriends,
    OpenFriends,
    SendStaminaToAllFriends,
)
from bot.state import ResolutionStatus


SEND_STAMINA_NOOP = "send_stamina.noop"
SEND_STAMINA_ALL_EXECUTED = "send_stamina.all_executed"
SEND_STAMINA_COMPLETED = "send_stamina.completed"

_FRIENDS_STATES = frozenset({STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE})


@dataclass(frozen=True)
class SendStaminaFlowResult(FlowResult):
    no_op: bool = False
    all_executed: bool = False
    daily_completed: bool = False


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


class SendStaminaFlow:
    """Send stamina once when its Friends Daily is active and return to Lobby."""

    name = "send_stamina"
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(
        precondition=ComponentRequirement.exact_state(SCREEN_LOBBY),
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
        ),
    )

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink,
        *,
        navigation_timeout: float = 6.0,
        completion_timeout: float = 3.0,
        navigation_stable_for: float = 0.25,
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
        self.navigation_timeout = _positive_duration(
            navigation_timeout, "navigation_timeout"
        )
        self.completion_timeout = _positive_duration(
            completion_timeout, "completion_timeout"
        )
        self.navigation_stable_for = _non_negative_duration(
            navigation_stable_for, "navigation_stable_for"
        )
        self.completion_stable_for = _non_negative_duration(
            completion_stable_for, "completion_stable_for"
        )

    def run(self) -> SendStaminaFlowResult:
        events: list[FlowEvent] = []
        all_executed = False
        try:
            if self._cancelled():
                return self._cancel(events, all_executed=False)
            lobby = self._initial_lobby()
            friends = self._act_and_wait(
                OpenFriends(),
                lobby,
                expected=_is_friends,
                abort_if=_has_incompatible_friends_navigation,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )

            no_op = not _is_daily_active(friends)
            if no_op:
                self._append_event(events, SEND_STAMINA_NOOP)
            else:
                if self._cancelled():
                    raise RuntimeWaitCancelled("send stamina flow cancelled")
                self.actions.execute(SendStaminaToAllFriends(), friends.geometry)
                all_executed = True
                self._append_event(events, SEND_STAMINA_ALL_EXECUTED)
                friends = self.observer.wait_until(
                    _is_daily_completed,
                    after_sequence=friends.sequence,
                    timeout=self.completion_timeout,
                    abort_if=_has_incompatible_daily_transition,
                    cancel_requested=self.cancel_requested,
                    stable_for=self.completion_stable_for,
                )
                assert _is_daily_completed(friends)
                self._append_event(events, SEND_STAMINA_COMPLETED)

            lobby = self._act_and_wait(
                CloseFriends(),
                friends,
                expected=_is_clean_lobby,
                abort_if=_has_incompatible_close_state,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )
            assert _is_clean_lobby(lobby)
            return SendStaminaFlowResult(
                FlowStatus.COMPLETED,
                tuple(events),
                no_op=no_op,
                all_executed=all_executed,
                daily_completed=True,
            )
        except RuntimeWaitCancelled:
            return self._cancel(events, all_executed=all_executed)
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._failed(
                events,
                f"state_wait_failed: {error}",
                all_executed=all_executed,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(
                events,
                f"{type(error).__name__}: {error}",
                all_executed=all_executed,
            )

    def _initial_lobby(self) -> RuntimeSnapshot:
        initial = self.observer.observe()
        if _is_clean_lobby(initial):
            return initial
        if not _is_passive_unknown(initial):
            raise RuntimeError("precondition_lobby_failed")
        return self.observer.wait_until(
            _is_clean_lobby,
            after_sequence=initial.sequence,
            timeout=self.navigation_timeout,
            abort_if=_has_incompatible_lobby_state,
            cancel_requested=self.cancel_requested,
            stable_for=self.navigation_stable_for,
        )

    def _act_and_wait(
        self,
        action,
        before: RuntimeSnapshot,
        *,
        expected,
        abort_if,
        timeout: float,
        stable_for: float,
    ) -> RuntimeSnapshot:
        if self._cancelled():
            raise RuntimeWaitCancelled("send stamina flow cancelled")
        self.actions.execute(action, before.geometry)
        return self.observer.wait_until(
            expected,
            after_sequence=before.sequence,
            timeout=timeout,
            abort_if=abort_if,
            cancel_requested=self.cancel_requested,
            stable_for=stable_for,
        )

    def _append_event(self, events: list[FlowEvent], kind: str) -> None:
        events.append(FlowEvent(kind))
        self._record(kind)

    def _cancel(
        self,
        events: list[FlowEvent],
        *,
        all_executed: bool,
    ) -> SendStaminaFlowResult:
        self._record("send_stamina.cancelled")
        return SendStaminaFlowResult(
            FlowStatus.CANCELLED,
            tuple(events),
            all_executed=all_executed,
        )

    def _failed(
        self,
        events: list[FlowEvent],
        error: str,
        *,
        all_executed: bool,
    ) -> SendStaminaFlowResult:
        self._record("send_stamina.failed", error=error)
        return SendStaminaFlowResult(
            FlowStatus.FAILED,
            tuple(events),
            error,
            all_executed=all_executed,
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


def _is_clean_lobby(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_LOBBY
        and not state.overlays
    )


def _is_friends(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_FRIENDS
        and set(state.overlays) <= _FRIENDS_STATES
    )


def _is_daily_active(snapshot: RuntimeSnapshot) -> bool:
    return (
        _is_friends(snapshot)
        and STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE in snapshot.state.overlays
    )


def _is_daily_completed(snapshot: RuntimeSnapshot) -> bool:
    return _is_friends(snapshot) and not snapshot.state.overlays


def _is_passive_unknown(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.UNKNOWN
        and not snapshot.state.overlays
    )


def _has_incompatible_lobby_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_LOBBY
        )
    )


def _has_incompatible_friends_navigation(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    overlays = set(state.overlays)
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(overlays - _FRIENDS_STATES)
        or (
            state.status is not ResolutionStatus.RESOLVED
            and bool(overlays)
        )
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context == SCREEN_LOBBY
            and bool(overlays)
        )
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {SCREEN_LOBBY, SCREEN_FRIENDS}
        )
    )


def _has_incompatible_daily_transition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    overlays = set(state.overlays)
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(overlays - _FRIENDS_STATES)
        or (
            state.status is not ResolutionStatus.RESOLVED
            and bool(overlays)
        )
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_FRIENDS
        )
    )


def _has_incompatible_close_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {SCREEN_FRIENDS, SCREEN_LOBBY}
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
    "SEND_STAMINA_ALL_EXECUTED",
    "SEND_STAMINA_COMPLETED",
    "SEND_STAMINA_NOOP",
    "SendStaminaFlow",
    "SendStaminaFlowResult",
)
