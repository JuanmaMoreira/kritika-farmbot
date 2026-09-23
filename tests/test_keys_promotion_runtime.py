from types import SimpleNamespace
import inspect

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.flow_contracts import FlowStatus
from bot.keys_promotion_runtime import (
    FreshKeyFacts,
    GoldCapacityRecoveryNavigation,
    GoldFullAckResult,
    KeysPromotionRuntime,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center_semantics import (
    INDICATOR_TRADING_KEYS_ACTIVE,
    INDICATOR_TRADING_KEYS_ROWS,
    LANDMARK_TRADING_CENTER_TITLE,
    SCREEN_TRADING,
)
from bot.trading_keys import KeyTradeOperation
from bot.trading_operation import TradeOutcome, TradeResult
from bot.trading_row_facts import KEYS_SECTION, TradingRowFact
from bot.treasure_fast_drain import GoldKeyDrainOutcome, GoldKeyDrainResult
from bot.treasure_keys import TreasureOutcome


GEOMETRY = FrameGeometry(width=2712, height=1220)


def _keys_snapshot(sequence):
    image = np.zeros((1220, 2712, 3), dtype=np.uint8)
    names = (
        LANDMARK_TRADING_CENTER_TITLE,
        INDICATOR_TRADING_KEYS_ACTIVE,
        INDICATOR_TRADING_KEYS_ROWS,
    )
    observations = tuple(
        Observation(name, 0.95, ObservationSource.LOCAL_CV) for name in names
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=SCREEN_TRADING,
            overlays=frozenset(),
        ),
        RuntimeFacts(),
        GEOMETRY,
    )


def _facts(sequence, *, bronze, silver):
    snapshot = _keys_snapshot(sequence)
    return FreshKeyFacts(
        snapshot,
        TradingRowFact(
            "silver_key", KEYS_SECTION, 0.46, bronze, 10, sequence
        ),
        TradingRowFact(
            "gold_key", KEYS_SECTION, 0.60, silver, 10, sequence
        ),
    )


def _step(status=FlowStatus.COMPLETED, *, final_snapshot=None, error=None):
    return SimpleNamespace(status=status, final_snapshot=final_snapshot, error=error)


class FakeTradingRuntime:
    def __init__(self, reads, trace, *, leave_status=FlowStatus.COMPLETED):
        self.reads = reads
        self.trace = trace
        self.leave_status = leave_status
        self.leave_calls = 0
        self.ensure_calls = 0

    def ensure_avatar_keys(self):
        self.ensure_calls += 1
        self.trace.append("ensure_avatar_keys")
        if not self.reads:
            return _step(FlowStatus.FAILED, error="no_read")
        return _step(final_snapshot=_keys_snapshot(self.reads[0].snapshot.sequence - 1))

    def leave_to_lobby(self):
        self.leave_calls += 1
        self.trace.append("leave_trading")
        return _step(self.leave_status, error=(
            None if self.leave_status is FlowStatus.COMPLETED else "leave_failed"
        ))


class FakeTreasureRuntime:
    def __init__(
        self,
        trace,
        *,
        status=FlowStatus.COMPLETED,
        open_outcome=TreasureOutcome.SUCCESS,
    ):
        self.trace = trace
        self.status = status
        self.open_outcome = open_outcome
        self.calls = 0
        self.open_calls = 0

    def enter_treasure_from_lobby(self):
        self.calls += 1
        self.trace.append("enter_treasure")
        return _step(
            self.status,
            error=None if self.status is FlowStatus.COMPLETED else "enter_failed",
        )

    def execute_gold_key_open(self, quantity, *, max_actions):
        self.open_calls += 1
        self.trace.append("open_gold_once")
        return SimpleNamespace(
            outcome=self.open_outcome,
            reason=(
                None
                if self.open_outcome is TreasureOutcome.SUCCESS
                else self.open_outcome.value
            ),
        )


