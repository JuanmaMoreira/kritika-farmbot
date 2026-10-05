"""Native current Hell chrome and acquired same-ROI absence."""
import json
from pathlib import Path
import cv2
import numpy as np
from bot.portal_notification import PortalNotificationProbe, PortalProbeOutcome

ROOT = Path(__file__).parent/'fixtures/portal_current'

def frame(name):
    entry = json.loads((ROOT/'manifest.json').read_text())[name]
    result = np.zeros(entry['shape'], dtype=np.uint8)
    h,w = result.shape[:2]
    x1,y1,x2,y2 = entry['roi']
    result[round(y1*h):round(y2*h),round(x1*w):round(x2*w)] = cv2.imread(str(ROOT/(name+'.png')))
    return result

def test_current_hell_x_is_confirmed_without_lowering_threshold():
    probe = PortalNotificationProbe()
    assert probe.confirm_threshold == .80
    assert probe.probe(frame('hell_mw')) is PortalProbeOutcome.CONFIRMED

def test_same_roi_without_portal_remains_absent():
    assert PortalNotificationProbe().probe(frame('absent_guild')) is PortalProbeOutcome.ABSENT
