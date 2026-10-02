"""L1 productive MW wiring: barrier, request preservation and hard bounds."""

import numpy as np
import pytest
from types import SimpleNamespace

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.flow_contracts import FlowEvent, FlowStatus
from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL
from bot.equipment_relief import (EquipmentReliefComposer, EquipmentReliefOutcome,
                                  EquipmentReliefResult)
from bot.equipment_combine_relief import (EquipmentCombineReliefOutcome,
                                          EquipmentCombineReliefResult)
from bot.socket_inventory_relief import SocketReliefOutcome, SocketReliefResult
from bot.monster_wave_activity import MonsterWaveActivity, MonsterWaveResult
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
    TradingSessionStep, KeysPromotionStep, UnresolvedCode, UnresolvedReason,
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
                 route_failing_step=None):
        self.calls = []
        self.first = first
        self.plan = plan
        self.route_status = route_status
        self.route_failing_step = route_failing_step
        self.second = MonsterWaveResult(FlowStatus.COMPLETED, events=(FlowEvent('monster_wave.completed'),))
        self.board = _board()
        self.clean = _anchor(12)

    def prepare(self):
        self.calls.append(("prepare",))
        return MonsterWaveResult(FlowStatus.COMPLETED, sapphires_initial=100)

    def run_pass(self, *, yield_resource_board=False, resume_after_relief=False):
        self.calls.append(("pass", yield_resource_board, resume_after_relief))
        return self.first if yield_resource_board else self.second

    def finish_pass(self, current):
        self.calls.append(("finish",))
        return self.second

    def reenter(self):
        self.calls.append(("reenter",))
        return MonsterWaveResult(FlowStatus.COMPLETED)

    def leave(self):
        self.calls.append(("leave",))
        return MonsterWaveResult(FlowStatus.COMPLETED)

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

    def accept_board(self, acquired):
        self.calls.append(("yes",))
        assert acquired is self.board
        return FlowStatus.COMPLETED, self.clean.context

    def execute_plan_once(self, plan, anchor):
        self.calls.append(("J",))
        assert plan is self.plan and anchor is self.clean
        assert sum(1 for c in self.calls if c[0] == "J") == 1
        final = _anchor(15)
        if self.route_status is not ResourceRouteExecutionStatus.SUCCESS:
            return ResourceRouteExecutionResult(
                self.route_status, failing_step=self.route_failing_step,
            )
        return ResourceRouteExecutionResult(
            self.route_status, executed_steps=plan.steps,
            final_context=final.context, final_snapshot=final.snapshot,
        )

    def exit_to_battle_mode(self, anchor):
        self.calls.append(("exit",))
        assert sum(1 for c in self.calls if c[0] == "exit") == 1
        return FlowStatus.COMPLETED, None

    def flow(self):
        inner = MonsterWaveFlow.__new__(MonsterWaveFlow)
        inner.activity = type("A", (), {
            "prepare": self.prepare, "run_pass": self.run_pass,
            "finish_pass": self.finish_pass, "reenter": self.reenter,
            "leave": self.leave, "_merge": staticmethod(MonsterWaveActivity._merge),
        })()
        inner.zone = type("Z", (), {})()
        return ProductiveMonsterWaveFlow(
            inner, boards=self, navigation=self, route=self,
            planner=self.planner, non_board=NonBoardResourceFacts(),
            clock=lambda: 10.1,
        )


def _pending(sequence=9):
    return MonsterWaveResult(FlowStatus.RESOURCE_BOARD_PENDING, board_sequence=sequence)


def test_request_preserved_first_yield_resume_no_yield_same_request():
    harness = _Harness(first=_pending(), plan=NONE)
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.COMPLETED
    assert harness.calls == [('prepare',), ('pass', True, False),
                             ('acquire', 9), ('plan', 8), ('yes',),
                             ('finish',), ('leave',)]
    assert result.sapphires_consumed == 100


def test_empty_plan_resumes_once_without_fabricating_j():
    harness = _Harness(first=_pending(), plan=NONE)
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.COMPLETED
    kinds = [c[0] for c in harness.calls]
    assert kinds.count("acquire") == 1
    assert kinds.count("plan") == 1
    assert kinds.count("yes") == 1
    assert kinds.count("close") == 0
    assert "J" not in kinds
    assert kinds.count("exit") == 0
    assert kinds.count("pass") == 1


