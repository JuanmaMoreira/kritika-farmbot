"""Bounded non-destructive Pet Summon inventory space relief."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
import math
from typing import Callable, Protocol

from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    CANDIDATE_PET_LOW_TIER,
    LANDMARK_PET_MASS_EVOLVE_CONFIRMATION,
    MODE_PET_MASS_EVOLVE_SELECTION,
    OVERLAY_PET_EPIC_SELECTOR,
    POPUP_PET_COMBINE_ALL,
    POPUP_PET_COMBINE_NO_MATERIAL,
    POPUP_PET_EPIC_RUNES_FULL,
    POPUP_PET_INVENTORY_FULL,
    POPUP_PET_MASS_EVOLVE_CONFIRMATION,
    SCREEN_PET_COMBINE,
    SCREEN_PET_COMBINE_RESULT,
    SCREEN_PET_SUMMON,
    SCREEN_PET_SUMMON_RESULT,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_PREMIUM_TICKET_AVAILABLE,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
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
    CancelPetMassEvolveSelection,
    ClosePetSummonResult,
    ConfirmPetCombineAll,
    ConfirmPetMassEvolve,
    NextPetCombinePage,
    OpenEpicPetSummon,
    OpenPetCombineAll,
    OpenPetMassEvolve,
    OpenTenEpicPets,
    RejectPetEpicRunesFull,
    RejectPetInventoryFull,
    SelectPetCombine,
    SelectPetLowTierCandidate,
    SelectPetSummon,
    TapCombineAnimation,
)
from bot.state import ResolutionStatus
from bot.tap_through_animation import (
    TapThroughAnimation,
    TapThroughOutcome,
    TapThroughPolicy,
)


_SAFE_TIERS = ("normal", "rare")
_EPIC_BATCH_RESULT_LIMIT = 10
_SUMMON_STATUSES = frozenset(
    {
        STATUS_PET_EPIC_AVAILABLE,
        STATUS_PET_EPIC_UNAVAILABLE,
        STATUS_PET_PREMIUM_GOLD,
        STATUS_PET_PREMIUM_TICKET_AVAILABLE,
        STATUS_PET_SUMMON_DAILY_ACTIVE,
    }
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
    max_candidate_pages: int = 20
    animation: TapThroughPolicy = TapThroughPolicy()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "state_timeout", _positive_duration(self.state_timeout, "state_timeout")
        )
        object.__setattr__(
            self, "stable_for", _non_negative_duration(self.stable_for, "stable_for")
        )
        for name in ("max_candidate_pages",):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            object.__setattr__(self, name, int(value))
        if not isinstance(self.animation, TapThroughPolicy):
            raise ValueError("animation must be a TapThroughPolicy")


@dataclass(frozen=True)
class PetSummonSpaceReliefResult:
    outcome: PetSummonSpaceReliefOutcome
    final_snapshot: RuntimeSnapshot
    combine_attempts: int = 0
    candidate_tier: str | None = None
    candidate_pages_checked: int = 0
    epic_openings: int = 0
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


class _CombineOutcome(str, Enum):
    EFFECT = "effect"
    NO_EFFECT = "no_effect"
    RUNES_FULL = "runes_full"


@dataclass(frozen=True)
class _CombineResult:
    outcome: _CombineOutcome
    snapshot: RuntimeSnapshot
    animation_taps: int = 0


class PetSummonSpaceRelief:
    """Try only Combine All, safe low-tier evolution and bounded Epic opens."""

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
        candidate_tier = None
        pages_checked = 0
        epic_openings = 0
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

            direct = self._combine_all(current, cancel_requested)
            combine_attempts += 1
            current = direct.snapshot
            animation_taps += direct.animation_taps
            if direct.outcome is _CombineOutcome.EFFECT:
                return self._finish(
                    PetSummonSpaceReliefOutcome.RELIEVED,
                    current,
                    combine_attempts=combine_attempts,
                    animation_taps=animation_taps,
                )

            candidate, current, pages_checked = self._find_candidate(
                current, cancel_requested
            )
            if candidate is None:
                if direct.outcome is not _CombineOutcome.RUNES_FULL:
                    return self._finish(
                        PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE,
                        current,
                        combine_attempts=combine_attempts,
                        candidate_pages_checked=pages_checked,
                        animation_taps=animation_taps,
                    )
            else:
                candidate_tier, target = candidate
                current, taps = self._mass_evolve(
                    current,
                    candidate_tier,
                    target,
                    cancel_requested,
                )
                animation_taps += taps

            current = self._cancel_selection_if_needed(current, cancel_requested)
            summon = self._act_and_wait(
                SelectPetSummon(),
                current,
                expected=_is_summon_ready,
                retryable_from=_is_clean_combine,
                cancel_requested=cancel_requested,
            )
            current, epic_openings = self._open_epics(
                summon, cancel_requested
            )
            current = self._act_and_wait(
                SelectPetCombine(),
                current,
                expected=_is_clean_combine,
                retryable_from=_is_summon_ready,
                cancel_requested=cancel_requested,
            )

            second = self._combine_all(current, cancel_requested)
            combine_attempts += 1
            current = second.snapshot
            animation_taps += second.animation_taps
            outcome = (
                PetSummonSpaceReliefOutcome.RELIEVED
                if second.outcome is _CombineOutcome.EFFECT
                else PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
            )
            return self._finish(
                outcome,
                current,
                combine_attempts=combine_attempts,
                candidate_tier=candidate_tier,
                candidate_pages_checked=pages_checked,
                epic_openings=epic_openings,
                animation_taps=animation_taps,
            )
        except RuntimeWaitCancelled:
            return self._finish(
                PetSummonSpaceReliefOutcome.CANCELLED,
                current,
                combine_attempts=combine_attempts,
                candidate_tier=candidate_tier,
                candidate_pages_checked=pages_checked,
                epic_openings=epic_openings,
                animation_taps=animation_taps,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            latest = getattr(error, "last_snapshot", None)
            return self._finish(
                PetSummonSpaceReliefOutcome.FAILED,
                latest or current,
                combine_attempts=combine_attempts,
                candidate_tier=candidate_tier,
                candidate_pages_checked=pages_checked,
                epic_openings=epic_openings,
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
                candidate_tier=candidate_tier,
                candidate_pages_checked=pages_checked,
                epic_openings=epic_openings,
                animation_taps=animation_taps,
                error=f"{type(error).__name__}: {error}",
            )

    def _combine_all(self, current, cancel_requested) -> _CombineResult:
        popup = self._act_and_wait(
            OpenPetCombineAll(),
            current,
            expected=lambda snapshot: (
                _is_popup(snapshot, POPUP_PET_COMBINE_ALL)
                or _is_popup(snapshot, POPUP_PET_COMBINE_NO_MATERIAL)
                or _is_runes_full(snapshot)
            ),
            retryable_from=_is_clean_combine,
            cancel_requested=cancel_requested,
        )
        if _is_popup(popup, POPUP_PET_COMBINE_NO_MATERIAL):
            clean = self._dismiss_no_material(popup, cancel_requested)
            return _CombineResult(_CombineOutcome.NO_EFFECT, clean)
        if _is_runes_full(popup):
            clean = self._reject_runes(popup, cancel_requested)
            return _CombineResult(_CombineOutcome.RUNES_FULL, clean)

        outcome = self._act_and_wait(
            ConfirmPetCombineAll(),
            popup,
            expected=lambda snapshot: (
                _is_combine_result(snapshot)
                or _is_popup(snapshot, POPUP_PET_COMBINE_NO_MATERIAL)
                or _is_runes_full(snapshot)
            ),
            retryable_from=lambda snapshot: _is_popup(
                snapshot, POPUP_PET_COMBINE_ALL
            ),
            cancel_requested=cancel_requested,
        )
        if _is_popup(outcome, POPUP_PET_COMBINE_NO_MATERIAL):
            clean = self._dismiss_no_material(outcome, cancel_requested)
            return _CombineResult(_CombineOutcome.NO_EFFECT, clean)
        if _is_runes_full(outcome):
            clean = self._reject_runes(outcome, cancel_requested)
            return _CombineResult(_CombineOutcome.RUNES_FULL, clean)
        clean, taps = self._tap_result(outcome, cancel_requested)
        return _CombineResult(_CombineOutcome.EFFECT, clean, taps)

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
        selection = MODE_PET_MASS_EVOLVE_SELECTION in popup.state.overlays
        expected = _is_mass_selection if selection else _is_clean_combine
        return self._act_and_wait(
            RejectPetEpicRunesFull(),
            popup,
            expected=expected,
            retryable_from=_is_runes_full,
            cancel_requested=cancel_requested,
        )

    def _find_candidate(self, current, cancel_requested):
        for page in range(1, self.policy.max_candidate_pages + 1):
            candidate = _safe_candidate(current)
            if candidate is not None:
                return candidate, current, page
            if page == self.policy.max_candidate_pages:
                return None, current, page
            current = self._act_and_wait(
                NextPetCombinePage(),
                current,
                expected=_is_clean_combine,
                retryable_from=_is_clean_combine,
                cancel_requested=cancel_requested,
            )
        raise AssertionError("bounded candidate loop exhausted unexpectedly")

    def _mass_evolve(
        self, current, tier: str, target, cancel_requested
    ) -> tuple[RuntimeSnapshot, int]:
        selection = self._act_and_wait(
            SelectPetLowTierCandidate(target),
            current,
            expected=_is_mass_selection,
            retryable_from=_is_clean_combine,
            cancel_requested=cancel_requested,
        )
        popup = self._act_and_wait(
            OpenPetMassEvolve(),
            selection,
            expected=lambda snapshot: (
                _is_mass_confirmation(snapshot) or _is_runes_full(snapshot)
            ),
            retryable_from=_is_mass_selection,
            cancel_requested=cancel_requested,
        )
        if _is_runes_full(popup):
            return self._reject_runes(popup, cancel_requested), 0
        observed_tier = _mass_confirmation_tier(popup)
        if observed_tier != tier:
            raise RuntimeError(
                f"mass_evolve_tier_mismatch: expected={tier} observed={observed_tier}"
            )
        result = self._act_and_wait(
            ConfirmPetMassEvolve(),
            popup,
            expected=lambda snapshot: (
                _is_combine_result(snapshot) or _is_runes_full(snapshot)
            ),
            retryable_from=_is_mass_confirmation,
            cancel_requested=cancel_requested,
        )
        if _is_runes_full(result):
            return self._reject_runes(result, cancel_requested), 0
        return self._tap_result(result, cancel_requested)

    def _tap_result(self, result, cancel_requested):
        tapped = self.tap_through.run(
            result,
            action=TapCombineAnimation(),
            expected=_is_combine_stable,
            tappable=_is_combine_result_tappable,
            transient=_is_combine_result_transient,
            cancel_requested=cancel_requested,
            policy=self.policy.animation,
        )
        if tapped.outcome is TapThroughOutcome.CANCELLED:
            raise RuntimeWaitCancelled("pet combine animation cancelled")
        if tapped.outcome is not TapThroughOutcome.COMPLETED:
            raise RuntimeError(
                f"pet_combine_animation_{tapped.outcome.value}: {tapped.error or 'incomplete'}"
            )
        return tapped.final_snapshot, tapped.tap_count

    def _cancel_selection_if_needed(self, current, cancel_requested):
        if not _is_mass_selection(current):
            if not _is_clean_combine(current):
                raise RuntimeError("pet_combine_state_incompatible_before_tab_change")
            return current
        return self._act_and_wait(
            CancelPetMassEvolveSelection(),
            current,
            expected=_is_clean_combine,
            retryable_from=_is_mass_selection,
            cancel_requested=cancel_requested,
        )

    def _open_epics(self, current, cancel_requested):
        opened = 0
        if STATUS_PET_EPIC_AVAILABLE in current.state.overlays:
            selector = self._act_and_wait(
                OpenEpicPetSummon(),
                current,
                expected=_is_epic_selector,
                retryable_from=_is_summon_epic_available,
                cancel_requested=cancel_requested,
            )
            outcome = self._act_and_wait(
                OpenTenEpicPets(),
                selector,
                expected=lambda snapshot: (
                    _is_summon_result(snapshot) or _is_pet_full(snapshot)
                ),
                retryable_from=_is_epic_selector,
                cancel_requested=cancel_requested,
            )
            if _is_pet_full(outcome):
                current = self._act_and_wait(
                    RejectPetInventoryFull(),
                    outcome,
                    expected=_is_summon_ready,
                    retryable_from=_is_pet_full,
                    cancel_requested=cancel_requested,
                )
            else:
                opened = 1
                current = self._dismiss_epic_batch_results(
                    outcome, cancel_requested
                )
        if not _is_summon_ready(current):
            raise RuntimeError("epic_opening_ended_in_incompatible_state")
        return current, opened

    def _dismiss_epic_batch_results(self, current, cancel_requested):
        """Support either one summary result or up to ten sequential results."""

        for _ in range(_EPIC_BATCH_RESULT_LIMIT):
            current = self._act_and_wait(
                ClosePetSummonResult(),
                current,
                expected=lambda snapshot: (
                    _is_summon_result(snapshot) or _is_summon_ready(snapshot)
                ),
                retryable_from=_is_summon_result,
                cancel_requested=cancel_requested,
            )
            if _is_summon_ready(current):
                return current
        raise RuntimeError("epic_batch_result_limit")

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
            candidate_tier=result.candidate_tier,
            candidate_pages_checked=result.candidate_pages_checked,
            epic_openings=result.epic_openings,
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


def _is_combine_stable(snapshot: RuntimeSnapshot) -> bool:
    return _is_clean_combine(snapshot) or _is_mass_selection(snapshot)


def _is_mass_selection(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_COMBINE
        and set(snapshot.state.overlays) == {MODE_PET_MASS_EVOLVE_SELECTION}
    )


def _is_popup(snapshot: RuntimeSnapshot, popup: str) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_COMBINE
        and popup in snapshot.state.overlays
        and set(snapshot.state.overlays)
        <= {popup, MODE_PET_MASS_EVOLVE_SELECTION}
    )


def _is_runes_full(snapshot: RuntimeSnapshot) -> bool:
    return _is_popup(snapshot, POPUP_PET_EPIC_RUNES_FULL)


def _is_mass_confirmation(snapshot: RuntimeSnapshot) -> bool:
    return _is_popup(snapshot, POPUP_PET_MASS_EVOLVE_CONFIRMATION)


def _mass_confirmation_tier(snapshot: RuntimeSnapshot) -> str | None:
    candidates = snapshot.observations.find(
        LANDMARK_PET_MASS_EVOLVE_CONFIRMATION
    )
    values = {item.value for item in candidates if item.value in _SAFE_TIERS}
    return next(iter(values)) if len(values) == 1 else None


def _safe_candidate(snapshot: RuntimeSnapshot):
    candidates = [
        item
        for item in snapshot.observations.find(CANDIDATE_PET_LOW_TIER)
        if item.value in _SAFE_TIERS and item.region is not None
    ]
    candidates.sort(key=lambda item: (_SAFE_TIERS.index(item.value), -item.confidence))
    if not candidates:
        return None
    selected = candidates[0]
    x1, y1, x2, y2 = selected.region
    return selected.value, ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


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


def _is_summon_ready(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    epic = overlays & {STATUS_PET_EPIC_AVAILABLE, STATUS_PET_EPIC_UNAVAILABLE}
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and len(epic) == 1
        and overlays <= _SUMMON_STATUSES
    )


def _is_summon_epic_available(snapshot: RuntimeSnapshot) -> bool:
    return _is_summon_ready(snapshot) and STATUS_PET_EPIC_AVAILABLE in snapshot.state.overlays


def _is_epic_selector(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON
        and OVERLAY_PET_EPIC_SELECTOR in overlays
        and overlays <= (_SUMMON_STATUSES | {OVERLAY_PET_EPIC_SELECTOR})
    )


def _is_summon_result(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_PET_SUMMON_RESULT
        and not snapshot.state.overlays
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
    "PetSummonSpaceRelief",
    "PetSummonSpaceReliefOutcome",
    "PetSummonSpaceReliefPolicy",
    "PetSummonSpaceReliefResult",
)
