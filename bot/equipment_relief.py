"""Bounded Combine-first composition for one Equipment-full caller operation.

The caller keeps its opaque business request and result vocabulary.  This
module owns only causal ordering, freshness barriers and the two relief
invocation bounds.  Concrete caller adapters still provide their verified
entry/return navigation; no route, candidate scan or sell policy is inferred.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from numbers import Integral
from typing import Generic, TypeVar

from bot.equipment_combine_relief import (
    EquipmentCombineReliefOutcome,
    EquipmentCombineReliefResult,
    EquipmentCombineReturnPlan,
)
from bot.equipment_sell_operation import (
    EquipmentSellOutcome,
    EquipmentSellRequest,
    EquipmentSellResult,
)
from bot.runtime_observer import RuntimeWaitCancelled


RequestT = TypeVar("RequestT")
ContextT = TypeVar("ContextT")
CallerResultT = TypeVar("CallerResultT")


def _never_cancel() -> bool:
    return False


class EquipmentReliefOutcome(str, Enum):
    CALLER_RESULT = "caller_result"
    CANCELLED = "cancelled"
    CALLER_CONTEXT_FAILED = "caller_context_failed"
    CALLER_EXECUTION_FAILED = "caller_execution_failed"
    NAVIGATION_FAILED = "navigation_failed"
    COMBINE_CANCELLED = "combine_cancelled"
    COMBINE_FAILED = "combine_failed"
    SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE = (
        "sell_required_but_no_authorized_candidate"
    )
    SELL_CANCELLED = "sell_cancelled"
    SELL_DENIED = "sell_denied"
    SELL_FAILED = "sell_failed"
    EQUIPMENT_FULL_AFTER_SELL = "equipment_full_after_sell"


@dataclass(frozen=True)
class FreshCallerContext(Generic[ContextT]):
    """Caller-owned precondition/facts with one comparable freshness cursor."""

    value: ContextT
    sequence: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, Integral)
            or self.sequence < 0
        ):
            raise ValueError("sequence must be a non-negative integer")
        object.__setattr__(self, "sequence", int(self.sequence))


@dataclass(frozen=True)
class EquipmentReliefSellPlan(Generic[CallerResultT]):
    """Explicit authorized Sell request plus caller-specific verified routing."""

    request: EquipmentSellRequest
    enter_inventory: Callable[[CallerResultT], None]
    return_to_caller: Callable[[EquipmentSellResult], int]

    def __post_init__(self) -> None:
        if not isinstance(self.request, EquipmentSellRequest):
            raise ValueError("request must be an EquipmentSellRequest")
        if not callable(self.enter_inventory) or not callable(self.return_to_caller):
            raise ValueError("sell navigation hooks must be callable")


@dataclass(frozen=True)
class EquipmentReliefRequest(Generic[RequestT, ContextT, CallerResultT]):
    """One opaque caller operation and the narrow adapters needed to retry it."""

    operation_request: RequestT
    acquire_context: Callable[[int | None], FreshCallerContext[ContextT]]
    execute_operation: Callable[[RequestT, ContextT], CallerResultT]
    is_equipment_full: Callable[[CallerResultT], bool]
    enter_combine: Callable[[CallerResultT], None]
    combine_return_plan: EquipmentCombineReturnPlan
    sell_plan: EquipmentReliefSellPlan[CallerResultT] | None = None
    cancel_requested: Callable[[], bool] = _never_cancel

    def __post_init__(self) -> None:
        hooks = (
            self.acquire_context,
            self.execute_operation,
            self.is_equipment_full,
            self.enter_combine,
            self.cancel_requested,
        )
        if any(not callable(hook) for hook in hooks):
            raise ValueError("caller and navigation hooks must be callable")
        if not isinstance(self.combine_return_plan, EquipmentCombineReturnPlan):
            raise ValueError("combine_return_plan must be an EquipmentCombineReturnPlan")
        if self.sell_plan is not None and not isinstance(
            self.sell_plan, EquipmentReliefSellPlan
        ):
            raise ValueError("sell_plan must be an EquipmentReliefSellPlan or None")


@dataclass(frozen=True)
class EquipmentReliefResult(Generic[CallerResultT]):
    outcome: EquipmentReliefOutcome
    stage: str
    caller_result: CallerResultT | None = None
    combine_result: EquipmentCombineReliefResult | None = None
    sell_result: EquipmentSellResult | None = None
    caller_attempt_count: int = 0
    combine_invocation_count: int = 0
    sell_invocation_count: int = 0
    error: str | None = None

    @property
    def returned_caller_result(self) -> bool:
        return self.outcome is EquipmentReliefOutcome.CALLER_RESULT


class _StopComposition(Exception):
    def __init__(
        self,
        outcome: EquipmentReliefOutcome,
        stage: str,
        error: str | None = None,
    ):
        super().__init__(error or stage)
        self.outcome = outcome
        self.stage = stage
        self.error = error


class EquipmentReliefComposer:
    """Compose one caller attempt, Combine retry and optional Sell retry."""

    def __init__(self, combine_relief, sell_runtime) -> None:
        if not callable(getattr(combine_relief, "run", None)):
            raise ValueError("combine_relief must provide run()")
        if not callable(getattr(sell_runtime, "execute", None)):
            raise ValueError("sell_runtime must provide execute()")
        self.combine_relief = combine_relief
        self.sell_runtime = sell_runtime

    def run(
        self,
        request: EquipmentReliefRequest[RequestT, ContextT, CallerResultT],
    ) -> EquipmentReliefResult[CallerResultT]:
        if not isinstance(request, EquipmentReliefRequest):
            raise ValueError("request must be an EquipmentReliefRequest")

        caller_result: CallerResultT | None = None
        combine_result: EquipmentCombineReliefResult | None = None
        sell_result: EquipmentSellResult | None = None
        caller_attempts = 0
        combine_invocations = 0
        sell_invocations = 0

        def finish(
            outcome: EquipmentReliefOutcome,
            stage: str,
            *,
            error: str | None = None,
        ) -> EquipmentReliefResult[CallerResultT]:
            return EquipmentReliefResult(
                outcome=outcome,
                stage=stage,
                caller_result=caller_result,
                combine_result=combine_result,
                sell_result=sell_result,
                caller_attempt_count=caller_attempts,
                combine_invocation_count=combine_invocations,
                sell_invocation_count=sell_invocations,
                error=error,
            )

        def ensure_not_cancelled(stage: str) -> None:
            try:
                cancelled = request.cancel_requested()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                raise _StopComposition(
                    EquipmentReliefOutcome.CANCELLED,
                    stage,
                    f"cancel_check_failed:{type(error).__name__}: {error}",
                ) from error
            if cancelled:
                raise _StopComposition(EquipmentReliefOutcome.CANCELLED, stage)

        def acquire(
            after_sequence: int | None,
            stage: str,
        ) -> FreshCallerContext[ContextT]:
            ensure_not_cancelled(stage)
            try:
                context = request.acquire_context(after_sequence)
            except (KeyboardInterrupt, SystemExit):
                raise
            except RuntimeWaitCancelled as error:
                raise _StopComposition(EquipmentReliefOutcome.CANCELLED, stage) from error
            except Exception as error:
                raise _StopComposition(
                    EquipmentReliefOutcome.CALLER_CONTEXT_FAILED,
                    stage,
                    f"{type(error).__name__}: {error}",
                ) from error
            if not isinstance(context, FreshCallerContext):
                raise _StopComposition(
                    EquipmentReliefOutcome.CALLER_CONTEXT_FAILED,
                    stage,
                    "acquire_context_did_not_return_fresh_context",
                )
            if after_sequence is not None and context.sequence <= after_sequence:
                raise _StopComposition(
                    EquipmentReliefOutcome.CALLER_CONTEXT_FAILED,
                    stage,
                    "caller_context_not_fresh",
                )
            return context

        def execute(context: FreshCallerContext[ContextT], stage: str) -> CallerResultT:
            nonlocal caller_attempts
            ensure_not_cancelled(stage)
            try:
                result = request.execute_operation(
                    request.operation_request,
                    context.value,
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except RuntimeWaitCancelled as error:
                raise _StopComposition(EquipmentReliefOutcome.CANCELLED, stage) from error
            except Exception as error:
                raise _StopComposition(
                    EquipmentReliefOutcome.CALLER_EXECUTION_FAILED,
                    stage,
                    f"{type(error).__name__}: {error}",
                ) from error
            caller_attempts += 1
            return result

        def equipment_full(result: CallerResultT, stage: str) -> bool:
            try:
                blocked = request.is_equipment_full(result)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as error:
                raise _StopComposition(
                    EquipmentReliefOutcome.CALLER_EXECUTION_FAILED,
                    stage,
                    f"equipment_full_classifier_failed:{type(error).__name__}: {error}",
                ) from error
            if type(blocked) is not bool:
                raise _StopComposition(
                    EquipmentReliefOutcome.CALLER_EXECUTION_FAILED,
                    stage,
                    "equipment_full_classifier_must_return_bool",
                )
            return blocked

        def navigate(callback, argument, stage: str) -> object:
            ensure_not_cancelled(stage)
            try:
                return callback(argument)
            except (KeyboardInterrupt, SystemExit):
                raise
            except RuntimeWaitCancelled as error:
                raise _StopComposition(EquipmentReliefOutcome.CANCELLED, stage) from error
            except Exception as error:
                raise _StopComposition(
                    EquipmentReliefOutcome.NAVIGATION_FAILED,
                    stage,
                    f"{type(error).__name__}: {error}",
                ) from error

        try:
            context = acquire(None, "caller.initial_context")
            caller_result = execute(context, "caller.initial_attempt")
            if not equipment_full(caller_result, "caller.initial_result"):
                return finish(EquipmentReliefOutcome.CALLER_RESULT, "caller.initial_result")

            navigate(request.enter_combine, caller_result, "combine.enter")
            ensure_not_cancelled("combine.run")
            combine_invocations = 1
            try:
                combine_result = self.combine_relief.run(
                    request.combine_return_plan,
                    cancel_requested=request.cancel_requested,
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except RuntimeWaitCancelled:
                return finish(
                    EquipmentReliefOutcome.COMBINE_CANCELLED,
                    "combine.run",
                )
            except Exception as error:
                return finish(
                    EquipmentReliefOutcome.COMBINE_FAILED,
                    "combine.run",
                    error=f"{type(error).__name__}: {error}",
                )
            if not isinstance(combine_result, EquipmentCombineReliefResult):
                raise _StopComposition(
                    EquipmentReliefOutcome.COMBINE_FAILED,
                    "combine.run",
                    "combine_returned_invalid_result",
                )
            if combine_result.outcome is EquipmentCombineReliefOutcome.CANCELLED:
                return finish(EquipmentReliefOutcome.COMBINE_CANCELLED, "combine.run")
            if combine_result.outcome is EquipmentCombineReliefOutcome.FAILED:
                return finish(
                    EquipmentReliefOutcome.COMBINE_FAILED,
                    "combine.run",
                    error=combine_result.error,
                )
            if combine_result.outcome not in {
                EquipmentCombineReliefOutcome.RELIEVED,
                EquipmentCombineReliefOutcome.NO_RELIEF_AVAILABLE,
            }:
                return finish(
                    EquipmentReliefOutcome.COMBINE_FAILED,
                    "combine.run",
                    error="combine_outcome_unknown",
                )
            combine_return = combine_result.final_snapshot
            if (
                combine_return is None
                or isinstance(getattr(combine_return, "sequence", None), bool)
                or not isinstance(getattr(combine_return, "sequence", None), Integral)
                or combine_return.sequence <= context.sequence
            ):
                return finish(
                    EquipmentReliefOutcome.COMBINE_FAILED,
                    "combine.return",
                    error="combine_return_not_fresh",
                )

            context = acquire(int(combine_return.sequence), "caller.context_after_combine")
            caller_result = execute(context, "caller.retry_after_combine")
            if not equipment_full(caller_result, "caller.result_after_combine"):
                return finish(
                    EquipmentReliefOutcome.CALLER_RESULT,
                    "caller.result_after_combine",
                )

            sell_plan = request.sell_plan
            if sell_plan is None:
                return finish(
                    EquipmentReliefOutcome.SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE,
                    "sell.plan",
                )

            navigate(sell_plan.enter_inventory, caller_result, "sell.enter_inventory")
            ensure_not_cancelled("sell.run")
            sell_invocations = 1
            try:
                sell_result = self.sell_runtime.execute(sell_plan.request)
            except (KeyboardInterrupt, SystemExit):
                raise
            except RuntimeWaitCancelled:
                return finish(EquipmentReliefOutcome.SELL_CANCELLED, "sell.run")
            except Exception as error:
                return finish(
                    EquipmentReliefOutcome.SELL_FAILED,
                    "sell.run",
                    error=f"{type(error).__name__}: {error}",
                )
            if not isinstance(sell_result, EquipmentSellResult):
                return finish(
                    EquipmentReliefOutcome.SELL_FAILED,
                    "sell.run",
                    error="sell_returned_invalid_result",
                )
            if sell_result.outcome is EquipmentSellOutcome.CANCELLED:
                return finish(EquipmentReliefOutcome.SELL_CANCELLED, "sell.run")
            if sell_result.outcome is EquipmentSellOutcome.DENIED:
                return finish(
                    EquipmentReliefOutcome.SELL_DENIED,
                    "sell.run",
                    error=sell_result.reason,
                )
            if sell_result.outcome is not EquipmentSellOutcome.SUCCESS:
                return finish(
                    EquipmentReliefOutcome.SELL_FAILED,
                    "sell.run",
                    error=sell_result.reason,
                )
            if not _verified_sell_success(sell_result):
                return finish(
                    EquipmentReliefOutcome.SELL_FAILED,
                    "sell.postcondition",
                    error="sell_success_without_verified_item_count_decrease",
                )

            return_sequence = navigate(
                sell_plan.return_to_caller,
                sell_result,
                "sell.return_to_caller",
            )
            assert sell_result.after is not None
            sell_after_sequence = sell_result.after.sequence
            if (
                isinstance(return_sequence, bool)
                or not isinstance(return_sequence, Integral)
                or return_sequence <= sell_after_sequence
                or return_sequence <= context.sequence
            ):
                return finish(
                    EquipmentReliefOutcome.NAVIGATION_FAILED,
                    "sell.return_to_caller",
                    error="sell_return_not_fresh",
                )

            context = acquire(int(return_sequence), "caller.context_after_sell")
            caller_result = execute(context, "caller.retry_after_sell")
            if equipment_full(caller_result, "caller.result_after_sell"):
                return finish(
                    EquipmentReliefOutcome.EQUIPMENT_FULL_AFTER_SELL,
                    "caller.result_after_sell",
                )
            return finish(
                EquipmentReliefOutcome.CALLER_RESULT,
                "caller.result_after_sell",
            )
        except _StopComposition as stopped:
            return finish(stopped.outcome, stopped.stage, error=stopped.error)


def _verified_sell_success(result: EquipmentSellResult) -> bool:
    before = result.before
    after = result.after
    return (
        result.outcome is EquipmentSellOutcome.SUCCESS
        and before is not None
        and after is not None
        and before.confirmed
        and after.confirmed
        and after.sequence > before.sequence
        and after.capacity == before.capacity
        and after.item_count < before.item_count
        and result.confirm_count == 1
    )


__all__ = (
    "EquipmentReliefComposer",
    "EquipmentReliefOutcome",
    "EquipmentReliefRequest",
    "EquipmentReliefResult",
    "EquipmentReliefSellPlan",
    "FreshCallerContext",
)
