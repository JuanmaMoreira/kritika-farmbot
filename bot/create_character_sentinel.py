"""Local visual detector for the ``Create Character (+)`` sentinel tile.

The ``+`` tile is dark and translucent over a dynamic background, so a whole
tile template would bake lighting in. This detector matches only the small
``+`` cross plus its dark-interior margin and reports where it matched, so
Rotation can derive the predecessor card from the grid layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real
from pathlib import Path

import math

import cv2
import numpy as np

from bot.capture import FrameSnapshot
from bot.character_select_layout import SEARCH_REGION
from bot.geometry import (
    RelativePoint,
    RelativeRegion,
    frame_dimensions,
    normalize_relative_region,
    relative_point_to_pixel,
    relative_region_to_pixels,
)

TEMPLATE_ASSET = Path("assets/ui/character-select-create-plus-template.png")

# Calibration corpus: datasets/character_select_sentinel_manifest.json
# (5 positives across columns 1-2, Y shifts, adjacent selection border and a
# cross-season account; 10 negatives of plain card grids).
#   negative anchor (max over negatives): 0.681
#   positive anchor (min over positives): 0.882
# Threshold is the gap midpoint; both margins stay >= 0.10.
MATCH_THRESHOLD = 0.78


@dataclass(frozen=True)
class CreateCharacterSentinelReading:
    confirmed: bool
    score: float
    location: RelativePoint | None


@dataclass(frozen=True)
class CreateCharacterSentinelDetector:
    """Locate the ``+`` cross inside the Character Select grid region."""

    template_path: Path = TEMPLATE_ASSET
    search_region: RelativeRegion = SEARCH_REGION
    threshold: float = MATCH_THRESHOLD
    template: np.ndarray = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.template_path, Path):
            raise ValueError("template_path must be a pathlib.Path")
        object.__setattr__(
            self, "search_region", normalize_relative_region(self.search_region)
        )
        object.__setattr__(self, "threshold", _threshold(self.threshold))
        template = self.template
        if template is None:
            template = _load_template(self.template_path)
        else:
            template = _check_template(template)
        object.__setattr__(self, "template", template)

    def measure(self, frame: FrameSnapshot) -> CreateCharacterSentinelReading:
        if not isinstance(frame, FrameSnapshot):
            raise ValueError("frame must be FrameSnapshot")
        image = frame.image
        width, height = frame_dimensions(image)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        x1, y1, x2, y2 = relative_region_to_pixels(
            self.search_region, width, height
        )
        search = gray[y1:y2, x1:x2]
        result = cv2.matchTemplate(search, self.template, cv2.TM_CCOEFF_NORMED)
        _, score, _, best = cv2.minMaxLoc(result)
        score = float(score)
        template_height, template_width = self.template.shape
        center = (
            (x1 + best[0] + template_width / 2) / width,
            (y1 + best[1] + template_height / 2) / height,
        )
        # Keep the reported center strictly inside the frame.
        center = (min(max(center[0], 0.0), 1.0), min(max(center[1], 0.0), 1.0))
        relative_point_to_pixel(center, 1, 1)
        if score >= self.threshold:
            return CreateCharacterSentinelReading(True, score, center)
        return CreateCharacterSentinelReading(False, score, None)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_template(path: Path) -> np.ndarray:
    if not isinstance(path, Path):
        raise ValueError("template_path must be a pathlib.Path")
    absolute = path if path.is_absolute() else _repo_root() / path
    if not absolute.is_file():
        raise ValueError(f"sentinel template not found: {absolute}")
    template = cv2.imread(str(absolute), cv2.IMREAD_GRAYSCALE)
    return _check_template(template)


def _check_template(template: object) -> np.ndarray:
    if not isinstance(template, np.ndarray):
        raise ValueError("template must be a grayscale NumPy array")
    if template.ndim != 2 or template.size == 0:
        raise ValueError("template must be a non-empty 2D array")
    if template.dtype != np.uint8:
        raise ValueError("template must be uint8")
    return template.copy()


def _threshold(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("threshold must be a finite number inside [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("threshold must be a finite number inside [0, 1]")
    return result


DEFAULT_SENTINEL_DETECTOR = CreateCharacterSentinelDetector()


__all__ = (
    "MATCH_THRESHOLD",
    "TEMPLATE_ASSET",
    "CreateCharacterSentinelDetector",
    "CreateCharacterSentinelReading",
    "DEFAULT_SENTINEL_DETECTOR",
)
