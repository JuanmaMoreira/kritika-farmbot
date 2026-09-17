"""C6a pure Keys promotion policy: order, refresh, quantity, boundaries."""

import inspect
from pathlib import Path

import pytest

from bot.keys_promotion import (
    KeysPromotionDecision,
    KeysPromotionKind,
    PendingCausalOperation,
    decide_after_trade,
    decide_next_keys_operation,
    default_keys_quantity,
    is_tradeable,
    pending_field_names,
)
from bot.trading_keys import KeyTradeOperation
from bot.trading_operation import TradeOutcome, TradeQuantityMode, TradeResult
from bot.trading_row_facts import KEYS_SECTION, MATERIALS_SECTION, TradingRowFact

BRONZE_ROW = "silver_key"  # Bronze input, Silver output.
SILVER_ROW = "gold_key"  # Silver input, Gold output.

POLICY_SOURCE = (
    Path(__file__).resolve().parent.parent / "bot" / "keys_promotion.py"
).read_text(encoding="utf-8")


def _fact(item_id, have, need, sequence, row_y=0.5):
    return TradingRowFact(
        item_id=item_id,
        section=KEYS_SECTION,
        row_y=row_y,
        have=have,
        need=need,
        sequence=sequence,
        evidence=(f"sample@{sequence}:{have}/{need}",),
    )


def _silver(have, need=10, sequence=10):
    return _fact(BRONZE_ROW, have, need, sequence, row_y=0.57)


def _gold(have, need=10, sequence=10):
    return _fact(SILVER_ROW, have, need, sequence, row_y=0.71)


def _decide(silver_have, gold_have, budget=3, need=10, sequence=10):
    return decide_next_keys_operation(
        silver_fact=_silver(silver_have, need, sequence),
        gold_fact=_gold(gold_have, need, sequence),
        budget_remaining=budget,
    )


def _result(outcome, before, after=None, boundary=None, reason=None):
    return TradeResult(
        outcome=outcome,
        before_fact=before,
        after_fact=after,
        boundary=boundary,
        reason=reason if reason is not None else outcome.value,
        evidence=(f"outcome:{outcome.value}",),
    )


def _after(previous, outcome, silver, gold, budget, **overrides):
    before_id = (
        SILVER_ROW if previous.operation is KeyTradeOperation.SILVER_TO_GOLD
        else BRONZE_ROW
    )
    before = _fact(before_id, 25, 10, 10)
    values = {
        "previous": previous,
        "result": _result(outcome, before, **overrides),
        "budget_remaining": budget,
        "silver_fact": silver,
        "gold_fact": gold,
    }
    return decide_after_trade(**values)


# Order: Silver->Gold first whenever Silver covers its need.

def test_both_tradeable_prefers_silver_to_gold():
    decision = _decide(silver_have=50, gold_have=25)
    assert decision.kind is KeysPromotionKind.NEXT_OPERATION
    assert decision.operation is KeyTradeOperation.SILVER_TO_GOLD


def test_silver_only_prefers_silver_to_gold():
    decision = _decide(silver_have=5, gold_have=25)
    assert decision.kind is KeysPromotionKind.NEXT_OPERATION
    assert decision.operation is KeyTradeOperation.SILVER_TO_GOLD


def test_bronze_only_requests_bronze_to_silver():
    decision = _decide(silver_have=50, gold_have=5)
    assert decision.kind is KeysPromotionKind.NEXT_OPERATION
    assert decision.operation is KeyTradeOperation.BRONZE_TO_SILVER


def test_neither_tradeable_is_terminal():
    decision = _decide(silver_have=5, gold_have=5)
    assert decision.kind is KeysPromotionKind.NO_MORE_PROMOTIONS
    assert decision.operation is None
    assert decision.quantity is None
    assert decision.pending is None


def test_exact_need_counts_as_tradeable():
    decision = _decide(silver_have=10, gold_have=10)
    assert decision.operation is KeyTradeOperation.SILVER_TO_GOLD
    boundary = _decide(silver_have=9, gold_have=10)
    assert boundary.operation is KeyTradeOperation.SILVER_TO_GOLD
    bronze = _decide(silver_have=10, gold_have=9)
    assert bronze.operation is KeyTradeOperation.BRONZE_TO_SILVER


# Refresh: SUCCESS never authorizes a second trade on the old snapshot.

