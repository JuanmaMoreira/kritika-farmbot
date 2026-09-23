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
            FlowStatus.COMPLETED,
            final_snapshot=final,
            after_sequence=final.sequence,
        )

    def enter_craft_from_mw(self, anchor, *, entry_capacity_proven):
        assert entry_capacity_proven is True
        self.trace.append("mw_qm_craft")
        return MonsterWaveNavigationResult(FlowStatus.COMPLETED)

    def enter_trading_from_mw(self, anchor):
        self.trace.append("mw_qm_trading")
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

    def execute(self, request):
        self.trace.append("craft_execute")
        return CraftOperationResult(CraftOutcome.SUCCESS)

    def request_back_to_origin(self):
        self.trace.append("craft_back")
        self.sequence += 1
        return CraftRouteResult(
            CraftRouteOutcome.BACK_REQUESTED,
            craft_fact=_craft_fact(self.sequence),
            inputs=("back_to_origin",),
        )


class FakeKeys:
    def __init__(self, trace, *, gold_full=False):
        self.trace = trace
        self.gold_full = gold_full

    def run(self, *, budget_remaining, recovery_navigation):
        self.trace.append(("keys", budget_remaining))
        if self.gold_full:
            assert recovery_navigation.source == "monster_wave"
            assert recovery_navigation.leave_trading().status is FlowStatus.COMPLETED
            assert recovery_navigation.enter_treasure().status is FlowStatus.COMPLETED
            self.trace.append("drain_all_gold")
            assert recovery_navigation.return_to_trading().status is FlowStatus.COMPLETED
            self.trace.append("retry_silver_to_gold")
        return SimpleNamespace(status=FlowStatus.COMPLETED, error=None)


class FakeMaterials:
    def __init__(self, trace):
        self.trace = trace

    def execute(self, step):
        self.trace.append(("materials", tuple(
            item.trading_item_id for item in step.operations
        )))
        return SimpleNamespace(status=FlowStatus.COMPLETED, error=None)


def _runtime(trace, *, gold_full=False, cancelled=lambda: False):
    navigation = FakeNavigation(trace)
    snapshots = FakeSnapshots(trace)
    craft = FakeCraft(trace)
    return MonsterWaveResourceRouteRuntime(
        navigation,
        snapshots,
        craft,
        FakeKeys(trace, gold_full=gold_full),
        FakeMaterials(trace),
        keys_budget_remaining=3,
        cancel_requested=cancelled,
    )


def test_no_prerequisites_returns_supplied_fresh_snapshot_with_zero_input():
    trace = []
    initial = _anchor(10)

    result = _runtime(trace).execute_plan_once(
        ResourceRoutePlan(ResourceRouteStatus.NO_PREREQUISITES), initial
    )

    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert result.final_snapshot is initial.snapshot
    assert result.final_context is initial.context
    assert trace == []


def test_non_executable_plan_gates_without_input():
    for status in (
        ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
        ResourceRouteStatus.CONTRADICTORY,
    ):
        trace = []
        plan = ResourceRoutePlan(
            status,
            unresolved=(UnresolvedReason(UnresolvedCode.MISSING_BOARD_SNAPSHOT),),
        )
        result = _runtime(trace).execute_plan_once(plan, _anchor(10))
        assert result.status is ResourceRouteExecutionStatus.NON_EXECUTABLE_PLAN
        assert trace == []


def test_craft_then_trading_serializes_both_blocks_through_fresh_mw():
    trace = []
    plan = ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=(
            CraftStep("weapon", "hero", 1),
            TradingSessionStep((KeysPromotionStep(), MATERIALS)),
        ),
    )

    result = _runtime(trace).execute_plan_once(plan, _anchor(10))

    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert result.executed_steps == plan.steps
    assert trace == [
        "mw_qm_craft",
        "craft_execute",
        "craft_back",
        ("fresh_mw", 21),
        "mw_qm_trading",
        ("keys", 3),
        ("materials", ("hero_weapon_crafting_material",)),
        "trading_x_mw",
        ("fresh_mw", 101),
    ]
    assert trace.index("craft_back") < trace.index("mw_qm_trading")
    assert trace.index(("fresh_mw", 21)) < trace.index("mw_qm_trading")


def test_keys_and_materials_share_one_trading_visit_in_required_order():
    trace = []
    plan = ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=(TradingSessionStep((KeysPromotionStep(), MATERIALS)),),
    )

    result = _runtime(trace).execute_plan_once(plan, _anchor(10))

    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace.count("mw_qm_trading") == 1
    assert trace.index(("keys", 3)) < trace.index(
        ("materials", ("hero_weapon_crafting_material",))
    )


def test_mw_gold_full_recovery_uses_no_lobby_and_reopens_trading_from_fresh_mw():
    trace = []
    plan = ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=(TradingSessionStep((KeysPromotionStep(), MATERIALS)),),
    )

    result = _runtime(trace, gold_full=True).execute_plan_once(plan, _anchor(10))

    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace == [
        "mw_qm_trading",
        ("keys", 3),
        "trading_x_mw",
        ("fresh_mw", 101),
        "mw_qm_treasure",
        "drain_all_gold",
        "treasure_back_mw",
        ("fresh_mw", 102),
        "mw_qm_trading",
        "retry_silver_to_gold",
        ("materials", ("hero_weapon_crafting_material",)),
        "trading_x_mw",
        ("fresh_mw", 103),
    ]
    assert all("lobby" not in repr(item).lower() for item in trace)
    assert trace.count("drain_all_gold") == 1
    assert trace.count("retry_silver_to_gold") == 1


