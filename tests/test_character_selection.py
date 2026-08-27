from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.character_selection import (
    CharacterSelectionDetector,
    CharacterSelectionState,
)


def _frame(image, sequence=1):
    return FrameSnapshot(image=image, timestamp=float(sequence), sequence=sequence)


def _image_with_border(fill_fraction=1.0):
    image = np.zeros((1000, 2000, 3), dtype=np.uint8)
    detector = CharacterSelectionDetector()
    x1, x2 = 960, 1260
    y1, y2 = 640, 840
    crop = image[y1:y2, x1:x2]
    border_x = round(crop.shape[1] * detector.border_x_fraction)
    border_y = round(crop.shape[0] * detector.border_y_fraction)
    mask = np.zeros(crop.shape[:2], dtype=bool)
    mask[:, :border_x] = True
    mask[:, -border_x:] = True
    mask[:border_y, :] = True
    mask[-border_y:, :] = True
    locations = np.argwhere(mask)
    selected = locations[: round(len(locations) * fill_fraction)]
    crop[selected[:, 0], selected[:, 1]] = (0, 255, 255)
    return image


def test_no_yellow_target_outline_is_unselected():
    reading = CharacterSelectionDetector().measure(
        _frame(np.zeros((1000, 2000, 3), dtype=np.uint8))
    )

    assert reading.state is CharacterSelectionState.UNSELECTED
    assert reading.yellow_border_ratio == 0.0


def test_yellow_target_outline_is_selected():
    reading = CharacterSelectionDetector().measure(_frame(_image_with_border()))

    assert reading.state is CharacterSelectionState.SELECTED
    assert reading.yellow_border_ratio == pytest.approx(1.0)


def test_middle_score_is_uncertain_and_not_treated_as_either_state():
    reading = CharacterSelectionDetector().measure(
        _frame(_image_with_border(fill_fraction=0.03))
    )

    assert reading.state is CharacterSelectionState.UNCERTAIN
    assert 0.01 < reading.yellow_border_ratio < 0.05


def test_portrait_yellow_inside_inner_area_does_not_confirm_selection():
    image = np.zeros((1000, 2000, 3), dtype=np.uint8)
    image[690:790, 1040:1180] = (0, 255, 255)

    reading = CharacterSelectionDetector().measure(_frame(image))

    assert reading.state is CharacterSelectionState.UNSELECTED


@pytest.mark.parametrize(
    "kwargs",
    (
        {"border_x_fraction": 0},
        {"border_y_fraction": 0.5},
        {"unselected_max_ratio": 0.05, "selected_min_ratio": 0.05},
        {"yellow_hue_min": 50, "yellow_hue_max": 40},
    ),
)
def test_detector_configuration_rejects_weak_or_invalid_bounds(kwargs):
    with pytest.raises(ValueError):
        CharacterSelectionDetector(**kwargs)


def test_detector_has_no_runtime_input_or_adb_dependency():
    source = Path("bot/character_selection.py").read_text(encoding="utf-8")

    assert "ActionExecutor" not in source
    assert "from bot.adb" not in source
    assert ".tap(" not in source
    assert ".swipe(" not in source
