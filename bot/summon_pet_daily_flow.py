"""Productive Lobby-to-Lobby Pet Summon Daily flow."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
import math
from typing import Callable, Protocol

from bot.catalog import (
    OVERLAY_PET_EPIC_SELECTOR,
    OVERLAY_PET_PREMIUM_GOLD_SELECTOR,
    OVERLAY_PET_PREMIUM_TICKET_SELECTOR,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_PET_INVENTORY_FULL,
    SCREEN_LOBBY,
    SCREEN_PET_COMBINE,
    SCREEN_PET_SUMMON,
    SCREEN_PET_SUMMON_RESULT,
    SCREEN_PETS_MANAGE,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_PREMIUM_TICKET_AVAILABLE,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
)
from bot.component_contracts import ComponentRequirement
from bot.event_log import EventSink
from bot.flow_contracts import FlowContract, FlowEvent, FlowResult, FlowScope, FlowStatus
from bot.pet_summon_space_relief import (
    PetSummonSpaceReliefOutcome,
    PetSummonSpaceReliefResult,
)
from bot.runtime_observer import (
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    AcceptPetInventoryFull,
    ClosePetSummonResult,
    ClosePets,
    OpenEpicPetSummon,
    OpenPets,
    OpenPremiumPetSummon,
    OpenSingleEpicPet,
    OpenSinglePremiumPet,
    RejectInsufficientGold,
    RejectPetInventoryFull,
    SelectPetSummon,
)
from bot.state import ResolutionStatus


SUMMON_PET_DAILY_NOOP = "summon_pet_daily.noop"
SUMMON_PET_DAILY_COMPLETED = "summon_pet_daily.completed"
SUMMON_PET_DAILY_INSUFFICIENT_GOLD = "summon_pet_daily.insufficient_gold"
SUMMON_PET_DAILY_SPACE_RELIEF_UNAVAILABLE = (
    "summon_pet_daily.space_relief_unavailable"
)
SUMMON_PET_DAILY_MANUAL_RESOLUTION = "summon_pet_daily.manual_resolution"

_SUMMON_STATUSES = frozenset(
    {
        STATUS_PET_EPIC_AVAILABLE,
        STATUS_PET_EPIC_UNAVAILABLE,
        STATUS_PET_PREMIUM_GOLD,
        STATUS_PET_PREMIUM_TICKET_AVAILABLE,
        STATUS_PET_SUMMON_DAILY_ACTIVE,
    }
)


@dataclass(frozen=True)
class SummonPetDailyFlowResult(FlowResult):
    no_op: bool = False
    daily_completed: bool = False
    daily_pending: bool = False
    relief_attempted: bool = False
    retry_attempted: bool = False
    summons_completed: int = 0


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition,
        *,
        after_sequence: int,
        timeout: float,
        abort_if=None,
        cancel_requested=None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class _Relief(Protocol):
    def run(
        self, cancel_requested: Callable[[], bool]
    ) -> PetSummonSpaceReliefResult: ...


class SummonPetDailyFlow:
    """Perform at most one Daily summon and one relief-backed retry."""

    name = "summon_pet_daily"
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(
        precondition=ComponentRequirement.exact_state(SCREEN_LOBBY),
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
        ),
    )

    def __init__(
        self,
        observer,
        actions,
        events: EventSink,
        pet_summon_space_relief: _Relief,
        *,
        navigation_timeout: float = 6.0,
        outcome_timeout: float = 12.0,
        navigation_stable_for: float = 0.25,
        outcome_stable_for: float = 0.5,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if not callable(getattr(pet_summon_space_relief, "run", None)):
            raise ValueError("pet_summon_space_relief must provide run()")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.pet_summon_space_relief = pet_summon_space_relief
        self.cancel_requested = cancel_requested
        self.navigation_timeout = _positive_duration(
            navigation_timeout, "navigation_timeout"
        )
        self.outcome_timeout = _positive_duration(outcome_timeout, "outcome_timeout")
        self.navigation_stable_for = _non_negative_duration(
            navigation_stable_for, "navigation_stable_for"
        )
        self.outcome_stable_for = _non_negative_duration(
            outcome_stable_for, "outcome_stable_for"
        )

    def run(self) -> SummonPetDailyFlowResult:
        events: list[FlowEvent] = []
        relief_attempted = False
        retry_attempted = False
        summons_completed = 0
        try:
            if self._cancelled():
                raise RuntimeWaitCancelled("summon pet daily flow cancelled")
            lobby = self._initial_lobby()
            pets = self._act_and_wait(
                OpenPets(),
                lobby,
                expected=_is_clean_pets_surface,
                retryable_from=_is_clean_lobby,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )
            if STATUS_PET_SUMMON_DAILY_ACTIVE not in pets.state.overlays:
                self._append_event(events, SUMMON_PET_DAILY_NOOP)
                self._close_to_lobby(pets)
                return SummonPetDailyFlowResult(
                    FlowStatus.COMPLETED,
                    tuple(events),
                    no_op=True,
                    daily_completed=True,
                )

            summon = pets
            if not _is_summon_ready(summon):
                summon = self._act_and_wait(
                    SelectPetSummon(),
                    pets,
                    expected=_is_summon_daily_active,
                    retryable_from=_is_clean_pets_surface,
                    timeout=self.navigation_timeout,
                    stable_for=self.navigation_stable_for,
                )

            while True:
                outcome = self._summon_once(summon)
                if _is_summon_result(outcome):
                    summons_completed += 1
                    summon = self._act_and_wait(
                        ClosePetSummonResult(),
                        outcome,
                        expected=_is_summon_daily_completed,
                        retryable_from=_is_summon_result,
                        timeout=self.navigation_timeout,
                        stable_for=self.outcome_stable_for,
                    )
                    self._append_event(events, SUMMON_PET_DAILY_COMPLETED)
                    self._close_to_lobby(summon)
                    return SummonPetDailyFlowResult(
                        FlowStatus.COMPLETED,
                        tuple(events),
                        daily_completed=True,
                        relief_attempted=relief_attempted,
                        retry_attempted=retry_attempted,
                        summons_completed=summons_completed,
                    )

                if _is_insufficient_gold(outcome):
                    summon = self._act_and_wait(
                        RejectInsufficientGold(),
                        outcome,
                        expected=_is_summon_daily_active,
                        retryable_from=_is_insufficient_gold,
                        timeout=self.navigation_timeout,
                        stable_for=self.navigation_stable_for,
                    )
                    self._append_event(
                        events, SUMMON_PET_DAILY_INSUFFICIENT_GOLD
                    )
                    self._close_to_lobby(summon)
                    return SummonPetDailyFlowResult(
                        FlowStatus.COMPLETED,
                        tuple(events),
                        daily_pending=True,
                        relief_attempted=relief_attempted,
                        retry_attempted=retry_attempted,
                        summons_completed=summons_completed,
                    )

                assert _is_pet_full(outcome)
                if relief_attempted:
                    summon = self._act_and_wait(
                        RejectPetInventoryFull(),
                        outcome,
                        expected=_is_summon_daily_active,
                        retryable_from=_is_pet_full,
                        timeout=self.navigation_timeout,
                        stable_for=self.navigation_stable_for,
                    )
                    self._append_event(
                        events, SUMMON_PET_DAILY_MANUAL_RESOLUTION
                    )
                    self._close_to_lobby(summon)
                    return SummonPetDailyFlowResult(
                        FlowStatus.COMPLETED,
                        tuple(events),
                        daily_pending=True,
                        relief_attempted=True,
                        retry_attempted=True,
                        summons_completed=summons_completed,
                    )

                combine = self._act_and_wait(
                    AcceptPetInventoryFull(),
                    outcome,
                    expected=_is_clean_combine,
                    retryable_from=_is_pet_full,
                    timeout=self.navigation_timeout,
                    stable_for=self.navigation_stable_for,
                )
                relief_attempted = True
                relief = self.pet_summon_space_relief.run(self.cancel_requested)
                if relief.outcome is PetSummonSpaceReliefOutcome.CANCELLED:
                    raise RuntimeWaitCancelled("pet summon space relief cancelled")
                if relief.outcome is PetSummonSpaceReliefOutcome.FAILED:
                    return self._failed(
                        events,
                        relief.error or "pet_summon_space_relief_failed",
                        relief_attempted=True,
                        retry_attempted=False,
                        summons_completed=summons_completed,
                    )
                if relief.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE:
                    self._append_event(
                        events, SUMMON_PET_DAILY_SPACE_RELIEF_UNAVAILABLE
                    )
                    self._append_event(
                        events, SUMMON_PET_DAILY_MANUAL_RESOLUTION
                    )
                    self._close_to_lobby(relief.final_snapshot)
                    return SummonPetDailyFlowResult(
                        FlowStatus.COMPLETED,
                        tuple(events),
                        daily_pending=True,
                        relief_attempted=True,
                        summons_completed=summons_completed,
                    )

                if not _is_clean_combine(relief.final_snapshot):
                    return self._failed(
                        events,
                        "pet_summon_space_relief_returned_incompatible_state",
                        relief_attempted=True,
                        retry_attempted=False,
                        summons_completed=summons_completed,
                    )
                summon = self._act_and_wait(
                    SelectPetSummon(),
                    relief.final_snapshot,
                    expected=_is_summon_daily_active,
                    retryable_from=_is_clean_combine,
                    timeout=self.navigation_timeout,
                    stable_for=self.navigation_stable_for,
                )
                retry_attempted = True
        except RuntimeWaitCancelled:
            return self._cancel(
                events,
                relief_attempted=relief_attempted,
                retry_attempted=retry_attempted,
                summons_completed=summons_completed,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._failed(
                events,
                f"state_wait_failed: {error}",
                relief_attempted=relief_attempted,
                retry_attempted=retry_attempted,
                summons_completed=summons_completed,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(
                events,
                f"{type(error).__name__}: {error}",
                relief_attempted=relief_attempted,
                retry_attempted=retry_attempted,
                summons_completed=summons_completed,
            )

    def _summon_once(self, summon: RuntimeSnapshot) -> RuntimeSnapshot:
        if not _is_summon_daily_active(summon):
            raise RuntimeError("summon_pet_daily_guard_missing")
        epic_available = STATUS_PET_EPIC_AVAILABLE in summon.state.overlays
        action = OpenEpicPetSummon() if epic_available else OpenPremiumPetSummon()
        selector_predicate = _is_epic_selector if epic_available else _is_premium_selector
        selector = self._act_and_wait(
            action,
            summon,
            expected=selector_predicate,
            retryable_from=_is_summon_daily_active,
            timeout=self.navigation_timeout,
            stable_for=self.navigation_stable_for,
        )
        open_one = OpenSingleEpicPet() if epic_available else OpenSinglePremiumPet()
        return self._act_and_wait(
            open_one,
            selector,
            expected=lambda snapshot: (
                _is_summon_result(snapshot)
                or _is_insufficient_gold(snapshot)
                or _is_pet_full(snapshot)
            ),
            retryable_from=selector_predicate,
            timeout=self.outcome_timeout,
            stable_for=self.outcome_stable_for,
        )

    def _initial_lobby(self) -> RuntimeSnapshot:
        initial = self.observer.observe()
        if _is_clean_lobby(initial):
            return initial
        if not _is_passive_unknown(initial):
            raise RuntimeError("precondition_lobby_failed")
        return self.observer.wait_until(
            _is_clean_lobby,
            after_sequence=initial.sequence,
            timeout=self.navigation_timeout,
            abort_if=lambda snapshot: _known_incompatible(
                snapshot, _is_clean_lobby, _is_passive_unknown
            ),
            cancel_requested=self.cancel_requested,
            stable_for=self.navigation_stable_for,
        )

    def _close_to_lobby(self, current: RuntimeSnapshot) -> RuntimeSnapshot:
        return self._act_and_wait(
            ClosePets(),
            current,
            expected=_is_clean_lobby,
            retryable_from=lambda snapshot: (
                _is_clean_pets_surface(snapshot)
                or _is_summon_daily_active(snapshot)
                or _is_summon_daily_completed(snapshot)
                or _is_clean_combine(snapshot)
            ),
            timeout=self.navigation_timeout,
            stable_for=self.navigation_stable_for,
        )

    def _act_and_wait(
        self,
        action,
        before,
        *,
        expected,
        retryable_from,
        timeout,
        stable_for,
    ):
        if self._cancelled():
            raise RuntimeWaitCancelled("summon pet daily flow cancelled")
        self.actions.execute(action, before.geometry)
        return self.observer.wait_until(
            expected,
            after_sequence=before.sequence,
            timeout=timeout,
            abort_if=lambda snapshot: _known_incompatible(
                snapshot, expected, retryable_from
            ),
            cancel_requested=self.cancel_requested,
            stable_for=stable_for,
        )

    def _append_event(self, events: list[FlowEvent], kind: str) -> None:
        events.append(FlowEvent(kind))
        self._record(kind)

    def _cancel(self, events, **kwargs):
        self._record("summon_pet_daily.cancelled")
        return SummonPetDailyFlowResult(
            FlowStatus.CANCELLED, tuple(events), **kwargs
        )

    def _failed(self, events, error: str, **kwargs):
        self._record("summon_pet_daily.failed", error=error)
        return SummonPetDailyFlowResult(
            FlowStatus.FAILED, tuple(events), error, **kwargs
        )

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass

    def _cancelled(self) -> bool:
        try:
            return self.cancel_requested() is True
        except Exception:
            return False


def _is_clean_lobby(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_LOBBY
        and not snapshot.state.overlays
    )


def _is_passive_unknown(snapshot: RuntimeSnapshot) -> bool:
    return snapshot.state.status is ResolutionStatus.UNKNOWN and not snapshot.state.overlays


def _is_clean_pets_surface(snapshot: RuntimeSnapshot) -> bool:
    if snapshot.state.status is not ResolutionStatus.RESOLVED:
        return False
    overlays = set(snapshot.state.overlays)
    if snapshot.state.base_context in {SCREEN_PETS_MANAGE, SCREEN_PET_COMBINE}:
        return overlays <= {STATUS_PET_SUMMON_DAILY_ACTIVE}
    return _is_summon_ready(snapshot)


def _is_clean_combine(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_COMBINE
        and not snapshot.state.overlays
    )


def _is_summon_ready(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    epic = overlays & {STATUS_PET_EPIC_AVAILABLE, STATUS_PET_EPIC_UNAVAILABLE}
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and len(epic) == 1
        and overlays <= _SUMMON_STATUSES
    )


def _is_summon_daily_active(snapshot: RuntimeSnapshot) -> bool:
    return _is_summon_ready(snapshot) and STATUS_PET_SUMMON_DAILY_ACTIVE in snapshot.state.overlays


def _is_summon_daily_completed(snapshot: RuntimeSnapshot) -> bool:
    return _is_summon_ready(snapshot) and STATUS_PET_SUMMON_DAILY_ACTIVE not in snapshot.state.overlays


def _is_epic_selector(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and OVERLAY_PET_EPIC_SELECTOR in overlays
        and overlays <= (_SUMMON_STATUSES | {OVERLAY_PET_EPIC_SELECTOR})
    )


def _is_premium_selector(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    selectors = overlays & {
        OVERLAY_PET_PREMIUM_TICKET_SELECTOR,
        OVERLAY_PET_PREMIUM_GOLD_SELECTOR,
    }
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and len(selectors) == 1
        and overlays
        <= (
            _SUMMON_STATUSES
            | {
                OVERLAY_PET_PREMIUM_TICKET_SELECTOR,
                OVERLAY_PET_PREMIUM_GOLD_SELECTOR,
            }
        )
    )


def _is_summon_result(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON_RESULT
        and not snapshot.state.overlays
    )


def _is_insufficient_gold(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and POPUP_INSUFFICIENT_GOLD in overlays
        and overlays <= (_SUMMON_STATUSES | {POPUP_INSUFFICIENT_GOLD})
    )


def _is_pet_full(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and POPUP_PET_INVENTORY_FULL in overlays
        and overlays <= (_SUMMON_STATUSES | {POPUP_PET_INVENTORY_FULL})
    )


def _known_incompatible(snapshot, expected, retryable_from) -> bool:
    if expected(snapshot) or retryable_from(snapshot):
        return False
    return snapshot.state.status in {
        ResolutionStatus.RESOLVED,
        ResolutionStatus.AMBIGUOUS,
    }


def _positive_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _non_negative_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


__all__ = (
    "SUMMON_PET_DAILY_COMPLETED",
    "SUMMON_PET_DAILY_INSUFFICIENT_GOLD",
    "SUMMON_PET_DAILY_MANUAL_RESOLUTION",
    "SUMMON_PET_DAILY_NOOP",
    "SUMMON_PET_DAILY_SPACE_RELIEF_UNAVAILABLE",
    "SummonPetDailyFlow",
    "SummonPetDailyFlowResult",
)
