"""Trading row facts: identity, counts, consensus, scope separation."""

import json
from pathlib import Path

import cv2
import pytest

from bot.ocr import OcrResult, RapidOcrEngine
from bot.perception.trading_center import row_bands
from bot.trading_row_facts import (
    CATALOG_TITLES,
    KEYS_SECTION,
    MATERIALS_SECTION,
    RowSample,
    TradingRowFact,
    TradingRowReader,
    consensus_row_samples,
    normalize_title,
    parse_pair,
    read_row_fact,
    section_for,
    title_matches,
)

ROOT = Path(__file__).resolve().parent.parent


def _sample(item_id="hero_armor_crafting_material", section=MATERIALS_SECTION,
            row_y=0.70, have=39, need=40, sequence=1):
    return RowSample(item_id=item_id, section=section, row_y=row_y,
                     have=have, need=need, sequence=sequence)


def _load_pairs_entries():
    payload = json.loads(
        (ROOT / "datasets/trading_row_pairs_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return [entry for entry in payload["entries"]
            if entry["review_status"] == "confirmed"]


# Identity.


def test_fresh_stable_row_reports_fact():
    fact = consensus_row_samples([_sample(sequence=1), _sample(sequence=2)])
    assert isinstance(fact, TradingRowFact)
    assert (fact.item_id, fact.have, fact.need) == (
        "hero_armor_crafting_material", 39, 40)
    assert fact.sequence == 2
    assert fact.evidence == ("sample@1:39/40", "sample@2:39/40")


def test_wrong_row_identity_reports_no_fact():
    samples = [_sample(sequence=1),
               _sample(item_id="hero_weapon_crafting_material", sequence=2)]
    assert consensus_row_samples(samples) is None


def test_shifted_row_reports_no_stale_fact():
    samples = [_sample(row_y=0.70, sequence=1), _sample(row_y=0.72, sequence=2)]
    assert consensus_row_samples(samples) is None


def test_foreign_section_reports_no_fact():
    with pytest.raises(ValueError):
        RowSample(item_id="hero_armor_crafting_material", section=KEYS_SECTION,
                  row_y=0.70, have=39, need=40, sequence=1)
    assert consensus_row_samples(
        [_sample(sequence=1),
         _sample(section=KEYS_SECTION,
                 item_id="silver_key", have=5, need=10, sequence=2)]
    ) is None


def test_section_ownership():
    assert section_for("hero_armor_crafting_material") == MATERIALS_SECTION
    assert section_for("silver_key") == KEYS_SECTION
    with pytest.raises(ValueError):
        section_for("nope")


# OCR parsing.


@pytest.mark.parametrize("text,expected", (
    ("33/30", (33, 30)),
    ("  3,420,525,277 / 25,000,000 ", (3420525277, 25000000)),
    ("0/1", (0, 1)),
    ("236/10", (236, 10)),
    ("412/10", (412, 10)),
    ("5,439", None),
    ("3.420.525.27", None),
    ("99/53/22", None),
    ("21:2/5", None),
    ("", None),
    (None, None),
))
def test_parse_pair_strict(text, expected):
    assert parse_pair(text) == expected


@pytest.mark.parametrize("text,expected", (
    ("  Super   Awakening Stone 5 ", "super awakening stone 5"),
    ("Silver Key 2", "silver key 2"),
))
def test_normalize_title(text, expected):
    assert normalize_title(text) == expected


def test_title_exact_prefix_wins():
    assert title_matches("Super Awakening Stone 5 Remaining: 13 d 6 h",
                         "super_awakening_stone")
    assert title_matches("silverkey2", "silver_key")
    assert not title_matches("lapiz 5", "lapiz_400")
    assert not title_matches("lapiz 400", "lapiz_5")
    assert not title_matches("accessory crafting material 10",
                             "hero_accessory_crafting_material")
    assert not title_matches("silver key 2", "gold_key")


def test_title_fuzzy_bounded():
    assert title_matches("gold kkey 2", "gold_key")
    assert not title_matches("gold gem chest key", "gold_key")
    assert not title_matches("waaeon craftin", "weapon_crafting_material")


def test_catalog_titles_stay_distinguishable():
    """No title may prefix-match a different row; near twins need margin.

    Prefix-anchored matching confuses row A for row B only if B's title
    starts with A's title (or within 2 edits on a shared long prefix).
    """
    flat = {item_id: normalize_title(title).replace(" ", "")
            for item_id, title in CATALOG_TITLES.items()}
    ids = sorted(flat)
    for pos, first in enumerate(ids):
        for second in ids[pos + 1:]:
            left, right = flat[first], flat[second]
            assert not right.startswith(left), (first, second)
            assert not left.startswith(right), (first, second)
            common = 0
            for left_char, right_char in zip(left, right):
                if left_char != right_char:
                    break
                common += 1
            if common >= 4:
                assert _edit_distance(left, right) > 2, (first, second)


def _edit_distance(first, second):
    previous = list(range(len(second) + 1))
    for i, left in enumerate(first, 1):
        current = [i]
        for j, right in enumerate(second, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


# Consensus.


def test_single_read_reports_no_fact():
    assert consensus_row_samples([_sample(sequence=1)]) is None


def test_changed_have_during_consensus_reports_no_fact():
    samples = [_sample(have=39, sequence=1), _sample(have=38, sequence=2)]
    assert consensus_row_samples(samples) is None


def test_row_drift_beyond_tolerance_reports_no_fact():
    samples = [_sample(row_y=0.70, sequence=1),
               _sample(row_y=0.70 + 0.016, sequence=2)]
    assert consensus_row_samples(samples) is None


def test_keys_local_phase_tolerance_still_rejects_another_row():
    samples = [
        _sample(item_id="gold_key", section=KEYS_SECTION,
                row_y=0.57, have=412, need=10, sequence=1),
        _sample(item_id="gold_key", section=KEYS_SECTION,
                row_y=0.62, have=412, need=10, sequence=2),
    ]
    assert consensus_row_samples(samples, row_tolerance=0.04) is None


def test_stale_sequence_reports_no_fact():
    samples = [_sample(sequence=2), _sample(sequence=2)]
    assert consensus_row_samples(samples) is None


def test_bounded_samples_stop_without_fact():
    samples = [_sample(have=index, sequence=index + 1) for index in range(6)]
    assert consensus_row_samples(samples, required=2, max_samples=4) is None


def test_row_fact_rejects_bad_fields():
    with pytest.raises(ValueError):
        TradingRowFact(item_id="hero_armor_crafting_material",
                       section=MATERIALS_SECTION, row_y=0.70,
                       have=-1, need=40, sequence=2)


# Separation: no input, no economics.


def test_module_has_no_input_or_trade_execution():
    source = (ROOT / "bot" / "trading_row_facts.py").read_text(encoding="utf-8")
    for forbidden in ("adb", "AdbClient", "ActionExecutor", ".tap(",
                      "should_trade", "should_max", "route", "planner"):
        assert forbidden not in source, forbidden
    assert "Gold Key capacity is NOT OBSERVABLE" in source


def test_read_row_fact_never_produces_input():
    import numpy as np

    reader = TradingRowReader(engine=_FakeEngine())
    blank = np.zeros((120, 240, 3), dtype=np.uint8)
    frames = [(blank, 1), (blank, 2)]
    assert read_row_fact(frames, item_id="hero_armor_crafting_material",
                         section=MATERIALS_SECTION, row_top=0.50, row_y=0.57,
                         reader=reader) is None


class _FakeEngine:
    def recognize(self, image):
        from bot.ocr import OcrResult
        return OcrResult(text="", confidence=0.0)


@pytest.mark.parametrize("texts,expected", (
    ((("412/10", 0.98), ("412/10", 0.87)), (412, 10)),
    ((("412/10", 0.98), ("412/", 0.87)), None),
    ((("412/10", 0.98), ("412/9", 0.87)), None),
    ((("412/10", 0.98), ("412/10", 0.49)), None),
))
def test_keys_cell_requires_two_complete_confident_agreeing_reads(texts, expected):
    import numpy as np

    class Engine:
        def __init__(self):
            self.values = iter(texts)

        def recognize(self, _image):
            text, confidence = next(self.values)
            return OcrResult(text, confidence)

    reader = TradingRowReader(Engine())
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    assert reader._read_key_pair_cell(frame, 0.5362) == expected


@pytest.mark.parametrize("path,silver,gold", (
    ("artifacts/acquisition-inventory-relief-chain/trading-keys-char2/20260910T002334_238388Z_01.png", 236, 412),
    ("artifacts/acquisition-inventory-relief-chain/trading-keys-char2/20260910T002334_363497Z_02.png", 236, 412),
    ("artifacts/acquisition-inventory-relief-chain/trading-keys-char2/20260910T002334_485307Z_03.png", 236, 412),
    ("artifacts/acquisition-inventory-relief-chain/trading-keys-recheck/20260909T224443_033566Z_01.png", 229, 188),
    ("artifacts/acquisition-inventory-relief-chain/trading-keys-recheck/20260909T224443_159830Z_02.png", 229, 188),
    ("artifacts/acquisition-inventory-relief-chain/trading-keys-recheck/20260909T224443_286782Z_03.png", 229, 188),
    ("screencaps/semantic/trading-center/keys-top/01.png", 5, 9),
))
def test_native_keys_rows_replay(path, silver, gold):
    frame = cv2.imread(str(ROOT / path))
    assert frame is not None
    reader = TradingRowReader(RapidOcrEngine())
    found = {}
    for top, _bottom, center, complete in row_bands(frame):
        if not complete:
            continue
        for item_id in ("silver_key", "gold_key"):
            sample = reader.read_sample(
                frame, 1, item_id=item_id, section=KEYS_SECTION,
                row_top=top, row_y=center,
            )
            if sample is not None:
                assert item_id not in found
                found[item_id] = (sample.have, sample.need)
    assert found == {"silver_key": (silver, 10), "gold_key": (gold, 10)}


def test_native_gold_row_does_not_match_silver_identity():
    frame = cv2.imread(str(ROOT / "artifacts/acquisition-inventory-relief-chain"
                          / "trading-keys-char2/20260910T002334_238388Z_01.png"))
    assert frame is not None
    reader = TradingRowReader(RapidOcrEngine())
    bands = [band for band in row_bands(frame) if band[3]]
    gold_top, _bottom, gold_center, _complete = bands[1]
    assert reader.read_sample(
        frame, 1, item_id="silver_key", section=KEYS_SECTION,
        row_top=gold_top, row_y=gold_center,
    ) is None


# Evaluator over the HIL pairs manifest: zero misparses allowed.


def _manifest_frames():
    return _load_pairs_entries()


def test_evaluator_reports_zero_wrong_reads():
    reader = TradingRowReader(engine=RapidOcrEngine())
    wrong = []
    covered = 0
    for entry in _manifest_frames():
        frame = cv2.imread(str(ROOT / entry["path"]))
        assert frame is not None, entry["path"]
        bands = row_bands(frame)
        complete = [band for band in bands if band[3]]
        assert len(complete) == 4, (entry["path"], len(complete))
        for band, expected in zip(complete, entry["rows"]):
            top, _, center, _ = band
            sample = reader.read_sample(
                frame, 1, item_id=expected["item_id"],
                section=entry["section"], row_top=top, row_y=center)
            if sample is None:
                continue
            covered += 1
            if (sample.have, sample.need) != (expected["have"],
                                              expected["need"]):
                wrong.append((entry["path"], expected["item_id"],
                              (sample.have, sample.need),
                              (expected["have"], expected["need"])))
    assert wrong == []
    assert covered >= 16
