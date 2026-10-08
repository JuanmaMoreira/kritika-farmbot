"""Fresh stream handoff and context-bound Stages profile safety."""
from types import SimpleNamespace as S

import pytest

from bot.runtime_observer import RuntimeWaitCancelled
from bot.stages_actions import StageControl as C
from bot.stages_runtime import StagesNavigation


def navigation(*,static=False,invalid_time=False,cancel=False):
    now=[10.];calls=[]
    initial=S(sequence=7,timestamp=9.9)
    delivered=S(sequence=8,timestamp=9.9 if invalid_time else 10.01)
    class Source:
        def get_frame(self):return initial if static or now[0]==10. else delivered
        def refresh_native(self):calls.append('native')
    def sleep(duration):now[0]+=duration;calls.append(('sleep',duration))
    def wait(predicate,**kwargs):
        assert predicate(S(sequence=9,timestamp=now[0]))
        assert kwargs['after_sequence']==7
        return S(sequence=9,timestamp=now[0])
    nav=StagesNavigation(S(source=Source(),wait_until=wait),None,
        clock=lambda:now[0],sleeper=sleep,cancel_requested=lambda:cancel and now[0]>10.)
    nav.cursor=7;nav.dispatched_at=9.95
    return nav,calls,now


def test_new_post_dispatch_stream_avoids_native_capture():
    nav,calls,_=navigation()
    assert nav.wait(lambda s:True).sequence==9
    assert 'native' not in calls


@pytest.mark.parametrize('options',[{'static':True},{'invalid_time':True}])
def test_missing_or_pre_input_stream_keeps_bounded_native_fallback(options):
    nav,calls,now=navigation(**options)
    nav.wait(lambda s:True)
    assert calls.count('native')==1
    assert 0<now[0]-10.<=.150001


def test_cancel_during_handoff_stops_before_native_or_wait():
    nav,calls,_=navigation(static=True,cancel=True)
    with pytest.raises(RuntimeWaitCancelled):nav.wait(lambda s:True)
    assert 'native' not in calls


@pytest.mark.parametrize('base',['screen.stages','screen.lobby',None,'screen.monster_wave'])
def test_change_profile_requires_verified_stages_parent(base):
    seen=[];panel=object()
    class Nav(StagesNavigation):
        def tap(self,*args):pass
        def wait(self,predicate,timeout,*,observer=None):
            seen.append(observer)
            return S(state=S(overlays=()))
    nav=Nav(None,None);nav.results_observer=panel
    nav.change(C.STAGE8,S(state=S(base_context=base)),{'config'})
    assert seen==[panel if base=='screen.stages' else None]


@pytest.mark.parametrize('blocker',['popup.equipment_inventory_full','popup.socket_inventory_full'])
def test_profile_preserves_original_blocker_relief_intent(blocker):
    calls=[]
    class Nav(StagesNavigation):
        def tap(self,*args):pass
        def wait(self,predicate,timeout,*,observer=None):return S(state=S(overlays=(blocker,)))
    nav=Nav(None,None);nav.results_observer=object()
    nav.relief=lambda control,snapshot,expected:calls.append((control,snapshot.state.overlays,expected)) or 'relieved'
    assert nav.change(C.START,S(state=S(base_context='screen.stages')),{'start'})=='relieved'
    assert calls==[(C.START,(blocker,),{'start'})]
