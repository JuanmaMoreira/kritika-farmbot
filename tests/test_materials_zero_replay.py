"""Red 0/40 effect must remain readable without another economic input."""
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.ocr import OcrResult, RapidOcrEngine
from bot.trading_row_facts import TradingRowReader, MATERIALS_SECTION, consensus_row_samples

FIXTURES=Path(__file__).parent/'fixtures/materials_zero'
ENTRIES=json.loads((FIXTURES/'manifest.json').read_text())['entries']


def frame(entry):
    image=np.zeros((*entry['shape'],3),np.uint8)
    x,y,xx,yy=entry['rect']
    data=(FIXTURES/entry['file']).read_bytes()
    assert sha256(data).hexdigest()==entry['sha256']
    image[y:yy,x:xx]=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    return image


@pytest.fixture(scope='module')
def engine():
    return RapidOcrEngine()


@pytest.mark.parametrize('entry',ENTRIES)
@pytest.mark.parametrize('native_scale',[False,True])
def test_retained_red_zero_has_two_agreeing_reads(engine,entry,native_scale):
    image=frame(entry)
    if native_scale:image=cv2.resize(image,(2712,1224))
    diagnostic={}
    pair=TradingRowReader(engine).read_pair(image,entry['row_top'],diagnostics=diagnostic)
    assert pair==(0,40)
    assert [r['parse_result'] for r in diagnostic['pair_reads']]==[(0,40),(0,40)]


def test_fresh_zero_consensus_preserves_material_identity(engine):
    samples=[TradingRowReader(engine).read_sample(frame(entry),i+1,
        item_id='hero_weapon_crafting_material',section=MATERIALS_SECTION,
        row_top=entry['row_top'],row_y=entry['row_y']) for i,entry in enumerate(ENTRIES)]
    assert all(sample is not None for sample in samples)
    fact=consensus_row_samples(samples)
    assert fact is not None and (fact.have,fact.need)==(0,40)


def test_exact_logged_disagreement_still_fails_closed():
    reads=json.loads((FIXTURES/'recorded_reads.json').read_text())
    engine=Mock(recognize=Mock(side_effect=[OcrResult(r['raw'],r['confidence']) for r in reads]))
    assert TradingRowReader(engine).read_pair(frame(ENTRIES[-1]),ENTRIES[-1]['row_top']) is None


def test_gray_corner_is_excluded_without_erasing_red_antialias():
    seen=[]
    engine=Mock(recognize=lambda image:(seen.append(image.copy()) or OcrResult('0/40',.99)))
    reader=TradingRowReader(engine)
    image=frame(ENTRIES[-1]);entry=ENTRIES[-1]
    assert reader.read_pair(image,entry['row_top'])==(0,40)
    assert len(seen)==2
    assert all(crop.ndim==2 and np.any((crop>0)&(crop<255)) for crop in seen)


@pytest.mark.parametrize('values',[('0/40','1/40'),('0/40','L0/40'),('0/40',''),
                                  ('0/40','0'),('0/40','0/'),('0/40','/40'),
                                  ('0/40','O/40'),('0/40','0/40 15')])
def test_red_preprocessing_never_accepts_disagreeing_pairs(values):
    engine=Mock(recognize=Mock(side_effect=[OcrResult(value,.99) for value in values]))
    assert TradingRowReader(engine).read_pair(frame(ENTRIES[-1]),ENTRIES[-1]['row_top']) is None


@pytest.mark.parametrize('confidences',[(.49,.99),(.99,.49)])
def test_red_color_cannot_bypass_ocr_confidence(confidences):
    engine=Mock(recognize=Mock(side_effect=[OcrResult('0/40',value) for value in confidences]))
    assert TradingRowReader(engine).read_pair(frame(ENTRIES[-1]),ENTRIES[-1]['row_top']) is None


def test_empty_localized_box_stays_unreadable_without_ocr(monkeypatch):
    monkeypatch.setattr('bot.trading_row_facts._localize_pair',
                        lambda *args:(.50,.60,.5001,.6001))
    engine=Mock()
    diagnostic={}
    assert TradingRowReader(engine).read_pair(frame(ENTRIES[-1]),ENTRIES[-1]['row_top'],
                                            diagnostics=diagnostic) is None
    assert diagnostic['localized_reason']=='empty_pair_roi'
    engine.recognize.assert_not_called()
