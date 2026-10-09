"""Regressions for the two October 9 local Gold failures."""
import json
from pathlib import Path
from types import SimpleNamespace as S
import cv2
import numpy as np
import pytest
from bot.runtime_observer import RuntimeWaitTimeout, RuntimeWaitCancelled
from bot.stages_runtime import StagesNavigation
from bot.stages_actions import StageControl as C
from bot.state import ResolutionStatus
from tests.test_stages_navigation import snapshot
from tests.test_ads_sdk_round import observe, frame

FIXTURE=Path(__file__).parent/'fixtures/ads_store_card'

def card():
    manifest=json.loads((FIXTURE/'manifest.json').read_text())
    h,w=manifest['shape']
    image=np.zeros((h,w,3),np.uint8)
    top=cv2.imread(str(FIXTURE/'terminal.png'));image[:top.shape[0]]=top
    x1,y1,x2,y2=manifest['footer_box']
    image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(FIXTURE/'footer.png'))
    return image

@pytest.mark.parametrize('scale',[1.,2712/960])
def test_failed_end_card_is_terminal_at_evidence_and_native_geometry(scale):
    image=card()
    if scale!=1.:image=cv2.resize(image,None,fx=scale,fy=scale)
    result=observe(image)
    assert result.close_point==(.922,.059) and not result.back_ready
    assert result.close_key=='sdk_store_card_close'

def test_store_card_plain_x_without_circle_does_not_authorize_close():
    image=card();h,w=image.shape[:2]
    roi=image[round(.026*h):round(.093*h),round(.906*w):round(.939*w)]
    roi[roi.mean(axis=2)>100]=255
    assert observe(image).close_point is None

def live_card():
    manifest=json.loads((FIXTURE/'live_manifest.json').read_text())
    h,w=manifest['shape'];image=np.zeros((h,w,3),np.uint8)
    for name,(x1,y1,x2,y2) in manifest['boxes'].items():
        image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(FIXTURE/(name+'.png')))
    return image

def test_natural_native_end_card_of_another_creative_has_same_terminal_authority():
    result=observe(live_card())
    assert result.close_key=='sdk_store_card_close' and result.close_point==(.922,.059)

@pytest.mark.parametrize('activity,focus,package',[
    ('com.hive.HiveUnityPlayerActivity',None,'game.package'),
    ('com.google.android.gms.ads.AdActivity',('game.package','com.hive.HiveUnityPlayerActivity'),'game.package'),
    ('com.google.android.gms.ads.AdActivity',None,'external.package'),
])
def test_store_card_requires_concordant_game_sdk_ownership(activity,focus,package):
    assert observe(card(),activity,focus,package).close_point is None

def test_end_card_without_footer_or_x_cannot_authorize_input():
    image=card();h,w=image.shape[:2]
    image[round(.867*h):]=0
    assert observe(image).close_point is None
    image=card();image[:round(.12*h)]=0
    assert observe(image).close_point is None

@pytest.mark.parametrize('name',['multipart_early','reward_card_terminal'])
def test_new_card_template_does_not_authorize_other_intermediate_or_uncredited_x(name):
    assert observe(frame(name)).close_point is None

@pytest.mark.parametrize('bad',['unknown','ambiguous','overlay','stale','before_input','old_sequence',None])
def test_stage_open_retry_needs_fresh_post_input_exposed_lobby(bad):
    last=snapshot();last.sequence=9;last.timestamp=9.5
    if bad=='unknown':last.state.base_context=None
    if bad=='ambiguous':last.state.status=ResolutionStatus.AMBIGUOUS
    if bad=='overlay':last.state.overlays=('popup.equipment_inventory_full',)
    if bad=='stale':last.timestamp=7.
    if bad=='before_input':last.timestamp=8.
    if bad=='old_sequence':last.sequence=4
    if bad is None:last=None
    calls=[]
    nav=StagesNavigation(None,None,clock=lambda:10.)
    nav.cursor=4;nav.dispatched_at=8.
    nav.wait=lambda *a,**k:snapshot()
    def change(*a,**k):
        calls.append(a[0]);raise RuntimeWaitTimeout(after_sequence=4,timeout=6.,last_snapshot=last)
    nav.change=change
    with pytest.raises(RuntimeWaitTimeout):nav.enter_target()
    assert calls==[C.OPEN]

@pytest.mark.parametrize('second_failure',[False,True])
def test_stage_navigation_no_effect_retries_once_and_never_repeats_consumption(second_failure):
    last=snapshot();last.sequence=9;last.timestamp=9.5
    normal=snapshot('normal',('abyssal','stage8','claim_inactive'))
    calls=[];waits=iter([snapshot(),last,normal,normal])
    nav=StagesNavigation(None,None,clock=lambda:10.)
    nav.cursor=4;nav.dispatched_at=8.
    nav.wait=lambda *a,**k:next(waits)
    def change(control,s,expected):
        calls.append(control)
        if control==C.OPEN and (calls.count(C.OPEN)==1 or second_failure):
            raise RuntimeWaitTimeout(after_sequence=4,timeout=6.,last_snapshot=last)
        return normal if control==C.OPEN else snapshot('config')
    nav.change=change
    if second_failure:
        with pytest.raises(RuntimeWaitTimeout):nav.enter_target()
        assert calls==[C.OPEN,C.OPEN]
    else:
        assert nav.enter_target().state.base_context=='screen.stages'
        assert calls==[C.OPEN,C.OPEN,C.STAGE8]

def test_stage_open_cancellation_does_not_retry():
    nav=StagesNavigation(None,None);nav.wait=lambda *a:snapshot()
    calls=[]
    def change(*a):calls.append(a[0]);raise RuntimeWaitCancelled('stop')
    nav.change=change
    with pytest.raises(RuntimeWaitCancelled):nav.enter_target()
    assert calls==[C.OPEN]
