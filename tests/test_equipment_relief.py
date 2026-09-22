from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot.equipment_relief as equipment_relief_module
from bot.equipment_combine_relief import (
    EquipmentCombineReliefOutcome,
    EquipmentCombineReliefResult,
    EquipmentCombineReturnPlan,
)
from bot.equipment_relief import (
    EquipmentReliefComposer,
    EquipmentReliefOutcome,
    EquipmentReliefRequest,
    EquipmentReliefSellPlan,
    FreshCallerContext,
)
from bot.equipment_sell_operation import (
    EquipmentSellCandidate,
    EquipmentSellOutcome,
    EquipmentSellRequest,
    EquipmentSellResult,
)
from bot.equipment_sell_policy import EquipmentSellAuthorization
from bot.equipment_sell_semantics import (
    EquipmentBulkGroup,
    EquipmentGrade,
    EquipmentInventoryFact,
    EquipmentType,
)


@dataclass(frozen=True)
class CallerResult:
    outcome: str
    attempt: int


def inventory(item_count, sequence, *, capacity=128):
    return EquipmentInventoryFact(
        item_count=item_count,
        capacity=capacity,
        page=1,
        total_pages=8,
        sequence=sequence,
        observed_at=float(sequence),
        sample_sequences=(sequence - 1, sequence),
    )


def sell_request():
    authorization = EquipmentSellAuthorization(
        allowed_types=frozenset({EquipmentType.GLOVES}),
        allowed_grades=frozenset({EquipmentGrade.EPIC}),
        allowed_enhance_states=frozenset({False}),
        allowed_bulk_groups=frozenset({EquipmentBulkGroup.EQUIPMENT_GRADE}),
        label="equipment-relief-test",
    )
    return EquipmentSellRequest(
        authorization=authorization,
        candidate=EquipmentSellCandidate(page=1, slot=3),
    )


def successful_sell_result():
    return EquipmentSellResult(
        outcome=EquipmentSellOutcome.SUCCESS,
        reason="item_count_decreased",
        before=inventory(120, 14),
        after=inventory(114, 18),
        inputs=("select_candidate", "open_confirmation", "confirm_bulk"),
    )


class Scenario:
    def __init__(
        self,
        outcomes,
        *,
        contexts=(1, 11, 21),
        combine_outcome=EquipmentCombineReliefOutcome.RELIEVED,
        combine_sequence=10,
        sell_result=None,
        with_sell_plan=True,
    ):
        self.outcomes = list(outcomes)
        self.contexts = list(contexts)
        self.trace = []
        self.operation_request = object()
        self.seen_requests = []
        self.seen_contexts = []
        self.combine = Mock()
        self.sell = Mock()
        self.combine.run.return_value = EquipmentCombineReliefResult(
            combine_outcome,
            final_snapshot=SimpleNamespace(sequence=combine_sequence),
            error="combine-error"
            if combine_outcome is EquipmentCombineReliefOutcome.FAILED
            else None,
        )
        self.sell.execute.return_value = sell_result or successful_sell_result()
        self.return_sequence = 20
        self.plan = (
            EquipmentReliefSellPlan(
                request=sell_request(),
                enter_inventory=self.enter_inventory,
                return_to_caller=self.return_to_caller,
            )
            if with_sell_plan
            else None
        )
        self.request = EquipmentReliefRequest(
            operation_request=self.operation_request,
            acquire_context=self.acquire_context,
            execute_operation=self.execute_operation,
            is_equipment_full=lambda result: result.outcome == "equipment_full",
            enter_combine=self.enter_combine,
            combine_return_plan=EquipmentCombineReturnPlan(
                action=object(), expected_return_state="screen.caller"
            ),
            sell_plan=self.plan,
        )
        self.composer = EquipmentReliefComposer(self.combine, self.sell)

    def acquire_context(self, after_sequence):
        self.trace.append(("acquire", after_sequence))
        sequence = self.contexts.pop(0)
        value = object()
        self.seen_contexts.append(value)
        return FreshCallerContext(value=value, sequence=sequence)

    def execute_operation(self, operation_request, context):
        self.seen_requests.append(operation_request)
        self.trace.append(("caller", context))
        return CallerResult(self.outcomes.pop(0), len(self.seen_requests))

    def enter_combine(self, result):
        self.trace.append(("combine.enter", result.attempt))

    def enter_inventory(self, result):
        self.trace.append(("sell.enter", result.attempt))

    def return_to_caller(self, result):
        self.trace.append(("sell.return", result.reason))
        return self.return_sequence


@pytest.mark.parametrize("terminal", ["success", "failed", "cancelled"])
def test_initial_non_equipment_full_result_returns_unchanged_without_relief(terminal):
    scenario = Scenario([terminal])

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_RESULT
    assert result.caller_result.outcome == terminal
    assert result.caller_attempt_count == 1
    assert result.combine_invocation_count == result.sell_invocation_count == 0
    scenario.combine.run.assert_not_called()
    scenario.sell.execute.assert_not_called()


