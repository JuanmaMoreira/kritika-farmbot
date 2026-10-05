import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_reader import EquipmentSellReader
from bot.equipment_sell_semantics import consensus_facts
from bot.ocr import RapidOcrEngine

ROOT = Path(__file__).parent / 'fixtures/equipment_low_tiers'
ENTRIES = json.loads((ROOT / 'manifest.json').read_text())['frames']


@pytest.fixture(scope='module')
def reader():
    return EquipmentSellReader(RapidOcrEngine())


def frame(entry):
    width, height = entry['geometry']
    image = np.zeros((height, width, 3), np.uint8)
    x1, y1, x2, y2 = entry['box']
    image[y1:y2, x1:x2] = cv2.imread(str(ROOT / entry['file']))
    return image


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['file'])
def test_actual_low_tier_panel_authorizes_bulk_with_redundant_guards(reader, entry):
    image = frame(entry)
    samples = [reader.detail_sample(image, sequence=s, observed_at=float(s)) for s in (1, 2)]
    fact = consensus_facts(samples, required=2, max_samples=4)
    assert fact is not None
    assert (fact.grade.value, fact.equipment_type.value, fact.enhance) == (
        entry['grade'], entry['type'], entry['enhance'])
    assert fact.grade_visual is fact.grade and fact.sell_available is True
    assert EquipmentSellPolicy().authorize(fact) is not None


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['file'])
def test_actual_low_tier_label_rejects_other_grade_templates(reader, entry):
    image = frame(entry)
    for grade, template in reader._grade_templates.items():
        if grade.value != entry['grade']:
            assert reader._template_score(image, template, (.565, .322, .745, .372)) < .92
