"""Compact, held-out live strips: identity, geometry and feedback replay."""
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from bot.trading_list_anchors import TradingListAnchors, ORDERED_MATERIAL_SUFFIX
from bot.trading_materials_productive import ProductiveMaterialsAdapter, TARGET, TARGETED_PROFILE, MAX_ROBUST_FORWARD_SWIPE
from bot.directed_list_scroll import navigate_to_target, ViewportReading, DirectedScrollOutcome

ROOT=Path(__file__).resolve().parents[1]
RECORDS=json.loads((ROOT/'datasets/ordered_navigation_replay.json').read_text())


def restore(record):
    h,w=record['shape'];x,y,x2,y2=record['rect']
    crop=cv2.imread(str(ROOT/record['path']))
    frame=np.zeros((h,w,3),np.uint8)
    frame[y:y2,x:x2]=crop
    return frame


@pytest.mark.parametrize('record',RECORDS,ids=lambda r:r['id'])
def test_live_anchor_identity_and_position(record):
    actual=TradingListAnchors().read(restore(record))
    assert [name for name,_ in actual]==[name for name,_ in record['expected']]
    assert [y for _,y in actual]==pytest.approx([y for _,y in record['expected']],abs=.002)


def test_live_feedback_replay_reaches_strong_material_target_with_one_residual():
    by_id={r['id']:r for r in RECORDS}
    names=['acquired_anchor','after_large','before_residual','target','target']
    anchors=TradingListAnchors()
    adapter=ProductiveMaterialsAdapter(None,None,None,None)
    readings=[]
    for seq,name in enumerate(names,1):
        frame=restore(by_id[name]);geometry=adapter.target_geometry(frame)
        pairs=anchors.read(frame) if geometry is None else ((TARGET,geometry[1]),)
        readings.append(ViewportReading(tuple(n for n,_ in pairs),seq,
            row_centers=tuple(y for _,y in pairs),target_row_y=geometry[1] if geometry else None))
    samples=iter(readings);emits=[];motions=[]
    result=navigate_to_target(catalog=ORDERED_MATERIAL_SUFFIX,target=TARGET,
        profile=TARGETED_PROFILE,observe=lambda:next(samples),emit=emits.append,
        max_gestures=3,telemetry=lambda **fields:motions.append(fields))
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert result.gesture_count==3 and result.corrections==1 and result.observations==5
    assert len([m for m in motions if m['phase']=='motion'])==3
    assert emits[-1].delta<emits[0].delta


def test_compressed_target_phase_uses_strong_title_geometry_and_preserves_c3():
    record=next(r for r in RECORDS if r['id']=='v2_phase_confirmation')
    frame=restore(record)
    from bot.trading_row_facts import TradingRowReader
    from bot.ocr import RapidOcrEngine
    adapter=ProductiveMaterialsAdapter(None,None,TradingRowReader(RapidOcrEngine()),None)
    geometry=adapter.target_geometry(frame)
    assert geometry is not None and geometry[1]==pytest.approx(.65,abs=.003)
    assert adapter.reader.read_pair(frame,geometry[0])==(366,40)


def test_final_coarse_and_single_directed_feedback_replay():
    by_id={r['id']:r for r in RECORDS}
    names=('v2_initial','v2_coarse_anchor','v2_target_first','v2_target_confirm')
    adapter=ProductiveMaterialsAdapter(None,None,None,None)
    samples=[]
    for sequence,name in enumerate(names,1):
        frame=restore(by_id[name]);geometry=adapter.target_geometry(frame)
        pairs=adapter.anchors.read(frame) if geometry is None else ((TARGET,geometry[1]),)
        samples.append(ViewportReading(tuple(n for n,_ in pairs),sequence,
            row_centers=tuple(y for _,y in pairs),target_row_y=geometry[1] if geometry else None))
    readings=iter(samples);emits=[];events=[]
    result=navigate_to_target(catalog=ORDERED_MATERIAL_SUFFIX,target=TARGET,
        profile=TARGETED_PROFILE,coarse=MAX_ROBUST_FORWARD_SWIPE,
        observe=lambda:next(readings),emit=emits.append,max_gestures=4,
        telemetry=lambda **event:events.append(event))
    assert result.outcome is DirectedScrollOutcome.TARGET_READY and result.gesture_count==2
    assert result.corrections==result.direction_reversals==0 and result.observations==4
    assert emits[0]==MAX_ROBUST_FORWARD_SWIPE
    plan=next(e for e in events if e['phase']=='plan')
    assert plan['target_expected_y']==pytest.approx(.65,abs=.007)
    assert result.stable_row_y==pytest.approx(.65,abs=.10)
