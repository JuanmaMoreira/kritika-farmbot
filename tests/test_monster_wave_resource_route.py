import inspect
from types import SimpleNamespace

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.craft_operation import CraftOperationResult, CraftOutcome
from bot.craft_runtime import CraftRouteOutcome, CraftRouteResult
from bot.craft_semantics import CraftContextFact
from bot.flow_contracts import FlowStatus
from bot.monster_wave_board_snapshot import build_monster_wave_board_snapshot
from bot.monster_wave_resource_route import (
    FreshMonsterWaveSnapshot,
    MonsterWaveNavigationResult,
    MonsterWavePrerequisiteNavigationRuntime,
    MonsterWaveResourceRouteRuntime,
    MonsterWaveSnapshotResult,
    MonsterWaveSnapshotRuntime,
    ResourceRouteExecutionStatus,
)
from bot.monster_wave_semantics import MW_NEEDS_TICKETS, SCREEN_MONSTER_WAVE
from bot.catalog import MENU_QUICK
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resource_route_planner import (
    CraftStep,
    KeysPromotionStep,
    ResourceRoutePlan,
    ResourceRouteStatus,
    TradingMaterialOperation,
    TradingMaterialsStep,
    TradingSessionStep,
    UnresolvedCode,
    UnresolvedReason,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center_semantics import SCREEN_TRADING
from bot.treasure_center_semantics import SCREEN_TREASURE
from bot.verified_transition import (
    VerifiedTransitionOutcome,
    VerifiedTransitionResult,
)
from bot.semantic_actions import (
    CloseTrading,
    OpenQuickMenu,
    SelectQuickMenuTrading,
    SelectQuickMenuTreasure,
)


def _mw_context(sequence):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    observations = (
        Observation(MW_NEEDS_TICKETS, 1.0, ObservationSource.LOCAL_CV),
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=SCREEN_MONSTER_WAVE,
            overlays=(),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _context(sequence, base, *, overlays=()):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), ()),
        ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=base,
            overlays=overlays,
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _anchor(sequence):
    context = _mw_context(sequence)
    snapshot = build_monster_wave_board_snapshot(
        context,
        after_sequence=sequence - 1,
        now=float(sequence),
    )
    assert snapshot is not None
    return FreshMonsterWaveSnapshot(context, snapshot)


def _craft_fact(sequence):
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
        observed_at=float(sequence),
        sample_sequences=(sequence - 1, sequence),
    )


MATERIALS = TradingMaterialsStep((
    TradingMaterialOperation(
        "hero_weapon_crafting_material",
        "weapon_material",
        "hero_weapon_material",
        2,
    ),
))


class FakeSnapshots:
    def __init__(self, trace):
        self.trace = trace

    def acquire(self, *, after_sequence):
        self.trace.append(("fresh_mw", after_sequence))
        return MonsterWaveSnapshotResult(
            FlowStatus.COMPLETED,
            fresh=_anchor(after_sequence + 1),
        )


class FakeNavigation:
    def __init__(self, trace):
        self.trace = trace
        self.sequence = 100
    def _mw_result(self, name):
        self.trace.append(name)
        self.sequence += 1
        final = _mw_context(self.sequence)
        return MonsterWaveNavigationResult(
            FlowStatus.COMPLETED, final_snapshot=final, after_sequence=final.sequence,
        )
    def enter_craft_from_mw(self, anchor):
        self.trace.append("mw_qm_craft")
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED)
    def continue_from_craft_lobby(self, *, after_sequence):
        self.trace.extend(["expected_lobby", "lobby_hub_mw"])
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED, after_sequence=after_sequence + 2)
    def enter_trading_from_mw(self, anchor):
        self.trace.append("mw_qm_trading")
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED)
    def enter_trading_from_craft(self):
        self.trace.append("craft_qm_trading")
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED)
    def leave_trading_to_craft(self):
        self.trace.append("trading_x_craft")
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED)
    def enter_treasure_from_mw(self, anchor):
        self.trace.append("mw_qm_treasure")
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED)
    def leave_trading_to_mw(self):
        return self._mw_result("trading_x_mw")
    def leave_treasure_to_mw(self):
        return self._mw_result("treasure_back_mw")


