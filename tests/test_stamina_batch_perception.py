from pathlib import Path
import json
import cv2
import numpy as np
from bot.perception.stages import StagesDetector

def test_fixed_stamina_identity_excludes_output_amount_after_increment():
    root=Path(__file__).parent/'fixtures/stamina_batch'
    meta=json.loads((root/'manifest.json').read_text())
    h,w=meta['frame_shape']
    frame=np.zeros((h,w,3),dtype=np.uint8)
    x1,y1,x2,y2=[round(v*d) for v,d in zip(meta['roi'],(w,h,w,h))]
    frame[y1:y2,x1:x2]=cv2.imread(str(root/'selected_two_identity.png'))
    detector=StagesDetector()
    assert meta['selected']==2 and meta['output_stamina']==100
    assert detector.present(frame,'stamina_panel')
    assert not detector.present(frame//3,'stamina_panel')
    assert not detector.present(np.zeros_like(frame),'stamina_panel')