def test_materials_only_does_not_run_keys_or_duplicate_trading():
    trace = []
    plan = ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=(TradingSessionStep((MATERIALS,)),),
    )

    result = _runtime(trace).execute_plan_once(plan, _anchor(10))

    assert result.status is ResourceRouteExecutionStatus.SUCCESS
    assert trace.count("mw_qm_trading") == 1
    assert not any(isinstance(item, tuple) and item[0] == "keys" for item in trace)


def test_unsupported_materials_then_keys_order_fails_before_input():
    trace = []
    plan = ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=(TradingSessionStep((MATERIALS, KeysPromotionStep())),),
    )

    result = _runtime(trace).execute_plan_once(plan, _anchor(10))

    assert result.status is ResourceRouteExecutionStatus.NON_EXECUTABLE_PLAN
    assert result.failing_step == "trading_operation_order"
    assert trace == []


def test_cancellation_stops_before_any_input():
    trace = []
    plan = ResourceRoutePlan(
        ResourceRouteStatus.READY,
        steps=(TradingSessionStep((MATERIALS,)),),
    )

    result = _runtime(trace, cancelled=lambda: True).execute_plan_once(
        plan, _anchor(10)
    )

    assert result.status is ResourceRouteExecutionStatus.CANCELLED
    assert trace == []


def test_j_has_no_quick_menu_to_mw_no_replan_and_no_battle_execution():
    import bot.monster_wave_resource_route as module

    source = inspect.getsource(module)
    assert "SelectQuickMenuMonsterWave" not in source
    assert "plan_resource_route" not in source
    assert "StartMonsterWaveSkip" not in source
    assert "ActivateMonsterWaveSkip" not in source
    assert "EquipmentReliefComposer" not in source


class _Observer:
    def __init__(self, snapshots=()):
        self.snapshots = list(snapshots)

    def wait_until(self, condition, **kwargs):
        for snapshot in list(self.snapshots):
            if condition(snapshot):
                self.snapshots.remove(snapshot)
                return snapshot
        raise RuntimeError("timeout")


class _Transition:
    def __init__(self, posts):
        self.posts = list(posts)
        self.actions = []

    def execute(self, name, action, before, *, expected, precondition, **kwargs):
        assert precondition(before)
        final = self.posts.pop(0)
        self.actions.append(action)
        outcome = (
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
            if expected(final)
            else VerifiedTransitionOutcome.TIMEOUT
        )
        return VerifiedTransitionResult(
            name,
            outcome,
            1,
            0,
            final,
            action_source_snapshot=before,
        )


class _CraftNavigationStub:
    def enter_from_verified_quick_menu(self, handoff, *, entry_capacity_proven):
        raise AssertionError("not used")

    def request_back_to_origin(self):
        raise AssertionError("not used")


def test_physical_mw_navigation_uses_open_menu_then_trading_tile_and_x_return():
    anchor = _anchor(1)
    menu = _context(2, SCREEN_MONSTER_WAVE, overlays=(MENU_QUICK,))
    trading = _context(3, SCREEN_TRADING)
    transition = _Transition((menu, trading))
    navigation = MonsterWavePrerequisiteNavigationRuntime(
        _Observer(), transition, _CraftNavigationStub()
    )

    entered = navigation.enter_trading_from_mw(anchor)

    assert entered.status is FlowStatus.COMPLETED
    assert [type(action) for action in transition.actions] == [
        OpenQuickMenu,
        SelectQuickMenuTrading,
    ]

    returned_mw = _mw_context(5)
    leave_transition = _Transition((returned_mw,))
    leave_navigation = MonsterWavePrerequisiteNavigationRuntime(
        _Observer((trading,)), leave_transition, _CraftNavigationStub()
    )
    left = leave_navigation.leave_trading_to_mw()

    assert left.status is FlowStatus.COMPLETED
    assert [type(action) for action in leave_transition.actions] == [CloseTrading]


def test_physical_mw_to_treasure_uses_only_verified_shifted_tile():
    menu = _context(2, SCREEN_MONSTER_WAVE, overlays=(MENU_QUICK,))
    treasure = _context(3, SCREEN_TREASURE)
    transition = _Transition((menu, treasure))
    navigation = MonsterWavePrerequisiteNavigationRuntime(
        _Observer(), transition, _CraftNavigationStub()
    )

    entered = navigation.enter_treasure_from_mw(_anchor(1))

    assert entered.status is FlowStatus.COMPLETED
    assert [type(action) for action in transition.actions] == [
        OpenQuickMenu,
        SelectQuickMenuTreasure,
    ]


def test_snapshot_runtime_reacquires_same_frame_fresh_mw_description():
    context = _mw_context(11)
    runtime = MonsterWaveSnapshotRuntime(
        _Observer((context,)),
        clock=lambda: 11.0,
    )

    result = runtime.acquire(after_sequence=10)

    assert result.status is FlowStatus.COMPLETED
    assert result.fresh is not None
    assert result.fresh.context is context
    assert result.fresh.snapshot.evidence.sequence == 11
