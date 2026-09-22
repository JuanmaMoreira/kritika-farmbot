"""Verified direct Treasure -> Quick Menu -> Trading adapter.

This is deliberately one route, not a router.  It owns the Quick Menu
open/select mechanics and provenance handoff only; it has no Keys policy,
Treasure drain semantics, trade retry, Lobby fallback, scroll, or recovery
planning.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.quick_menu import (
    QuickMenuHandoff,
    quick_menu_matches_origin,
    select_quick_menu_trading_action,
)
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.semantic_actions import OpenQuickMenu
from bot.state import ResolutionStatus
from bot.trading_center import clean_trading
from bot.trading_center_semantics import SCREEN_TRADING
from bot.treasure_center import clean_treasure
from bot.treasure_center_semantics import SCREEN_TREASURE
from bot.verified_transition import VerifiedTransitionPolicy


@dataclass(frozen=True)
class QuickMenuTradingResult(FlowResult):
    """Two verified transitions plus the fresh Trading postcondition."""

    final_snapshot: RuntimeSnapshot | None = None
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


def _finish(transitions, status, **kwargs) -> QuickMenuTradingResult:
    return QuickMenuTradingResult(
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


def _foreign_or_ambiguous(snapshot) -> bool:
    state = snapshot.state
    if state.status is ResolutionStatus.AMBIGUOUS:
        return True
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context not in (SCREEN_TREASURE, SCREEN_TRADING)
    )


class QuickMenuTradingRuntime:
    """Open Treasure's Quick Menu and select the verified Trading tile."""

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

    def treasure_to_trading(self) -> QuickMenuTradingResult:
        """Require stable Treasure and return a posterior clean Trading frame."""

        transitions = []
        try:
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                clean_treasure,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return _finish(transitions, FlowStatus.CANCELLED)
            opened = self.transition.execute(
                "quick_menu.treasure.open",
                OpenQuickMenu(),
                before,
                expected=lambda item: quick_menu_matches_origin(
                    item, SCREEN_TREASURE
                ),
                precondition=clean_treasure,
                retryable_from=None,
                abort_if=_foreign_or_ambiguous,
                policy=_single_attempt_policy(),
            )
            transitions.append(opened)
            if self.cancel_requested():
                return _finish(
                    transitions,
                    FlowStatus.CANCELLED,
                    final_snapshot=opened.final_snapshot,
                )
            menu = opened.final_snapshot
            if (
                not opened.succeeded
                or menu.sequence <= before.sequence
                or not quick_menu_matches_origin(menu, SCREEN_TREASURE)
            ):
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=menu,
                    error=(
                        "quick_menu.treasure.open_failed:"
                        f"{opened.outcome.value}:{opened.error}"
                    ),
                    failure=opened.failure,
                )
            handoff = QuickMenuHandoff.from_open_result(opened, clean_treasure)
            if handoff is None:
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=menu,
                    error="quick_menu_origin_handoff_invalid",
                )
            selected = self.transition.execute(
                "quick_menu.treasure.select_trading",
                select_quick_menu_trading_action(handoff.origin),
                menu,
                expected=clean_trading,
                precondition=handoff.allows,
                retryable_from=None,
                on_recovery=handoff.invalidate,
                abort_if=lambda item: (
                    not clean_treasure(item)
                    and handoff.observe(item, clean_trading)
                )
                or _foreign_or_ambiguous(item),
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(selected)
            if self.cancel_requested():
                return _finish(
                    transitions,
                    FlowStatus.CANCELLED,
                    final_snapshot=selected.final_snapshot,
                )
            final = selected.final_snapshot
            if (
                not selected.succeeded
                or final.sequence <= menu.sequence
                or not clean_trading(final)
            ):
                return _finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        "quick_menu.treasure.select_trading_failed:"
                        f"{selected.outcome.value}:{selected.error}"
                    ),
                    failure=selected.failure,
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


def treasure_to_trading(runtime: QuickMenuTradingRuntime) -> QuickMenuTradingResult:
    return runtime.treasure_to_trading()


__all__ = (
    "QuickMenuTradingResult",
    "QuickMenuTradingRuntime",
    "treasure_to_trading",
)
