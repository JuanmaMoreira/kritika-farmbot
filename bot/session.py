"""Minimal sequential composition of PER_CHARACTER flows and rotation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from numbers import Integral, Real
from time import perf_counter
from typing import Callable

from bot.component_contracts import ComponentContract, ComponentRequirement
from bot.config import DEFAULT_CHARACTER_COUNT
from bot.event_log import EventSink
from bot.event_context import event_context, event_scope, new_correlation_id, operation_scope
from bot.failure_cause import FailureCause
from bot.eligibility import EligibilityCheck, EligibilityResult, EligibilityStatus
from bot.failure_evidence import publish_failure
from bot.flow_contracts import publish_flow_events, run_flow_with_optional_seed
from bot.flow_contracts import (
    FlowEvent,
    FlowContract,
    FlowResult,
    FlowScope,
    FlowStatus,
    PerCharacterFlow,
)
from bot.preconditions import EnsureResult, PreconditionEnsurer
from bot.prepared_activity import PreparedActivity
from bot.character_resources import character_resource_scope
from bot.runtime_observer import RuntimeWaitCancelled
from bot.rotation import RotationResult, RotationStrategy


def controlled_unavailable(result: FlowResult, allowed: frozenset[str]) -> bool:
    """Only registry-declared business unavailability can follow routine policy."""
    return (result.status is FlowStatus.MANUAL_RESOLUTION
            and result.error is None and result.failure is None
            and bool(result.events)
            and all(event.kind in allowed for event in result.events))


class SessionStatus(str, Enum):
    COMPLETED = "completed"
    MANUAL_RESOLUTION = "manual_resolution"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CharacterContext:
    """Optional recognized class label and its OCR confidence, never session index."""

    name: str | None = None
    name_confidence: float | None = None

    def __post_init__(self) -> None:
        if self.name is not None:
            if not isinstance(self.name, str) or not self.name.strip():
                raise ValueError("name must be None or a non-empty string")
            object.__setattr__(self, "name", self.name.strip())
        if self.name_confidence is not None:
            confidence = self.name_confidence
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, Real)
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise ValueError("name_confidence must be between zero and one")
            object.__setattr__(self, "name_confidence", float(confidence))


@dataclass(frozen=True)
class SessionPlan:
    character_count: int
    flows: tuple[PerCharacterFlow, ...]
    rotation_strategy: RotationStrategy
    rotate: bool = field(default=True, kw_only=True)
    eligibility: tuple[EligibilityCheck | None, ...] = field(default=(), kw_only=True)
    controlled_unavailable: tuple[frozenset[str], ...] = field(default=(), kw_only=True)
    step_positions: tuple[int, ...] = field(default=(), kw_only=True)

    def __post_init__(self) -> None:
        count = _positive_integer(self.character_count, "character_count")
        flows = tuple(self.flows)
        if not flows:
            raise ValueError("flows must contain at least one PER_CHARACTER flow")
        for flow in flows:
            if getattr(flow, "scope", None) is not FlowScope.PER_CHARACTER:
                raise ValueError("only PER_CHARACTER flows are supported")
            if not isinstance(getattr(flow, "name", None), str) or not flow.name.strip():
                raise ValueError("each flow must have a non-empty name")
            if not callable(getattr(flow, "run", None)):
                raise ValueError("each flow must provide run()")
            if not isinstance(getattr(flow, "contract", None), FlowContract):
                raise ValueError("each flow must declare a FlowContract")
        rotation = self.rotation_strategy
        if not callable(getattr(rotation, "advance", None)):
            raise ValueError("rotation_strategy must provide advance()")
        if getattr(rotation, "character_count", None) != count:
            raise ValueError(
                "rotation_strategy.character_count must match character_count"
            )
        if not isinstance(getattr(rotation, "contract", None), ComponentContract):
            raise ValueError("rotation_strategy must declare a ComponentContract")
        if type(self.rotate) is not bool:
            raise ValueError("rotate must be bool")
        object.__setattr__(self, "character_count", count)
        object.__setattr__(self, "flows", flows)
        checks = tuple(self.eligibility) or (None,) * len(flows)
        if len(checks) != len(flows) or any(
            check is not None and not callable(getattr(check, "evaluate", None))
            for check in checks
        ):
            raise ValueError("eligibility must contain one check or None per flow")
        object.__setattr__(self, "eligibility", checks)
        policies = tuple(self.controlled_unavailable) or (frozenset(),) * len(flows)
        if len(policies) != len(flows) or any(not isinstance(p, frozenset) for p in policies):
            raise ValueError("controlled_unavailable must contain one event set per flow")
        object.__setattr__(self, "controlled_unavailable", policies)
        positions = tuple(self.step_positions) or tuple(range(len(flows)))
        if len(positions) != len(flows):
            raise ValueError("step_positions must contain one position per flow")
        object.__setattr__(self, "step_positions", positions)

    @classmethod
    def standard(
        cls,
        *,
        flows: tuple[PerCharacterFlow, ...],
        rotation_strategy: RotationStrategy,
        character_count: int = DEFAULT_CHARACTER_COUNT,
        rotate: bool = True,
        eligibility: tuple[EligibilityCheck | None, ...] = (),
        controlled_unavailable: tuple[frozenset[str], ...] = (),
        step_positions: tuple[int, ...] = (),
    ) -> "SessionPlan":
        return cls(character_count, flows, rotation_strategy, rotate=rotate, eligibility=eligibility,
                   controlled_unavailable=controlled_unavailable, step_positions=step_positions)


@dataclass(frozen=True)
class SessionCharacterResult:
    index: int
    character_context: CharacterContext
    flow_results: tuple[FlowResult, ...]
    advance_result: RotationResult | None = None
    completed: bool = False

    @property
    def events(self) -> tuple[FlowEvent, ...]:
        return tuple(
            event for result in self.flow_results for event in result.events
        )


@dataclass(frozen=True)
class SessionResult:
    status: SessionStatus
    characters_processed: int
    advances_completed: int
    character_results: tuple[SessionCharacterResult, ...]
    failure_character_index: int | None = None
    failure_flow: str | None = None
    failure_cause: str | None = None
    failure: FailureCause | None = field(default=None, kw_only=True)
    run_id: str | None = field(default=None, kw_only=True)
    session_id: str | None = field(default=None, kw_only=True)
    expected_character_count: int | None = field(default=None, kw_only=True)
    flow_names: tuple[str, ...] = field(default=(), kw_only=True)
    duration: float | None = field(default=None, kw_only=True, compare=False)
    failure_flow_position: int | None = field(default=None, kw_only=True)

    def __post_init__(self):
        context = event_context()
        object.__setattr__(self, "run_id", self.run_id or context["run_id"])
        object.__setattr__(self, "session_id", self.session_id or context["session_id"])
        if self.failure_cause is not None and self.failure is None:
            object.__setattr__(self, "failure", FailureCause.from_error(self.failure_cause, kind="session_failure"))

    @property
    def events(self) -> tuple[FlowEvent, ...]:
        return tuple(
            event for character in self.character_results for event in character.events
        )

    def event_count(self, kind: str) -> int:
        return sum(event.kind == kind for event in self.events)

    @property
    def low_gold_count(self) -> int:
        return self.event_count("low_gold")

    @property
    def inventory_full_count(self) -> int:
        return self.event_count("inventory_full")


class SessionRunner:
    """Execute a plan sequentially and abort conservatively on technical failure."""

    def __init__(
        self,
        plan: SessionPlan,
        *,
        preconditions: PreconditionEnsurer,
        events: EventSink,
        cancel_requested: Callable[[], bool] = lambda: False,
        character_context_factory: Callable[[int], CharacterContext] | None = None,
    ) -> None:
        if not isinstance(plan, SessionPlan):
            raise ValueError("plan must be SessionPlan")
        if not isinstance(preconditions, PreconditionEnsurer):
            raise ValueError(
                "preconditions must provide ensure() and current_satisfies_any()"
            )
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record(event, **fields)")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        if character_context_factory is not None and not callable(
            character_context_factory
        ):
            raise ValueError("character_context_factory must be callable or None")
        self.plan = plan
        self.preconditions = preconditions
        self.events = events
        self.cancel_requested = cancel_requested
        self.character_context_factory = character_context_factory
        self._observation_cancelled = False

    def run(self) -> SessionResult:
        self._observation_cancelled = False
        started = perf_counter()
        with event_scope(
            run_id=event_context()["run_id"] or getattr(self.events, "run_id", None) or new_correlation_id(),
            session_id=new_correlation_id(), character_index=None, flow=None,
            operation_id=None, parent_operation_id=None, step=None,
        ):
            result = self._run()
            return replace(
                result,
                expected_character_count=self.plan.character_count,
                flow_names=tuple(flow.name for flow in self.plan.flows),
                duration=max(0.0, perf_counter() - started),
            )

    def _run(self) -> SessionResult:
        character_results: list[SessionCharacterResult] = []
        advances_completed = 0
        self._record("session.started", character_count=self.plan.character_count)

        for index in range(1, self.plan.character_count + 1):
            if self._cancelled():
                return self._cancel(character_results, advances_completed)

            with event_scope(character_index=index), character_resource_scope():
                context = CharacterContext()
                self._record(
                    "session.character.started",
                    character_index=index,
                    character_count=self.plan.character_count,
                    character_name=context.name,
                )
                flow_results: list[FlowResult] = []
                next_requested = None
                for flow_position, flow in enumerate(self.plan.flows):
                    with event_scope(flow=flow.name, flow_id=flow.name,
                                     step_index=self.plan.step_positions[flow_position] + 1,
                                     occurrence=sum(f.name == flow.name for f in self.plan.flows[:flow_position+1])), operation_scope(flow.name):
                        if self._cancelled():
                            character_results.append(
                                SessionCharacterResult(index, context, tuple(flow_results))
                            )
                            return self._cancel(character_results, advances_completed)

                        next_requested = next_requested or flow.name
                        # Deferred routing naturally looks through pure no-work proofs,
                        # in literal step order. Never call Eligibility/entry readiness here.
                        proof = (getattr(flow, 'routing_no_work', None)
                                 if self.plan.eligibility[flow_position] is None else None)
                        if proof is not None:
                            try:
                                no_work = proof()
                                if no_work is not None and (not isinstance(no_work, FlowResult)
                                        or no_work.status is not FlowStatus.COMPLETED
                                        or no_work.error is not None or no_work.failure is not None):
                                    raise ValueError('invalid_routing_no_work_proof')
                            except RuntimeWaitCancelled:
                                character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                                return self._cancel(character_results, advances_completed)
                            except Exception as error:
                                character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                                return self._fail(character_results, advances_completed, index=index,
                                                  flow=flow.name, flow_position=flow_position, cause=str(error))
                            if self._cancelled():
                                character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                                return self._cancel(character_results, advances_completed)
                            if no_work is not None:
                                flow_results.append(no_work)
                                self._record_flow_events(flow.name, no_work.events, index, context)
                                self._record('routine.step.result', result=no_work.status.value, decision='no_work_proven')
                                self._record('flow.completed', component=flow.name, flow=flow.name,
                                             character_index=index, business_event_count=len(no_work.events),
                                             current_surface=getattr(self.preconditions, 'last_context', None),
                                             no_work_proven=True)
                                continue

                        zone = flow.zone if isinstance(flow, PreparedActivity) else None
                        # Entry-only readiness runs before opening a visit. From an
                        # existing hub/MW, Navigation ensures the hub directly.
                        at_zone_entry = zone is not None and self._current_satisfies_any((zone.entry_requirement,))
                        requirement = (zone.entry_requirement if at_zone_entry
                                       else flow.contract.precondition)
                        if self._cancelled():
                            character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                            return self._cancel(character_results, advances_completed)
                        ensured = self._ensure(requirement, requested_flow=next_requested, useful_flow=flow.name)
                        if self._cancelled():
                            character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                            return self._cancel(character_results, advances_completed)
                        next_requested = None
                        if flow_position == 0:
                            # Reuse the first precondition's observation. Identity
                            # adds no capture/navigation and never authorizes input.
                            context = self._character_context(index)
                        if not ensured.succeeded:
                            character_results.append(
                                SessionCharacterResult(index, context, tuple(flow_results))
                            )
                            return self._fail(
                                character_results,
                                advances_completed,
                                index=index,
                                flow=flow.name,
                                flow_position=flow_position,
                                failure=ensured.failure,
                                cause=(
                                    "flow_precondition_failed: "
                                    f"{ensured.error or 'unknown'}"
                                ),
                            )

                        early_result = None
                        pending_precheck = None
                        stopped_at_entry = False
                        if at_zone_entry and flow.entry_readiness is not None:
                            if self.plan.eligibility[flow_position] is not None:
                                early_result = FlowResult(FlowStatus.FAILED, error="entry_readiness_conflicts_with_eligibility")
                            else:
                                early_result = self._observe_precheck(replace(flow, precheck=flow.entry_readiness))
                            stopped_at_entry = early_result is not None
                        if at_zone_entry and early_result is None:
                            pending_precheck = self._observe_precheck(flow)
                            if pending_precheck is not None and self.plan.eligibility[flow_position] is None:
                                # Without Eligibility, its terminal owner result is
                                # already useful at the verified entry: no zone input.
                                early_result = pending_precheck
                                stopped_at_entry = True
                            else:
                                early_result = (pending_precheck if pending_precheck is not None
                                                and pending_precheck.status is FlowStatus.CANCELLED
                                                else self._enter_zone(zone))
                            if early_result is None:
                                if not self._current_satisfies_any((flow.contract.precondition,)):
                                    early_result = FlowResult(FlowStatus.FAILED,
                                                              error="prepared_hub_entry_unconfirmed")
                        if zone is not None and not at_zone_entry and early_result is None:
                            # This is the selected step's fresh entry, not lookahead.
                            # Resource probes retain pending Eligibility precedence.
                            pending_precheck = self._observe_precheck(flow)
                            if pending_precheck is not None and pending_precheck.status is FlowStatus.CANCELLED:
                                early_result = pending_precheck
                        if self._cancelled():
                            early_result = FlowResult(FlowStatus.CANCELLED)
                        check = self.plan.eligibility[flow_position]
                        if check is not None and early_result is None:
                            decision = self._evaluate_eligibility(check)
                            if self._cancelled() or decision.status is EligibilityStatus.CANCELLED:
                                character_results.append(
                                    SessionCharacterResult(index, context, tuple(flow_results))
                                )
                                return self._cancel(character_results, advances_completed)
                            if decision.status in {EligibilityStatus.UNKNOWN, EligibilityStatus.FAILED}:
                                character_results.append(
                                    SessionCharacterResult(index, context, tuple(flow_results))
                                )
                                return self._fail(
                                    character_results, advances_completed, index=index,
                                    flow=flow.name, flow_position=flow_position,
                                    cause=decision.reason, failure=decision.failure,
                                )
                            # A definitive decision must leave the entry contract
                            # verified. Do not normalize or retry on a bad return.
                            entry_restored = self._current_satisfies_any((flow.contract.precondition,))
                            if self._cancelled():
                                character_results.append(
                                    SessionCharacterResult(index, context, tuple(flow_results))
                                )
                                return self._cancel(character_results, advances_completed)
                            if not entry_restored:
                                character_results.append(
                                    SessionCharacterResult(index, context, tuple(flow_results))
                                )
                                return self._fail(
                                    character_results, advances_completed, index=index,
                                    flow=flow.name, flow_position=flow_position,
                                    cause="eligibility_return_postcondition_failed",
                                )
                            if decision.status is EligibilityStatus.NOT_ELIGIBLE:
                                early_result = FlowResult(
                                    FlowStatus.SKIPPED_NOT_ELIGIBLE, skip_reason=decision.reason)

                        # Eligibility owns whether this position is due. Resource
                        # evidence cannot shortcut that decision or gate the hub.
                        if early_result is None:
                            early_result = pending_precheck
                        if early_result is None or early_result.status is FlowStatus.COMPLETED:
                            self._record(
                                "flow.started", component=flow.name, flow=flow.name,
                                character_index=index, character_name=context.name,
                            )
                        # A verified precondition snapshot may seed the flow's
                        # initial observation only while this runner sent no
                        # input since its capture: no eligibility decision and
                        # no zone entry on this position. The probes in between
                        # (eligibility return check, entry restore) observe but
                        # never act, so they cannot stale the evidence.
                        # Ensurers without snapshot evidence behave as before.
                        seed = (
                            getattr(ensured, "snapshot", None)
                            if check is None and zone is None
                            else None
                        )
                        result = early_result if early_result is not None else self._run_flow(flow, seed)
                        controlled = controlled_unavailable(result, self.plan.controlled_unavailable[flow_position])
                        postconditions = ((zone.entry_requirement,) if stopped_at_entry
                                          else flow.contract.successful_postconditions)
                        if controlled or result.status in {FlowStatus.COMPLETED, FlowStatus.SKIPPED_NOT_ELIGIBLE}:
                            confirmed = self._current_satisfies_any(postconditions)
                            if self._cancelled():
                                result = replace(result, status=FlowStatus.CANCELLED, skip_reason=None)
                            elif not confirmed:
                                result = replace(
                                    result, status=FlowStatus.FAILED, skip_reason=None,
                                    error="flow_completed_outside_successful_postconditions",
                                    failure=FailureCause.from_error(
                                        "flow_completed_outside_successful_postconditions",
                                        kind="postcondition_rejected",
                                    ),
                                )
                        self._record("routine.step.result", result=result.status.value,
                                     decision="continue" if controlled and result.status is FlowStatus.MANUAL_RESOLUTION
                                     or result.status in {FlowStatus.COMPLETED, FlowStatus.SKIPPED_NOT_ELIGIBLE} else "stop")
                        if result.status is FlowStatus.SKIPPED_NOT_ELIGIBLE:
                            flow_results.append(result)
                            self._record(
                                "flow.skipped_not_eligible", component=flow.name,
                                flow=flow.name, flow_position=flow_position,
                                character_index=index, character_name=context.name,
                                reason=result.skip_reason,
                            )
                            continue
                        flow_results.append(result)
                        self._record_flow_events(flow.name, result.events, index, context)
                        if result.status is FlowStatus.RESOURCE_BOARD_PENDING:
                            self._record('flow.resource_board_pending', component=flow.name,
                                         flow=flow.name, character_index=index,
                                         board_sequence=getattr(result, 'board_sequence', None))
                            character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                            return self._fail(
                                character_results, advances_completed,
                                index=index, flow=flow.name, flow_position=flow_position,
                                cause='resource_board_pending',
                            )
                        if result.status is FlowStatus.MANUAL_RESOLUTION and controlled:
                            self._record("flow.controlled_unavailable", component=flow.name,
                                         flow=flow.name, flow_position=flow_position,
                                         character_index=index, continued=True)
                            if self._cancelled():
                                character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                                return self._cancel(character_results, advances_completed)
                            continue
                        if result.status is FlowStatus.MANUAL_RESOLUTION:
                            self._record('flow.manual_resolution', component=flow.name,
                                         flow=flow.name, character_index=index)
                            character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                            self._record('session.manual_resolution', flow=flow.name, character_index=index)
                            return SessionResult(
                                SessionStatus.MANUAL_RESOLUTION,
                                characters_processed=sum(item.completed for item in character_results),
                                advances_completed=advances_completed,
                                character_results=tuple(character_results),
                            )
                        if result.status is FlowStatus.CANCELLED:
                            self._record(
                                "flow.cancelled",
                                component=flow.name,
                                flow=flow.name,
                                character_index=index,
                            )
                            character_results.append(
                                SessionCharacterResult(index, context, tuple(flow_results))
                            )
                            return self._cancel(character_results, advances_completed)
                        if result.status is FlowStatus.FAILED:
                            failure = publish_failure(
                                self.events,
                                "flow.failed",
                                result.failure,
                                component=flow.name,
                                flow=flow.name,
                                character_index=index,
                                error=result.error,
                            )
                            result = replace(result, failure=failure)
                            flow_results[-1] = result
                            character_results.append(
                                SessionCharacterResult(index, context, tuple(flow_results))
                            )
                            return self._fail(
                                character_results,
                                advances_completed,
                                index=index,
                                flow=flow.name,
                                flow_position=flow_position,
                                cause=result.error or "flow_failed",
                                failure=result.failure,
                            )
                        self._record(
                            "flow.completed",
                            component=flow.name,
                            flow=flow.name,
                            character_index=index,
                            business_event_count=len(result.events),
                            current_surface=getattr(self.preconditions, 'last_context', None),
                        )
                        if self._cancelled():
                            character_results.append(
                                SessionCharacterResult(index, context, tuple(flow_results))
                            )
                            return self._cancel(character_results, advances_completed)

                if not self.plan.rotate:
                    character_results.append(SessionCharacterResult(index, context, tuple(flow_results), completed=True))
                    continue
                with event_scope(flow=None), operation_scope("rotation"):
                    rotation_contract = self.plan.rotation_strategy.contract
                    requirement = getattr(self.plan.rotation_strategy, 'preferred_entry', rotation_contract.precondition)
                    ensured = self._ensure(requirement, requested_flow=next_requested or 'rotation', useful_flow='rotation')
                    if self._cancelled():
                        character_results.append(SessionCharacterResult(index, context, tuple(flow_results)))
                        return self._cancel(character_results, advances_completed)
                    if not ensured.succeeded:
                        character_results.append(
                            SessionCharacterResult(index, context, tuple(flow_results))
                        )
                        return self._fail(
                            character_results,
                            advances_completed,
                            index=index,
                            failure=ensured.failure,
                            cause=(
                                "rotation_precondition_failed: "
                                f"{ensured.error or 'unknown'}"
                            ),
                        )

                    self._record(
                        "rotation.started",
                        component="rotation",
                        character_index=index,
                    )
                    rotation_result = self._advance()
                    if not rotation_result.succeeded:
                        failure = publish_failure(
                            self.events,
                            "rotation.failed",
                            rotation_result.failure,
                            component="rotation",
                            character_index=index,
                            error=rotation_result.error,
                        )
                        rotation_result = replace(rotation_result, failure=failure)
                        character_results.append(
                            SessionCharacterResult(
                                index,
                                context,
                                tuple(flow_results),
                                advance_result=rotation_result,
                            )
                        )
                        return self._fail(
                            character_results,
                            advances_completed,
                            index=index,
                            cause=rotation_result.error or "rotation_failed",
                            failure=rotation_result.failure,
                        )
                    if not self._current_satisfies_any(
                        rotation_contract.successful_postconditions
                    ):
                        character_results.append(
                            SessionCharacterResult(
                                index,
                                context,
                                tuple(flow_results),
                                advance_result=rotation_result,
                            )
                        )
                        return self._fail(
                            character_results,
                            advances_completed,
                            index=index,
                            cause="rotation_completed_outside_successful_postconditions",
                        )

                    advances_completed += 1
                    self._record(
                        "rotation.completed",
                        component="rotation",
                        character_index=index,
                        advances_completed=advances_completed,
                    )
                    character_results.append(
                        SessionCharacterResult(
                            index,
                            context,
                            tuple(flow_results),
                            advance_result=rotation_result,
                            completed=True,
                        )
                    )
                self._record(
                    "session.character.completed",
                    character_index=index,
                    character_name=context.name,
                )

        result = SessionResult(
            SessionStatus.COMPLETED,
            characters_processed=len(character_results),
            advances_completed=advances_completed,
            character_results=tuple(character_results),
        )
        self._record(
            "session.completed",
            characters_processed=result.characters_processed,
            advances_completed=result.advances_completed,
        )
        return result

    @staticmethod
    def _observe_precheck(flow: PreparedActivity) -> FlowResult | None:
        try:
            if flow.precheck is not None:
                result = flow.precheck()
                if result is not None:
                    if not isinstance(result, FlowResult) or result.status is FlowStatus.SKIPPED_NOT_ELIGIBLE:
                        raise TypeError("invalid prepared activity precheck result")
                    return result
            return None
        except RuntimeWaitCancelled:
            return FlowResult(FlowStatus.CANCELLED)
        except Exception as error:
            return FlowResult(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                              failure=FailureCause.from_error(error, kind="exception"))

    def _enter_zone(self, zone) -> FlowResult | None:
        try:
            entered = zone.enter()
            if not isinstance(entered, FlowResult) or entered.status is FlowStatus.SKIPPED_NOT_ELIGIBLE:
                raise TypeError("invalid zone entry result")
            self._record('navigation.handoff', current_surface=zone.entry_requirement.name,
                         destination=zone.hub_requirement.name if entered.succeeded else None,
                         required_entry=zone.hub_requirement.name, route='enter_zone',
                         next_requested_flow=event_context()['flow'], next_useful_flow=event_context()['flow'],
                         reason='entry_requirement')
            return None if entered.succeeded else entered
        except RuntimeWaitCancelled:
            return FlowResult(FlowStatus.CANCELLED)
        except Exception as error:
            return FlowResult(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                              failure=FailureCause.from_error(error, kind="exception"))

    def _character_context(self, index: int) -> CharacterContext:
        if self.character_context_factory is None:
            return CharacterContext()
        try:
            context = self.character_context_factory(index)
            if isinstance(context, CharacterContext):
                return context
        except Exception:
            pass
        # Optional identity used for observability must never make gameplay fatal.
        return CharacterContext()

    def _run_flow(self, flow: PerCharacterFlow, initial_snapshot: object | None = None) -> FlowResult:
        try:
            result = run_flow_with_optional_seed(flow, initial_snapshot)
            if not isinstance(result, FlowResult):
                return FlowResult(
                    FlowStatus.FAILED,
                    error="flow returned an invalid result",
                )
            if result.status is FlowStatus.SKIPPED_NOT_ELIGIBLE:
                return FlowResult(
                    FlowStatus.FAILED,
                    error="eligibility skips must originate before flow execution",
                )
            return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return FlowResult(
                FlowStatus.FAILED,
                error=f"{type(error).__name__}: {error}",
                failure=FailureCause.from_error(error, kind="exception"),
            )

    def _advance(self) -> RotationResult:
        try:
            return self.plan.rotation_strategy.advance()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            from bot.rotation import RotationOutcome

            return RotationResult(
                RotationOutcome.ABORTED,
                error=f"{type(error).__name__}: {error}",
                failure=FailureCause.from_error(error, kind="exception"),
            )

    @staticmethod
    def _evaluate_eligibility(check: EligibilityCheck) -> EligibilityResult:
        try:
            result = check.evaluate()
            if not isinstance(result, EligibilityResult):
                raise TypeError("invalid eligibility result")
            return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return EligibilityResult(
                EligibilityStatus.FAILED,
                f"eligibility_failed: {type(error).__name__}: {error}",
                FailureCause.from_error(error, kind="exception"),
            )

    def _ensure(self, requirement: ComponentRequirement, *, requested_flow=None, useful_flow=None) -> EnsureResult:
        try:
            result = self.preconditions.ensure(requirement)
            if isinstance(result, EnsureResult):
                self._record('navigation.handoff', current_surface=result.context_before,
                             destination=result.context_after, required_entry=requirement.name,
                             next_requested_flow=requested_flow, next_useful_flow=useful_flow,
                             route=result.route or result.outcome.value, reason='entry_requirement')
                return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except RuntimeWaitCancelled:
            self._observation_cancelled = True
        except Exception:
            pass
        from bot.preconditions import EnsureOutcome

        return EnsureResult(
            EnsureOutcome.FAILED,
            requirement,
            None,
            None,
            "invalid_precondition_result",
        )

    def _current_satisfies_any(
        self,
        requirements: tuple[ComponentRequirement, ...],
    ) -> bool:
        try:
            return self.preconditions.current_satisfies_any(requirements) is True
        except (KeyboardInterrupt, SystemExit):
            raise
        except RuntimeWaitCancelled:
            self._observation_cancelled = True
        except Exception:
            return False

    def _cancelled(self) -> bool:
        if self._observation_cancelled:
            return True
        try:
            return self.cancel_requested() is True
        except Exception:
            return False

    def _record_flow_events(
        self,
        flow_name: str,
        flow_events: tuple[FlowEvent, ...],
        index: int,
        context: CharacterContext,
    ) -> None:
        publish_flow_events(
            self.events, flow_name, flow_events,
            character_index=index, character_name=context.name,
        )

    def _cancel(
        self,
        character_results: list[SessionCharacterResult],
        advances_completed: int,
    ) -> SessionResult:
        result = SessionResult(
            SessionStatus.CANCELLED,
            characters_processed=sum(item.completed for item in character_results),
            advances_completed=advances_completed,
            character_results=tuple(character_results),
        )
        self._record(
            "session.cancelled",
            characters_processed=result.characters_processed,
            advances_completed=result.advances_completed,
        )
        return result

    def _fail(
        self,
        character_results: list[SessionCharacterResult],
        advances_completed: int,
        *,
        index: int,
        cause: str,
        flow: str | None = None,
        flow_position: int | None = None,
        failure: FailureCause | None = None,
    ) -> SessionResult:
        result = SessionResult(
            SessionStatus.FAILED,
            characters_processed=sum(item.completed for item in character_results),
            advances_completed=advances_completed,
            character_results=tuple(character_results),
            failure_character_index=index,
            failure_flow=flow,
            failure_flow_position=flow_position,
            failure_cause=cause,
            failure=failure,
        )
        enriched_failure = publish_failure(
            self.events,
            "session.failed",
            result.failure,
            character_index=index,
            flow=flow,
            cause=cause,
            advances_completed=advances_completed,
        )
        return replace(result, failure=enriched_failure)

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


__all__ = (
    "CharacterContext",
    "SessionCharacterResult",
    "SessionPlan",
    "SessionResult",
    "SessionRunner",
    "SessionStatus",
)
