"""Incremental replay of the affected Android SDK terminal authority."""
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace as S
import time
import cv2
from bot.ads_manager import AndroidAdsObserver
from bot.observations import Observation, ObservationSource
from bot.perception.stages import StagesDetector
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs
from tests.test_gold_cycle_failures import card, live_card
from tests.test_ads_sdk_round import frame

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/gold_cycle_20261009/ad_evaluator'

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
    cases={name:(frame(name),name in {'legacy_terminal','natural_terminal','natural_light_terminal'})
        for name in ['legacy_terminal','natural_terminal','natural_light_terminal','multipart_early','reward_card_terminal']}
    cases['failed_card']=(card(),True)
    cases['failed_card_native_scale']=(cv2.resize(card(),(2712,1224)),True)
    cases['natural_native_card']=(live_card(),True)
    image=card();image[round(.867*image.shape[0]):]=0;cases['card_no_footer']=(image,False)
    image=card();image[:round(.12*image.shape[0])]=0;cases['card_no_x']=(image,False)
    for name,(image,_) in cases.items():cv2.imwrite(str(OUT/(name+'.png')),image)
    results,stats=evaluate_detector_frame_pairs(ROOT,[OUT/(name+'.png') for name in cases],(TerminalReplay(),),cache_path=OUT/'cache.json')
    mismatches=[name for (name,(_,expected)),result in zip(cases.items(),results) if bool(result.observations)!=expected]
    payload={'stats':asdict(stats),'mismatches':mismatches,'cases':{name:expected for name,(_,expected) in cases.items()}}
    (OUT/'result.json').write_text(json.dumps(payload,indent=2),encoding='utf8');print(json.dumps(payload))
    return bool(mismatches)

if __name__=='__main__':raise SystemExit(main())
