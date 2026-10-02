from bot.keys_promotion import (decide_next_keys_operation, decide_after_trade,
    KeysPromotionPhase as Phase, KeysPromotionKind as Kind)
from bot.trading_row_facts import TradingRowFact, KEYS_SECTION
from bot.trading_keys import KeyTradeOperation as Op
from bot.trading_operation import TradeQuantityMode as Q, TradeOutcome, TradeResult


def rows(bronze,silver,sequence):
    return dict(silver_fact=TradingRowFact('silver_key',KEYS_SECTION,.43,bronze,10,sequence),
                gold_fact=TradingRowFact('gold_key',KEYS_SECTION,.57,silver,10,sequence))


def step(bronze,silver,phase=Phase.INITIAL):
    return decide_next_keys_operation(**rows(bronze,silver,10),budget_remaining=100,phase=phase)


def test_complete_bronze_fits_then_fresh_facts_preserve_bronze_until_exhausted():
    decision=step(410,416)
    assert decision.operation is Op.BRONZE_TO_SILVER
    sequence=[]
    for b,s in ((210,456),(10,496),(0,498),(0,298),(0,98),(0,8)):
        sequence.append(decision.operation)
        previous=decision.silver_fact if decision.operation is Op.BRONZE_TO_SILVER else decision.gold_fact
        fresh=rows(b,s,previous.sequence+2)
        result=TradeResult(TradeOutcome.SUCCESS,before_fact=previous,
                          after_fact=fresh['silver_fact' if decision.operation is Op.BRONZE_TO_SILVER else 'gold_fact'])
        decision=decide_after_trade(previous=decision,result=result,budget_remaining=99,**fresh)
    assert sequence==[Op.BRONZE_TO_SILVER]*3+[Op.SILVER_TO_GOLD]*3
    assert decision.kind is Kind.NO_MORE_PROMOTIONS


def test_minimum_predrain_stops_as_soon_as_whole_bronze_fits():
    first=step(490,499)
    assert first.phase is Phase.SILVER_PRE_DRAIN
    assert (first.quantity.mode,first.quantity.amount)==(Q.EXACT,1)
    # 98 minted Silver needs ten conversions of ten Silver to make room.
    assert step(490,409,Phase.SILVER_PRE_DRAIN).operation is Op.SILVER_TO_GOLD
    assert step(490,399,Phase.SILVER_PRE_DRAIN).operation is Op.BRONZE_TO_SILVER


def test_bronze_phase_does_not_predrain_for_a_later_batch_that_still_has_room_now():
    assert step(490,450,Phase.BRONZE).operation is Op.BRONZE_TO_SILVER
    assert step(490,470,Phase.BRONZE).operation is Op.SILVER_TO_GOLD
    assert step(490,450,step(490,470,Phase.BRONZE).phase).operation is Op.BRONZE_TO_SILVER


def test_bronze_exhaustion_enters_silver_final_max():
    decision=step(9,499,Phase.BRONZE)
    assert decision.phase is Phase.SILVER_FINAL
    assert decision.quantity.mode is Q.MAX_ALLOWED


def test_zero_budget_does_not_authorize_phase_input():
    decision=decide_next_keys_operation(**rows(490,499,10),budget_remaining=0)
    assert decision.kind is Kind.BUDGET_EXHAUSTED
