"""Pure visual geometry derived from the dimensions of each captured frame."""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Sequence

PixelPoint = tuple[int, int]
PixelRegion = tuple[int, int, int, int]
RelativePoint = tuple[float, float]
RelativeRegion = tuple[float, float, float, float]


def frame_dimensions(frame: object) -> tuple[int, int]:
    """Return ``(width, height)`` from an OpenCV/NumPy ``frame.shape``.

    OpenCV shapes are ordered ``(height, width, channels)``. Device metadata
    such as ``adb shell wm size`` is deliberately not consulted: it may be used
    by infrastructure for diagnostics, but is not the geometry of this frame.
    """

    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        raise ValueError("frame must expose a shape with height and width")

    height = _dimension(shape[0], "height")
    width = _dimension(shape[1], "width")
    return width, height


def relative_point_to_pixel(
    point: Sequence[Real], width: int, height: int
) -> PixelPoint:
    """Map normalized ``(x, y)`` to an addressable pixel index.

    Coordinates use floor scaling. The inclusive normalized endpoint ``1`` is
    saturated to the last valid index, so ``(1, 1)`` maps to
    ``(width - 1, height - 1)``.
    """

    width = _dimension(width, "width")
    height = _dimension(height, "height")
    x, y = _point(point)
    return (
        min(math.floor(x * width), width - 1),
        min(math.floor(y * height), height - 1),
    )


def relative_region_to_pixels(
    region: Sequence[Real], width: int, height: int
) -> PixelRegion:
    """Map normalized ``(x1, y1, x2, y2)`` to pixel slice boundaries.

    Region ends are exclusive, matching NumPy slicing. Boundaries use floor
    scaling, so the full region maps to ``(0, 0, width, height)``. Regions must
    have positive normalized area.
    """

    width = _dimension(width, "width")
    height = _dimension(height, "height")
    x1, y1, x2, y2 = normalize_relative_region(region)
    return (
        math.floor(x1 * width),
        math.floor(y1 * height),
        math.floor(x2 * width),
        math.floor(y2 * height),
    )


def normalize_relative_region(region: Sequence[Real]) -> RelativeRegion:
    """Validate and return a normalized immutable relative region."""

    return _region(region)


def _dimension(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _coordinate(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    coordinate = float(value)
    if not math.isfinite(coordinate) or not 0.0 <= coordinate <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return coordinate


def _point(point: Sequence[Real]) -> RelativePoint:
    if len(point) != 2:
        raise ValueError("point must contain exactly (x, y)")
    return _coordinate(point[0], "x"), _coordinate(point[1], "y")


def _region(region: Sequence[Real]) -> RelativeRegion:
    if len(region) != 4:
        raise ValueError("region must contain exactly (x1, y1, x2, y2)")
    x1, y1, x2, y2 = (
        _coordinate(value, name)
        for value, name in zip(region, ("x1", "y1", "x2", "y2"))
    )
    if x1 >= x2 or y1 >= y2:
        raise ValueError("region must have x1 < x2 and y1 < y2")
    return x1, y1, x2, y2
