from pathlib import Path
import json,cv2,numpy as np
from bot.ads_manager import read_sdk_progress

def test_native_progress_and_completed_bar_absence():
    root=Path(__file__).parent/'fixtures/ads_progress'
    entries=json.loads((root/'manifest.json').read_text())['entries']
    fractions=[]
    for e in entries:
        h,w=e['shape'];frame=np.zeros((h,w,3),np.uint8)
        crop=cv2.imread(str(root/e['file']));frame[:crop.shape[0]]=crop
        fraction=read_sdk_progress(frame)
        assert (fraction is not None)==e['present'],e['file']
        if fraction is not None:fractions.append(fraction)
    assert fractions==sorted(fractions) and fractions[0]<.3 and fractions[-1]>.9

def test_fragmented_color_is_unknown_not_progress():
    frame=np.zeros((1220,2712,3),np.uint8)
    frame[:15,103:500]=(50,205,240)
    frame[:15,1000:1500]=(50,205,240)
    assert read_sdk_progress(frame) is None

def test_progress_does_not_read_uninitialized_frame():
    assert read_sdk_progress(None) is None
