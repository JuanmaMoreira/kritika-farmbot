"""Incremental Trading Center perception evaluation over the HIL corpus."""

import json
from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.perception import (
    TRADING_SCOPE,
    build_trading_perception,
    select_detectors,
)
from bot.perception.local_cv import LocalCvDetector
from bot.perception.trading_center import (
    TRADING_CENTER_TITLE_SPEC,
    TradingRowsDetector,
    TradingTabsDetector,
    row_bands,
)

ROOT = Path(__file__).resolve().parent.parent
VOCABULARY = {
    "landmark.trading_center_title",
    "indicator.trading_general_active",
    "indicator.trading_keys_active",
    "indicator.trading_material_rows",
    "indicator.trading_keys_rows",
}


def _load_entries():
    payload = json.loads(
        (ROOT / "datasets/trading_center_semantic_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return [
        entry for entry in payload["entries"] if entry["review_status"] == "confirmed"
    ]


def test_trading_detectors_match_curated_labels_without_errors():
    title = LocalCvDetector(TRADING_CENTER_TITLE_SPEC, asset_root=ROOT)
    tabs = TradingTabsDetector(asset_root=ROOT)
    rows = TradingRowsDetector(asset_root=ROOT)
    wrong = []
    for entry in _load_entries():
        frame = cv2.imread(str(ROOT / entry["path"]))
        assert frame is not None, entry["path"]
        found = {
            observation.name
            for observation in (
                *title.detect(frame),
                *tabs.detect(frame),
                *rows.detect(frame),
            )
        }
        expected = set(entry["observations"])
        assert found <= VOCABULARY, (entry["path"], found - VOCABULARY)
        if found != expected:
            wrong.append((entry["path"], sorted(expected), sorted(found)))
    assert wrong == []


def test_trading_title_calibration_keeps_lobby_below_any_trading_frame():
    detector = LocalCvDetector(TRADING_CENTER_TITLE_SPEC, asset_root=ROOT)
    scores = {}
    for entry in _load_entries():
        frame = cv2.imread(str(ROOT / entry["path"]))
        scores[entry["path"]] = detector.measure(frame).raw_match_score
    lobby = scores["screencaps/semantic/trading-center/lobby/01.png"]
    trading = [
        score for path, score in scores.items() if "lobby" not in path
    ]
    assert min(trading) > lobby


def test_trading_tab_orange_gap_separates_active_from_inactive():
    detector = TradingTabsDetector(asset_root=ROOT)
    general_active, general_inactive = [], []
    keys_active, keys_inactive = [], []
    for entry in _load_entries():
        frame = cv2.imread(str(ROOT / entry["path"]))
        reading = detector.measure(frame)
        names = set(entry["observations"])
        (general_active if "indicator.trading_general_active" in names
         else general_inactive).append(reading.general_orange_fraction)
        (keys_active if "indicator.trading_keys_active" in names
         else keys_inactive).append(reading.keys_orange_fraction)
    assert min(general_active) > max(general_inactive)
    assert min(keys_active) > max(keys_inactive)


@pytest.mark.parametrize(
    "frame_path,full_bands,partial_bands",
    (
        ("general-top/01.png", 4, 0),
        ("general-mid/01.png", 4, 0),
        ("general-mid/02.png", 4, 0),
        ("general-mid/03.png", 4, 0),
        ("general-mid/04.png", 4, 0),
        ("general-mid/05.png", 4, 0),
        ("general-bottom/01.png", 4, 0),
        ("keys-top/01.png", 4, 0),
    ),
)
def test_row_bands_follow_pitch_grid(frame_path, full_bands, partial_bands):
    frame = cv2.imread(
        str(ROOT / "screencaps/semantic/trading-center" / frame_path)
    )
    bands = row_bands(frame)
    assert sum(1 for band in bands if band[3]) == full_bands
    assert sum(1 for band in bands if not band[3]) == partial_bands
    centers = [band[2] for band in bands if band[3]]
    for first, second in zip(centers, centers[1:]):
        assert second - first == pytest.approx(0.1418, abs=0.005)


def test_trading_scope_selects_standalone_detectors_in_order():
    source = build_trading_perception(asset_root=ROOT)
    assert len(source.detectors) == 3
    scoped = select_detectors(source, TRADING_SCOPE)
    assert tuple(scoped.detectors) == tuple(source.detectors)


@pytest.mark.parametrize(
    "frame_path,expected",
    (
        ("general-top/01.png", {
            "landmark.trading_center_title",
            "indicator.trading_general_active",
            "indicator.trading_material_rows",
        }),
        ("keys-top/01.png", {
            "landmark.trading_center_title",
            "indicator.trading_keys_active",
            "indicator.trading_keys_rows",
        }),
        ("lobby/01.png", set()),
    ),
)
def test_trading_scope_resolves_expected_labels(frame_path, expected):
    source = build_trading_perception(asset_root=ROOT)
    scoped = select_detectors(source, TRADING_SCOPE)
    frame = cv2.imread(
        str(ROOT / "screencaps/semantic/trading-center" / frame_path)
    )
    batch = scoped.analyze(FrameSnapshot(frame, 1.0, 1))
    assert {observation.name for observation in batch.observations} == expected


def test_trading_title_stays_silent_off_trading():
    detector = LocalCvDetector(TRADING_CENTER_TITLE_SPEC, asset_root=ROOT)
    frames = sorted((ROOT / "screencaps/semantic/daily-quests-mailbox").rglob("*.png"))[:10]
    frames += sorted((ROOT / "screencaps/semantic/monster-wave").rglob("*.png"))[:5]
    assert len(frames) == 15
    fired = []
    for path in frames:
        frame = cv2.imread(str(path))
        if detector.detect(frame):
            fired.append(str(path.relative_to(ROOT)))
    assert fired == []
