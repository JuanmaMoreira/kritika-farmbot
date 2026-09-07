"""Shared Character Select grid geometry (fixed 3-column row-major layout).

The grid holds character cards in reading order (left to right, top to
bottom) followed by exactly one ``Create Character (+)`` tile. Rotation
locates the ``+`` tile and derives its predecessor from this layout, so no
caller may hardcode card positions or count characters.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from bot.geometry import (
    RelativePoint,
    RelativeRegion,
    normalize_relative_region,
)

COLUMN_COUNT = 3

# Tile centers measured from live evidence (sentinel cross detections at
# x=0.555 col1 / x=0.668 col2 plus the red-corner lattice). The cross is
# centered in its tile, so detection x directly marks tile centers.
COLUMN_CENTERS: tuple[float, float, float] = (0.555, 0.668, 0.781)
COLUMN_PITCH = 0.113

# Vertical pitch between card rows from the red-corner lattice
# (0.360 / 0.513 / 0.665 across mid-grid evidence).
ROW_PITCH = 0.152

# Half extents of one card tile (tile ~0.112 wide, ~0.126 tall).
TILE_HALF_WIDTH = 0.056
TILE_HALF_HEIGHT = 0.063

# Sentinel search area: covers all three columns with tile margin, from the
# first card row down to the bottom banner. Bottom-row tiles may be partially
# covered and still match (Fase 1 cond02).
SEARCH_REGION: RelativeRegion = (0.485, 0.19, 0.86, 0.83)

# A detection must fall this close to a column center to be assignable.
COLUMN_TOLERANCE = 0.04


def sentinel_column(location: RelativePoint) -> int:
    """Return the 1-based grid column of a sentinel detection center."""

    x, _ = _point(location)
    best = min(
        range(COLUMN_COUNT), key=lambda index: abs(x - COLUMN_CENTERS[index])
    )
    if abs(x - COLUMN_CENTERS[best]) > COLUMN_TOLERANCE:
        raise ValueError(
            f"sentinel x={x:.3f} is outside every grid column "
            f"(centers {COLUMN_CENTERS})"
        )
    return best + 1


def predecessor_center(sentinel_location: RelativePoint) -> RelativePoint:
    """Return the tap center of the card immediately before ``+``.

    Column 2/3: card to the left on the same row. Column 1: column 3 of the
    row above. The Y always comes from the live detection, never from a
    fixed "last character" coordinate.
    """

    x, y = _point(sentinel_location)
    column = sentinel_column((x, y))
    if column == 1:
        return (COLUMN_CENTERS[2], y - ROW_PITCH)
    return (COLUMN_CENTERS[column - 2], y)


def tile_box(center: RelativePoint) -> RelativeRegion:
    """Return the card-sized box around a tile center (e.g. selection ROI)."""

    x, y = _point(center)
    return normalize_relative_region(
        (
            x - TILE_HALF_WIDTH,
            y - TILE_HALF_HEIGHT,
            x + TILE_HALF_WIDTH,
            y + TILE_HALF_HEIGHT,
        )
    )


def _point(value: Sequence[Real]) -> RelativePoint:
    try:
        x, y = value
    except (TypeError, ValueError) as error:
        raise ValueError("point must be an (x, y) pair") from error
    for name, coordinate in (("x", x), ("y", y)):
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, Real)
            or not math.isfinite(coordinate)
            or not 0.0 <= coordinate <= 1.0
        ):
            raise ValueError(f"{name} must be a finite number inside [0, 1]")
    return (float(x), float(y))


__all__ = (
    "COLUMN_CENTERS",
    "COLUMN_COUNT",
    "COLUMN_PITCH",
    "COLUMN_TOLERANCE",
    "ROW_PITCH",
    "SEARCH_REGION",
    "TILE_HALF_HEIGHT",
    "TILE_HALF_WIDTH",
    "predecessor_center",
    "sentinel_column",
    "tile_box",
)
