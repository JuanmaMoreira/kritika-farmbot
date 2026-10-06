import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.equipment_sell_reader import (
    EquipmentSellReader, CONFIRM_IDENTITY_ROI,
    CONFIRM_IDENTITY_CONTINUATION_ROI, CONFIRM_COIN_GROUP_LINE_ROIS,
    parse_confirmation,
)
from bot.equipment_sell_semantics import EquipmentBulkGroup, consensus_facts
from bot.ocr import OcrResult, RapidOcrEngine


def test_long_name_native_popup_reads_full_identity_and_exact_bulk_scope():
    root = Path(__file__).parent / 'fixtures/equipment_name_wrap'
    entry = json.loads((root/'manifest.json').read_text())
    width, height = entry['geometry']
    frame = np.zeros((height, width, 3), np.uint8)
    x, y, xx, yy = entry['box']
    frame[y:yy, x:xx] = cv2.imread(str(root/entry['file']))
    reader = EquipmentSellReader(RapidOcrEngine())
    facts = [reader.confirmation_sample(frame,sequence=s,observed_at=float(s)) for s in (1,2)]
    fact = consensus_facts(facts,required=2,max_samples=4)
    assert fact is not None
    assert fact.item_name == "Laoku's Destructive Phantom Sword"
    assert fact.group is EquipmentBulkGroup.EQUIPMENT_GRADE
    assert fact.group_type is None
    assert reader.last_confirmation_diagnostic['continuation']['text'] == 'Sword] for 15 K Coins.'


@pytest.mark.parametrize('continuation,confidence',[
    ('Sword for 15 K Coins.',.99),  # Missing closing bracket remains unreadable.
    ('Sword] forever 15 K Coins.',.99),
    ('Sword] for 15 K Coins.',.79),
    ('',0.),
])
def test_incomplete_or_uncertain_continuation_never_credits_confirmation(continuation,confidence):
    reader = EquipmentSellReader(RapidOcrEngine())
    reads = {
        CONFIRM_IDENTITY_ROI:OcrResult("Selling [Laoku's Destructive Phantom",.99),
        CONFIRM_IDENTITY_CONTINUATION_ROI:OcrResult(continuation,confidence),
    }
    reads.update(zip(CONFIRM_COIN_GROUP_LINE_ROIS,[OcrResult(t,.99) for t in (
        'If you would like to sell all of the','Equipment of this grade,','use the Sell [Bulk] button.')]))
    reader._read = lambda frame,region,**kwargs: reads.get(region,OcrResult('',0.))
    assert reader.confirmation_sample(np.zeros((100,200,3),np.uint8),sequence=1,observed_at=1.) is None


def test_complete_wrapped_identity_still_requires_independent_exact_bulk_scope():
    assert parse_confirmation("Selling [Laoku's Destructive Phantom Sword] for 15 K Coins.",['Sell [Bulk]']) is None
