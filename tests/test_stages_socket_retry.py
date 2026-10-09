"""Regression: Steam Walker required a second normal Socket relief at Start."""
from types import SimpleNamespace as S
import pytest
import bot.stages_reliefs as module
from bot.stages_actions import StageControl as C
from bot.semantic_actions import AcceptSocketInventoryFull
from bot.relief_policy import ReliefCoordinator, ReliefPolicy, SocketReliefPolicy

FULL='popup.socket_inventory_full'

def setup(monkeypatch,outcomes,repeats):
    full=S(sequence=1,state=S(overlays=(FULL,)))
    config=S(sequence=3)
    success=S(sequence=4)
    entered=[];runs=[]
    nav=S(events=None,cancel_requested=lambda:False,cursor=0,
          wait=lambda *a,**kw:config,act=lambda action,s:entered.append(action))
    relief=module.StagesReliefs(nav,S(socket_relief=S()),None)
    def run(*a,**kw):
        outcome=next(outcomes);runs.append((outcome,kw['policy']))
        return S(outcome=S(value=outcome),succeeded=True,final_snapshot=config)
    relief.dependencies.socket_relief.run=run
    relief.dependencies.reliefs=ReliefCoordinator()
    def change(*a):
        return relief(C.START,full,{'start'}) if next(repeats) else success
    nav.change=change
    monkeypatch.setattr(module,'exposed',lambda s:True)
    monkeypatch.setattr(module,'lobby',lambda s:False)
    monkeypatch.setattr(module,'surface',lambda s:'config')
    return relief,full,success,entered,runs

def test_effect_then_fresh_full_runs_normal_yes_relief_once_more(monkeypatch):
    relief,full,success,entered,runs=setup(monkeypatch,iter(['relieved','relieved']),iter([True,False]))
    assert relief(C.START,full,{'start'}) is success
    assert [r[0] for r in runs]==['relieved','relieved']
    assert runs[0][1]==SocketReliefPolicy(True,True)
    assert runs[1][1]==SocketReliefPolicy(False,True)
    assert relief.dependencies.reliefs.policy.socket==SocketReliefPolicy(True,True)
    assert len(entered)==2 and all(isinstance(a,AcceptSocketInventoryFull) for a in entered)

@pytest.mark.parametrize('outcomes,repeats,expected',[
    (['no_relief_available'],[True],1),
    (['relieved','relieved'],[True,True],2),
    (['relieved','no_relief_available'],[True,True],2),
])
def test_no_effect_or_third_full_stops_before_another_yes(monkeypatch,outcomes,repeats,expected):
    relief,full,_,entered,runs=setup(monkeypatch,iter(outcomes),iter(repeats))
    with pytest.raises(ValueError,match='bound exhausted'):relief(C.START,full,{'start'})
    assert len(runs)==expected and len(entered)==expected

def test_reset_clears_retry_authority(monkeypatch):
    relief,_,_,_,_=setup(monkeypatch,iter([]),iter([]))
    relief.used.add(FULL);relief.socket_retry_available=True;relief.socket_retried=True
    relief.reset()
    assert not relief.used and not relief.socket_retry_available and not relief.socket_retried

def test_recurring_full_never_enables_disabled_sale(monkeypatch):
    relief,full,success,_,runs=setup(monkeypatch,iter(['relieved','no_relief_available']),iter([True,False]))
    relief.dependencies.reliefs=ReliefCoordinator(ReliefPolicy(socket=SocketReliefPolicy(True,False)))
    assert relief(C.START,full,{'start'}) is success
    assert runs[1][1]==SocketReliefPolicy(False,False)
    assert relief.dependencies.reliefs.policy.socket==SocketReliefPolicy(True,False)