def test_ready_plan_executes_preparation_exactly_once_then_resumes():
    harness = _Harness(first=_pending(), plan=READY)
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.COMPLETED
    kinds = [c[0] for c in harness.calls]
    assert kinds == ["prepare", "pass", "acquire", "plan", "close", "J",
                     "exit", "reenter", "pass", "leave"]


def test_non_pending_never_acquires_plans_or_resumes():
    harness = _Harness(first=MonsterWaveResult(FlowStatus.COMPLETED,
                       events=(FlowEvent('monster_wave.completed'),)), plan=NONE)
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.COMPLETED
    assert harness.calls == [("prepare",), ("pass", True, False), ("leave",)]


def test_j_failure_never_resumes_second_leg():
    harness = _Harness(first=_pending(), plan=READY,
                       route_status=ResourceRouteExecutionStatus.STEP_FAILED)
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.FAILED
    kinds = [c[0] for c in harness.calls]
    assert kinds.count("pass") == 1
    assert kinds.count("J") == 1
    assert "exit" not in kinds


def test_planner_called_once_with_barrier_snapshot():
    harness = _Harness(first=_pending(sequence=20), plan=NONE)
    harness.board = _board(sequence=22, barrier=20)
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.COMPLETED
    assert ("acquire", 20) in harness.calls
    assert ("plan", 20) in harness.calls


def _blocked(kind):
    return MonsterWaveResult(FlowStatus.MANUAL_RESOLUTION, events=(
        FlowEvent("monster_wave.manual_resolution", fields={"blocker": kind}),
    ))


@pytest.mark.parametrize("blockers", [
    (POPUP_EQUIPMENT_INVENTORY_FULL,),
    (POPUP_SOCKET_INVENTORY_FULL,),
    (POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL),
    (POPUP_SOCKET_INVENTORY_FULL, POPUP_EQUIPMENT_INVENTORY_FULL),
    (POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_EQUIPMENT_INVENTORY_FULL),
    (POPUP_SOCKET_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL),
])
def test_l2_reactive_bounds_and_same_request_without_second_preparation(blockers):
    from dataclasses import replace

    harness = _Harness(first=_pending(), plan=READY)
    scripted = [_blocked(kind) for kind in blockers] + [MonsterWaveResult(
        FlowStatus.COMPLETED, events=(FlowEvent('monster_wave.completed'),))]
    calls = []
    current_blocker = [None]

    class Observer:
        def observe(self):
            kind = current_blocker[0]
            ctx = _context(25)
            return replace(ctx, state=replace(ctx.state, overlays=(kind,)))

        def wait_until(self, predicate, *, after_sequence, **kwargs):
            ctx = _context(after_sequence + 1)
            assert predicate(ctx)
            return ctx

    class Navigation:
        def close_board(self, board):
            return harness.close_board(board)

        def accept_board(self, board):
            return harness.accept_board(board)

        def exit_to_battle_mode(self, anchor):
            return harness.exit_to_battle_mode(anchor)

        def enter_blocker_relief(self, kind):
            calls.append(("enter", kind))

        def exit_after_relief(self, context):
            calls.append(("return", context.sequence))

    class Combine:
        def run(self, plan, cancel_requested):
            calls.append(("combine",))
            return EquipmentCombineReliefResult(
                EquipmentCombineReliefOutcome.RELIEVED,
                final_snapshot=_context(30),
            )

    class Sell:
        def execute(self, request):
            pytest.fail("no authorized MW Sell plan")

    class Socket:
        def run(self, plan, cancel_requested):
            calls.append(("socket",))
            return SocketReliefResult(SocketReliefOutcome.RELIEVED,
                                      final_snapshot=_context(40))

    def activity_run(*, yield_resource_board=False, resume_after_relief=False):
        harness.calls.append(("pass", yield_resource_board, resume_after_relief))
        if yield_resource_board:
            return harness.first
        result = scripted.pop(0)
        current_blocker[0] = (result.events[0].fields["blocker"]
                              if result.status is FlowStatus.MANUAL_RESOLUTION else None)
        return result

    inner = MonsterWaveFlow.__new__(MonsterWaveFlow)
    inner.activity = type("Activity", (), {
        "prepare": staticmethod(harness.prepare),
        "run_pass": staticmethod(activity_run),
        "reenter": staticmethod(harness.reenter),
        "leave": staticmethod(harness.leave),
        "_merge": staticmethod(MonsterWaveActivity._merge),
        "observer": Observer(),
        "cancel_requested": staticmethod(lambda: False),
    })()
    inner.zone = type("Zone", (), {})()
    flow = ProductiveMonsterWaveFlow(
        inner, boards=harness, navigation=Navigation(), route=harness,
        planner=harness.planner, non_board=NonBoardResourceFacts(),
        equipment_relief=EquipmentReliefComposer(Combine(), Sell()),
        socket_relief=Socket(), clock=lambda: 10.1,
    )
    result = flow._run_activity_l1()
    repeated = len(blockers) > 1 and blockers[0] == blockers[1]
    expected = (FlowStatus.MANUAL_RESOLUTION if repeated and blockers[0] == POPUP_EQUIPMENT_INVENTORY_FULL
                else FlowStatus.FAILED if repeated else FlowStatus.COMPLETED)
    assert result.status is expected, result.error
    assert sum(c[0] == "combine" for c in calls) <= 1
    assert sum(c[0] == "socket" for c in calls) <= 1
    assert [c[1] for c in calls if c[0] == "enter"] == list(dict.fromkeys(blockers))
    kinds = [c[0] for c in harness.calls]
    assert kinds.count("acquire") == kinds.count("plan") == kinds.count("J") == 1
    assert all(c[1:] == (False, True) for c in harness.calls if c[0] == "pass" and c != ('pass', True, False))


