"""Physical title colors, held-out names, ambiguous ink and economic boundaries."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_reader import EquipmentSellReader, DETAIL_GRADE_TYPE_ROI
from bot.equipment_sell_semantics import EquipmentGrade as G, consensus_facts
from bot.equipment_title_color import selected_title_color, TITLE_INK_ROI
from bot.geometry import relative_region_to_pixels
from bot.ocr import OcrResult, RapidOcrEngine


ROOT = Path(__file__).parent / "fixtures/equipment_title_color"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
ENTRIES = MANIFEST["entries"]
BY_ID = {entry["id"]: entry for entry in ENTRIES}


def native(entry):
    w, h = entry["geometry"]
    frame = np.zeros((h, w, 3), np.uint8)
    for crop in entry["crops"]:
        data = (ROOT / crop["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == crop["sha256"]
        x, y, xx, yy = crop["box"]
        frame[y:yy, x:xx] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return frame


@pytest.fixture(scope="module")
def reader():
    return EquipmentSellReader(RapidOcrEngine())


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry["id"])
def test_native_corpus_keeps_tier_type_family_and_context_separate(reader, entry):
    frame = native(entry)
    facts = [reader.detail_sample(frame, sequence=s, observed_at=float(s)) for s in (1, 2)]
    if entry["grade"] is None:
        assert facts == [None, None]
        return
    fact = consensus_facts(facts)
    assert fact is not None and fact.confirmed and fact.tier_by_color
    assert (fact.grade.value, fact.equipment_type.value, fact.enhance) == (
        entry["grade"], entry["type"], entry["enhance"])
    assert fact.name == "" and fact.grade_visual is fact.grade
    authorization = EquipmentSellPolicy().authorize(fact)
    if fact.grade is G.ETHEREAL_PLUS or entry["id"] == "ethereal_necklace":
        assert authorization is None
    else:
        assert authorization is not None


@pytest.mark.parametrize("entry", [entry for entry in ENTRIES if entry["grade"] == "legendary"],
                         ids=lambda entry: entry["id"])
def test_legendary_names_never_need_title_ocr_or_legendary_word(entry, reader, monkeypatch):
    calls = []
    def subtype_only(frame, region, **kwargs):
        calls.append(region)
        # Deliberately misread the tier token. Only the subtype is consumed.
        return OcrResult(f"[Unreadable tier] {entry['type']}", .99)
    monkeypatch.setattr(reader, "_read", subtype_only)
    fact = reader.detail_sample(native(entry), sequence=1, observed_at=1.)
    assert fact is not None and fact.grade is G.LEGENDARY
    assert calls == [DETAIL_GRADE_TYPE_ROI]


@pytest.mark.parametrize("case", list(MANIFEST["failure_coverage"]))
def test_recent_legendary_failure_has_honest_pixel_or_semantic_coverage(reader, case):
    coverage = MANIFEST["failure_coverage"][case]
    if coverage["panel"] is None:
        assert coverage["semantic_test"] == "test_equipment_sell_origin"
        assert "not retained" in coverage["limit"]
        return
    fact = reader.detail_sample(native(BY_ID[coverage["panel"]]), sequence=1, observed_at=1.)
    assert fact is not None and fact.grade is G.LEGENDARY


@pytest.mark.parametrize("key", [entry["id"] for entry in ENTRIES if entry["grade"] not in (None, "ethereal+")])
@pytest.mark.parametrize("variation", ["dark", "bright", "codec", "blur", "noise", "resized"])
def test_native_ink_generalizes_capture_variations(key, variation):
    frame = native(BY_ID[key])
    if variation == "dark": frame = np.clip(frame.astype(float) * .75, 0, 255).astype(np.uint8)
    elif variation == "bright": frame = np.clip(frame.astype(float) * 1.15, 0, 255).astype(np.uint8)
    elif variation == "codec":
        _, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    elif variation == "blur": frame = cv2.GaussianBlur(frame, (3, 3), .5)
    elif variation == "noise":
        noise = np.random.default_rng(7).integers(-3, 4, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    else: frame = cv2.resize(frame, None, fx=.75, fy=.75, interpolation=cv2.INTER_AREA)
    expected = G(BY_ID[key]["grade"])
    assert selected_title_color(frame).grade is expected


def recolored_title(hue, *, saturation=240, mixed=False):
    frame = native(BY_ID["legendary_phantom"])
    x, y, xx, yy = relative_region_to_pixels(TITLE_INK_ROI, frame.shape[1], frame.shape[0])
    crop = frame[y:yy, x:xx]
    ink = selected_title_color(frame).mask > 0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hsv[:, :, 0][ink] = hue
    hsv[:, :, 1][ink] = saturation
    if mixed:
        half = ink.copy(); half[:, :ink.shape[1]//2] = False
        hsv[:, :, 0][half] = 59
    frame[y:yy, x:xx] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return frame


@pytest.mark.parametrize("hue,saturation,mixed", [(5, 240, False), (20, 240, False),
                                                  (10, 80, False), (10, 240, True)])
def test_close_unacquired_or_mixed_colors_are_unknown_and_cannot_sell(reader, hue, saturation, mixed):
    frame = recolored_title(hue, saturation=saturation, mixed=mixed)
    assert selected_title_color(frame).grade is G.UNKNOWN
    assert reader.detail_sample(frame, sequence=1, observed_at=1.) is None
    assert EquipmentSellPolicy().authorize(None) is None


@pytest.mark.parametrize("decoration", ["solid", "specks", "horizontal_border"])
def test_orange_background_highlights_and_decorations_are_not_title_ink(decoration):
    frame = np.zeros((1224, 2712, 3), np.uint8)
    x, y, xx, yy = relative_region_to_pixels(TITLE_INK_ROI, frame.shape[1], frame.shape[0])
    if decoration == "solid": frame[y:yy, x:xx] = (0, 100, 255)
    elif decoration == "specks":
        for offset in range(10, 300, 30): frame[y+12:y+15, x+offset:x+offset+3] = (0, 100, 255)
    else: frame[y+5:y+8, x:xx] = (0, 100, 255)
    assert selected_title_color(frame).grade is G.UNKNOWN


def test_red_plus_cannot_be_downgraded_by_bad_ocr(reader, monkeypatch):
    monkeypatch.setattr(reader, "_read", lambda *args, **kwargs: OcrResult("[Legendary] Chest Armor", .99))
    fact = reader.detail_sample(native(BY_ID["ethereal_plus"]), sequence=1, observed_at=1.)
    assert fact is not None and fact.grade is G.ETHEREAL_PLUS
    assert EquipmentSellPolicy().authorize(replace(fact, sequence=2, sample_sequences=(1, 2))) is None


def test_red_without_unambiguous_grade_marker_is_unknown(reader):
    frame = native(BY_ID["ethereal_necklace"])
    x, y, xx, yy = relative_region_to_pixels((.565,.322,.745,.372), frame.shape[1], frame.shape[0])
    frame[y:yy, x:xx] = 0
    assert selected_title_color(frame).grade is G.ETHEREAL
    assert reader.detail_sample(frame, sequence=1, observed_at=1.) is None


def test_color_fact_consensus_does_not_depend_on_debug_name(reader):
    fact = reader.detail_sample(native(BY_ID["legendary_phantom"]), sequence=1, observed_at=1.)
    changed_spelling = replace(fact, name="Desructive", sequence=2, observed_at=2., sample_sequences=(2,))
    assert consensus_facts([fact, changed_spelling]).confirmed


@pytest.mark.parametrize("variation", ["codec", "blur", "dim", "resized"])
def test_red_plus_capture_variations_never_become_sellable_ethereal(reader, variation):
    frame = native(BY_ID["ethereal_plus"])
    if variation == "codec":
        _, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    elif variation == "blur": frame = cv2.GaussianBlur(frame, (3, 3), .6)
    elif variation == "dim": frame = np.clip(frame.astype(float) * .75, 0, 255).astype(np.uint8)
    else: frame = cv2.resize(frame, None, fx=.75, fy=.75, interpolation=cv2.INTER_AREA)
    fact = reader.detail_sample(frame, sequence=1, observed_at=1.)
    assert fact is None or fact.grade is G.ETHEREAL_PLUS


def test_white_glow_cannot_supply_a_different_tier():
    frame = native(BY_ID["legendary_alter"])
    x, y, xx, yy = relative_region_to_pixels(TITLE_INK_ROI, frame.shape[1], frame.shape[0])
    cv2.line(frame, (x+140, y), (x+180, yy-1), (255,255,255), 6, cv2.LINE_AA)
    assert selected_title_color(frame).grade in (G.LEGENDARY, G.UNKNOWN)
