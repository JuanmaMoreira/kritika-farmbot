import argparse

import pytest

from tools.world_boss_live_acquisition import (
    _non_negative_float,
    _positive_int,
    _relative_coordinate,
    _safe_label,
    parse_args,
)


def test_capture_arguments_are_labeled_and_bounded():
    args = parse_args(
        ["capture", "--label", "world-boss-main", "--count", "4", "--interval", "0"]
    )

    assert args.command == "capture"
    assert args.label == "world-boss-main"
    assert args.count == 4
    assert args.interval == 0


def test_tap_and_swipe_coordinates_remain_explicit():
    tap = parse_args(
        ["tap", "--label", "open-boss", "--x", "0.25", "--y", "0.75"]
    )
    swipe = parse_args(
        [
            "swipe",
            "--label",
            "probe-scroll",
            "--x",
            "0.5",
            "--y",
            "0.8",
            "--x2",
            "0.5",
            "--y2",
            "0.2",
        ]
    )

    assert (tap.x, tap.y) == (0.25, 0.75)
    assert (swipe.x, swipe.y, swipe.x2, swipe.y2) == (0.5, 0.8, 0.5, 0.2)


@pytest.mark.parametrize(
    ("converter", "value"),
    [
        (_safe_label, "World Boss"),
        (_relative_coordinate, "-0.01"),
        (_relative_coordinate, "1.01"),
        (_positive_int, "0"),
        (_non_negative_float, "-1"),
    ],
)
def test_invalid_probe_inputs_are_rejected(converter, value):
    with pytest.raises(argparse.ArgumentTypeError):
        converter(value)
