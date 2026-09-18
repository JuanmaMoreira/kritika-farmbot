"""Incremental Treasure Center perception evaluation over the HIL corpus."""

import json
from pathlib import Path

import cv2

from bot.perception import (
    TREASURE_SCOPE,
    TREASURE_SCOPE_SPEC_NAMES,
    build_default_perception,
    build_treasure_perception,
    select_detectors,
)
from bot.perception.local_cv import LocalCvDetector
from bot.perception.treasure_center import (
    TREASURE_CENTER_SPECS,
    TREASURE_TITLE_SPEC,
    TreasureContentDetector,
)

ROOT = Path(__file__).resolve().parent.parent
VOCABULARY = {
    "landmark.treasure_title",
    "indicator.treasure_gold_key_selector",
    "indicator.treasure_gold_key_repeat",
    "indicator.treasure_karat_base",
    "indicator.treasure_karat_repeat",
    "indicator.treasure_selector_popup",
    "indicator.treasure_result",
}


def _load_entries():
    payload = json.loads(
        (ROOT / "datasets/treasure_center_semantic_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return [
        entry for entry in payload["entries"] if entry["review_status"] == "confirmed"
    ]


def test_treasure_detectors_match_curated_labels_without_errors():
    title = LocalCvDetector(TREASURE_TITLE_SPEC, asset_root=ROOT)
    content = TreasureContentDetector(asset_root=ROOT)
    wrong = []
    for entry in _load_entries():
        frame = cv2.imread(str(ROOT / entry["path"]))
        assert frame is not None, entry["path"]
        found = {
            observation.name
            for observation in (
                *title.detect(frame),
                *content.detect(frame),
            )
        }
        assert found <= VOCABULARY, (entry["path"], found - VOCABULARY)
        if entry["base_context"] == "screen.treasure":
            expected = set(entry["observations"])
            if found != expected:
                wrong.append((entry["path"], sorted(expected), sorted(found)))
        else:
            # Cross-screen silence: no Treasure vocabulary may leak onto
            # foreign screens (their own labels live in their manifests).
            if found:
                wrong.append((entry["path"], [], sorted(found)))
    assert wrong == []


def test_treasure_title_calibration_separates_states_from_foreign_screens():
    detector = LocalCvDetector(TREASURE_TITLE_SPEC, asset_root=ROOT)
    treasure_scores = []
    foreign_scores = []
    for entry in _load_entries():
        frame = cv2.imread(str(ROOT / entry["path"]))
        score = detector.measure(frame).semantic_confidence
        if entry["base_context"] == "screen.treasure":
            treasure_scores.append(score)
        else:
            foreign_scores.append(score)
    assert min(treasure_scores) == 1.0
    assert max(foreign_scores) == 0.0


def test_treasure_scope_holds_title_plus_content_detector():
    assert TREASURE_SCOPE_SPEC_NAMES == frozenset(
        {"landmark.treasure_title"}
    )
    assert TREASURE_SCOPE.name == "treasure"
    assert TREASURE_SCOPE.spec_names == TREASURE_SCOPE_SPEC_NAMES
    assert TREASURE_SCOPE.specialized_types == (TreasureContentDetector,)


def test_treasure_standalone_perception_has_two_detectors():
    engine = build_treasure_perception(ROOT)
    assert len(engine.detectors) == 2


def test_treasure_title_spec_is_promoted_to_default_engine():
    assert TREASURE_CENTER_SPECS == (TREASURE_TITLE_SPEC,)
    engine = build_default_perception(ROOT)
    names = {
        detector.spec.name
        for detector in engine.detectors
        if isinstance(detector, LocalCvDetector)
    }
    assert TREASURE_TITLE_SPEC.name in names


def test_treasure_content_detector_needs_no_other_assets():
    detector = TreasureContentDetector(asset_root=ROOT)
    assert len(detector.asset_paths) == 3
    for path in detector.asset_paths:
        assert Path(path).is_file()
