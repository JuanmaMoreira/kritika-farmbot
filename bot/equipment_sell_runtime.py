"""Equipment-specific live adapter for one verified sale.

The caller owns navigation and capture lifecycle.  This adapter only samples
the current Equipment Inventory surface, delegates policy/order to the pure
operation, and translates its four physical intents through ActionExecutor.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.event_log import record_best_effort
from bot.equipment_sell_operation import (
    EquipmentSellOutcome,
    EquipmentSellRequest,
    EquipmentSellResult,
    execute_equipment_sell,
)
from bot.equipment_sell_semantics import consensus_facts
from bot.semantic_actions import (
    CancelEquipmentSale,
    CloseEquipmentDetail,
    NextEquipmentInventoryPage,
    PreviousEquipmentInventoryPage,
    OpenEquipmentCapacityRow,
    ConfirmEquipmentCapacityExpansion,
    CancelEquipmentCapacityExpansion,
    ConfirmEquipmentBulkSale,
    OpenEquipmentSell,
    SelectEquipmentInventorySlot,
)


class EquipmentSellRuntime:
    """Run one sale from an already-open Equipment Inventory page."""

    def __init__(
        self,
        source,
        reader,
        actions: ActionExecutor,
        *,
        sample_timeout: float = 4.0,
        sample_interval: float = 0.05,
        cancel_requested: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        events=None,
    ) -> None:
        if not callable(getattr(source, "get_frame", None)):
            raise ValueError("source must provide get_frame()")
        for method in ("inventory_sample", "detail_sample", "confirmation_sample"):
            if not callable(getattr(reader, method, None)):
                raise ValueError(f"reader must provide {method}()")
        if not isinstance(actions, ActionExecutor):
            raise ValueError("actions must be an ActionExecutor")
        if sample_timeout <= 0 or sample_interval < 0:
            raise ValueError("sampling durations must be positive/non-negative")
        if not all(callable(value) for value in (cancel_requested, clock, sleeper)):
            raise ValueError("runtime callbacks must be callable")
        self.source = source
        self.reader = reader
        self.actions = actions
        self.sample_timeout = float(sample_timeout)
        self.sample_interval = float(sample_interval)
        self.cancel_requested = cancel_requested
        self.clock = clock
        self.sleeper = sleeper
        self._latest = None
        self._after_sequence = 0
        self._not_before = 0.0
        self.events = events

    def execute(self, request: EquipmentSellRequest) -> EquipmentSellResult:
        """Execute at most one confirm; never navigate, scan or retry input."""

        if not isinstance(request, EquipmentSellRequest):
            raise ValueError("request must be EquipmentSellRequest")
        before = self._read_consensus("inventory_sample", after_sequence=self._after_sequence)
        if before is None:
            return EquipmentSellResult(
                outcome=(
                    EquipmentSellOutcome.CANCELLED
                    if self.cancel_requested()
                    else EquipmentSellOutcome.FAILED
                ),
                reason=(
                    "cancelled"
                    if self.cancel_requested()
                    else "initial_inventory_unreadable"
                ),
            )
        self._after_sequence = before.sequence

        return execute_equipment_sell(
            request=request,
            before=before,
            select_candidate=lambda candidate: self._tap(
                SelectEquipmentInventorySlot(candidate.slot)
            ),
            read_detail=lambda: self._read_next("detail_sample"),
            open_confirmation=lambda: self._tap(OpenEquipmentSell()),
            read_confirmation=lambda: self._read_next("confirmation_sample"),
            confirm_bulk=lambda: self._tap(ConfirmEquipmentBulkSale()),
            cancel_confirmation=lambda: self._tap(CancelEquipmentSale()),
            read_inventory=lambda: self._read_next("inventory_sample", predicate=lambda v: v.item_count < before.item_count),
            cancel_requested=self.cancel_requested,
        )

    def execute_relief(self, policy):
        from bot.equipment_inventory_relief import execute_inventory_relief
        started = self.clock()
        result = execute_inventory_relief(
            policy, read_inventory=self._inventory_after,
            inspect=self._inspect, bulk_sell=self._bulk_candidate,
            expand=self._expand, cancel_requested=self.cancel_requested,
        )
        record_best_effort(self.events, "equipment.inventory_relief.result",
                          outcome=result.outcome, reason=result.reason,
                          before_count=getattr(result.before,"item_count",None),
                          after_count=getattr(result.after,"item_count",None),
                          capacity=getattr(result.after,"capacity",None),
                          sales=len(result.sales), expansions=len(result.expansions),
                          elapsed_seconds=self.clock()-started)
        return result

    def _inventory_after(self, cursor, predicate=lambda v: True):
        fact = self._read_consensus("inventory_sample",
                                    after_sequence=max(cursor, self._after_sequence),
                                    predicate=predicate)
        if fact is not None:
            self._after_sequence = fact.sequence
        return fact

    def _navigate_page(self, page, expected):
        current = self._inventory_after(0)
        if current is None:
            raise RuntimeError("inventory_navigation_unreadable")
        for _ in range(current.total_pages):
            if (current.item_count,current.capacity) != (expected.item_count,expected.capacity):
                raise RuntimeError("inventory_changed_during_scan")
            if current.page == page:
                return current
            action = NextEquipmentInventoryPage() if current.page < page else PreviousEquipmentInventoryPage()
            target = current.page + (1 if current.page < page else -1)
            self._tap(action)
            current = self._inventory_after(0, predicate=lambda v: v.page == target)
            if current is None:
                raise RuntimeError("inventory_page_transition_unverified")
        raise RuntimeError("inventory_page_bound")

    def _inspect(self, candidate, inventory):
        self._navigate_page(candidate.page, inventory)
        self._tap(SelectEquipmentInventorySlot(candidate.slot))
        detail = self._read_next("detail_sample")
        self._tap(CloseEquipmentDetail())
        # Prove closing the detail preserved Inventory and the scan list.
        closed = self._inventory_after(0)
        if closed is None or (closed.item_count,closed.capacity,closed.page) != (
                inventory.item_count,inventory.capacity,candidate.page):
            raise RuntimeError("detail_close_unverified")
        record_best_effort(self.events, "equipment.sell.scan.item", page=candidate.page,
                          slot=candidate.slot, name=getattr(detail,"name",None),
                          grade=getattr(getattr(detail,"grade",None),"value",None),
                          equipment_type=getattr(getattr(detail,"equipment_type",None),"value",None),
                          enhance=getattr(detail,"enhance",None),
                          sell_available=getattr(detail,"sell_available",None),
                          grade_visual=getattr(getattr(detail,"grade_visual",None),"value",None),
                          source_sequence=getattr(detail,"sequence",None))
        return detail

    def _bulk_candidate(self, candidate, authorization, item):
        from bot.equipment_sell_operation import EquipmentSellRequest
        result = self.execute(EquipmentSellRequest(authorization, candidate, expected_item=item))
        record_best_effort(self.events, "equipment.sell.bulk.result", outcome=result.outcome.value,
                          reason=result.reason, confirms=result.confirm_count,
                          before_count=getattr(result.before,"item_count",None),
                          after_count=getattr(result.after,"item_count",None))
        return result

    def _expand(self, before):
        from bot.equipment_inventory_relief import EquipmentCapacityExpansionResult
        page, row = before.capacity // 16 + 1, (before.capacity % 16) // 4
        if page > before.total_pages:
            return EquipmentCapacityExpansionResult(before,None,None,0,"capacity_limit")
        self._navigate_page(page, before)
        values = []
        deadline = self.clock() + self.sample_timeout
        while self.clock() < deadline and len(values) < 2:
            f = self.source.get_frame()
            if f.sequence <= self._after_sequence or not 0 <= self.clock()-f.timestamp <= 2:
                self.sleeper(self.sample_interval)
                continue
            self._latest = f
            self._after_sequence = f.sequence
            cost = self.reader.capacity_row_cost(f.image,row)
            if cost is None or (values and values[-1] != cost):
                values = []
            if cost is not None:
                values.append(cost)
        if len(values) < 2 or values[-1] <= 0 or self.cancel_requested():
            return EquipmentCapacityExpansionResult(before,None,None,0,"row_cost_unreadable")
        cost = values[-1]
        self._tap(OpenEquipmentCapacityRow(row))
        samples = []
        deadline = self.clock() + self.sample_timeout
        while self.clock() < deadline:
            f = self.source.get_frame()
            if f.sequence <= self._after_sequence or f.timestamp < self._not_before:
                self.sleeper(self.sample_interval)
                continue
            self._latest = f
            self._after_sequence = f.sequence
            value = self.reader.expansion_sample(f.image,sequence=f.sequence,observed_at=f.timestamp)
            if value is not None and 0 <= self.clock()-value[2] <= 2 and value[0] == cost:
                samples.append(value)
                if len(samples) >= 2:
                    break
            else:
                samples = []
        if len(samples) < 2 or self.cancel_requested():
            if self.reader.expansion_visible(self._latest.image):
                self._tap(CancelEquipmentCapacityExpansion())
            return EquipmentCapacityExpansionResult(before,None,cost,0,"expansion_popup_unverified")
        # Dispatch once. Any exception or missing effect terminates the intent.
        self._tap(ConfirmEquipmentCapacityExpansion())
        after = self._inventory_after(0, predicate=lambda v: v.capacity == before.capacity+4)
        return EquipmentCapacityExpansionResult(before,after,cost,1,
                                                 "verified" if after else "effect_inconclusive")

    def _read_next(self, method_name: str, predicate=lambda v: True):
        fact = self._read_consensus(
            method_name,
            after_sequence=self._after_sequence, predicate=predicate,
        )
        if fact is not None:
            self._after_sequence = fact.sequence
        return fact

    def _read_consensus(self, method_name: str, *, after_sequence: int, predicate=lambda value: True):
        deadline = self.clock() + self.sample_timeout
        samples = []
        examined_sequences: set[int] = set()
        # OCR consensus still uses at most four recent positive samples.  The
        # physical Sell transition may expose many fresh animation frames
        # before Item Count becomes readable, so bound observation separately
        # instead of exhausting the read on the first four frames.
        while len(examined_sequences) < 48 and self.clock() < deadline:
            if self.cancel_requested():
                return None
            snapshot = self.source.get_frame()
            if (
                snapshot.sequence <= after_sequence
                or snapshot.sequence in examined_sequences
                or snapshot.timestamp < self._not_before
                or not 0 <= self.clock() - snapshot.timestamp <= 2.0
            ):
                self.sleeper(self.sample_interval)
                continue
            examined_sequences.add(snapshot.sequence)
            self._latest = snapshot
            started = self.clock()
            sample = getattr(self.reader, method_name)(
                snapshot.image,
                sequence=snapshot.sequence,
                observed_at=snapshot.timestamp,
            )
            record_best_effort(self.events, "equipment.sell.facts.sample", method=method_name,
                              source_sequence=snapshot.sequence, elapsed_seconds=self.clock()-started,
                              complete=sample is not None,
                              diagnostic=getattr(self.reader, {
                                  "inventory_sample":"last_context_diagnostic",
                                  "detail_sample":"last_detail_diagnostic",
                                  "confirmation_sample":"last_confirmation_diagnostic",
                              }.get(method_name,""),None))
            if sample is not None and predicate(sample) and 0 <= self.clock() - snapshot.timestamp <= 2.0:
                samples.append(sample)
                samples = samples[-4:]
                consensus = consensus_facts(samples, required=2, max_samples=4)
                if consensus is not None:
                    return consensus
            else:
                samples = []
            self.sleeper(self.sample_interval)
        return None

    def _tap(self, action) -> None:
        if self.cancel_requested():
            raise RuntimeError("equipment_action_cancelled")
        if self._latest is None or not 0 <= self.clock() - self._latest.timestamp <= 2.0:
            raise RuntimeError("no fresh frame available for action geometry")
        self.actions.execute(
            action,
            FrameGeometry.from_frame(self._latest.image),
            events=self.events, source_sequence=self._latest.sequence,
        )
        self._after_sequence = self._latest.sequence
        self._not_before = self.clock()


__all__ = ("EquipmentSellRuntime",)