class FakeQuickMenuRuntime:
    def __init__(self, trace, *, status=FlowStatus.COMPLETED, sequence=20):
        self.trace = trace
        self.status = status
        self.sequence = sequence
        self.calls = 0

    def treasure_to_trading(self):
        self.calls += 1
        self.trace.append("quick_menu_to_trading")
        return _step(
            self.status,
            final_snapshot=(
                _keys_snapshot(self.sequence)
                if self.status is FlowStatus.COMPLETED
                else None
            ),
            error=None if self.status is FlowStatus.COMPLETED else "quick_failed",
        )


class Harness:
    def __init__(
        self,
        reads,
        outcomes,
        *,
        leave_status=FlowStatus.COMPLETED,
        treasure_status=FlowStatus.COMPLETED,
        treasure_open_outcome=TreasureOutcome.SUCCESS,
        quick_status=FlowStatus.COMPLETED,
        drain_outcome=GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED,
    ):
        self.trace = []
        self.reads = list(reads)
        self.outcomes = list(outcomes)
        self.trade_calls = []
        self.read_barriers = []
        self.drain_calls = 0
        self.trading = FakeTradingRuntime(
            self.reads, self.trace, leave_status=leave_status
        )
        self.treasure = FakeTreasureRuntime(
            self.trace,
            status=treasure_status,
            open_outcome=treasure_open_outcome,
        )
        self.quick = FakeQuickMenuRuntime(self.trace, status=quick_status)
        self.drain_outcome = drain_outcome
        self.runtime = KeysPromotionRuntime(
            self.trading,
            self.treasure,
            self.quick,
            read_key_facts=self.read,
            execute_key_trade=self.trade,
            drain_gold_keys=self.drain,
            acknowledge_gold_full=self.ack_gold_full,
        )

    def ack_gold_full(self, pending):
        self.trace.append("ack_gold_full")
        return GoldFullAckResult(
            FlowStatus.COMPLETED, final_snapshot=_keys_snapshot(3),
        )

    def read(self, after_sequence):
        self.trace.append("read_facts")
        self.read_barriers.append(after_sequence)
        return self.reads.pop(0)

    def trade(self, *, operation, snapshot, row_fact, quantity):
        self.trace.append(f"trade:{operation.value}")
        self.trade_calls.append((operation, snapshot, row_fact, quantity))
        outcome = self.outcomes.pop(0)
        after = None
        if outcome is TradeOutcome.SUCCESS:
            after = TradingRowFact(
                row_fact.item_id,
                row_fact.section,
                row_fact.row_y,
                max(0, row_fact.have - row_fact.need),
                row_fact.need,
                row_fact.sequence + 1,
            )
        return TradeResult(
            outcome,
            row_fact,
            after_fact=after,
            boundary="output_full" if outcome is TradeOutcome.OUTPUT_FULL else None,
            reason=None if outcome is TradeOutcome.SUCCESS else outcome.value,
        )

    def drain(self):
        self.drain_calls += 1
        self.trace.append("drain_gold")
        return GoldKeyDrainResult(
            self.drain_outcome,
            karat_boundary_seen=(
                self.drain_outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
            ),
        )


def test_no_tradeable_keys_completes_without_navigation_or_trade():
    harness = Harness([_facts(2, bronze=0, silver=0)], [])

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.COMPLETED
    assert not harness.trade_calls
    assert harness.trading.leave_calls == harness.treasure.calls == 0
    assert harness.quick.calls == harness.drain_calls == 0


