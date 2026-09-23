from unittest.mock import Mock

import numpy as np

from bot.action_executor import (
    ActionExecutor,
    DEFAULT_CRAFT_ACTION_TARGETS,
    DEFAULT_ROTATION_ACTION_TARGETS,
)
from bot.capture import FrameSnapshot
from bot.craft_runtime import CraftRouteOutcome, CraftRuntime
from bot.craft_operation import CraftOutcome
from bot.craft_policy import CraftRequest
from bot.craft_semantics import (
    CraftContextFact,
    CraftCurrency,
    CraftFamily,
    CraftItemType,
    CraftRecipeFact,
    CraftResultFact,
    CraftTier,
    QuickMenuCraftFact,
)
from bot.equipment_sell_semantics import EquipmentInventoryFact
from bot.quick_menu import QuickMenuHandoff
from bot.semantic_actions import QuickMenuLayout


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value

    def sleep(self, amount):
        self.value += max(amount, 0.01)


class Source:
    def __init__(self, sequences):
        self.items = [
            FrameSnapshot(np.zeros((100, 200, 3), dtype=np.uint8), 100.0, sequence)
            for sequence in sequences
        ]
        self.index = 0

    def get_frame(self):
        item = self.items[min(self.index, len(self.items) - 1)]
        self.index += 1
        return item


class InventoryReader:
    def __init__(self, *, count=111, capacity=112, readable=True, observed_at=100.0):
        self.count = count
        self.capacity = capacity
        self.readable = readable
        self.observed_at = observed_at

    def inventory_sample(self, frame, *, sequence, observed_at):
        if not self.readable:
            return None
        return EquipmentInventoryFact(
            item_count=self.count,
            capacity=self.capacity,
            page=7,
            total_pages=22,
            sequence=sequence,
            observed_at=self.observed_at,
            sample_sequences=(sequence,),
        )


class CraftReader:
    def quick_menu_sample(self, frame, *, sequence, observed_at):
        return QuickMenuCraftFact(
            lobby_label="Lobby",
            craft_label="Craft",
            guild_label="Guild",
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
        )

    def context_sample(self, frame, *, sequence, observed_at):
        return CraftContextFact(
            title="Craft",
            rate_label="Rate",
            expert_label="Expert Craft",
            weapon_material=325,
            armor_material=734,
            accessory_material=645,
            weapon_capacity=999,
            armor_capacity=999,
            accessory_capacity=999,
            weapon_hero_cost=49,
            armor_hero_cost=49,
            accessory_hero_cost=49,
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
        )

    def recipe_sample(self, frame, *, sequence, observed_at):
        return CraftRecipeFact(
            family=CraftFamily.WEAPON,
            tier=CraftTier.HERO,
            item_type=CraftItemType.WEAPON,
            currency=CraftCurrency.MATERIAL,
            unit_cost=49,
            quantity=1,
            quantity_cap=10,
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
        )

    def result_sample(self, frame, *, sequence, observed_at):
        return CraftResultFact(
            marker="Laoku's Destructive Sword",
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
        )

    def currency_boundary_sample(self, frame, *, sequence, observed_at):
        return None


def runtime(*, sequences, inventory=None, craft=None, cancelled=lambda: False):
    adb = Mock()
    clock = Clock()
    value = CraftRuntime(
        Source(sequences),
        inventory or InventoryReader(),
        craft or CraftReader(),
        ActionExecutor(adb),
        sample_timeout=0.2,
        sample_interval=0.01,
        cancel_requested=cancelled,
        clock=clock,
        sleeper=clock.sleep,
    )
    return value, adb


def test_one_free_slot_allows_verified_quick_menu_to_craft_entry():
    value, adb = runtime(sequences=range(1, 7))

    result = value.enter()

    assert result.outcome is CraftRouteOutcome.ENTERED
    assert result.inventory_fact.capacity - result.inventory_fact.item_count == 1
    assert result.craft_fact.confirmed
    assert result.inputs == ("open_quick_menu", "select_craft")
    assert adb.tap.call_count == 2


