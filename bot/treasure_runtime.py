"""Autonomous Treasure runtime over the E Gold Keys capability.

Small composable operations, not a monolithic flow (C6b needs the
pieces separately). The caller already decided to open Treasure;
nothing here decides why, how much relief anyone needs, or any
outside policy. No capacity-blocked boundary, no silver-to-gold
operation, no craft, no relief, no monster wave, no planners, no
stages, no list motion: separation is tested, not just documented.

Operations (each bounded, single-attempt, state-guarded):

- ``enter_treasure_from_lobby``: clean Lobby -> tap Treasure tile ->
  fresh Treasure context. Wrong source authorizes zero input.
- ``execute_gold_key_open``: Treasure grid with Gold readiness ->
  tap Gold chest -> selector popup with fresh per-control facts ->
  existing E ``execute_gold_key_open`` capability with profile
  targets -> verified consumption. One causal tap per open, fresh
  Gold-vs-Karat guard before every tap, zero blind retries.
- ``leave_treasure_to_lobby``: result dismissed when present ->
  clean Treasure -> Back -> clean Lobby with a fresh
  postcondition. SUCCESS is never reported for merely touching
  Back.
- ``open_gold_keys_from_lobby``: minimal wrapper composing the
  three (enter -> execute -> leave), always restoring Lobby.

Fact preference plan: the popup offers 1 and 10 at once while a
fact carries one amount, so the operation expands the requested
quantity into a greedy preference (10s then 1s; OPEN_ONCE prefers
the minimal single spend). Each ``read_state`` serves the plan
position for its iteration when demonstrated and falls back to the
other demonstrated control otherwise; the capability still enforces
exactness (overshoot fails closed, UP_TO caps with verified opens).
Facts always come from fresh snapshots, never manufactured.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.catalog import SCREEN_LOBBY
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import (
    DismissTreasureResult,
    ExitTreasure,
    OpenTreasure,
    SelectGoldChest,
)
from bot.state import ResolutionStatus
from bot.treasure_center import (
    has_result,
    has_selector_popup,
    is_gold_keys_content_ready,
    is_treasure_screen,
)
from bot.treasure_facts import fact_for_repeat, fact_for_single
from bot.treasure_keys import (
    GOLD_ALLOWED_CURRENCY_KINDS,
    GoldKeyOpenRequest,
    GoldKeyOpenResult,
    GoldKeyQuantity,
    TreasureCurrencyFact,
    TreasureOutcome,
    check_gold_ready,
    execute_gold_key_open as execute_capability,
)
from bot.treasure_profile import TREASURE_PROFILE, open_targets
from bot.verified_transition import VerifiedTransitionPolicy


def is_clean_lobby(snapshot) -> bool:
    """Resolved Lobby without overlays (entry source / return home)."""
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_LOBBY
        and not state.overlays
    )


def _is_foreign_or_ambiguous(snapshot) -> bool:
    state = snapshot.state
    if state.status is ResolutionStatus.AMBIGUOUS:
        return True
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context not in (SCREEN_LOBBY,)
        and not is_treasure_screen(snapshot)
    )


def _treasure_gone_unexpected(snapshot) -> bool:
    """Abort Treasure waits when the context is lost unexpectedly."""
    state = snapshot.state
    if state.status is ResolutionStatus.AMBIGUOUS:
        return True
    if state.status is ResolutionStatus.UNKNOWN:
        return False
    return not is_treasure_screen(snapshot)


@dataclass(frozen=True)
class TreasureStepResult(FlowResult):
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True)
class TreasureSessionResult(FlowResult):
    enter: TreasureStepResult | None = None
    open: GoldKeyOpenResult | None = None
    leave: TreasureStepResult | None = None
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


def _finish_step(transitions, status, **kwargs) -> TreasureStepResult:
    return TreasureStepResult(
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


class TreasureRuntime:
    """Owns one Lobby -> Treasure -> Lobby visit; no policy beyond it."""

    entry_requirement_lobby = True

    def __init__(
        self,
        observer,
        transition,
        *,
        profile=TREASURE_PROFILE,
        cancel_requested=lambda: False,
    ):
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
        self.profile = profile
        self.cancel_requested = cancel_requested

    def enter_treasure_from_lobby(self) -> TreasureStepResult:
        """Verify clean Lobby, tap the Treasure tile, verify arrival."""
        transitions = []
        try:
            if self.cancel_requested():
                return _finish_step(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                is_clean_lobby,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return _finish_step(transitions, FlowStatus.CANCELLED)
            result = self.transition.execute(
                "treasure.enter",
                OpenTreasure(),
                before,
                expected=is_treasure_screen,
                precondition=is_clean_lobby,
                retryable_from=None,
                abort_if=_is_foreign_or_ambiguous,
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(result)
            if self.cancel_requested():
                return _finish_step(transitions, FlowStatus.CANCELLED)
            if not result.succeeded:
                return _finish_step(
                    transitions,
                    FlowStatus.FAILED,
                    error=(
                        f"treasure.enter_failed: {result.outcome.value}: "
                        f"{result.error}"
                    ),
                    failure=result.failure,
                )
            if not is_treasure_screen(result.final_snapshot):
                return _finish_step(
                    transitions,
                    FlowStatus.FAILED,
                    error="treasure_postcondition_failed",
                )
            return _finish_step(transitions, FlowStatus.COMPLETED)
        except RuntimeWaitCancelled:
            return _finish_step(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return _finish_step(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def execute_gold_key_open(
        self, quantity: GoldKeyQuantity, *, max_actions: int = 10
    ) -> GoldKeyOpenResult:
        """Open Gold Keys from a Treasure grid with fresh runtime facts."""
        try:
            before = self.observer.wait_until(
                is_gold_keys_content_ready,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
        except RuntimeWaitCancelled:
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.CANCELLED,
                before=None,
                reason="user_cancelled",
                evidence=("cancel_before_input",),
            )
        except Exception as error:
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=None,
                reason=f"wait_failed:{type(error).__name__}",
                evidence=("readiness_wait_failed",),
            )
        ready_reason = check_gold_ready(before)
        if ready_reason is not None:
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=None,
                reason=ready_reason,
                evidence=(f"readiness:{ready_reason}",),
            )
        selector = self.transition.execute(
            "treasure.open_selector",
            SelectGoldChest(),
            before,
            expected=has_selector_popup,
            precondition=is_gold_keys_content_ready,
            retryable_from=None,
            abort_if=_treasure_gone_unexpected,
            stable_for=0.25,
            policy=_single_attempt_policy(),
        )
        if not selector.succeeded or not has_selector_popup(
            selector.final_snapshot
        ):
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=None,
                reason=(
                    f"selector_failed:{selector.outcome.value}:"
                    f"{selector.error}"
                ),
                evidence=("selector_not_reached",),
            )
        plan = _expand_quantity(quantity, max_actions)
        reads = {"count": 0}
        latest = {"snapshot": selector.final_snapshot}

        def read_state() -> TreasureCurrencyFact | None:
            try:
                snapshot = self.observer.observe()
            except Exception:
                return None
            latest["snapshot"] = snapshot
            iteration = reads["count"] // 2
            reads["count"] += 1
            prefer = plan[iteration] if iteration < len(plan) else 1
            builders = (
                (fact_for_repeat, fact_for_single)
                if prefer == 10
                else (fact_for_single, fact_for_repeat)
            )
            for build in builders:
                fact = build(snapshot, sequence=snapshot.sequence)
                if fact is not None and (
                    fact.currency == "gold_key" or fact.currency == "karat"
                ):
                    break
            else:
                fact = builders[0](snapshot, sequence=snapshot.sequence)
            return fact

        def tap(point: tuple[float, float]) -> None:
            geometry = latest["snapshot"].geometry
            pixel = (
                int(point[0] * geometry.width),
                int(point[1] * geometry.height),
            )
            actions = getattr(self.transition, "actions", None)
            adb = getattr(actions, "adb", None)
            if adb is None or not callable(getattr(adb, "tap", None)):
                raise ValueError("transition must expose actions.adb.tap")
            adb.tap(*pixel)

        request = GoldKeyOpenRequest(
            quantity=quantity,
            allowed_currency_kinds=frozenset(GOLD_ALLOWED_CURRENCY_KINDS),
            targets=open_targets(self.profile),
            max_actions=max_actions,
            max_fact_age=2,
            source="lobby",
            return_to="lobby",
        )
        return execute_capability(
            snapshot=selector.final_snapshot,
            request=request,
            tap=tap,
            read_state=read_state,
            cancel_requested=self.cancel_requested,
        )

    def leave_treasure_to_lobby(self) -> TreasureStepResult:
        """Dismiss a result when present, Back to Lobby, verify home."""
        transitions = []
        try:
            if self.cancel_requested():
                return _finish_step(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                is_treasure_screen,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if has_result(before):
                if self.cancel_requested():
                    return _finish_step(transitions, FlowStatus.CANCELLED)
                dismissed = self.transition.execute(
                    "treasure.dismiss_result",
                    DismissTreasureResult(),
                    before,
                    expected=lambda item: (
                        is_treasure_screen(item) and not has_result(item)
                    ),
                    precondition=has_result,
                    retryable_from=None,
                    abort_if=_treasure_gone_unexpected,
                    stable_for=0.25,
                    policy=_single_attempt_policy(),
                )
                transitions.append(dismissed)
                if self.cancel_requested():
                    return _finish_step(transitions, FlowStatus.CANCELLED)
                if not dismissed.succeeded:
                    return _finish_step(
                        transitions,
                        FlowStatus.FAILED,
                        error=(
                            "treasure.dismiss_failed: "
                            f"{dismissed.outcome.value}:{dismissed.error}"
                        ),
                        failure=dismissed.failure,
                    )
                before = dismissed.final_snapshot
            if self.cancel_requested():
                return _finish_step(transitions, FlowStatus.CANCELLED)
            left = self.transition.execute(
                "treasure.leave",
                ExitTreasure(),
                before,
                expected=is_clean_lobby,
                precondition=is_treasure_screen,
                retryable_from=None,
                abort_if=lambda item: (
                    item.state.status is ResolutionStatus.AMBIGUOUS
                ),
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(left)
            if self.cancel_requested():
                return _finish_step(transitions, FlowStatus.CANCELLED)
            if not left.succeeded or not is_clean_lobby(left.final_snapshot):
                return _finish_step(
                    transitions,
                    FlowStatus.FAILED,
                    error=(
                        f"treasure.leave_failed: {left.outcome.value}:"
                        f"{left.error}"
                    ),
                    failure=left.failure,
                )
            return _finish_step(transitions, FlowStatus.COMPLETED)
        except RuntimeWaitCancelled:
            return _finish_step(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return _finish_step(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def open_gold_keys_from_lobby(
        self, quantity: GoldKeyQuantity, *, max_actions: int = 10
    ) -> TreasureSessionResult:
        """Compose enter -> execute -> leave, always restoring Lobby."""
        if self.cancel_requested():
            return TreasureSessionResult(FlowStatus.CANCELLED)
        entered = self.enter_treasure_from_lobby()
        if entered.status is FlowStatus.CANCELLED:
            return TreasureSessionResult(FlowStatus.CANCELLED, enter=entered)
        if entered.status is not FlowStatus.COMPLETED:
            return TreasureSessionResult(
                FlowStatus.FAILED,
                enter=entered,
                error=entered.error,
                failure=entered.failure,
            )
        opened = self.execute_gold_key_open(quantity, max_actions=max_actions)
        if opened.outcome is TreasureOutcome.CANCELLED:
            left = self.leave_treasure_to_lobby()
            return TreasureSessionResult(
                FlowStatus.CANCELLED, enter=entered, open=opened, leave=left
            )
        left = self.leave_treasure_to_lobby()
        if opened.outcome is not TreasureOutcome.SUCCESS:
            return TreasureSessionResult(
                FlowStatus.FAILED,
                enter=entered,
                open=opened,
                leave=left,
                error=f"treasure.open_{opened.outcome.value}:{opened.reason}",
            )
        if left.status is not FlowStatus.COMPLETED:
            return TreasureSessionResult(
                FlowStatus.FAILED,
                enter=entered,
                open=opened,
                leave=left,
                error=left.error,
                failure=left.failure,
            )
        return TreasureSessionResult(
            FlowStatus.COMPLETED, enter=entered, open=opened, leave=left
        )


def _expand_quantity(
    quantity: GoldKeyQuantity, max_actions: int
) -> tuple[int, ...]:
    from bot.treasure_keys import GoldKeyQuantityMode

    if quantity.mode is GoldKeyQuantityMode.OPEN_ONCE:
        return (1,)
    if quantity.mode is GoldKeyQuantityMode.MAX_WITHIN_BUDGET:
        return (10,) * max(1, int(max_actions))
    amount = int(quantity.amount or 0)
    tens, ones = divmod(max(0, amount), 10)
    return (10,) * tens + (1,) * ones


__all__ = (
    "TreasureRuntime",
    "TreasureSessionResult",
    "TreasureStepResult",
    "enter_treasure_from_lobby",
    "execute_gold_key_open",
    "is_clean_lobby",
    "leave_treasure_to_lobby",
    "open_gold_keys_from_lobby",
)


def enter_treasure_from_lobby(runtime: TreasureRuntime) -> TreasureStepResult:
    """Functional alias for the enter operation."""
    return runtime.enter_treasure_from_lobby()


def execute_gold_key_open(
    runtime: TreasureRuntime,
    quantity: GoldKeyQuantity,
    *,
    max_actions: int = 10,
) -> GoldKeyOpenResult:
    """Functional alias for the execute operation."""
    return runtime.execute_gold_key_open(quantity, max_actions=max_actions)


def leave_treasure_to_lobby(runtime: TreasureRuntime) -> TreasureStepResult:
    """Functional alias for the leave operation."""
    return runtime.leave_treasure_to_lobby()


def open_gold_keys_from_lobby(
    runtime: TreasureRuntime,
    quantity: GoldKeyQuantity,
    *,
    max_actions: int = 10,
) -> TreasureSessionResult:
    """Functional alias for the composed session."""
    return runtime.open_gold_keys_from_lobby(quantity, max_actions=max_actions)
