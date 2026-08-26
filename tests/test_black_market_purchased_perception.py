from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.geometry import relative_region_to_pixels
from bot.observations import ObservationSource
from bot.perception import (
    BLACK_MARKET_GOLD_ASSET,
    BLACK_MARKET_PURCHASED_ASSETS,
    BLACK_MARKET_PURCHASED_CALIBRATION,
    BLACK_MARKET_PURCHASED_CONFIDENCE_THRESHOLD,
    BLACK_MARKET_PURCHASED_OBSERVATION,
    BLACK_MARKET_PURCHASED_SLOT_REGIONS,
    BlackMarketPurchasedDetector,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _asset(path, mode=cv2.IMREAD_COLOR):
    image = cv2.imread(str(REPOSITORY_ROOT / path), mode)
    assert image is not None
    return image


def _frame_with_purchased(*slot_indices):
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    asset = _asset(BLACK_MARKET_PURCHASED_ASSETS[0])
    height, width = asset.shape[:2]
    for slot_index in slot_indices:
        x1, y1, x2, y2 = relative_region_to_pixels(
            BLACK_MARKET_PURCHASED_SLOT_REGIONS[slot_index], 2712, 1224
        )
        assert width <= x2 - x1 and height <= y2 - y1
        frame[y1 : y1 + height, x1 : x1 + width] = asset
    return frame


@pytest.mark.parametrize("slot_index", range(10))
def test_purchased_asset_can_be_detected_in_every_slot(slot_index):
    detector = BlackMarketPurchasedDetector(asset_root=REPOSITORY_ROOT)

    observations = detector.detect(_frame_with_purchased(slot_index))

    assert len(observations) == 1
    assert observations[0].name == BLACK_MARKET_PURCHASED_OBSERVATION
    assert observations[0].value == slot_index
    assert observations[0].confidence == 1.0
    assert observations[0].source is ObservationSource.LOCAL_CV


def test_purchased_detector_emits_multiple_slots_in_row_major_order():
    detector = BlackMarketPurchasedDetector(asset_root=REPOSITORY_ROOT)

    observations = detector.detect(_frame_with_purchased(2, 5, 8))

    assert tuple(item.value for item in observations) == (2, 5, 8)


@pytest.mark.parametrize(
    "panel",
    (
        np.full((40, 240, 3), (0, 0, 220), dtype=np.uint8),  # KARATS-like red
        np.full((40, 240, 3), (30, 140, 220), dtype=np.uint8),  # Video-like orange
    ),
)
def test_flat_karats_or_video_like_panel_is_not_purchased(panel):
    detector = BlackMarketPurchasedDetector(asset_root=REPOSITORY_ROOT)
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    x1, y1, _, _ = relative_region_to_pixels(
        BLACK_MARKET_PURCHASED_SLOT_REGIONS[4], 2712, 1224
    )
    frame[y1 : y1 + 40, x1 : x1 + 240] = panel

    assert detector.detect(frame) == ()


def test_gold_asset_inside_price_panel_is_not_purchased():
    detector = BlackMarketPurchasedDetector(asset_root=REPOSITORY_ROOT)
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    gold = _asset(BLACK_MARKET_GOLD_ASSET)
    x1, y1, _, _ = relative_region_to_pixels(
        BLACK_MARKET_PURCHASED_SLOT_REGIONS[6], 2712, 1224
    )
    frame[y1 : y1 + gold.shape[0], x1 : x1 + gold.shape[1]] = gold

    assert detector.detect(frame) == ()


def test_purchased_detector_preloads_both_native_renderings_once():
    loader = Mock(wraps=cv2.imread)
    detector = BlackMarketPurchasedDetector(
        asset_root=REPOSITORY_ROOT, template_loader=loader
    )

    detector.detect(_frame_with_purchased(3))
    detector.detect(_frame_with_purchased(8))

    assert loader.call_count == 2
    assert detector.template_shapes == ((40, 240), (40, 240))


def test_purchased_detector_uses_evaluated_global_gap():
    assert BLACK_MARKET_PURCHASED_CALIBRATION.negative_anchor == pytest.approx(
        0.557578444480896
    )
    assert BLACK_MARKET_PURCHASED_CALIBRATION.positive_anchor == pytest.approx(
        0.8815832138061523
    )
    assert BLACK_MARKET_PURCHASED_CONFIDENCE_THRESHOLD == 0.80
