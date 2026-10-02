"""Standalone Craft entry and direct Quick Menu handoff runtime.

The runtime owns only verified physical entry/return mechanics.  It does not
own Equipment Relief, caller retry, Monster Wave policy, or continuation from Lobby.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import time

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.craft_semantics import (
    CraftContextFact,
    CraftFamily,
    CraftTier,
    QuickMenuCraftFact,
    consensus_craft_facts,
)
from bot.craft_operation import CraftOperationResult, CraftOutcome, execute_craft
from bot.craft_policy import CraftQuantityMode, CraftRequest, requested_quantity
from bot.equipment_sell_semantics import EquipmentInventoryFact, consensus_facts
from bot.quick_menu import QuickMenuHandoff, select_quick_menu_craft_action
from bot.runtime_observer import RuntimeSnapshot
from bot.semantic_actions import (
    CancelCraft,
    ConfirmCraftMaterial,
    DismissCraftResult,
    ExitCraft,
    ExitEquipmentInventory,
    OpenHeroCraft,
    OpenQuickMenu,
    RejectCraftPremium,
    SelectCraftMax,
    SelectQuickMenuCraft,
    SelectQuickMenuInventory,
    SelectQuickMenuTrading,
    QuickMenuLayout,
)


class CraftRouteOutcome(str, Enum):
    ENTERED = "entered"
    QUICK_MENU_OPEN = "quick_menu_open"
    TRADING_REQUESTED = "trading_requested"
    BACK_REQUESTED = "back_requested"
    CAPACITY_BLOCKED = "capacity_blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class CraftRouteResult:
    outcome: CraftRouteOutcome
    inventory_fact: EquipmentInventoryFact | None = None
    craft_fact: CraftContextFact | None = None
    quick_menu_fact: QuickMenuCraftFact | None = None
    reason: str | None = None
    inputs: tuple[str, ...] = ()
    return_base: str | None = None


@dataclass(frozen=True)
class HeroMaterialDrainResult:
    outcome: CraftOutcome
    batches: tuple[CraftOperationResult, ...] = ()
    final_fact: CraftContextFact | None = None
    reason: str | None = None


class CraftRuntime:
    """Enter Craft from Equipment Inventory or hand off its Quick Menu."""

    def __init__(
        self,
        source,
        inventory_reader,
        craft_reader,
        actions: ActionExecutor,
        *,
        sample_timeout: float = 4.0,
        effect_timeout: float = 35.0,
        sample_interval: float = 0.05,
        max_fact_age: float = 5.0,
        cancel_requested: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        events=None,
    ) -> None:
        if not callable(getattr(source, "get_frame", None)):
            raise ValueError("source must provide get_frame()")
        if not callable(getattr(inventory_reader, "inventory_sample", None)):
            raise ValueError("inventory_reader must provide inventory_sample()")
        for method in (
            "quick_menu_sample", "context_sample", "recipe_sample",
            "currency_boundary_sample", "result_sample",
        ):
            if not callable(getattr(craft_reader, method, None)):
                raise ValueError(f"craft_reader must provide {method}()")
        if not isinstance(actions, ActionExecutor):
            raise ValueError("actions must be an ActionExecutor")
        if (
            sample_timeout <= 0
            or effect_timeout <= 0
            or sample_interval < 0
            or max_fact_age <= 0
        ):
            raise ValueError("sampling durations must be positive/non-negative")
        if not all(callable(value) for value in (cancel_requested, clock, sleeper)):
            raise ValueError("runtime callbacks must be callable")
        self.source = source
        self.inventory_reader = inventory_reader
        self.craft_reader = craft_reader
        self.actions = actions
        self.sample_timeout = float(sample_timeout)
        self.effect_timeout = float(effect_timeout)
        self.sample_interval = float(sample_interval)
        self.max_fact_age = float(max_fact_age)
        self.cancel_requested = cancel_requested
        self.clock = clock
        self.sleeper = sleeper
        self.events = events
        self._latest = None
        self._after_sequence = 0
        self._not_before = 0.0
        self._return_base = None

    def enter(self) -> CraftRouteResult:
        """Require one free Equipment slot before any Craft navigation input."""

        inputs: list[str] = []
        inventory = self._read_consensus(
            self.inventory_reader,
            "inventory_sample",
            after_sequence=0,
            consensus=consensus_facts,
        )
        if inventory is None or not self._fresh(inventory):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                inventory_fact=inventory,
                reason="cancelled" if self.cancel_requested() else "equipment_capacity_unreadable_or_stale",
            )
        free_slots = inventory.capacity - inventory.item_count
        if free_slots < 1:
            return CraftRouteResult(
                CraftRouteOutcome.CAPACITY_BLOCKED,
                inventory_fact=inventory,
                reason="no_free_equipment_slot",
            )
        if self.cancel_requested():
            return CraftRouteResult(CraftRouteOutcome.CANCELLED, inventory_fact=inventory, reason="cancelled")

        self._tap(OpenQuickMenu())
        inputs.append("open_quick_menu")
        menu = self._read_consensus(
            self.craft_reader,
            "quick_menu_sample",
            after_sequence=inventory.sequence,
            consensus=consensus_craft_facts,
        )
        if menu is None or not self._fresh(menu):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                inventory_fact=inventory,
                quick_menu_fact=menu,
                reason="cancelled" if self.cancel_requested() else "quick_menu_not_verified",
                inputs=tuple(inputs),
            )
        if self.cancel_requested():
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED, inventory_fact=inventory,
                quick_menu_fact=menu, reason="cancelled", inputs=tuple(inputs),
            )

        self._tap(SelectQuickMenuCraft())
        inputs.append("select_craft")
        craft = self._read_consensus(
            self.craft_reader,
            "context_sample",
            after_sequence=menu.sequence,
            consensus=consensus_craft_facts,
        )
        if craft is None or not self._fresh(craft):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                inventory_fact=inventory,
                craft_fact=craft,
                quick_menu_fact=menu,
                reason="cancelled" if self.cancel_requested() else "fresh_craft_not_verified",
                inputs=tuple(inputs),
            )
        return CraftRouteResult(
            CraftRouteOutcome.ENTERED,
            inventory_fact=inventory,
            craft_fact=craft,
            quick_menu_fact=menu,
            inputs=tuple(inputs),
        )

    def open_quick_menu_or_handoff(self) -> CraftRouteResult:
        """Open Quick Menu directly from fresh Craft; never normalize to Lobby."""

        craft = self._read_consensus(
            self.craft_reader,
            "context_sample",
            after_sequence=0,
            consensus=consensus_craft_facts,
        )
        if craft is None or not self._fresh(craft):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                craft_fact=craft,
                reason="cancelled" if self.cancel_requested() else "craft_context_unreadable_or_stale",
            )
        if self.cancel_requested():
            return CraftRouteResult(CraftRouteOutcome.CANCELLED, craft_fact=craft, reason="cancelled")
        self._tap(OpenQuickMenu())
        menu = self._read_consensus(
            self.craft_reader,
            "quick_menu_sample",
            after_sequence=craft.sequence,
            consensus=consensus_craft_facts, diagnostic=self._quick_menu_diagnostic,
        )
        if menu is None or not self._fresh(menu):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                craft_fact=craft,
                quick_menu_fact=menu,
                reason="cancelled" if self.cancel_requested() else "quick_menu_not_verified",
                inputs=("open_quick_menu",),
            )
        return CraftRouteResult(
            CraftRouteOutcome.QUICK_MENU_OPEN,
            craft_fact=craft,
            quick_menu_fact=menu,
            inputs=("open_quick_menu",),
        )

    def probe_equipment_capacity(self) -> CraftRouteResult:
        """Read current Equipment slots and prove return to this Craft visit."""
        # Capacity is relevant only when this branch will create Equipment.
        current = self.observe_context(after_sequence=0)
        if current.outcome is not CraftRouteOutcome.ENTERED:
            return current
        if current.craft_fact.weapon_material is None:
            return CraftRouteResult(CraftRouteOutcome.FAILED, craft_fact=current.craft_fact,
                                    reason="weapon_material_unavailable")
        if current.craft_fact.weapon_material < 49:
            return current
        opened = self.open_quick_menu_or_handoff()
        if opened.outcome is not CraftRouteOutcome.QUICK_MENU_OPEN:
            return opened
        assert opened.quick_menu_fact is not None
        if self.cancel_requested():
            return CraftRouteResult(CraftRouteOutcome.CANCELLED, reason="cancelled",
                                    inputs=opened.inputs)
        # Labels become readable before this menu accepts Inventory input.
        # Live acquisition raced its transition; wait once, then re-prove the
        # same overlay on newer frames. Never retry the selection tap.
        self.sleeper(0.35)
        ready_menu = self._read_consensus(
            self.craft_reader, "quick_menu_sample",
            after_sequence=opened.quick_menu_fact.sequence,
            consensus=consensus_craft_facts,
            diagnostic=self._quick_menu_diagnostic,
        )
        if ready_menu is None or not self._fresh(ready_menu):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                reason="cancelled" if self.cancel_requested() else "quick_menu_not_verified",
                inputs=opened.inputs,
            )
        if self.cancel_requested():
            return CraftRouteResult(CraftRouteOutcome.CANCELLED, reason="cancelled",
                                    inputs=opened.inputs)
        self._tap(SelectQuickMenuInventory())
        inputs = (*opened.inputs, "select_inventory")
        inventory = self._read_consensus(
            self.inventory_reader, "inventory_sample",
            after_sequence=ready_menu.sequence,
            consensus=consensus_facts, diagnostic=self._capacity_probe_diagnostic,
        )
        if inventory is None or not self._fresh(inventory):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                inventory_fact=inventory,
                reason="cancelled" if self.cancel_requested() else "equipment_capacity_unreadable_or_stale",
                inputs=inputs,
            )
        if self.cancel_requested():
            return CraftRouteResult(CraftRouteOutcome.CANCELLED, inventory_fact=inventory,
                                    reason="cancelled", inputs=inputs)
        self._tap(ExitEquipmentInventory())
        from bot.catalog import SCREEN_LOBBY
        self._return_base = SCREEN_LOBBY
        inputs = (*inputs, "back_to_craft")
        restored = self.observe_context(after_sequence=inventory.sequence)
        if restored.outcome is not CraftRouteOutcome.ENTERED or restored.craft_fact is None:
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if restored.outcome is CraftRouteOutcome.CANCELLED
                else CraftRouteOutcome.FAILED,
                inventory_fact=inventory, craft_fact=restored.craft_fact,
                reason="cancelled" if restored.outcome is CraftRouteOutcome.CANCELLED
                else "craft_not_restored",
                inputs=inputs,
            )
        if inventory.capacity - inventory.item_count < 1:
            return CraftRouteResult(CraftRouteOutcome.CAPACITY_BLOCKED,
                                    inventory_fact=inventory, craft_fact=restored.craft_fact,
                                    reason="no_free_equipment_slot", inputs=inputs)
        return CraftRouteResult(CraftRouteOutcome.ENTERED,
                                inventory_fact=inventory, craft_fact=restored.craft_fact,
                                inputs=inputs)

    def note_inventory_return(self):
        """Known physical contract: this Craft visit subsequently exits to Lobby."""
        from bot.catalog import SCREEN_LOBBY
        self._return_base = SCREEN_LOBBY

    def enter_from_verified_quick_menu(
        self,
        handoff: QuickMenuHandoff,
        menu_snapshot: RuntimeSnapshot,
    ) -> CraftRouteResult:
        """Consume the direct caller handoff and verify fresh Craft context."""

        if not isinstance(handoff, QuickMenuHandoff):
            raise ValueError("handoff must be QuickMenuHandoff")
        if (
            not isinstance(menu_snapshot, RuntimeSnapshot)
            or not handoff.allows(menu_snapshot)
            or handoff.layout is not QuickMenuLayout.SHIFTED
            or not 0.0 <= self.clock() - menu_snapshot.timestamp <= self.max_fact_age
        ):
            return CraftRouteResult(
                CraftRouteOutcome.FAILED,
                reason="quick_menu_origin_handoff_invalid",
            )
        if self.cancel_requested():
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED,
                reason="cancelled",
            )
        try:
            action = select_quick_menu_craft_action(handoff.origin)
        except ValueError:
            return CraftRouteResult(
                CraftRouteOutcome.FAILED,
                reason="quick_menu_craft_target_not_authorized",
            )
        self._return_base = None
        self.actions.execute(action, menu_snapshot.geometry)
        handoff.invalidate()
        craft = self._read_consensus(
            self.craft_reader,
            "context_sample",
            after_sequence=menu_snapshot.sequence,
            consensus=consensus_craft_facts,
            diagnostic=self._craft_entry_diagnostic,
        )
        if craft is None or not self._fresh(craft):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED
                if self.cancel_requested()
                else CraftRouteOutcome.FAILED,
                craft_fact=craft,
                reason=(
                    "cancelled"
                    if self.cancel_requested()
                    else "fresh_craft_not_verified"
                ),
                inputs=("select_craft",),
            )
        return CraftRouteResult(
            CraftRouteOutcome.ENTERED,
            craft_fact=craft,
            inputs=("select_craft",),
        )

    def request_back_to_origin(self) -> CraftRouteResult:
        """Emit Craft Back once; the caller verifies the known branch postcondition."""

        craft = self._read_consensus(
            self.craft_reader,
            "context_sample",
            after_sequence=0,
            consensus=consensus_craft_facts,
        )
        if craft is None or not self._fresh(craft):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED
                if self.cancel_requested()
                else CraftRouteOutcome.FAILED,
                craft_fact=craft,
                reason=(
                    "cancelled"
                    if self.cancel_requested()
                    else "craft_context_unreadable_or_stale"
                ),
            )
        if self.cancel_requested():
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED,
                craft_fact=craft,
                reason="cancelled",
            )
        self._tap(ExitCraft())
        return CraftRouteResult(
            CraftRouteOutcome.BACK_REQUESTED,
            craft_fact=craft,
            inputs=("back_to_origin",),
            return_base=self._return_base,
        )

    def execute(self, request: CraftRequest) -> CraftOperationResult:
        """Execute one bounded Craft action from an already-open clean Craft."""

        if not isinstance(request, CraftRequest):
            raise ValueError("request must be CraftRequest")
        before = self._read_consensus(
            self.craft_reader,
            "context_sample",
            after_sequence=0,
            consensus=consensus_craft_facts,
        )
        if before is None or not self._fresh(before):
            return CraftOperationResult(
                CraftOutcome.CANCELLED if self.cancel_requested() else CraftOutcome.FAILED,
                before_fact=before,
                reason="cancelled" if self.cancel_requested() else "craft_context_unreadable_or_stale",
            )
        self._after_sequence = before.sequence
        target = requested_quantity(request, material=before.material_for(request.family) or 0,
                                    unit_cost=before.hero_cost_for(request.family) or 0, ui_cap=10)
        expected_material = (before.material_for(request.family) -
                             target * before.hero_cost_for(request.family)
                             if target is not None else None)
        recipe_before_max = None
        max_dispatched = False

        def read_recipe():
            nonlocal recipe_before_max, expected_material
            if max_dispatched:
                baseline = recipe_before_max
                desired = requested_quantity(
                    request, material=before.material_for(request.family) or 0,
                    unit_cost=baseline.unit_cost, ui_cap=baseline.quantity_cap,
                )
                return self._read_next("recipe_sample", predicate=lambda value: (
                    value.family is baseline.family and value.tier is baseline.tier
                    and value.currency is baseline.currency
                    and value.unit_cost == baseline.unit_cost
                    and value.quantity_cap == baseline.quantity_cap
                    and value.quantity == desired
                ))
            recipe_before_max = self._read_next("recipe_sample")
            if recipe_before_max is not None:
                quantity = requested_quantity(
                    request, material=before.material_for(request.family) or 0,
                    unit_cost=recipe_before_max.unit_cost,
                    ui_cap=recipe_before_max.quantity_cap,
                )
                expected_material = (before.material_for(request.family) -
                                     quantity * recipe_before_max.unit_cost
                                     if quantity is not None else None)
            return recipe_before_max

        def select_max():
            nonlocal max_dispatched
            self._tap(SelectCraftMax())
            max_dispatched = True

        result = execute_craft(
            request=request,
            before=before,
            open_recipe=lambda: self._tap(OpenHeroCraft(request.family)),
            read_recipe=read_recipe,
            select_max=select_max,
            cancel_recipe=lambda: self._tap(CancelCraft()),
            confirm_material=lambda: self._tap(ConfirmCraftMaterial()),
            read_result=lambda: self._read_next(
                "result_sample", timeout=self.effect_timeout
            ),
            dismiss_result=lambda: self._tap(DismissCraftResult()),
            read_context=lambda: self._read_effect_context(request.family, expected_material),
            read_currency_boundary=lambda: self._read_next(
                "currency_boundary_sample"
            ),
            reject_karats=lambda: self._tap(RejectCraftPremium()),
            cancel_requested=self.cancel_requested,
            clock=self.clock,
            max_fact_age=self.max_fact_age,
        )
        from bot.event_log import record_best_effort
        record_best_effort(self.events, "craft.operation.result", outcome=result.outcome.value,
                          reason=result.reason, inputs=result.inputs,
                          before_material=before.material_for(request.family),
                          expected_material=expected_material,
                          after_material=result.after_fact.material_for(request.family)
                          if result.after_fact else None,
                          quantity=result.recipe_fact.quantity if result.recipe_fact else None)
        return result

    def _read_effect_context(self, family, expected_material):
        """Wait for the economic effect after dismissal without another input."""
        deadline = self.clock() + self.sample_timeout
        last_valid = None
        from bot.event_log import record_best_effort
        while self.clock() < deadline:
            fact = self._read_next("context_sample", timeout=deadline - self.clock())
            if fact is None or not self._fresh(fact):
                break
            last_valid = fact
            matched = fact.material_for(family) == expected_material
            record_best_effort(self.events, "craft.effect.sample", sequence=fact.sequence,
                              actual_material=fact.material_for(family),
                              expected_material=expected_material, matched=matched,
                              reader=getattr(self.craft_reader, "last_context_diagnostic", None))
            if matched:
                return fact
            if self.cancel_requested():
                return None
            self.sleeper(self.sample_interval)
        return last_valid if last_valid is not None and self._fresh(last_valid) else None

    def drain_hero_material(self, *, max_batches: int) -> HeroMaterialDrainResult:
        """Drain the entered Hero Weapon Craft context with verified progress."""
        if isinstance(max_batches, bool) or not isinstance(max_batches, int) or max_batches < 1:
            raise ValueError("max_batches must be positive")
        batches: list[CraftOperationResult] = []
        previous: CraftContextFact | None = None
        request = CraftRequest(
            family=CraftFamily.WEAPON, tier=CraftTier.HERO,
            quantity_mode=CraftQuantityMode.MAX_AVAILABLE,
        )
        for _ in range(max_batches):
            if self.cancel_requested():
                return HeroMaterialDrainResult(CraftOutcome.CANCELLED, tuple(batches), previous)
            current = self._read_consensus(
                self.craft_reader, "context_sample",
                after_sequence=0 if previous is None else previous.sequence,
                consensus=consensus_craft_facts,
            )
            if current is None or not self._fresh(current):
                return HeroMaterialDrainResult(
                    CraftOutcome.FAILED, tuple(batches), previous,
                    "fresh_craft_context_unavailable",
                )
            if current.weapon_hero_cost is None:
                return HeroMaterialDrainResult(
                    CraftOutcome.FAILED, tuple(batches), current,
                    "weapon_cost_unavailable",
                )
            if current.weapon_hero_cost != 49:
                return HeroMaterialDrainResult(
                    CraftOutcome.FAILED, tuple(batches), current,
                    "unexpected_hero_recipe_cost",
                )
            if current.weapon_material is None:
                return HeroMaterialDrainResult(
                    CraftOutcome.FAILED, tuple(batches), current,
                    "weapon_material_unavailable",
                )
            if current.weapon_material < 49:
                return HeroMaterialDrainResult(CraftOutcome.SUCCESS, tuple(batches), current)
            result = self.execute(request)
            batches.append(result)
            if result.outcome is not CraftOutcome.SUCCESS:
                return HeroMaterialDrainResult(
                    result.outcome, tuple(batches), result.after_fact, result.reason,
                )
            if (result.before_fact is None or result.after_fact is None
                    or result.before_fact.weapon_material != current.weapon_material
                    or result.after_fact.sequence <= result.before_fact.sequence
                    or result.after_fact.weapon_material >= result.before_fact.weapon_material):
                return HeroMaterialDrainResult(
                    CraftOutcome.FAILED, tuple(batches), result.after_fact,
                    "craft_progress_not_proven",
                )
            previous = result.after_fact
            if previous.weapon_material < 49:
                return HeroMaterialDrainResult(CraftOutcome.SUCCESS, tuple(batches), previous)
        return HeroMaterialDrainResult(
            CraftOutcome.FAILED, tuple(batches), previous, "craft_batch_budget_exhausted",
        )

    def select_trading_from_open_menu(self, *, after_sequence: int) -> CraftRouteResult:
        """Use a fresh local Craft Quick Menu fact for the modal handoff."""
        menu = self._read_consensus(
            self.craft_reader, "quick_menu_sample",
            after_sequence=after_sequence, consensus=consensus_craft_facts,
        )
        if menu is None or not self._fresh(menu):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                quick_menu_fact=menu, reason="fresh_craft_quick_menu_unavailable",
            )
        if self.cancel_requested():
            return CraftRouteResult(CraftRouteOutcome.CANCELLED, quick_menu_fact=menu)
        self._tap(SelectQuickMenuTrading())
        return CraftRouteResult(
            CraftRouteOutcome.TRADING_REQUESTED, quick_menu_fact=menu,
            inputs=("select_trading",),
        )

    def observe_context(self, *, after_sequence: int) -> CraftRouteResult:
        """Prove Trading's X restored Craft before another Craft action."""
        craft = self._read_consensus(
            self.craft_reader, "context_sample",
            after_sequence=after_sequence, consensus=consensus_craft_facts,
        )
        if craft is None or not self._fresh(craft):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED if self.cancel_requested() else CraftRouteOutcome.FAILED,
                craft_fact=craft, reason="craft_not_restored",
            )
        return CraftRouteResult(CraftRouteOutcome.ENTERED, craft_fact=craft)

    def _read_next(self, method_name: str, *, timeout: float | None = None, predicate=lambda value: True):
        fact = self._read_consensus(
            self.craft_reader,
            method_name,
            after_sequence=self._after_sequence,
            consensus=consensus_craft_facts,
            timeout=timeout,
            diagnostic=self._recipe_diagnostic if method_name == "recipe_sample" else None,
            predicate=predicate,
        )
        if fact is not None:
            self._after_sequence = fact.sequence
        return fact

    def _recipe_diagnostic(self, **fields) -> None:
        from bot.event_log import record_best_effort
        fields["reader"] = getattr(self.craft_reader, "last_recipe_diagnostic", None)
        record_best_effort(self.events, "craft.recipe.sample", **fields)

    def _quick_menu_diagnostic(self, **fields) -> None:
        from bot.event_log import record_best_effort
        fields["reader"] = getattr(self.craft_reader, "last_quick_menu_diagnostic", None)
        record_best_effort(self.events, "craft.quick_menu.sample", **fields)

    def _capacity_probe_diagnostic(self, **fields) -> None:
        from bot.event_log import record_best_effort
        record_best_effort(self.events, "craft.capacity_probe.sample", **fields)

    def _craft_entry_diagnostic(self, **fields) -> None:
        if self.events is not None:
            self.events.record("craft.entry_postcondition_sample", **fields)

    def _read_consensus(
        self, reader, method_name, *, after_sequence, consensus, timeout=None,
        diagnostic=None, predicate=lambda value: True,
    ):
        duration = self.sample_timeout if timeout is None else float(timeout)
        deadline = self.clock() + duration
        # Fast CV rejection during an animation must not exhaust 48 samples
        # in ~3 s and silently replace the caller's 35 s effect deadline.
        max_examined = 48
        if method_name == "result_sample":
            import math
            max_examined = max(48, math.ceil(duration / max(self.sample_interval, 0.01)))
        samples = []
        examined_sequences: set[int] = set()
        while len(examined_sequences) < max_examined and self.clock() < deadline:
            if self.cancel_requested():
                return None
            snapshot = self.source.get_frame()
            if (snapshot.sequence <= after_sequence or snapshot.sequence in examined_sequences
                    or snapshot.timestamp < self._not_before
                    or not 0.0 <= self.clock() - snapshot.timestamp <= self.max_fact_age):
                if diagnostic is not None:
                    diagnostic(sequence=snapshot.sequence, frame_timestamp=snapshot.timestamp,
                               rejection="sequence_before_barrier_or_repeated",
                               after_sequence=after_sequence)
                self.sleeper(self.sample_interval)
                continue
            examined_sequences.add(snapshot.sequence)
            self._latest = snapshot
            sample = getattr(reader, method_name)(
                snapshot.image,
                sequence=snapshot.sequence,
                observed_at=snapshot.timestamp,
            )
            fact = None
            if (sample is not None and predicate(sample)
                    and 0.0 <= self.clock() - snapshot.timestamp <= self.max_fact_age):
                samples = [*samples[-3:], sample]
                fact = consensus(samples, required=2, max_samples=4)
            else:
                samples = []
            if diagnostic is not None:
                diagnostic(
                    sequence=snapshot.sequence, frame_timestamp=snapshot.timestamp,
                    after_sequence=after_sequence,
                    rejection=("reader_rejected" if sample is None else
                               "consensus_pending" if fact is None else None),
                    reader=getattr(reader, "last_context_diagnostic", None),
                    sample_sequences=tuple(item.sequence for item in samples),
                )
            if fact is not None:
                return fact
            self.sleeper(self.sample_interval)
        if diagnostic is not None:
            diagnostic(rejection="timeout", after_sequence=after_sequence,
                       examined_sequences=tuple(sorted(examined_sequences)),
                       elapsed_limit=self.sample_timeout if timeout is None else float(timeout))
        return None

    def _fresh(self, fact) -> bool:
        return bool(
            fact.confirmed
            and 0.0 <= self.clock() - fact.observed_at <= self.max_fact_age
        )

    def _tap(self, action) -> None:
        if self._latest is None:
            raise RuntimeError("no fresh frame available for action geometry")
        if self.cancel_requested():
            raise RuntimeError("craft_cancelled_before_dispatch")
        if not 0.0 <= self.clock() - self._latest.timestamp <= self.max_fact_age:
            raise RuntimeError("craft_dispatch_frame_stale")
        self.actions.execute(action, FrameGeometry.from_frame(self._latest.image),
                             events=self.events, source_sequence=self._latest.sequence)
        self._after_sequence = max(self._after_sequence, self._latest.sequence)
        self._not_before = self.clock()


__all__ = ("CraftRouteOutcome", "CraftRouteResult", "CraftRuntime", "HeroMaterialDrainResult")
