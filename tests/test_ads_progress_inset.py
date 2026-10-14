"""Live SDK viewport inset from failed multipart ad f1309e11."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.ads_manager import AdObservation, AdsManager, AdsOutcome, read_sdk_progress
from tests.test_ads_sdk_round import observe, MAIN, SDK, PKG

ROOT=Path(__file__).parent/'fixtures/ads_progress_inset'
ENTRIES=json.loads((ROOT/'manifest.json').read_text())['entries']


def frame(entry):
    result=np.zeros((*entry['shape'],3),dtype=np.uint8)
    crop=cv2.imread(str(ROOT/entry['file']))
    result[:crop.shape[0]]=crop
    return result


def test_live_inset_bar_is_moving_without_terminal_authority():
    fractions=[]
    for entry in ENTRIES:
        image=frame(entry)
        # The original reader demanded yellow at x=.038, in the black inset.
        assert not image[0,round(.038*image.shape[1])].any()
        observation=observe(image)
        assert observation.active and observation.progress is not None
        assert not observation.back_ready and observation.close_point is None
        fractions.append(observation.progress)
    assert fractions==sorted(fractions)
    assert fractions[-1]-fractions[0]>.01


@pytest.mark.parametrize('activity,focus',[(MAIN,None),(SDK,(PKG,MAIN))])
def test_inset_progress_requires_concordant_sdk_ownership(activity,focus):
    assert observe(frame(ENTRIES[-1]),activity,focus).progress is None


@pytest.mark.parametrize('shape',[(433,960),(1224,2712)])
@pytest.mark.parametrize('kind',['fragmented','outside_sdk_edge','too_short'])
def test_yellow_without_bounded_contiguous_sdk_fill_remains_unknown(shape,kind):
    h,w=shape
    image=np.zeros((h,w,3),np.uint8)
    start=.080 if kind=='outside_sdk_edge' else .052
    end=start+.002 if kind=='too_short' else .35
    image[:round(.012*h),round(start*w):round(end*w)]=(50,205,240)
    if kind=='fragmented':image[:round(.012*h),round(.5*w):round(.7*w)]=(50,205,240)
    assert read_sdk_progress(image) is None


def test_live_bar_pixels_extend_observation_without_uncredited_close():
    """Synthetic lifecycle timing, with exact relative capture gaps/pixels.

    Replay the retained motion just before the 60s fallback. No terminal was
    acquired in this failure: cancellation is the test's stopping condition,
    not an invented completion/reward for the live ad.
    """
    def run(reader):
        now=[0.]
        seen=[]
        timestamps=[58.+e['timestamp']-ENTRIES[0]['timestamp'] for e in ENTRIES]
        def current():
            eligible=[i for i,t in enumerate(timestamps) if now[0]>=t]
            progress=reader(frame(ENTRIES[eligible[-1]])) if eligible else None
            seen.append(now[0])
            return AdObservation(now[0],active=True,progress=progress)
        manager=AdsManager(current,lambda *a:pytest.fail('progress is not close authority'),
            lambda *a:pytest.fail('ticket'),lambda *a:pytest.fail('uncredited Back'),
            clock=lambda:now[0],sleeper=lambda t:now.__setitem__(0,now[0]+t),
            poll_interval=.1,cancel_requested=lambda:now[0]>=61.)
        return manager.complete_requested_launch(),seen
    # Original reader emitted None for all three retained frames.
    old,_=run(lambda image:None)
    assert old.outcome is AdsOutcome.RECOVERY_FAILED and old.elapsed_seconds<61.
    fixed,seen=run(read_sdk_progress)
    assert fixed.outcome is AdsOutcome.CANCELLED and max(seen)>60.
