"""C6b causal Gold-capacity recovery orchestration.

The standalone route remains explicit and local:

Trading -> Lobby -> Treasure -> Quick Menu -> Trading -> Avatar & Keys.

Policy stays in :mod:`bot.keys_promotion`; Trading, Treasure and Quick Menu
keep their physical ownership.  This module only preserves the causal
Silver->Gold request, composes one recovery visit, and permits one retry.
Callers with another verified immediate origin may inject the same three
physical handoffs without moving causal recovery policy out of C6b.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from numbers import Integral

from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.keys_promotion import (
    GOLD_ROW_ID,
    SILVER_ROW_ID,
    KeysPromotionDecision,
    KeysPromotionKind,
    PendingCausalOperation,
    decide_after_trade,
    decide_next_keys_operation,
)
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.trading_keys import KeyTradeOperation, is_keys_ready
from bot.trading_operation import TradeOutcome, TradePanelFact, TradeResult
from bot.trading_row_facts import KEYS_SECTION, TradingRowFact
from bot.treasure_fast_drain import GoldKeyDrainOutcome, GoldKeyDrainResult
from bot.treasure_keys import GoldKeyQuantity, GoldKeyQuantityMode, TreasureOutcome


@dataclass(frozen=True)
class FreshKeyFacts:
    """One Keys-ready snapshot and both row facts read from that frame set."""

    snapshot: RuntimeSnapshot
    silver_fact: TradingRowFact
    gold_fact: TradingRowFact

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, RuntimeSnapshot):
            raise ValueError("snapshot must be RuntimeSnapshot")
        if not isinstance(self.silver_fact, TradingRowFact) or not isinstance(
            self.gold_fact, TradingRowFact
        ):
            raise ValueError("silver_fact and gold_fact must be TradingRowFact")
        if (
            self.silver_fact.item_id != SILVER_ROW_ID
            or self.silver_fact.section != KEYS_SECTION
        ):
            raise ValueError("silver_fact must be the Keys silver_key row")
        if (
            self.gold_fact.item_id != GOLD_ROW_ID
            or self.gold_fact.section != KEYS_SECTION
        ):
            raise ValueError("gold_fact must be the Keys gold_key row")
        if (
            self.silver_fact.sequence != self.snapshot.sequence
            or self.gold_fact.sequence != self.snapshot.sequence
        ):
            raise ValueError("both row facts must belong to snapshot.sequence")
        if not is_keys_ready(self.snapshot):
            raise ValueError("snapshot must be fresh Avatar & Keys readiness")


@dataclass(frozen=True)
class GoldFullAckResult(FlowResult):
    """One verified OK dismissal after the causal output-full alert."""

    final_snapshot: RuntimeSnapshot | None = None


def acknowledge_gold_full_boundary(
    pending: PendingCausalOperation,
    *,
    read_panel,
    tap_ok,
    read_keys_context,
    cancel_requested=lambda: False,
) -> GoldFullAckResult:
    """Dismiss the observed alert once, then require fresh clean Keys."""
    if not isinstance(pending, PendingCausalOperation):
        raise ValueError("pending must be PendingCausalOperation")
    if not all(callable(item) for item in (
        read_panel, tap_ok, read_keys_context, cancel_requested,
    )):
        raise ValueError("ack callbacks must be callable")
    if cancel_requested():
        return GoldFullAckResult(FlowStatus.CANCELLED)
    panel = read_panel()
    if (not isinstance(panel, TradePanelFact)
            or panel.sequence <= pending.before_fact.sequence
            or not panel.panel_open or not panel.shows_output_full):
        return GoldFullAckResult(FlowStatus.FAILED, error="fresh_gold_full_alert_unavailable")
    if cancel_requested():
        return GoldFullAckResult(FlowStatus.CANCELLED)
    tap_ok()
    after = read_keys_context(after_sequence=panel.sequence)
    if (not isinstance(after, RuntimeSnapshot)
            or after.sequence <= panel.sequence or not is_keys_ready(after)):
        return GoldFullAckResult(FlowStatus.FAILED, error="gold_full_ack_not_verified")
    return GoldFullAckResult(FlowStatus.COMPLETED, final_snapshot=after)


@dataclass(frozen=True)
class KeysPromotionRuntimeResult(FlowResult):
    """Terminal orchestration result with bounded causal audit data."""

    decision: KeysPromotionDecision | None = None
    pending: PendingCausalOperation | None = None
    final_facts: FreshKeyFacts | None = None
    trade_attempts: tuple[KeyTradeOperation, ...] = ()
    recovery_steps: tuple[str, ...] = ()
    recovery_count: int = 0
    retry_count: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "trade_attempts", tuple(self.trade_attempts))
        object.__setattr__(self, "recovery_steps", tuple(self.recovery_steps))
        if self.recovery_count not in (0, 1):
            raise ValueError("recovery_count must be zero or one")
        if self.retry_count not in (0, 1):
            raise ValueError("retry_count must be zero or one")


@dataclass(frozen=True)
class GoldCapacityRecoveryNavigation:
    """Three source-aware physical hooks used by one C6b recovery.

    C6b retains ownership of the causal Gold-full decision, drain and retry.
    The supplied hooks own only the immediate-origin navigation contract.
    """

    source: str
    leave_trading: Callable[[], object]
    enter_treasure: Callable[[], object]
    return_to_trading: Callable[[], object]
    leave_step: str
    enter_step: str
    return_step: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("source must be a non-empty string")
        for name in ("leave_trading", "enter_treasure", "return_to_trading"):
            if not callable(getattr(self, name)):
                raise ValueError(f"{name} must be callable")
        for name in ("leave_step", "enter_step", "return_step"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")


class _Cancelled(Exception):
    pass


class _StepFailed(Exception):
    pass


class KeysPromotionRuntime:
    """Run C6a and one optional causal Gold-capacity recovery cycle."""

    def __init__(
        self,
        trading_runtime,
        treasure_runtime,
        quick_menu_runtime,
        *,
        read_key_facts,
        execute_key_trade,
        drain_gold_keys,
        acknowledge_gold_full=None,
        cancel_requested=lambda: False,
    ) -> None:
        for owner, method in (
            (trading_runtime, "ensure_avatar_keys"),
            (trading_runtime, "leave_to_lobby"),
            (treasure_runtime, "enter_treasure_from_lobby"),
            (treasure_runtime, "execute_gold_key_open"),
            (quick_menu_runtime, "treasure_to_trading"),
        ):
            if not callable(getattr(owner, method, None)):
                raise ValueError(f"runtime must provide {method}()")
        for callback, name in (
            (read_key_facts, "read_key_facts"),
            (execute_key_trade, "execute_key_trade"),
            (drain_gold_keys, "drain_gold_keys"),
            (cancel_requested, "cancel_requested"),
        ):
            if not callable(callback):
                raise ValueError(f"{name} must be callable")
        self.trading_runtime = trading_runtime
        self.treasure_runtime = treasure_runtime
        self.quick_menu_runtime = quick_menu_runtime
        self.read_key_facts = read_key_facts
        self.execute_key_trade = execute_key_trade
        self.drain_gold_keys = drain_gold_keys
        if acknowledge_gold_full is not None and not callable(acknowledge_gold_full):
            raise ValueError("acknowledge_gold_full must be callable or None")
        self.acknowledge_gold_full = acknowledge_gold_full
        self.cancel_requested = cancel_requested

    def run(
        self,
        *,
        budget_remaining: int,
        recovery_navigation: GoldCapacityRecoveryNavigation | None = None,
        defer_recovery: bool = False,
        recovery_already_used: bool = False,
    ) -> KeysPromotionRuntimeResult:
        """Promote Keys with one bounded Silver->Gold OUTPUT_FULL recovery."""

        if (
            isinstance(budget_remaining, bool)
            or not isinstance(budget_remaining, Integral)
            or int(budget_remaining) < 0
        ):
            raise ValueError("budget_remaining must be a non-negative integer")
        budget = int(budget_remaining)
        if recovery_navigation is not None and not isinstance(
            recovery_navigation, GoldCapacityRecoveryNavigation
        ):
            raise ValueError(
                "recovery_navigation must be GoldCapacityRecoveryNavigation or None"
            )
        attempts: list[KeyTradeOperation] = []
        recovery_steps: list[str] = []
        pending: PendingCausalOperation | None = None
        facts: FreshKeyFacts | None = None
        decision: KeysPromotionDecision | None = None
        recovered = recovery_already_used
        retry_count = 0

        def finish(status, **kwargs) -> KeysPromotionRuntimeResult:
            return KeysPromotionRuntimeResult(
                status,
                decision=kwargs.pop("decision", decision),
                pending=pending,
                final_facts=kwargs.pop("final_facts", facts),
                trade_attempts=tuple(attempts),
                recovery_steps=tuple(recovery_steps),
                recovery_count=int(recovered),
                retry_count=retry_count,
                **kwargs,
            )

        try:
            facts = self._fresh_facts(after_sequence=0)
            decision = decide_next_keys_operation(
                silver_fact=facts.silver_fact,
                gold_fact=facts.gold_fact,
                budget_remaining=budget,
            )
            while True:
                if decision.kind in (
                    KeysPromotionKind.NO_MORE_PROMOTIONS,
                    KeysPromotionKind.BUDGET_EXHAUSTED,
                ):
                    return finish(FlowStatus.COMPLETED)
                if decision.kind is KeysPromotionKind.FAILED:
                    return finish(
                        FlowStatus.FAILED,
                        error=f"keys_policy_failed:{decision.reason}",
                    )
                if decision.kind is not KeysPromotionKind.NEXT_OPERATION:
                    return finish(
                        FlowStatus.FAILED,
                        error=f"unexpected_policy_state:{decision.kind.value}",
                    )
                if self._cancelled():
                    raise _Cancelled()
                result = self._execute(decision, facts)
                attempts.append(decision.operation)  # type: ignore[arg-type]
                if result.outcome is TradeOutcome.CANCELLED:
                    raise _Cancelled()
                budget -= 1

                if result.outcome is TradeOutcome.OUTPUT_FULL:
                    folded = decide_after_trade(
                        previous=decision,
                        result=result,
                        budget_remaining=budget,
                    )
                    if folded.kind is not KeysPromotionKind.GOLD_CAPACITY_BLOCKED:
                        decision = folded
                        continue
                    if recovered:
                        decision = folded
                        return finish(
                            FlowStatus.FAILED,
                            error="gold_capacity_recovery_already_used",
                        )
                    pending = folded.pending
                    assert isinstance(pending, PendingCausalOperation)
                    if self.acknowledge_gold_full is None:
                        return finish(FlowStatus.FAILED, error="gold_full_ack_unavailable")
                    acknowledged = self.acknowledge_gold_full(pending)
                    if not isinstance(acknowledged, GoldFullAckResult):
                        return finish(FlowStatus.FAILED, error="gold_full_ack_invalid")
                    if acknowledged.status is FlowStatus.CANCELLED:
                        raise _Cancelled()
                    if (acknowledged.status is not FlowStatus.COMPLETED
                            or acknowledged.final_snapshot is None
                            or acknowledged.final_snapshot.sequence <= pending.before_fact.sequence
                            or not is_keys_ready(acknowledged.final_snapshot)):
                        return finish(FlowStatus.FAILED, error="gold_full_ack_not_verified")
                    recovery_steps.append("trading.ack_gold_full")
                    if defer_recovery:
                        decision = folded
                        return finish(FlowStatus.COMPLETED)
                    resolved = self.resolve_pending(
                        pending,
                        budget_remaining=budget,
                        recovery_navigation=recovery_navigation,
                    )
                    return KeysPromotionRuntimeResult(
                        resolved.status, error=resolved.error, failure=resolved.failure,
                        decision=resolved.decision, pending=pending,
                        final_facts=resolved.final_facts,
                        trade_attempts=(*attempts, *resolved.trade_attempts),
                        recovery_steps=(*recovery_steps, *resolved.recovery_steps),
                        recovery_count=resolved.recovery_count,
                        retry_count=resolved.retry_count,
                    )

                if result.outcome in (
                    TradeOutcome.SUCCESS,
                    TradeOutcome.INSUFFICIENT_INPUT,
                    TradeOutcome.NO_MORE_INPUT,
                ):
                    facts = self._fresh_facts(
                        after_sequence=self._post_trade_barrier(facts, result)
                    )
                    decision = decide_after_trade(
                        previous=decision,
                        result=result,
                        budget_remaining=budget,
                        silver_fact=facts.silver_fact,
                        gold_fact=facts.gold_fact,
                    )
                    continue
                decision = decide_after_trade(
                    previous=decision,
                    result=result,
                    budget_remaining=budget,
                )
        except (_Cancelled, RuntimeWaitCancelled):
            return finish(FlowStatus.CANCELLED)
        except _StepFailed as error:
            return finish(FlowStatus.FAILED, error=str(error))
        except Exception as error:
            return finish(
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def resolve_pending(
        self,
        pending: PendingCausalOperation,
        *,
        budget_remaining: int,
        recovery_navigation: GoldCapacityRecoveryNavigation | None = None,
    ) -> KeysPromotionRuntimeResult:
        """Drain Gold and retry the saved Silver->Gold operation exactly once."""
        if not isinstance(pending, PendingCausalOperation):
            raise ValueError("pending must be PendingCausalOperation")
        if recovery_navigation is not None and not isinstance(
            recovery_navigation, GoldCapacityRecoveryNavigation
        ):
            raise ValueError("recovery_navigation must be GoldCapacityRecoveryNavigation or None")
        if isinstance(budget_remaining, bool) or not isinstance(budget_remaining, Integral) or budget_remaining < 0:
            raise ValueError("budget_remaining must be non-negative")
        steps: list[str] = []
        try:
            fresh = self._recover_gold_capacity(
                after_sequence=pending.before_fact.sequence,
                recovery_steps=steps,
                recovery_navigation=recovery_navigation,
            )
            decision = KeysPromotionDecision(
                kind=KeysPromotionKind.NEXT_OPERATION,
                operation=pending.operation,
                quantity=pending.quantity,
                silver_fact=fresh.silver_fact,
                gold_fact=fresh.gold_fact,
                reason="causal_retry_after_gold_drain",
                evidence=("retry:causal_silver_to_gold", *pending.evidence),
            )
            if self._cancelled():
                raise _Cancelled()
            retry = self._execute(decision, fresh)
            steps.append("trade.retry_silver_to_gold")
            if retry.outcome is TradeOutcome.CANCELLED:
                raise _Cancelled()
            if retry.outcome is not TradeOutcome.SUCCESS:
                reason = (
                    "causal_retry_output_full"
                    if retry.outcome is TradeOutcome.OUTPUT_FULL
                    else f"causal_retry_failed:{retry.outcome.value}"
                )
                return KeysPromotionRuntimeResult(
                    FlowStatus.FAILED, error=reason,
                    pending=pending, decision=decision, final_facts=fresh,
                    trade_attempts=(pending.operation,), recovery_steps=tuple(steps),
                    recovery_count=1, retry_count=1,
                )
            continued = self.run(
                budget_remaining=int(budget_remaining),
                recovery_already_used=True,
            )
            return KeysPromotionRuntimeResult(
                continued.status, error=continued.error, failure=continued.failure,
                decision=continued.decision, pending=pending,
                final_facts=continued.final_facts,
                trade_attempts=(pending.operation, *continued.trade_attempts),
                recovery_steps=(*steps, *continued.recovery_steps),
                recovery_count=1, retry_count=1,
            )
        except (_Cancelled, RuntimeWaitCancelled):
            return KeysPromotionRuntimeResult(
                FlowStatus.CANCELLED, pending=pending, recovery_steps=tuple(steps),
                recovery_count=1,
            )
        except Exception as error:
            return KeysPromotionRuntimeResult(
                FlowStatus.FAILED, error=str(error) or type(error).__name__,
                pending=pending, recovery_steps=tuple(steps), recovery_count=1,
            )

    def _fresh_facts(self, *, after_sequence: int) -> FreshKeyFacts:
        if self._cancelled():
            raise _Cancelled()
        step = self.trading_runtime.ensure_avatar_keys()
        if step.status is FlowStatus.CANCELLED:
            raise _Cancelled()
        final = getattr(step, "final_snapshot", None)
        if step.status is not FlowStatus.COMPLETED or final is None:
            raise _StepFailed(
                f"ensure_avatar_keys_failed:{getattr(step, 'error', None)}"
            )
        barrier = max(int(after_sequence), int(final.sequence))
        if self._cancelled():
            raise _Cancelled()
        fresh = self.read_key_facts(barrier)
        if not isinstance(fresh, FreshKeyFacts):
            raise _StepFailed("fresh_key_facts_unavailable")
        if fresh.snapshot.sequence <= barrier:
            raise _StepFailed("stale_key_facts")
        return fresh

    def _execute(
        self, decision: KeysPromotionDecision, facts: FreshKeyFacts
    ) -> TradeResult:
        assert decision.operation is not None
        assert decision.quantity is not None
        row = (
            facts.gold_fact
            if decision.operation is KeyTradeOperation.SILVER_TO_GOLD
            else facts.silver_fact
        )
        result = self.execute_key_trade(
            operation=decision.operation,
            snapshot=facts.snapshot,
            row_fact=row,
            quantity=decision.quantity,
        )
        if not isinstance(result, TradeResult):
            raise _StepFailed("execute_key_trade_invalid_result")
        return result

    def _recover_gold_capacity(
        self,
        *,
        after_sequence: int,
        recovery_steps: list[str],
        recovery_navigation: GoldCapacityRecoveryNavigation | None,
    ) -> FreshKeyFacts:
        navigation = recovery_navigation or GoldCapacityRecoveryNavigation(
            source="lobby",
            leave_trading=self.trading_runtime.leave_to_lobby,
            enter_treasure=self.treasure_runtime.enter_treasure_from_lobby,
            return_to_trading=self.quick_menu_runtime.treasure_to_trading,
            leave_step="trading.leave_to_lobby",
            enter_step="treasure.enter_from_lobby",
            return_step="quick_menu.treasure_to_trading",
        )

        left = navigation.leave_trading()
        recovery_steps.append(navigation.leave_step)
        self._require_step(left, "trading_leave")

        entered = navigation.enter_treasure()
        recovery_steps.append(navigation.enter_step)
        self._require_step(entered, "treasure_enter")

        if self._cancelled():
            raise _Cancelled()
        opened = self.treasure_runtime.execute_gold_key_open(
            GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE),
            max_actions=2,
        )
        recovery_steps.append("treasure.open_gold_once")
        if opened.outcome is TreasureOutcome.CANCELLED:
            raise _Cancelled()
        if opened.outcome is not TreasureOutcome.SUCCESS:
            raise _StepFailed(
                f"gold_drain_entry_failed:{opened.outcome.value}:{opened.reason}"
            )

        if self._cancelled():
            raise _Cancelled()
        drained = self.drain_gold_keys()
        recovery_steps.append("treasure.drain_all_gold")
        if not isinstance(drained, GoldKeyDrainResult):
            raise _StepFailed("gold_drain_invalid_result")
        if drained.outcome is GoldKeyDrainOutcome.CANCELLED:
            raise _Cancelled()
        if drained.outcome is not GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED:
            raise _StepFailed(
                f"gold_drain_failed:{drained.outcome.value}:{drained.reason}"
            )

        returned = navigation.return_to_trading()
        recovery_steps.append(navigation.return_step)
        self._require_step(returned, "quick_menu_return")
        final = getattr(returned, "final_snapshot", None)
        if final is None:
            raise _StepFailed("quick_menu_return_missing_trading_snapshot")
        recovery_steps.append("trading.ensure_avatar_keys")
        fresh = self._fresh_facts(
            after_sequence=max(int(after_sequence), int(final.sequence))
        )
        recovery_steps.append("facts.refresh_after_relief")
        return fresh

    @staticmethod
    def _require_step(result, name: str) -> None:
        if result.status is FlowStatus.CANCELLED:
            raise _Cancelled()
        if result.status is not FlowStatus.COMPLETED:
            raise _StepFailed(f"{name}_failed:{getattr(result, 'error', None)}")

    @staticmethod
    def _post_trade_barrier(
        facts: FreshKeyFacts, result: TradeResult
    ) -> int:
        sequences = [
            facts.snapshot.sequence,
            facts.silver_fact.sequence,
            facts.gold_fact.sequence,
        ]
        if result.after_fact is not None:
            sequences.append(result.after_fact.sequence)
        return max(sequences)

    def _cancelled(self) -> bool:
        try:
            return self.cancel_requested() is True
        except Exception:
            return False


__all__ = (
    "FreshKeyFacts",
    "GoldFullAckResult",
    "acknowledge_gold_full_boundary",
    "GoldCapacityRecoveryNavigation",
    "KeysPromotionRuntime",
    "KeysPromotionRuntimeResult",
)
