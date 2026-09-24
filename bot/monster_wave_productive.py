"""Productive Monster Wave wiring (L1): consume one RESOURCE_BOARD_PENDING.

One original MW intent runs as:
  first activity (same request + yield=True)
  -> RESOURCE_BOARD_PENDING(board_sequence)
  -> acquire one board snapshot after barrier (A1, <=1)
  -> plan once (I2, <=1)
  -> close board once + execute preparation at most once (J, <=1)
  -> exit to Battle Mode once
  -> resume SAME request once (yield=False, <=1)
  -> terminal result or surfaced blocker.

No recursive second preparation, no post-J replan. Empty plan resumes
without fabricating work. Equipment/Socket Full on the resumed attempt
surfaces as MANUAL_RESOLUTION with no relief (L2 out of scope).
"""

from __future__ import annotations

from dataclasses import replace
import time

from bot.flow_contracts import FlowResult, FlowStatus
from bot.monster_wave_activity import MonsterWaveResult
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_resource_route import (
    FreshMonsterWaveSnapshot,
    ResourceRouteExecutionStatus,
)
from bot.prepared_activity import PreparedActivity
from bot.resource_route_planner import (
    NonBoardResourceFacts,
    ResourcePlanningInput,
    ResourceRoutePlan,
    ResourceRouteStatus,
    plan_resource_route,
)
from bot.runtime_observer import RuntimeWaitCancelled


