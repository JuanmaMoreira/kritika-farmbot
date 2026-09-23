"""Standalone Craft entry and direct Quick Menu handoff runtime.

The runtime owns only verified physical entry/return mechanics.  It does not
own Equipment Relief, caller retry, Monster Wave policy, or Lobby recovery.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import time

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.craft_semantics import (
    CraftContextFact,
    QuickMenuCraftFact,
    consensus_craft_facts,
)
from bot.craft_operation import CraftOperationResult, CraftOutcome, execute_craft
from bot.craft_policy import CraftRequest
from bot.equipment_sell_semantics import EquipmentInventoryFact, consensus_facts
from bot.quick_menu import QuickMenuHandoff
from bot.semantic_actions import (
    CancelCraft,
    ConfirmCraftMaterial,
    DismissCraftResult,
    ExitCraft,
    OpenHeroCraft,
    OpenQuickMenu,
    RejectCraftPremium,
    SelectCraftMax,
    SelectQuickMenuCraft,
    QuickMenuLayout,
)


class CraftRouteOutcome(str, Enum):
    ENTERED = "entered"
    QUICK_MENU_OPEN = "quick_menu_open"
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
        self._latest = None
        self._after_sequence = 0

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
            consensus=consensus_craft_facts,
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

    def enter_from_verified_quick_menu(
        self,
        handoff: QuickMenuHandoff,
        *,
        entry_capacity_proven: bool,
    ) -> CraftRouteResult:
        """Consume one shifted-menu handoff and verify fresh Craft context.

        The caller owns the immediate origin and may pass capacity proof only
        when the immutable route plan already passed Craft's free-slot gate.
        """

        if not isinstance(handoff, QuickMenuHandoff):
            raise ValueError("handoff must be QuickMenuHandoff")
        if entry_capacity_proven is not True:
            return CraftRouteResult(
                CraftRouteOutcome.CAPACITY_BLOCKED,
                reason="craft_entry_capacity_not_proven",
            )
        if not handoff.valid or handoff.layout is not QuickMenuLayout.SHIFTED:
            return CraftRouteResult(
                CraftRouteOutcome.FAILED,
                reason="quick_menu_origin_handoff_invalid",
            )
        menu = self._read_consensus(
            self.craft_reader,
            "quick_menu_sample",
            after_sequence=handoff.menu_sequence,
            consensus=consensus_craft_facts,
        )
        if menu is None or not self._fresh(menu):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED
                if self.cancel_requested()
                else CraftRouteOutcome.FAILED,
                quick_menu_fact=menu,
                reason=(
                    "cancelled"
                    if self.cancel_requested()
                    else "quick_menu_not_verified"
                ),
            )
        if self.cancel_requested():
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED,
                quick_menu_fact=menu,
                reason="cancelled",
            )
        self._tap(SelectQuickMenuCraft())
        handoff.invalidate()
        craft = self._read_consensus(
            self.craft_reader,
            "context_sample",
            after_sequence=menu.sequence,
            consensus=consensus_craft_facts,
        )
        if craft is None or not self._fresh(craft):
            return CraftRouteResult(
                CraftRouteOutcome.CANCELLED
                if self.cancel_requested()
                else CraftRouteOutcome.FAILED,
                craft_fact=craft,
                quick_menu_fact=menu,
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
            quick_menu_fact=menu,
            inputs=("select_craft",),
        )

    def request_back_to_origin(self) -> CraftRouteResult:
        """Emit Craft Back once; the caller must verify the immediate origin."""

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
        return execute_craft(
            request=request,
            before=before,
            open_recipe=lambda: self._tap(OpenHeroCraft(request.family)),
            read_recipe=lambda: self._read_next("recipe_sample"),
            select_max=lambda: self._tap(SelectCraftMax()),
            cancel_recipe=lambda: self._tap(CancelCraft()),
            confirm_material=lambda: self._tap(ConfirmCraftMaterial()),
            read_result=lambda: self._read_next(
                "result_sample", timeout=self.effect_timeout
            ),
            dismiss_result=lambda: self._tap(DismissCraftResult()),
            read_context=lambda: self._read_next("context_sample"),
            read_currency_boundary=lambda: self._read_next(
                "currency_boundary_sample"
            ),
            reject_karats=lambda: self._tap(RejectCraftPremium()),
            cancel_requested=self.cancel_requested,
            clock=self.clock,
            max_fact_age=self.max_fact_age,
        )

    def _read_next(self, method_name: str, *, timeout: float | None = None):
        fact = self._read_consensus(
            self.craft_reader,
            method_name,
            after_sequence=self._after_sequence,
            consensus=consensus_craft_facts,
            timeout=timeout,
        )
        if fact is not None:
            self._after_sequence = fact.sequence
        return fact

    def _read_consensus(
        self, reader, method_name, *, after_sequence, consensus, timeout=None
    ):
        deadline = self.clock() + (
            self.sample_timeout if timeout is None else float(timeout)
        )
        samples = []
        examined_sequences: set[int] = set()
        while len(examined_sequences) < 48 and self.clock() < deadline:
            if self.cancel_requested():
                return None
            snapshot = self.source.get_frame()
            if snapshot.sequence <= after_sequence or snapshot.sequence in examined_sequences:
                self.sleeper(self.sample_interval)
                continue
            examined_sequences.add(snapshot.sequence)
            self._latest = snapshot
            sample = getattr(reader, method_name)(
                snapshot.image,
                sequence=snapshot.sequence,
                observed_at=snapshot.timestamp,
            )
            if sample is not None:
                samples = [*samples[-3:], sample]
                fact = consensus(samples, required=2, max_samples=4)
                if fact is not None:
                    return fact
            self.sleeper(self.sample_interval)
        return None

    def _fresh(self, fact) -> bool:
        return bool(
            fact.confirmed
            and 0.0 <= self.clock() - fact.observed_at <= self.max_fact_age
        )

    def _tap(self, action) -> None:
        if self._latest is None:
            raise RuntimeError("no fresh frame available for action geometry")
        self.actions.execute(action, FrameGeometry.from_frame(self._latest.image))


__all__ = ("CraftRouteOutcome", "CraftRouteResult", "CraftRuntime")
