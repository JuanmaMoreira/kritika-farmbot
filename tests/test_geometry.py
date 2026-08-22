import numpy as np
import pytest

from bot.geometry import (
    frame_dimensions,
    relative_point_to_pixel,
    relative_region_to_pixels,
)


def test_frame_dimensions_historical_landscape_frame():
    frame = np.empty((1224, 2712, 3), dtype=np.uint8)

    assert frame_dimensions(frame) == (2712, 1224)


def test_frame_dimensions_other_landscape_resolution():
    frame = np.empty((1080, 1920, 3), dtype=np.uint8)

    assert frame_dimensions(frame) == (1920, 1080)


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((0.0, 0.0), (0, 0)),
        ((1.0, 1.0), (2711, 1223)),
        ((0.5, 0.5), (1356, 612)),
        ((0.333, 0.666), (903, 815)),
    ],
)
def test_relative_point_to_pixel(point, expected):
    assert relative_point_to_pixel(point, 2712, 1224) == expected


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        ((0.0, 0.0, 1.0, 1.0), (0, 0, 1920, 1080)),
        ((0.25, 0.25, 0.75, 0.75), (480, 270, 1440, 810)),
        ((0.1, 0.2, 0.4, 0.6), (192, 216, 768, 648)),
    ],
)
def test_relative_region_to_pixels(region, expected):
    assert relative_region_to_pixels(region, 1920, 1080) == expected


@pytest.mark.parametrize(
    "point",
    [
        (-0.01, 0.5),
        (1.01, 0.5),
        (0.5, -0.01),
        (0.5, 1.01),
        (float("nan"), 0.5),
    ],
)
def test_relative_point_rejects_invalid_coordinates(point):
    with pytest.raises(ValueError):
        relative_point_to_pixel(point, 1920, 1080)


@pytest.mark.parametrize(
    "region",
    [
        (-0.01, 0.0, 1.0, 1.0),
        (0.0, 0.0, 1.01, 1.0),
        (0.8, 0.0, 0.2, 1.0),
        (0.0, 0.8, 1.0, 0.2),
        (0.5, 0.0, 0.5, 1.0),
        (0.0, 0.5, 1.0, 0.5),
    ],
)
def test_relative_region_rejects_invalid_or_inverted_regions(region):
    with pytest.raises(ValueError):
        relative_region_to_pixels(region, 1920, 1080)


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 1080), (-1, 1080), (1920, 0), (1920, -1)],
)
def test_geometry_rejects_invalid_dimensions(width, height):
    with pytest.raises(ValueError):
        relative_point_to_pixel((0.5, 0.5), width, height)


@pytest.mark.parametrize("shape", [(0, 1920, 3), (1080, 0, 3), (1920,)])
def test_frame_dimensions_rejects_invalid_shapes(shape):
    class Frame:
        pass

    frame = Frame()
    frame.shape = shape

    with pytest.raises(ValueError):
        frame_dimensions(frame)
