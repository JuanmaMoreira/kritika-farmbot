"""Replay terminal SDK pill missed by GUI session d3ba3a20; no hardware."""
import json
from pathlib import Path
from types import SimpleNamespace as S

import cv2
import numpy as np
import pytest

from bot.ads_manager import AdObservation, AdsManager, AdsOutcome
from tests.test_ads_sdk_round import observe, SDK, MAIN, PKG

FIXTURES = Path(__file__).parent/'fixtures/ads_reward_pill'
ENTRIES = json.loads((FIXTURES/'manifest.json').read_text())['entries']


def frame(entry=ENTRIES[-1]):
    image = np.zeros((*entry['shape'], 3), np.uint8)
    chrome = cv2.imread(str(FIXTURES/entry['file']))
    image[:chrome.shape[0]] = chrome
    return image


@pytest.mark.parametrize('entry', ENTRIES)
@pytest.mark.parametrize('native_scale', [False, True])
def test_retained_terminal_pill_authorizes_back(entry, native_scale):
    image = frame(entry)
    if native_scale:
        image = cv2.resize(image, (2712, 1224))
    result = observe(image)
    assert result.active and result.back_ready
    assert result.close_key == 'reward_granted_pill'
    assert result.close_point is None


@pytest.mark.parametrize('missing', ['x', 'reward'])
def test_pill_requires_both_explicit_reward_and_x(missing):
    image = frame(); h,w = image.shape[:2]
    x1,x2 = (.915,.942) if missing == 'x' else (.78,.91)
    image[round(.035*h):round(.104*h),round(x1*w):round(x2*w)] = 99
    result = observe(image)
    assert not result.back_ready and result.close_point is None


@pytest.mark.parametrize('activity,focus,package', [
    (MAIN, None, PKG), (SDK, (PKG, MAIN), PKG),
    (SDK, None, 'external.package'), ('other.AdActivity', None, PKG),
])
def test_pill_requires_concordant_google_sdk_ownership(activity, focus, package):
    result = observe(frame(), activity, focus, package)
    assert not result.back_ready and result.close_point is None


def test_next_ad_suppresses_pill_authority():
    result = observe(frame(), chrome_ocr=S(recognize=lambda image:S(text='Next ad', confidence=.99)))
    assert result.intermediate == 'next_ad'
    assert not result.back_ready and result.close_point is None


def test_slow_ocr_cannot_authorize_pill_back(monkeypatch):
    now = [100.]
    monkeypatch.setattr('bot.ads_manager.time.monotonic', lambda:now[0])
    def recognize(image):
        now[0] += 2.1
        return S(text='eward granted', confidence=.95)
    result = observe(frame(), chrome_ocr=S(recognize=recognize))
    assert not result.back_ready and result.close_point is None


def test_pill_at_deadline_closes_once_and_waits_for_results():
    terminal = observe(frame())
    now = [0.]; backs = []
    def current():
        if backs:
            return AdObservation(now[0], game_present=True, returned=True)
        return terminal if now[0] >= 60. else AdObservation(now[0], active=True)
    manager = AdsManager(current, lambda *args:pytest.fail('creative tap'),
        lambda *args:pytest.fail('ticket'), lambda snapshot:backs.append(now[0]),
        clock=lambda:now[0], sleeper=lambda delay:now.__setitem__(0, now[0]+delay))
    assert manager.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert backs == [60.]
