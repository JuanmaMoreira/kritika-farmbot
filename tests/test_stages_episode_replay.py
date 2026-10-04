"""Exact native/stream pixels for episode identity, including global broadcast."""
from pathlib import Path
import json,time
from types import SimpleNamespace as S
import cv2,numpy as np,pytest
from bot.perception.stages import StagesDetector,has,surface
from bot.observations import ObservationBatch
from bot.stages_runtime import StagesNavigation
from bot.stages_actions import StageControl as C
from bot.state import ResolutionStatus
root=Path(__file__).parent/'fixtures/stages_episode'
manifest=json.loads((root/'manifest.json').read_text())

def frame(label):
 entry=manifest[label];f=np.zeros(entry['shape'],dtype=np.uint8);h,w=f.shape[:2]
 for region in entry['regions']:
  x1,y1,x2,y2=region['roi']
  f[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(root/region['file']))
 return f

def snap(label,sequence=1,timestamp=10.):
 f=frame(label);observations=StagesDetector().detect(f)
 return S(sequence=sequence,timestamp=timestamp,frame=S(image=f),
  observations=ObservationBatch(sequence,timestamp,observations),
  state=S(status=ResolutionStatus.RESOLVED,base_context='screen.stages',overlays=()))

@pytest.mark.parametrize('label',['latest_pre_claim','pre_server_broadcast','post_clear','pre_clear','native_clear'])
def test_real_episode_positives_same_threshold(label):
 d=StagesDetector();f=frame(label)
 assert d.score(f,'abyssal')>=.94
 assert has(snap(label),'abyssal') and surface(snap(label))=='normal'

@pytest.mark.parametrize('label',['other_episode_elite','world_map_dropdown'])
def test_real_other_episode_and_dropdown_are_negative(label):
 assert StagesDetector().score(frame(label),'abyssal',undimmed=False)<.30
 assert not has(snap(label),'abyssal')

def test_dimmed_title_does_not_authorize_skip():
 d=StagesDetector();f=(frame('post_clear')*.55).astype(np.uint8)
 assert not d.present(f,'abyssal')

@pytest.mark.parametrize('label',['latest_pre_claim','pre_server_broadcast','post_clear','native_clear'])
def test_real_initial_positive_integration_zero_world_map_and_selection(label):
 s=snap(label);calls=[];lobby=S(state=S(status=ResolutionStatus.RESOLVED,base_context='screen.lobby',overlays=()));waits=iter([lobby,s,s])
 class Nav(StagesNavigation):
  def claim_rewards(self,item):return snap('post_clear')  # Claim physical loop is covered separately.
  def wait(self,predicate,**kw):
   item=next(waits);assert predicate(item);return item
  def change(self,control,snapshot,expected,**kw):
   calls.append(control)
   assert control in {C.OPEN,C.STAGE8}
   return s
 n=Nav(None,None,clock=lambda:10.1);n.enter_target()
 assert calls==[C.OPEN,C.STAGE8]

def test_wrong_episode_normal_fixture_navigates_once_and_requires_post_verify():
 # A fixture with the real Ep.1 title pixels on Normal chrome represents
 # the mode-independent title mismatch without physically switching gameplay.
 wrong=frame('post_clear');different=frame('other_episode_elite');h,w=wrong.shape[:2]
 roi=(.435,.165,.567,.189);x1,y1,x2,y2=roi
 nh,nw=different.shape[:2]
 wrong[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.resize(
  different[round(y1*nh):round(y2*nh),round(x1*nw):round(x2*nw)],
  (round(x2*w)-round(x1*w),round(y2*h)-round(y1*h)))
 observations=StagesDetector().detect(wrong)
 s=S(sequence=1,timestamp=10.,frame=S(image=wrong),state=S(status=ResolutionStatus.RESOLVED,
  base_context='screen.stages',overlays=()),observations=ObservationBatch(1,10.,observations))
 assert surface(s)=='normal' and not has(s,'abyssal')
 post=snap('post_clear',2);calls=[];lobby=S(state=S(status=ResolutionStatus.RESOLVED,base_context='screen.lobby',overlays=()));waits=iter([lobby,s,post,post])
 class Nav(StagesNavigation):
  def claim_rewards(self,item):return snap('post_clear')  # Claim physical loop is covered separately.
  def wait(self,predicate,**kw):
   item=next(waits);assert predicate(item);return item
  def change(self,control,item,expected,**kw):
   calls.append(control)
   return snap('world_map_dropdown') if control in {C.WORLD_MAP,C.ABYSSAL_TAIL} and expected!={'normal'} else post if expected=={'normal'} else s
 n=Nav(None,None,clock=lambda:10.1);n.enter_target()
 assert calls==[C.OPEN,C.WORLD_MAP,C.ABYSSAL_TAIL,C.WORLD_MAP,C.STAGE8]

def test_stale_positive_snapshot_cannot_authorize_stage_input():
 s=snap('post_clear',timestamp=1.)
 actions=[];n=StagesNavigation(None,S(execute=lambda *a,**k:actions.append(a)),clock=lambda:10.)
 with pytest.raises(ValueError,match='stale'):n.tap(C.STAGE8,s)
 assert actions==[]


@pytest.mark.parametrize('label',['channel_chat','channel_chat_second'])
def test_existing_channel_chat_keeps_lower_episode_stripe_visible(label):
 assert StagesDetector().score(frame(label),'abyssal')>=.94
 assert has(snap(label),'abyssal')
