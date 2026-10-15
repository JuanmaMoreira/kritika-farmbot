"""A2: exact native-resolution SDK pixels; Android ownership is modeled."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as S

import cv2
import numpy as np
import pytest

from bot.ads_manager import AdsManager, AdsOutcome, AdObservation, AndroidAdsObserver
from tests.test_ads_sdk_round import observe, SDK, MAIN, PKG


FIXTURES = Path(__file__).parent/'fixtures/ads_right_light_native'
MANIFEST = json.loads((FIXTURES/'manifest.json').read_text())


def frame():
    path = FIXTURES/MANIFEST['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == MANIFEST['fixture_sha256']
    image = np.zeros(MANIFEST['shape'], np.uint8)
    x1,y1,x2,y2 = MANIFEST['bounds']
    image[y1:y2,x1:x2] = cv2.imread(str(path))  # Exact pixels, no resize.
    return image


def negative(kind):
    image = frame();h,w = image.shape[:2]
    if kind == 'creative':
        x1,y1,x2,y2 = MANIFEST['bounds']
        crop = image[y1:y2,x1:x2].copy();image[:] = 0
        image[round(.4*h):round(.4*h)+crop.shape[0],round(.4*w):round(.4*w)+crop.shape[1]] = crop
    elif kind == 'dim':
        image = (image*.5).astype(np.uint8)
    else:
        boxes = {'no_x':(.898,.06,.921,.115), 'no_reward':(.778,.065,.895,.11),
                 'half_x_covered':(.898,.06,.909,.115),
                 'label_covered':(.785,.065,.82,.11)}
        x1,y1,x2,y2 = boxes[kind]
        image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)] = 128
    return image


def test_original_resolution_terminal_authorizes_existing_back_without_ocr_or_tap():
    result = observe(frame())
    assert result.active and result.back_ready
    assert result.close_key == 'reward_granted_right_light_pill'
    assert result.close_point is None


@pytest.mark.parametrize('variant', ['gray_pill','round_x'])
def test_existing_terminal_paths_skip_the_new_templates(monkeypatch,variant):
    from bot.perception.stages import StagesDetector
    from tests.test_ads_reward_pill import frame as old_pill
    from tests.test_ads_sdk_round import frame as sdk_frame
    present = StagesDetector.present
    def guarded(self,image,name):
        assert name not in {'ad_reward_close_right_light_pill','ad_reward_right_light_pill_x'}
        return present(self,image,name)
    monkeypatch.setattr(StagesDetector,'present',guarded)
    result = observe(old_pill() if variant == 'gray_pill' else sdk_frame('natural_terminal'))
    assert result.back_ready or result.close_point is not None


@pytest.mark.parametrize('kind', ['no_x','no_reward','half_x_covered','label_covered','creative','dim'])
def test_missing_covered_or_content_controls_never_authorize_close(kind):
    result = observe(negative(kind))
    assert not result.back_ready and result.close_point is None


@pytest.mark.parametrize('activity,focus,package', [
    (MAIN,None,PKG),(SDK,(PKG,MAIN),PKG),(SDK,None,'external.package'),
    ('other.AdActivity',None,PKG),
])
def test_native_terminal_requires_concordant_acquired_android_ownership(activity,focus,package):
    result = observe(frame(),activity,focus,package)
    assert not result.back_ready and result.close_point is None


def test_next_ad_veto_remains_dominant():
    result = observe(frame(),chrome_ocr=S(recognize=lambda _:S(text='Next ad',confidence=.99)))
    assert result.intermediate == 'next_ad'
    assert not result.back_ready and result.close_point is None


def test_observation_expiring_during_android_checks_cannot_authorize_back(monkeypatch):
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
def test_terminal_closes_immediately_once_and_requires_caller_return(returned):
    terminal = observe(frame()); now = [0.]; backs = []
    def current():
        return AdObservation(now[0],game_present=returned,returned=returned) if backs else terminal
    manager = AdsManager(current,lambda *a:pytest.fail('unexpected tap'),
        lambda *a:pytest.fail('unexpected ticket'),lambda _:backs.append(now[0]),
        clock=lambda:now[0],sleeper=lambda dt:now.__setitem__(0,now[0]+dt))
    result = manager.complete_requested_launch()
    assert result.outcome is (AdsOutcome.RETURNED if returned else AdsOutcome.RECOVERY_FAILED)
    assert result.close_steps == 1 and backs == [0.]
    if returned: assert result.elapsed_seconds == manager.poll_interval
