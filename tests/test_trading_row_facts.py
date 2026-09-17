"""Trading row facts: identity, counts, consensus, scope separation."""

import json
from pathlib import Path

import cv2
import pytest

from bot.ocr import RapidOcrEngine
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
