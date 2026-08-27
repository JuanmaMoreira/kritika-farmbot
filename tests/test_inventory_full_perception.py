from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_INVENTORY_FULL,
    SCREEN_BLACK_MARKET,
    SEMANTIC_CONFIDENCE_THRESHOLD,
    build_default_resolver,
)
from bot.perception import (
    INVENTORY_FULL_OK_BUTTON_SPEC,
    LocalCvDetector,
    build_default_perception,
)


ROOT = Path(__file__).resolve().parents[1]
POSITIVE_DIR = (
    ROOT
    / "screencaps/semantic/inventory_full/20260827T075832_116844Z"
)
NEGATIVES = (
    ROOT
    / "screencaps/semantic/workbench/20260823T061544_647270Z-11461340/"
    "frame-00001706.png",
    ROOT
    / "screencaps/semantic/workbench/20260823T064721_367331Z-addb7117/"
    "frame-00000905.png",
    ROOT
    / "screencaps/semantic/black_market_currency/20260825T204903_103690Z.png",
    ROOT / "screencaps/semantic/lobby/20260823T025455_304538Z.png",
    ROOT / "screencaps/batch/20260402_172143_642136.png",
)


def _read(path):
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert frame is not None, path
    return frame


def test_real_inventory_full_frames_are_detected_without_message_text():
    detector = LocalCvDetector(INVENTORY_FULL_OK_BUTTON_SPEC, asset_root=ROOT)
    scores = [
        detector.measure(_read(path)).raw_match_score
        for path in sorted(POSITIVE_DIR.glob("frame-*.png"))
    ]

    assert len(scores) == 6
    assert min(scores) == pytest.approx(0.9836453795433044)
    assert max(scores) == pytest.approx(0.9999406933784485)
    assert all(detector.detect(_read(path)) for path in POSITIVE_DIR.glob("frame-*.png"))


@pytest.mark.parametrize("path", NEGATIVES)
def test_relevant_non_inventory_frames_do_not_emit_inventory_full(path):
    detector = LocalCvDetector(INVENTORY_FULL_OK_BUTTON_SPEC, asset_root=ROOT)

    assert detector.detect(_read(path)) == ()


def test_inventory_full_calibration_boundary_matches_catalog_threshold():
    calibration = INVENTORY_FULL_OK_BUTTON_SPEC.calibration
    raw_threshold = calibration.negative_anchor + SEMANTIC_CONFIDENCE_THRESHOLD * (
        calibration.positive_anchor - calibration.negative_anchor
    )

    assert raw_threshold == pytest.approx(0.9658956527709961)
    assert calibration.confidence(raw_threshold) == pytest.approx(
        SEMANTIC_CONFIDENCE_THRESHOLD
    )
    assert calibration.confidence(raw_threshold - 1e-6) < (
        SEMANTIC_CONFIDENCE_THRESHOLD
    )


def test_production_pipeline_resolves_inventory_full_only_with_black_market_gate():
    frame = _read(next(POSITIVE_DIR.glob("frame-*.png")))
    engine = build_default_perception(ROOT)
    snapshot = FrameSnapshot(frame, timestamp=1.0, sequence=1)

    state = build_default_resolver().resolve(engine.analyze(snapshot))

    assert state.base_context == SCREEN_BLACK_MARKET
    assert state.overlays == (POPUP_INVENTORY_FULL,)