class FakeCraft:
    def __init__(self, trace):
        self.trace = trace
        self.sequence = 20
        self.return_base = "screen.lobby"
    def probe_equipment_capacity(self):
        self.trace.append("probe_capacity")
        return CraftRouteResult(CraftRouteOutcome.ENTERED)
    def drain_hero_material(self, *, max_batches):
        assert max_batches > 0
        self.trace.append("drain_hero")
        return SimpleNamespace(outcome=CraftOutcome.SUCCESS)
    def request_back_to_origin(self):
        self.trace.append("craft_back")
        self.sequence += 1
        return CraftRouteResult(
            CraftRouteOutcome.BACK_REQUESTED,
            craft_fact=_craft_fact(self.sequence),
            return_base=self.return_base,
        )


class FakeKeys:
    def __init__(self, trace, *, gold_full=False):
        self.trace = trace
        self.gold_full = gold_full
    def run(self, *, budget_remaining, defer_recovery):
        assert defer_recovery is True
        self.trace.append(("keys", budget_remaining))
        if self.gold_full:
            self.trace.append("ack_gold_full")
        return SimpleNamespace(
            status=FlowStatus.COMPLETED, pending=object() if self.gold_full else None,
            trade_attempts=("silver_to_gold",) if self.gold_full else (),
            remaining_budget=(6 if self.gold_full else 7),
        )
    def resolve_pending(self, pending, *, budget_remaining, recovery_navigation):
        assert recovery_navigation.source == "monster_wave"
        assert recovery_navigation.leave_trading().status is FlowStatus.COMPLETED
        assert recovery_navigation.enter_treasure().status is FlowStatus.COMPLETED
        self.trace.append("drain_all_gold")
        assert recovery_navigation.return_to_trading().status is FlowStatus.COMPLETED
        self.trace.append("retry_same_silver_to_gold")
        return SimpleNamespace(status=FlowStatus.COMPLETED)


class FakeMaterials:
    def __init__(self, trace):
        self.trace = trace
    def execute(self, step, *, max_batches):
        assert max_batches == 32
        self.trace.append("drain_weapon")
        return SimpleNamespace(status=FlowStatus.COMPLETED)


def _runtime(trace, *, gold_full=False, cancelled=lambda: False):
    return MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), FakeCraft(trace),
        FakeKeys(trace, gold_full=gold_full), FakeMaterials(trace),
        keys_budget_remaining=3, cancel_requested=cancelled,
    )


def _plan(*, craft=False, materials=False, keys=True):
    steps = []
    if craft:
        steps.append(CraftStep("weapon", "hero"))
    if keys or materials:
        operations = [KeysPromotionStep()]
        if materials:
            operations.append(TradingMaterialsStep())
        steps.append(TradingSessionStep(tuple(operations)))
    return ResourceRoutePlan(
        ResourceRouteStatus.READY if steps else ResourceRouteStatus.NO_PREREQUISITES,
        steps=tuple(steps),
    )


def test_no_prerequisites_sends_no_input():
    trace = []
    initial = _anchor(10)
    result = _runtime(trace).execute_plan_once(_plan(keys=False), initial)
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert result.final_snapshot is initial.snapshot
    assert trace == []


