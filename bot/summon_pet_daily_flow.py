"""Productive Manage-to-Summon Pet Summon Daily flow."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
import math
import time
from typing import Callable, Protocol

from bot.catalog import (
    OVERLAY_PET_EPIC_SELECTOR,
    OVERLAY_PET_PREMIUM_GOLD_SELECTOR,
    OVERLAY_PET_PREMIUM_TICKET_SELECTOR,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_PET_INVENTORY_FULL,
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
    OpenEpicPetSummon,
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
        precondition=ComponentRequirement.exact_state(SCREEN_PETS_MANAGE),
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_PETS_MANAGE),
            ComponentRequirement.exact_state(SCREEN_PET_SUMMON),
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

    def run(self) -> "SummonPetDailyFlowResult":
        events: list[FlowEvent] = []
        relief_attempted = False
        retry_attempted = False
        summons_completed = 0
        try:
            if self._cancelled():
                raise RuntimeWaitCancelled("summon pet daily flow cancelled")
            pets = self._initial_manage()
            if STATUS_PET_SUMMON_DAILY_ACTIVE not in pets.state.overlays:
                self._append_event(events, "summon_pet_daily.noop")
                return SummonPetDailyFlowResult(
                    status=FlowStatus.COMPLETED,
                    events=tuple(events),
                    no_op=True,
                    daily_completed=True,
                )

            # Navigate to Summon tab
            summon = self._act_and_wait(
                SelectPetSummon(),
                self._is_summon_ready,
                pets,
                retryable_from=self._is_clean_manage,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )

            while True:
                outcome = self._summon_once(summon)
                if self._is_summon_result(outcome):
                    self._act_and_wait(
                        ClosePetSummonResult(),
                        self._is_summon_ready,
                        outcome,
                        retryable_from=self._is_summon_result,
                        timeout=self.navigation_timeout,
                        stable_for=self.outcome_stable_for,
                    )
                    self._append_event(events, "summon_pet_daily.completed")
                    return SummonPetDailyFlowResult(
                        status=FlowStatus.COMPLETED,
                        events=tuple(events),
                        daily_completed=True,
                        relief_attempted=relief_attempted,
                        retry_attempted=retry_attempted,
                        summons_completed=1,
                    )

                if self._is_insufficient_gold(outcome):
                    self._act_and_wait(
                        RejectInsufficientGold(),
                        self._is_summon_ready,
                        outcome,
                        retryable_from=self._is_insufficient_gold,
                        timeout=self.navigation_timeout,
                        stable_for=self.navigation_stable_for,
                    )
                    self._append_event(events, "summon_pet_daily.insufficient_gold")
                    return SummonPetDailyFlowResult(
                        status=FlowStatus.COMPLETED,
                        events=tuple(events),
                        daily_pending=True,
                        relief_attempted=relief_attempted,
                        retry_attempted=retry_attempted,
                        summons_completed=0,
                    )

                assert self._is_pet_full(outcome)
                if relief_attempted:
                    self._act_and_wait(
                        RejectPetInventoryFull(),
                        self._is_summon_ready,
                        outcome,
                        retryable_from=self._is_pet_full,
                        timeout=self.navigation_timeout,
                        stable_for=self.navigation_stable_for,
                    )
                    self._append_event(
                        events, "summon_pet_daily.manual_resolution"
                    )
                    return SummonPetDailyFlowResult(
                        status=FlowStatus.COMPLETED,
                        events=tuple(events),
                        daily_pending=True,
                        relief_attempted=True,
                        retry_attempted=True,
                        summons_completed=0,
                    )

                # First Pet Full -> relief
                combine = self._act_and_wait(
                    AcceptPetInventoryFull(),
                    self._is_clean_combine,
                    outcome,
                    retryable_from=self._is_pet_full,
                    timeout=self.navigation_timeout,
                    stable_for=self.navigation_stable_for,
                )
                relief_attempted = True
                relief = self.pet_summon_space_relief.run(self.cancel_requested)
                if relief.outcome == PetSummonSpaceReliefOutcome.CANCELLED:
                    raise RuntimeWaitCancelled("pet summon space relief cancelled")
                if relief.outcome == PetSummonSpaceReliefOutcome.FAILED:
                    return self._failed(
                        events,
                        relief.error or "pet_summon_space_relief_failed",
                        relief_attempted=True,
                        retry_attempted=False,
                        summons_completed=0,
                    )
                if relief.outcome == PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE:
                    self._append_event(
                        events, "summon_pet_daily.space_relief_unavailable"
                    )
                    self._append_event(
                        events, "summon_pet_daily.manual_resolution"
                    )
                    summon = self._act_and_wait(
                        SelectPetSummon(),
                        self._is_summon_ready,
                        relief.final_snapshot,
                        retryable_from=self._is_clean_combine,
                        timeout=self.navigation_timeout,
                        stable_for=self.navigation_stable_for,
                    )
                    return SummonPetDailyFlowResult(
                        status=FlowStatus.COMPLETED,
                        events=tuple(events),
                        daily_pending=True,
                        relief_attempted=True,
                        summons_completed=0,
                    )

                if not self._is_clean_combine(relief.final_snapshot):
                    return self._failed(
                        events,
                        "pet_summon_space_relief_returned_incompatible_state",
                        relief_attempted=True,
                        retry_attempted=retry_attempted,
                        summons_completed=0,
                    )

                # Post-relief re-entry: retry once with same logic
                summon = self._act_and_wait(
                    SelectPetSummon(),
                    self._is_summon_ready,
                    relief.final_snapshot,
                    retryable_from=self._is_clean_combine,
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
        """Execute one summon attempt: Epic if available, else Premium. Tap 1(Open) directly."""
        if self._cancelled():
            raise RuntimeWaitCancelled("summon pet daily flow cancelled")
        if not self._is_summon_ready(summon):
            raise RuntimeError("summon_pet_daily_guard_missing")

        epic_available = STATUS_PET_EPIC_AVAILABLE in summon.state.overlays

        # Tap Epic or Premium card, then wait 0.25s, then tap 1(Open) directly - NO selector wait
        if epic_available:
            # Tap Epic card
            self.actions.execute(OpenEpicPetSummon(), summon.geometry)
            # Minimum delay before tapping 1(Open)
            time.sleep(0.25)
            # Tap 1(Open) directly
            self.actions.execute(OpenSingleEpicPet(), summon.geometry)
        else:
            # Premium: could be ticket or gold selector, accept either
            self.actions.execute(OpenPremiumPetSummon(), summon.geometry)
            # Minimum delay before tapping 1(Open)
            time.sleep(0.25)
            # Tap 1(Open) directly
            self.actions.execute(OpenSinglePremiumPet(), summon.geometry)

        # Wait for result (summon result, insufficient gold, or pet full)
        return self.observer.wait_until(
            lambda snapshot: self._is_summon_result(snapshot)
                or self._is_insufficient_gold(snapshot)
                or self._is_pet_full(snapshot),
            after_sequence=summon.sequence,
            timeout=self.outcome_timeout,
            abort_if=lambda snapshot: self._known_incompatible(
                snapshot,
                lambda s: self._is_summon_result(s)
                    or self._is_insufficient_gold(s)
                    or self._is_pet_full(s),
                lambda s: self._is_summon_ready(s) or self._is_selector(s, epic_available),
            ),
            cancel_requested=self.cancel_requested,
            stable_for=self.outcome_stable_for,
        )

    def _initial_manage(self) -> RuntimeSnapshot:
        initial = self.observer.observe()
        if self._is_clean_manage(initial):
            return initial
        if not self._is_passive_unknown(initial):
            raise RuntimeError("precondition_pet_manage_failed")
        return self.observer.wait_until(
            self._is_clean_manage,
            after_sequence=initial.sequence,
            timeout=self.navigation_timeout,
            abort_if=lambda snapshot: self._known_incompatible(
                snapshot, self._is_clean_manage, self._is_passive_unknown
            ),
            cancel_requested=self.cancel_requested,
            stable_for=self.navigation_stable_for,
        )

    def _act_and_wait(
        self,
        action,
        expected: Callable[[RuntimeSnapshot], bool],
        before: RuntimeSnapshot,
        retryable_from: Callable[[RuntimeSnapshot], bool],
        timeout: float,
        stable_for: float,
    ) -> RuntimeSnapshot:
        if self._cancelled():
            raise RuntimeWaitCancelled("summon pet daily flow cancelled")

        if not retryable_from(before):
            raise RuntimeError("summon_pet_navigation_guard_missing")
        self.actions.execute(action, before.geometry)
        return self.observer.wait_until(
            expected,
            after_sequence=before.sequence,
            timeout=timeout,
            abort_if=lambda snapshot: self._known_incompatible(
                snapshot, expected, retryable_from
            ) and not self._is_summon_shell(snapshot),
            cancel_requested=self.cancel_requested,
            stable_for=stable_for,
        )

    def _append_event(self, events: list[FlowEvent], kind: str) -> None:
        events.append(FlowEvent(kind))

    def _cancel(self, events, **kwargs):
        self._record("summon_pet_daily.cancelled")
        return SummonPetDailyFlowResult(
            status=FlowStatus.CANCELLED, events=tuple(events), **kwargs
        )

    def _failed(self, events, error: str, **kwargs):
        self._record("summon_pet_daily.failed", error=error)
        return SummonPetDailyFlowResult(
            status=FlowStatus.FAILED, events=tuple(events), error=error, **kwargs
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

    # State predicates
    def _is_summon_shell(self, snapshot):
        """Allow partial navigation evidence to settle, without allowing input."""
        return (
            snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_SUMMON
            and set(snapshot.state.overlays) <= _SUMMON_STATUSES
        )

    def _is_clean_manage(self, snapshot):
        return (
            snapshot.state.status == ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PETS_MANAGE
            and set(snapshot.state.overlays) <= {STATUS_PET_SUMMON_DAILY_ACTIVE}
        )

    def _is_passive_unknown(self, snapshot):
        return snapshot.state.status == ResolutionStatus.UNKNOWN and not snapshot.state.overlays

    def _is_clean_combine(self, snapshot):
        return (
            snapshot.state.status == ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_COMBINE
            and not snapshot.state.overlays
        )

    def _is_summon_ready(self, snapshot):
        """Clean Pet Summon with Epic status resolved (AVAILABLE or UNAVAILABLE)."""
        overlays = set(snapshot.state.overlays)
        epic = overlays & {STATUS_PET_EPIC_AVAILABLE, STATUS_PET_EPIC_UNAVAILABLE}
        return (
            snapshot.state.status == ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_SUMMON
            and len(epic) == 1
            and overlays <= {
                STATUS_PET_EPIC_AVAILABLE,
                STATUS_PET_EPIC_UNAVAILABLE,
                STATUS_PET_PREMIUM_GOLD,
                STATUS_PET_PREMIUM_TICKET_AVAILABLE,
                STATUS_PET_SUMMON_DAILY_ACTIVE,
            }
        )

    def _is_summon_result(self, snapshot):
        return (
            snapshot.state.status == ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_SUMMON_RESULT
            and not snapshot.state.overlays
        )

    def _is_selector(self, snapshot, epic):
        selectors = (
            {OVERLAY_PET_EPIC_SELECTOR} if epic else
            {OVERLAY_PET_PREMIUM_GOLD_SELECTOR, OVERLAY_PET_PREMIUM_TICKET_SELECTOR}
        )
        overlays = set(snapshot.state.overlays)
        return (
            snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_SUMMON
            and len(overlays & selectors) == 1
            and overlays <= _SUMMON_STATUSES | selectors
        )

    def _is_insufficient_gold(self, snapshot):
        overlays = set(snapshot.state.overlays)
        return (
            snapshot.state.status == ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_SUMMON
            and POPUP_INSUFFICIENT_GOLD in overlays
            and overlays <= {
                STATUS_PET_EPIC_AVAILABLE,
                STATUS_PET_EPIC_UNAVAILABLE,
                STATUS_PET_PREMIUM_GOLD,
                STATUS_PET_PREMIUM_TICKET_AVAILABLE,
                STATUS_PET_SUMMON_DAILY_ACTIVE,
                POPUP_INSUFFICIENT_GOLD,
            }
        )

    def _is_pet_full(self, snapshot):
        overlays = set(snapshot.state.overlays)
        return (
            snapshot.state.status == ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_PET_SUMMON
            and POPUP_PET_INVENTORY_FULL in overlays
            and overlays <= {
                STATUS_PET_EPIC_AVAILABLE,
                STATUS_PET_EPIC_UNAVAILABLE,
                STATUS_PET_PREMIUM_GOLD,
                STATUS_PET_PREMIUM_TICKET_AVAILABLE,
                STATUS_PET_SUMMON_DAILY_ACTIVE,
                POPUP_PET_INVENTORY_FULL,
            }
        )

    def _known_incompatible(self, snapshot, expected_fn, retryable_fn):
        if expected_fn(snapshot) or retryable_fn(snapshot):
            return False
        return snapshot.state.status in {ResolutionStatus.RESOLVED, ResolutionStatus.AMBIGUOUS}

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
    "SummonPetDailyFlow",
    "SummonPetDailyFlowResult",
)
