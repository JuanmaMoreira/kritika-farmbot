"""Geometry tests for the Character Select 3-column grid layout."""

from __future__ import annotations

import pytest

from bot.character_select_layout import (
    COLUMN_CENTERS,
    COLUMN_COUNT,
    ROW_PITCH,
    predecessor_center,
    sentinel_column,
    tile_box,
)


def test_three_column_slots():
    assert COLUMN_COUNT == 3
    assert len(COLUMN_CENTERS) == 3
    assert list(COLUMN_CENTERS) == sorted(COLUMN_CENTERS)


def test_live_col2_detection_assigns_column_two():
    assert sentinel_column((0.6676, 0.7484)) == 2
    assert sentinel_column((0.6676, 0.7900)) == 2


def test_live_col1_detection_assigns_column_one():
    assert sentinel_column((0.5551, 0.7484)) == 1


def test_far_outside_grid_is_invalid():
    with pytest.raises(ValueError):
        sentinel_column((0.30, 0.75))
    with pytest.raises(ValueError):
        sentinel_column((0.95, 0.75))


def test_col2_sentinel_predecessor_is_col1_same_row():
    target = predecessor_center((0.6676, 0.7484))
    assert target[0] == pytest.approx(COLUMN_CENTERS[0])
    assert target[1] == pytest.approx(0.7484)


def test_col3_sentinel_predecessor_is_col2_same_row():
    target = predecessor_center((COLUMN_CENTERS[2], 0.60))
    assert target[0] == pytest.approx(COLUMN_CENTERS[1])
    assert target[1] == pytest.approx(0.60)


def test_col1_sentinel_predecessor_is_col3_previous_row():
    target = predecessor_center((0.5551, 0.7484))
    assert target[0] == pytest.approx(COLUMN_CENTERS[2])
    assert target[1] == pytest.approx(0.7484 - ROW_PITCH)


def test_predecessor_y_follows_variable_sentinel_y():
    low = predecessor_center((COLUMN_CENTERS[1], 0.79))
    high = predecessor_center((COLUMN_CENTERS[1], 0.70))
    assert low[1] == pytest.approx(0.79)
    assert high[1] == pytest.approx(0.70)
    assert low[1] - high[1] == pytest.approx(0.09)


def test_predecessor_is_independent_of_character_count():
    # Same sentinel position always yields the same target: no counting.
    first = predecessor_center((COLUMN_CENTERS[1], 0.7484))
    second = predecessor_center((COLUMN_CENTERS[1], 0.7484))
    assert first == second


def test_tile_box_is_card_sized_and_contains_center():
    center = (COLUMN_CENTERS[1], 0.7484)
    x1, y1, x2, y2 = tile_box(center)
    assert x1 < center[0] < x2
    assert y1 < center[1] < y2
    assert (x2 - x1) == pytest.approx(0.112)
    assert (y2 - y1) == pytest.approx(0.126)


def test_invalid_points_rejected():
    with pytest.raises(ValueError):
        predecessor_center((2.0, 0.5))
    with pytest.raises(ValueError):
        tile_box(("x", 0.5))
