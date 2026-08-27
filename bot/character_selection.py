"""Local visual postcondition for the last Character Select card."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Real

import cv2
import numpy as np

from bot.capture import FrameSnapshot
from bot.geometry import (
    RelativeRegion,
    frame_dimensions,
    normalize_relative_region,
    relative_region_to_pixels,
)


class CharacterSelectionState(str, Enum):
    UNSELECTED = "unselected"
    SELECTED = "selected"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class CharacterSelectionReading:
    state: CharacterSelectionState
    yellow_border_ratio: float


@dataclass(frozen=True)
class CharacterSelectionDetector:
    """Classify the fixed target card from its yellow selection outline.

    The outer mask deliberately excludes most portrait content. Values between
    the two calibrated thresholds are uncertain and therefore never authorize
    either success or a retry.
    """

    region: RelativeRegion = (0.48, 0.64, 0.63, 0.84)
    border_x_fraction: float = 0.16
    border_y_fraction: float = 0.18
    yellow_hue_min: int = 10
    yellow_hue_max: int = 40
    saturation_min: int = 120
    value_min: int = 180
    unselected_max_ratio: float = 0.01
    selected_min_ratio: float = 0.05

    def __post_init__(self) -> None:
        object.__setattr__(self, "region", normalize_relative_region(self.region))
        for name in ("border_x_fraction", "border_y_fraction"):
            value = _fraction(getattr(self, name), name)
            if value >= 0.5:
                raise ValueError(f"{name} must be less than 0.5")
            object.__setattr__(self, name, value)
        for name in (
            "yellow_hue_min",
            "yellow_hue_max",
            "saturation_min",
            "value_min",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if not 0 <= self.yellow_hue_min <= self.yellow_hue_max <= 179:
            raise ValueError("yellow hue bounds must be inside OpenCV HSV [0, 179]")
        if not 0 <= self.saturation_min <= 255:
            raise ValueError("saturation_min must be inside [0, 255]")
        if not 0 <= self.value_min <= 255:
            raise ValueError("value_min must be inside [0, 255]")
        unselected = _ratio(self.unselected_max_ratio, "unselected_max_ratio")
        selected = _ratio(self.selected_min_ratio, "selected_min_ratio")
        if unselected >= selected:
            raise ValueError("unselected_max_ratio must be below selected_min_ratio")
        object.__setattr__(self, "unselected_max_ratio", unselected)
        object.__setattr__(self, "selected_min_ratio", selected)

    def measure(self, frame: FrameSnapshot) -> CharacterSelectionReading:
        if not isinstance(frame, FrameSnapshot):
            raise ValueError("frame must be FrameSnapshot")
        image = frame.image
        width, height = frame_dimensions(image)
        x1, y1, x2, y2 = relative_region_to_pixels(
            self.region, width, height
        )
        crop = image[y1:y2, x1:x2]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(
            hsv,
            np.array(
                [self.yellow_hue_min, self.saturation_min, self.value_min],
                dtype=np.uint8,
            ),
            np.array([self.yellow_hue_max, 255, 255], dtype=np.uint8),
        )
        crop_height, crop_width = yellow.shape
        border_x = max(1, round(crop_width * self.border_x_fraction))
        border_y = max(1, round(crop_height * self.border_y_fraction))
        border = np.zeros_like(yellow, dtype=bool)
        border[:, :border_x] = True
        border[:, crop_width - border_x :] = True
        border[:border_y, :] = True
        border[crop_height - border_y :, :] = True
        ratio = float(np.count_nonzero(yellow[border]) / np.count_nonzero(border))
        if ratio >= self.selected_min_ratio:
            state = CharacterSelectionState.SELECTED
        elif ratio <= self.unselected_max_ratio:
            state = CharacterSelectionState.UNSELECTED
        else:
            state = CharacterSelectionState.UNCERTAIN
        return CharacterSelectionReading(
            state=state,
            yellow_border_ratio=ratio,
        )


def _fraction(value: object, name: str) -> float:
    result = _ratio(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _ratio(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite ratio inside [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{name} must be a finite ratio inside [0, 1]")
    return result


DEFAULT_CHARACTER_SELECTION_DETECTOR = CharacterSelectionDetector()


__all__ = (
    "CharacterSelectionDetector",
    "CharacterSelectionReading",
    "CharacterSelectionState",
    "DEFAULT_CHARACTER_SELECTION_DETECTOR",
)
