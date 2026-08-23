"""Legacy visual matching helpers with no device or capture ownership.

This module is deliberately transitional. It preserves the useful, pure
OpenCV knowledge from the legacy ``screen.py`` while the perception layer is
redesigned in Phase 2. Callers must provide the frame explicitly; ADB, scrcpy
lifecycle and input commands belong to the 0.2 infrastructure.
"""

from __future__ import annotations

import os
from numbers import Real

import cv2
import numpy as np

from bot.geometry import frame_dimensions, relative_region_to_pixels


def find_image_on_screen(
    screenshot_img: np.ndarray,
    template_path: str | os.PathLike[str],
    region: tuple[float, float, float, float] | None = None,
    threshold: float = 0.8,
) -> tuple[int, int] | None:
    """Return the center of the best template match in an explicit BGR frame.

    ``region`` uses normalized frame coordinates. Templates are matched at
    their stored size; selecting and scaling visual assets is a perception
    concern intentionally deferred to Phase 2.
    """

    search, template, offset_x, offset_y = _prepare_match(
        screenshot_img, template_path, region
    )
    if not _template_fits(search, template):
        return None

    score_map = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_score, _, max_location = cv2.minMaxLoc(score_map)
    if max_score < _threshold(threshold):
        return None

    template_height, template_width = template.shape
    return (
        max_location[0] + offset_x + template_width // 2,
        max_location[1] + offset_y + template_height // 2,
    )


def find_all_on_screen(
    screenshot_img: np.ndarray,
    template_path: str | os.PathLike[str],
    region: tuple[float, float, float, float] | None = None,
    threshold: float = 0.8,
) -> list[tuple[int, int]]:
    """Return non-overlapping template centers in an explicit BGR frame.

    Candidates are considered by descending confidence and overlapping
    responses are suppressed. Results are ordered top-to-bottom, then left-
    to-right, matching the useful ordering of the legacy implementation.
    """

    search, template, offset_x, offset_y = _prepare_match(
        screenshot_img, template_path, region
    )
    if not _template_fits(search, template):
        return []

    score_map = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    y_locations, x_locations = np.where(score_map >= _threshold(threshold))
    template_height, template_width = template.shape
    candidates = sorted(
        (
            (float(score_map[y, x]), int(x), int(y))
            for x, y in zip(x_locations, y_locations)
        ),
        reverse=True,
    )

    selected: list[tuple[int, int]] = []
    for _, x, y in candidates:
        if any(
            abs(x - selected_x) < template_width
            and abs(y - selected_y) < template_height
            for selected_x, selected_y in selected
        ):
            continue
        selected.append((x, y))

    centers = [
        (
            x + offset_x + template_width // 2,
            y + offset_y + template_height // 2,
        )
        for x, y in selected
    ]
    centers.sort(key=lambda point: (point[1], point[0]))
    return centers


def _prepare_match(
    screenshot_img: np.ndarray,
    template_path: str | os.PathLike[str],
    region: tuple[float, float, float, float] | None,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    if not isinstance(screenshot_img, np.ndarray) or screenshot_img.ndim != 3:
        raise ValueError("screenshot_img must be an HxWxC NumPy frame")
    width, height = frame_dimensions(screenshot_img)

    screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
    template = cv2.imread(os.fspath(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(f"Template image not found: {template_path}")

    if region is None:
        return screenshot_gray, template, 0, 0

    x1, y1, x2, y2 = relative_region_to_pixels(region, width, height)
    return screenshot_gray[y1:y2, x1:x2], template, x1, y1


def _template_fits(search: np.ndarray, template: np.ndarray) -> bool:
    return (
        search.size > 0
        and template.size > 0
        and template.shape[0] <= search.shape[0]
        and template.shape[1] <= search.shape[1]
    )


def _threshold(value: Real) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("threshold must be a real number in [0, 1]")
    result = float(value)
    if not np.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("threshold must be in [0, 1]")
    return result
