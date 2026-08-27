"""Minimal sequential composition of PER_CHARACTER flows and rotation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable

from bot.component_contracts import ComponentContract, ComponentRequirement
from bot.config import DEFAULT_CHARACTER_COUNT
from bot.event_log import EventSink
from bot.flow_contracts import (
    FlowEvent,
    FlowContract,
    FlowResult,
    FlowScope,
    FlowStatus,
    PerCharacterFlow,
)
from bot.preconditions import EnsureResult, PreconditionEnsurer
from bot.rotation import RotationResult, RotationStrategy


class SessionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CharacterContext:
    """Stable character metadata; identity remains optional until OCR exists."""

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
        object.__setattr__(self, "character_count", count)
        object.__setattr__(self, "flows", flows)

    @classmethod
    def standard(
        cls,
        *,
        flows: tuple[PerCharacterFlow, ...],
        rotation_strategy: RotationStrategy,
        character_count: int = DEFAULT_CHARACTER_COUNT,
    ) -> "SessionPlan":
        return cls(character_count, flows, rotation_strategy)


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

    def run(self) -> SessionResult:
        character_results: list[SessionCharacterResult] = []
        advances_completed = 0
        self._record("session.started", character_count=self.plan.character_count)

        for index in range(1, self.plan.character_count + 1):
            if self._cancelled():
                return self._cancel(character_results, advances_completed)

            context = self._character_context(index)
            self._record(
                "session.character.started",
                character_index=index,
                character_name=context.name,
            )
            flow_results: list[FlowResult] = []
            for flow in self.plan.flows:
                if self._cancelled():
                    character_results.append(
                        SessionCharacterResult(index, context, tuple(flow_results))
                    )
                    return self._cancel(character_results, advances_completed)

                ensured = self._ensure(flow.contract.precondition)
                if not ensured.succeeded:
                    character_results.append(
                        SessionCharacterResult(index, context, tuple(flow_results))
                    )
                    return self._fail(
                        character_results,
                        advances_completed,
                        index=index,
                        flow=flow.name,
                        cause=(
                            "flow_precondition_failed: "
                            f"{ensured.error or 'unknown'}"
                        ),
                    )

                result = self._run_flow(flow)
                flow_results.append(result)
                self._record_flow_events(flow.name, result.events, index, context)
                if result.status is FlowStatus.FAILED:
                    character_results.append(
                        SessionCharacterResult(index, context, tuple(flow_results))
                    )
                    return self._fail(
                        character_results,
                        advances_completed,
                        index=index,
                        flow=flow.name,
                        cause=result.error or "flow_failed",
                    )
                if not self._current_satisfies_any(
                    flow.contract.successful_postconditions
                ):
                    character_results.append(
                        SessionCharacterResult(index, context, tuple(flow_results))
                    )
                    return self._fail(
                        character_results,
                        advances_completed,
                        index=index,
                        flow=flow.name,
                        cause="flow_completed_outside_successful_postconditions",
                    )
                if self._cancelled():
                    character_results.append(
                        SessionCharacterResult(index, context, tuple(flow_results))
                    )
                    return self._cancel(character_results, advances_completed)

            rotation_contract = self.plan.rotation_strategy.contract
            ensured = self._ensure(rotation_contract.precondition)
            if not ensured.succeeded:
                character_results.append(
                    SessionCharacterResult(index, context, tuple(flow_results))
                )
                return self._fail(
                    character_results,
                    advances_completed,
                    index=index,
                    cause=(
                        "rotation_precondition_failed: "
                        f"{ensured.error or 'unknown'}"
                    ),
                )

            rotation_result = self._advance()
            if not rotation_result.succeeded:
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

    def _run_flow(self, flow: PerCharacterFlow) -> FlowResult:
        try:
            result = flow.run()
            if not isinstance(result, FlowResult):
                return FlowResult(
                    FlowStatus.FAILED,
                    error="flow returned an invalid result",
                )
            return result
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return FlowResult(
                FlowStatus.FAILED,
                error=f"{type(error).__name__}: {error}",
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
            )

    def _ensure(self, requirement: ComponentRequirement) -> EnsureResult:
        try:
            result = self.preconditions.ensure(requirement)
            if isinstance(result, EnsureResult):
                return result
        except (KeyboardInterrupt, SystemExit):
            raise
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
        except Exception:
            return False

    def _cancelled(self) -> bool:
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
        for event in flow_events:
            fields: dict[str, object] = {
                "character_index": index,
                "character_name": context.name,
            }
            if event.detail is not None:
                fields["detail"] = event.detail
            self._record(f"{flow_name}.{event.kind}", **fields)

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
    ) -> SessionResult:
        result = SessionResult(
            SessionStatus.FAILED,
            characters_processed=sum(item.completed for item in character_results),
            advances_completed=advances_completed,
            character_results=tuple(character_results),
            failure_character_index=index,
            failure_flow=flow,
            failure_cause=cause,
        )
        self._record(
            "session.failed",
            character_index=index,
            flow=flow,
            cause=cause,
            advances_completed=advances_completed,
        )
        return result

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
