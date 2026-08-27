import pytest

from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus


def test_completed_flow_without_events():
    result = FlowResult(FlowStatus.COMPLETED)

    assert result.succeeded
    assert result.events == ()


def test_completed_flow_supports_multiple_extensible_business_events():
    result = FlowResult(
        FlowStatus.COMPLETED,
        events=(
            FlowEvent("low_gold"),
            FlowEvent("inventory_full", detail="meteorite"),
        ),
    )

    assert result.event_count("low_gold") == 1
    assert result.event_count("inventory_full") == 1
    assert result.events[1].detail == "meteorite"


def test_failed_status_is_independent_from_prior_business_events():
    result = FlowResult(
        FlowStatus.FAILED,
        events=(FlowEvent("low_gold"), FlowEvent("inventory_full")),
        error="postcondition_lobby_failed",
    )

    assert not result.succeeded
    assert result.event_count("low_gold") == 1
    assert result.event_count("inventory_full") == 1


def test_completed_flow_cannot_carry_a_technical_error():
    with pytest.raises(ValueError, match="completed flow"):
        FlowResult(FlowStatus.COMPLETED, error="contradiction")
