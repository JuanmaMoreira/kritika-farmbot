from pathlib import Path
import json,cv2,numpy as np
from bot.equipment_block_scan import EquipmentBlockMatcher

fixtures=Path(__file__).parent/'fixtures/equipment_block_scan'


def test_native_glow_crops_never_merge_different_types_or_tiers():
    matcher=EquipmentBlockMatcher()
    rows=json.loads((fixtures/'manifest.json').read_text())
    samples=[(r,cv2.imread(str(fixtures/r['path']))) for r in rows]
    accepted=fallback=0
    for a,reference in samples:
        for b,candidate in samples:
            same=matcher.equivalent((reference,),candidate)
            if a['label']!=b['label']:
                assert not same,(a['path'],b['path'])
            elif a['source']==b['source'] and a['slot']!=b['slot']:
                accepted+=int(same);fallback+=int(not same)
    assert accepted>fallback  # Ambiguous glow remains an ordinary candidate.


def test_blank_or_missing_visual_evidence_is_sequential_fallback():
    matcher=EquipmentBlockMatcher()
    blank=np.zeros((100,120,3),np.uint8)
    assert not matcher.equivalent((blank,),blank)
    assert not matcher.equivalent((None,),blank)
    assert not matcher.equivalent((),None)
