"""46/40 white effect: red icon art cannot choose the numeral filter."""
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.ocr import OcrResult, RapidOcrEngine
from bot.trading_row_facts import TradingRowReader, MATERIALS_SECTION, consensus_row_samples

FIXTURES=Path(__file__).parent/'fixtures/materials_white_effect'
MANIFEST=json.loads((FIXTURES/'manifest.json').read_text())
ENTRIES=MANIFEST['entries']


def frame(entry):
    image=np.zeros((*entry['shape'],3),np.uint8)
    x,y,xx,yy=entry['rect']
    data=(FIXTURES/entry['file']).read_bytes()
    assert sha256(data).hexdigest()==entry['sha256']
    image[y:yy,x:xx]=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    return image


@pytest.fixture(scope='module')
def engine():return RapidOcrEngine()


@pytest.mark.parametrize('entry',ENTRIES)
def test_retained_white_effect_has_two_agreeing_reads(engine,entry):
    diagnostic={}
    assert TradingRowReader(engine).read_pair(frame(entry),entry['row_top'],diagnostics=diagnostic)==(46,40)
    assert [r['parse_result'] for r in diagnostic['pair_reads']]==[(46,40),(46,40)]


def test_white_effect_forms_fresh_material_consensus(engine):
    reader=TradingRowReader(engine)
    samples=[reader.read_sample(frame(entry),i+1,item_id='hero_weapon_crafting_material',
        section=MATERIALS_SECTION,row_top=entry['row_top'],row_y=entry['row_y']) for i,entry in enumerate(ENTRIES)]
    assert all(samples)
    fact=consensus_row_samples(samples)
    assert fact is not None and (fact.have,fact.need)==(46,40)


@pytest.mark.parametrize('native_scale',[False,True])
def test_recorded_roi_color_decision_is_shared_by_both_reads(engine,monkeypatch,native_scale):
    """Retained pixels with the actual native crop coordinates, not native pixels."""
    image=frame(ENTRIES[-1])
    if native_scale:image=cv2.resize(image,(2712,1224))
    tight=tuple(MANIFEST['recorded_reads'][0]['roi'])
    wide=tuple(MANIFEST['recorded_reads'][1]['roi'])
    monkeypatch.setattr('bot.trading_row_facts._localize_pair',lambda *args:tight)
    reader=TradingRowReader(engine)
    # This is the regression: the icon's red entered only the wide crop.
    assert reader._parse_box(image,wide,red_pair=True) is None
    assert reader.read_pair(image,ENTRIES[-1]['row_top'])==(46,40)


def test_wide_red_icon_does_not_convert_white_ocr_to_grayscale():
    seen=[]
    engine=Mock(recognize=lambda image:(seen.append(image.copy()) or OcrResult('46/40',.99)))
    entry=ENTRIES[-1]
    assert TradingRowReader(engine).read_pair(frame(entry),entry['row_top'])==(46,40)
    assert len(seen)==2 and all(image.ndim==3 for image in seen)


def test_exact_logged_disagreement_stays_unreadable():
    engine=Mock(recognize=Mock(side_effect=[OcrResult(r['raw'],r['confidence']) for r in MANIFEST['recorded_reads']]))
    entry=ENTRIES[-1]
    assert TradingRowReader(engine).read_pair(frame(entry),entry['row_top']) is None
