"""The optional name-approved HIL harness keeps its extra authorization guard."""

from unittest.mock import Mock

import pytest

from bot.equipment_sell_reader import DETAIL_TITLE_ROI
from bot.equipment_sell_semantics import EquipmentGrade as G, EquipmentItemFact, EquipmentType as T
from bot.ocr import OcrResult
from tools.equipment_sell_hil import _ApprovedNameReader


@pytest.mark.parametrize("text,confidence,accepted", [
    ("Laoku's Destructive Gear", .99, True),
    ("Other Gear", .99, False),
    ("Laoku's Destructive Gear", .79, False),
])
def test_explicit_hil_name_approval_is_separate_from_color_tier(text, confidence, accepted):
    fact = EquipmentItemFact("", G.LEGENDARY, T.HELMET, False, 1, 1., (1,),
                             tier_by_color=True, grade_visual=G.LEGENDARY, sell_available=True)
    reader = Mock()
    reader.detail_sample.return_value = fact
    reader._read.return_value = OcrResult(text, confidence)
    guarded = _ApprovedNameReader(reader, "Laoku's Destructive Gear")
    frame = object()
    result = guarded.detail_sample(frame, sequence=1, observed_at=1.)
    assert (result is fact) == accepted
    reader._read.assert_called_once_with(frame, DETAIL_TITLE_ROI, scale=2.0)


def test_unknown_detail_cannot_be_authorized_by_hil_name():
    reader = Mock()
    reader.detail_sample.return_value = None
    assert _ApprovedNameReader(reader, "Approved name").detail_sample(object()) is None
    reader._read.assert_not_called()
