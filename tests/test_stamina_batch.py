from types import SimpleNamespace as S
import pytest

from bot.stamina_purchase import StaminaPurchase, QUANTITY_ROI
from bot.stages_actions import StageAction, StageControl as C
from bot.semantic_actions import ConfirmTradingTrade, OpenTrading
from bot.stages_balances import StageBalances
from bot.state import ResolutionStatus

def purchase(have, *, cap=20, broken_selection=False, after=None, inconclusive=False):
    current=S(sequence=1,flags=set(),quantity=(1,cap),state=S(base_context='screen.lobby',
        status=ResolutionStatus.RESOLVED,overlays=()))
    current.frame=S(image=current)
    actions=[];reads=[]
    def act(a,s):
        actions.append(a)
        if isinstance(a,OpenTrading):current.flags={'currency','stamina_row'}
        elif isinstance(a,StageAction) and a.control==C.STAMINA_ROW:
            current.flags={'stamina_panel','kcoin'}
        elif isinstance(a,StageAction) and a.control==C.STAMINA_INCREMENT:
            if not broken_selection:current.quantity=(current.quantity[0]+1,cap)
        elif isinstance(a,ConfirmTradingTrade):
            if not inconclusive:current.flags={'currency','stamina_row'}
        current.state.base_context='screen.lobby' if type(a).__name__=='CloseTrading' else 'screen.trading'
    def wait(predicate):
        if not predicate(current):raise TimeoutError('fresh effect inconclusive')
        return current
    def pair(s,roi):
        assert roi==QUANTITY_ROI  # no currency OCR
        reads.append(roi);return s.quantity
    before=StageBalances(have,0,102,current)
    fresh=StageBalances(after if after is not None else have+50*((max(0,300-have)+49)//50),0,102,current)
    nav=S(act=act,wait=wait,events=None,clock=lambda:10.,
        stamina_increments=lambda count,s:[act(StageAction(C.STAMINA_INCREMENT),s) for _ in range(count)])
    balances=S(pair=pair,read=lambda:fresh)
    detector=S(present=lambda frame,k:k in frame.flags)
    return StaminaPurchase(nav,balances,detector),before,fresh,actions,reads

@pytest.mark.parametrize('have,trades',[(299,1),(250,1),(249,2),(140,4),(50,5),(300,0),(440,0)])
def test_exact_batch_from_fresh_have(have,trades):
    op,before,after,actions,reads=purchase(have)
    result=op.ensure(before)
    assert result is (after if trades else before)
    assert sum(isinstance(a,OpenTrading) for a in actions)==bool(trades)
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==bool(trades)
    assert sum(isinstance(a,StageAction) and a.control==C.STAMINA_INCREMENT for a in actions)==max(0,trades-1)
    if not trades:assert not reads
    else:assert len(reads)==2  # initial quantity and final quantity, never between > taps

def test_selection_effect_inconclusive_never_confirms_or_retries():
    op,before,_,actions,_=purchase(140,broken_selection=True)
    with pytest.raises(ValueError,match='selected quantity mismatch'):op.ensure(before)
    assert sum(isinstance(a,StageAction) and a.control==C.STAMINA_INCREMENT for a in actions)==3
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)

def test_panel_cap_below_requested_diagnoses_without_consumption():
    op,before,_,actions,_=purchase(50,cap=4)
    with pytest.raises(ValueError,match='cap 4 below requested 5'):op.ensure(before)
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)

@pytest.mark.parametrize('inconclusive,after',[(True,None),(False,250)])
def test_unverified_consumption_never_confirms_twice(inconclusive,after):
    op,before,_,actions,_=purchase(140,inconclusive=inconclusive,after=after)
    with pytest.raises((TimeoutError,ValueError)):op.ensure(before)
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==1

def test_final_quantity_verification_failure_never_confirms():
    op,before,_,actions,_=purchase(250)
    reads=iter([(1,20),(2,20)])
    op.balances.pair=lambda *a:next(reads)
    with pytest.raises(ValueError,match='selected quantity mismatch'):op.ensure(before)
    assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)


def test_final_frame_before_quantity_update_waits_without_more_taps_or_confirm():
    op,before,after,actions,_=purchase(77)
    original=op.nav.wait
    seen=[]
    def wait(predicate):
        if before.snapshot.quantity==(5,20) and 'stamina_panel' in before.snapshot.flags:
            before.snapshot.quantity=(4,20)
            assert not predicate(before.snapshot)
            assert not any(isinstance(a,ConfirmTradingTrade) for a in actions)
            seen.append(4)
            before.snapshot.quantity=(5,20)
            seen.append(5)
        return original(predicate)
    op.nav.wait=wait
    assert op.ensure(before) is after
    assert seen==[4,5]
    assert sum(isinstance(a,StageAction) and a.control==C.STAMINA_INCREMENT for a in actions)==4
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==1