def test_combine_relief_retries_same_request_once_with_fresh_context():
    scenario = Scenario(["equipment_full", "success"])

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_RESULT
    assert result.stage == "caller.result_after_combine"
    assert result.caller_attempt_count == 2
    assert result.combine_invocation_count == 1
    assert result.sell_invocation_count == 0
    assert scenario.seen_requests == [scenario.operation_request] * 2
    assert len({id(value) for value in scenario.seen_contexts}) == 2
    assert ("acquire", 10) in scenario.trace
    scenario.combine.run.assert_called_once_with(
        scenario.request.combine_return_plan,
        cancel_requested=scenario.request.cancel_requested,
    )
    scenario.sell.execute.assert_not_called()


def test_combine_no_relief_available_still_retries_caller_before_sell():
    scenario = Scenario(
        ["equipment_full", "terminal_failure"],
        combine_outcome=EquipmentCombineReliefOutcome.NO_RELIEF_AVAILABLE,
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_RESULT
    assert result.caller_result.outcome == "terminal_failure"
    assert result.caller_attempt_count == 2
    scenario.sell.execute.assert_not_called()


@pytest.mark.parametrize(
    "combine_outcome,expected",
    [
        (EquipmentCombineReliefOutcome.CANCELLED, EquipmentReliefOutcome.COMBINE_CANCELLED),
        (EquipmentCombineReliefOutcome.FAILED, EquipmentReliefOutcome.COMBINE_FAILED),
    ],
)
def test_combine_cancel_or_technical_failure_stops_without_sell_or_retry(
    combine_outcome, expected
):
    scenario = Scenario(["equipment_full"], combine_outcome=combine_outcome)

    result = scenario.composer.run(scenario.request)

    assert result.outcome is expected
    assert result.caller_attempt_count == 1
    assert result.combine_invocation_count == 1
    assert result.sell_invocation_count == 0
    scenario.sell.execute.assert_not_called()


def test_unexpected_combine_exception_fails_closed_without_sell():
    scenario = Scenario(["equipment_full"])
    scenario.combine.run.side_effect = RuntimeError("combine broke")

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.COMBINE_FAILED
    assert result.error == "RuntimeError: combine broke"
    assert result.combine_invocation_count == 1
    scenario.sell.execute.assert_not_called()


def test_second_equipment_full_without_explicit_sell_plan_fails_before_inventory():
    scenario = Scenario(
        ["equipment_full", "equipment_full"],
        with_sell_plan=False,
    )

    result = scenario.composer.run(scenario.request)

    assert (
        result.outcome
        is EquipmentReliefOutcome.SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE
    )
    assert result.caller_attempt_count == 2
    assert result.sell_invocation_count == 0
    assert not any(step[0] == "sell.enter" for step in scenario.trace)
    scenario.sell.execute.assert_not_called()


@pytest.mark.parametrize(
    "combine_outcome",
    [
        EquipmentCombineReliefOutcome.RELIEVED,
        EquipmentCombineReliefOutcome.NO_RELIEF_AVAILABLE,
    ],
)
def test_sell_success_reorients_then_retries_same_request_with_new_context(
    combine_outcome,
):
    scenario = Scenario(
        ["equipment_full", "equipment_full", "success"],
        combine_outcome=combine_outcome,
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_RESULT
    assert result.stage == "caller.result_after_sell"
    assert result.caller_attempt_count == 3
    assert result.combine_invocation_count == result.sell_invocation_count == 1
    assert scenario.seen_requests == [scenario.operation_request] * 3
    assert len({id(value) for value in scenario.seen_contexts}) == 3
    assert ("acquire", 20) in scenario.trace
    scenario.sell.execute.assert_called_once_with(scenario.plan.request)


def test_equipment_full_after_sell_fails_closed_without_second_relief():
    scenario = Scenario(
        ["equipment_full", "equipment_full", "equipment_full"]
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.EQUIPMENT_FULL_AFTER_SELL
    assert result.caller_attempt_count == 3
    assert result.combine_invocation_count == result.sell_invocation_count == 1
    scenario.combine.run.assert_called_once()
    scenario.sell.execute.assert_called_once()


def test_other_terminal_result_after_sell_is_returned_to_caller():
    scenario = Scenario(
        ["equipment_full", "equipment_full", "business_failure"]
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_RESULT
    assert result.caller_result.outcome == "business_failure"


@pytest.mark.parametrize(
    "sell_outcome,expected",
    [
        (EquipmentSellOutcome.CANCELLED, EquipmentReliefOutcome.SELL_CANCELLED),
        (EquipmentSellOutcome.DENIED, EquipmentReliefOutcome.SELL_DENIED),
        (EquipmentSellOutcome.FAILED, EquipmentReliefOutcome.SELL_FAILED),
    ],
)
def test_non_successful_sell_never_returns_or_retries_caller(sell_outcome, expected):
    scenario = Scenario(
        ["equipment_full", "equipment_full"],
        sell_result=EquipmentSellResult(sell_outcome, sell_outcome.value),
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is expected
    assert result.caller_attempt_count == 2
    assert result.sell_invocation_count == 1
    assert not any(step[0] == "sell.return" for step in scenario.trace)
    scenario.sell.execute.assert_called_once()


def test_unexpected_sell_exception_fails_closed_without_caller_retry():
    scenario = Scenario(["equipment_full", "equipment_full"])
    scenario.sell.execute.side_effect = RuntimeError("sell broke")

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.SELL_FAILED
    assert result.error == "RuntimeError: sell broke"
    assert result.caller_attempt_count == 2
    assert result.sell_invocation_count == 1
    assert not any(step[0] == "sell.return" for step in scenario.trace)


@pytest.mark.parametrize(
    "bad_sell",
    [
        EquipmentSellResult(
            EquipmentSellOutcome.SUCCESS,
            "unchanged",
            before=inventory(120, 14),
            after=inventory(120, 18),
            inputs=("confirm_bulk",),
        ),
        EquipmentSellResult(
            EquipmentSellOutcome.SUCCESS,
            "two_confirms",
            before=inventory(120, 14),
            after=inventory(114, 18),
            inputs=("confirm_bulk", "confirm_bulk"),
        ),
    ],
)
def test_sell_success_claim_requires_decrease_and_exactly_one_confirm(bad_sell):
    scenario = Scenario(
        ["equipment_full", "equipment_full"],
        sell_result=bad_sell,
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.SELL_FAILED
    assert result.error == "sell_success_without_verified_item_count_decrease"
    assert not any(step[0] == "sell.return" for step in scenario.trace)


def test_stale_context_after_combine_stops_before_caller_retry():
    scenario = Scenario(["equipment_full"], contexts=(1, 10))

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_CONTEXT_FAILED
    assert result.error == "caller_context_not_fresh"
    assert result.caller_attempt_count == 1
    scenario.sell.execute.assert_not_called()


def test_stale_context_after_sell_stops_before_final_caller_retry():
    scenario = Scenario(
        ["equipment_full", "equipment_full"],
        contexts=(1, 11, 20),
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CALLER_CONTEXT_FAILED
    assert result.error == "caller_context_not_fresh"
    assert result.caller_attempt_count == 2
    scenario.sell.execute.assert_called_once()


def test_invalid_sell_return_barrier_stops_before_fresh_context_or_retry():
    scenario = Scenario(["equipment_full", "equipment_full"])
    scenario.return_sequence = 18

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.NAVIGATION_FAILED
    assert result.error == "sell_return_not_fresh"
    assert result.caller_attempt_count == 2
    assert len(scenario.seen_contexts) == 2


def test_navigation_failure_stops_before_relief_invocation():
    scenario = Scenario(["equipment_full"])
    scenario.request = EquipmentReliefRequest(
        operation_request=scenario.operation_request,
        acquire_context=scenario.acquire_context,
        execute_operation=scenario.execute_operation,
        is_equipment_full=lambda result: result.outcome == "equipment_full",
        enter_combine=lambda result: (_ for _ in ()).throw(RuntimeError("route")),
        combine_return_plan=EquipmentCombineReturnPlan(
            action=object(), expected_return_state="screen.caller"
        ),
        sell_plan=scenario.plan,
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.NAVIGATION_FAILED
    assert result.stage == "combine.enter"
    assert result.combine_invocation_count == 0
    scenario.combine.run.assert_not_called()


def test_cancel_before_sell_produces_zero_destructive_input():
    scenario = Scenario(["equipment_full", "equipment_full"])
    checks = iter([False, False, False, False, False, False, True])
    scenario.request = EquipmentReliefRequest(
        operation_request=scenario.operation_request,
        acquire_context=scenario.acquire_context,
        execute_operation=scenario.execute_operation,
        is_equipment_full=lambda result: result.outcome == "equipment_full",
        enter_combine=scenario.enter_combine,
        combine_return_plan=EquipmentCombineReturnPlan(
            action=object(), expected_return_state="screen.caller"
        ),
        sell_plan=scenario.plan,
        cancel_requested=lambda: next(checks, True),
    )

    result = scenario.composer.run(scenario.request)

    assert result.outcome is EquipmentReliefOutcome.CANCELLED
    assert result.sell_invocation_count == 0
    scenario.sell.execute.assert_not_called()


def test_composer_imports_no_caller_business_or_neighbor_resource_modules():
    source = equipment_relief_module.__loader__.get_source(  # type: ignore[union-attr]
        equipment_relief_module.__name__
    )
    assert source is not None
    for forbidden in (
        "bot.craft",
        "bot.monster_wave",
        "bot.trading",
        "bot.treasure",
        "bot.quick_menu",
    ):
        assert forbidden not in source
