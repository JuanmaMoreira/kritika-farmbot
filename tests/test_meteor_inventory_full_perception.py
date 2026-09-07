from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_METEOR_INVENTORY_FULL,
    SCREEN_WORLD_BOSS,
    SEMANTIC_CONFIDENCE_THRESHOLD,
    build_default_resolver,
)
from bot.perception import (
    METEOR_INVENTORY_FULL_PROMPT_SPEC,
    SOCKET_INVENTORY_FULL_PROMPT_SPEC,
    LocalCvDetector,
    build_default_perception,
)


ROOT = Path(__file__).resolve().parents[1]
METEOR_POSITIVES = (
    ROOT / "screencaps/semantic/world_boss/meteor_full/20260906T000119_016095Z_01.png",
    ROOT / "screencaps/semantic/world_boss/meteor_full/20260906T000119_491865Z_02.png",
)
# Closest visual neighbour shares the second line verbatim; equipment uses a
# different 4-line prompt with X close; battle-after frames prove popup
# disappearance; lobby proves no emission off-caller.
METEOR_NEGATIVES = (
    ROOT / "screencaps/semantic/world_boss/inventory_full/20260828T114407_020995Z_01.png",
    ROOT / "screencaps/semantic/world_boss/inventory_full/20260828T114407_472240Z_02.png",
    ROOT / "screencaps/semantic/world_boss/bag_full/20260828T202141_500454Z_01.png",
    ROOT / "screencaps/semantic/world_boss/meteor_full_after/20260906T000701_955529Z_01.png",
    ROOT / "screencaps/semantic/lobby/20260823T025455_304538Z.png",
)


def _read(path):
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert frame is not None, path
    return frame


def test_meteor_positives_match_manifest_range_and_emit():
    detector = LocalCvDetector(METEOR_INVENTORY_FULL_PROMPT_SPEC, asset_root=ROOT)
    scores = [detector.measure(_read(path)).raw_match_score for path in METEOR_POSITIVES]

    assert min(scores) == pytest.approx(0.992478, abs=0.005)
    assert max(scores) == pytest.approx(0.999972, abs=0.005)
    assert all(detector.detect(_read(path)) for path in METEOR_POSITIVES)


@pytest.mark.parametrize("path", METEOR_NEGATIVES)
def test_closest_prompts_and_clean_frames_do_not_emit_meteor(path):
    detector = LocalCvDetector(METEOR_INVENTORY_FULL_PROMPT_SPEC, asset_root=ROOT)

    assert detector.detect(_read(path)) == ()


def test_socket_prompt_is_strongest_reviewed_negative_below_emit_gap():
    meteor = LocalCvDetector(METEOR_INVENTORY_FULL_PROMPT_SPEC, asset_root=ROOT)
    socket_frame = _read(METEOR_NEGATIVES[0])

    raw = meteor.measure(socket_frame).raw_match_score

    assert raw == pytest.approx(0.762491, abs=0.01)
    assert raw < meteor.spec.calibration.negative_anchor + 0.01


def test_socket_detector_stays_below_catalog_threshold_on_meteor_frames():
    from bot.catalog import SEMANTIC_CONFIDENCE_THRESHOLD

    socket = LocalCvDetector(SOCKET_INVENTORY_FULL_PROMPT_SPEC, asset_root=ROOT)

    for path in METEOR_POSITIVES:
        detected = socket.detect(_read(path))
        assert detected == () or all(
            obs.confidence < SEMANTIC_CONFIDENCE_THRESHOLD for obs in detected
        )


def test_meteor_calibration_boundary_matches_catalog_threshold():
    calibration = METEOR_INVENTORY_FULL_PROMPT_SPEC.calibration
    raw_threshold = calibration.negative_anchor + SEMANTIC_CONFIDENCE_THRESHOLD * (
        calibration.positive_anchor - calibration.negative_anchor
    )

    assert raw_threshold == pytest.approx(0.9464682, abs=1e-4)
    assert calibration.confidence(raw_threshold) == pytest.approx(
        SEMANTIC_CONFIDENCE_THRESHOLD
    )
    assert calibration.confidence(raw_threshold - 1e-6) < SEMANTIC_CONFIDENCE_THRESHOLD


def test_production_pipeline_resolves_meteor_over_world_boss():
    frame = _read(METEOR_POSITIVES[0])
    engine = build_default_perception(ROOT)
    snapshot = FrameSnapshot(frame, timestamp=1.0, sequence=1)

    state = build_default_resolver().resolve(engine.analyze(snapshot))

    assert state.base_context == SCREEN_WORLD_BOSS
    assert state.overlays == (POPUP_METEOR_INVENTORY_FULL,)


def test_production_pipeline_resolves_meteor_after_frame_as_clean_world_boss():
    frame = _read(
        ROOT / "screencaps/semantic/world_boss/meteor_full_after/20260906T000701_955529Z_01.png"
    )
    engine = build_default_perception(ROOT)
    snapshot = FrameSnapshot(frame, timestamp=1.0, sequence=1)

    state = build_default_resolver().resolve(engine.analyze(snapshot))

    assert state.base_context == SCREEN_WORLD_BOSS
    assert state.overlays == ()
