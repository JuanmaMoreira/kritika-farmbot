"""Incidental Pet Summon inventory relief through one Combine All attempt."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from typing import Callable, Protocol

from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    POPUP_PET_COMBINE_ALL,
    POPUP_PET_COMBINE_NO_MATERIAL,
    POPUP_PET_EPIC_RUNES_FULL,
    SCREEN_PET_COMBINE,
    SCREEN_PET_COMBINE_RESULT,
)
from bot.event_log import EventSink
from bot.runtime_observer import (
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    AcknowledgePetCombineNoMaterial,
    ConfirmPetCombineAll,
    OpenPetCombineAll,
    RejectPetEpicRunesFull,
    TapCombineAnimation,
)
from bot.state import ResolutionStatus
from bot.tap_through_animation import (
    TapThroughAnimation,
    TapThroughOutcome,
    TapThroughPolicy,
)


class PetSummonSpaceReliefOutcome(str, Enum):
    RELIEVED = "relieved"
    NO_RELIEF_AVAILABLE = "no_relief_available"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PetSummonSpaceReliefPolicy:
    state_timeout: float = 6.0
    stable_for: float = 0.25
    animation: TapThroughPolicy = TapThroughPolicy()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "state_timeout", _positive_duration(self.state_timeout, "state_timeout")
        )
        object.__setattr__(
            self, "stable_for", _non_negative_duration(self.stable_for, "stable_for")
        )
        if not isinstance(self.animation, TapThroughPolicy):
            raise ValueError("animation must be a TapThroughPolicy")


@dataclass(frozen=True)
class PetSummonSpaceReliefResult:
    outcome: PetSummonSpaceReliefOutcome
    final_snapshot: RuntimeSnapshot
    combine_attempts: int = 0
    animation_taps: int = 0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome is PetSummonSpaceReliefOutcome.RELIEVED


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


class PetSummonSpaceRelief:
    """Try one verified Combine All and perform no general Pets maintenance."""

    def __init__(
        self,
        observer,
        actions,
        events: EventSink,
        *,
        tap_through: TapThroughAnimation | None = None,
        policy: PetSummonSpaceReliefPolicy | None = None,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.tap_through = tap_through or TapThroughAnimation(
            observer, actions, events
        )
        self.policy = policy or PetSummonSpaceReliefPolicy()

    def run(
        self,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> PetSummonSpaceReliefResult:
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        current = self.observer.observe()
        combine_attempts = 0
        animation_taps = 0
        self._record("pet_summon_space_relief.started", sequence=current.sequence)
        try:
            if cancel_requested():
                raise RuntimeWaitCancelled("pet summon space relief cancelled")
            if not _is_clean_combine(current):
                return self._finish(
                    PetSummonSpaceReliefOutcome.FAILED,
                    current,
                    error="precondition_pet_combine_failed",
                )

            popup = self._act_and_wait(
                OpenPetCombineAll(),
                current,
                expected=_is_safe_combine_outcome,
                retryable_from=_is_clean_combine,
                cancel_requested=cancel_requested,
            )
            combine_attempts = 1
            current = popup

            if _is_popup(popup, POPUP_PET_COMBINE_NO_MATERIAL):
                current = self._dismiss_no_material(popup, cancel_requested)
                return self._finish(
                    PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE,
                    current,
                    combine_attempts=combine_attempts,
                )
            if _is_popup(popup, POPUP_PET_EPIC_RUNES_FULL):
                current = self._reject_runes(popup, cancel_requested)
                return self._finish(
                    PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE,
                    current,
                    combine_attempts=combine_attempts,
                )

            outcome = self._act_and_wait(
                ConfirmPetCombineAll(),
                popup,
                expected=lambda snapshot: (
                    _is_combine_result(snapshot)
                    or _is_clean_combine(snapshot)
                    or _is_popup(snapshot, POPUP_PET_COMBINE_NO_MATERIAL)
                    or _is_popup(snapshot, POPUP_PET_EPIC_RUNES_FULL)
                ),
                retryable_from=lambda snapshot: _is_popup(
                    snapshot, POPUP_PET_COMBINE_ALL
                ),
                cancel_requested=cancel_requested,
            )
            current = outcome
            if _is_clean_combine(outcome):
                return self._finish(
                    PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE,
                    current,
                    combine_attempts=combine_attempts,
                )
            if _is_popup(outcome, POPUP_PET_COMBINE_NO_MATERIAL):
                current = self._dismiss_no_material(outcome, cancel_requested)
                return self._finish(
                    PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE,
                    current,
                    combine_attempts=combine_attempts,
                )
            if _is_popup(outcome, POPUP_PET_EPIC_RUNES_FULL):
                current = self._reject_runes(outcome, cancel_requested)
                return self._finish(
                    PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE,
                    current,
                    combine_attempts=combine_attempts,
                )

            current, animation_taps = self._tap_result(outcome, cancel_requested)
            return self._finish(
                PetSummonSpaceReliefOutcome.RELIEVED,
                current,
                combine_attempts=combine_attempts,
                animation_taps=animation_taps,
            )
        except RuntimeWaitCancelled:
            return self._finish(
                PetSummonSpaceReliefOutcome.CANCELLED,
                current,
                combine_attempts=combine_attempts,
                animation_taps=animation_taps,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            latest = getattr(error, "last_snapshot", None) or getattr(
                error, "snapshot", None
            )
            return self._finish(
                PetSummonSpaceReliefOutcome.FAILED,
                latest or current,
                combine_attempts=combine_attempts,
                animation_taps=animation_taps,
                error=f"state_wait_failed: {error}",
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._finish(
                PetSummonSpaceReliefOutcome.FAILED,
                current,
                combine_attempts=combine_attempts,
                animation_taps=animation_taps,
                error=f"{type(error).__name__}: {error}",
            )

    def _dismiss_no_material(self, popup, cancel_requested):
        return self._act_and_wait(
            AcknowledgePetCombineNoMaterial(),
            popup,
            expected=_is_clean_combine,
            retryable_from=lambda snapshot: _is_popup(
                snapshot, POPUP_PET_COMBINE_NO_MATERIAL
            ),
            cancel_requested=cancel_requested,
        )

    def _reject_runes(self, popup, cancel_requested):
        return self._act_and_wait(
            RejectPetEpicRunesFull(),
            popup,
            expected=_is_clean_combine,
            retryable_from=lambda snapshot: _is_popup(
                snapshot, POPUP_PET_EPIC_RUNES_FULL
            ),
            cancel_requested=cancel_requested,
        )

    def _tap_result(self, result, cancel_requested):
        tapped = self.tap_through.run(
            result,
            action=TapCombineAnimation(),
            expected=_is_clean_combine,
            tappable=_is_combine_result_tappable,
            transient=_is_combine_result_transient,
            cancel_requested=cancel_requested,
            policy=self.policy.animation,
        )
        if tapped.outcome is TapThroughOutcome.CANCELLED:
            raise RuntimeWaitCancelled("pet combine animation cancelled")
        if tapped.outcome is not TapThroughOutcome.COMPLETED:
            raise RuntimeError(
                f"pet_combine_animation_{tapped.outcome.value}: "
                f"{tapped.error or 'incomplete'}"
            )
        return tapped.final_snapshot, tapped.tap_count

    def _act_and_wait(
        self,
        action,
        before,
        *,
        expected,
        retryable_from,
        cancel_requested,
    ):
        if cancel_requested():
            raise RuntimeWaitCancelled("pet summon space relief cancelled")
        self.actions.execute(action, before.geometry)
        return self.observer.wait_until(
            expected,
            after_sequence=before.sequence,
            timeout=self.policy.state_timeout,
            abort_if=lambda snapshot: _known_incompatible(
                snapshot, expected, retryable_from
            ),
            cancel_requested=cancel_requested,
            stable_for=self.policy.stable_for,
        )

    def _finish(self, outcome, snapshot, **kwargs):
        result = PetSummonSpaceReliefResult(outcome, snapshot, **kwargs)
        self._record(
            "pet_summon_space_relief.finished",
            outcome=outcome.value,
            sequence=snapshot.sequence,
            combine_attempts=result.combine_attempts,
            animation_taps=result.animation_taps,
            error=result.error,
        )
        return result

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _is_clean_combine(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_COMBINE
        and not snapshot.state.overlays
    )


def _is_popup(snapshot: RuntimeSnapshot, popup: str) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_COMBINE
        and set(snapshot.state.overlays) == {popup}
    )


def _is_safe_combine_outcome(snapshot: RuntimeSnapshot) -> bool:
    return any(
        _is_popup(snapshot, popup)
        for popup in (
            POPUP_PET_COMBINE_ALL,
            POPUP_PET_COMBINE_NO_MATERIAL,
            POPUP_PET_EPIC_RUNES_FULL,
        )
    )


def _is_combine_result(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_COMBINE_RESULT
        and not snapshot.state.overlays
    )


def _is_combine_result_tappable(snapshot: RuntimeSnapshot) -> bool:
    return _is_combine_result(snapshot) and bool(
        snapshot.observations.find(ACTIVITY_COMBINE_ANIMATION_TAPPABLE)
    )


def _is_combine_result_transient(snapshot: RuntimeSnapshot) -> bool:
    return snapshot.state.status is ResolutionStatus.UNKNOWN or _is_combine_result(snapshot)


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
    "PetSummonSpaceRelief",
    "PetSummonSpaceReliefOutcome",
    "PetSummonSpaceReliefPolicy",
    "PetSummonSpaceReliefResult",
)
