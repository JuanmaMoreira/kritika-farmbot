"""Reuse only C4's successful, fresh, exact effect evidence."""
from dataclasses import replace
from unittest.mock import Mock
import pytest
from bot.keys_promotion_runtime import FreshKeyFacts, KeysPromotionRuntime, VerifiedKeyTradeResult
from bot.trading_operation import TradeOutcome, TradeResult
from bot.trading_row_facts import TradingRowFact
from test_trading_key_row_reader import snapshot


def facts(sequence,bronze,silver):
    return FreshKeyFacts(snapshot(sequence),
        TradingRowFact('silver_key','keys',.42,bronze,10,sequence),
        TradingRowFact('gold_key','keys',.56,silver,10,sequence))


def setup(clock=11.5):
    before=facts(10,40,60);after=facts(11,30,62)
    result=VerifiedKeyTradeResult(TradeOutcome.SUCCESS,before.silver_fact,after.silver_fact,
                                 inputs=('tap_row','tap_confirm'),fresh_key_facts=after)
    runtime=KeysPromotionRuntime(Mock(),Mock(),Mock(),read_key_facts=Mock(),
        execute_key_trade=Mock(),drain_gold_keys=Mock(),clock=lambda:clock)
    runtime._fresh_facts=Mock(return_value='reacquired')
    return runtime,before,after,result


def test_c4_consensus_is_used_once_without_new_capture_or_navigation():
    runtime,before,after,result=setup()
    assert runtime._facts_after_trade(before,result) is after
    runtime._fresh_facts.assert_not_called()
    runtime.trading_runtime.ensure_avatar_keys.assert_not_called()


@pytest.mark.parametrize('change',('expired','future','different_effect','old_sequence','no_effect','ordinary_result'))
def test_reuse_fails_closed_or_reacquires_on_invalid_evidence(change):
    runtime,before,after,result=setup(15 if change=='expired' else 10 if change=='future' else 11.5)
    if change=='different_effect': result=replace(result,after_fact=replace(result.after_fact,have=29))
    if change=='old_sequence':
        after=facts(10,30,62);result=replace(result,after_fact=after.silver_fact,fresh_key_facts=after)
    if change=='no_effect': result=replace(result,outcome=TradeOutcome.NO_EFFECT)
    if change=='ordinary_result': result=TradeResult(TradeOutcome.SUCCESS,before.silver_fact,after.silver_fact)
    assert runtime._facts_after_trade(before,result)=='reacquired'
    runtime._fresh_facts.assert_called_once()


def test_productive_c4_attaches_same_two_row_consensus_used_for_effect():
    from bot.trading_key_facts_reader import execute_productive_key_trade
    from bot.trading_keys import KeyTradeOperation
    from bot.trading_operation import TradePanelFact,TradeQuantity,TradeQuantityMode
    before=facts(10,40,60);after=facts(15,30,62)
    panel=TradePanelFact('silver_key',40,10,(1,20),sequence=11)
    class Observer:
        def wait_until(self,condition,**kwargs):
            item=snapshot(12 if kwargs['after_sequence']==10 else 14)
            assert condition(item);return item
    reader=Mock();reader.read_snapshot.side_effect=(panel,None)
    actions=Mock();read=Mock(return_value=after)
    result=execute_productive_key_trade(operation=KeyTradeOperation.BRONZE_TO_SILVER,
        snapshot=before.snapshot,row_fact=before.silver_fact,
        quantity=TradeQuantity(TradeQuantityMode.EXACT,1),observer=Observer(),actions=actions,
        panel_reader=reader,read_facts=read,cancel_requested=lambda:False,clock=lambda:13.5)
    assert result.outcome is TradeOutcome.SUCCESS
    assert isinstance(result,VerifiedKeyTradeResult) and result.fresh_key_facts is after
    assert result.after_fact is after.silver_fact
    assert result.inputs.count('tap_confirm')==1
    read.assert_called_once_with(14)  # post-confirm frame; same consensus, no reread