def test_zero_free_slots_causes_zero_craft_navigation_input():
    value, adb = runtime(
        sequences=(1, 2),
        inventory=InventoryReader(count=112, capacity=112),
    )

    result = value.enter()

    assert result.outcome is CraftRouteOutcome.CAPACITY_BLOCKED
    adb.tap.assert_not_called()


def test_unreadable_capacity_fails_closed_with_zero_input():
    value, adb = runtime(
        sequences=(1, 2),
        inventory=InventoryReader(readable=False),
    )

    result = value.enter()

    assert result.outcome is CraftRouteOutcome.FAILED
    assert result.reason == "equipment_capacity_unreadable_or_stale"
    adb.tap.assert_not_called()


def test_stale_capacity_fails_closed_with_zero_input():
    value, adb = runtime(
        sequences=(1, 2),
        inventory=InventoryReader(observed_at=0.0),
    )

    result = value.enter()

    assert result.outcome is CraftRouteOutcome.FAILED
    adb.tap.assert_not_called()


def test_incompatible_source_context_means_no_inventory_fact_and_zero_input():
    value, adb = runtime(
        sequences=(1, 2),
        inventory=InventoryReader(readable=False),
    )

    result = value.enter()

    assert result.inventory_fact is None
    adb.tap.assert_not_called()


def test_stale_craft_evidence_cannot_satisfy_entry():
    class StaleCraftReader(CraftReader):
        def context_sample(self, frame, *, sequence, observed_at):
            fact = super().context_sample(frame, sequence=sequence, observed_at=0.0)
            return fact

    value, adb = runtime(sequences=range(1, 7), craft=StaleCraftReader())

    result = value.enter()

    assert result.outcome is CraftRouteOutcome.FAILED
    assert result.reason == "fresh_craft_not_verified"
    assert adb.tap.call_count == 2


def test_entry_cancellation_propagates_before_any_input():
    value, adb = runtime(sequences=(1, 2), cancelled=lambda: True)

    result = value.enter()

    assert result.outcome is CraftRouteOutcome.CANCELLED
    adb.tap.assert_not_called()


def test_quick_menu_opens_directly_from_craft_without_lobby_normalization():
    value, adb = runtime(sequences=range(1, 5))

    result = value.open_quick_menu_or_handoff()

    assert result.outcome is CraftRouteOutcome.QUICK_MENU_OPEN
    assert result.inputs == ("open_quick_menu",)
    adb.tap.assert_called_once_with(
        int(DEFAULT_ROTATION_ACTION_TARGETS.open_quick_menu[0] * 200),
        int(DEFAULT_ROTATION_ACTION_TARGETS.open_quick_menu[1] * 100),
    )


def test_runtime_execute_returns_success_only_after_fresh_material_decrease():
    class ProductiveCraftReader(CraftReader):
        def context_sample(self, frame, *, sequence, observed_at):
            fact = super().context_sample(frame, sequence=sequence, observed_at=observed_at)
            if sequence >= 7:
                return CraftContextFact(
                    **{
                        **fact.__dict__,
                        "weapon_material": 276,
                    }
                )
            return fact

    value, adb = runtime(sequences=range(1, 9), craft=ProductiveCraftReader())

    result = value.execute(CraftRequest(CraftFamily.WEAPON))

    assert result.outcome is CraftOutcome.SUCCESS
    assert result.inputs == ("open_recipe", "confirm_material", "dismiss_result")
    assert adb.tap.call_count == 3
    safe = DEFAULT_CRAFT_ACTION_TARGETS.dismiss_result_safe_side
    assert adb.tap.call_args_list[-1].args == (int(safe[0] * 200), int(safe[1] * 100))


def test_verified_shifted_handoff_enters_craft_once_with_planner_capacity_gate():
    value, adb = runtime(sequences=range(2, 8))
    handoff = QuickMenuHandoff(
        origin="screen.monster_wave",
        action_source_sequence=0,
        menu_sequence=1,
        layout=QuickMenuLayout.SHIFTED,
    )

    result = value.enter_from_verified_quick_menu(
        handoff,
        entry_capacity_proven=True,
    )

    assert result.outcome is CraftRouteOutcome.ENTERED
    assert result.inputs == ("select_craft",)
    assert handoff.valid is False
    adb.tap.assert_called_once_with(79, 49)