class ProductiveMonsterWaveFlow:
    """Thin L1 composition root over the existing MW activity and J/K owners."""

    name = "monster_wave"
    scope = MonsterWaveFlow.scope
    contract = MonsterWaveFlow.contract

    def __init__(
        self,
        inner: MonsterWaveFlow,
        *,
        boards,
        navigation,
        route,
        planner=plan_resource_route,
        non_board: NonBoardResourceFacts | None = None,
        clock=time.monotonic,
    ) -> None:
        if not isinstance(inner, MonsterWaveFlow):
            raise ValueError("inner must be MonsterWaveFlow")
        for owner, method in (
            (boards, "acquire"),
            (navigation, "close_board"),
            (navigation, "exit_to_battle_mode"),
            (route, "execute_plan_once"),
        ):
            if not callable(getattr(owner, method, None)):
                raise ValueError(f"runtime must provide {method}()")
        if not callable(planner):
            raise ValueError("planner must be callable")
        if non_board is None:
            non_board = NonBoardResourceFacts()
        if not isinstance(non_board, NonBoardResourceFacts):
            raise ValueError("non_board must be NonBoardResourceFacts")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self.inner = inner
        self.activity = inner.activity
        self.zone = inner.zone
        self.boards = boards
        self.navigation = navigation
        self.route = route
        self.planner = planner
        self.non_board = non_board
        self.clock = clock

    def prepared(self, zone, *, daily=False, yield_resource_board=False):
        # Productive L1 always consumes the board internally: first leg
        # uses the original daily request + yield=True, resume uses the
        # same daily request + yield=False. The incoming yield flag is
        # legacy compat and never rebuilds the request from defaults.
        if not isinstance(daily, bool):
            raise ValueError("daily must be bool")
        return PreparedActivity(
            self.name, zone, lambda: self._run_activity_l1(daily=daily),
        )

    def run(self, *, yield_resource_board=False):
        # Standalone path (Lobby -> Lobby): same L1 inside one zone visit.
        # The incoming yield flag is ignored; L1 always starts with True.
        entered = self.zone.enter()
        if not entered.succeeded:
            return MonsterWaveResult(
                entered.status, error=entered.error, failure=entered.failure,
                transition_outcomes=entered.transition_outcomes,
                transition_attempts=entered.transition_attempts,
            )
        first = self._first_leg(daily=False)
        if first.status is not FlowStatus.RESOURCE_BOARD_PENDING:
            result = first
            result = replace(
                result,
                transition_outcomes=entered.transition_outcomes + result.transition_outcomes,
                transition_attempts=entered.transition_attempts + result.transition_attempts,
            )
            if not result.succeeded:
                return result
            closed = self.zone.leave()
            return replace(
                result, status=closed.status, error=closed.error, failure=closed.failure,
                transition_outcomes=result.transition_outcomes + closed.transition_outcomes,
                transition_attempts=result.transition_attempts + closed.transition_attempts,
            )
        second = self._consume_pending(first, daily=False)
        second = replace(
            second,
            transition_outcomes=(
                entered.transition_outcomes
                + first.transition_outcomes
                + second.transition_outcomes
            ),
            transition_attempts=(
                entered.transition_attempts
                + first.transition_attempts
                + second.transition_attempts
            ),
        )
        if not second.succeeded:
            return second
        closed = self.zone.leave()
        return replace(
            second, status=closed.status, error=closed.error, failure=closed.failure,
            transition_outcomes=second.transition_outcomes + closed.transition_outcomes,
            transition_attempts=second.transition_attempts + closed.transition_attempts,
        )

    def _first_leg(self, *, daily: bool) -> MonsterWaveResult:
        return self.activity.run(daily_sapphires=daily, yield_resource_board=True)

    def _resume_leg(self, *, daily: bool) -> MonsterWaveResult:
        return self.activity.run(daily_sapphires=daily, yield_resource_board=False)

    def _run_activity_l1(self, *, daily: bool) -> FlowResult:
        """Prepared path: zone is owned by SessionRunner, only activity legs."""
        try:
            first = self._first_leg(daily=daily)
        except RuntimeWaitCancelled:
            return MonsterWaveResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveResult(
                FlowStatus.FAILED, error=str(error) or type(error).__name__,
            )
        if first.status is not FlowStatus.RESOURCE_BOARD_PENDING:
            return first
        return self._consume_pending(first, daily=daily)

    def _consume_pending(self, first: MonsterWaveResult, *, daily: bool) -> FlowResult:
        """Acquire -> plan once -> close + J at most once -> resume once."""
        try:
            board_sequence = first.board_sequence
            if type(board_sequence) is not int or board_sequence < 1:
                return MonsterWaveResult(
                    FlowStatus.FAILED, error="pending_board_sequence_invalid",
                    events=first.events,
                )
            # A1: one board snapshot strictly after the pending barrier.
            try:
                board = self.boards.acquire(after_sequence=board_sequence)
            except RuntimeWaitCancelled:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            except Exception as error:
                return MonsterWaveResult(
                    FlowStatus.FAILED,
                    error=str(error) or type(error).__name__,
                    events=first.events,
                )
            # I2: plan exactly once from the fresh snapshot + explicit facts.
            try:
                plan = self.planner(
                    ResourcePlanningInput(
                        board.snapshot, self.non_board, self.clock(),
                        board.after_sequence,
                    )
                )
            except RuntimeWaitCancelled:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            except Exception as error:
                return MonsterWaveResult(
                    FlowStatus.FAILED,
                    error=str(error) or type(error).__name__,
                    events=first.events,
                )
            if not isinstance(plan, ResourceRoutePlan):
                return MonsterWaveResult(
                    FlowStatus.FAILED, error="planner_must_return_plan",
                    events=first.events,
                )
            # Close the open board once to reach clean MW for J/resume.
            try:
                closed_status, anchor, _close_result = self.navigation.close_board(board)
            except RuntimeWaitCancelled:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            except Exception as error:
                return MonsterWaveResult(
                    FlowStatus.FAILED,
                    error=str(error) or type(error).__name__,
                    events=first.events,
                )
            if closed_status is FlowStatus.CANCELLED:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            if closed_status is not FlowStatus.COMPLETED or not isinstance(
                anchor, FreshMonsterWaveSnapshot
            ):
                return MonsterWaveResult(
                    FlowStatus.FAILED, error=f"close_board_failed:{closed_status.value}",
                    events=first.events,
                )
            if plan.status is ResourceRouteStatus.READY:
                # J: execute the immutable plan exactly once, no replan.
                try:
                    route_result = self.route.execute_plan_once(plan, anchor)
                except RuntimeWaitCancelled:
                    return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
                except Exception as error:
                    return MonsterWaveResult(
                        FlowStatus.FAILED,
                        error=str(error) or type(error).__name__,
                        events=first.events,
                    )
                if route_result.status is ResourceRouteExecutionStatus.CANCELLED:
                    return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
                if route_result.status is not ResourceRouteExecutionStatus.SUCCESS:
                    return MonsterWaveResult(
                        FlowStatus.FAILED,
                        error=f"preparation_failed:{route_result.status.value}",
                        events=first.events,
                    )
                if tuple(route_result.executed_steps) != tuple(plan.steps):
                    return MonsterWaveResult(
                        FlowStatus.FAILED, error="plan_not_fully_executed",
                        events=first.events,
                    )
                try:
                    anchor = FreshMonsterWaveSnapshot(
                        route_result.final_context, route_result.final_snapshot
                    )
                except (TypeError, ValueError):
                    return MonsterWaveResult(
                        FlowStatus.FAILED, error="fresh_mw_postcondition_invalid",
                        events=first.events,
                    )
            elif plan.status not in {
                ResourceRouteStatus.NO_PREREQUISITES,
                ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
                ResourceRouteStatus.CONTRADICTORY,
            }:
                return MonsterWaveResult(
                    FlowStatus.FAILED, error="unexpected_plan_status",
                    events=first.events,
                )
            # Exit MW clean to Battle Mode once before the causal resume.
            try:
                exit_status, _exit_result = self.navigation.exit_to_battle_mode(anchor)
            except RuntimeWaitCancelled:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            except Exception as error:
                return MonsterWaveResult(
                    FlowStatus.FAILED,
                    error=str(error) or type(error).__name__,
                    events=first.events,
                )
            if exit_status is FlowStatus.CANCELLED:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            if exit_status is not FlowStatus.COMPLETED:
                return MonsterWaveResult(
                    FlowStatus.FAILED, error=f"exit_failed:{exit_status.value}",
                    events=first.events,
                )
            # Causal resume: SAME request (daily preserved) + yield=False, once.
            try:
                second = self._resume_leg(daily=daily)
            except RuntimeWaitCancelled:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            except Exception as error:
                return MonsterWaveResult(
                    FlowStatus.FAILED,
                    error=str(error) or type(error).__name__,
                    events=first.events,
                )
            # Merge first-leg business evidence (pending) with terminal leg.
            try:
                merged = tuple(first.events) + tuple(second.events)
                return replace(second, events=merged)
            except Exception:
                return second
        except RuntimeWaitCancelled:
            return MonsterWaveResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveResult(
                FlowStatus.FAILED, error=str(error) or type(error).__name__,
            )


__all__ = ("ProductiveMonsterWaveFlow",)
