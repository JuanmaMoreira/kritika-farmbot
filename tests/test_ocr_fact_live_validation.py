import argparse

import pytest

from tools.ocr_fact_live_validation import (
    _non_negative_float,
    _positive_float,
    _positive_int,
    parse_args,
)


def test_live_validation_selects_fact_and_bounded_sampling():
    args = parse_args(
        ["timer", "--reads", "5", "--timeout", "3", "--interval", "1"]
    )

    assert args.fact == "timer"
    assert args.reads == 5
    assert args.timeout == 3.0
    assert args.interval == 1.0


@pytest.mark.parametrize(
    ("converter", "value"),
    [
        (_positive_int, "0"),
        (_positive_float, "0"),
        (_non_negative_float, "-0.1"),
    ],
)
def test_live_validation_rejects_unbounded_arguments(converter, value):
    with pytest.raises(argparse.ArgumentTypeError):
        converter(value)
