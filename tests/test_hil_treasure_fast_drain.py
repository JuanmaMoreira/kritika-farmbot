import pytest

from tools.hil_treasure_fast_drain import (
    EconomicInputCap,
    parse_args,
    remaining_economic_inputs,
)


def test_burst_cap_is_explicit_and_named_as_economic():
    args = parse_args([
        "--mode",
        "burst",
        "--approved-economic-inputs",
        "40",
    ])
    assert args.approved_economic_inputs == 40
    with pytest.raises(SystemExit):
        parse_args(["--mode", "burst", "--max-inputs", "40"])


def test_entry_consumes_the_same_approved_economic_budget():
    assert remaining_economic_inputs(40, 1) == 39
    assert remaining_economic_inputs(40, 0) == 40
    with pytest.raises(ValueError):
        remaining_economic_inputs(1, 2)


def test_economic_guard_never_emits_more_than_approved_cap():
    emitted = []
    guarded = EconomicInputCap(40, emitted.append)
    for index in range(40):
        guarded((index, index))

    with pytest.raises(RuntimeError, match="approved economic input cap"):
        guarded((40, 40))

    assert guarded.emitted == 40
    assert len(emitted) == 40