def test_keys_only_never_enters_general():
    trace = []
    result = _runtime(trace).execute_plan_once(_plan(), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace == ["mw_qm_trading", ("keys", 3), "trading_x_mw", ("fresh_mw", 101)]


def test_craft_inventory_branch_exits_to_expected_lobby_then_mw():
    trace = []
    result = _runtime(trace).execute_plan_once(
        _plan(craft=True, keys=False), _anchor(10),
    )
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace == ["mw_qm_craft", "probe_capacity", "drain_hero", "craft_back", "expected_lobby", "lobby_hub_mw", ("fresh_mw", 23)]


def test_zero_equipment_slots_surface_blocker_before_any_craft_action():
    trace = []
    class FullCraft(FakeCraft):
        def probe_equipment_capacity(self):
            self.trace.append("probe_capacity")
            return CraftRouteResult(CraftRouteOutcome.CAPACITY_BLOCKED,
                                    reason="no_free_equipment_slot")
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), FullCraft(trace),
        FakeKeys(trace), FakeMaterials(trace), keys_budget_remaining=3,
    )
    result = runtime.execute_plan_once(_plan(craft=True, keys=False), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED
    assert result.capability_result.outcome is CraftRouteOutcome.CAPACITY_BLOCKED
    assert trace == ["mw_qm_craft", "probe_capacity"]


def test_j_accepts_lazy_keys_budget_and_preserves_deferred_remainder():
    trace = []
    class LazyKeys(FakeKeys):
        def resolve_pending(self, pending, *, budget_remaining, recovery_navigation):
            self.trace.append(("keys_remainder", budget_remaining))
            return super().resolve_pending(
                pending, budget_remaining=budget_remaining,
                recovery_navigation=recovery_navigation,
            )
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), FakeCraft(trace),
        LazyKeys(trace, gold_full=True), FakeMaterials(trace),
    )
    result = runtime.execute_plan_once(_plan(keys=True), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert ("keys", None) in trace
    assert ("keys_remainder", 6) in trace


def test_unreadable_equipment_capacity_fails_closed_before_craft():
    trace = []
    class UnreadableCraft(FakeCraft):
        def probe_equipment_capacity(self):
            self.trace.append("probe_capacity")
            return CraftRouteResult(CraftRouteOutcome.FAILED,
                                    reason="equipment_capacity_unreadable_or_stale")
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), UnreadableCraft(trace),
        FakeKeys(trace), FakeMaterials(trace), keys_budget_remaining=3,
    )
    result = runtime.execute_plan_once(_plan(craft=True, keys=False), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.STEP_FAILED
    assert trace == ["mw_qm_craft", "probe_capacity"]


def test_craft_and_keys_return_to_mw_before_keys_only_trading():
    trace = []
    result = _runtime(trace).execute_plan_once(_plan(craft=True), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace == [
        "mw_qm_craft", "probe_capacity", "drain_hero", "craft_back", "expected_lobby", "lobby_hub_mw", ("fresh_mw", 23),
        "mw_qm_trading", ("keys", 3), "trading_x_mw", ("fresh_mw", 101),
    ]


def test_materials_pay_for_keys_then_general_without_craft():
    trace = []
    result = _runtime(trace).execute_plan_once(
        _plan(materials=True), _anchor(10),
    )
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace == [
        "mw_qm_trading", ("keys", 3), "drain_weapon",
        "trading_x_mw", ("fresh_mw", 101),
    ]


def test_trading_modal_restores_craft_and_second_drain_precedes_back():
    trace = []
    plan = _plan(craft=True, materials=True)
    result = _runtime(trace).execute_plan_once(plan, _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert result.executed_steps == plan.steps
    assert trace == [
        "mw_qm_craft", "probe_capacity", "drain_hero", "craft_qm_trading",
        ("keys", 3), "drain_weapon", "trading_x_craft",
        "drain_hero", "craft_back", "expected_lobby", "lobby_hub_mw", ("fresh_mw", 23),
    ]


def test_combined_gold_full_defers_treasure_until_after_craft_back_to_mw():
    trace = []
    result = _runtime(trace, gold_full=True).execute_plan_once(
        _plan(craft=True, materials=True), _anchor(10),
    )
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace == [
        "mw_qm_craft", "probe_capacity", "drain_hero", "craft_qm_trading",
        ("keys", 3), "ack_gold_full", "drain_weapon", "trading_x_craft",
        "drain_hero", "craft_back", "expected_lobby", "lobby_hub_mw", ("fresh_mw", 23),
        "mw_qm_treasure", "drain_all_gold", "treasure_back_mw",
        ("fresh_mw", 101), "mw_qm_trading", "retry_same_silver_to_gold",
        "trading_x_mw", ("fresh_mw", 102),
    ]


def test_material_gold_full_defers_until_trading_x_returns_mw():
    trace = []
    result = _runtime(trace, gold_full=True).execute_plan_once(
        _plan(materials=True), _anchor(10),
    )
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace.index("drain_weapon") < trace.index("trading_x_mw") < trace.index("mw_qm_treasure")


def test_cancellation_before_input_and_unsupported_order_fail_closed():
    trace = []
    cancelled = _runtime(trace, cancelled=lambda: True).execute_plan_once(
        _plan(materials=True), _anchor(10),
    )
    assert cancelled.status is ResourceRouteExecutionStatus.CANCELLED
    assert trace == []
    bad = ResourceRoutePlan(ResourceRouteStatus.READY,
        steps=(TradingSessionStep((TradingMaterialsStep(), KeysPromotionStep())),))
    invalid = _runtime(trace).execute_plan_once(bad, _anchor(10))
    assert invalid.status is ResourceRouteExecutionStatus.NON_EXECUTABLE_PLAN
    assert trace == []

def test_craft_modal_navigation_uses_one_x_and_fresh_restored_craft():
    trace = []
    class Craft:
        def enter_from_verified_quick_menu(self, *args, **kwargs):
            pass
        def request_back_to_origin(self):
            pass
        def open_quick_menu_or_handoff(self):
            trace.append("craft_open_menu")
            return CraftRouteResult(
                CraftRouteOutcome.QUICK_MENU_OPEN,
                quick_menu_fact=SimpleNamespace(sequence=20),
            )
        def select_trading_from_open_menu(self, *, after_sequence):
            assert after_sequence == 20
            trace.append("craft_select_trading")
            return CraftRouteResult(
                CraftRouteOutcome.TRADING_REQUESTED,
                quick_menu_fact=SimpleNamespace(sequence=21),
            )
        def observe_context(self, *, after_sequence):
            assert after_sequence == 30
            trace.append("observe_restored_craft")
            return CraftRouteResult(
                CraftRouteOutcome.ENTERED, craft_fact=_craft_fact(31),
            )
    class Observer:
        def wait_until(self, predicate, **kwargs):
            snapshot = _context(30, SCREEN_TRADING)
            assert predicate(snapshot)
            return snapshot
    class Actions:
        def execute(self, action, geometry):
            assert isinstance(action, CloseTrading)
            trace.append("trading_x")
    class Transition:
        actions = Actions()
        def execute(self, *args, **kwargs):
            raise AssertionError("unexpected transition")
    nav = MonsterWavePrerequisiteNavigationRuntime(
        Observer(), Transition(), Craft(),
    )
    entered = nav.enter_trading_from_craft()
    assert entered.status is FlowStatus.COMPLETED
    left = nav.leave_trading_to_craft()
    assert left.status is FlowStatus.COMPLETED
    assert left.after_sequence == 31
    assert trace == [
        "craft_open_menu", "craft_select_trading", "trading_x",
        "observe_restored_craft",
    ]

def test_failed_materials_keeps_deferred_pending_in_result():
    trace = []
    class FailedMaterials:
        def execute(self, step, *, max_batches):
            trace.append("materials_failed")
            return SimpleNamespace(status=FlowStatus.FAILED, error="typed_boundary")
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), FakeCraft(trace),
        FakeKeys(trace, gold_full=True), FailedMaterials(),
        keys_budget_remaining=3,
    )
    result = runtime.execute_plan_once(_plan(materials=True), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.STEP_FAILED
    assert result.pending is not None
    assert trace == ["mw_qm_trading", ("keys", 3), "ack_gold_full", "materials_failed"]


def _blocked_craft_fact(sequence):
    from bot.equipment_sell_semantics import EquipmentInventoryFact
    inventory = EquipmentInventoryFact(
        item_count=112, capacity=112, page=7, total_pages=22,
        sequence=sequence, observed_at=float(sequence),
        sample_sequences=(sequence - 1, sequence),
    )
    return CraftRouteResult(
        CraftRouteOutcome.CAPACITY_BLOCKED,
        inventory_fact=inventory, craft_fact=_craft_fact(sequence + 1),
        reason="no_free_equipment_slot",
    )


def _free_craft_result(sequence):
    return CraftRouteResult(CraftRouteOutcome.ENTERED, craft_fact=_craft_fact(sequence))


def test_craft_capacity_blocked_preserved_without_relief():
    trace = []
    class FullCraft(FakeCraft):
        def probe_equipment_capacity(self):
            self.trace.append("probe_capacity")
            return _blocked_craft_fact(20)
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), FullCraft(trace),
        FakeKeys(trace), FakeMaterials(trace), keys_budget_remaining=3,
    )
    result = runtime.execute_plan_once(_plan(craft=True, keys=False), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED
    assert result.failing_step == "craft"
    assert result.capability_result.outcome is CraftRouteOutcome.CAPACITY_BLOCKED
    assert trace == ["mw_qm_craft", "probe_capacity"]


def test_craft_blocker_invokes_composer_once_and_retries_only_craft_then_continues():
    from bot.equipment_relief import EquipmentReliefOutcome, EquipmentReliefResult
    trace = []

    class FlakyCraft(FakeCraft):
        def __init__(self, trace):
            super().__init__(trace)
            self.probes = 0
        def probe_equipment_capacity(self):
            self.probes += 1
            self.trace.append("probe_capacity")
            if self.probes == 1:
                return _blocked_craft_fact(20)
            return _free_craft_result(30)
        def drain_hero_material(self, *, max_batches):
            self.trace.append("drain_hero")
            return SimpleNamespace(outcome=CraftOutcome.SUCCESS)
        def observe_context(self, *, after_sequence):
            self.trace.append("observe_craft")
            return CraftRouteResult(
                CraftRouteOutcome.ENTERED, craft_fact=_craft_fact(after_sequence + 1),
            )

    # Offline composition: the fake composer drives J's acquire/execute
    # hooks (probe+drain) exactly as the real composer would after a
    # successful Combine, proving retry-only-Craft + continue in the SAME
    # execute_plan_once. J's production Craft->Combine entry fails closed
    # without input until HIL proves it; the fake bypasses only that entry.
    class SuccessComposer:
        def __init__(self):
            self.calls = 0
        def run(self, request):
            self.calls += 1
            trace.append("composer_once")
            assert request.sell_plan is None
            ctx0 = request.acquire_context(None)
            r0 = request.execute_operation(request.operation_request, ctx0.value)
            assert request.is_equipment_full(r0) is True
            trace.append("combine_once")
            ctx1 = request.acquire_context(100)
            r1 = request.execute_operation(request.operation_request, ctx1.value)
            return EquipmentReliefResult(
                EquipmentReliefOutcome.CALLER_RESULT, "caller.retry_after_combine",
                caller_result=r1, caller_attempt_count=2,
                combine_invocation_count=1,
            )
    composer = SuccessComposer()
    craft = FlakyCraft(trace)
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), craft,
        FakeKeys(trace), FakeMaterials(trace), keys_budget_remaining=3,
        equipment_relief=composer,
    )
    result = runtime.execute_plan_once(_plan(craft=True, keys=False), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert composer.calls == 1
    # Retry ONLY the CraftStep (second probe + single drain), then the SAME
    # execute_plan_once continues to Back+fresh MW. No trading, no replan.
    assert trace == [
        "mw_qm_craft", "probe_capacity",
        "composer_once", "combine_once", "observe_craft",
        "probe_capacity", "drain_hero",
        "craft_back", "expected_lobby", "lobby_hub_mw", ("fresh_mw", 23),
    ]


def test_craft_relief_failure_stops_without_further_input_and_no_sell():
    from bot.equipment_relief import EquipmentReliefOutcome, EquipmentReliefResult
    trace = []
    sell_calls = []

    class FullCraft(FakeCraft):
        def probe_equipment_capacity(self):
            self.trace.append("probe_capacity")
            return _blocked_craft_fact(20)
        def drain_hero_material(self, *, max_batches):
            raise AssertionError("no drain after failed relief")
        def observe_context(self, *, after_sequence):
            # Retry acquire after Combine still sees full Craft; exercised
            # once by the fake composer to prove still-blocked -> fail closed.
            self.trace.append("observe_craft")
            return CraftRouteResult(
                CraftRouteOutcome.ENTERED, craft_fact=_craft_fact(after_sequence + 1),
            )

    class FailingComposer:
        def __init__(self):
            self.calls = 0
        def run(self, request):
            self.calls += 1
            trace.append("composer_once")
            assert request.sell_plan is None
            # Exercise J's hooks like the real composer: initial blocked,
            # Combine once (simulated), retry still blocked -> no Sell plan.
            ctx0 = request.acquire_context(None)
            r0 = request.execute_operation(request.operation_request, ctx0.value)
            assert request.is_equipment_full(r0) is True
            trace.append("combine_once")
            return EquipmentReliefResult(
                EquipmentReliefOutcome.SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE,
                "sell.plan",
            )

    composer = FailingComposer()
    runtime = MonsterWaveResourceRouteRuntime(
        FakeNavigation(trace), FakeSnapshots(trace), FullCraft(trace),
        FakeKeys(trace), FakeMaterials(trace), keys_budget_remaining=3,
        equipment_relief=composer,
    )
    result = runtime.execute_plan_once(_plan(craft=True, keys=False), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED
    assert result.failing_step == "craft"
    assert composer.calls == 1
    assert sell_calls == []
    # No drain, no trading, no Back, no fresh MW after failed relief.
    assert trace == ["mw_qm_craft", "probe_capacity", "composer_once", "combine_once"]


def test_craft_missing_verified_popup_stops_before_combine_or_sell():
    from bot.equipment_relief import EquipmentReliefComposer
    trace = []
    combine_calls = []
    sell_calls = []

    class FullCraft(FakeCraft):
        def probe_equipment_capacity(self):
            self.trace.append("probe_capacity")
            return _blocked_craft_fact(20)
        def drain_hero_material(self, *, max_batches):
            raise AssertionError("no drain when entry fails closed")
        def observe_context(self, *, after_sequence):
            raise AssertionError("no observe when entry fails closed")

    class Combine:
        def run(self, plan, cancel_requested):
            combine_calls.append(plan)
            raise AssertionError("no Combine without verified Craft entry")

    class Sell:
        def execute(self, request):
            sell_calls.append(request)
            raise AssertionError("no authorized MW Sell plan")

    composer = EquipmentReliefComposer(Combine(), Sell())
    class MissingPopupNavigation(FakeNavigation):
        def enter_combine_from_craft(self, capacity):
            raise ValueError("craft_full_popup_not_verified")
    runtime = MonsterWaveResourceRouteRuntime(
        MissingPopupNavigation(trace), FakeSnapshots(trace), FullCraft(trace),
        FakeKeys(trace), FakeMaterials(trace), keys_budget_remaining=3,
        equipment_relief=composer,
    )
    result = runtime.execute_plan_once(_plan(craft=True, keys=False), _anchor(10))
    assert result.status is ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED
    assert result.failing_step == "craft"
    assert combine_calls == []
    assert sell_calls == []
    assert trace == ["mw_qm_craft", "probe_capacity"]
