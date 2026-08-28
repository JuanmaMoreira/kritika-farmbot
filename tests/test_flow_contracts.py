import pytest

from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY
from bot.component_contracts import ComponentRequirement, RequirementKind
from bot.flow_contracts import FlowContract, FlowEvent, FlowResult, FlowStatus


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


def test_cancelled_flow_is_neither_completed_nor_failed():
    result = FlowResult(FlowStatus.CANCELLED)

    assert not result.succeeded
    assert result.status is FlowStatus.CANCELLED


def test_completed_flow_cannot_carry_a_technical_error():
    with pytest.raises(ValueError, match="completed flow"):
        FlowResult(FlowStatus.COMPLETED, error="contradiction")


def test_flow_contract_declares_exact_precondition():
    contract = FlowContract(
        ComponentRequirement.exact_state(SCREEN_LOBBY),
        (ComponentRequirement.exact_state(SCREEN_LOBBY),),
    )

    assert contract.precondition.kind is RequirementKind.EXACT_STATE
    assert contract.precondition.name == SCREEN_LOBBY


def test_flow_contract_accepts_multiple_successful_postconditions():
    contract = FlowContract(
        ComponentRequirement.exact_state(SCREEN_LOBBY),
        (
            ComponentRequirement.exact_state(SCREEN_LOBBY),
            ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),
        ),
    )

    assert tuple(item.name for item in contract.successful_postconditions) == (
        SCREEN_LOBBY,
        SCREEN_BATTLE_MODE_SELECT,
    )


def test_completed_result_does_not_encode_an_implicit_lobby_state():
    result = FlowResult(FlowStatus.COMPLETED)
    contract = FlowContract(
        ComponentRequirement.exact_state(SCREEN_LOBBY),
        (ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT),),
    )

    assert result.succeeded
    assert all(
        postcondition.name != SCREEN_LOBBY
        for postcondition in contract.successful_postconditions
    )
