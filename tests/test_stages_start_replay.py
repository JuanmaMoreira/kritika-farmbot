"""Select Striker remains exposed beside the Hell Portal banner's close button."""
import json
from pathlib import Path
import cv2
import numpy as np
from bot.perception.stages import StagesDetector

ROOT = Path(__file__).parent / 'fixtures/stages_start'

def portal_frame():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    frame = np.zeros(manifest['shape'], dtype=np.uint8)
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = manifest['roi']
    frame[round(y1*h):round(y2*h), round(x1*w):round(x2*w)] = cv2.imread(str(ROOT/'portal_start.png'))
    return frame

def test_portal_banner_does_not_hide_select_striker_identity():
    detector = StagesDetector()
    frame = portal_frame()
    assert detector.score(frame, 'start') >= .94
    assert next(o.value for o in detector.detect(frame) if o.name == 'stages.surface') == 'start'

def test_dimmed_striker_title_cannot_authorize_auto_input():
    detector = StagesDetector()
    assert not detector.present((portal_frame() * .55).astype(np.uint8), 'start')
    assert not detector.present(np.zeros_like(portal_frame()), 'start')
