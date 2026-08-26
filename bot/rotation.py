"""Transversal character rotation strategies, independent from gameplay flows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable, Protocol, runtime_checkable

from bot.action_executor import ActionExecutor
from bot.catalog import MENU_QUICK, SCREEN_CHARACTER_SELECT, SCREEN_LOBBY
from bot.character_select_scroll import (
    CharacterSelectScrollProfile,
    DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE,
)
from bot.event_log import EventSink
from bot.observed_scroll import (
    ObservedScroll,
    ObservedScrollOutcome,
    ScrollAttemptKind,
    ScrollAttemptMeasurement,
)
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    ConfirmCharacterSelection,
    OpenCharacterSelect,
    OpenQuickMenu,
    SelectLastVisibleCharacter,
)
from bot.state import ResolutionStatus


class RotationOutcome(str, Enum):
    SUCCESS = "success"
    ABORTED = "aborted"


@dataclass(frozen=True)
class RotationResult:
    outcome: RotationOutcome
    swipe_count: int = 0
    effective_swipe_count: int = 0
    bottom_confirmation_count: int = 0
    end_difference: float | None = None
    error: str | None = None
    scroll_attempts: tuple[ScrollAttemptMeasurement, ...] = ()
    scroll_attempt_kinds: tuple[ScrollAttemptKind, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.outcome is RotationOutcome.SUCCESS


@runtime_checkable
class RotationStrategy(Protocol):
    """Minimal strategy contract required by a future SessionRunner."""

    character_count: int

    def advance(self) -> RotationResult: ...


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class StandardRotation:
    """Advance once using Quick Menu and the MRU Character Select list."""

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink,
        *,
        character_count: int = 28,
        timeout: float = 6.0,
        precondition_settle_for: float = 0.25,
        selection_settle_for: float = 0.25,
        scroll_profile: CharacterSelectScrollProfile = (
            DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE
        ),
        observed_scroll: ObservedScroll | None = None,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute(intent, geometry)")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record(event)")
        self.character_count = _positive_integer(character_count, "character_count")
        self.timeout = _positive_duration(timeout, "timeout")
        self.precondition_settle_for = _non_negative_duration(
            precondition_settle_for, "precondition_settle_for"
        )
        self.selection_settle_for = _non_negative_duration(
            selection_settle_for, "selection_settle_for"
        )
        if not isinstance(scroll_profile, CharacterSelectScrollProfile):
            raise ValueError("scroll_profile must be CharacterSelectScrollProfile")
        if observed_scroll is None:
            observed_scroll = ObservedScroll(observer, actions)
        if not callable(getattr(observed_scroll, "scroll_to_edge", None)):
            raise ValueError("observed_scroll must provide scroll_to_edge()")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.scroll_profile = scroll_profile
        self.observed_scroll = observed_scroll

    def advance(self) -> RotationResult:
        """Perform exactly one Lobby -> different character -> Lobby change."""

        try:
            return self._advance()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._abort(f"{type(error).__name__}: {error}")

    def _advance(self) -> RotationResult:
        initial = self.observer.observe()
        if not _is_clean_base(initial, SCREEN_LOBBY):
            if not _can_wait_for_lobby_precondition(initial):
                return self._abort("precondition_lobby_failed")
            try:
                initial = self.observer.wait_until(
                    lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
                    after_sequence=initial.sequence,
                    timeout=self.timeout,
                    abort_if=_has_incompatible_lobby_precondition,
                    stable_for=self.precondition_settle_for,
                )
            except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
                return self._abort(f"precondition_lobby_failed: {error}")

        self.actions.execute(OpenQuickMenu(), initial.geometry)
        try:
            quick_menu = self.observer.wait_until(
                _has_quick_menu,
                after_sequence=initial.sequence,
                timeout=self.timeout,
                abort_if=_has_unexpected_quick_menu_state,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._abort(f"quick_menu_navigation_failed: {error}")

        self.actions.execute(OpenCharacterSelect(), quick_menu.geometry)
        try:
            character_select = self.observer.wait_until(
                lambda snapshot: _is_clean_base(
                    snapshot, SCREEN_CHARACTER_SELECT
                ),
                after_sequence=quick_menu.sequence,
                timeout=self.timeout,
                abort_if=_has_unexpected_character_select_transition,
                stable_for=self.scroll_profile.settle_for,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._abort(f"character_select_navigation_failed: {error}")

        scroll_result = self.observed_scroll.scroll_to_edge(
            character_select,
            detector=self.scroll_profile.detector(),
            config=self.scroll_profile.config(),
            is_compatible=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            abort_if=_has_incompatible_clean_screen,
        )
        scroll_attempts = scroll_result.attempts
        scroll_attempt_kinds = scroll_result.attempt_kinds
        swipe_count = len(scroll_attempts)
        effective_swipe_count = scroll_result.effective_gesture_count
        bottom_confirmation_count = scroll_result.confirmation_count
        end_difference = (
            scroll_attempts[-1].settled_difference if scroll_attempts else None
        )
        if not scroll_result.edge_reached:
            reason = (
                "scroll_limit_reached"
                if scroll_result.outcome is ObservedScrollOutcome.LIMIT_REACHED
                else f"character_select_scroll_failed: {scroll_result.error}"
            )
            return self._abort(
                reason,
                swipe_count=swipe_count,
                effective_swipe_count=effective_swipe_count,
                bottom_confirmation_count=bottom_confirmation_count,
                end_difference=end_difference,
                scroll_attempts=scroll_attempts,
                scroll_attempt_kinds=scroll_attempt_kinds,
            )
        character_select = scroll_result.final_snapshot

        self.actions.execute(
            SelectLastVisibleCharacter(), character_select.geometry
        )
        try:
            selected = self.observer.wait_until(
                lambda snapshot: _is_clean_base(
                    snapshot, SCREEN_CHARACTER_SELECT
                ),
                after_sequence=character_select.sequence,
                timeout=self.timeout,
                abort_if=_has_incompatible_clean_screen,
                stable_for=self.selection_settle_for,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._abort(
                f"character_selection_failed: {error}",
                swipe_count=swipe_count,
                effective_swipe_count=effective_swipe_count,
                bottom_confirmation_count=bottom_confirmation_count,
                end_difference=end_difference,
                scroll_attempts=tuple(scroll_attempts),
                scroll_attempt_kinds=tuple(scroll_attempt_kinds),
            )

        self.actions.execute(ConfirmCharacterSelection(), selected.geometry)
        try:
            self.observer.wait_until(
                lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
                after_sequence=selected.sequence,
                timeout=self.timeout,
                abort_if=_has_incompatible_clean_screen,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._abort(
                f"return_to_lobby_failed: {error}",
                swipe_count=swipe_count,
                effective_swipe_count=effective_swipe_count,
                bottom_confirmation_count=bottom_confirmation_count,
                end_difference=end_difference,
                scroll_attempts=tuple(scroll_attempts),
                scroll_attempt_kinds=tuple(scroll_attempt_kinds),
            )

        return RotationResult(
            outcome=RotationOutcome.SUCCESS,
            swipe_count=swipe_count,
            effective_swipe_count=effective_swipe_count,
            bottom_confirmation_count=bottom_confirmation_count,
            end_difference=end_difference,
            scroll_attempts=tuple(scroll_attempts),
            scroll_attempt_kinds=tuple(scroll_attempt_kinds),
        )

    def _abort(
        self,
        reason: str,
        *,
        swipe_count: int = 0,
        effective_swipe_count: int = 0,
        bottom_confirmation_count: int = 0,
        end_difference: float | None = None,
        scroll_attempts: tuple[ScrollAttemptMeasurement, ...] = (),
        scroll_attempt_kinds: tuple[ScrollAttemptKind, ...] = (),
    ) -> RotationResult:
        try:
            self.events.record("rotation.standard.unexpected_state")
        except Exception:
            pass
        return RotationResult(
            outcome=RotationOutcome.ABORTED,
            swipe_count=swipe_count,
            effective_swipe_count=effective_swipe_count,
            bottom_confirmation_count=bottom_confirmation_count,
            end_difference=end_difference,
            error=reason,
            scroll_attempts=scroll_attempts,
            scroll_attempt_kinds=scroll_attempt_kinds,
        )


def _is_clean_base(snapshot: RuntimeSnapshot, base: str) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == base
        and not state.overlays
    )


def _has_quick_menu(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        set(state.overlays) == {MENU_QUICK}
        and (
            state.status is ResolutionStatus.UNKNOWN
            or (
                state.status is ResolutionStatus.RESOLVED
                and state.base_context == SCREEN_LOBBY
            )
        )
    )


def _can_wait_for_lobby_precondition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return state.status is ResolutionStatus.UNKNOWN and not state.overlays


def _has_incompatible_lobby_precondition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_LOBBY
        )
    )


def _has_unexpected_quick_menu_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(set(state.overlays) - {MENU_QUICK})
    )


def _has_unexpected_character_select_transition(
    snapshot: RuntimeSnapshot,
) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(set(state.overlays) - {MENU_QUICK})
    )


def _has_incompatible_clean_screen(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or bool(snapshot.state.overlays)
    )


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


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
    "RotationOutcome",
    "RotationResult",
    "RotationStrategy",
    "StandardRotation",
)
