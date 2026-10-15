"""Visual evidence without screen authority; global adoption remains blocked."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.perception import build_default_perception
from bot.perception.engine import PerceptionEngine
from bot.perception.global_loading import ACTIVITY_GLOBAL_LOADING, GlobalLoadingDetector

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('scale', [.5, 1., 1.25])
def test_acquired_arena_ring_emits_activity_without_screen_authority(scale):
    frame = cv2.imread(str(ROOT/'tests/fixtures/arena_b1/loading.png'))
    assert frame is not None
    if scale != 1:
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    batch = PerceptionEngine((GlobalLoadingDetector(),)).analyze(FrameSnapshot(frame, 10., 7))
    assert batch.sequence == 7 and batch.timestamp == 10.
    assert [o.name for o in batch.observations] == [ACTIVITY_GLOBAL_LOADING]
    # Activity alone cannot invent a BASE or a screen.loading state.
    resolved = build_default_resolver().resolve(batch)
    assert resolved.base_context is None
    assert not resolved.overlays


def test_no_detection_emits_no_negative_authority():
    assert GlobalLoadingDetector().detect(np.zeros((612, 1356, 3), np.uint8)) == ()


def test_experiment_is_excluded_from_all_default_flow_perception():
    assert not any(isinstance(d, GlobalLoadingDetector) for d in build_default_perception().detectors)


def test_white_scene_cannot_be_mistaken_for_cyan_loading():
    assert GlobalLoadingDetector().detect(np.full((612, 1356, 3), 255, np.uint8)) == ()
