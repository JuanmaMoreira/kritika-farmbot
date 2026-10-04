"""First causal divergences of the all-inventory-full Steam Walker smoke."""
import json
from pathlib import Path
from dataclasses import replace
import cv2
import numpy as np
import pytest
from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import *
from bot.observations import Observation,ObservationBatch,ObservationSource
from bot.runtime_observer import RuntimeFacts,RuntimeSnapshot
from bot.state import ResolutionStatus,ResolvedState
from bot.semantic_actions import TapEtherealResultAnimation,ConfirmCombineAll
from bot.equipment_combine_relief import (_is_random_part_panel,_is_ethereal_result_animation,
 _is_tappable_animation,EquipmentCombineRelief,EquipmentCombineStrategyOutcome)
from bot.tap_through_animation import TapThroughAnimation,TapThroughPolicy,TapThroughOutcome
from test_equipment_combine_relief import (mode,panel,snapshot,Transitions,Events,DrainObserver,DrainActions)
ROOT=Path(__file__).parent/'fixtures/combine_animation'

def replay(label):
 m=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))[label]
 w,h=m['stored_evidence_geometry'];im=np.zeros((h,w,3),np.uint8)
 x1,y1,x2,y2=m['crop_pixels'];im[y1:y2,x1:x2]=cv2.imread(str(ROOT/(label+'.png')))
 seq=m['sequence'];state=m['state'];ts=float(seq)
 obs=tuple(Observation(o['name'],o['confidence'],ObservationSource.LOCAL_CV) for o in m['observations'])
 return RuntimeSnapshot(FrameSnapshot(im,ts,seq),ObservationBatch(seq,ts,obs),
  ResolvedState(ResolutionStatus(state['status']),seq,ts,base_context=state['base_context'],overlays=tuple(state['overlays'])),
  RuntimeFacts(),FrameGeometry.from_frame(im))

def test_real_ethereal_panel_flash_is_not_a_result_phase():
 pre=replay('ethereal_pre_animation');active=replay('ethereal_animation')
 assert _is_random_part_panel(pre) and not _is_ethereal_result_animation(pre)
 assert not _is_random_part_panel(active) and _is_ethereal_result_animation(active)

def test_real_fuse_animation_arms_a_result_without_waiting_for_visual_stability():
 active=replay('fuse_animation')
 assert _is_tappable_animation(active)
 # The result veil remains sufficient if the animated emblem drops below .8.
 weak=replace(active,observations=ObservationBatch(active.sequence,active.timestamp,()))
 assert not _is_tappable_animation(weak)
 assert _is_ethereal_result_animation(weak)

@pytest.mark.parametrize('label',['transmute','fuse'])
def test_confirm_once_then_multiple_lateral_taps_until_menu_recovers(label):
 active_mode=MODE_COMBINE_FUSE if label=='fuse' else MODE_COMBINE_TRANSMUTE
 status=STATUS_COMBINE_FUSE_AVAILABLE if label=='fuse' else STATUS_COMBINE_TRANSMUTE_AVAILABLE
 initial=mode(1,active_mode,status);popup=snapshot(2,overlays=(active_mode,status,POPUP_COMBINE_ALL))
 active=snapshot(3,overlays=(active_mode,));active.frame.image[:]=40
 still=snapshot(4,overlays=(active_mode,));still.frame.image[:]=40
 done=mode(5,active_mode)
 observer=DrainObserver([still,done]);observer.observe=lambda:initial
 actions=DrainActions();driver=Transitions([popup,active])
 primitive=TapThroughAnimation(observer,actions,clock=lambda:0.,sleeper=lambda _:None)
 op=EquipmentCombineRelief(observer,actions,Events(),verified_transition=driver,tap_through=primitive)
 result,final,taps=op._base_combine(initial,mode=active_mode,status=status,label=label,cancel_requested=lambda:False)
 assert result is EquipmentCombineStrategyOutcome.EFFECT and final is done and taps==2
 assert all(isinstance(a,TapEtherealResultAnimation) for a in actions.executed)
 assert sum(isinstance(c[1],ConfirmCombineAll) for c in driver.calls)==1
 assert driver.calls[-1][3]['stable_for']==0.
 assert not driver.calls[-1][3]['expected'](mode(10,active_mode))
 assert not driver.calls[-1][3]['expected'](popup)

@pytest.mark.parametrize('base,status,overlays',[
 ('screen.lobby',ResolutionStatus.RESOLVED,()),
 (None,ResolutionStatus.AMBIGUOUS,()),
 (SCREEN_COMBINE,ResolutionStatus.RESOLVED,(POPUP_COMBINE_ALL,)),
 (None,ResolutionStatus.UNKNOWN,(POPUP_ETHEREAL_MASS_COMBINE,))])
def test_post_confirm_phase_never_authorizes_popup_foreign_or_ambiguous(base,status,overlays):
 s=snapshot(1);s.frame.image[:]=40
 s=replace(s,state=ResolvedState(status,1,1.,base_context=base,overlays=overlays,base_candidates=(SCREEN_COMBINE,"screen.lobby") if status is ResolutionStatus.AMBIGUOUS else ()))
 assert not _is_ethereal_result_animation(s)
