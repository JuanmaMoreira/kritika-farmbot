from types import SimpleNamespace as S
import pytest
from bot.stages_runtime import StagesNavigation
from bot.runtime_observer import RuntimeWaitTimeout,RuntimeWaitCancelled

@pytest.mark.parametrize('fresh_matches',[True,False])
def test_stale_matching_surface_reacquires_native_without_input(fresh_matches):
    now=[11.];stale=S(sequence=8,timestamp=10.2,layer='config')
    fresh=S(sequence=20,timestamp=13.9,layer='config' if fresh_matches else 'foreign')
    calls=[]
    class Source:
        def get_frame(self):return stale
        def refresh_native(self):calls.append('native')
    class Observer:
        source=Source()
        def wait_until(self,predicate,**kwargs):
            calls.append(('wait',kwargs['after_sequence'],kwargs['timeout']))
            if len(calls)==1:
                now[0]=14.;assert not predicate(stale)
                raise RuntimeWaitTimeout(after_sequence=7,timeout=6.,last_snapshot=stale)
            if not predicate(fresh):
                raise RuntimeWaitTimeout(after_sequence=8,timeout=2.,last_snapshot=fresh)
            return fresh
    actions=S(execute=lambda *a,**k:pytest.fail('observation recovery must not emit input'))
    nav=StagesNavigation(Observer(),actions,clock=lambda:now[0]);nav.cursor=7;nav.dispatched_at=10.
    if fresh_matches:
        assert nav.wait(lambda s:s.layer=='config') is fresh
        assert nav.cursor==20
    else:
        with pytest.raises(RuntimeWaitTimeout):nav.wait(lambda s:s.layer=='config')
    assert calls==[('wait',7,6.),'native',('wait',8,2.)]

def test_fresh_wrong_surface_timeout_remains_failure_without_native_retry():
    item=S(sequence=8,timestamp=10.5,layer='foreign')
    class Source:
        def get_frame(self):return item
        def refresh_native(self):pytest.fail('fresh mismatch must stay failed')
    class Observer:
        source=Source()
        def wait_until(self,predicate,**kwargs):
            raise RuntimeWaitTimeout(after_sequence=7,timeout=6.,last_snapshot=item)
    nav=StagesNavigation(Observer(),None,clock=lambda:11.);nav.cursor=7
    with pytest.raises(RuntimeWaitTimeout):nav.wait(lambda s:s.layer=='config')

def test_cancelled_wait_does_not_reacquire_or_emit_input():
    class Observer:
        def wait_until(self,*a,**k):raise RuntimeWaitCancelled('cancel')
    nav=StagesNavigation(Observer(),None,clock=lambda:11.)
    with pytest.raises(RuntimeWaitCancelled):nav.wait(lambda s:True)
