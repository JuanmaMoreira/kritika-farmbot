"""Equipment-specific live adapter for one verified sale.

The caller owns navigation and capture lifecycle.  This adapter only samples
the current Equipment Inventory surface, delegates policy/order to the pure
operation, and translates its four physical intents through ActionExecutor.
"""

from __future__ import annotations

import time
import numpy as np
import cv2
from dataclasses import dataclass
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
from bot.equipment_block_scan import EquipmentBlockMatcher
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


@dataclass(frozen=True)
class _SelectedSalePanel:
    candidate: object
    inventory: object
    item: object
    frame: object
    input_barrier: float


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
        self._selected_sale=None;self._scan_policy=None
        self._latest = None
        self._after_sequence = 0
        self._not_before = 0.0
        self.events = events
        try:
            self.block_matcher = EquipmentBlockMatcher()
        except (OSError, ValueError, KeyError, TypeError):
            self.block_matcher = None
        self._block_reference = None
        self._block_stats = dict(comparisons=0,cv_slots_skipped=0,blocks_skipped=0,
                                 discovery_panels=0,panels_opened=0,fallback_count=0,logical_slots_skipped=0,
                                 protected_panel_opens=0,sellable_panel_opens=0,same_item_reopens=0)

    def _block_crop(self, image, center):
        try:
            return self.block_matcher.crop(image,center) if self.block_matcher else None
        except Exception:
            return None

    def execute(self, request: EquipmentSellRequest, *, selected=None) -> EquipmentSellResult:
        """Execute at most one confirm; never navigate, scan or retry input."""

        if not isinstance(request, EquipmentSellRequest):
            raise ValueError("request must be EquipmentSellRequest")
        before = selected.inventory if selected is not None else self._read_consensus("inventory_sample", after_sequence=self._after_sequence)
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
        if selected is None:self._after_sequence = before.sequence

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
            selected_item=selected.item if selected is not None else None,
            selection_current=lambda:self._selected_panel_current(selected),
        )

    def execute_relief(self, policy):
        from bot.equipment_inventory_relief import execute_inventory_relief
        started = self.clock()
        self._scan_policy=policy;self._selected_sale=None
        self._block_reference = None
        self._block_stats = dict(comparisons=0,cv_slots_skipped=0,blocks_skipped=0,
                                 discovery_panels=0,panels_opened=0,fallback_count=0,logical_slots_skipped=0,
                                 protected_panel_opens=0,sellable_panel_opens=0,same_item_reopens=0)
        result = execute_inventory_relief(
            policy, read_inventory=self._inventory_after,
            inspect=self._inspect, bulk_sell=self._bulk_candidate,
            expand=self._expand, cancel_requested=self.cancel_requested,
            skip_protected=self._skip_protected,telemetry=self._scan_telemetry,
        )
        record_best_effort(self.events, "equipment.inventory_relief.result",
                          outcome=result.outcome, reason=result.reason,
                          before_count=getattr(result.before,"item_count",None),
                          after_count=getattr(result.after,"item_count",None),
                          capacity=getattr(result.after,"capacity",None),
                          sales=len(result.sales), expansions=len(result.expansions),
                          elapsed_seconds=self.clock()-started)
        record_best_effort(self.events, 'equipment.sell.scan.summary',
                          **self._block_stats,elapsed_seconds=self.clock()-started)
        self._block_reference = None;self._selected_sale=None;self._scan_policy=None
        return result

    def _scan_telemetry(self, **fields):
        if fields.get('phase')=='logical_skip':
            self._block_stats['logical_slots_skipped']+=fields['end']-fields['start']+1
        if fields.get('phase')=='cv_fallback':
            self._block_stats['fallback_count']+=1
        record_best_effort(self.events,'equipment.sell.scan.transition',**fields)

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
        selected_inventory=self._navigate_page(candidate.page, inventory)
        center=self.actions.equipment_targets.inventory_slots[candidate.slot]
        first=self._block_crop(self._latest.image,center)
        self._tap(SelectEquipmentInventorySlot(candidate.slot))
        detail = self._read_next("detail_sample")
        allowed=self._scan_policy.authorize(detail) if self._scan_policy is not None else None
        selected=bool(allowed is not None and self._latest is not None and
            self._latest.sequence==detail.sequence and 0<=self.clock()-detail.observed_at<=2.)
        if selected:
            self._selected_sale=_SelectedSalePanel(candidate,selected_inventory,detail,self._latest,self._not_before)
            self._block_reference=None
            self._block_stats['sellable_panel_opens']+=1
        else:
            self._block_stats['protected_panel_opens']+=1
            self._tap(CloseEquipmentDetail())
            # Prove closing the detail preserved Inventory and the scan list.
            closed = self._inventory_after(0)
            if closed is None or (closed.item_count,closed.capacity,closed.page) != (
                    inventory.item_count,inventory.capacity,candidate.page):
                raise RuntimeError("detail_close_unverified")
            second=self._block_crop(self._latest.image,center)
            self._block_reference=(candidate,(inventory.item_count,inventory.capacity),(first,second))
        if self._block_stats:
            self._block_stats['discovery_panels']+=1
        record_best_effort(self.events, "equipment.sell.scan.item", page=candidate.page,
                          slot=candidate.slot, name=getattr(detail,"name",None),
                          grade=getattr(getattr(detail,"grade",None),"value",None),
                          equipment_type=getattr(getattr(detail,"equipment_type",None),"value",None),
                          enhance=getattr(detail,"enhance",None),
                          sell_available=getattr(detail,"sell_available",None),
                          grade_visual=getattr(getattr(detail,"grade_visual",None),"value",None),
                          source_sequence=getattr(detail,"sequence",None))
        return detail

    def _skip_protected(self, candidate, inventory, item):
        """Return the first differing logical slot; never return item policy."""
        index=(candidate.page-1)*16+candidate.slot
        reference=self._block_reference
        if (self.block_matcher is None or reference is None or reference[0]!=candidate or
                reference[1]!=(inventory.item_count,inventory.capacity)):
            self._scan_telemetry(phase='cv_fallback',index=index)
            return index-1
        refs=reference[2]
        previous_page=candidate.page
        next_index=index-1
        while next_index>=0 and not self.cancel_requested():
            page,slot=divmod(next_index,16);page+=1
            if page!=previous_page:
                self._navigate_page(page,inventory)
                previous_page=page
            if self._latest is None or not 0<=self.clock()-self._latest.timestamp<=2:
                self._inventory_after(0)
            if self._latest is None or not 0<=self.clock()-self._latest.timestamp<=2:
                self._scan_telemetry(phase='cv_fallback',index=next_index)
                break
            center=self.actions.equipment_targets.inventory_slots[slot]
            query=self._block_crop(self._latest.image,center)
            score=self.block_matcher.score(refs,query)
            self._block_stats['comparisons']+=1
            if score is None or score<self.block_matcher.threshold:
                if score is None or score>=self.block_matcher.uncertain_floor:
                    self._block_stats['fallback_count']+=1
                break
            self._block_stats['cv_slots_skipped']+=1
            next_index-=1
        skipped=index-next_index-1
        if skipped:
            self._block_stats['blocks_skipped']+=1
        record_best_effort(self.events,'equipment.sell.scan.block',anchor_index=index,
                          next_candidate_index=next_index,slots_skipped=skipped,
                          reference_phase_count=len(refs))
        return next_index

    def _selected_panel_current(self,selected):
        # Strong fresh panel + unchanged input lineage authorize the item.
        # Correlation only invalidates continuity; it never authorizes Sell.
        def reject(reason, **fields):
            record_best_effort(self.events,"equipment.sell.selected_panel.continuity",
                              outcome="invalidated",reason=reason,**fields)
            return False
        if (selected is None or self._selected_sale is not selected or
                self._after_sequence!=selected.item.sequence or self._not_before!=selected.input_barrier or
                self._latest is not selected.frame):
            return reject("input_or_candidate_changed")
        if not 0<=self.clock()-selected.item.observed_at<=2.:
            return reject("strong_panel_stale")
        frame=self.source.get_frame()
        if (frame.sequence<selected.item.sequence or frame.image.shape!=selected.frame.image.shape or
                not 0<=self.clock()-frame.timestamp<=2.):
            return reject("current_frame_stale_or_geometry_changed")
        h,w=frame.image.shape[:2];scores={}
        # Live codec/faint inventory glow changes pixels of an unchanged panel.
        # Thresholds retain the real item-change negative separation; policy
        # and Bulk popup remain the destructive authorization boundaries.
        for name,region,threshold in (
                ("title",(.514,.255,.731,.310),.999),
                ("grade_type",(.560,.315,.750,.365),.995),
                ("sell",(.765,.452,.817,.503),.999)):
            x1,y1,x2,y2=region
            a=frame.image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]
            b=selected.frame.image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]
            if a.size==0:return reject("empty_panel_region",region=name)
            if np.array_equal(a,b):score=1.
            elif np.std(a)==0 or np.std(b)==0:score=0.
            else:score=float(cv2.matchTemplate(a,b,cv2.TM_CCOEFF_NORMED).max())
            scores[name]=score
            if not np.isfinite(score) or score<threshold:
                return reject("panel_region_changed",region=name,score=score,threshold=threshold)
        self._latest=frame
        record_best_effort(self.events,"equipment.sell.selected_panel.continuity",
                          outcome="retained",source_sequence=frame.sequence,scores=scores)
        return True

    def _bulk_candidate(self, candidate, authorization, item):
        self._block_reference=None
        from bot.equipment_sell_operation import EquipmentSellRequest
        selected=self._selected_sale
        if selected is not None and (selected.candidate!=candidate or selected.item!=item):
            return EquipmentSellResult(EquipmentSellOutcome.DENIED,'selected_candidate_changed')
        if selected is None:self._block_stats['same_item_reopens']+=1
        result = self.execute(EquipmentSellRequest(authorization, candidate, expected_item=item),selected=selected)
        record_best_effort(self.events, "equipment.sell.bulk.result", outcome=result.outcome.value,
                          reason=result.reason, confirms=result.confirm_count,
                          logical_index=(candidate.page-1)*16+candidate.slot,
                          before_count=getattr(result.before,"item_count",None),
                          after_count=getattr(result.after,"item_count",None))
        return result

    def _expand(self, before):
        self._block_reference=None
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
        self._selected_sale=None
        if self.cancel_requested():
            raise RuntimeError("equipment_action_cancelled")
        if self._latest is None or not 0 <= self.clock() - self._latest.timestamp <= 2.0:
            raise RuntimeError("no fresh frame available for action geometry")
        self.actions.execute(
            action,
            FrameGeometry.from_frame(self._latest.image),
            events=self.events, source_sequence=self._latest.sequence,
        )
        if isinstance(action, SelectEquipmentInventorySlot):
            self._block_stats['panels_opened']+=1
        self._after_sequence = self._latest.sequence
        self._not_before = self.clock()


__all__ = ("EquipmentSellRuntime",)
