"""Post-ad freshness regression from session b2f41405, 2026-10-06."""
from types import SimpleNamespace as S
import json
from pathlib import Path

import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception import build_default_perception, select_detectors
from bot.runtime_observer import RuntimeObserver, RuntimeWaitTimeout, RuntimeWaitCancelled
from bot.stages_actions import StageControl as C
from bot.stages_runtime import StagesNavigation, lobby
from bot.stages_wiring import build_stages_daily, STAGES_RESULTS_RETURN_SCOPE


def test_productive_wiring_scopes_return_but_keeps_full_lobby_observer():
    observer = RuntimeObserver(S(get_frame=lambda: None), build_default_perception(), build_default_resolver())
    deps = S(observer=observer, actions=S(adb=None), events=None,
             cancel_requested=lambda: False, config=S(game_package='game.package'), ocr_engine=S())
    nav = build_stages_daily(deps, S(equipment_relief=None)).nav
    assert nav.results_observer.source is nav.observer.source
    assert nav.results_observer.resolver is nav.observer.resolver
    assert nav.results_observer.perception.detectors == select_detectors(
        nav.observer.perception, STAGES_RESULTS_RETURN_SCOPE).detectors
    assert len(nav.observer.perception.detectors) > len(nav.results_observer.perception.detectors)


def return_navigation(*,scoped=True,upper=None,lobby_upper=None,cancel=False):
    """Replay captured Config semantics with logged slow analysis, no hardware.

    Synthetic Results/Normal/Lobby exercise the acquired closing chain. The
    Config facts come verbatim from the failure; clocks model capture time and
    analysis separately, never relabelling an old frame at completion.
    """
    captured = json.loads((Path(__file__).parent/'fixtures/stages_results_return/config.json').read_text())
    now = [100.]
    state = ['results']
    sequence = [3036]
    actions = []
    waits = []
    cancelled = [False]
    image = np.zeros((32,64,3), dtype=np.uint8)

    class Source:
        def get_frame(self):
            sequence[0] += 1
            now[0] += .01
            return FrameSnapshot(image, now[0], sequence[0])

    class Perception:
        def __init__(self,narrow):self.narrow=narrow
        def analyze(self,frame):
            waits.append((self.narrow,state[0]))
            # Live Config analysis took 2.3553854s, longer than the 2s guard.
            now[0] += .07 if self.narrow else 2.3553854 if state[0]=='config' else .2
            if cancel and state[0]=='config':cancelled[0]=True
            if state[0]=='config':
                facts = [(o['name'],o['value']) for o in captured['observations']]
            elif state[0]=='lobby':facts = [('landmark.lobby_trading_center_label',None)]
            else:
                facts = [('stages.surface',state[0]),('stages.'+state[0],None),('stages.base',None)]
            if upper and state[0]=='config':facts.append((upper,None))
            if lobby_upper and state[0]=='lobby':facts.append((lobby_upper,None))
            return ObservationBatch(frame.sequence,frame.timestamp,tuple(
                Observation(name,1.,ObservationSource.LOCAL_CV,value=value) for name,value in facts))

    source=Source()
    broad=RuntimeObserver(source,Perception(False),build_default_resolver(),
                          clock=lambda:now[0],sleeper=lambda t:now.__setitem__(0,now[0]+t))
    narrow=broad.scoped(Perception(True))
    def execute(action,*args,**kwargs):
        actions.append(action.control)
        state[0]={C.RESULTS_OK:'config',C.CLOSE_CONFIG:'normal',C.BACK:'lobby'}[action.control]
    nav=StagesNavigation(broad,S(execute=execute),clock=lambda:now[0],
                         cancel_requested=lambda:cancelled[0])
    nav.cursor=3034
    nav.results_observer=narrow if scoped else None
    return nav,actions,waits


def test_logged_config_latency_old_timeout_fixed_one_ack_and_full_lobby():
    old,actions,_=return_navigation(scoped=False)
    with pytest.raises(RuntimeWaitTimeout):old.acknowledge_results()
    assert actions==[C.RESULTS_OK]
    nav,actions,waits=return_navigation()
    assert lobby(nav.acknowledge_results())
    assert actions==[C.RESULTS_OK,C.CLOSE_CONFIG,C.BACK]
    # No redundant broad Config reacquisition after the verified OK effect.
    assert waits==[(True,'results'),(True,'config'),(True,'normal'),(False,'lobby')]


@pytest.mark.parametrize('upper',[
    'landmark.quick_menu_lobby_tile',
    'landmark.equipment_inventory_full_prompt',
    'landmark.socket_inventory_full_prompt',
    'stages.no_ads','stages.alert','stages.auto',
])
def test_covered_config_never_authorizes_close_or_back(upper):
    nav,actions,_=return_navigation(upper=upper)
    with pytest.raises(RuntimeWaitTimeout):nav.acknowledge_results()
    assert actions==[C.RESULTS_OK]


def test_cancel_during_config_observation_stops_before_close():
    nav,actions,_=return_navigation(cancel=True)
    with pytest.raises(RuntimeWaitCancelled):nav.acknowledge_results()
    assert actions==[C.RESULTS_OK]


def test_terminal_lobby_still_requires_full_clean_completion():
    nav,actions,_=return_navigation(lobby_upper='landmark.mailbox_title')
    with pytest.raises(RuntimeWaitTimeout):nav.acknowledge_results()
    assert actions==[C.RESULTS_OK,C.CLOSE_CONFIG,C.BACK]


def test_scoped_snapshot_still_cannot_authorize_stale_input():
    nav,actions,_=return_navigation()
    stale=S(timestamp=nav.clock()-2.01)
    with pytest.raises(ValueError,match='stale'):nav.act(S(),stale)
    assert actions==[]
