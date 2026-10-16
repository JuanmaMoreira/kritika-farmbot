"""A2: acquired compact SDK reward capsule at original native resolution."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as S

import cv2
import numpy as np
import pytest

from bot.ads_manager import AdsManager, AdsOutcome, AdObservation, AndroidAdsObserver
from tests.test_ads_sdk_round import observe, SDK, MAIN, PKG

FIXTURES = Path(__file__).parent/'fixtures/ads_compact_native'
MANIFEST = json.loads((FIXTURES/'manifest.json').read_text())


def frame():
    path = FIXTURES/MANIFEST['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == MANIFEST['fixture_sha256']
    image = np.zeros(MANIFEST['shape'], np.uint8)
    x1,y1,x2,y2 = MANIFEST['bounds']
    image[y1:y2,x1:x2] = cv2.imread(str(path))
    return image


def test_native_label_and_own_x_authorize_existing_back():
    result = observe(frame())
    assert result.active and result.back_ready
    assert result.close_key == 'reward_granted_compact_pill'
    assert result.close_point is None


@pytest.mark.parametrize('kind', ['no_x','no_reward','covered_label','half_x','creative','dim'])
def test_absent_covered_or_content_controls_cannot_close(kind):
    image = frame(); h,w = image.shape[:2]
    if kind == 'dim':
        image = (image*.5).astype(np.uint8)
    elif kind == 'creative':
        x1,y1,x2,y2 = MANIFEST['bounds']
        crop = image[y1:y2,x1:x2].copy(); image[:] = 0
        image[round(.4*h):round(.4*h)+crop.shape[0],round(.4*w):round(.4*w)+crop.shape[1]] = crop
    else:
        boxes = {'no_x':(.922,.031,.949,.088), 'no_reward':(.799,.020,.920,.098),
                 'covered_label':(.810,.025,.850,.095), 'half_x':(.922,.031,.937,.088)}
        x1,y1,x2,y2 = boxes[kind]
        image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)] = 128
    result = observe(image)
    assert not result.back_ready and result.close_point is None


@pytest.mark.parametrize('activity,focus,package', [
    (MAIN,None,PKG),(SDK,(PKG,MAIN),PKG),(SDK,None,'external.package'),
    ('other.AdActivity',None,PKG),
])
def test_requires_concordant_acquired_android_ownership(activity,focus,package):
    result = observe(frame(),activity,focus,package)
    assert not result.back_ready and result.close_point is None


def test_next_ad_veto_remains_dominant():
    result = observe(frame(),chrome_ocr=S(recognize=lambda _:S(text='Next ad',confidence=.99)))
    assert result.intermediate == 'next_ad'
    assert not result.back_ready and result.close_point is None


def test_expiring_during_android_checks_cannot_authorize_back(monkeypatch):
    now = [100.]
    monkeypatch.setattr('bot.ads_manager.time.monotonic',lambda:now[0])
    def recognize(_):
        now[0] += 2.1
        return S(text='eward granted',confidence=.99)
    result = observe(frame(),chrome_ocr=S(recognize=recognize))
    assert not result.back_ready and result.close_point is None


@pytest.mark.parametrize('timestamp', [97.,101.])
def test_stale_or_future_pixels_never_authorize_back(monkeypatch,timestamp):
    monkeypatch.setattr('bot.ads_manager.time.monotonic',lambda:100.)
    snapshot = S(timestamp=timestamp,frame=S(image=frame()))
    def shell(*args):
        label = 'topResumedActivity=ActivityRecord{a u0 ' if args[1]=='activity' else 'mCurrentFocus=Window{a u0 '
        return S(stdout=label+PKG+'/'+SDK+'}')
    observer = S(observe=lambda:snapshot,source=S(refresh_native=lambda:None))
    from bot.perception.stages import StagesDetector
    result = AndroidAdsObserver(observer,S(shell=shell),PKG,StagesDetector(),
        returned=lambda _:False,unavailable=lambda _:False,skip_ticket=lambda _:False,
        game_visible=lambda _:False)()
    assert not result.back_ready and result.close_point is None


@pytest.mark.parametrize('returned', [True, False])
def test_one_close_requires_caller_return(returned):
    terminal = observe(frame()); now = [0.]; backs = []
    def current():
        return AdObservation(now[0],game_present=returned,returned=returned) if backs else terminal
    manager = AdsManager(current,lambda *a:pytest.fail('unexpected tap'),
        lambda *a:pytest.fail('unexpected ticket'),lambda _:backs.append(now[0]),
        clock=lambda:now[0],sleeper=lambda dt:now.__setitem__(0,now[0]+dt))
    result = manager.complete_requested_launch()
    assert result.outcome is (AdsOutcome.RETURNED if returned else AdsOutcome.RECOVERY_FAILED)
    assert result.close_steps == 1 and backs == [0.]


def test_existing_terminal_does_not_pay_compact_probes(monkeypatch):
    from bot.perception.stages import StagesDetector
    from tests.test_ads_right_light_native import frame as old_frame
    original = StagesDetector.present
    def guarded(self,image,name):
        assert name not in {'ad_reward_close_compact_pill','ad_reward_compact_pill_x'}
        return original(self,image,name)
    monkeypatch.setattr(StagesDetector,'present',guarded)
    assert observe(old_frame()).back_ready
