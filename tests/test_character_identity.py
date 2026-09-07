import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.catalog import SCREEN_LOBBY, SCREEN_CHARACTER_SELECT
from bot.character_identity import (
    LOBBY_PERSONAL_NAME_ROI, MIN_NAME_CONFIDENCE, PERSONAL_NAME_CLASSES,
    KNOWN_LOBBY_NAME_OCR_VARIANTS,
    LobbyNameRecognizer,
)
from bot.geometry import relative_region_to_pixels
from bot.ocr import OcrResult, RapidOcrEngine
from bot.state import ResolutionStatus


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/character_identity_manifest.json"
EXPECTED = {
    "DRAKEN三BB": "Burst Breaker", "DRAKEN一BK": "Berserker", "DRAKEN二DB": "Demon Blade",
    "Drakenn25": "Kaiserin", "Drakenn13": "Noblia", "Drakenn10": "Ice Warlock",
    "Drakenn09": "Crimson Assassin", "DRAKEN四R": "Rang", "Drakenn26": "Telumpel",
    "Drakenn20": "Halo Mage", "Drakenn19": "Strike Archer", "Drakenn23": "Galaxy Lord",
    "Drakenn08": "Wandering Master", "Drakenn14": "Steam Walker",
    "Drakennn15": "Mystic Wolf Guardian", "Drakenn16": "Blood Demon", "Drakenn06": "Eclair",
    "Drakenn21": "Dark Valkyrie", "Drakennn17": "Elemental Fairy", "Drakenn24": "Hastati",
    "DRAKEN六FS": "Flame Striker", "Drakenn27": "Eilla", "Drakenn11": "Lina",
    "Drakenn12": "Cat Acrobat", "Drakenn18": "Shadow Mage", "DRAKEN五M": "Monk",
    "DRAKEN四BD": "Blade Dancer", "Drakenn22": "Dimension Manipulator",
}


def snapshot(*, image=None, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY, overlays=()):
    return SimpleNamespace(
        state=SimpleNamespace(status=status, base_context=base, overlays=frozenset(overlays)),
        frame=SimpleNamespace(image=np.zeros((400, 800, 3), np.uint8) if image is None else image),
    )


@pytest.mark.parametrize("name,class_name", EXPECTED.items())
def test_exact_unicode_lookup(name, class_name):
    engine = Mock(recognize=Mock(return_value=OcrResult(name, .99)))
    identity = LobbyNameRecognizer(engine).recognize(snapshot())
    assert identity.personal_name == name
    assert identity.class_name == class_name
    assert identity.confidence == .99
    assert engine.recognize.call_count == 1


def test_mapping_is_exact_complete_and_immutable():
    assert dict(PERSONAL_NAME_CLASSES) == EXPECTED
    with pytest.raises(TypeError):
        PERSONAL_NAME_CLASSES["Drakenn25"] = "other"


@pytest.mark.parametrize("text", [
    "", "Drakenn99", "Drakenn15", "Drakenn17", "drakenn25",
    "DRAKEN—BK", "DRAKENーBK", "DRAKEN1BK", "DRAKEN二BB",
    "Drakenn25 CP", "prefix Drakenn25", "Drakenn25\nDrakenn26", " Drakenn25", "Drakenn25 ",
    "Ｄｒａｋｅｎｎ25", "Drakenn\u200b25", "DRAKEN四", "DRAKEN四B", "DRAKEN四RD",
])
def test_unknown_contaminated_alias_or_near_name_is_never_repaired(text):
    assert LobbyNameRecognizer(Mock(recognize=Mock(return_value=OcrResult(text, 1)))).recognize(snapshot()) is None


VARIANTS = {
    "DRAKEN-BK": "DRAKEN一BK", "DRAKEN-DB": "DRAKEN二DB",
    "DRAKENDB": "DRAKEN二DB", "DRAKEN=BB": "DRAKEN三BB",
}


@pytest.mark.parametrize("text,canonical", VARIANTS.items())
@pytest.mark.parametrize("confidence", [.95, .99])
def test_closed_variants_preserve_exact_canonical_unicode(text, canonical, confidence):
    engine = Mock(recognize=Mock(return_value=OcrResult(text, confidence, (("line_count", 1),))))
    identity = LobbyNameRecognizer(engine).recognize(snapshot())
    assert identity.personal_name == canonical
    assert identity.class_name == EXPECTED[canonical]
    assert identity.confidence == confidence
    assert engine.recognize.call_count == 1


def test_variants_are_separate_immutable_and_have_only_authoritative_targets():
    assert dict(KNOWN_LOBBY_NAME_OCR_VARIANTS) == VARIANTS
    assert not (VARIANTS.keys() & PERSONAL_NAME_CLASSES.keys())
    assert set(VARIANTS.values()) == {"DRAKEN一BK", "DRAKEN二DB", "DRAKEN三BB"}
    with pytest.raises(TypeError):
        KNOWN_LOBBY_NAME_OCR_VARIANTS["DRAKEN-BK"] = "other"


