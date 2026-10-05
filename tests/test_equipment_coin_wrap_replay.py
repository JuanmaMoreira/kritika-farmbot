import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.equipment_sell_reader import EquipmentSellReader, parse_confirmation
from bot.equipment_sell_semantics import EquipmentBulkGroup, consensus_facts
from bot.ocr import RapidOcrEngine

ROOT = Path(__file__).parent / 'fixtures/equipment_coin_wrap'
ENTRIES = json.loads((ROOT / 'manifest.json').read_text())['frames']


@pytest.fixture(scope='module')
def reader():
    return EquipmentSellReader(RapidOcrEngine())


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['file'])
def test_wrapped_k_coin_popup_preserves_identity_and_bulk_scope(reader, entry):
    width, height = entry['geometry']
    image = np.zeros((height, width, 3), np.uint8)
    x, y, xx, yy = entry['box']
    image[y:yy, x:xx] = cv2.imread(str(ROOT / entry['file']))
    facts = [reader.confirmation_sample(image, sequence=s, observed_at=float(s)) for s in (1, 2)]
    fact = consensus_facts(facts, required=2, max_samples=4)
    assert fact is not None
    assert fact.item_name == "Laoku's Destructive Earrings"
    assert fact.group is EquipmentBulkGroup.EQUIPMENT_GRADE
    assert fact.group_type is None


def test_wrapped_identity_without_exact_bulk_scope_cannot_authorize_sale():
    assert parse_confirmation("Selling [Laoku's Destructive Earrings] for", ['Sell [Bulk]']) is None
    assert parse_confirmation("Selling [Laoku's Destructive Earrings] forever", [
        'all of the Equipment of this grade', 'Sell [Bulk]']) is None
