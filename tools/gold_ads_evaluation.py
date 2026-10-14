"""Incremental replay of the affected Android SDK terminal authority."""
from dataclasses import asdict
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace as S
import time
import cv2
import numpy as np
from bot.ads_manager import AndroidAdsObserver, read_sdk_progress
from bot.observations import Observation, ObservationSource
from bot.perception.stages import StagesDetector
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs
from tests.test_gold_cycle_failures import card, live_card
from tests.test_ads_sdk_round import frame
from tests.test_ads_reward_pill import ENTRIES as PILL_ENTRIES, frame as pill_frame
from tests.test_ads_reward_left_pill import ENTRIES as LEFT_PILL_ENTRIES, frame as left_pill_frame

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/gold_cycle_20261009/ad_evaluator'

class ProgressReplay:
    evaluation_id='gold.google_sdk_progress'
    asset_paths=(ROOT/'bot/ads_manager.py',)
    def detect(self,image):
        progress=read_sdk_progress(image)
        return (() if progress is None else
            (Observation('ad.progress',1.,ObservationSource.LOCAL_CV,value=progress),))

class TerminalReplay:
    evaluation_id='gold.google_sdk_terminal'
    def __init__(self):
        self._detector=StagesDetector(ROOT)
        self.asset_paths=(*self._detector.asset_paths,ROOT/'bot/ads_manager.py')
    def detect(self,image):
        sdk='game/com.google.android.gms.ads.AdActivity'
        def shell(*args):return S(stdout=('topResumedActivity=ActivityRecord{a u0 ' if args[1]=='activity' else 'mCurrentFocus=Window{a u0 ')+sdk+'}')
        snap=S(timestamp=time.monotonic(),frame=S(image=image))
        result=AndroidAdsObserver(S(observe=lambda:snap),S(shell=shell),'game',self._detector,
            returned=lambda s:False,unavailable=lambda s:False,skip_ticket=lambda s:False,game_visible=lambda s:False)()
        return (Observation('ad.terminal',1.,ObservationSource.LOCAL_CV),) if result.close_point or result.back_ready else ()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    progress_cases={}
    for group in ('ads_progress','ads_progress_inset','ads_reward_pill','ads_reward_left_pill'):
        root=ROOT/'tests/fixtures'/group
        for entry in json.loads((root/'manifest.json').read_text())['entries']:
            path=root/entry['file']
            expected_hash=entry.get('fixture_sha256',entry.get('sha256'))
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:
                raise ValueError(f'fixture hash mismatch: {path}')
            if group.startswith('ads_progress'):
                image=np.zeros((*entry['shape'],3),np.uint8)
                strip=cv2.imread(str(path));image[:strip.shape[0]]=strip
                progress_cases[group+'_'+path.stem]=(image,entry.get('present',True))
    cases={name:(frame(name),name in {'legacy_terminal','natural_terminal','natural_light_terminal'})
        for name in ['legacy_terminal','natural_terminal','natural_light_terminal','multipart_early','reward_card_terminal']}
    cases['failed_card']=(card(),True)
    cases['failed_card_native_scale']=(cv2.resize(card(),(2712,1224)),True)
    cases['natural_native_card']=(live_card(),True)
    image=card();image[round(.867*image.shape[0]):]=0;cases['card_no_footer']=(image,False)
    image=card();image[:round(.12*image.shape[0])]=0;cases['card_no_x']=(image,False)
    for entry in PILL_ENTRIES:
        cases['pill_'+Path(entry['file']).stem]=(pill_frame(entry),True)
    cases['pill_native_scale']=(cv2.resize(pill_frame(),(2712,1224)),True)
    image=pill_frame();h,w=image.shape[:2]
    image[round(.035*h):round(.104*h),round(.915*w):round(.942*w)]=99
    cases['pill_no_x']=(image,False)
    image=pill_frame()
    image[round(.035*h):round(.104*h),round(.78*w):round(.91*w)]=99
    cases['pill_no_reward']=(image,False)
    for entry in LEFT_PILL_ENTRIES:
        cases['left_pill_'+Path(entry['file']).stem]=(left_pill_frame(entry),True)
    image=left_pill_frame();h,w=image.shape[:2]
    cases['left_pill_native_scale']=(cv2.resize(image,tuple(reversed(LEFT_PILL_ENTRIES[-1]['native_shape']))),True)
    image=left_pill_frame()
    image[round(.014*h):round(.107*h),round(.05*w):round(.077*w)]=255
    cases['left_pill_no_x']=(image,False)
    image=left_pill_frame()
    image[round(.014*h):round(.107*h),round(.08*w):round(.203*w)]=255
    cases['left_pill_no_reward']=(image,False)
    for name,(image,_) in cases.items():cv2.imwrite(str(OUT/(name+'.png')),image)
    results,stats=evaluate_detector_frame_pairs(ROOT,[OUT/(name+'.png') for name in cases],(TerminalReplay(),),cache_path=OUT/'cache.json')
    mismatches=[name for (name,(_,expected)),result in zip(cases.items(),results) if bool(result.observations)!=expected]
    payload={'stats':asdict(stats),'mismatches':mismatches,'cases':{name:expected for name,(_,expected) in cases.items()}}
    for name,(image,_) in progress_cases.items():cv2.imwrite(str(OUT/(name+'.png')),image)
    progress_results,progress_stats=evaluate_detector_frame_pairs(ROOT,
        [OUT/(name+'.png') for name in progress_cases],(ProgressReplay(),),cache_path=OUT/'progress_cache.json')
    progress_mismatches=[name for (name,(_,expected)),result in zip(progress_cases.items(),progress_results)
        if bool(result.observations)!=expected]
    payload['progress']={'stats':asdict(progress_stats),'mismatches':progress_mismatches,
        'cases':{name:{'expected_present':expected,
            'fraction':result.observations[0].value if result.observations else None}
            for (name,(_,expected)),result in zip(progress_cases.items(),progress_results)}}
    (OUT/'result.json').write_text(json.dumps(payload,indent=2),encoding='utf8');print(json.dumps(payload))
    return bool(mismatches or progress_mismatches)

if __name__=='__main__':raise SystemExit(main())