def test_silver_success_rereads_fresh_facts_then_completes():
    harness = Harness(
        [_facts(2, bronze=0, silver=20), _facts(4, bronze=0, silver=0)],
        [TradeOutcome.SUCCESS],
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.COMPLETED
    assert result.trade_attempts == (KeyTradeOperation.SILVER_TO_GOLD,)
    assert harness.read_barriers == [1, 3]


def test_bronze_success_rereads_fresh_facts_then_completes():
    harness = Harness(
        [_facts(2, bronze=20, silver=0), _facts(4, bronze=0, silver=0)],
        [TradeOutcome.SUCCESS],
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.COMPLETED
    assert result.trade_attempts == (KeyTradeOperation.BRONZE_TO_SILVER,)


def test_trade_cancellation_propagates():
    harness = Harness(
        [_facts(2, bronze=0, silver=20)], [TradeOutcome.CANCELLED]
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.CANCELLED
    assert harness.trading.leave_calls == 0


def test_ordinary_trade_failure_propagates_without_navigation():
    harness = Harness([_facts(2, bronze=0, silver=20)], [TradeOutcome.FAILED])

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.trading.leave_calls == harness.drain_calls == 0


def _gold_full_harness(*, retry=TradeOutcome.SUCCESS, post_retry=True, **kwargs):
    reads = [
        _facts(2, bronze=0, silver=20),
        _facts(30, bronze=0, silver=20),
    ]
    if post_retry:
        reads.append(_facts(32, bronze=0, silver=0))
    return Harness(
        reads,
        [TradeOutcome.OUTPUT_FULL, retry],
        **kwargs,
    )


def test_gold_full_runs_exact_direct_route_and_retries_fresh_same_operation():
    harness = _gold_full_harness()

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.COMPLETED
    assert result.pending is not None
    assert result.pending.operation is KeyTradeOperation.SILVER_TO_GOLD
    assert result.recovery_count == result.retry_count == 1
    assert harness.trading.leave_calls == 1
    assert harness.treasure.calls == 1
    assert harness.treasure.open_calls == 1
    assert harness.drain_calls == 1
    assert harness.quick.calls == 1
    assert result.trade_attempts == (
        KeyTradeOperation.SILVER_TO_GOLD,
        KeyTradeOperation.SILVER_TO_GOLD,
    )
    assert harness.trade_calls[1][2].sequence == 30
    assert harness.trade_calls[1][3] == result.pending.quantity
    route = harness.trace[harness.trace.index("leave_trading"):]
    assert route[:8] == [
        "leave_trading",
        "enter_treasure",
        "open_gold_once",
        "drain_gold",
        "quick_menu_to_trading",
        "ensure_avatar_keys",
        "read_facts",
        "trade:silver_to_gold",
    ]
    assert "lobby" not in route[route.index("drain_gold") + 1:]


def test_source_aware_recovery_hooks_replace_only_physical_handoffs():
    harness = _gold_full_harness()
    route = []
    navigation = GoldCapacityRecoveryNavigation(
        source="monster_wave",
        leave_trading=lambda: route.append("x_to_mw") or _step(),
        enter_treasure=lambda: route.append("mw_to_treasure") or _step(),
        return_to_trading=lambda: route.append(
            "treasure_back_mw_to_trading"
        ) or _step(final_snapshot=_keys_snapshot(20)),
        leave_step="trading.x_to_monster_wave",
        enter_step="monster_wave.quick_menu_to_treasure",
        return_step="treasure.back_to_monster_wave.quick_menu_to_trading",
    )

    result = harness.runtime.run(
        budget_remaining=4,
        recovery_navigation=navigation,
    )

    assert result.status is FlowStatus.COMPLETED
    assert route == [
        "x_to_mw",
        "mw_to_treasure",
        "treasure_back_mw_to_trading",
    ]
    assert "leave_trading" not in harness.trace
    assert "enter_treasure" not in harness.trace
    assert "quick_menu_to_trading" not in harness.trace
    assert result.recovery_steps[0:4] == (
        "trading.ack_gold_full",
        "trading.x_to_monster_wave",
        "monster_wave.quick_menu_to_treasure",
        "treasure.open_gold_once",
    )


def test_fresh_lobby_is_required_before_treasure_entry():
    harness = _gold_full_harness(leave_status=FlowStatus.FAILED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.trading.leave_calls == 1
    assert harness.treasure.calls == harness.drain_calls == harness.quick.calls == 0


def test_treasure_failure_stops_before_drain_quick_menu_and_retry():
    harness = _gold_full_harness(treasure_status=FlowStatus.FAILED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.treasure.calls == 1
    assert harness.treasure.open_calls == 0
    assert harness.drain_calls == harness.quick.calls == 0


def test_cancelled_initial_gold_open_propagates_before_fast_drain():
    harness = _gold_full_harness(
        treasure_open_outcome=TreasureOutcome.CANCELLED
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.CANCELLED
    assert harness.treasure.open_calls == 1
    assert harness.drain_calls == harness.quick.calls == 0


def test_failed_initial_gold_open_stops_before_fast_drain():
    harness = _gold_full_harness(
        treasure_open_outcome=TreasureOutcome.FAILED
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.treasure.open_calls == 1
    assert harness.drain_calls == harness.quick.calls == 0
    assert len(harness.trade_calls) == 1


def test_treasure_cancellation_propagates():
    harness = _gold_full_harness(treasure_status=FlowStatus.CANCELLED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.CANCELLED
    assert harness.drain_calls == harness.quick.calls == 0


def test_trading_leave_cancellation_propagates_before_treasure():
    harness = _gold_full_harness(leave_status=FlowStatus.CANCELLED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.CANCELLED
    assert harness.treasure.calls == harness.drain_calls == 0


def test_failed_gold_drain_stops_before_quick_menu_and_retry():
    harness = _gold_full_harness(drain_outcome=GoldKeyDrainOutcome.FAILED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.drain_calls == 1
    assert harness.quick.calls == 0
    assert len(harness.trade_calls) == 1


def test_quick_menu_failure_stops_before_avatar_keys_reread_and_retry():
    harness = _gold_full_harness(quick_status=FlowStatus.FAILED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.quick.calls == 1
    assert len(harness.trade_calls) == 1
    assert harness.trading.ensure_calls == 1


def test_quick_menu_cancellation_propagates():
    harness = _gold_full_harness(quick_status=FlowStatus.CANCELLED)

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.CANCELLED
    assert len(harness.trade_calls) == 1


def test_pre_relief_or_stale_facts_cannot_authorize_retry():
    harness = Harness(
        [_facts(2, bronze=0, silver=20), _facts(2, bronze=0, silver=20)],
        [TradeOutcome.OUTPUT_FULL],
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert "stale_key_facts" in result.error
    assert len(harness.trade_calls) == 1


def test_retry_output_full_fails_closed_without_second_drain():
    harness = _gold_full_harness(
        retry=TradeOutcome.OUTPUT_FULL, post_retry=False
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert result.error == "causal_retry_output_full"
    assert harness.drain_calls == 1
    assert harness.quick.calls == 1
    assert len(harness.trade_calls) == 2


def test_later_gold_full_after_successful_recovery_never_recovers_twice():
    harness = Harness(
        [
            _facts(2, bronze=20, silver=20),
            _facts(30, bronze=20, silver=20),
            _facts(32, bronze=20, silver=20),
        ],
        [TradeOutcome.OUTPUT_FULL, TradeOutcome.SUCCESS, TradeOutcome.OUTPUT_FULL],
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert result.error == "gold_capacity_recovery_already_used"
    assert harness.drain_calls == 1


def test_bronze_output_full_never_triggers_gold_recovery():
    harness = Harness(
        [_facts(2, bronze=20, silver=0)], [TradeOutcome.OUTPUT_FULL]
    )

    result = harness.runtime.run(budget_remaining=3)

    assert result.status is FlowStatus.FAILED
    assert harness.drain_calls == harness.quick.calls == 0


def test_c6b_and_quick_menu_adapter_keep_neighbor_domains_out():
    import bot.keys_promotion_runtime as c6b
    import bot.quick_menu_trading as quick

    c6b_source = inspect.getsource(c6b).lower()
    quick_source = inspect.getsource(quick).lower()
    for forbidden in (
        "equipment",
        "inventory_relief",
        "combine",
        "sell",
        "craft",
        "monster_wave",
        "directed_list_scroll",
        "swipe",
        "up_to",
    ):
        assert forbidden not in c6b_source
    for forbidden in (
        "pendingcausaloperation",
        "keys_promotion",
        "output_full",
        "silver_to_gold",
    ):
        assert forbidden not in quick_source

def test_deferred_gold_full_acks_and_preserves_exact_pending():
    harness = _gold_full_harness()
    pending_result = harness.runtime.run(budget_remaining=3, defer_recovery=True)
    assert pending_result.status is FlowStatus.COMPLETED
    assert pending_result.pending is not None
    assert pending_result.pending.operation is KeyTradeOperation.SILVER_TO_GOLD
    assert pending_result.recovery_count == 0
    assert "ack_gold_full" in harness.trace
    assert harness.drain_calls == harness.trading.leave_calls == 0
    route = []
    navigation = GoldCapacityRecoveryNavigation(
        source="monster_wave",
        leave_trading=lambda: route.append("already_in_mw") or _step(),
        enter_treasure=lambda: route.append("enter_treasure") or _step(),
        return_to_trading=lambda: route.append("return_to_trading") or _step(
            final_snapshot=_keys_snapshot(20),
        ),
        leave_step="mw.anchor", enter_step="mw.to_treasure",
        return_step="treasure.to_mw.to_trading",
    )
    resolved = harness.runtime.resolve_pending(
        pending_result.pending, budget_remaining=2,
        recovery_navigation=navigation,
    )
    assert resolved.status is FlowStatus.COMPLETED
    assert resolved.retry_count == resolved.recovery_count == 1
    assert route == ["already_in_mw", "enter_treasure", "return_to_trading"]
    assert harness.drain_calls == 1
    assert harness.trade_calls[1][3] == pending_result.pending.quantity


def test_deferred_retry_output_full_never_starts_second_cycle():
    harness = _gold_full_harness(retry=TradeOutcome.OUTPUT_FULL, post_retry=False)
    pending = harness.runtime.run(budget_remaining=3, defer_recovery=True).pending
    assert pending is not None
    navigation = GoldCapacityRecoveryNavigation(
        source="monster_wave",
        leave_trading=lambda: _step(),
        enter_treasure=lambda: _step(),
        return_to_trading=lambda: _step(final_snapshot=_keys_snapshot(20)),
        leave_step="mw.anchor", enter_step="mw.to_treasure",
        return_step="treasure.to_mw.to_trading",
    )
    resolved = harness.runtime.resolve_pending(
        pending, budget_remaining=2, recovery_navigation=navigation,
    )
    assert resolved.status is FlowStatus.FAILED
    assert resolved.retry_count == resolved.recovery_count == 1
    assert harness.drain_calls == 1


def test_output_full_ack_needs_fresh_alert_and_clean_keys_after_one_ok():
    from bot.keys_promotion_runtime import acknowledge_gold_full_boundary
    from bot.trading_operation import TradePanelFact
    harness = _gold_full_harness()
    pending = harness.runtime.run(budget_remaining=3, defer_recovery=True).pending
    assert pending is not None
    taps = []
    panel = TradePanelFact(
        item_id="gold_key", input_have=20, input_need=10,
        quantity=None, sequence=pending.before_fact.sequence + 1,
        shows_output_full=True,
    )
    result = acknowledge_gold_full_boundary(
        pending,
        read_panel=lambda: panel,
        tap_ok=lambda: taps.append("ok"),
        read_keys_context=lambda *, after_sequence: _keys_snapshot(after_sequence + 1),
    )
    assert result.status is FlowStatus.COMPLETED
    assert taps == ["ok"]
    taps.clear()
    stale = acknowledge_gold_full_boundary(
        pending,
        read_panel=lambda: TradePanelFact(
            item_id="gold_key", input_have=20, input_need=10, quantity=None,
            sequence=pending.before_fact.sequence, shows_output_full=True,
        ),
        tap_ok=lambda: taps.append("wrong"),
        read_keys_context=lambda **kwargs: _keys_snapshot(99),
    )
    assert stale.status is FlowStatus.FAILED
    assert taps == []
