"""Productive Lobby-to-Lobby Daily Quests flow."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.catalog import (
    MODE_DAILY_QUESTS,
    SCREEN_LOBBY,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
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
from bot.semantic_actions import ClaimAllDailyQuests, CloseDailyQuests, OpenDailyQuests
from bot.state import ResolutionStatus


DAILY_QUESTS_NOOP = "daily_quests.noop"
DAILY_QUESTS_CLAIM_ALL_EXECUTED = "daily_quests.claim_all_executed"
DAILY_QUESTS_CLAIM_ALL_COMPLETED = "daily_quests.claim_all_completed"


@dataclass(frozen=True)
class DailyQuestsFlowResult(FlowResult):
    no_op: bool = False
    claim_all_executed: bool = False
    claim_all_completed: bool = False


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


class DailyQuestsFlow:
    """Claim visible Daily Quest rows once and return to Lobby."""

    name = "daily_quests"
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
        claim_timeout: float = 8.0,
        navigation_stable_for: float = 0.25,
        claim_stable_for: float = 0.5,
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
        self.claim_timeout = _positive_duration(claim_timeout, "claim_timeout")
        self.navigation_stable_for = _non_negative_duration(
            navigation_stable_for, "navigation_stable_for"
        )
        self.claim_stable_for = _non_negative_duration(
            claim_stable_for, "claim_stable_for"
        )

    def run(self) -> DailyQuestsFlowResult:
        events: list[FlowEvent] = []
        try:
            if self._cancelled():
                return self._cancel(events)
            lobby = self._initial_lobby()
            daily = self._act_and_wait(
                OpenDailyQuests(),
                lobby,
                expected=_is_daily_quests,
                abort_if=_has_incompatible_daily_navigation,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )

            no_op = STATUS_DAILY_QUESTS_CLAIMABLE not in daily.state.overlays
            claim_executed = False
            claim_completed = False
            if no_op:
                self._append_event(events, DAILY_QUESTS_NOOP)
            else:
                claim_executed = True
                self._append_event(events, DAILY_QUESTS_CLAIM_ALL_EXECUTED)
                daily = self._act_and_wait(
                    ClaimAllDailyQuests(),
                    daily,
                    expected=_is_daily_quests_settled,
                    abort_if=_has_incompatible_daily_state,
                    timeout=self.claim_timeout,
                    stable_for=self.claim_stable_for,
                )
                claim_completed = True
                self._append_event(events, DAILY_QUESTS_CLAIM_ALL_COMPLETED)

            lobby = self._act_and_wait(
                CloseDailyQuests(),
                daily,
                expected=_is_clean_lobby,
                abort_if=_has_incompatible_close_state,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )
            assert _is_clean_lobby(lobby)
            return DailyQuestsFlowResult(
                FlowStatus.COMPLETED,
                tuple(events),
                no_op=no_op,
                claim_all_executed=claim_executed,
                claim_all_completed=claim_completed,
            )
        except RuntimeWaitCancelled:
            return self._cancel(events)
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._failed(events, f"state_wait_failed: {error}")
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(events, f"{type(error).__name__}: {error}")

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
            raise RuntimeWaitCancelled("daily quests flow cancelled")
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

    def _cancel(self, events: list[FlowEvent]) -> DailyQuestsFlowResult:
        self._record("daily_quests.cancelled")
        return DailyQuestsFlowResult(FlowStatus.CANCELLED, tuple(events))

    def _failed(
        self, events: list[FlowEvent], error: str
    ) -> DailyQuestsFlowResult:
        self._record("daily_quests.failed", error=error)
        return DailyQuestsFlowResult(FlowStatus.FAILED, tuple(events), error)

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


def _is_daily_quests(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_QUESTS
        and MODE_DAILY_QUESTS in state.overlays
        and set(state.overlays)
        <= {MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE}
    )


def _is_daily_quests_settled(snapshot: RuntimeSnapshot) -> bool:
    return (
        _is_daily_quests(snapshot)
        and STATUS_DAILY_QUESTS_CLAIMABLE not in snapshot.state.overlays
    )


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


def _has_incompatible_daily_navigation(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(
            set(state.overlays)
            - {MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE}
        )
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {SCREEN_LOBBY, SCREEN_QUESTS}
        )
    )


def _has_incompatible_daily_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and not _is_daily_quests(snapshot)
        )
        or bool(
            set(state.overlays)
            - {MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE}
        )
    )


def _has_incompatible_close_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(
            set(state.overlays)
            - {MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE}
        )
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {SCREEN_QUESTS, SCREEN_LOBBY}
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
    "DAILY_QUESTS_CLAIM_ALL_COMPLETED",
    "DAILY_QUESTS_CLAIM_ALL_EXECUTED",
    "DAILY_QUESTS_NOOP",
    "DailyQuestsFlow",
    "DailyQuestsFlowResult",
)
