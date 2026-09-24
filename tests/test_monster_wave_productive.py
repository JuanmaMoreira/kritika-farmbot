"""L1 productive MW wiring: barrier, request preservation and hard bounds."""

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.flow_contracts import FlowStatus
from bot.monster_wave_activity import MonsterWaveResult
from bot.monster_wave_board_reader import BOARD_ROWS, MonsterWaveBoardRow, MonsterWaveBoardSample
from bot.monster_wave_board_snapshot import (
    BoardEvidence, BoardPopup, MaxState, MonsterWaveBoardSnapshot, Tickets,
)
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_productive import ProductiveMonsterWaveFlow
from bot.monster_wave_resource_route import (
    FreshMonsterWaveSnapshot, ResourceRouteExecutionResult,
    ResourceRouteExecutionStatus,
)
from bot.monster_wave_semantics import MW_BOARD, MW_NEEDS_TICKETS, POPUP_MW_BOARD, SCREEN_MONSTER_WAVE
from bot.monster_wave_standalone import (
    FreshMonsterWaveBoard, MonsterWaveBoardAcquisitionRuntime,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resource_route_planner import (
    NonBoardResourceFacts, ResourceRoutePlan, ResourceRouteStatus,
    TradingSessionStep, KeysPromotionStep,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.monster_wave_board_snapshot import build_monster_wave_board_snapshot


def _context(sequence, *, popup=False, timestamp=None):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    timestamp = float(sequence) if timestamp is None else timestamp
    names = (MW_BOARD,) if popup else (MW_NEEDS_TICKETS,)
    observations = tuple(Observation(name, 1.0, ObservationSource.LOCAL_CV) for name in names)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, observations),
        ResolvedState(ResolutionStatus.RESOLVED, sequence, timestamp,
                      base_context=SCREEN_MONSTER_WAVE,
                      overlays=(POPUP_MW_BOARD,) if popup else ()),
        RuntimeFacts(), FrameGeometry.from_frame(image),
    )


ROWS = tuple(MonsterWaveBoardRow(item_id, 1, 100) for item_id, _, _ in BOARD_ROWS)


class _Observer:
    def __init__(self, first, second):
        self.first, self.second = first, second
        self.calls = []

    def observe(self):
        self.calls.append("observe")
        return self.first

    def wait_until(self, predicate, *, after_sequence, **kwargs):
        self.calls.append("wait")
        assert predicate(self.second)
        assert self.second.sequence > after_sequence
        return self.second


class _Reader:
    def read_sample(self, ctx):
        return MonsterWaveBoardSample(ROWS, ctx.sequence, ctx.timestamp,
                                      tuple(item_id for item_id, _, _ in BOARD_ROWS))


def test_barrier_rejects_non_negative_contract():
    runtime = MonsterWaveBoardAcquisitionRuntime(
        _Observer(_context(9, popup=True), _context(10, popup=True)), _Reader(),
    )
    for bad in (-1, True, "8", None):
        with pytest.raises(ValueError, match="after_sequence"):
            runtime.acquire(after_sequence=bad)


def test_barrier_requires_frames_strictly_after_pending_sequence():
    # First open but stale (9 <= 9) triggers one bounded wait for fresh 10,
    # then second must be > 10. Here second is 10 -> consensus unavailable,
    # but the barrier path is exercised (two waits, no OCR on stale pair).
    class _StaleFirst:
        def __init__(self):
            self.calls = []

        def observe(self):
            self.calls.append("observe")
            return _context(9, popup=True)

        def wait_until(self, predicate, *, after_sequence, **kwargs):
            self.calls.append(("wait", after_sequence))
            assert kwargs["timeout"] == 3.0
            # First recovery wait: barrier 9 -> fresh 10; second wait: 10 -> 11.
            seq = 10 if after_sequence == 9 else 11
            ctx = _context(seq, popup=True, timestamp=float(seq))
            assert predicate(ctx)
            return ctx

    runtime = MonsterWaveBoardAcquisitionRuntime(
        _StaleFirst(), _Reader(), clock=lambda: 11.1,
    )
    board = runtime.acquire(after_sequence=9)
    assert board.context.sequence == 11
    assert board.after_sequence == 9
    assert board.snapshot.evidence.row_sequences == (10, 11)
    assert board.snapshot.evidence.sequence == 11


def test_barrier_preserves_spacing_final_age_and_bounded_wait():
    # Spacing >1.0s between captures must fail before OCR.
    first = _context(9, popup=True, timestamp=9.0)
    second = _context(10, popup=True, timestamp=10.5)
    runtime = MonsterWaveBoardAcquisitionRuntime(
        _Observer(first, second), _Reader(), clock=lambda: 10.6,
    )
    with pytest.raises(ValueError, match="consensus_unavailable"):
        runtime.acquire(after_sequence=8)
    # Final age >2.0s must fail (clock far after second).
    runtime = MonsterWaveBoardAcquisitionRuntime(
        _Observer(_context(9, popup=True), _context(10, popup=True)),
        _Reader(), clock=lambda: 12.5,
    )
    with pytest.raises(ValueError, match="snapshot_unavailable"):
        runtime.acquire(after_sequence=8)


def _anchor(sequence):
    ctx = _context(sequence)
    snap = build_monster_wave_board_snapshot(ctx, after_sequence=sequence - 1, now=float(sequence))
    return FreshMonsterWaveSnapshot(ctx, snap)


def _board(sequence=10, barrier=8):
    ctx = _context(sequence, popup=True)
    snap = MonsterWaveBoardSnapshot(
        None, Tickets.UNKNOWN, None, MaxState(None, None, None, None),
        BoardPopup.PRESENT_WITH_ROWS, (), ROWS, BoardEvidence(sequence, float(sequence), (sequence - 1, sequence)),
    )
    return FreshMonsterWaveBoard(ctx, snap, barrier)