@pytest.mark.parametrize("outcome,expected", [
    (SocketReliefOutcome.CANCELLED, FlowStatus.CANCELLED),
    (SocketReliefOutcome.FAILED, FlowStatus.FAILED),
])
def test_l2_socket_terminal_relief_prevents_further_mw_input(outcome, expected):
    calls = []
    flow = ProductiveMonsterWaveFlow.__new__(ProductiveMonsterWaveFlow)
    flow.activity = type("Activity", (), {"cancel_requested": staticmethod(lambda: False)})()
    flow.navigation = type("Navigation", (), {
        "enter_blocker_relief": lambda self, blocker: calls.append(("enter", blocker)),
        "exit_after_relief": lambda self, snapshot: pytest.fail("no return after terminal relief"),
    })()
    flow.equipment_sell_plan = None
    flow.socket_relief = type("Socket", (), {
        "run": lambda self, plan, cancel_requested: (
            calls.append(("relief",)) or SocketReliefResult(outcome)
        ),
    })()
    flow.equipment_relief = None
    flow._resume_leg = lambda: pytest.fail("no retry after terminal relief")
    result = flow._relieve_blockers(_blocked(POPUP_SOCKET_INVENTORY_FULL))
    assert result.status is expected
    assert calls == [("enter", POPUP_SOCKET_INVENTORY_FULL), ("relief",)]


def test_l2_rejects_ambiguous_blocker_without_relief():
    flow = ProductiveMonsterWaveFlow.__new__(ProductiveMonsterWaveFlow)
    flow.activity = type("Activity", (), {"cancel_requested": staticmethod(lambda: False)})()
    flow.equipment_relief = flow.socket_relief = None
    flow._resume_leg = lambda: pytest.fail("ambiguous result cannot retry")
    ambiguous = MonsterWaveResult(FlowStatus.MANUAL_RESOLUTION, events=(
        FlowEvent("monster_wave.manual_resolution", fields={"blocker": POPUP_EQUIPMENT_INVENTORY_FULL}),
        FlowEvent("monster_wave.manual_resolution", fields={"blocker": POPUP_SOCKET_INVENTORY_FULL}),
    ))
    result = flow._relieve_blockers(ambiguous)
    assert result.status is FlowStatus.FAILED
    assert result.error == "mw_blocker_result_ambiguous"


