from types import SimpleNamespace as S
import numpy as np
import pytest
from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import Observation,ObservationBatch,ObservationSource
from bot.runtime_observer import RuntimeSnapshot,RuntimeFacts,RuntimeWaitCancelled
from bot.state import ResolvedState,ResolutionStatus
from bot.stages_runtime import StagesNavigation
from bot.stages_actions import StageControl as C
from bot.perception.stages import StagesDetector,StagesClaimDetector


def snap(sequence,kind):
 image=np.zeros((100,200,3),np.uint8);timestamp=10.+sequence*.16
 obs=[Observation('stages.surface',1.,ObservationSource.LOCAL_CV,value='normal')]
 if kind in {'active','gray'}:obs.append(Observation('stages.claim_'+('active' if kind=='active' else 'inactive'),1.,ObservationSource.LOCAL_CV))
 overlays=('popup.foreign',) if kind=='modal' else ()
 base='screen.stages' if kind!='foreign' else 'screen.other'
 status=ResolutionStatus.UNKNOWN if kind=='unknown' else ResolutionStatus.RESOLVED
 if kind=='unknown':base=None;obs=[]
 return RuntimeSnapshot(FrameSnapshot(image,timestamp,sequence),ObservationBatch(sequence,timestamp,tuple(obs)),
  ResolvedState(status,sequence,timestamp,base_context=base,overlays=overlays),RuntimeFacts(),FrameGeometry.from_frame(image))


def run(kinds,cancel=lambda:False):
 values=iter(snap(i+2,k) for i,k in enumerate(kinds));initial=snap(1,'active');now=[10.17];calls=[];cycles=[]
 class Nav(StagesNavigation):
  def wait(self,predicate,**kw):
   item=next(values);now[0]=item.timestamp+.01;cycles.append(item);assert predicate(item);return item
  def tap(self,control,item):assert control==C.CLAIM;calls.append(item.sequence)
 n=Nav(None,None,clock=lambda:now[0],sleeper=lambda dt:now.__setitem__(0,now[0]+dt),cancel_requested=cancel)
 return n,initial,calls,cycles


def test_zero_claims_does_no_extra_work():
 n,_,calls,cycles=run([]);gray=snap(1,'gray')
 assert n.claim_rewards(gray) is gray and not calls and not cycles

@pytest.mark.parametrize('count',[1,3,7])
def test_claims_use_fresh_minimal_cycles_until_gray(count):
 n,s,calls,cycles=run(['active']*(count-1)+['gray'])
 assert n.claim_rewards(s).sequence==count+1
 assert len(calls)==len(cycles)==count


def test_extra_tap_during_inactive_transition_is_harmless():
 # UI may still show active for one fresh frame after the last reward.
 n,s,calls,cycles=run(['active','gray']);n.claim_rewards(s)
 assert len(calls)==2 and len(cycles)==2


def test_stuck_signal_hits_tap_bound():
 n,s,calls,_=run(['active']*20)
 with pytest.raises(ValueError,match='max_taps'):n.claim_rewards(s)
 assert len(calls)==20

@pytest.mark.parametrize('kind',['modal','foreign','unknown'])
def test_context_change_or_unknown_stops_claim_inputs(kind):
 n,s,calls,_=run([kind])
 with pytest.raises(ValueError,match='incompatible_state'):n.claim_rewards(s)
 assert len(calls)==1


def test_cancel_stops_before_claim_input():
 n,s,calls,_=run([],cancel=lambda:True)
 with pytest.raises(RuntimeWaitCancelled):n.claim_rewards(s)
 assert not calls


def test_claim_scope_omits_episode_and_stage8_checks_but_keeps_upper_layers():
 d=StagesDetector();calls=[]
 def present(frame,name):calls.append(name);return name=='normal'
 d.present=present
 list(StagesClaimDetector(d).detect(np.zeros((100,200,3),np.uint8)))
 assert 'normal' in calls and 'world_map' in calls and 'config' in calls
 assert 'abyssal' not in calls and 'stage8' not in calls


def test_stamina_setup_batch_no_perception_and_cancel_bound():
 calls=[];now=[10.];n=StagesNavigation(None,S(execute=lambda *a,**kw:calls.append(a)),clock=lambda:now[0],sleeper=lambda dt:now.__setitem__(0,now[0]+dt))
 s=snap(1,'active');n.stamina_increments(4,s)
 assert len(calls)==4 and all(a[0].control==C.STAMINA_INCREMENT for a in calls)
 with pytest.raises(ValueError,match='bound'):n.stamina_increments(20,s)
 n.cancel_requested=lambda:True
 with pytest.raises(RuntimeWaitCancelled):n.stamina_increments(1,s)
 assert len(calls)==4
