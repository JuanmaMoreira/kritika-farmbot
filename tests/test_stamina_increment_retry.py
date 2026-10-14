"""Quantity feedback handles a lost > without repeating the payment."""
from copy import deepcopy
from types import SimpleNamespace as S

import pytest

from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import ConfirmTradingTrade
from bot.stages_actions import StageAction, StageControl as C
from bot.stages_runtime import StagesNavigation
from bot.state import ResolutionStatus
from tests.test_stamina_batch import purchase


def selection(batches, *, have=41, cancelled=lambda:False):
    op,before,after,actions,_=purchase(have)
    now=[10.];sequence=[1];script=iter(batches)
    current=before.snapshot
    current.timestamp=10.
    current.flags={'stamina_panel','kcoin'}
    current.state.base_context='screen.trading'
    current.geometry=S()

    def wait_until(predicate,**kwargs):
        last=None
        for change in next(script):
            now[0]+=.5;sequence[0]+=1
            last=deepcopy(current)
            last.sequence=sequence[0];last.timestamp=now[0]-.01
            if isinstance(change,int):last.quantity=(change,20)
            else:
                for key,value in change.items():
                    if key in ('status','base_context','overlays'):setattr(last.state,key,value)
                    else:setattr(last,key,value)
            if predicate(last):return last
        raise RuntimeWaitTimeout(after_sequence=kwargs['after_sequence'],
            timeout=kwargs['timeout'],last_snapshot=last)

    def execute(action,geometry,**kwargs):
        actions.append(action);now[0]+=.01
    nav=StagesNavigation(S(wait_until=wait_until),S(execute=execute),
        clock=lambda:now[0],sleeper=lambda dt:now.__setitem__(0,now[0]+dt),
        cancel_requested=cancelled)
    op.nav=nav
    return op,current,actions


def increments(actions):
    return sum(isinstance(a,StageAction) and a.control is C.STAMINA_INCREMENT for a in actions)


def test_individual_increments_preserve_total_acquired_quantity_bound():
    op,current,actions=selection([])
    with pytest.raises(ValueError,match='tap bound'):
        op._select_quantity(current,21,30)
    assert not actions


def test_lost_fifth_increment_reaches_six_before_single_confirmation():
    op,before,after,actions,_=purchase(41)
    select,current,inputs=selection([[2],[3],[4],[5],[5],[5],[6]])
    op._select_quantity=lambda s,trades,cap:select._select_quantity(current,trades,cap)
    assert op.ensure(before) is after
    assert increments(inputs)==6
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==1


def test_late_increment_after_timeout_does_not_retry():
    op,current,actions=selection([[1],[2]])
    assert op._select_quantity(current,2,20).quantity==(2,20)
    assert increments(actions)==1


def test_second_lost_tap_stops_without_another_retry():
    op,current,actions=selection([[1],[1],[1]])
    with pytest.raises(ValueError,match='quantity mismatch'):
        op._select_quantity(current,2,20)
    assert increments(actions)==2


def test_retry_budget_is_one_for_the_entire_purchase():
    op,current,actions=selection([[1],[1],[2],[2]])
    with pytest.raises(ValueError,match='quantity mismatch'):
        op._select_quantity(current,3,20)
    assert increments(actions)==3


@pytest.mark.parametrize('bad',[
    {'status':ResolutionStatus.UNKNOWN}, {'status':ResolutionStatus.AMBIGUOUS},
    {'base_context':'screen.craft'}, {'overlays':('popup.foreign',)},
    {'flags':{'kcoin'}}, {'quantity':(1,19)}, {'quantity':(3,20)},
    {'sequence':1}, {'timestamp':10.}, {'timestamp':7.}, {'timestamp':20.},
])
def test_retry_requires_same_fresh_post_input_panel_and_quantity(bad):
    op,current,actions=selection([[bad]])
    with pytest.raises(ValueError,match='quantity mismatch'):
        op._select_quantity(current,2,20)
    assert increments(actions)==1


def test_unreadable_quantity_never_retries():
    op,current,actions=selection([[1]])
    pair=op.balances.pair
    def unreadable(s,roi):
        if s.sequence>1:raise ValueError('OCR inconclusive')
        return pair(s,roi)
    op.balances.pair=unreadable
    with pytest.raises(ValueError,match='quantity mismatch'):
        op._select_quantity(current,2,20)
    assert increments(actions)==1


def test_unknown_recheck_never_authorizes_retry():
    op,current,actions=selection([[1],[{'status':ResolutionStatus.UNKNOWN}]])
    with pytest.raises(RuntimeWaitTimeout):op._select_quantity(current,2,20)
    assert increments(actions)==1


def test_cancel_before_retry_emits_no_extra_tap():
    checks=[0]
    def cancel():
        checks[0]+=1
        return checks[0]>=3
    op,current,actions=selection([[1]],cancelled=cancel)
    with pytest.raises(RuntimeWaitCancelled):op._select_quantity(current,2,20)
    assert increments(actions)==1
