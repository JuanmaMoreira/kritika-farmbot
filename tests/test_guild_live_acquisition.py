import argparse

import pytest

from tools.guild_live_acquisition import parse_args


def test_live_acquisition_defaults_are_bounded_and_observational():
    args = parse_args(["--label", "attendance-transition"])

    assert args.label == "attendance-transition"
    assert args.interval == 0.25
    assert args.max_seconds == 90.0


@pytest.mark.parametrize("label", ["Guild", "guild pending", "guild/pending"])
def test_live_acquisition_rejects_unsafe_labels(label):
    with pytest.raises(SystemExit):
        parse_args(["--label", label])


@pytest.mark.parametrize("option", ["--interval", "--max-seconds"])
def test_live_acquisition_rejects_non_positive_bounds(option):
    with pytest.raises(SystemExit):
        parse_args(["--label", "guild", option, "0"])