def test_l2_equipment_relief_success_retries_same_pass_without_battle_mode_round_trip():
    from dataclasses import replace

    calls = []
    resumed = MonsterWaveResult(FlowStatus.COMPLETED, events=(FlowEvent('monster_wave.completed'),))

    class Observer:
        def observe(self):
            ctx = _context(25)
            return replace(ctx, state=replace(ctx.state, overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,)))

        def wait_until(self, predicate, *, after_sequence, **kwargs):
            ctx = _context(after_sequence + 1)
            assert predicate(ctx)
            return ctx

    class Combine:
        def run(self, plan, cancel_requested):
            calls.append(("combine",))
            return EquipmentCombineReliefResult(
                EquipmentCombineReliefOutcome.RELIEVED,
                final_snapshot=_context(30),
            )

    class Sell:
        def execute(self, request):
            pytest.fail("no authorized MW Sell plan")

    def run_pass(*, yield_resource_board=False, resume_after_relief=False):
        calls.append(("pass", yield_resource_board, resume_after_relief))
        return resumed

    flow = ProductiveMonsterWaveFlow.__new__(ProductiveMonsterWaveFlow)
    flow.activity = type("Activity", (), {
        "observer": Observer(),
        "cancel_requested": staticmethod(lambda: False),
        "run_pass": staticmethod(run_pass),
        "reenter": staticmethod(lambda: pytest.fail("no MW reentry after relief")),
    })()
    flow.navigation = type("Navigation", (), {
        "enter_blocker_relief": lambda self, blocker: calls.append(("enter", blocker)),
        "exit_after_relief": lambda self, context: pytest.fail("no battle-mode exit after relief"),
        "exit_to_battle_mode": lambda self, anchor: pytest.fail("no battle-mode exit after relief"),
    })()
    flow.equipment_relief = EquipmentReliefComposer(Combine(), Sell())
    flow.equipment_sell_plan = None
    flow.socket_relief = None

    result = flow._relieve_blockers(_blocked(POPUP_EQUIPMENT_INVENTORY_FULL))

    assert result.status is FlowStatus.COMPLETED
    assert ("enter", POPUP_EQUIPMENT_INVENTORY_FULL) in calls
    assert ("combine",) in calls
    # Direct retry of the same SKIP/pass: no ExitMonsterWave, no battle-mode
    # visit, no reentry, no fresh preparation — only the resume pass.
    assert calls.count(("pass", False, True)) == 1
    assert [c for c in calls if c[0] == "pass"] == [("pass", False, True)]
    assert FlowEvent('monster_wave.completed') in result.events


@pytest.mark.parametrize("outcome,expected", [
    (EquipmentReliefOutcome.CANCELLED, FlowStatus.CANCELLED),
    (EquipmentReliefOutcome.COMBINE_FAILED, FlowStatus.FAILED),
    (EquipmentReliefOutcome.SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE, FlowStatus.MANUAL_RESOLUTION),
])
def test_l2_equipment_terminal_relief_prevents_further_mw_input(outcome, expected):
    calls = []
    flow = ProductiveMonsterWaveFlow.__new__(ProductiveMonsterWaveFlow)
    flow.activity = type("Activity", (), {"cancel_requested": staticmethod(lambda: False)})()
    flow.equipment_relief = type("Equipment", (), {
        "run": lambda self, request: (
            calls.append("relief") or EquipmentReliefResult(outcome, "combine.run")
        ),
    })()
    flow.equipment_sell_plan = None
    flow.socket_relief = None
    flow._resume_leg = lambda: pytest.fail("no retry after terminal relief")
    result = flow._relieve_blockers(_blocked(POPUP_EQUIPMENT_INVENTORY_FULL))
    assert result.status is expected
    assert calls == ["relief"]


def test_j_capacity_blocked_preserves_failing_step_without_replan_or_second_j():
    from bot.monster_wave_resource_route import ResourceRouteExecutionStatus
    harness = _Harness(
        first=_pending(), plan=READY,
        route_status=ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED,
        route_failing_step="craft",
    )
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.FAILED
    # failing_step stays visible in the error/log, not degraded to generic.
    assert "equipment_capacity_blocked" in result.error
    assert "craft" in result.error
    kinds = [c[0] for c in harness.calls]
    # Outer board/planner/J stay 1/1/1, no replan, no second J, no resume.
    assert kinds.count("acquire") == 1
    assert kinds.count("plan") == 1
    assert kinds.count("J") == 1
    assert kinds.count("pass") == 1
    assert "exit" not in kinds


@pytest.mark.parametrize('balance,passes', [(0, 0), (1, 1), (100, 1),
                                            (101, 2), (250, 3)])
