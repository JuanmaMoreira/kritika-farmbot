"""Bounded composition of G, I, J and the existing MW SKIP activity."""

from types import SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.flow_contracts import FlowStatus
from bot.monster_wave_actions import DeclineMonsterWaveInventory, ExitMonsterWave
from bot.monster_wave_activity import MonsterWaveResult
from bot.monster_wave_board_reader import BOARD_ROWS, MonsterWaveBoardRow, MonsterWaveBoardSample
from bot.monster_wave_board_snapshot import (
    BoardEvidence, BoardPopup, MaxState, MonsterWaveBoardSnapshot, Tickets,
    build_monster_wave_board_snapshot,
)
from bot.monster_wave_resource_route import (
    FreshMonsterWaveSnapshot, ResourceRouteExecutionResult,
    ResourceRouteExecutionStatus,
)
from bot.monster_wave_semantics import MW_BOARD, MW_NEEDS_TICKETS, POPUP_MW_BOARD, SCREEN_MONSTER_WAVE
from bot.monster_wave_standalone import (
    FreshMonsterWaveBoard, MonsterWaveBoardAcquisitionRuntime,
    MonsterWaveStandaloneMode as Mode, MonsterWaveStandaloneNavigationRuntime,
    MonsterWaveStandaloneRequest as Request, MonsterWaveStandaloneRunner,
    MonsterWaveStandaloneStatus as Status,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resource_route_planner import (
    IncomingRewardFact, NonBoardResourceFacts, ResourceRoutePlan,
    ResourceRouteStatus, TradingSessionStep, KeysPromotionStep,
    UnresolvedCode, UnresolvedReason,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransitionOutcome, VerifiedTransitionResult


def context(sequence, *, popup=False, foreign=False, base=None):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    names = (MW_BOARD,) if popup else (MW_NEEDS_TICKETS,)
    observations = tuple(Observation(name, 1.0, ObservationSource.LOCAL_CV) for name in names)
    base = base or ("screen.lobby" if foreign else SCREEN_MONSTER_WAVE)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(ResolutionStatus.RESOLVED, sequence, float(sequence),
                      base_context=base, overlays=(POPUP_MW_BOARD,) if popup else ()),
        RuntimeFacts(), FrameGeometry.from_frame(image),
    )


ROWS = tuple(MonsterWaveBoardRow(item_id, 1, 100) for item_id, _, _ in BOARD_ROWS)
FACTS = NonBoardResourceFacts(incoming_rewards=tuple(
    IncomingRewardFact(item_id, 0) for item_id, _, _ in BOARD_ROWS
))
READY = ResourceRoutePlan(ResourceRouteStatus.READY,
                          steps=(TradingSessionStep((KeysPromotionStep(),)),))
NONE = ResourceRoutePlan(ResourceRouteStatus.NO_PREREQUISITES)
UNRESOLVED = ResourceRoutePlan(
    ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
    unresolved=(UnresolvedReason(UnresolvedCode.MISSING_INCOMING_REWARD),),
)


def board():
    ctx = context(10, popup=True)
    snap = MonsterWaveBoardSnapshot(
        None, Tickets.UNKNOWN, None, MaxState(None, None, None, None),
        BoardPopup.PRESENT_WITH_ROWS, (), ROWS, BoardEvidence(10, 10.0, (9, 10)),
    )
    return FreshMonsterWaveBoard(ctx, snap, 8)


def anchor(sequence):
    ctx = context(sequence)
    snap = build_monster_wave_board_snapshot(ctx, after_sequence=sequence - 1, now=float(sequence))
    return FreshMonsterWaveSnapshot(ctx, snap)


class Harness:
    def __init__(self, plan=NONE, *, route_status=ResourceRouteExecutionStatus.SUCCESS,
                 exit_status=FlowStatus.COMPLETED, activity_status=FlowStatus.COMPLETED):
        self.calls = []
        self.plan = plan
        self.route_status = route_status
        self.exit_status = exit_status
        self.activity_status = activity_status
        self.initial = board()
        self.clean = anchor(12)

    def acquire(self):
        self.calls.append("acquire")
        return self.initial

    def planner(self, planning):
        self.calls.append("plan")
        assert planning.non_board is FACTS
        assert planning.after_sequence == self.initial.after_sequence
        return self.plan

    def close_board(self, acquired):
        self.calls.append("close")
        assert acquired is self.initial
        return FlowStatus.COMPLETED, self.clean, None

    def execute_plan_once(self, plan, clean):
        self.calls.append("J")
        assert plan is self.plan and clean is self.clean
        final = anchor(15)
        return ResourceRouteExecutionResult(
            self.route_status,
            executed_steps=plan.steps if self.route_status is ResourceRouteExecutionStatus.SUCCESS else (),
            final_context=final.context if self.route_status is ResourceRouteExecutionStatus.SUCCESS else None,
            final_snapshot=final.snapshot if self.route_status is ResourceRouteExecutionStatus.SUCCESS else None,
        )

    def exit_to_battle_mode(self, clean):
        self.calls.append("exit")
        assert isinstance(clean, FreshMonsterWaveSnapshot)
        if self.exit_status is not FlowStatus.COMPLETED:
            return self.exit_status, None
        final = context(clean.context.sequence + 1, base="screen.battle_mode_select")
        return self.exit_status, VerifiedTransitionResult(
            "monster_wave.standalone.exit_to_battle_mode",
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT, 1, 0, final,
        )

    def run(self):
        self.calls.append("MW")
        return MonsterWaveResult(self.activity_status)

    def runner(self):
        return MonsterWaveStandaloneRunner(self, self, self, self,
                                           planner=self.planner, clock=lambda: 10.1)


def test_acquire_only_has_no_planner_or_input():
    h = Harness()
    result = h.runner().run(Request(Mode.ACQUIRE_ONLY))
    assert result.status is Status.COMPLETED and result.initial_board is h.initial
    assert h.calls == ["acquire"]


def test_plan_only_calls_pure_planner_once_and_leaves_popup_open():
    h = Harness()
    result = h.runner().run(Request(Mode.PLAN_ONLY, FACTS))
    assert result.initial_plan is NONE and result.status is Status.COMPLETED
    assert h.calls == ["acquire", "plan"]


def test_plan_only_uses_real_planner_with_explicit_zero_rewards():
    h = Harness()
    runner = MonsterWaveStandaloneRunner(h, h, h, h, clock=lambda: 10.1)
    result = runner.run(Request(Mode.PLAN_ONLY, FACTS))
    assert result.initial_plan.status is ResourceRouteStatus.NO_PREREQUISITES
    assert h.calls == ["acquire"]


@pytest.mark.parametrize("mode", [Mode.PLAN_ONLY, Mode.PREREQUISITES_ONLY, Mode.FULL_ONE_SHOT])
def test_unresolved_never_routes_or_runs_mw(mode):
    h = Harness(UNRESOLVED)
    result = h.runner().run(Request(mode, FACTS))
    assert result.status is Status.UNRESOLVED and result.initial_plan is UNRESOLVED
    assert h.calls == ["acquire", "plan"]


def test_contradictory_plan_never_closes_popup_or_routes():
    contradictory = ResourceRoutePlan(
        ResourceRouteStatus.CONTRADICTORY,
        unresolved=(UnresolvedReason(UnresolvedCode.CONTRADICTORY_NON_BOARD_FACTS),),
    )
    h = Harness(contradictory)
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.status is Status.UNRESOLVED
    assert result.initial_plan is contradictory and h.calls == ["acquire", "plan"]


def test_no_prerequisites_closes_popup_without_j():
    h = Harness()
    result = h.runner().run(Request(Mode.PREREQUISITES_ONLY, FACTS))
    assert result.status is Status.COMPLETED and result.fresh_mw is h.clean
    assert h.calls == ["acquire", "plan", "close"]


def test_prerequisite_route_once_and_j_success_is_postcondition():
    h = Harness(READY)
    result = h.runner().run(Request(Mode.PREREQUISITES_ONLY, FACTS))
    assert result.status is Status.COMPLETED
    assert result.fresh_mw.context.sequence == 15
    assert result.route_result.executed_steps == READY.steps
    assert h.calls == ["acquire", "plan", "close", "J"]


@pytest.mark.parametrize("route_status,expected", [
    (ResourceRouteExecutionStatus.STEP_FAILED, Status.FAILED),
    (ResourceRouteExecutionStatus.CANCELLED, Status.CANCELLED),
])
def test_j_failure_or_cancel_stops_before_mw(route_status, expected):
    h = Harness(READY, route_status=route_status)
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.status is expected and result.phase == "prerequisites"
    assert h.calls == ["acquire", "plan", "close", "J"]


def test_j_success_without_full_plan_execution_is_rejected():
    h = Harness(READY)
    original = h.execute_plan_once

    def incomplete(plan, clean):
        result = original(plan, clean)
        return ResourceRouteExecutionResult(
            ResourceRouteExecutionStatus.SUCCESS, executed_steps=(),
            final_context=result.final_context, final_snapshot=result.final_snapshot,
        )

    h.execute_plan_once = incomplete
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.reason == "plan_not_fully_executed"
    assert "exit" not in h.calls and "MW" not in h.calls


def test_j_success_without_fresh_mw_is_rejected():
    h = Harness(READY)

    def stale(plan, clean):
        return ResourceRouteExecutionResult(
            ResourceRouteExecutionStatus.SUCCESS, executed_steps=plan.steps,
            final_context=clean.context, final_snapshot=clean.snapshot,
        )

    h.execute_plan_once = stale
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.reason == "fresh_mw_postcondition_stale"
    assert "exit" not in h.calls and "MW" not in h.calls


@pytest.mark.parametrize("plan,calls", [
    (NONE, ["acquire", "plan", "close", "exit", "MW"]),
    (READY, ["acquire", "plan", "close", "J", "exit", "MW"]),
])
def test_full_one_shot_calls_activity_once(plan, calls):
    h = Harness(plan)
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.status is Status.COMPLETED
    assert result.activity_result.status is FlowStatus.COMPLETED
    assert h.calls == calls


def test_exit_failure_stops_before_activity():
    h = Harness(exit_status=FlowStatus.FAILED)
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.status is Status.FAILED and result.phase == "exit_to_battle_mode"
    assert h.calls == ["acquire", "plan", "close", "exit"]


def test_activity_manual_resolution_propagated_without_relief():
    h = Harness(activity_status=FlowStatus.MANUAL_RESOLUTION)
    result = h.runner().run(Request(Mode.FULL_ONE_SHOT, FACTS))
    assert result.activity_result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.reason == FlowStatus.MANUAL_RESOLUTION.value
    assert h.calls.count("MW") == 1


def test_planning_facts_must_be_explicit():
    with pytest.raises(ValueError, match="explicit NonBoardResourceFacts"):
        Request(Mode.FULL_ONE_SHOT)


class Observer:
    def __init__(self, first, second):
        self.first, self.second = first, second

    def observe(self):
        return self.first

    def wait_until(self, predicate, *, after_sequence, **kwargs):
        assert self.second.sequence > after_sequence
        assert predicate(self.second)
        return self.second


class Reader:
    def read_sample(self, ctx):
        return MonsterWaveBoardSample(ROWS, ctx.sequence, ctx.timestamp,
                                      tuple(item_id for item_id, _, _ in BOARD_ROWS))


def test_read_only_acquisition_two_matching_popup_frames():
    acquired = MonsterWaveBoardAcquisitionRuntime(
        Observer(context(9, popup=True), context(10, popup=True)), Reader(),
        clock=lambda: 10.1,
    ).acquire()
    assert acquired.snapshot.resource_rows == ROWS
    assert acquired.snapshot.evidence.row_sequences == (9, 10)


@pytest.mark.parametrize("foreign", [True, False])
def test_read_only_acquisition_fails_closed_without_open_board(foreign):
    first = context(9, foreign=foreign)
    with pytest.raises(ValueError, match="popup_not_open"):
        MonsterWaveBoardAcquisitionRuntime(Observer(first, context(10, popup=True)), Reader()).acquire()


def test_exit_adapter_uses_existing_intent_once_with_clean_mw_guard():
    clean = anchor(12)
    final = SimpleNamespace(sequence=14, state=SimpleNamespace(status=ResolutionStatus.RESOLVED,
                            base_context="screen.battle_mode_select", overlays=()))

    class Transition:
        calls = 0

        def execute(self, name, action, before, **kwargs):
            self.calls += 1
            assert isinstance(action, ExitMonsterWave)
            assert before.sequence == 13
            assert kwargs["precondition"](before)
            assert kwargs["expected"](final)
            assert kwargs["policy"].max_attempts == 1
            return SimpleNamespace(succeeded=True, attempt_count=1, final_snapshot=final)

    transition = Transition()
    class Snapshots:
        def acquire(self, *, after_sequence):
            assert after_sequence == 12
            return SimpleNamespace(status=FlowStatus.COMPLETED, fresh=anchor(13))

    status, _ = MonsterWaveStandaloneNavigationRuntime(transition, Snapshots()).exit_to_battle_mode(clean)
    assert status is FlowStatus.COMPLETED and transition.calls == 1


def test_close_adapter_uses_existing_decline_and_fresh_reacquisition():
    acquired = board()
    clean = anchor(12)

    class Transition:
        observer = Observer(context(10, popup=True), context(11, popup=True))

        def execute(self, name, action, before, **kwargs):
            assert isinstance(action, DeclineMonsterWaveInventory)
            assert before.sequence == 11
            assert kwargs["precondition"](before)
            assert kwargs["expected"](clean.context)
            return SimpleNamespace(succeeded=True, attempt_count=1, final_snapshot=clean.context)

    class Snapshots:
        def acquire(self, *, after_sequence):
            assert after_sequence == 12
            return SimpleNamespace(status=FlowStatus.COMPLETED, fresh=anchor(13))

    status, result, _ = MonsterWaveStandaloneNavigationRuntime(
        Transition(), Snapshots()
    ).close_board(acquired)
    assert status is FlowStatus.COMPLETED and result.context.sequence == 13
