from types import SimpleNamespace as S
import numpy as np
import pytest
from bot.stages_runtime import StagesNavigation
from bot.stages_actions import StageControl as C
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.state import ResolutionStatus

def snapshot(layer=None,flags=()):
    obs=[Observation('stages.'+f,1.,ObservationSource.LOCAL_CV) for f in flags]
    if layer:obs.append(Observation('stages.surface',1.,ObservationSource.LOCAL_CV,value=layer))
    return S(sequence=1,timestamp=0.,state=S(status=ResolutionStatus.RESOLVED,base_context='screen.stages' if layer else 'screen.lobby',
        overlays=('popup.stages_'+layer,) if layer else ()),
        observations=ObservationBatch(sequence=1,timestamp=0.,observations=tuple(obs)),
        frame=S(image=np.zeros((100,200,3),dtype=np.uint8)))

def run_entry(*,elite=False,confirmed=True,unknown=False,unresolved=False):
    normal=snapshot('normal',('claim_inactive','stage8')+ (('abyssal',) if confirmed else ()))
    fresh=snapshot('normal',('claim_inactive','stage8')+ (('abyssal',) if confirmed and not unknown else ()))
    verified=snapshot('normal',('claim_inactive','abyssal','stage8'))
    calls=[];waits=iter([snapshot(),fresh]+([] if confirmed and not unknown else [fresh if unresolved else verified])+[verified])
    class Nav(StagesNavigation):
        def wait(self,predicate,**kw):
            s=next(waits)
            if not predicate(s):raise TimeoutError('episode not verified')
            calls.append('fresh');return s
        def change(self,control,s,expected,**kw):
            calls.append(control)
            if control==C.OPEN:return snapshot('elite') if elite else normal
            if control==C.NORMAL:return normal
            if control==C.WORLD_MAP:return snapshot('world_map') if expected=={'world_map'} else verified
            if control==C.ABYSSAL_TAIL:return snapshot('world_map')
            if control==C.STAGE8:return snapshot('config')
            raise AssertionError(control)
    return Nav(None,None),calls

@pytest.mark.parametrize('elite',[False,True])
def test_confirmed_abyssal_skips_world_map_including_elite_to_normal(elite):
    nav,calls=run_entry(elite=elite)
    nav.enter_target()
    assert C.WORLD_MAP not in calls and C.ABYSSAL_TAIL not in calls
    assert calls[-1]==C.STAGE8
    assert (C.NORMAL in calls)==elite

def test_other_episode_selects_tail_closes_map_and_freshly_verifies():
    nav,calls=run_entry(confirmed=False)
    nav.enter_target()
    assert [c for c in calls if c!='fresh']==[C.OPEN,C.WORLD_MAP,C.ABYSSAL_TAIL,C.WORLD_MAP,C.STAGE8]

def test_unknown_fresh_identity_uses_safe_resolution_instead_of_cached_positive():
    nav,calls=run_entry(confirmed=True,unknown=True)
    nav.enter_target()
    assert C.ABYSSAL_TAIL in calls and calls[-2:]==['fresh',C.STAGE8]

def test_unknown_after_selection_fails_closed_without_stage8():
    nav,calls=run_entry(confirmed=False,unresolved=True)
    with pytest.raises(TimeoutError):nav.enter_target()
    assert C.STAGE8 not in calls and calls.count(C.WORLD_MAP)==2


def test_episode_verified_before_claim_toast_no_recheck_or_world_map():
    normal=snapshot('normal',('claim_active','abyssal','stage8'))
    toast=snapshot('normal',('claim_inactive','stage8'))
    calls=[];waits=iter([snapshot(),normal,toast])
    class Nav(StagesNavigation):
        def wait(self,predicate,**kw):
            item=next(waits);assert predicate(item);calls.append('fresh');return item
        def claim_rewards(self,item):
            assert 'episode_verified' in calls
            calls.append('claims');return toast
        def change(self,control,item,expected,**kw):
            calls.append(control);return normal if control==C.OPEN else snapshot('config')
    class Events:
        def record(self,event,**fields):
            if event=='stages.episode_check':
                assert fields['episode']=='abyssal_rion';calls.append('episode_verified')
    Nav(None,None,events=Events()).enter_target()
    assert calls.index('episode_verified')<calls.index('claims')<calls.index(C.STAGE8)
    assert calls.count('episode_verified')==1 and C.WORLD_MAP not in calls
