"""Acquired circular Google SDK close is terminal, never arbitrary content X."""
from pathlib import Path
from types import SimpleNamespace as S
import json
import time
import cv2
import numpy as np
import pytest
from bot.ads_manager import AndroidAdsObserver, AdObservation, AdsManager, AdsOutcome
from bot.perception.stages import StagesDetector

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent/'fixtures/ads_sdk_round'
SDK = 'com.google.android.gms.ads.AdActivity'
MAIN = 'com.hive.HiveUnityPlayerActivity'
PKG = 'game.package'

def frame(name):
    entries = json.loads((FIXTURES/'manifest.json').read_text())['entries']
    entry = next(e for e in entries if e['file']==name+'.png')
    result = np.zeros((*entry['shape'],3),np.uint8)
    chrome = cv2.imread(str(FIXTURES/entry['file']))
    result[:chrome.shape[0]] = chrome
    return result

def observe(image, activity=SDK, focused=None, package=PKG, chrome_ocr=None):
    focused = (package, activity) if focused is None else focused
    snapshot = S(timestamp=time.monotonic(), frame=S(image=image))
    def shell(*args):
        value = package+'/'+activity if args[1]=='activity' else '/'.join(focused)
        label = 'topResumedActivity=ActivityRecord{a u0 ' if args[1]=='activity' else 'mCurrentFocus=Window{a u0 '
        return S(stdout=label+value+'}')
    return AndroidAdsObserver(S(observe=lambda:snapshot), S(shell=shell), PKG,
        StagesDetector(ROOT), returned=lambda s:False, unavailable=lambda s:False,
        skip_ticket=lambda s:False, game_visible=lambda s:False, chrome_ocr=chrome_ocr)()

@pytest.mark.parametrize('name',['legacy_terminal','natural_terminal','natural_light_terminal'])
def test_exact_native_circular_sdk_chrome_publishes_only_its_close(name):
    result = observe(frame(name))
    assert result.active and not result.back_ready
    assert result.close_point == (.922,.059)
    assert result.close_key == 'sdk_round_close'

@pytest.mark.parametrize('activity,focus,package', [
    (MAIN, None, PKG), (SDK, (PKG, MAIN), PKG),
    (SDK, None, 'external.package'), ('other.AdActivity', None, 'external.package'),
    ('other.AdActivity', None, PKG),
])
def test_terminal_pixels_without_concordant_acquired_sdk_ownership_publish_no_close(activity,focus,package):
    result = observe(frame('natural_terminal'), activity, focus, package)
    assert not result.back_ready and result.close_point is None

def test_circular_x_without_acquired_sdk_sound_structure_is_not_terminal():
    image = frame('natural_terminal')
    h,w = image.shape[:2]
    image[round(.04*h):round(.13*h),round(.05*w):round(.10*w)] = 0
    assert observe(image).close_point is None

def test_identical_content_x_at_center_is_not_a_sdk_terminal():
    image = frame('natural_terminal')
    h,w = image.shape[:2]
    crop = image[round(.019*h):round(.099*h),round(.905*w):round(.939*w)].copy()
    image[round(.012*h):round(.108*h),round(.902*w):round(.945*w)] = 0
    y,x = round(.45*h), round(.45*w)
    image[y:y+crop.shape[0],x:x+crop.shape[1]] = crop
    assert observe(image).close_point is None

def test_native_intermediate_part_with_progress_is_not_terminal():
    result = observe(frame('multipart_early'))
    assert result.active and result.progress is not None
    assert not result.back_ready and result.close_point is None

def test_acquired_round_close_at_five_seconds_is_dispatched_immediately():
    now = [0.]
    inputs = []
    strong = observe(frame('natural_terminal'))
    def current():
        if inputs: return AdObservation(now[0], returned=True, game_present=True)
        return strong if now[0]>=5. else AdObservation(now[0], active=True)
    def sleep(seconds): now[0] += seconds
    manager = AdsManager(current, lambda snapshot,point:inputs.append((now[0],point)),
        lambda *args:pytest.fail('ticket'), lambda *args:pytest.fail('Back'),
        clock=lambda:now[0], sleeper=sleep)
    assert manager.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert inputs == [(5.,(.922,.059))]


