"""Regression for character 10's Sell failure in session f4663332."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.equipment_sell_reader import (
    CONFIRM_COIN_GROUP_LINE_ROIS,
    CONFIRM_GROUP_LINE_ROIS,
    CONFIRM_IDENTITY_CONTINUATION_ROI,
    CONFIRM_IDENTITY_ROI,
    EquipmentSellReader,
    parse_confirmation,
)
from bot.equipment_sell_semantics import EquipmentBulkGroup, consensus_facts
from bot.ocr import OcrResult, RapidOcrEngine


def test_native_payment_wrap_preserves_name_and_independent_bulk_scope():
    root = Path(__file__).parent / "fixtures/equipment_payment_wrap"
    entry = json.loads((root / "manifest.json").read_text())
    data = (root / entry["file"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    width, height = entry["geometry"]
    frame = np.zeros((height, width, 3), np.uint8)
    x, y, xx, yy = entry["box"]
    frame[y:yy, x:xx] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    reader = EquipmentSellReader(RapidOcrEngine())

    # The old path chose these unshifted regions solely because line 1 lacks "for".
    identity = reader._read(frame, CONFIRM_IDENTITY_ROI, scale=2.5)
    old_groups = [reader._read(frame, roi, scale=2.5).text for roi in CONFIRM_GROUP_LINE_ROIS]
    assert identity.text == "Selling [Laoku's Destructive Shortsword]"
    assert parse_confirmation(identity.text, old_groups) is None

    facts = [reader.confirmation_sample(frame, sequence=s, observed_at=float(s)) for s in (1, 2)]
    fact = consensus_facts(facts, required=2, max_samples=4)
    assert fact is not None and fact.confirmed
    assert fact.item_name == "Laoku's Destructive Shortsword"
    assert fact.group is EquipmentBulkGroup.EQUIPMENT_GRADE
    assert fact.group_type is None
    assert reader.last_confirmation_diagnostic["continuation"]["text"] == "for 15 K Coins."


@pytest.mark.parametrize("payment,confidence", [
    ("for 15 K Coins.", .79),
    ("forever 15 K Coins.", .99),
    ("for ? K Coins.", .99),
    ("for 15 Karats.", .99),
    ("for 15 Gold.", .99),
    ("for 15 K Coins and 1 Karat.", .99),
    ("for 15/20 K Coins.", .99),
    ("", 0.),
])
def test_uncertain_or_invalid_payment_cannot_select_shifted_scope(payment, confidence):
    reader = EquipmentSellReader(RapidOcrEngine())
    reads = {
        CONFIRM_IDENTITY_ROI: OcrResult("Selling [Laoku's Destructive Shortsword]", .99),
        CONFIRM_IDENTITY_CONTINUATION_ROI: OcrResult(payment, confidence),
    }
    reads.update(zip(CONFIRM_COIN_GROUP_LINE_ROIS, [OcrResult(t, .99) for t in (
        "If you would like to sell all of the", "Equipment of this grade,", "use the Sell [Bulk] button.",
    )]))
    reader._read = lambda frame, region, **kwargs: reads.get(region, OcrResult("", 0.))
    assert reader.confirmation_sample(np.zeros((100, 200, 3), np.uint8), sequence=1, observed_at=1.) is None


@pytest.mark.parametrize('payment', ['for 15 K Coins.', 'for 1,500 K Coins.'])
def test_positive_k_coin_quote_selects_only_the_independent_bulk_scope(payment):
    reader = EquipmentSellReader(RapidOcrEngine())
    reads = {
        CONFIRM_IDENTITY_ROI: OcrResult("Selling [Laoku's Destructive Shortsword]", .99),
        CONFIRM_IDENTITY_CONTINUATION_ROI: OcrResult(payment, .99),
    }
    reads.update(zip(CONFIRM_COIN_GROUP_LINE_ROIS, [OcrResult(t, .99) for t in (
        "If you would like to sell all of the", "Equipment of this grade,",
        "use the Sell [Bulk] button.",
    )]))
    reader._read = lambda frame, region, **kwargs: reads.get(region, OcrResult("", 0.))
    fact = reader.confirmation_sample(np.zeros((100, 200, 3), np.uint8), sequence=1, observed_at=1.)
    assert fact is not None and fact.group is EquipmentBulkGroup.EQUIPMENT_GRADE
    assert payment in fact.evidence[0]


def test_positive_payment_does_not_substitute_for_bulk_scope():
    reader = EquipmentSellReader(RapidOcrEngine())
    reads = {
        CONFIRM_IDENTITY_ROI: OcrResult("Selling [Laoku's Destructive Shortsword]", .99),
        CONFIRM_IDENTITY_CONTINUATION_ROI: OcrResult("for 15 K Coins.", .99),
    }
    reads.update(zip(CONFIRM_COIN_GROUP_LINE_ROIS, [OcrResult(t, .99) for t in (
        "If you would like to sell all of the", "Unknown items of this grade,", "use the Sell [Bulk] button.",
    )]))
    reader._read = lambda frame, region, **kwargs: reads.get(region, OcrResult("", 0.))
    assert reader.confirmation_sample(np.zeros((100, 200, 3), np.uint8), sequence=1, observed_at=1.) is None
