"""Calibration and unit tests for the Create Character (+) sentinel detector.

The evidence corpus lives in datasets/character_select_sentinel_manifest.json:
5 positives (columns 1-2, Y shifts, adjacent selection border, cross-season
account) and 10 negatives (plain card grids). The threshold must keep both
margins: every positive confirmed, every negative rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.character_select_layout import SEARCH_REGION
from bot.create_character_sentinel import (
    MATCH_THRESHOLD,
    CreateCharacterSentinelDetector,
    CreateCharacterSentinelReading,
)

ROOT = Path(__file__).resolve().parents[1]


def _manifest():
    return json.loads(
        (ROOT / "datasets/character_select_sentinel_manifest.json").read_text(
            encoding="utf-8"
        )
    )


def _snapshot(path: str, sequence: int) -> FrameSnapshot:
    image = cv2.imread(str(ROOT / path))
    assert image is not None, f"missing calibration frame: {path}"
    return FrameSnapshot(image=image, sequence=sequence, timestamp=float(sequence))


@pytest.fixture()
def detector() -> CreateCharacterSentinelDetector:
    return CreateCharacterSentinelDetector()


def test_threshold_matches_calibrated_gap():
    assert MATCH_THRESHOLD == pytest.approx(0.78)
    # Anchors measured on the evidence corpus; the threshold is their midpoint.
    assert 0.681 < MATCH_THRESHOLD < 0.882


def test_all_positives_confirmed_with_expected_column(detector):
    expected_columns = {}
    for entry in _manifest()["positives"]:
        expected_columns[entry["path"]] = entry["plus_column"]
    assert len(expected_columns) == 5
    for sequence, (path, column) in enumerate(expected_columns.items()):
        reading = detector.measure(_snapshot(path, sequence))
        assert reading.confirmed, f"sentinel missed: {path}"
        assert reading.score >= 0.882, f"weak positive score: {path}"
        assert reading.location is not None
        # Column slots: col1 ~0.555, col2 ~0.668 (pitch 0.113).
        expected_x = 0.555 + (column - 1) * 0.113
        assert reading.location[0] == pytest.approx(expected_x, abs=0.02)


def test_all_negatives_rejected_with_margin(detector):
    negatives = [entry["path"] for entry in _manifest()["negatives"]]
    assert len(negatives) == 10
    for sequence, path in enumerate(negatives, start=100):
        reading = detector.measure(_snapshot(path, sequence))
        assert not reading.confirmed, f"false sentinel: {path}"
        assert reading.location is None
        assert reading.score <= 0.681, f"weak negative margin: {path}"


def test_shifted_y_positive_still_locates(detector):
    reading = detector.measure(
        _snapshot(
            "screencaps/semantic/character_select/sentinel/plus-col2-shifted.png",
            1,
        )
    )
    assert reading.confirmed
    # Same column as the unshifted frame, clearly different row height.
    assert reading.location[0] == pytest.approx(0.668, abs=0.01)
    assert reading.location[1] == pytest.approx(0.790, abs=0.02)


def test_selected_border_adjacent_positive_still_locates(detector):
    reading = detector.measure(
        _snapshot(
            "screencaps/semantic/character_select/20260823T025400_922432Z.png",
            2,
        )
    )
    assert reading.confirmed
    assert reading.score >= 0.90


def test_synthetic_template_paste_is_confirmed():
    template = np.full((12, 12), 200, dtype=np.uint8)
    template[5:7, :] = 40
    template[:, 5:7] = 40
    local = CreateCharacterSentinelDetector(
        template=template, search_region=(0.0, 0.0, 1.0, 1.0), threshold=0.5
    )
    frame = np.full((120, 200, 3), 60, dtype=np.uint8)
    frame[50:62, 80:92] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
    reading = local.measure(FrameSnapshot(image=frame, sequence=1, timestamp=1.0))
    assert reading.confirmed
    assert reading.score == pytest.approx(1.0, abs=1e-6)
    assert reading.location[0] == pytest.approx(86 / 200, abs=0.01)
    assert reading.location[1] == pytest.approx(56 / 120, abs=0.01)


def test_plain_frame_is_rejected():
    template = np.full((12, 12), 200, dtype=np.uint8)
    template[5:7, :] = 40
    template[:, 5:7] = 40
    local = CreateCharacterSentinelDetector(
        template=template, search_region=(0.0, 0.0, 1.0, 1.0), threshold=0.5
    )
    frame = np.full((120, 200, 3), 60, dtype=np.uint8)
    reading = local.measure(FrameSnapshot(image=frame, sequence=1, timestamp=1.0))
    assert not reading.confirmed
    assert isinstance(reading, CreateCharacterSentinelReading)


def test_search_region_defaults_to_character_select_grid(detector):
    assert detector.search_region == SEARCH_REGION


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        CreateCharacterSentinelDetector(template_path="not-a-path")
    with pytest.raises(ValueError):
        CreateCharacterSentinelDetector(template=np.zeros((0, 0), dtype=np.uint8))
    with pytest.raises(ValueError):
        CreateCharacterSentinelDetector(threshold=1.5)
    with pytest.raises(ValueError):
        CreateCharacterSentinelDetector().measure(object())
