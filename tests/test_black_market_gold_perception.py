from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.geometry import relative_region_to_pixels
from bot.observations import ObservationSource
from bot.perception import (
    BLACK_MARKET_GOLD_ASSET,
    BLACK_MARKET_GOLD_CALIBRATION,
    BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD,
    BLACK_MARKET_GOLD_OBSERVATION,
    BLACK_MARKET_GOLD_SLOT_REGIONS,
    BLACK_MARKET_GRID_COLUMNS,
    BLACK_MARKET_GRID_ROWS,
    BLACK_MARKET_SLOT_COUNT,
    BlackMarketGoldDetector,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _asset() -> np.ndarray:
    image = cv2.imread(
        str(REPOSITORY_ROOT / BLACK_MARKET_GOLD_ASSET), cv2.IMREAD_COLOR
    )
    assert image is not None
    return image


def _frame_with_gold(*slot_indices: int) -> np.ndarray:
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    asset = _asset()
    height, width = asset.shape[:2]
    for slot_index in slot_indices:
        x1, y1, x2, y2 = relative_region_to_pixels(
            BLACK_MARKET_GOLD_SLOT_REGIONS[slot_index],
            frame.shape[1],
            frame.shape[0],
        )
        assert width <= x2 - x1
        assert height <= y2 - y1
        frame[y1 : y1 + height, x1 : x1 + width] = asset
    return frame


def test_black_market_grid_is_fixed_row_major_five_by_two():
    assert BLACK_MARKET_GRID_ROWS == 5
    assert BLACK_MARKET_GRID_COLUMNS == 2
    assert BLACK_MARKET_SLOT_COUNT == 10
    assert len(BLACK_MARKET_GOLD_SLOT_REGIONS) == 10
    assert len(set(BLACK_MARKET_GOLD_SLOT_REGIONS)) == 10

    for index, region in enumerate(BLACK_MARKET_GOLD_SLOT_REGIONS):
        expected_row = index // 2
        expected_column = index % 2
        assert region[0] == pytest.approx((0.4355, 0.7459)[expected_column])
        assert region[1] == pytest.approx(0.285 + expected_row * 0.1328)


@pytest.mark.parametrize("slot_index", range(BLACK_MARKET_SLOT_COUNT))
def test_gold_asset_can_be_detected_independently_in_every_slot(slot_index):
    detector = BlackMarketGoldDetector(asset_root=REPOSITORY_ROOT)

    observations = detector.detect(_frame_with_gold(slot_index))

    assert len(observations) == 1
    observation = observations[0]
    assert observation.name == BLACK_MARKET_GOLD_OBSERVATION
    assert observation.value == slot_index
    assert observation.confidence == 1.0
    assert observation.source is ObservationSource.LOCAL_CV
    assert observation.region == BLACK_MARKET_GOLD_SLOT_REGIONS[slot_index]


def test_gold_detector_emits_multiple_slots_in_row_major_order():
    detector = BlackMarketGoldDetector(asset_root=REPOSITORY_ROOT)

    observations = detector.detect(_frame_with_gold(0, 4, 7, 9))

    assert tuple(item.value for item in observations) == (0, 4, 7, 9)


def test_gold_detector_treats_every_non_confident_slot_as_ineligible():
    detector = BlackMarketGoldDetector(asset_root=REPOSITORY_ROOT)
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)

    assert detector.detect(frame) == ()
    readings = detector.measure(frame)
    assert len(readings) == 10
    assert tuple(item.slot_index for item in readings) == tuple(range(10))
    assert tuple((item.row, item.column) for item in readings) == tuple(
        (index // 2, index % 2) for index in range(10)
    )


def test_gold_detector_preloads_the_legacy_asset_once():
    loader = Mock(wraps=cv2.imread)
    detector = BlackMarketGoldDetector(
        asset_root=REPOSITORY_ROOT, template_loader=loader
    )

    detector.detect(_frame_with_gold(2))
    detector.detect(_frame_with_gold(3))

    loader.assert_called_once_with(
        str((REPOSITORY_ROOT / BLACK_MARKET_GOLD_ASSET).resolve()),
        cv2.IMREAD_GRAYSCALE,
    )
    assert detector.template_shape == (55, 57)


def test_gold_detector_uses_conservative_empirical_gap():
    assert BLACK_MARKET_GOLD_CALIBRATION.negative_anchor == pytest.approx(
        0.5731779932975769
    )
    assert BLACK_MARKET_GOLD_CALIBRATION.positive_anchor == pytest.approx(
        0.9343795776367188
    )
    assert BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD == 0.80


@pytest.mark.parametrize(
    "frame",
    (
        np.zeros((10, 10), dtype=np.uint8),
        np.zeros((10, 10, 3), dtype=np.float32),
        np.zeros((0, 10, 3), dtype=np.uint8),
    ),
)
def test_gold_detector_rejects_invalid_frames(frame):
    detector = BlackMarketGoldDetector(asset_root=REPOSITORY_ROOT)

    with pytest.raises(ValueError, match="frame must be"):
        detector.detect(frame)
