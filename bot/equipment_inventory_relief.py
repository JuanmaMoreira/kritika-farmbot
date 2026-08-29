"""Reusable bounded support operation for equipment inventory relief."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    MODE_COMBINE_FUSE,
    MODE_COMBINE_TRANSMUTE,
    PANEL_COMBINE_AWAKENED_TRANSMUTE,
    PANEL_COMBINE_ETHEREAL_RANDOM_PART,
    POPUP_COMBINE_ALL,
    POPUP_ETHEREAL_MASS_COMBINE,
    POPUP_ETHEREAL_NO_MATERIAL,
    SCREEN_COMBINE,
    STATUS_COMBINE_ETHEREAL_AVAILABLE,
    STATUS_COMBINE_FUSE_AVAILABLE,
    STATUS_COMBINE_TRANSMUTE_AVAILABLE,
)
from bot.event_log import EventSink
from bot.observations import validate_semantic_name
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.semantic_actions import (
    AcknowledgeEtherealNoMaterial,
    ConfirmCombineAll,
    ConfirmEtherealMassCombine,
    OpenAwakenedTransmute,
    OpenCombineAll,
    OpenEtherealMassCombine,
    OpenEtherealRandomPart,
    SelectCombineFuse,
    SelectCombineTransmute,
    TapCombineAnimation,
)
from bot.state import ResolutionStatus
from bot.tap_through_animation import (
    TapThroughAnimation,
    TapThroughOutcome,
    TapThroughPolicy,
)
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


class EquipmentReliefOutcome(str, Enum):
    RELIEVED = "relieved"
    NO_RELIEF_AVAILABLE = "no_relief_available"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EquipmentStrategyOutcome(str, Enum):
    NOT_RUN = "not_run"
    SKIPPED = "skipped"
    EFFECT = "effect"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class EquipmentReturnPlan:
    action: object
    expected_return_state: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_return_state",
            validate_semantic_name(self.expected_return_state),
        )


@dataclass(frozen=True)
class EquipmentReliefResult:
    outcome: EquipmentReliefOutcome
    transmute: EquipmentStrategyOutcome = EquipmentStrategyOutcome.NOT_RUN
    ethereal: EquipmentStrategyOutcome = EquipmentStrategyOutcome.NOT_RUN
    fuse: EquipmentStrategyOutcome = EquipmentStrategyOutcome.NOT_RUN
    animation_taps: int = 0
    final_snapshot: RuntimeSnapshot | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome in {
            EquipmentReliefOutcome.RELIEVED,
            EquipmentReliefOutcome.NO_RELIEF_AVAILABLE,
        }


class EquipmentInventoryRelief:
    """Run Transmute, conditional Ethereal, then fresh Fuse and return exactly."""

    def __init__(
        self,
        observer,
        actions,
        events: EventSink,
        *,
        verified_transition: VerifiedTransition | None = None,
        tap_through: TapThroughAnimation | None = None,
        transition_timeout: float = 6.0,
        stable_for: float = 0.25,
        animation_policy: TapThroughPolicy = TapThroughPolicy(),
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if transition_timeout <= 0 or stable_for < 0:
            raise ValueError("timeout must be positive and stability non-negative")
        if not isinstance(animation_policy, TapThroughPolicy):
            raise ValueError("animation_policy must be TapThroughPolicy")
        self.observer = observer
        self.actions = actions
        self.events = events
        self.stable_for = float(stable_for)
        self.animation_policy = animation_policy
        self.transition = verified_transition or VerifiedTransition(
            observer, actions, events
        )
        self.tap_through = tap_through or TapThroughAnimation(
            observer, actions, events
        )
        self.normal_policy = VerifiedTransitionPolicy(
            normal_timeout=transition_timeout,
            grace_timeout=1.0,
            max_attempts=2,
        )
        self.single_action_policy = VerifiedTransitionPolicy(
            normal_timeout=transition_timeout,
            grace_timeout=0.5,
            max_attempts=1,
        )

    def run(
        self,
        return_plan: EquipmentReturnPlan,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> EquipmentReliefResult:
        if not isinstance(return_plan, EquipmentReturnPlan):
            raise ValueError("return_plan must be an EquipmentReturnPlan")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        try:
            return self._run(return_plan, cancel_requested)
        except (KeyboardInterrupt, SystemExit):
            raise
        except RuntimeWaitCancelled:
            return self._cancelled()
        except Exception as error:
            return self._failed(f"{type(error).__name__}: {error}")

    def _run(self, return_plan, cancel_requested):
        if cancel_requested():
            return self._cancelled()
        current = self.observer.observe()
        if not _is_stable_combine(current):
            return self._failed(
                "equipment_relief_precondition_rejected",
                final_snapshot=current,
            )
        self._record("equipment_relief.started", sequence=current.sequence)

        transmute_menu = self._transition(
            "equipment_relief.select_transmute",
            SelectCombineTransmute(),
            current,
            expected=_is_transmute_menu,
            precondition=_is_stable_combine,
        )
        if transmute_menu is None:
            return self._failed("equipment_transmute_entry_failed", final_snapshot=current)

        transmute, current, taps = self._base_combine(
            transmute_menu,
            mode=MODE_COMBINE_TRANSMUTE,
            status=STATUS_COMBINE_TRANSMUTE_AVAILABLE,
            cancel_requested=cancel_requested,
            label="transmute",
        )
        if transmute is EquipmentStrategyOutcome.CANCELLED:
            return self._cancelled(transmute=transmute, animation_taps=taps, final_snapshot=current)
        if transmute is EquipmentStrategyOutcome.FAILED:
            return self._failed("equipment_transmute_failed", transmute=transmute, animation_taps=taps, final_snapshot=current)

        ethereal, current, ethereal_taps = self._ethereal(current, cancel_requested)
        taps += ethereal_taps
        if ethereal is EquipmentStrategyOutcome.CANCELLED:
            return self._cancelled(transmute=transmute, ethereal=ethereal, animation_taps=taps, final_snapshot=current)
        if ethereal is EquipmentStrategyOutcome.FAILED:
            return self._failed("equipment_ethereal_failed", transmute=transmute, ethereal=ethereal, animation_taps=taps, final_snapshot=current)

        if cancel_requested():
            return self._cancelled(transmute=transmute, ethereal=ethereal, animation_taps=taps, final_snapshot=current)
        fuse_menu = self._transition(
            "equipment_relief.select_fuse",
            SelectCombineFuse(),
            current,
            expected=_is_fuse_menu,
            precondition=_is_transmute_menu,
        )
        if fuse_menu is None:
            return self._failed("equipment_fuse_entry_failed", transmute=transmute, ethereal=ethereal, animation_taps=taps, final_snapshot=current)
        fuse, current, fuse_taps = self._base_combine(
            fuse_menu,
            mode=MODE_COMBINE_FUSE,
            status=STATUS_COMBINE_FUSE_AVAILABLE,
            cancel_requested=cancel_requested,
            label="fuse",
        )
        taps += fuse_taps
        if fuse is EquipmentStrategyOutcome.CANCELLED:
            return self._cancelled(transmute=transmute, ethereal=ethereal, fuse=fuse, animation_taps=taps, final_snapshot=current)
        if fuse is EquipmentStrategyOutcome.FAILED:
            return self._failed("equipment_fuse_failed", transmute=transmute, ethereal=ethereal, fuse=fuse, animation_taps=taps, final_snapshot=current)

        if cancel_requested():
            return self._cancelled(transmute=transmute, ethereal=ethereal, fuse=fuse, animation_taps=taps, final_snapshot=current)
        returned = self._transition(
            "equipment_relief.return",
            return_plan.action,
            current,
            expected=lambda item: _is_clean_base(item, return_plan.expected_return_state),
            precondition=_is_fuse_menu,
        )
        if returned is None:
            return self._failed("equipment_return_failed", transmute=transmute, ethereal=ethereal, fuse=fuse, animation_taps=taps, final_snapshot=current)

        relieved = EquipmentStrategyOutcome.EFFECT in {transmute, ethereal, fuse}
        outcome = EquipmentReliefOutcome.RELIEVED if relieved else EquipmentReliefOutcome.NO_RELIEF_AVAILABLE
        self._record(
            "equipment_relief.finished",
            outcome=outcome.value,
            transmute=transmute.value,
            ethereal=ethereal.value,
            fuse=fuse.value,
            animation_taps=taps,
            expected_return_state=return_plan.expected_return_state,
        )
        return EquipmentReliefResult(outcome, transmute, ethereal, fuse, taps, returned)

    def _base_combine(self, current, *, mode, status, cancel_requested, label):
        if cancel_requested():
            return EquipmentStrategyOutcome.CANCELLED, current, 0
        expected_menu = _is_transmute_menu if mode == MODE_COMBINE_TRANSMUTE else _is_fuse_menu
        if status not in current.state.overlays:
            self._record(f"equipment_relief.{label}_skipped")
            return EquipmentStrategyOutcome.SKIPPED, current, 0
        popup = self._transition(
            f"equipment_relief.{label}.open_combine_all",
            OpenCombineAll(),
            current,
            expected=lambda item: _is_combine_all_popup(item, mode),
            precondition=lambda item: expected_menu(item) and status in item.state.overlays,
        )
        if popup is None:
            return EquipmentStrategyOutcome.FAILED, current, 0
        animation = self._transition(
            f"equipment_relief.{label}.confirm_combine_all",
            ConfirmCombineAll(),
            popup,
            expected=_is_tappable_animation,
            precondition=lambda item: _is_combine_all_popup(item, mode),
            tolerated=_is_combine_animation_transient,
            policy=self.single_action_policy,
        )
        if animation is None:
            self._record(f"equipment_relief.{label}_contradiction", reason="no_verified_animation")
            return EquipmentStrategyOutcome.FAILED, popup, 0
        tapped = self.tap_through.run(
            animation,
            action=TapCombineAnimation(),
            expected=lambda item: expected_menu(item) and status not in item.state.overlays,
            tappable=_is_tappable_animation,
            transient=_is_combine_animation_transient,
            cancel_requested=cancel_requested,
            policy=self.animation_policy,
        )
        if tapped.outcome is TapThroughOutcome.CANCELLED:
            return EquipmentStrategyOutcome.CANCELLED, tapped.final_snapshot, tapped.tap_count
        if not tapped.succeeded:
            self._record(f"equipment_relief.{label}_failed", reason=tapped.outcome.value)
            return EquipmentStrategyOutcome.FAILED, tapped.final_snapshot, tapped.tap_count
        self._record(f"equipment_relief.{label}_effect", taps=tapped.tap_count)
        return EquipmentStrategyOutcome.EFFECT, tapped.final_snapshot, tapped.tap_count

    def _ethereal(self, current, cancel_requested):
        if cancel_requested():
            return EquipmentStrategyOutcome.CANCELLED, current, 0
        if STATUS_COMBINE_ETHEREAL_AVAILABLE not in current.state.overlays:
            self._record("equipment_relief.ethereal_skipped")
            return EquipmentStrategyOutcome.SKIPPED, current, 0
        awakened = self._transition(
            "equipment_relief.ethereal.open_awakened",
            OpenAwakenedTransmute(),
            current,
            expected=_is_awakened_panel,
            precondition=lambda item: _is_transmute_menu(item) and STATUS_COMBINE_ETHEREAL_AVAILABLE in item.state.overlays,
        )
        if awakened is None:
            return EquipmentStrategyOutcome.FAILED, current, 0
        random_part = self._transition(
            "equipment_relief.ethereal.open_random_part",
            OpenEtherealRandomPart(),
            awakened,
            expected=_is_random_part_panel,
            precondition=_is_awakened_panel,
        )
        if random_part is None:
            return EquipmentStrategyOutcome.FAILED, awakened, 0
        outcome = self._transition(
            "equipment_relief.ethereal.open_mass_combine",
            OpenEtherealMassCombine(),
            random_part,
            expected=lambda item: _is_ethereal_confirm(item) or _is_ethereal_no_material(item),
            precondition=_is_random_part_panel,
            policy=self.single_action_policy,
        )
        if outcome is None:
            return EquipmentStrategyOutcome.FAILED, random_part, 0
        if _is_ethereal_no_material(outcome):
            acknowledged = self._transition(
                "equipment_relief.ethereal.ack_no_material",
                AcknowledgeEtherealNoMaterial(),
                outcome,
                expected=_is_random_part_panel,
                precondition=_is_ethereal_no_material,
            )
            if acknowledged is not None:
                restored = self._transition(
                    "equipment_relief.ethereal.restore_transmute",
                    SelectCombineTransmute(),
                    acknowledged,
                    expected=_is_transmute_menu,
                    precondition=_is_random_part_panel,
                )
                acknowledged = restored or acknowledged
            self._record("equipment_relief.ethereal_defensive_no_material")
            return EquipmentStrategyOutcome.FAILED, acknowledged or outcome, 0
        animation = self._transition(
            "equipment_relief.ethereal.confirm_mass_combine",
            ConfirmEtherealMassCombine(),
            outcome,
            expected=_is_tappable_animation,
            precondition=_is_ethereal_confirm,
            tolerated=_is_combine_animation_transient,
            policy=self.single_action_policy,
        )
        if animation is None:
            return EquipmentStrategyOutcome.FAILED, outcome, 0
        tapped = self.tap_through.run(
            animation,
            action=TapCombineAnimation(),
            expected=_is_random_part_panel,
            tappable=_is_tappable_animation,
            transient=_is_combine_animation_transient,
            cancel_requested=cancel_requested,
            policy=self.animation_policy,
        )
        if tapped.outcome is TapThroughOutcome.CANCELLED:
            return EquipmentStrategyOutcome.CANCELLED, tapped.final_snapshot, tapped.tap_count
        if not tapped.succeeded:
            return EquipmentStrategyOutcome.FAILED, tapped.final_snapshot, tapped.tap_count
        restored = self._transition(
            "equipment_relief.ethereal.return_transmute",
            SelectCombineTransmute(),
            tapped.final_snapshot,
            expected=lambda item: _is_transmute_menu(item) and STATUS_COMBINE_ETHEREAL_AVAILABLE not in item.state.overlays,
            precondition=_is_random_part_panel,
        )
        if restored is None:
            return EquipmentStrategyOutcome.FAILED, tapped.final_snapshot, tapped.tap_count
        self._record("equipment_relief.ethereal_effect", taps=tapped.tap_count)
        return EquipmentStrategyOutcome.EFFECT, restored, tapped.tap_count

    def _transition(self, name, action, before, *, expected, precondition, tolerated=lambda _: False, policy=None):
        result = self.transition.execute(
            name,
            action,
            before,
            expected=expected,
            precondition=precondition,
            retryable_from=precondition,
            abort_if=lambda item: _known_incompatible(item, expected, precondition) and not tolerated(item),
            stable_for=self.stable_for,
            policy=policy or self.normal_policy,
        )
        self._record("equipment_relief.transition", name=name, outcome=result.outcome.value, attempts=result.attempt_count)
        return result.final_snapshot if result.succeeded else None

    def _cancelled(self, **kwargs):
        self._record("equipment_relief.cancelled")
        return EquipmentReliefResult(EquipmentReliefOutcome.CANCELLED, **kwargs)

    def _failed(self, error, **kwargs):
        self._record("equipment_relief.failed", error=error)
        return EquipmentReliefResult(EquipmentReliefOutcome.FAILED, error=error, **kwargs)

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


_TRANSMUTE_STATUSES = frozenset(
    {
        STATUS_COMBINE_TRANSMUTE_AVAILABLE,
        STATUS_COMBINE_ETHEREAL_AVAILABLE,
    }
)
_FUSE_STATUSES = frozenset({STATUS_COMBINE_FUSE_AVAILABLE})


def _is_clean_base(snapshot: RuntimeSnapshot, context: str) -> bool:
    return snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == context and not snapshot.state.overlays


def _is_stable_mode(snapshot: RuntimeSnapshot, mode: str) -> bool:
    overlays = set(snapshot.state.overlays)
    allowed_statuses = (
        _TRANSMUTE_STATUSES
        if mode == MODE_COMBINE_TRANSMUTE
        else _FUSE_STATUSES
    )
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_COMBINE
        and mode in overlays
        and overlays <= (allowed_statuses | {mode})
        and not _has_tappable_observation(snapshot)
    )


def _is_stable_combine(snapshot: RuntimeSnapshot) -> bool:
    return _is_stable_mode(snapshot, MODE_COMBINE_TRANSMUTE) or _is_stable_mode(snapshot, MODE_COMBINE_FUSE)


def _is_transmute_menu(snapshot: RuntimeSnapshot) -> bool:
    return _is_stable_mode(snapshot, MODE_COMBINE_TRANSMUTE)


def _is_fuse_menu(snapshot: RuntimeSnapshot) -> bool:
    return _is_stable_mode(snapshot, MODE_COMBINE_FUSE)


def _has_tappable_observation(snapshot: RuntimeSnapshot) -> bool:
    return bool(snapshot.observations.find(ACTIVITY_COMBINE_ANIMATION_TAPPABLE))


def _is_tappable_animation(snapshot: RuntimeSnapshot) -> bool:
    return snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == SCREEN_COMBINE and _has_tappable_observation(snapshot)


def _is_combine_animation_transient(snapshot: RuntimeSnapshot) -> bool:
    return snapshot.state.status is ResolutionStatus.UNKNOWN or (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_COMBINE
        and not any(name.startswith("popup.") for name in snapshot.state.overlays)
    )


def _is_combine_all_popup(snapshot: RuntimeSnapshot, mode: str) -> bool:
    overlays = set(snapshot.state.overlays)
    allowed_statuses = (
        _TRANSMUTE_STATUSES
        if mode == MODE_COMBINE_TRANSMUTE
        else _FUSE_STATUSES
    )
    return snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == SCREEN_COMBINE and mode in overlays and POPUP_COMBINE_ALL in overlays and overlays <= (allowed_statuses | {mode, POPUP_COMBINE_ALL})


def _is_awakened_panel(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == SCREEN_COMBINE and overlays == {MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_AWAKENED_TRANSMUTE}


def _is_random_part_panel(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == SCREEN_COMBINE and overlays == {MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_ETHEREAL_RANDOM_PART} and not _has_tappable_observation(snapshot)


def _is_ethereal_confirm(snapshot: RuntimeSnapshot) -> bool:
    return set(snapshot.state.overlays) == {MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE} and snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == SCREEN_COMBINE


def _is_ethereal_no_material(snapshot: RuntimeSnapshot) -> bool:
    return set(snapshot.state.overlays) == {MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_NO_MATERIAL} and snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context == SCREEN_COMBINE


def _known_incompatible(snapshot, expected, retryable_from) -> bool:
    if expected(snapshot) or retryable_from(snapshot):
        return False
    return snapshot.state.status in {ResolutionStatus.RESOLVED, ResolutionStatus.AMBIGUOUS}


__all__ = (
    "EquipmentInventoryRelief",
    "EquipmentReliefOutcome",
    "EquipmentReliefResult",
    "EquipmentReturnPlan",
    "EquipmentStrategyOutcome",
)
