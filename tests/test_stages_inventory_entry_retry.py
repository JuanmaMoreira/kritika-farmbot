"""e81b3bb2: verify Inventory before Sell, retry only from post-input Lobby."""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, SCREEN_LOBBY
from bot.equipment_relief import EquipmentReliefResult, EquipmentReliefOutcome
from bot.runtime_observer import RuntimeWaitTimeout, RuntimeWaitCancelled
from bot.stages_actions import StageAction, StageControl
from bot.stages_reliefs import StagesReliefs
from bot.stages_runtime import StagesNavigation
from bot.state import ResolutionStatus
from tests.test_mailbox_flow import snapshot


def setup(*, bad=None, second_failure=False, late=False, cancel=False):
    initial=snapshot(12,1.,base=SCREEN_LOBBY)
    retained=snapshot(40,7.8,base=SCREEN_LOBBY)
    if bad in ('unknown','ambiguous'):
        retained=replace(retained,state=replace(retained.state,base_context=None,
            status=ResolutionStatus.UNKNOWN if bad=='unknown' else ResolutionStatus.AMBIGUOUS,
            base_candidates=() if bad=='unknown' else (SCREEN_LOBBY,'screen.stages')))
    if bad=='foreign':retained=snapshot(40,7.8,base='screen.stages')
    if bad=='overlay':retained=replace(retained,state=replace(retained.state,overlays=('popup.foreign',)))
    if bad in ('stale','future','pre_input','old_sequence'):
        retained=snapshot(12 if bad=='old_sequence' else 40,
            {'stale':5.,'future':9.,'pre_input':1.1,'old_sequence':7.8}[bad],base=SCREEN_LOBBY)
    fresh=snapshot(41,8.2,base=None if late else SCREEN_LOBBY)
    entered=snapshot(42,8.6,base=None)
    timeout=RuntimeWaitTimeout(after_sequence=12,timeout=6.,last_snapshot=retained)
    waits=[(initial,1.1),(timeout,8.),(fresh,8.3),(entered,8.7)]
    if bad=='missing':timeout.last_snapshot=None
    if second_failure:
        waits[-1]=(RuntimeWaitTimeout(after_sequence=41,timeout=6.,
                     last_snapshot=snapshot(43,14.,base=SCREEN_LOBBY)),14.1)
    clock=NS(now=0.,cancelled=False)
    class Observer:
        def wait_until(self,predicate,*,after_sequence,cancel_requested=None,**kwargs):
            value,clock.now=waits.pop(0)
            if isinstance(value,Exception):raise value
            assert value.sequence>after_sequence and predicate(value)
            if cancel and value is fresh:clock.cancelled=True
            return value
    actions=[]
    executor=NS(execute=lambda action,*a,**kw:actions.append(action))
    nav=StagesNavigation(Observer(),executor,clock=lambda:clock.now,
                         cancel_requested=lambda:clock.cancelled)
    nav.exit_to_lobby=lambda:None
    readable={41 if late else 42}
    reader=NS(inventory_sample=lambda image,*,sequence,observed_at:
              NS() if sequence in readable else None)
    owner=NS(reader=reader,_after_sequence=0,_not_before=0.)
    sells=[]
    def run(request):
        request.sell_plan.enter_inventory(None)
        sells.append('sell')
        return EquipmentReliefResult(EquipmentReliefOutcome.CALLER_RESULT,'caller.result_after_sell',
                                     caller_result=entered)
    relief=StagesReliefs(nav,NS(),NS(run=run,sell_runtime=owner))
    return relief,actions,sells,owner


def execute(relief):
    return relief(StageControl.START,NS(state=NS(overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,))),{'start'})


@pytest.mark.parametrize('second_failure',[False,True])
def test_lost_inventory_tap_retries_once_before_sell(second_failure):
    relief,actions,sells,owner=setup(second_failure=second_failure)
    if second_failure:
        with pytest.raises(RuntimeWaitTimeout):execute(relief)
    else:
        assert execute(relief).sequence==42
    assert actions==[StageAction(StageControl.LOBBY_INVENTORY)]*2
    assert sells==([] if second_failure else ['sell'])
    assert owner._after_sequence==41 and owner._not_before==8.3


def test_inventory_appearing_late_continues_without_second_tap():
    relief,actions,sells,owner=setup(late=True)
    execute(relief)
    assert actions==[StageAction(StageControl.LOBBY_INVENTORY)]
    assert sells==['sell'] and owner._after_sequence==12


@pytest.mark.parametrize('bad',['unknown','ambiguous','foreign','overlay','stale','future',
                                'pre_input','old_sequence','missing'])
def test_unreadable_inventory_does_not_authorize_retry_without_fresh_lobby(bad):
    relief,actions,sells,_=setup(bad=bad)
    with pytest.raises(RuntimeWaitTimeout):execute(relief)
    assert actions==[StageAction(StageControl.LOBBY_INVENTORY)] and not sells


def test_cancel_before_second_tap_stops_without_sell():
    relief,actions,sells,_=setup(cancel=True)
    with pytest.raises(RuntimeWaitCancelled):execute(relief)
    assert actions==[StageAction(StageControl.LOBBY_INVENTORY)] and not sells