NONE = ResourceRoutePlan(ResourceRouteStatus.NO_PREREQUISITES)
READY = ResourceRoutePlan(ResourceRouteStatus.READY,
                          steps=(TradingSessionStep((KeysPromotionStep(),)),))


class _Harness:
    """Fakes for productive bounds: activity + boards + planner + nav + route."""

    def __init__(self, *, first, plan=NONE, route_status=ResourceRouteExecutionStatus.SUCCESS,
                 daily_expected=True):
        self.calls = []
        self.first = first
        self.plan = plan
        self.route_status = route_status
        self.daily_expected = daily_expected
        self.second = MonsterWaveResult(FlowStatus.COMPLETED)
        self.board = _board()
        self.clean = _anchor(12)

    def _activity_run(self, *, daily_sapphires, yield_resource_board):
        self.calls.append(("activity", daily_sapphires, yield_resource_board))
        assert daily_sapphires is self.daily_expected
        if yield_resource_board:
            assert len([c for c in self.calls if c[0] == "activity"]) == 1
            return self.first
        assert len([c for c in self.calls if c[0] == "activity"]) == 2
        return self.second

    def acquire(self, *, after_sequence):
        self.calls.append(("acquire", after_sequence))
        assert after_sequence == self.first.board_sequence
        assert sum(1 for c in self.calls if c[0] == "acquire") == 1
        return self.board

    def planner(self, planning):
        self.calls.append(("plan", planning.after_sequence))
        assert planning.after_sequence == self.board.after_sequence
        assert sum(1 for c in self.calls if c[0] == "plan") == 1
        return self.plan

    def close_board(self, acquired):
        self.calls.append(("close",))
        assert acquired is self.board
        assert sum(1 for c in self.calls if c[0] == "close") == 1
        return FlowStatus.COMPLETED, self.clean, None

    def execute_plan_once(self, plan, anchor):
        self.calls.append(("J",))
        assert plan is self.plan and anchor is self.clean
        assert sum(1 for c in self.calls if c[0] == "J") == 1
        final = _anchor(15)
        if self.route_status is not ResourceRouteExecutionStatus.SUCCESS:
            return ResourceRouteExecutionResult(self.route_status)
        return ResourceRouteExecutionResult(
            self.route_status, executed_steps=plan.steps,
            final_context=final.context, final_snapshot=final.snapshot,
        )

    def exit_to_battle_mode(self, anchor):
        self.calls.append(("exit",))
        assert sum(1 for c in self.calls if c[0] == "exit") == 1
        return FlowStatus.COMPLETED, None

    def flow(self, *, daily):
        inner = MonsterWaveFlow.__new__(MonsterWaveFlow)
        inner.activity = type("A", (), {"run": self._activity_run})()
        inner.zone = type("Z", (), {})()
        return ProductiveMonsterWaveFlow(
            inner, boards=self, navigation=self, route=self,
            planner=self.planner, non_board=NonBoardResourceFacts(),
            clock=lambda: 10.1,
        )


def _pending(sequence=9):
    return MonsterWaveResult(FlowStatus.RESOURCE_BOARD_PENDING, board_sequence=sequence)


def test_request_preserved_first_yield_resume_no_yield_same_daily():
    harness = _Harness(first=_pending(), plan=NONE, daily_expected=True)
    result = harness.flow(daily=True)._run_activity_l1(daily=True)
    assert result.status is FlowStatus.COMPLETED
    activities = [c for c in harness.calls if c[0] == "activity"]
    assert activities == [("activity", True, True), ("activity", True, False)]


def test_empty_plan_resumes_once_without_fabricating_j():
    harness = _Harness(first=_pending(), plan=NONE)
    result = harness.flow(daily=True)._run_activity_l1(daily=True)
    assert result.status is FlowStatus.COMPLETED
    kinds = [c[0] for c in harness.calls]
    assert kinds.count("acquire") == 1
    assert kinds.count("plan") == 1
    assert kinds.count("close") == 1
    assert "J" not in kinds
    assert kinds.count("exit") == 1
    assert kinds.count("activity") == 2


def test_ready_plan_executes_preparation_exactly_once_then_resumes():
    harness = _Harness(first=_pending(), plan=READY)
    result = harness.flow(daily=True)._run_activity_l1(daily=True)
    assert result.status is FlowStatus.COMPLETED
    kinds = [c[0] for c in harness.calls]
    assert kinds == ["activity", "acquire", "plan", "close", "J", "exit", "activity"]


def test_non_pending_never_acquires_plans_or_resumes():
    harness = _Harness(first=MonsterWaveResult(FlowStatus.COMPLETED), plan=NONE)
    result = harness.flow(daily=True)._run_activity_l1(daily=True)
    assert result.status is FlowStatus.COMPLETED
    assert harness.calls == [("activity", True, True)]


def test_j_failure_never_resumes_second_leg():
    harness = _Harness(first=_pending(), plan=READY,
                       route_status=ResourceRouteExecutionStatus.STEP_FAILED)
    result = harness.flow(daily=True)._run_activity_l1(daily=True)
    assert result.status is FlowStatus.FAILED
    kinds = [c[0] for c in harness.calls]
    assert kinds.count("activity") == 1
    assert kinds.count("J") == 1
    assert "exit" not in kinds


def test_planner_called_once_with_barrier_snapshot():
    harness = _Harness(first=_pending(sequence=20), plan=NONE)
    harness.board = _board(sequence=22, barrier=20)
    result = harness.flow(daily=True)._run_activity_l1(daily=True)
    assert result.status is FlowStatus.COMPLETED
    assert ("acquire", 20) in harness.calls
    assert ("plan", 20) in harness.calls
