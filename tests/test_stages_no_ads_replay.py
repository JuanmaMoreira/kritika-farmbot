"""Acquired live upper alert must capture input, even with an exposed Auto title."""
from pathlib import Path
import json,time
from types import SimpleNamespace as S
import cv2,numpy as np,pytest
from bot.perception.stages import StagesDetector,surface
from bot.observations import ObservationBatch
from bot.ads_manager import AndroidAdsObserver,AdsOutcome
from bot.stages_wiring import is_no_ads_alert
from bot.stages_runtime import StagesNavigation
from bot.stages_actions import StageControl as C
from bot.state import ResolutionStatus
from test_stages_daily import manager
from test_stages_episode_replay import frame as episode_frame
root=Path(__file__).parent/'fixtures/stages_no_ads'
manifest=json.loads((root/'manifest.json').read_text())
def frame(label):
 entry=manifest[label];f=np.zeros(entry['shape'],dtype=np.uint8);h,w=f.shape[:2]
 for region in entry['regions']:
  x1,y1,x2,y2=region['roi']
  f[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(root/region['file']))
 return f

def snapshot(label):
 f=frame(label);obs=StagesDetector().detect(f)
 return S(timestamp=time.monotonic(),sequence=1,frame=S(image=f),geometry=None,
  observations=ObservationBatch(1,time.monotonic(),obs),
  state=S(status=ResolutionStatus.RESOLVED,base_context='screen.stages',overlays=('popup.stages_no_ads',)))

@pytest.mark.parametrize('label',['native','stream'])
def test_real_loading_select_character_is_no_ads_not_auto_or_exhaustion(label):
 d=StagesDetector();f=frame(label)
 assert d.score(f,'auto')>.99  # Red reproduction: lower title was visible.
 assert d.score(f,'no_ads')>=.94
 assert d.score(f,'daily_exhausted')<.30
 assert surface(snapshot(label))=='no_ads'
 assert is_no_ads_alert(snapshot(label),S(text=lambda *a:pytest.fail('fixed text OCR')))

@pytest.mark.parametrize('label',['native','stream'])
def test_android_and_ads_manager_preserve_real_popup_as_unavailable_no_back(label):
 s=snapshot(label);pkg='game.package';activity='com.hive.HiveUnityPlayerActivity'
 texts=iter(['topResumedActivity=ActivityRecord{a u0 '+pkg+'/'+activity+' t1}',
             'mCurrentFocus=Window{a u0 '+pkg+'/'+activity+'}'])
 o=AndroidAdsObserver(S(observe=lambda:s),S(shell=lambda *a:S(stdout=next(texts))),pkg,
  StagesDetector(),returned=lambda s:False,unavailable=lambda s:is_no_ads_alert(s,None),
  skip_ticket=lambda s:False,game_visible=lambda s:surface(s) is not None)()
 assert o.game_present and o.unavailable and not o.exhausted
 m,seen=manager([o]);assert m.complete_requested_launch().outcome is AdsOutcome.UNAVAILABLE
 assert seen==[]

@pytest.mark.parametrize('label',['native','stream'])
def test_unknown_single_ok_body_never_leaks_lower_auto_authority(label):
 f=frame(label);h,w=f.shape[:2]
 # Perturb identity only, keeping the acquired real OK and exposed Auto title.
 f[round(.39*h):round(.55*h),round(.35*w):round(.65*w)]=0
 obs=StagesDetector().detect(f);s=S(observations=ObservationBatch(1,0.,obs))
 assert surface(s)=='alert'
 assert not is_no_ads_alert(s,S(text=lambda *a:'Unknown game alert'))

@pytest.mark.parametrize('label',['latest_pre_claim','post_clear','other_episode_elite','world_map_dropdown'])
def test_real_non_alert_frames_do_not_match_unavailable_body(label):
 assert StagesDetector().score(episode_frame(label),'no_ads')<.30


def test_acknowledge_popup_then_reclassify_auto_without_closing_underlying_panel():
 s=snapshot('native');calls=[]
 # Change transition test: actual post-close Auto semantic supplied by its owner.
 from test_stages_navigation import snapshot as semantic
 auto=semantic('auto');n=StagesNavigation(None,None)
 n.tap=lambda c,s:calls.append(c)
 n.wait=lambda predicate,*args: auto if predicate(auto) else pytest.fail('wrong expected surface')
 assert n.change(C.NO_ADS_OK,s,{'auto'}) is auto
 assert calls==[C.NO_ADS_OK]
