"""Productive MW: prepare once, then route each fresh SKIP pass."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
import time
from uuid import uuid4

from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL
from bot.equipment_combine_relief import EquipmentCombineReturnPlan
from bot.equipment_relief import (EquipmentReliefOutcome, EquipmentReliefRequest,
                                  FreshCallerContext)
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.monster_wave_activity import MonsterWaveResult, clean_mw, popup, skip_state
from bot.monster_wave_flow import MonsterWaveFlow
from bot.sapphire_pressure import sapphire_pressure_passes
from bot.event_log import record_best_effort
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
from bot.semantic_actions import ExitCombine, ExitSocket
from bot.socket_inventory_relief import SocketReliefOutcome, SocketReturnPlan
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE


class ProductiveMonsterWaveFlow:
    """Compose fresh board decisions with the existing MW and route owners."""

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
        equipment_relief=None,
        equipment_sell_plan=None,
        socket_relief=None,
        clock=time.monotonic,
    ) -> None:
        if not isinstance(inner, MonsterWaveFlow):
            raise ValueError("inner must be MonsterWaveFlow")
        for owner, method in (
            (boards, "acquire"),
            (navigation, "close_board"),
            (navigation, "accept_board"),
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
        self.equipment_relief = equipment_relief
        self.equipment_sell_plan = equipment_sell_plan
        self.socket_relief = socket_relief
        self.clock = clock

    def prepared(self, zone, *, yield_resource_board=False):
        return PreparedActivity(
            self.name, zone, partial(self._run_activity_l1, keep_current=True),
            entry_readiness=self.entry_readiness, exit_postconditions=self.contract.successful_postconditions,
        )

    def entry_readiness(self):
        return self.inner.entry_readiness(pressure_relief=True)

    def run(self, *, yield_resource_board=False):
        # Enter once, finish gameplay on a verified reusable surface.
        ready=self.entry_readiness()
        if ready is not None:return ready
        entered = self.zone.enter()
        if not entered.succeeded:
            return MonsterWaveResult(
                entered.status, error=entered.error, failure=entered.failure,
                transition_outcomes=entered.transition_outcomes,
                transition_attempts=entered.transition_attempts,
            )
        result = self._run_activity_l1(keep_current=True)
        result = replace(result,
            transition_outcomes=entered.transition_outcomes + result.transition_outcomes,
            transition_attempts=entered.transition_attempts + result.transition_attempts)
        if not result.succeeded:
            return result
        return result

    def _first_leg(self) -> MonsterWaveResult:
        return self.activity.run_pass(yield_resource_board=True)

    def _resume_leg(self) -> MonsterWaveResult:
        entered = self.activity.reenter()
        if not entered.succeeded:
            return entered
        passed = self.activity.run_pass(resume_after_relief=True)
        return self.activity._merge(entered, passed)

    def _run_activity_l1(self, *, return_to_lobby=False, keep_current=False) -> FlowResult:
        """Prepare once; reevaluate pressure after each verified CLEAR effect."""
        try:
            prepared = self.activity.prepare(pressure_relief=True)
        except RuntimeWaitCancelled:
            return MonsterWaveResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveResult(
                FlowStatus.FAILED, error=str(error) or type(error).__name__,
            )
        if not prepared.succeeded or prepared.event_count('monster_wave.no_work'):
            return prepared
        def finish_surface():
            if not keep_current:
                return (self.activity.leave(return_to_lobby=True)
                        if return_to_lobby else self.activity.leave())
            if self.activity.cancel_requested():
                return MonsterWaveResult(FlowStatus.CANCELLED)
            final = self.activity.observer.observe()
            if not clean_mw(final):
                return MonsterWaveResult(FlowStatus.FAILED, error='mw_completion_surface_unconfirmed')
            return MonsterWaveResult(FlowStatus.COMPLETED, final_snapshot=final)

        initial = prepared.sapphires_initial
        if type(initial) is not int or initial < 0:
            return MonsterWaveResult(FlowStatus.FAILED, error='mw_initial_sapphires_unavailable',
                                     events=prepared.events)
        balance = initial
        pass_budget = max(32, sapphire_pressure_passes(initial))
        result = prepared
        consumed = 0
        for _ in range(pass_budget):
            if sapphire_pressure_passes(balance) == 0:
                break
            try:
                first = self._first_leg()
            except RuntimeWaitCancelled:
                first = MonsterWaveResult(FlowStatus.CANCELLED)
            except Exception as error:
                first = MonsterWaveResult(FlowStatus.FAILED, error=str(error) or type(error).__name__)
            passed = (self._consume_pending(first)
                      if first.status is FlowStatus.RESOURCE_BOARD_PENDING
                      else self._relieve_blockers(first))
            result = replace(passed,
                events=result.events + passed.events,
                transition_outcomes=result.transition_outcomes + passed.transition_outcomes,
                transition_attempts=result.transition_attempts + passed.transition_attempts,
                sapphires_initial=initial, sapphires_consumed=consumed)
            if not passed.succeeded:
                return result
            if passed.event_count('monster_wave.insufficient_sapphires'):
                # The popup alone cannot prove the pressure postcondition.
                try:
                    fact = self.activity.read_sapphires_after_clear()
                    if sapphire_pressure_passes(fact.value):
                        raise ValueError('mw_pressure_remaining_after_insufficient_sapphires')
                except RuntimeWaitCancelled:
                    return replace(result, status=FlowStatus.CANCELLED)
                except Exception as error:
                    return replace(result, status=FlowStatus.FAILED, error=str(error))
                left = finish_surface()
                return replace(left,
                    events=result.events + left.events,
                    transition_outcomes=result.transition_outcomes + left.transition_outcomes,
                    transition_attempts=result.transition_attempts + left.transition_attempts,
                    sapphires_initial=initial, sapphires_consumed=consumed)
            if passed.event_count('monster_wave.completed') != 1:
                return replace(result, status=FlowStatus.FAILED,
                               error='mw_pass_without_confirmed_clear')
            try:
                fact = self.activity.read_sapphires_after_clear()
            except RuntimeWaitCancelled:
                return replace(result, status=FlowStatus.CANCELLED)
            except Exception as error:
                return replace(result, status=FlowStatus.FAILED, error=str(error))
            record_best_effort(getattr(self.activity, 'events', None),
                'monster_wave.sapphire_effect', before=balance, after=fact.value,
                source_sequence=fact.sequence, passes_needed=sapphire_pressure_passes(fact.value))
            consumed += max(0, balance - fact.value)
            balance = fact.value
            result = replace(result, sapphires_consumed=consumed,
                events=result.events + (FlowEvent('monster_wave.sapphire_effect', fields={
                    'after':balance, 'source_sequence':fact.sequence}),))
        if sapphire_pressure_passes(balance):
            return replace(result, status=FlowStatus.FAILED, error='mw_pressure_pass_budget_exhausted')
        left = finish_surface()
        return replace(left,
            events=result.events + left.events,
            transition_outcomes=result.transition_outcomes + left.transition_outcomes,
            transition_attempts=result.transition_attempts + left.transition_attempts,
            sapphires_initial=initial, sapphires_consumed=consumed)

    def _consume_pending(self, first: MonsterWaveResult) -> FlowResult:
        """YES clean board, or NO and relieve/retry this blocked pass once."""
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
            from bot.event_log import record_best_effort

            record_best_effort(
                getattr(self.activity, "events", None),
                "monster_wave.resource_plan",
                plan_status=plan.status.value,
                step_kinds=tuple(step.capability for step in plan.steps),
                evidence_items=tuple(dict.fromkeys(
                    fact.item_id for fact in plan.evidence
                    if fact.item_id is not None
                )),
            )
            if plan.status in {ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
                               ResourceRouteStatus.CONTRADICTORY}:
                return MonsterWaveResult(
                    FlowStatus.FAILED, error=f"board_plan_{plan.status.value}",
                    events=first.events,
                )
            if plan.status is ResourceRouteStatus.NO_PREREQUISITES:
                accepted_status, after_yes = self.navigation.accept_board(board)
                if accepted_status is FlowStatus.CANCELLED:
                    return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
                if accepted_status is not FlowStatus.COMPLETED or after_yes is None:
                    return MonsterWaveResult(FlowStatus.FAILED,
                                             error='accept_board_failed', events=first.events)
                passed = self._relieve_blockers(self.activity.finish_pass(after_yes))
                return replace(passed, events=first.events + passed.events,
                               transition_outcomes=first.transition_outcomes + passed.transition_outcomes,
                               transition_attempts=first.transition_attempts + passed.transition_attempts)
            # Pressure: decline this board before the existing relief route.
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
                    failing = getattr(route_result, "failing_step", None) or "unknown"
                    capability = getattr(route_result, "capability_result", None)
                    record_best_effort(
                        getattr(self.activity, "events", None), "monster_wave.preparation.failed",
                        route_status=route_result.status.value, failing_step=failing,
                        reason=getattr(capability, "reason", None),
                        outcome=getattr(getattr(capability, "outcome", None), "value", None),
                        inputs=getattr(capability, "inputs", ()),
                        route_evidence=getattr(route_result, "evidence", ()),
                    )
                    return MonsterWaveResult(
                        FlowStatus.FAILED,
                        error=f"preparation_failed:{route_result.status.value}:{failing}",
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
            else:
                return MonsterWaveResult(
                    FlowStatus.FAILED, error="unexpected_plan_status",
                    events=first.events,
                )
            # The route returns a verified fresh MW anchor after closing its
            # modal or resolving its real return destination. Resume the SAME
            # pass on MW; Back/reentry would discard this valid parent context.
            record_best_effort(getattr(self.activity,"events",None),
                "monster_wave.prerequisite.resume",context=SCREEN_MONSTER_WAVE,
                source_sequence=anchor.context.sequence,back_count=0,mw_reentry=0)
            try:
                second = self.activity.run_pass(resume_after_relief=True)
            except RuntimeWaitCancelled:
                return MonsterWaveResult(FlowStatus.CANCELLED, events=first.events)
            except Exception as error:
                return MonsterWaveResult(
                    FlowStatus.FAILED,
                    error=str(error) or type(error).__name__,
                    events=first.events,
                )
            second = self._relieve_blockers(second)
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

    @staticmethod
    def _blocker(result: MonsterWaveResult) -> str | None:
        if result.status is not FlowStatus.MANUAL_RESOLUTION:
            return None
        matches = [event.fields.get("blocker") for event in result.events
                   if event.kind == "monster_wave.manual_resolution"]
        if len(matches) != 1 or matches[0] not in {
            POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL,
        }:
            raise ValueError("mw_blocker_result_ambiguous")
        return matches[0]

    def _relieve_blockers(self, result: MonsterWaveResult) -> MonsterWaveResult:
        """Compose only the two causal blocker branches after L1's final resume."""
        equipment_used = False
        socket_used = False
        events = list(result.events)

        def retry() -> MonsterWaveResult:
            if self.activity.cancel_requested():
                raise RuntimeWaitCancelled()
            returned = self._resume_leg()
            events.extend(returned.events)
            return returned

        try:
            while result.status is FlowStatus.MANUAL_RESOLUTION:
                blocker = self._blocker(result)
                if blocker == POPUP_EQUIPMENT_INVENTORY_FULL:
                    if equipment_used:
                        raise ValueError("mw_equipment_recovery_exhausted")
                    equipment_used = True
                    if self.equipment_relief is None:
                        return result
                    initial = result
                    first_attempt = True

                    def acquire(after_sequence):
                        if self.activity.cancel_requested():
                            raise RuntimeWaitCancelled()
                        if after_sequence is None:
                            context = self.activity.observer.observe()
                            if not popup(blocker)(context):
                                raise ValueError("mw_equipment_popup_not_fresh")
                        else:
                            context = self.activity.observer.wait_until(
                                lambda s: clean_mw(s) and skip_state(s) is not None,
                                after_sequence=after_sequence, timeout=6,
                                stable_for=.25,
                                cancel_requested=self.activity.cancel_requested,
                            )
                        return FreshCallerContext(context, context.sequence)

                    def execute(_request, context):
                        nonlocal first_attempt
                        if first_attempt:
                            first_attempt = False
                            return initial
                        # Same-pass retry from the restored MW: the combine
                        # return plan already verified screen.monster_wave and
                        # acquire() confirmed fresh clean MW, so the pass is
                        # retried directly without exiting to Battle Mode.
                        # run_pass re-observes and still requires active MAX.
                        if self.activity.cancel_requested():
                            raise RuntimeWaitCancelled()
                        passed = self.activity.run_pass(resume_after_relief=True)
                        events.extend(passed.events)
                        return passed

                    request = EquipmentReliefRequest(
                        operation_request=initial,
                        acquire_context=acquire,
                        execute_operation=execute,
                        is_equipment_full=lambda r: self._blocker(r) == POPUP_EQUIPMENT_INVENTORY_FULL,
                        enter_combine=lambda _: self.navigation.enter_blocker_relief(blocker),
                        combine_return_plan=EquipmentCombineReturnPlan(
                            ExitCombine(), SCREEN_MONSTER_WAVE),
                        sell_plan=self.equipment_sell_plan,
                        cancel_requested=self.activity.cancel_requested,
                    )
                    relief = self.equipment_relief.run(request)
                    if relief.outcome in {EquipmentReliefOutcome.CANCELLED,
                                          EquipmentReliefOutcome.COMBINE_CANCELLED,
                                          EquipmentReliefOutcome.SELL_CANCELLED}:
                        return MonsterWaveResult(FlowStatus.CANCELLED, events=tuple(events))
                    if relief.outcome is EquipmentReliefOutcome.SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE:
                        # Known full after the bounded Combine attempt. A Sell
                        # policy/candidate is missing: stop as an expected manual
                        # boundary without another SKIP, Combine or consumption.
                        return MonsterWaveResult(FlowStatus.MANUAL_RESOLUTION, events=tuple(events))
                    if relief.outcome is not EquipmentReliefOutcome.CALLER_RESULT:
                        raise ValueError(f"mw_equipment_relief:{relief.outcome.value}:{relief.error or relief.stage}")
                    result = relief.caller_result
                elif blocker == POPUP_SOCKET_INVENTORY_FULL:
                    if socket_used:
                        raise ValueError("mw_socket_recovery_exhausted")
                    socket_used = True
                    if self.socket_relief is None:
                        return result
                    self.navigation.enter_blocker_relief(blocker)
                    relief = self.socket_relief.run(
                        SocketReturnPlan(ExitSocket(), SCREEN_MONSTER_WAVE),
                        cancel_requested=self.activity.cancel_requested,
                    )
                    if relief.outcome is SocketReliefOutcome.CANCELLED:
                        return MonsterWaveResult(FlowStatus.CANCELLED, events=tuple(events))
                    if relief.outcome not in {SocketReliefOutcome.RELIEVED,
                                              SocketReliefOutcome.NO_RELIEF_AVAILABLE}:
                        raise ValueError(f"mw_socket_relief:{relief.error or relief.outcome.value}")
                    self.navigation.exit_after_relief(relief.final_snapshot)
                    result = retry()
                else:
                    raise ValueError("mw_blocker_result_ambiguous")
            if result.succeeded and result.event_count('monster_wave.completed') == 1:
                # Retain the real intermediate manual boundary, and explicitly
                # resolve only this pass's blockers after its confirmed CLEAR.
                for index,pending in enumerate(tuple(events)):
                    if pending.kind == 'monster_wave.manual_resolution':
                        boundary_id=uuid4().hex
                        events[index]=replace(pending,fields={**pending.fields,'relief_boundary_id':boundary_id})
                        events.append(FlowEvent('monster_wave.relief_resolved', fields={
                            'blocker': pending.fields.get('blocker'),
                            'relief_boundary_id':boundary_id,
                            'resolved_event_created_at': pending.created_at.isoformat(),
                        }))
            return replace(result, events=tuple(events))
        except RuntimeWaitCancelled:
            return MonsterWaveResult(FlowStatus.CANCELLED, events=tuple(events))
        except Exception as error:
            return MonsterWaveResult(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                                     events=tuple(events))


__all__ = ("ProductiveMonsterWaveFlow",)