@pytest.mark.parametrize("text", VARIANTS)
@pytest.mark.parametrize("kwargs", [
    dict(confidence=.949999), dict(confidence=.91536),
    dict(confidence=1, metadata=(("line_count", 2),)),
])
def test_variants_never_bypass_confidence_or_line_gate(text, kwargs):
    engine = Mock(recognize=Mock(return_value=OcrResult(text, **kwargs)))
    assert LobbyNameRecognizer(engine).recognize(snapshot()) is None


@pytest.mark.parametrize("text", [
    "DRAKENBK", "DRAKEN=BK", "DRAKEN-BB", "DRAKENBB", "DRAKEN=DB", "DRAKEN--DB",
    "DRAKEN-BKX", "DRAKEN-DBB", "DRAKEN=BBB", "DRAKENDBK", "DRAKEN-BK DB",
    " DRAKEN-BK", "DRAKEN-DB ", "DRAKENDB\n", "DRAKEN=BB\u200b", "draken-bk",
    "DRAKEM-BK", "OTHER-BK", "prefixDRAKEN-BK", "DRAKEN-BKsuffix", "DRAKEN-D B",
    "DRAKEN=B B", "DRAKEN-B K", "Drakenn-25", "DRAKEN-四R", "DRAKEN=四BD",
])
def test_closed_variants_reject_near_names_contaminated_suffixes_and_partial_matches(text):
    engine = Mock(recognize=Mock(return_value=OcrResult(text, 1)))
    assert LobbyNameRecognizer(engine).recognize(snapshot()) is None


@pytest.mark.parametrize("text", VARIANTS)
@pytest.mark.parametrize("state", [dict(status=ResolutionStatus.UNKNOWN),
                                     dict(status=ResolutionStatus.AMBIGUOUS),
                                     dict(base=SCREEN_CHARACTER_SELECT),
                                     dict(overlays=("menu.quick",))])
def test_variant_lookup_requires_clean_lobby(text, state):
    engine = Mock(recognize=Mock(return_value=OcrResult(text, 1)))
    assert LobbyNameRecognizer(engine).recognize(snapshot(**state)) is None
    engine.recognize.assert_not_called()


@pytest.mark.parametrize("confidence,accepted", [(.949999, False), (.95, True), (1, True), (0, False)])
def test_confidence_gate(confidence, accepted):
    result = OcrResult("Drakenn25", confidence)
    assert (LobbyNameRecognizer(Mock(recognize=Mock(return_value=result))).recognize(snapshot()) is not None) == accepted
    assert MIN_NAME_CONFIDENCE == .95


def test_multiline_result_and_backend_exception_are_nonfatal():
    engine = Mock(recognize=Mock(return_value=OcrResult("Drakenn25", 1, (("line_count", 2),))))
    assert LobbyNameRecognizer(engine).recognize(snapshot()) is None
    engine.recognize.side_effect = RuntimeError("backend failed")
    assert LobbyNameRecognizer(engine).recognize(snapshot()) is None


@pytest.mark.parametrize("state", [
    dict(status=ResolutionStatus.UNKNOWN), dict(status=ResolutionStatus.AMBIGUOUS),
    dict(base=SCREEN_CHARACTER_SELECT), dict(base=None), dict(overlays=("menu.quick",)),
])
def test_wrong_context_never_invokes_ocr(state):
    engine = Mock()
    assert LobbyNameRecognizer(engine).recognize(snapshot(**state)) is None
    engine.recognize.assert_not_called()


def test_missing_snapshot_never_invokes_ocr():
    engine = Mock()
    assert LobbyNameRecognizer(engine).recognize(None) is None
    engine.recognize.assert_not_called()


def test_crop_scales_from_frame_and_backend_cannot_mutate_capture():
    image = np.arange(500 * 1000 * 3, dtype=np.uint8).reshape(500, 1000, 3)
    original = image.copy()
    def recognize(crop):
        x1, y1, x2, y2 = relative_region_to_pixels(LOBBY_PERSONAL_NAME_ROI, 1000, 500)
        np.testing.assert_array_equal(crop, original[y1:y2, x1:x2])
        crop[:] = 0
        return OcrResult("Drakenn25", 1)
    assert LobbyNameRecognizer(SimpleNamespace(recognize=recognize)).recognize(snapshot(image=image))
    np.testing.assert_array_equal(image, original)


def test_real_ocr_curated_pairs_and_manifest_provenance():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    assert len(entries) == 84
    assert len({e["path"] for e in entries}) == 84
    assert {e["personal_name"]: e["class_name"] for e in entries} == EXPECTED
    assert sum(e["split"] == "calibration" for e in entries) == 28
    assert sum(e["split"] == "validation" for e in entries) == 56
    curated = [e for e in entries if "crop" in e]
    assert len(curated) == 18
    width, height = manifest["curation"]["frame_size"]
    x1, y1, x2, y2 = relative_region_to_pixels(LOBBY_PERSONAL_NAME_ROI, width, height)
    recognizer = LobbyNameRecognizer(RapidOcrEngine())
    for entry in curated:
        path = ROOT / entry["crop"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["crop_sha256"]
        image = np.zeros((height, width, 3), np.uint8)
        image[y1:y2, x1:x2] = cv2.imread(str(path))
        identity = recognizer.recognize(snapshot(image=image))
        assert identity.personal_name == entry["personal_name"]
        assert identity.class_name == entry["class_name"]
