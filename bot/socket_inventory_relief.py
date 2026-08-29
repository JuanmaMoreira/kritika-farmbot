"""Reusable bounded support operation for safe Socket inventory relief."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from bot.catalog import (
    LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    POPUP_SOCKET_ENHANCE_ALL,
    POPUP_SOCKET_NO_MATERIAL,
    POPUP_SOCKET_SELL,
    SCREEN_SOCKET,
)
from bot.event_log import EventSink
from bot.observations import validate_semantic_name
from bot.perception.socket import (
    SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION,
    SOCKET_INCOMPATIBLE_OPAL_OBSERVATION,
)
from bot.runtime_facts import FactReadStatus
from bot.runtime_observer import (
    RuntimeSnapshot,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    AcknowledgeSocketNoMaterial,
    CancelSocketSell,
    CloseSocketEnhanceAll,
    OpenSocketEnhanceAll,
    OpenSocketEquipmentHome,
    OpenSocketSell,
    SelectSocketEnhanceGold,
    SelectSocketOpalSlot,
    SellSocketInBulk,
    TapSocketEnhanceAnimation,
)
from bot.state import ResolutionStatus
from bot.tap_through_animation import (
    TapThroughAnimation,
    TapThroughOutcome,
    TapThroughPolicy,
)
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


class SocketReliefOutcome(str, Enum):
    RELIEVED = "relieved"
    NO_RELIEF_AVAILABLE = "no_relief_available"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SocketStrategyOutcome(str, Enum):
    NOT_RUN = "not_run"
    EFFECT = "effect"
    NO_EFFECT = "no_effect"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SocketReturnPlan:
    action: object
    expected_return_state: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_return_state",
            validate_semantic_name(self.expected_return_state),
        )


@dataclass(frozen=True)
class SocketReliefResult:
    outcome: SocketReliefOutcome
    enhance: SocketStrategyOutcome = SocketStrategyOutcome.NOT_RUN
    sell: SocketStrategyOutcome = SocketStrategyOutcome.NOT_RUN
    animation_taps: int = 0
    final_snapshot: RuntimeSnapshot | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome in {
            SocketReliefOutcome.RELIEVED,
            SocketReliefOutcome.NO_RELIEF_AVAILABLE,
        }


class _FactReader(Protocol):
    def read_socket_sell_item_level(self, **kwargs): ...


class SocketInventoryRelief:
    """Try Enhance then one safe bulk sale and restore a declared state."""

    def __init__(
        self,
        observer,
        actions,
        facts: _FactReader,
        events: EventSink,
        *,
        verified_transition: VerifiedTransition | None = None,
        tap_through: TapThroughAnimation | None = None,
        transition_timeout: float = 6.0,
        fact_timeout: float = 8.0,
        stable_for: float = 0.25,
        animation_policy: TapThroughPolicy = TapThroughPolicy(),
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(facts, "read_socket_sell_item_level", None)):
            raise ValueError("facts must provide read_socket_sell_item_level()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if transition_timeout <= 0 or fact_timeout <= 0 or stable_for < 0:
            raise ValueError("timeouts must be positive and stability non-negative")
        if not isinstance(animation_policy, TapThroughPolicy):
            raise ValueError("animation_policy must be TapThroughPolicy")
        self.observer = observer
        self.actions = actions
        self.facts = facts
        self.events = events
        self.stable_for = float(stable_for)
        self.fact_timeout = float(fact_timeout)
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
        return_plan: SocketReturnPlan,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> SocketReliefResult:
        if not isinstance(return_plan, SocketReturnPlan):
            raise ValueError("return_plan must be a SocketReturnPlan")
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
        if not _is_clean_socket(current):
            return self._failed(
                "socket_relief_precondition_rejected",
                final_snapshot=current,
            )
        self._record("socket_relief.started", sequence=current.sequence)

        enhance, current, animation_taps = self._enhance(
            current, cancel_requested
        )
        if enhance is SocketStrategyOutcome.CANCELLED:
            return self._cancelled(
                enhance=enhance,
                animation_taps=animation_taps,
                final_snapshot=current,
            )
        if enhance is SocketStrategyOutcome.FAILED:
            return self._failed(
                "socket_enhance_failed",
                enhance=enhance,
                animation_taps=animation_taps,
                final_snapshot=current,
            )

        sell = SocketStrategyOutcome.NOT_RUN
        relief_effect = enhance is SocketStrategyOutcome.EFFECT
        if not relief_effect:
            sell, current = self._sell(current, cancel_requested)
            if sell is SocketStrategyOutcome.CANCELLED:
                return self._cancelled(
                    enhance=enhance,
                    sell=sell,
                    animation_taps=animation_taps,
                    final_snapshot=current,
                )
            if sell is SocketStrategyOutcome.FAILED:
                return self._failed(
                    "socket_sell_failed",
                    enhance=enhance,
                    sell=sell,
                    animation_taps=animation_taps,
                    final_snapshot=current,
                )
            relief_effect = sell is SocketStrategyOutcome.EFFECT

        if cancel_requested():
            return self._cancelled(
                enhance=enhance,
                sell=sell,
                animation_taps=animation_taps,
                final_snapshot=current,
            )
        returned = self._transition(
            "socket_relief.return",
            return_plan.action,
            current,
            expected=lambda item: _is_clean_base(
                item, return_plan.expected_return_state
            ),
            precondition=_is_clean_socket,
        )
        if returned is None:
            return self._failed(
                "socket_return_failed",
                enhance=enhance,
                sell=sell,
                animation_taps=animation_taps,
                final_snapshot=current,
            )
        outcome = (
            SocketReliefOutcome.RELIEVED
            if relief_effect
            else SocketReliefOutcome.NO_RELIEF_AVAILABLE
        )
        self._record(
            "socket_relief.finished",
            outcome=outcome.value,
            enhance=enhance.value,
            sell=sell.value,
            animation_taps=animation_taps,
            expected_return_state=return_plan.expected_return_state,
        )
        return SocketReliefResult(
            outcome,
            enhance,
            sell,
            animation_taps,
            returned,
        )

    def _enhance(self, current, cancel_requested):
        modal = self._transition(
            "socket_relief.open_enhance_all",
            OpenSocketEnhanceAll(),
            current,
            expected=_is_enhance_modal,
            precondition=_is_clean_socket,
        )
        if modal is None:
            return SocketStrategyOutcome.FAILED, current, 0
        if cancel_requested():
            return SocketStrategyOutcome.CANCELLED, modal, 0
        outcome = self._transition(
            "socket_relief.enhance_gold",
            SelectSocketEnhanceGold(),
            modal,
            expected=lambda item: _is_tappable_animation(item)
            or _is_no_material(item),
            precondition=_is_enhance_modal,
            policy=self.single_action_policy,
        )
        if outcome is None:
            self._record("socket_relief.enhance_failed", reason="outcome_timeout")
            return SocketStrategyOutcome.FAILED, modal, 0
        if _is_tappable_animation(outcome):
            self._record("socket_relief.enhance_effect")
            tapped = self.tap_through.run(
                outcome,
                action=TapSocketEnhanceAnimation(),
                expected=_is_clean_socket,
                tappable=_is_tappable_animation,
                transient=lambda item: item.state.status is ResolutionStatus.UNKNOWN,
                cancel_requested=cancel_requested,
                policy=self.animation_policy,
            )
            if tapped.outcome is TapThroughOutcome.CANCELLED:
                return (
                    SocketStrategyOutcome.CANCELLED,
                    tapped.final_snapshot,
                    tapped.tap_count,
                )
            if not tapped.succeeded:
                self._record(
                    "socket_relief.enhance_failed",
                    reason=tapped.outcome.value,
                    taps=tapped.tap_count,
                )
                return (
                    SocketStrategyOutcome.FAILED,
                    tapped.final_snapshot,
                    tapped.tap_count,
                )
            return (
                SocketStrategyOutcome.EFFECT,
                tapped.final_snapshot,
                tapped.tap_count,
            )

        self._record("socket_relief.enhance_no_effect")
        modal = self._transition(
            "socket_relief.ack_no_material",
            AcknowledgeSocketNoMaterial(),
            outcome,
            expected=_is_enhance_modal,
            precondition=_is_no_material,
        )
        if modal is None:
            return SocketStrategyOutcome.FAILED, outcome, 0
        current = self._transition(
            "socket_relief.close_enhance_all",
            CloseSocketEnhanceAll(),
            modal,
            expected=_is_clean_socket,
            precondition=_is_enhance_modal,
        )
        if current is None:
            return SocketStrategyOutcome.FAILED, modal, 0
        return SocketStrategyOutcome.NO_EFFECT, current, 0

    def _sell(self, current, cancel_requested):
        equipment = self._transition(
            "socket_relief.open_equipment_home",
            OpenSocketEquipmentHome(),
            current,
            expected=_is_equipment_home,
            precondition=_is_clean_socket,
        )
        if equipment is None:
            return SocketStrategyOutcome.FAILED, current
        candidates = _incompatible_slots(equipment)
        if not candidates:
            self._record("socket_relief.sell_no_candidate")
            return SocketStrategyOutcome.NO_EFFECT, equipment

        for slot in candidates:
            if cancel_requested():
                return SocketStrategyOutcome.CANCELLED, equipment
            if slot not in _incompatible_slots(equipment):
                continue
            self._record("socket_relief.sell_candidate", slot=slot)
            try:
                self.actions.execute(SelectSocketOpalSlot(slot), equipment.geometry)
                selected = self.observer.wait_until(
                    lambda item: _is_equipment_home(item)
                    and slot in _incompatible_slots(item),
                    after_sequence=equipment.sequence,
                    timeout=self.normal_policy.normal_timeout,
                    stable_for=self.stable_for,
                    cancel_requested=cancel_requested,
                )
            except RuntimeWaitCancelled:
                return SocketStrategyOutcome.CANCELLED, equipment
            except RuntimeWaitTimeout:
                return SocketStrategyOutcome.FAILED, equipment
            popup = self._transition(
                "socket_relief.open_sell",
                OpenSocketSell(),
                selected,
                expected=_is_sell_popup,
                precondition=lambda item, selected_slot=slot: (
                    _is_equipment_home(item)
                    and selected_slot in _incompatible_slots(item)
                ),
            )
            if popup is None:
                return SocketStrategyOutcome.FAILED, selected
            read = self.facts.read_socket_sell_item_level(
                after_sequence=popup.sequence,
                timeout=self.fact_timeout,
                cancel_requested=cancel_requested,
            )
            if read.status is FactReadStatus.CANCELLED:
                cleaned = self._cancel_sell(popup)
                return SocketStrategyOutcome.CANCELLED, cleaned or popup
            if read.status is FactReadStatus.CONFIRMED:
                fact = read.fact
                assert fact is not None
                level = fact.value
                self._record(
                    "socket_relief.sell_level_confirmed",
                    slot=slot,
                    level=level,
                    confidence=fact.confidence,
                )
            else:
                level = None
                self._record(
                    "socket_relief.sell_level_rejected",
                    slot=slot,
                    status=read.status.value,
                    detail=read.detail,
                )
            if level != 0:
                equipment = self._cancel_sell(popup)
                if equipment is None:
                    return SocketStrategyOutcome.FAILED, popup
                continue

            sold = self._transition(
                "socket_relief.sell_bulk",
                SellSocketInBulk(),
                popup,
                expected=lambda item, sold_slot=slot: (
                    _is_equipment_home(item)
                    and sold_slot not in _incompatible_slots(item)
                ),
                precondition=_is_sell_popup,
                tolerated=_is_clean_socket,
                policy=self.single_action_policy,
            )
            if sold is None:
                self._record(
                    "socket_relief.sell_failed",
                    slot=slot,
                    reason="postcondition_unverified",
                )
                return SocketStrategyOutcome.FAILED, popup
            self._record("socket_relief.sell_bulk_verified", slot=slot)
            return SocketStrategyOutcome.EFFECT, sold

        return SocketStrategyOutcome.NO_EFFECT, equipment

    def _cancel_sell(self, popup):
        return self._transition(
            "socket_relief.cancel_sell",
            CancelSocketSell(),
            popup,
            expected=_is_equipment_home,
            precondition=_is_sell_popup,
        )

    def _transition(
        self,
        name,
        action,
        before,
        *,
        expected,
        precondition,
        tolerated=lambda item: False,
        policy=None,
    ):
        selected_policy = policy or self.normal_policy
        result = self.transition.execute(
            name,
            action,
            before,
            expected=expected,
            precondition=precondition,
            retryable_from=precondition,
            abort_if=lambda item: _known_incompatible(
                item, expected, precondition
            )
            and not tolerated(item),
            stable_for=self.stable_for,
            policy=selected_policy,
        )
        self._record(
            "socket_relief.transition",
            name=name,
            outcome=result.outcome.value,
            attempts=result.attempt_count,
        )
        return result.final_snapshot if result.succeeded else None

    def _cancelled(self, **kwargs):
        self._record("socket_relief.cancelled")
        return SocketReliefResult(SocketReliefOutcome.CANCELLED, **kwargs)

    def _failed(self, error, **kwargs):
        self._record("socket_relief.failed", error=error)
        return SocketReliefResult(
            SocketReliefOutcome.FAILED, error=error, **kwargs
        )

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _is_clean_base(snapshot: RuntimeSnapshot, context: str) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == context
        and not snapshot.state.overlays
    )


def _is_clean_socket(snapshot: RuntimeSnapshot) -> bool:
    return _is_clean_base(snapshot, SCREEN_SOCKET)


def _is_enhance_modal(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_SOCKET
        and set(snapshot.state.overlays) == {POPUP_SOCKET_ENHANCE_ALL}
    )


def _is_no_material(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_SOCKET
        and set(snapshot.state.overlays)
        == {POPUP_SOCKET_ENHANCE_ALL, POPUP_SOCKET_NO_MATERIAL}
    )


def _is_sell_popup(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_SOCKET
        and set(snapshot.state.overlays) == {POPUP_SOCKET_SELL}
    )


def _is_equipment_home(snapshot: RuntimeSnapshot) -> bool:
    return _is_clean_socket(snapshot) and bool(
        snapshot.observations.find(LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE)
    )


def _is_tappable_animation(snapshot: RuntimeSnapshot) -> bool:
    return bool(
        snapshot.observations.find(
            SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION
        )
    )


def _incompatible_slots(snapshot: RuntimeSnapshot) -> tuple[int, ...]:
    values = []
    for observation in snapshot.observations.find(
        SOCKET_INCOMPATIBLE_OPAL_OBSERVATION
    ):
        value = observation.value
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if 0 <= value < 16:
            values.append(value)
    return tuple(sorted(set(values)))


def _known_incompatible(snapshot, expected, retryable_from) -> bool:
    if expected(snapshot) or retryable_from(snapshot):
        return False
    return snapshot.state.status in {
        ResolutionStatus.RESOLVED,
        ResolutionStatus.AMBIGUOUS,
    }


__all__ = (
    "SocketInventoryRelief",
    "SocketReliefOutcome",
    "SocketReliefResult",
    "SocketReturnPlan",
    "SocketStrategyOutcome",
)
