"""Acquired light SDK reward pill on the left; no creative or hardware."""
import json
from pathlib import Path
from types import SimpleNamespace as S

import cv2
import numpy as np
import pytest

from bot.ads_manager import AdObservation, AdsManager, AdsOutcome
from tests.test_ads_sdk_round import observe, SDK, MAIN, PKG

FIXTURES=Path(__file__).parent/'fixtures/ads_reward_left_pill'
ENTRIES=json.loads((FIXTURES/'manifest.json').read_text())['entries']


def frame(entry=ENTRIES[-1]):
    image=np.zeros((*entry['shape'],3),np.uint8)
    chrome=cv2.imread(str(FIXTURES/entry['file']))
    image[:chrome.shape[0]]=chrome
    return image


@pytest.mark.parametrize('entry',ENTRIES)
@pytest.mark.parametrize('native_scale',[False,True])
def test_retained_left_reward_pill_authorizes_back(entry,native_scale):
    image=frame(entry)
    if native_scale:image=cv2.resize(image,tuple(reversed(entry['native_shape'])))
    result=observe(image)
    assert result.active and result.back_ready and result.close_point is None
    assert result.close_key=='reward_granted_left_pill'


@pytest.mark.parametrize('missing',['x','reward'])
def test_requires_both_explicit_reward_label_and_bound_x(missing):
    image=frame();h,w=image.shape[:2]
    x1,x2=(.05,.077) if missing=='x' else (.08,.203)
    image[round(.014*h):round(.107*h),round(x1*w):round(x2*w)]=255
    result=observe(image)
    assert not result.back_ready and result.close_point is None


def test_identical_reward_pill_in_creative_position_is_not_authority():
    image=frame();h,w=image.shape[:2]
    pill=image[:round(.13*h),:round(.22*w)].copy()
    image[:round(.13*h)]=0
    y,x=round(.4*h),round(.4*w)
    image[y:y+pill.shape[0],x:x+pill.shape[1]]=pill
    result=observe(image)
    assert not result.back_ready and result.close_point is None


@pytest.mark.parametrize('activity,focus,package',[
    (MAIN,None,PKG),(SDK,(PKG,MAIN),PKG),
    (SDK,None,'external.package'),('other.AdActivity',None,PKG),
])
def test_requires_concordant_acquired_sdk_ownership(activity,focus,package):
    result=observe(frame(),activity,focus,package)
    assert not result.back_ready and result.close_point is None


def test_next_ad_veto_preserved():
    result=observe(frame(),chrome_ocr=S(recognize=lambda image:S(text='Next ad',confidence=.99)))
    assert result.intermediate=='next_ad'
    assert not result.back_ready and result.close_point is None


def test_slow_observation_cannot_authorize_left_pill_back(monkeypatch):
    now=[100.]
    monkeypatch.setattr('bot.ads_manager.time.monotonic',lambda:now[0])
    def recognize(image):
        now[0]+=2.1
        return S(text='',confidence=0.)
    result=observe(frame(),chrome_ocr=S(recognize=recognize))
    assert not result.back_ready and result.close_point is None


def test_left_reward_pill_closes_immediately_then_waits_for_results():
    terminal=observe(frame());now=[0.];backs=[]
    def current():
        if backs:return AdObservation(now[0],game_present=True,returned=True)
        return terminal if now[0]>=5. else AdObservation(now[0],active=True)
    manager=AdsManager(current,lambda *args:pytest.fail('creative tap'),
        lambda *args:pytest.fail('ticket'),lambda snapshot:backs.append(now[0]),
        clock=lambda:now[0],sleeper=lambda dt:now.__setitem__(0,now[0]+dt))
    result=manager.complete_requested_launch()
    assert result.outcome is AdsOutcome.RETURNED and result.close_steps==1
    assert backs==[5.]
