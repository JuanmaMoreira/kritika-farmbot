"""Parametrized demand and payment guards reuse the Ads purchase owner."""
from types import SimpleNamespace as NS
import pytest
from test_stamina_batch import purchase
from bot.stamina_purchase import PAYMENT_ROI,QUANTITY_ROI
from bot.semantic_actions import ConfirmTradingTrade,OpenTrading,CancelTradingTrade
from bot.stages_actions import StageControl as C,StageAction
from bot.stages_balances import StageBalances

def manual(have,required,*,coins=4000,cap=20,price=200,after=None,inconclusive=False):
    count=min((max(0,required-have)+49)//50,cap,coins//200)
    op,before,fresh,actions,_=purchase(have,cap=cap,
        after=after if after is not None else have+count*50,inconclusive=inconclusive)
    def pair(s,roi):
        return s.quantity if roi==QUANTITY_ROI else (coins,price*s.quantity[0])
    op.balances.pair=pair
    act=op.nav.act
    def guarded_action(action,s):
        if isinstance(action,CancelTradingTrade):s.flags={'currency','stamina_row'}
        act(action,s)
    op.nav.act=guarded_action
    return op,before,fresh,actions

@pytest.mark.parametrize('have,required,trades',[(59,60,1),(1,60,2),(60,60,0),
    (180,600,9),(300,480,4),(480,480,0)])
def test_demand_uses_real_packets_no_ads300_requirement(have,required,trades):
    op,before,after,actions=manual(have,required)
    r=op.supply(before,required)
    assert r.covered and r.purchased==trades*50
    assert r.kcoin_cost == (trades*200 if trades else None)
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==bool(trades)
    assert sum(isinstance(a,OpenTrading) for a in actions)==bool(trades)
    assert not op.pending

@pytest.mark.parametrize('coins,cap,bought,outcome',[(199,20,0,'insufficient_kcoins'),
    (400,20,100,'insufficient_kcoins'),(4000,2,100,'trade_limit')])
def test_partial_or_impossible_coverage_returns_verified_lobby(coins,cap,bought,outcome):
    op,before,_,actions=manual(0,600,coins=coins,cap=cap)
    result=op.supply(before,600)
    assert result.purchased==bought and not result.covered and result.outcome==outcome
    assert type(actions[-1]).__name__=='CloseTrading'
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==bool(bought)

def test_changed_price_rejects_confirmation_and_premium():
    op,before,_,actions=manual(1,60,price=201)
    with pytest.raises(ValueError,match='K Coin200'):op.supply(before,60)
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)

def test_explicit_zero_trade_capacity_is_functional_and_no_confirmation():
    op,before,_,actions=manual(0,60,cap=0)
    before.snapshot.quantity=(0,0)
    result=op.supply(before,60)
    assert result.outcome=='trade_limit' and not result.covered and result.purchased==0
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)

def test_unacquired_cap_cannot_authorize_unbounded_setup_or_purchase():
    op,before,_,actions=manual(0,6000,cap=200)
    with pytest.raises(ValueError,match='acquired bounds'):op.supply(before,6000)
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)
    assert not any(isinstance(a,StageAction) and a.control is C.STAMINA_INCREMENT for a in actions)

def test_fresh_final_payment_must_cover_total_quantity():
    op,before,_,actions=manual(1,60)
    reads=0
    original=op.balances.pair
    def pair(s,roi):
        nonlocal reads
        if roi==PAYMENT_ROI:
            reads+=1
            if reads==2:return (199,400)
        return original(s,roi)
    op.balances.pair=pair
    with pytest.raises(ValueError,match='coverage'):op.supply(before,60)
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)

@pytest.mark.parametrize('inconclusive,after',[(True,None),(False,59)])
def test_uncertain_confirmation_retains_receipt_and_never_repeats(inconclusive,after):
    op,before,_,actions=manual(59,60,after=after,inconclusive=inconclusive)
    with pytest.raises((TimeoutError,ValueError)):op.supply(before,60)
    assert op.pending is not None
    # Even if regen now supplies a full packet, unchanged payment is no proof.
    op.balances.read=lambda:StageBalances(109,0,102,before.snapshot)
    with pytest.raises(ValueError,match='payment unresolved'):op.supply(before,60)
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==1

def test_reconciled_payment_then_stamina_gain_closes_without_new_trade():
    op,before,after,actions=manual(59,60,inconclusive=True)
    with pytest.raises(TimeoutError):op.supply(before,60)
    pair=op.balances.pair
    op.balances.pair=lambda s,roi:(3800,200) if roi==PAYMENT_ROI else pair(s,roi)
    r=op.supply(before,60)
    assert r.covered and r.purchased==50 and not op.pending
    assert r.kcoin_cost == 200
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==1

def test_normal_claim_precedes_demand_and_sufficient_balance_skips_trade():
    from test_manual_stages import operation,snap
    op,nav=operation();trace=[]
    values=iter([NS(stamina=30,sapphires=0,sapphire_limit=102),
        NS(stamina=60,sapphires=0,sapphire_limit=102)])
    op.balances.read=lambda:trace.append('read') or next(values)
    nav.enter_episode=lambda episode:trace.append('claim') or snap('normal')
    nav.exit_to_lobby=lambda s:trace.append('lobby')
    from bot.stamina_purchase import StaminaSupplyResult
    op.stamina_purchase=NS(pending=None,supply=lambda before,required:
        trace.append(('supply',before.stamina,required)) or StaminaSupplyResult(before,required))
    r=op.prepare_stamina(60)
    assert trace==['read','claim','lobby','read',('supply',60,60)] and r.covered