def test_productive_loop_uses_initial_balance_and_fresh_board_each_pass(balance, passes):
    calls = []
    boards = []
    plans = [NONE, READY, NONE]
    clear = MonsterWaveResult(FlowStatus.COMPLETED,
                              events=(FlowEvent('monster_wave.completed'),))

    def prepare():
        calls.append(('prepare',))
        return MonsterWaveResult(FlowStatus.COMPLETED, sapphires_initial=balance)

    def run_pass(*, yield_resource_board=False, resume_after_relief=False):
        calls.append(('pass', yield_resource_board, resume_after_relief))
        if resume_after_relief:
            return clear
        index = sum(item[0] == 'pass' and item[1] for item in calls)
        return _pending(sequence=index * 10)

    def acquire(*, after_sequence):
        board = _board(sequence=after_sequence + 2, barrier=after_sequence)
        boards.append(board)
        calls.append(('board', after_sequence))
        return board

    def planner(planning):
        index = len(boards) - 1
        assert planning.board is boards[index].snapshot
        assert planning.after_sequence == boards[index].after_sequence
        calls.append(('plan', index))
        return plans[index]

    def close_board(board):
        assert board is boards[-1]
        calls.append(('no',))
        return FlowStatus.COMPLETED, _anchor(board.context.sequence + 2), None

    def execute_plan_once(plan, anchor):
        assert plan is READY
        calls.append(('relief',))
        final = _anchor(anchor.context.sequence + 2)
        return ResourceRouteExecutionResult(
            ResourceRouteExecutionStatus.SUCCESS, executed_steps=plan.steps,
            final_context=final.context, final_snapshot=final.snapshot)

    activity = SimpleNamespace(
        prepare=prepare, run_pass=run_pass, finish_pass=lambda _: clear,
        reenter=lambda: MonsterWaveResult(FlowStatus.COMPLETED),
        leave=lambda: MonsterWaveResult(FlowStatus.COMPLETED),
        _merge=MonsterWaveActivity._merge,
    )
    inner = MonsterWaveFlow.__new__(MonsterWaveFlow)
    inner.activity, inner.zone = activity, object()
    navigation = SimpleNamespace(
        close_board=close_board,
        accept_board=lambda board: (calls.append(('yes',)) or FlowStatus.COMPLETED,
                                    board.context),
        exit_to_battle_mode=lambda _: (FlowStatus.COMPLETED, None),
    )
    flow = ProductiveMonsterWaveFlow(
        inner, boards=SimpleNamespace(acquire=acquire), navigation=navigation,
        route=SimpleNamespace(execute_plan_once=execute_plan_once),
        planner=planner, clock=lambda: 100.0)
    result = flow._run_activity_l1()
    assert result.succeeded, result.error
    assert result.sapphires_initial == balance
    assert result.sapphires_consumed == balance
    assert result.event_count('monster_wave.completed') == passes
    assert calls.count(('prepare',)) == 1
    assert len(boards) == len({id(board) for board in boards}) == passes
    assert sum(item[0] == 'plan' for item in calls) == passes
    assert sum(item[0] == 'yes' for item in calls) == passes - int(passes > 1)
    assert sum(item[0] == 'no' for item in calls) == int(passes > 1)
    assert sum(item[0] == 'relief' for item in calls) == int(passes > 1)


@pytest.mark.parametrize('status', [ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
                                    ResourceRouteStatus.CONTRADICTORY])
def test_unresolved_board_stops_before_yes_no_or_retry(status):
    harness = _Harness(first=_pending(), plan=ResourceRoutePlan(
        status, unresolved=(UnresolvedReason(UnresolvedCode.BOARD_CONTENT_UNKNOWN),)))
    result = harness.flow()._run_activity_l1()
    assert result.status is FlowStatus.FAILED
    assert result.sapphires_consumed == 0
    assert [c[0] for c in harness.calls] == ['prepare', 'pass', 'acquire', 'plan']


def test_insufficient_sapphires_is_terminal_without_extra_pass():
    harness = _Harness(first=MonsterWaveResult(
        FlowStatus.COMPLETED, events=(FlowEvent('monster_wave.insufficient_sapphires'),)))
    result = harness.flow()._run_activity_l1()
    assert result.succeeded
    assert result.sapphires_consumed == 0
    assert result.event_count('monster_wave.insufficient_sapphires') == 1
    assert harness.calls == [('prepare',), ('pass', True, False), ('leave',)]
