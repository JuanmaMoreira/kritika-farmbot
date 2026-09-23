"""Minimal General/materials composition over closed C2/C3/C4 owners.

The caller supplies one already-planned ``TradingMaterialsStep``.  This
adapter selects General, locates only each explicit row, requires a fresh C3
fact, and delegates one exact C4 operation.  It performs no diagnosis,
speculative row visit, routing, replanning or recovery policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.directed_list_scroll import DirectedScrollOutcome, DirectedScrollResult
from bot.flow_contracts import FlowResult, FlowStatus
from bot.resource_route_planner import (
    TradingMaterialOperation,
    TradingMaterialsStep,
)
from bot.runtime_observer import RuntimeSnapshot
from bot.trading_center import is_materials_content_ready
from bot.trading_operation import (
    TradeOutcome,
    TradeQuantity,
    TradeQuantityMode,
    TradeResult,
)
from bot.trading_row_facts import MATERIALS_SECTION, TradingRowFact


@dataclass(frozen=True)
class FreshMaterialFact:
    """One General-ready snapshot and its same-frame explicit row fact."""

    snapshot: RuntimeSnapshot
    row_fact: TradingRowFact

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, RuntimeSnapshot):
            raise ValueError("snapshot must be RuntimeSnapshot")
        if not isinstance(self.row_fact, TradingRowFact):
            raise ValueError("row_fact must be TradingRowFact")
        if self.row_fact.section != MATERIALS_SECTION:
            raise ValueError("row_fact must belong to materials")
        if self.row_fact.sequence != self.snapshot.sequence:
            raise ValueError("row_fact must belong to snapshot.sequence")
        if not is_materials_content_ready(self.snapshot):
            raise ValueError("snapshot must be fresh General/material readiness")


@dataclass(frozen=True)
class TradingMaterialsResult(FlowResult):
    executed_operations: tuple[TradingMaterialOperation, ...] = ()
    trade_results: tuple[TradeResult, ...] = ()
    final_fact: FreshMaterialFact | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "executed_operations", tuple(self.executed_operations))
        object.__setattr__(self, "trade_results", tuple(self.trade_results))


class TradingMaterialsRuntime:
    """Execute one immutable materials step inside an open Trading context."""

    def __init__(
        self,
        trading_runtime,
        *,
        locate_material,
        read_material_fact,
        execute_material_trade,
        cancel_requested=lambda: False,
    ) -> None:
        if not callable(getattr(trading_runtime, "ensure_general", None)):
            raise ValueError("trading_runtime must provide ensure_general()")
        for callback, name in (
            (locate_material, "locate_material"),
            (read_material_fact, "read_material_fact"),
            (execute_material_trade, "execute_material_trade"),
            (cancel_requested, "cancel_requested"),
        ):
            if not callable(callback):
                raise ValueError(f"{name} must be callable")
        self.trading_runtime = trading_runtime
        self.locate_material = locate_material
        self.read_material_fact = read_material_fact
        self.execute_material_trade = execute_material_trade
        self.cancel_requested = cancel_requested

    def execute(self, step: TradingMaterialsStep, *, max_batches: int = 32) -> TradingMaterialsResult:
        if not isinstance(step, TradingMaterialsStep):
            raise ValueError("step must be TradingMaterialsStep")
        if isinstance(max_batches, bool) or not isinstance(max_batches, int) or max_batches < 1:
            raise ValueError("max_batches must be positive")
        if len(step.operations) != 1 or (
            step.operations[0].trading_item_id,
            step.operations[0].source_item_id,
            step.operations[0].destination_item_id,
        ) != ("hero_weapon_crafting_material", "weapon_material", "hero_weapon_material"):
            raise ValueError("only Weapon -> Hero material is supported")
        executed: list[TradingMaterialOperation] = []
        results: list[TradeResult] = []
        latest: FreshMaterialFact | None = None

        def finish(status: FlowStatus, **kwargs) -> TradingMaterialsResult:
            return TradingMaterialsResult(
                status,
                executed_operations=tuple(executed),
                trade_results=tuple(results),
                final_fact=latest,
                **kwargs,
            )

        if self._cancelled():
            return finish(FlowStatus.CANCELLED)
        general = self.trading_runtime.ensure_general()
        if general.status is FlowStatus.CANCELLED:
            return finish(FlowStatus.CANCELLED)
        general_snapshot = getattr(general, "final_snapshot", None)
        if general.status is not FlowStatus.COMPLETED or not isinstance(
            general_snapshot, RuntimeSnapshot
        ):
            return finish(
                FlowStatus.FAILED,
                error=f"ensure_general_failed:{getattr(general, 'error', None)}",
            )
        barrier = general_snapshot.sequence

        for operation in step.operations:
            if self._cancelled():
                return finish(FlowStatus.CANCELLED)
            located = self.locate_material(
                target=operation.trading_item_id,
                after_sequence=barrier,
            )
            if not isinstance(located, DirectedScrollResult):
                return finish(FlowStatus.FAILED, error="material_location_invalid")
            if located.outcome is not DirectedScrollOutcome.TARGET_READY:
                return finish(
                    FlowStatus.FAILED,
                    error=(
                        "material_location_failed:"
                        f"{located.outcome.value}:{located.reason}"
                    ),
                )
            if located.last_sequence is None or located.last_sequence <= barrier:
                return finish(FlowStatus.FAILED, error="material_location_stale")
            fact_barrier = max(barrier, located.last_sequence)
            latest = self.read_material_fact(
                target=operation.trading_item_id,
                after_sequence=fact_barrier,
            )
            if not isinstance(latest, FreshMaterialFact):
                return finish(FlowStatus.FAILED, error="fresh_material_fact_unavailable")
            if (
                latest.snapshot.sequence <= fact_barrier
                or latest.row_fact.item_id != operation.trading_item_id
            ):
                return finish(FlowStatus.FAILED, error="fresh_material_fact_mismatch")
            for _ in range(max_batches):
                if self._cancelled():
                    return finish(FlowStatus.CANCELLED)
                if latest.row_fact.need != 40:
                    return finish(FlowStatus.FAILED, error="unexpected_weapon_trade_need")
                if latest.row_fact.have < 40:
                    return finish(FlowStatus.COMPLETED)
                result = self.execute_material_trade(
                    operation=operation,
                    snapshot=latest.snapshot,
                    row_fact=latest.row_fact,
                    quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
                )
                if not isinstance(result, TradeResult):
                    return finish(FlowStatus.FAILED, error="material_trade_invalid_result")
                results.append(result)
                if result.outcome is TradeOutcome.CANCELLED:
                    return finish(FlowStatus.CANCELLED)
                if result.outcome is not TradeOutcome.SUCCESS:
                    return finish(
                        FlowStatus.FAILED,
                        error=f"material_trade_failed:{result.outcome.value}:{result.reason}",
                    )
                if (result.after_fact is None
                        or result.after_fact.sequence <= latest.row_fact.sequence
                        or result.after_fact.have >= latest.row_fact.have):
                    return finish(FlowStatus.FAILED, error="material_trade_progress_not_proven")
                executed.append(operation)
                barrier = result.after_fact.sequence
                latest = self.read_material_fact(
                    target=operation.trading_item_id, after_sequence=barrier,
                )
                if (not isinstance(latest, FreshMaterialFact)
                        or latest.snapshot.sequence <= barrier
                        or latest.row_fact.item_id != operation.trading_item_id):
                    return finish(FlowStatus.FAILED, error="fresh_material_fact_unavailable")
                if latest.row_fact.have != result.after_fact.have:
                    return finish(FlowStatus.FAILED, error="fresh_material_fact_contradictory")
                if latest.row_fact.have < 40:
                    return finish(FlowStatus.COMPLETED)
            return finish(FlowStatus.FAILED, error="material_batch_budget_exhausted")
        return finish(FlowStatus.COMPLETED)

    def _cancelled(self) -> bool:
        try:
            return self.cancel_requested() is True
        except Exception:
            return False


__all__ = (
    "FreshMaterialFact",
    "TradingMaterialsResult",
    "TradingMaterialsRuntime",
)