def test_verified_handoff_without_capacity_proof_emits_zero_input():
    value, adb = runtime(sequences=range(2, 8))
    handoff = QuickMenuHandoff(
        origin="screen.monster_wave",
        action_source_sequence=0,
        menu_sequence=1,
        layout=QuickMenuLayout.SHIFTED,
    )

    result = value.enter_from_verified_quick_menu(
        handoff,
        entry_capacity_proven=False,
    )

    assert result.outcome is CraftRouteOutcome.CAPACITY_BLOCKED
    adb.tap.assert_not_called()


def test_craft_back_is_one_public_immediate_origin_action():
    value, adb = runtime(sequences=range(1, 5))

    result = value.request_back_to_origin()

    assert result.outcome is CraftRouteOutcome.BACK_REQUESTED
    assert result.inputs == ("back_to_origin",)
    assert result.craft_fact is not None
    adb.tap.assert_called_once_with(160, 7)


def test_craft_runtime_has_no_neighbor_policy_or_relief_ownership():
    import bot.craft_runtime as module

    source = open(module.__file__, encoding="utf-8").read()

    assert "EquipmentReliefComposer" not in source
    assert "MonsterWave" not in source
    assert "OpenTrading" not in source
    assert "OpenTreasure" not in source
    assert "OpenEquipmentSell" not in source
    assert "OpenEquipmentCombine" not in source

def test_hero_drain_repeats_max_available_with_partial_final_batch():
    from dataclasses import replace
    from bot.craft_operation import CraftOperationResult
    from bot.craft_policy import CraftQuantityMode

    base = CraftReader().context_sample(None, sequence=10, observed_at=100.0)
    facts = [replace(base, weapon_material=amount, sequence=sequence)
             for sequence, amount in ((10, 1040), (20, 550), (30, 60), (40, 11))]
    runtime = CraftRuntime.__new__(CraftRuntime)
    runtime.craft_reader = CraftReader()
    runtime.cancel_requested = lambda: False
    runtime._fresh = lambda fact: True
    reads = iter(facts[:3])
    runtime._read_consensus = lambda *args, **kwargs: next(reads)
    operations = iter([
        CraftOperationResult(CraftOutcome.SUCCESS, before_fact=facts[0], after_fact=facts[1]),
        CraftOperationResult(CraftOutcome.SUCCESS, before_fact=facts[1], after_fact=facts[2]),
        CraftOperationResult(CraftOutcome.SUCCESS, before_fact=facts[2], after_fact=facts[3]),
    ])
    modes = []
    def execute(request):
        modes.append(request.quantity_mode)
        return next(operations)
    runtime.execute = execute
    result = runtime.drain_hero_material(max_batches=3)
    assert result.outcome is CraftOutcome.SUCCESS
    assert result.final_fact.weapon_material == 11
    assert modes == [CraftQuantityMode.MAX_AVAILABLE] * 3


def test_hero_drain_requires_progress_and_respects_budget():
    from dataclasses import replace
    from bot.craft_operation import CraftOperationResult
    fact = CraftReader().context_sample(None, sequence=10, observed_at=100.0)
    fact = replace(fact, weapon_material=800)
    runtime = CraftRuntime.__new__(CraftRuntime)
    runtime.craft_reader = CraftReader()
    runtime.cancel_requested = lambda: False
    runtime._fresh = lambda value: True
    runtime._read_consensus = lambda *args, **kwargs: fact
    runtime.execute = lambda request: CraftOperationResult(
        CraftOutcome.SUCCESS, before_fact=fact,
        after_fact=replace(fact, sequence=11),
    )
    assert runtime.drain_hero_material(max_batches=2).reason == "craft_progress_not_proven"
    runtime.execute = lambda request: CraftOperationResult(
        CraftOutcome.SUCCESS, before_fact=fact,
        after_fact=replace(fact, sequence=11, weapon_material=310),
    )
    assert runtime.drain_hero_material(max_batches=1).reason == "craft_batch_budget_exhausted"
