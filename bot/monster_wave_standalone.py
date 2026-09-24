"""One bounded, opt-in Monster Wave resource route and SKIP composition.

The caller supplies non-board planning facts and the closed J/activity runtimes.
This module does not enter MW, discover resources, or repeat a route or SKIP.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time

from bot.battle_mode_zone import is_battle_mode_select
from bot.flow_contracts import FlowStatus
from bot.monster_wave_actions import DeclineMonsterWaveInventory, ExitMonsterWave
from bot.monster_wave_activity import MonsterWaveResult, clean_mw, skip_state
from bot.monster_wave_board_reader import MonsterWaveBoardReader, consensus_board_samples
from bot.monster_wave_board_snapshot import (
    BoardPopup, MonsterWaveBoardSnapshot, build_monster_wave_board_snapshot,
)
from bot.monster_wave_resource_route import (
    FreshMonsterWaveSnapshot, MonsterWaveSnapshotRuntime,
    ResourceRouteExecutionResult, ResourceRouteExecutionStatus,
)
from bot.monster_wave_semantics import POPUP_MW_BOARD, SCREEN_MONSTER_WAVE
from bot.resource_route_planner import (
    NonBoardResourceFacts, ResourcePlanningInput, ResourceRoutePlan,
    ResourceRouteStatus, plan_resource_route,
)
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionPolicy, VerifiedTransitionResult


def _board_open(context: RuntimeSnapshot) -> bool:
    state = context.state
    return (state.status is ResolutionStatus.RESOLVED
            and state.base_context == SCREEN_MONSTER_WAVE
            and state.overlays == (POPUP_MW_BOARD,))


@dataclass(frozen=True)
class FreshMonsterWaveBoard:
    context: RuntimeSnapshot
    snapshot: MonsterWaveBoardSnapshot
    after_sequence: int

    def __post_init__(self) -> None:
        if (not _board_open(self.context)
                or self.snapshot.board_popup is not BoardPopup.PRESENT_WITH_ROWS
                or self.snapshot.evidence.sequence != self.context.sequence
                or self.snapshot.evidence.row_sequences[0] <= self.after_sequence):
            raise ValueError("fresh five-row MW board required")


class MonsterWaveBoardAcquisitionRuntime:
    """Read two agreeing frames of an already-open board; send no input."""

    def __init__(self, observer, reader: MonsterWaveBoardReader, *,
                 cancel_requested=lambda: False, clock=time.monotonic) -> None:
        self.observer = observer
        self.reader = reader
        self.cancel_requested = cancel_requested
        self.clock = clock

    def acquire(self) -> FreshMonsterWaveBoard:
        if self.cancel_requested():
            raise RuntimeWaitCancelled()
        first = self.observer.observe()
        if not _board_open(first):
            raise ValueError("fresh_mw_board_popup_not_open")
        second = self.observer.wait_until(
            _board_open, after_sequence=first.sequence, timeout=3.0,
            abort_if=lambda s: not _board_open(s),
            cancel_requested=self.cancel_requested,
        )
        if (not _board_open(second)
                or second.sequence <= first.sequence
                or second.timestamp <= first.timestamp
                or second.timestamp - first.timestamp > 1.0):
            raise ValueError("mw_board_consensus_unavailable")
        now = self.clock()
        if second.timestamp > now or now - second.timestamp > 2.0:
            raise ValueError("fresh_mw_board_snapshot_unavailable")
        sample1 = self.reader.read_sample(first)
        if sample1 is None:
            raise ValueError("first_mw_board_sample_unreadable")
        sample2 = self.reader.read_sample(second)
        if sample2 is None:
            raise ValueError("second_mw_board_sample_unreadable")
        barrier = first.sequence - 1
        fact = consensus_board_samples((sample1, sample2), after_sequence=barrier)
        if fact is None:
            raise ValueError("mw_board_consensus_unavailable")
        board = build_monster_wave_board_snapshot(
            second, after_sequence=barrier, now=self.clock(), board_fact=fact,
        )
        if board is None:
            raise ValueError("fresh_mw_board_snapshot_unavailable")
        return FreshMonsterWaveBoard(second, board, barrier)


class MonsterWaveStandaloneNavigationRuntime:
    """Only the two existing, verified MW actions needed by this caller."""

    def __init__(self, transition, snapshots: MonsterWaveSnapshotRuntime,
                 *, cancel_requested=lambda: False) -> None:
        self.transition = transition
        self.snapshots = snapshots
        self.cancel_requested = cancel_requested

    def close_board(self, board: FreshMonsterWaveBoard):
        if self.cancel_requested():
            return FlowStatus.CANCELLED, None, None
        current = self.transition.observer.wait_until(
            _board_open, after_sequence=board.context.sequence, timeout=3.0,
            abort_if=lambda s: not _board_open(s),
            cancel_requested=self.cancel_requested, stable_for=.25,
        )
        result = self.transition.execute(
            "monster_wave.standalone.decline_board", DeclineMonsterWaveInventory(),
            current, precondition=_board_open, expected=lambda s: clean_mw(s) and skip_state(s) is not None,
            policy=VerifiedTransitionPolicy(max_attempts=1), stable_for=.25,
        )
        if not result.succeeded or result.attempt_count != 1 or result.final_snapshot.sequence <= current.sequence:
            return FlowStatus.FAILED, None, result
        acquired = self.snapshots.acquire(after_sequence=result.final_snapshot.sequence)
        return acquired.status, acquired.fresh, result

    def exit_to_battle_mode(self, anchor: FreshMonsterWaveSnapshot):
        if self.cancel_requested():
            return FlowStatus.CANCELLED, None
        refreshed = self.snapshots.acquire(after_sequence=anchor.context.sequence)
        if refreshed.status is not FlowStatus.COMPLETED:
            return refreshed.status, None
        if refreshed.fresh is None:
            return FlowStatus.FAILED, None
        before = refreshed.fresh.context
        result = self.transition.execute(
            "monster_wave.standalone.exit_to_battle_mode", ExitMonsterWave(),
            before,
            precondition=lambda s: clean_mw(s) and skip_state(s) is not None,
            expected=is_battle_mode_select,
            policy=VerifiedTransitionPolicy(max_attempts=1), stable_for=.25,
        )
        if (not result.succeeded or result.attempt_count != 1
                or result.final_snapshot.sequence <= before.sequence
                or not is_battle_mode_select(result.final_snapshot)):
            return FlowStatus.FAILED, result
        return FlowStatus.COMPLETED, result


class MonsterWaveStandaloneMode(str, Enum):
    ACQUIRE_ONLY = "acquire_only"
    PLAN_ONLY = "plan_only"
    PREREQUISITES_ONLY = "prerequisites_only"
    FULL_ONE_SHOT = "full_one_shot"


class MonsterWaveStandaloneStatus(str, Enum):
    COMPLETED = "completed"
    UNRESOLVED = "unresolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class MonsterWaveStandaloneRequest:
    mode: MonsterWaveStandaloneMode
    non_board: NonBoardResourceFacts | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, MonsterWaveStandaloneMode):
            raise ValueError("mode must be MonsterWaveStandaloneMode")
        if self.mode is not MonsterWaveStandaloneMode.ACQUIRE_ONLY and not isinstance(
            self.non_board, NonBoardResourceFacts
        ):
            raise ValueError("planning modes require explicit NonBoardResourceFacts")


@dataclass(frozen=True)
class MonsterWaveStandaloneResult:
    status: MonsterWaveStandaloneStatus
    phase: str
    reason: str | None = None
    initial_board: FreshMonsterWaveBoard | None = None
    initial_plan: ResourceRoutePlan | None = None
    close_result: VerifiedTransitionResult | None = None
    fresh_mw: FreshMonsterWaveSnapshot | None = None
    route_result: ResourceRouteExecutionResult | None = None
    exit_result: VerifiedTransitionResult | None = None
    activity_result: MonsterWaveResult | None = None
    evidence: tuple[str, ...] = ()


class MonsterWaveStandaloneRunner:
    def __init__(self, boards, navigation, route, activity, *,
                 planner=plan_resource_route, clock=time.monotonic) -> None:
        self.boards = boards
        self.navigation = navigation
        self.route = route
        self.activity = activity
        self.planner = planner
        self.clock = clock

    def run(self, request: MonsterWaveStandaloneRequest) -> MonsterWaveStandaloneResult:
        if not isinstance(request, MonsterWaveStandaloneRequest):
            raise ValueError("request must be MonsterWaveStandaloneRequest")
        details = {}
        evidence = []
        phase = "acquire"

        def finish(status, phase, reason=None):
            return MonsterWaveStandaloneResult(
                status, phase, reason, evidence=tuple(evidence), **details,
            )

        try:
            board = self.boards.acquire()
            details["initial_board"] = board
            evidence.append(f"board_sequence:{board.context.sequence}")
            if request.mode is MonsterWaveStandaloneMode.ACQUIRE_ONLY:
                return finish(MonsterWaveStandaloneStatus.COMPLETED, "acquire")

            phase = "plan"
            plan = self.planner(ResourcePlanningInput(
                board.snapshot, request.non_board, self.clock(), board.after_sequence,
            ))
            if not isinstance(plan, ResourceRoutePlan):
                raise ValueError("planner must return ResourceRoutePlan")
            details["initial_plan"] = plan
            evidence.append(f"plan_status:{plan.status.value}")
            if request.mode is MonsterWaveStandaloneMode.PLAN_ONLY:
                status = (MonsterWaveStandaloneStatus.UNRESOLVED if plan.status in {
                    ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
                    ResourceRouteStatus.CONTRADICTORY,
                } else MonsterWaveStandaloneStatus.COMPLETED)
                return finish(status, "plan", plan.status.value)
            if plan.status in {ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
                               ResourceRouteStatus.CONTRADICTORY}:
                return finish(MonsterWaveStandaloneStatus.UNRESOLVED, "plan", plan.status.value)

            phase = "close_board"
            closed_status, anchor, close_result = self.navigation.close_board(board)
            details["close_result"] = close_result
            if closed_status is not FlowStatus.COMPLETED or not isinstance(anchor, FreshMonsterWaveSnapshot):
                status = (MonsterWaveStandaloneStatus.CANCELLED if closed_status is FlowStatus.CANCELLED
                          else MonsterWaveStandaloneStatus.FAILED)
                return finish(status, "close_board", closed_status.value)
            details["fresh_mw"] = anchor
            evidence.append(f"clean_mw_sequence:{anchor.context.sequence}")

            if plan.status is ResourceRouteStatus.READY:
                phase = "prerequisites"
                route_result = self.route.execute_plan_once(plan, anchor)
                details["route_result"] = route_result
                evidence.extend(route_result.evidence)
                if route_result.status is not ResourceRouteExecutionStatus.SUCCESS:
                    status = (MonsterWaveStandaloneStatus.CANCELLED if route_result.status is ResourceRouteExecutionStatus.CANCELLED
                              else MonsterWaveStandaloneStatus.FAILED)
                    return finish(status, "prerequisites", route_result.status.value)
                if route_result.executed_steps != plan.steps:
                    return finish(MonsterWaveStandaloneStatus.FAILED, "prerequisites", "plan_not_fully_executed")
                try:
                    anchor = FreshMonsterWaveSnapshot(route_result.final_context, route_result.final_snapshot)
                except (TypeError, ValueError):
                    return finish(MonsterWaveStandaloneStatus.FAILED, "prerequisites", "fresh_mw_postcondition_invalid")
                if anchor.context.sequence <= details["fresh_mw"].context.sequence:
                    return finish(MonsterWaveStandaloneStatus.FAILED, "prerequisites", "fresh_mw_postcondition_stale")
                details["fresh_mw"] = anchor
                evidence.append(f"j_final_mw_sequence:{anchor.context.sequence}")
            if request.mode is MonsterWaveStandaloneMode.PREREQUISITES_ONLY:
                return finish(MonsterWaveStandaloneStatus.COMPLETED, "prerequisites")

            phase = "exit_to_battle_mode"
            exit_status, exit_result = self.navigation.exit_to_battle_mode(anchor)
            details["exit_result"] = exit_result
            if exit_status is not FlowStatus.COMPLETED:
                status = (MonsterWaveStandaloneStatus.CANCELLED if exit_status is FlowStatus.CANCELLED
                          else MonsterWaveStandaloneStatus.FAILED)
                return finish(status, "exit_to_battle_mode", exit_status.value)
            if (not isinstance(exit_result, VerifiedTransitionResult)
                    or not exit_result.succeeded or exit_result.attempt_count != 1
                    or exit_result.final_snapshot.sequence <= anchor.context.sequence
                    or not is_battle_mode_select(exit_result.final_snapshot)):
                return finish(MonsterWaveStandaloneStatus.FAILED, "exit_to_battle_mode", "battle_mode_postcondition_invalid")
            evidence.append("verified_exit_to_battle_mode")
            phase = "monster_wave"
            activity_result = self.activity.run()
            details["activity_result"] = activity_result
            evidence.append(f"monster_wave_status:{activity_result.status.value}")
            if activity_result.status is FlowStatus.CANCELLED:
                return finish(MonsterWaveStandaloneStatus.CANCELLED, "monster_wave", activity_result.status.value)
            if activity_result.status is not FlowStatus.COMPLETED:
                return finish(MonsterWaveStandaloneStatus.FAILED, "monster_wave", activity_result.status.value)
            return finish(MonsterWaveStandaloneStatus.COMPLETED, "monster_wave")
        except RuntimeWaitCancelled:
            return finish(MonsterWaveStandaloneStatus.CANCELLED, phase, "cancelled")
        except Exception as error:
            return finish(MonsterWaveStandaloneStatus.FAILED, phase, str(error) or type(error).__name__)
