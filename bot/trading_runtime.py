"""Verified Trading navigation required before C6b orchestration.

This runtime owns only three bounded physical transitions:

- clean Lobby -> Trading;
- resolved Trading -> fresh Avatars & Keys readiness;
- resolved Trading -> fresh General/material readiness;
- clean Trading -> clean Lobby.

It contains no trade policy, row selection, scrolling, Treasure knowledge or
C6a/C6b outcome handling. The injected observer must use resolver-complete
navigation perception plus the existing Trading tab/rows detectors; use
``build_trading_navigation_perception`` for the production composition.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.catalog import SCREEN_LOBBY
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.semantic_actions import (
    CloseTrading,
    OpenTrading,
    SelectTradingAvatarKeys,
    SelectTradingGeneral,
)
from bot.state import ResolutionStatus
from bot.trading_center import (
    clean_trading,
    is_materials_content_ready,
    is_trading_screen,
)
from bot.trading_center_semantics import SCREEN_TRADING
from bot.trading_keys import is_keys_ready
from bot.verified_transition import VerifiedTransitionPolicy


def is_clean_lobby(snapshot) -> bool:
    """Resolved Lobby without overlays."""

    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_LOBBY
        and not state.overlays
    )


def _foreign_or_ambiguous(snapshot) -> bool:
    state = snapshot.state
    if state.status is ResolutionStatus.AMBIGUOUS:
        return True
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context not in (SCREEN_LOBBY, SCREEN_TRADING)
    )


def _trading_lost(snapshot) -> bool:
    state = snapshot.state
    if state.status is ResolutionStatus.AMBIGUOUS:
        return True
    if state.status is ResolutionStatus.UNKNOWN:
        return False
    return not is_trading_screen(snapshot)


@dataclass(frozen=True)
class TradingStepResult(FlowResult):
    """One navigation result with the fresh postcondition when available."""

    final_snapshot: RuntimeSnapshot | None = None
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


def _finish(transitions, status, **kwargs) -> TradingStepResult:
    return TradingStepResult(
        status,
        **kwargs,
        transition_outcomes=tuple(
            (item.name, item.outcome.value) for item in transitions
        ),
        transition_attempts=tuple(
            (item.name, item.attempt_count, item.grace_wait_count)
            for item in transitions
        ),
    )


def _single_attempt_policy() -> VerifiedTransitionPolicy:
    return VerifiedTransitionPolicy(
        normal_timeout=6.0,
        grace_timeout=2.0,
        retry_guard_timeout=0.0,
        max_attempts=1,
    )


class TradingRuntime:
    """Small verified navigation wrapper; no Trading business decisions."""

    def __init__(self, observer, transition, *, cancel_requested=lambda: False):
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(transition, "execute", None)):
            raise ValueError("transition must provide execute()")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.observer = observer
        self.transition = transition
        self.cancel_requested = cancel_requested

    def enter_from_lobby(self) -> TradingStepResult:
        """Open Trading directly from a clean Lobby and verify freshness."""

        transitions = []
        try:
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                is_clean_lobby,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            result = self.transition.execute(
                "trading.enter",
                OpenTrading(),
                before,
                expected=clean_trading,
                precondition=is_clean_lobby,
                retryable_from=None,
                abort_if=_foreign_or_ambiguous,
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(result)
            if self.cancel_requested():
                return _finish(
                    transitions,
                    FlowStatus.CANCELLED,
                    final_snapshot=result.final_snapshot,
                )
            final = result.final_snapshot
            if (
                not result.succeeded
                or final.sequence <= before.sequence
                or not clean_trading(final)
            ):
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        f"trading.enter_failed:{result.outcome.value}:"
                        f"{result.error}"
                    ),
                    failure=result.failure,
                )
            return _finish(
                transitions,
                FlowStatus.COMPLETED,
                final_snapshot=final,
            )
        except RuntimeWaitCancelled:
            return _finish(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return _finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def ensure_avatar_keys(self) -> TradingStepResult:
        """Idempotently obtain fresh Avatars & Keys readiness, without scroll."""

        transitions = []
        try:
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                clean_trading,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            if is_keys_ready(before):
                return _finish(
                    transitions,
                    FlowStatus.COMPLETED,
                    final_snapshot=before,
                )
            result = self.transition.execute(
                "trading.select_avatar_keys",
                SelectTradingAvatarKeys(),
                before,
                expected=is_keys_ready,
                precondition=clean_trading,
                retryable_from=None,
                abort_if=_trading_lost,
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(result)
            if self.cancel_requested():
                return _finish(
                    transitions,
                    FlowStatus.CANCELLED,
                    final_snapshot=result.final_snapshot,
                )
            final = result.final_snapshot
            if (
                not result.succeeded
                or final.sequence <= before.sequence
                or not is_keys_ready(final)
            ):
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        "trading.select_avatar_keys_failed:"
                        f"{result.outcome.value}:{result.error}"
                    ),
                    failure=result.failure,
                )
            return _finish(
                transitions,
                FlowStatus.COMPLETED,
                final_snapshot=final,
            )
        except RuntimeWaitCancelled:
            return _finish(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return _finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def ensure_general(self) -> TradingStepResult:
        """Idempotently obtain fresh General/material readiness."""

        transitions = []
        try:
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                clean_trading,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            if is_materials_content_ready(before):
                return _finish(
                    transitions,
                    FlowStatus.COMPLETED,
                    final_snapshot=before,
                )
            result = self.transition.execute(
                "trading.select_general",
                SelectTradingGeneral(),
                before,
                expected=is_materials_content_ready,
                precondition=clean_trading,
                retryable_from=None,
                abort_if=_trading_lost,
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(result)
            if self.cancel_requested():
                return _finish(
                    transitions,
                    FlowStatus.CANCELLED,
                    final_snapshot=result.final_snapshot,
                )
            final = result.final_snapshot
            if (
                not result.succeeded
                or final.sequence <= before.sequence
                or not is_materials_content_ready(final)
            ):
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        "trading.select_general_failed:"
                        f"{result.outcome.value}:{result.error}"
                    ),
                    failure=result.failure,
                )
            return _finish(
                transitions,
                FlowStatus.COMPLETED,
                final_snapshot=final,
            )
        except RuntimeWaitCancelled:
            return _finish(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return _finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def leave_to_lobby(self) -> TradingStepResult:
        """Close Trading through its verified X and require fresh Lobby."""

        transitions = []
        try:
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                clean_trading,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            result = self.transition.execute(
                "trading.leave",
                CloseTrading(),
                before,
                expected=is_clean_lobby,
                precondition=clean_trading,
                retryable_from=None,
                abort_if=lambda item: (
                    item.state.status is ResolutionStatus.AMBIGUOUS
                ),
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(result)
            if self.cancel_requested():
                return _finish(
                    transitions,
                    FlowStatus.CANCELLED,
                    final_snapshot=result.final_snapshot,
                )
            final = result.final_snapshot
            if (
                not result.succeeded
                or final.sequence <= before.sequence
                or not is_clean_lobby(final)
            ):
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        f"trading.leave_failed:{result.outcome.value}:"
                        f"{result.error}"
                    ),
                    failure=result.failure,
                )
            return _finish(
                transitions,
                FlowStatus.COMPLETED,
                final_snapshot=final,
            )
        except RuntimeWaitCancelled:
            return _finish(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return _finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )


def enter_from_lobby(runtime: TradingRuntime) -> TradingStepResult:
    return runtime.enter_from_lobby()


def ensure_avatar_keys(runtime: TradingRuntime) -> TradingStepResult:
    return runtime.ensure_avatar_keys()


def ensure_general(runtime: TradingRuntime) -> TradingStepResult:
    return runtime.ensure_general()


def leave_to_lobby(runtime: TradingRuntime) -> TradingStepResult:
    return runtime.leave_to_lobby()


__all__ = (
    "TradingRuntime",
    "TradingStepResult",
    "ensure_avatar_keys",
    "ensure_general",
    "enter_from_lobby",
    "is_clean_lobby",
    "leave_to_lobby",
)
