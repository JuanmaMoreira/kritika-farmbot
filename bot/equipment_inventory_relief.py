"""Equipment Inventory owner: restartable tail-first relief after Combine."""
from __future__ import annotations
from dataclasses import dataclass, replace
from bot.equipment_sell_operation import EquipmentSellCandidate, EquipmentSellOutcome, EquipmentSellResult
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_semantics import EquipmentGrade, EquipmentInventoryFact


@dataclass(frozen=True)
class EquipmentCapacityExpansionResult:
    before: EquipmentInventoryFact
    after: EquipmentInventoryFact | None
    cost: int | None
    confirm_count: int
    reason: str

    @property
    def succeeded(self):
        return (self.reason == "verified" and self.confirm_count == 1 and
                self.cost is not None and self.cost > 0 and self.after is not None and
                self.before.confirmed and self.after.confirmed and
                self.after.sequence > self.before.sequence and
                self.after.item_count == self.before.item_count and
                self.after.capacity == self.before.capacity + 4)


@dataclass(frozen=True)
class EquipmentInventoryReliefResult:
    outcome: str
    reason: str
    before: EquipmentInventoryFact | None = None
    after: EquipmentInventoryFact | None = None
    sales: tuple[EquipmentSellResult, ...] = ()
    expansions: tuple[EquipmentCapacityExpansionResult, ...] = ()

    @property
    def succeeded(self):
        return (self.outcome == "success" and self.after is not None and
                self.after.confirmed and self.after.item_count < self.after.capacity)