@pytest.fixture(scope='module')
def chrome_engine():
    from bot.ocr import RapidOcrEngine
    engine=RapidOcrEngine()
    engine.recognize(np.zeros((32,128,3),np.uint8))
    return engine


def test_real_red_sdk_reward_text_and_white_x_are_terminal(chrome_engine):
    terminal=observe(frame('reward_card_terminal'),chrome_ocr=chrome_engine)
    assert terminal.active and terminal.back_ready
    assert terminal.close_key=='reward_granted_text'
    assert terminal.close_point is None


def test_white_x_without_explicit_reward_text_is_not_terminal():
    terminal=observe(frame('reward_card_terminal'))
    assert not terminal.back_ready and terminal.close_point is None


@pytest.mark.parametrize('activity,focus',[(MAIN,None),(SDK,(PKG,MAIN)),('other.AdActivity',None)])
def test_reward_ocr_is_not_read_outside_acquired_sdk_ownership(activity,focus):
    engine=S(recognize=lambda *args:pytest.fail('OCR outside SDK chrome'))
    terminal=observe(frame('reward_card_terminal'),activity,focus,chrome_ocr=engine)
    assert not terminal.back_ready and terminal.close_point is None


@pytest.mark.parametrize('text,confidence',[('Reward pending',.99),('Reward granted',.5),('Next ad',.99)])
def test_nonterminal_or_low_confidence_label_cannot_credit_white_x(text,confidence):
    engine=S(recognize=lambda image:S(text=text,confidence=confidence))
    terminal=observe(frame('reward_card_terminal'),chrome_ocr=engine)
    assert not terminal.back_ready and terminal.close_point is None
    assert terminal.intermediate==('next_ad' if text=='Next ad' else None)


def test_next_ad_overrides_circular_close_as_intermediate():
    engine=S(recognize=lambda image:S(text='Next ad',confidence=.99))
    terminal=observe(frame('natural_terminal'),chrome_ocr=engine)
    assert terminal.intermediate=='next_ad'
    assert not terminal.back_ready and terminal.close_point is None


def test_reward_words_without_acquired_x_do_not_authorize_back():
    engine=S(recognize=lambda image:S(text='Reward granted',confidence=.99))
    terminal=observe(frame('multipart_early'),chrome_ocr=engine)
    assert not terminal.back_ready and terminal.close_point is None


def test_plain_corner_x_without_circle_is_not_terminal():
    image=frame('natural_light_terminal')
    h,w=image.shape[:2]
    # Keep the SDK X glyph and sound, but erase the circular boundary.
    roi=image[round(.012*h):round(.108*h),round(.902*w):round(.945*w)]
    roi[roi.mean(axis=2)>200]=255
    assert observe(image).close_point is None


def test_real_reward_ocr_at_five_seconds_backs_once_then_results(chrome_engine):
    strong=observe(frame('reward_card_terminal'),chrome_ocr=chrome_engine)
    now=[0.];backs=[]
    def current():
        if backs:return AdObservation(now[0],returned=True,game_present=True)
        return strong if now[0]>=5. else AdObservation(now[0],active=True)
    def sleep(seconds):now[0]+=seconds
    manager=AdsManager(current,lambda *args:pytest.fail('content tap'),lambda *args:pytest.fail('ticket'),
        lambda snapshot:backs.append(now[0]),clock=lambda:now[0],sleeper=sleep)
    assert manager.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert backs==[5.]


@pytest.mark.parametrize('name',['reward_card_terminal','natural_terminal'])
def test_slow_sdk_ocr_cannot_publish_stale_terminal_authority(monkeypatch,name):
    now=[100.]
    monkeypatch.setattr('bot.ads_manager.time.monotonic',lambda:now[0])
    def recognize(image):
        now[0]+=2.1
        return S(text='Reward granted',confidence=.99)
    terminal=observe(frame(name),chrome_ocr=S(recognize=recognize))
    assert terminal.active
    assert not terminal.back_ready and terminal.close_point is None
    assert terminal.close_key is None