def test_success_silver_to_gold_rejects_stale_snapshot():
    previous = _decide(silver_have=50, gold_have=25)
    stale_silver = _silver(50, sequence=10)
    stale_gold = _gold(25, sequence=10)
    decision = _after(
        previous, TradeOutcome.SUCCESS, stale_silver, stale_gold, budget=2,
        after=_gold(20, sequence=13),
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "stale_facts"
    assert decision.operation is None


def test_success_bronze_to_silver_rejects_stale_snapshot():
    previous = _decide(silver_have=50, gold_have=5)
    assert previous.operation is KeyTradeOperation.BRONZE_TO_SILVER
    decision = _after(
        previous, TradeOutcome.SUCCESS, _silver(50, sequence=10),
        _gold(5, sequence=10), budget=2, after=_silver(40, sequence=13),
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "stale_facts"


def test_success_with_fresh_facts_redecides_silver_first():
    previous = _decide(silver_have=50, gold_have=5)
    decision = _after(
        previous, TradeOutcome.SUCCESS, _silver(40, sequence=11),
        _gold(15, sequence=12), budget=2, after=_silver(40, sequence=13),
    )
    assert decision.kind is KeysPromotionKind.NEXT_OPERATION
    assert decision.operation is KeyTradeOperation.SILVER_TO_GOLD


def test_success_with_fresh_empty_facts_terminates():
    previous = _decide(silver_have=50, gold_have=25)
    decision = _after(
        previous, TradeOutcome.SUCCESS, _silver(5, sequence=11),
        _gold(5, sequence=12), budget=2, after=_gold(20, sequence=13),
    )
    assert decision.kind is KeysPromotionKind.NO_MORE_PROMOTIONS


def test_half_refreshed_snapshot_stays_stale():
    previous = _decide(silver_have=50, gold_have=5)
    decision = _after(
        previous, TradeOutcome.SUCCESS, _silver(40, sequence=11),
        _gold(15, sequence=10), budget=2, after=_silver(40, sequence=13),
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "stale_facts"


def test_after_fact_of_one_row_never_feeds_the_other():
    previous = _decide(silver_have=50, gold_have=5)
    params = set(inspect.signature(decide_after_trade).parameters)
    assert "after_fact" not in params
    # Even when C5 reports a rich after_fact, the next step still needs
    # an explicit fresh fact-set for both rows.
    decision = decide_after_trade(
        previous=previous,
        result=_result(
            TradeOutcome.SUCCESS, _silver(50, 10, 10),
            after=_silver(40, 10, 13),
        ),
        budget_remaining=2,
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "missing_facts"


# Quantity: explicit MAX_ALLOWED, delegated descriptively, no capacity math.

def test_next_quantity_is_max_allowed():
    for decision in (
        _decide(silver_have=50, gold_have=25),
        _decide(silver_have=50, gold_have=5),
    ):
        assert decision.quantity is not None
        assert decision.quantity.mode is TradeQuantityMode.MAX_ALLOWED
        assert decision.quantity.amount is None
        assert decision.quantity == default_keys_quantity()


def test_no_output_capacity_arithmetic_in_policy():
    assert "_key_counts" not in POLICY_SOURCE
    assert "499" not in POLICY_SOURCE


def test_next_carries_causal_facts_for_audit():
    decision = _decide(silver_have=50, gold_have=25)
    assert decision.silver_fact is not None
    assert decision.gold_fact is not None
    assert decision.silver_fact.item_id == BRONZE_ROW
    assert decision.gold_fact.item_id == SILVER_ROW
    assert "order:silver_first" in decision.evidence


# Boundaries: Gold-full preserves the causal request; the rest fail closed.

def test_output_full_silver_to_gold_preserves_causal_boundary():
    previous = _decide(silver_have=50, gold_have=25)
    before = _gold(25, sequence=10)
    result = _result(
        TradeOutcome.OUTPUT_FULL, before,
        boundary="output_full", reason="output_full_on_open",
    )
    decision = decide_after_trade(
        previous=previous, result=result, budget_remaining=2,
        silver_fact=_silver(50, sequence=11),
        gold_fact=_gold(25, sequence=12),
    )
    assert decision.kind is KeysPromotionKind.GOLD_CAPACITY_BLOCKED
    assert decision.operation is None
    pending = decision.pending
    assert isinstance(pending, PendingCausalOperation)
    assert pending.operation is KeyTradeOperation.SILVER_TO_GOLD
    assert pending.quantity.mode is TradeQuantityMode.MAX_ALLOWED
    assert pending.before_fact == before
    assert pending.boundary == "output_full"
    assert "boundary:output_full" in pending.evidence


def test_gold_boundary_needs_no_fresh_reads():
    previous = _decide(silver_have=50, gold_have=25)
    result = _result(
        TradeOutcome.OUTPUT_FULL, _gold(25, sequence=10),
        boundary="output_full", reason="output_full_on_open",
    )
    decision = decide_after_trade(
        previous=previous, result=result, budget_remaining=2,
    )
    assert decision.kind is KeysPromotionKind.GOLD_CAPACITY_BLOCKED
    assert decision.pending is not None


def test_pending_carries_no_treasure_routing_or_amount():
    names = set(pending_field_names())
    assert names == {
        "operation", "quantity", "before_fact",
        "boundary", "reason", "evidence",
    }
    for forbidden in ("route", "back", "lobby", "retry", "treasure",
                      "amount", "repeat", "should_"):
        assert forbidden not in names, forbidden
    previous = _decide(silver_have=50, gold_have=25)
    result = _result(
        TradeOutcome.OUTPUT_FULL, _gold(25, sequence=10),
        boundary="output_full", reason="output_full_on_open",
    )
    pending = decide_after_trade(
        previous=previous, result=result, budget_remaining=2,
    ).pending
    assert pending is not None
    joined = " ".join(pending.evidence).casefold()
    assert "treasure" not in joined


def test_output_full_bronze_to_silver_fails_closed():
    previous = _decide(silver_have=50, gold_have=5)
    result = _result(
        TradeOutcome.OUTPUT_FULL, _silver(50, sequence=10),
        boundary="output_full", reason="output_full_on_open",
    )
    decision = decide_after_trade(
        previous=previous, result=result, budget_remaining=2,
        silver_fact=_silver(50, sequence=11),
        gold_fact=_gold(5, sequence=12),
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "unexpected_output_full"
    assert decision.pending is None


@pytest.mark.parametrize("outcome", [
    TradeOutcome.NO_EFFECT,
    TradeOutcome.FAILED,
    TradeOutcome.CANCELLED,
])
def test_terminal_outcomes_do_not_authorize_another_trade(outcome):
    previous = _decide(silver_have=50, gold_have=25)
    decision = _after(
        previous, outcome, _silver(50, sequence=11),
        _gold(25, sequence=12), budget=2,
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.operation is None
    assert decision.pending is None


def test_limit_reached_fails_closed():
    previous = _decide(silver_have=50, gold_have=25)
    decision = _after(
        previous, TradeOutcome.LIMIT_REACHED, _silver(50, sequence=11),
        _gold(25, sequence=12), budget=2, boundary="limit_reached",
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "limit_reached"


def test_insufficient_input_requires_fresh_facts():
    previous = _decide(silver_have=50, gold_have=25)
    stale = _after(
        previous, TradeOutcome.INSUFFICIENT_INPUT,
        _silver(50, sequence=10), _gold(25, sequence=10), budget=2,
        boundary="insufficient_input",
    )
    assert stale.kind is KeysPromotionKind.FAILED
    assert stale.reason == "stale_facts"


def test_insufficient_input_with_fresh_empty_facts_terminates():
    previous = _decide(silver_have=50, gold_have=25)
    decision = _after(
        previous, TradeOutcome.INSUFFICIENT_INPUT,
        _silver(5, sequence=11), _gold(5, sequence=12), budget=2,
        boundary="insufficient_input",
    )
    assert decision.kind is KeysPromotionKind.NO_MORE_PROMOTIONS


def test_no_more_input_with_fresh_bronze_authorizes_next():
    previous = _decide(silver_have=50, gold_have=25)
    decision = _after(
        previous, TradeOutcome.NO_MORE_INPUT,
        _silver(50, sequence=11), _gold(5, sequence=12), budget=2,
    )
    assert decision.kind is KeysPromotionKind.NEXT_OPERATION
    assert decision.operation is KeyTradeOperation.BRONZE_TO_SILVER


# Budget: explicit, bounded, no hidden loops.

def test_zero_budget_authorizes_nothing():
    decision = _decide(silver_have=50, gold_have=25, budget=0)
    assert decision.kind is KeysPromotionKind.BUDGET_EXHAUSTED
    assert decision.operation is None
    assert decision.quantity is None


def test_budget_exhausted_after_bounded_steps():
    first = _decide(silver_have=50, gold_have=5, budget=1)
    assert first.kind is KeysPromotionKind.NEXT_OPERATION
    decision = _after(
        first, TradeOutcome.SUCCESS, _silver(40, sequence=11),
        _gold(15, sequence=12), budget=0, after=_silver(40, sequence=13),
    )
    assert decision.kind is KeysPromotionKind.BUDGET_EXHAUSTED
    assert decision.operation is None


@pytest.mark.parametrize("budget", [-1, "3", None, True, 2.5])
def test_invalid_budget_is_a_programmer_error(budget):
    with pytest.raises(ValueError):
        _decide(silver_have=50, gold_have=25, budget=budget)


def test_budget_has_no_default():
    for function in (decide_next_keys_operation, decide_after_trade):
        parameter = inspect.signature(function).parameters["budget_remaining"]
        assert parameter.default is inspect.Parameter.empty


def test_policy_runs_no_loops():
    import bot.keys_promotion as policy

    for function in (policy.decide_next_keys_operation,
                     policy.decide_after_trade):
        source = inspect.getsource(function)
        assert "while" not in source
        assert "for " not in source


# Facts: incompatible rows fail closed without authorizing input.

def test_wrong_row_identity_fails_closed():
    decision = decide_next_keys_operation(
        silver_fact=_gold(25, sequence=10),
        gold_fact=_gold(25, sequence=10),
        budget_remaining=3,
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "silver_fact_mismatch"
    assert decision.operation is None


def test_material_row_fails_closed():
    material = TradingRowFact(
        item_id="hero_weapon_crafting_material",
        section=MATERIALS_SECTION, row_y=0.5,
        have=100, need=10, sequence=10,
    )
    decision = decide_next_keys_operation(
        silver_fact=material, gold_fact=_gold(25, sequence=10),
        budget_remaining=3,
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.operation is None


def test_incoherent_need_fails_closed():
    decision = decide_next_keys_operation(
        silver_fact=_silver(50, need=0, sequence=10),
        gold_fact=_gold(25, sequence=10),
        budget_remaining=3,
    )
    assert decision.kind is KeysPromotionKind.FAILED
    assert decision.reason == "incoherent_need"


@pytest.mark.parametrize("silver,gold", [
    (None, None), ("silver_key", "gold_key"), (123, 456),
])
def test_wrong_fact_types_are_programmer_errors(silver, gold):
    with pytest.raises(ValueError):
        decide_next_keys_operation(
            silver_fact=silver, gold_fact=gold, budget_remaining=3,
        )


def test_is_tradeable_uses_have_over_need():
    assert is_tradeable(_silver(10, need=10, sequence=1))
    assert is_tradeable(_silver(11, need=10, sequence=1))
    assert not is_tradeable(_silver(9, need=10, sequence=1))
    assert not is_tradeable(_silver(10, need=0, sequence=1))
    with pytest.raises(ValueError):
        is_tradeable("50/10")


# Separation: pure policy, no UI, no sinks, no capacity inference.

def test_module_has_no_sink_or_hardware_imports():
    import_lines = [
        line for line in POLICY_SOURCE.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("treasure", "craft", "relief", "monster_wave",
                      "planner", "stage", "inventory", "adb",
                      "action_executor", "capture", "tap", "swipe",
                      "gesture", "scroll", "emit", "human_input"):
        assert forbidden not in joined, forbidden


def test_module_has_no_routing_or_counts_constructs():
    assert "GoldKeyOpenRequest" not in POLICY_SOURCE
    assert "route_plan" not in POLICY_SOURCE
    assert "def should_" not in POLICY_SOURCE
    assert "def promote" not in POLICY_SOURCE
    assert "def _key_counts" not in POLICY_SOURCE
    assert "_key_counts(" not in POLICY_SOURCE


def test_signatures_take_no_io_or_targets():
    forbidden = {"tap", "read_panel", "read_row", "read_state", "targets",
                 "cancel_requested", "max_point", "confirm_point", "emit",
                 "swipe", "gesture"}
    for function in (decide_next_keys_operation, decide_after_trade):
        assert not (set(inspect.signature(function).parameters) & forbidden)


def test_gold_capacity_stays_not_observable():
    assert "NOT OBSERVABLE" in POLICY_SOURCE
    assert "Gold capacity is NOT OBSERVABLE" in POLICY_SOURCE


def test_no_retry_vocabulary_in_policy():
    assert "retry" not in POLICY_SOURCE.casefold()