def slot_candidate(index):
    if type(index) is not int or index < 0:
        raise ValueError("slot index must be non-negative")
    return EquipmentSellCandidate(index // 16 + 1, index % 16)


def execute_inventory_relief(policy: EquipmentSellPolicy, *, read_inventory,
                             inspect, bulk_sell, expand, cancel_requested=lambda: False,
                             max_cycles=96, skip_protected=None, telemetry=lambda **kw: None):
    """Strong sale guards; visual discovery; logical ranges survive valid Bulk.

    Bulk deletes one contiguous group ending at the first sellable candidate
    found from the tail. Certified protected successors retain their order.
    Images never survive a mutation; expansion or contradictory deltas reset
    the logical model as well. The optional discovery callback authorizes no sale.
    """
    if not isinstance(policy, EquipmentSellPolicy) or type(max_cycles) is not int or max_cycles < 1:
        raise ValueError("invalid policy/budget")
    before = after = None
    sales = []
    expansions = []
    cursor = 0
    protected = []
    known_have = known_capacity = None

    def protect(lo, hi):
        protected.append((lo, hi))
        protected.sort()
        merged=[]
        for start,end in protected:
            if merged and start<=merged[-1][1]+1:
                merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
            else:merged.append((start,end))
        protected[:]=merged

    def finish(outcome, reason):
        return EquipmentInventoryReliefResult(outcome, reason, before, after,
                                              tuple(sales), tuple(expansions))
    for _ in range(max_cycles):
        if cancel_requested():
            return finish("cancelled", "cancelled")
        fresh = read_inventory(cursor)
        if fresh is None or not fresh.confirmed or fresh.sequence <= cursor:
            return finish("failed", "inventory_unreadable_or_stale")
        after = fresh
        if (known_have,known_capacity)!=(fresh.item_count,fresh.capacity):
            protected.clear()
        known_have,known_capacity=fresh.item_count,fresh.capacity
        if before is None:
            before = fresh
        if fresh.item_count < fresh.capacity:
            return finish("success", "capacity_available")
        if fresh.capacity % 4 or fresh.capacity > fresh.total_pages * 16:
            return finish("failed", "capacity_grid_contradictory")
        candidate = item = authorization = None
        unknown = False
        index=fresh.capacity-1
        while index>=0:
            if cancel_requested():
                return finish("cancelled", "cancelled")
            certified=next(((lo,hi) for lo,hi in protected if lo<=index<=hi),None)
            if certified is not None:
                telemetry(phase='logical_skip',start=certified[0],end=index)
                index=certified[0]-1
                continue
            selected = slot_candidate(index)
            observed = inspect(selected, fresh)
            if observed is None or not observed.confirmed or not observed.complete or observed.sequence <= fresh.sequence:
                unknown = True
                index-=1
                continue
            cursor = max(cursor, observed.sequence)
            if observed.grade is EquipmentGrade.ETHEREAL_PLUS:
                break
            allowed = policy.authorize(observed)
            if (allowed is None and observed.sell_available is not False and
                policy.authorize(replace(observed, sell_available=True,
                                         grade_visual=observed.grade)) is not None):
                unknown = True
            if allowed is not None:
                candidate, item, authorization = selected, observed, allowed
                break
            # A protected Ethereal category needs positive strong visual guards
            # before either visual grouping or retained logical certification.
            if (observed.grade is EquipmentGrade.ETHEREAL and
                    observed.grade_visual is observed.grade and observed.sell_available is True):
                next_index=index-1
                if skip_protected is not None:
                    try:
                        discovered=skip_protected(selected,fresh,observed)
                        if type(discovered) is int and -1<=discovered<index:
                            next_index=discovered
                    except Exception:
                        telemetry(phase='cv_fallback',index=index)
                protect(next_index+1,index)
                index=next_index
            else:
                index-=1
        if candidate is not None:
            sale = bulk_sell(candidate, authorization, item)
            sales.append(sale)
            if (sale.outcome is not EquipmentSellOutcome.SUCCESS or sale.confirm_count != 1 or
                sale.before is None or sale.after is None or not sale.before.confirmed or not sale.after.confirmed or
                sale.before.sequence <= cursor or sale.after.sequence <= sale.before.sequence or
                sale.before.capacity != fresh.capacity or
                sale.after.sequence <= cursor or sale.after.capacity != fresh.capacity or
                sale.before.item_count != fresh.item_count or
                sale.after.item_count >= sale.before.item_count):
                return finish("failed", "bulk_effect_inconclusive")
            after = sale.after
            cursor = after.sequence
            if after.item_count < after.capacity:
                telemetry(phase='bulk_capacity_available',
                          sold_end=(candidate.page-1)*16+candidate.slot,
                          delta=fresh.item_count-after.item_count,
                          next_unseen_index=None)
                return finish("success", "bulk_freed_capacity")
            delta=fresh.item_count-after.item_count
            sold_end=(candidate.page-1)*16+candidate.slot
            sold_start=sold_end-delta+1
            # No removed member may intersect an already-certified protected
            # range. Otherwise the deletion model is not demonstrated.
            compatible=sold_start>=0 and not unknown
            if sold_end<fresh.capacity-1:
                compatible=compatible and any(
                    lo<=sold_end+1 and hi==fresh.capacity-1 for lo,hi in protected)
            if any(lo<=sold_end and hi>=sold_start for lo,hi in protected):
                compatible=False
            transformed=[]
            if compatible:
                for lo,hi in protected:
                    transformed.append((lo-delta,hi-delta) if lo>sold_end else (lo,hi))
            protected[:]=transformed
            known_have,known_capacity=after.item_count,after.capacity
            telemetry(phase='bulk_scan_transform',sold_start=sold_start,sold_end=sold_end,
                      delta=delta,compatible=compatible,protected_ranges=tuple(protected),
                      new_region_start=max(0,after.capacity-delta),new_region_end=after.capacity-1,
                      next_unseen_index=after.capacity-1)
            continue
        if unknown:
            return finish("failed", "scan_identity_unreadable")
        purchase = expand(fresh)
        expansions.append(purchase)
        if not purchase.succeeded or purchase.after.sequence <= cursor:
            return finish("failed", "expansion_effect_inconclusive")
        after = purchase.after
        protected.clear()
        known_have=known_capacity=None
        cursor = after.sequence
        if after.item_count < after.capacity:
            return finish("success", "expansion_freed_capacity")
        # Newly accessible items must be evaluated from the new tail.
    return finish("failed", "relief_budget_exhausted")
