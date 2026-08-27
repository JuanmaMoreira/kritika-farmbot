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
from bot.character_selection import (
    CharacterSelectionDetector,
    CharacterSelectionState,
    DEFAULT_CHARACTER_SELECTION_DETECTOR,
)
from bot.config import DEFAULT_CHARACTER_COUNT
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
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionPolicy,
    VerifiedTransitionResult,
)


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
    transitions: tuple["RotationTransitionTrace", ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.outcome is RotationOutcome.SUCCESS


@dataclass(frozen=True)
class RotationTransitionTrace:
    name: str
    outcome: str
    attempt_count: int
    grace_wait_count: int
    effect_state: str | None = None
    effect_score: float | None = None


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
        character_count: int = DEFAULT_CHARACTER_COUNT,
        timeout: float = 6.0,
        precondition_settle_for: float = 0.25,
        selection_settle_for: float = 0.25,
        selection_normal_timeout: float = 1.0,
        selection_grace_timeout: float = 0.75,
        selection_max_attempts: int = 2,
        transition_grace_timeout: float = 2.0,
        transition_max_attempts: int = 2,
        scroll_profile: CharacterSelectScrollProfile = (
            DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE
        ),
        observed_scroll: ObservedScroll | None = None,
        verified_transition: VerifiedTransition | None = None,
        selection_detector: CharacterSelectionDetector = (
            DEFAULT_CHARACTER_SELECTION_DETECTOR
        ),
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
        self.transition_policy = VerifiedTransitionPolicy(
            normal_timeout=self.timeout,
            grace_timeout=transition_grace_timeout,
            max_attempts=transition_max_attempts,
        )
        self.selection_policy = VerifiedTransitionPolicy(
            normal_timeout=selection_normal_timeout,
            grace_timeout=selection_grace_timeout,
            max_attempts=selection_max_attempts,
        )
        if not isinstance(selection_detector, CharacterSelectionDetector):
            raise ValueError("selection_detector must be CharacterSelectionDetector")
        if not isinstance(scroll_profile, CharacterSelectScrollProfile):
            raise ValueError("scroll_profile must be CharacterSelectScrollProfile")
        if observed_scroll is None:
            observed_scroll = ObservedScroll(observer, actions)
        if not callable(getattr(observed_scroll, "scroll_to_edge", None)):
            raise ValueError("observed_scroll must provide scroll_to_edge()")
        if verified_transition is None:
            verified_transition = VerifiedTransition(observer, actions)
        if not callable(getattr(verified_transition, "execute", None)):
            raise ValueError("verified_transition must provide execute()")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.scroll_profile = scroll_profile
        self.observed_scroll = observed_scroll
        self.verified_transition = verified_transition
        self.selection_detector = selection_detector

    def advance(self) -> RotationResult:
        """Perform exactly one Lobby -> different character -> Lobby change."""

        try:
            return self._advance()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._abort(f"{type(error).__name__}: {error}")

    def _advance(self) -> RotationResult:
        transitions: list[RotationTransitionTrace] = []
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

        quick_menu_result = self.verified_transition.execute(
            "rotation.open_quick_menu",
            OpenQuickMenu(),
            initial,
            expected=_has_quick_menu,
            precondition=lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_LOBBY
            ),
            abort_if=_has_unexpected_quick_menu_state,
            policy=self.transition_policy,
        )
        transitions.append(_transition_trace(quick_menu_result))
        if not quick_menu_result.succeeded:
            return self._abort(
                "quick_menu_navigation_failed: "
                f"{quick_menu_result.outcome.value}: {quick_menu_result.error}",
                transitions=tuple(transitions),
            )
        quick_menu = quick_menu_result.final_snapshot

        character_select_result = self.verified_transition.execute(
            "rotation.open_character_select",
            OpenCharacterSelect(),
            quick_menu,
            expected=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            precondition=_has_quick_menu,
            retryable_from=_has_quick_menu,
            abort_if=_has_unexpected_character_select_transition,
            stable_for=self.scroll_profile.settle_for,
            policy=self.transition_policy,
        )
        transitions.append(_transition_trace(character_select_result))
        if not character_select_result.succeeded:
            return self._abort(
                "character_select_navigation_failed: "
                f"{character_select_result.outcome.value}: "
                f"{character_select_result.error}",
                transitions=tuple(transitions),
            )
        character_select = character_select_result.final_snapshot

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
                transitions=tuple(transitions),
            )
        character_select = scroll_result.final_snapshot

        selection_result = self.verified_transition.execute(
            "rotation.select_last_visible_character",
            SelectLastVisibleCharacter(),
            character_select,
            expected=self._is_target_card_selected,
            precondition=self._is_target_card_unselected,
            retryable_from=self._is_target_card_unselected,
            abort_if=_has_unexpected_character_selection_state,
            stable_for=self.selection_settle_for,
            policy=self.selection_policy,
        )
        selection_reading = self.selection_detector.measure(
            selection_result.final_snapshot.frame
        )
        transitions.append(
            _transition_trace(
                selection_result,
                effect_state=selection_reading.state.value,
                effect_score=selection_reading.yellow_border_ratio,
            )
        )
        if not selection_result.succeeded:
            return self._abort(
                "character_selection_failed: "
                f"{selection_result.outcome.value}: "
                f"{selection_result.error}",
                swipe_count=swipe_count,
                effective_swipe_count=effective_swipe_count,
                bottom_confirmation_count=bottom_confirmation_count,
                end_difference=end_difference,
                scroll_attempts=tuple(scroll_attempts),
                scroll_attempt_kinds=tuple(scroll_attempt_kinds),
                transitions=tuple(transitions),
            )
        selected = selection_result.final_snapshot

        confirmation_result = self.verified_transition.execute(
            "rotation.confirm_character_selection",
            ConfirmCharacterSelection(),
            selected,
            expected=lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
            precondition=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            abort_if=_has_incompatible_clean_screen,
            policy=self.transition_policy,
        )
        transitions.append(_transition_trace(confirmation_result))
        if not confirmation_result.succeeded:
            return self._abort(
                "return_to_lobby_failed: "
                f"{confirmation_result.outcome.value}: "
                f"{confirmation_result.error}",
                swipe_count=swipe_count,
                effective_swipe_count=effective_swipe_count,
                bottom_confirmation_count=bottom_confirmation_count,
                end_difference=end_difference,
                scroll_attempts=tuple(scroll_attempts),
                scroll_attempt_kinds=tuple(scroll_attempt_kinds),
                transitions=tuple(transitions),
            )

        return RotationResult(
            outcome=RotationOutcome.SUCCESS,
            swipe_count=swipe_count,
            effective_swipe_count=effective_swipe_count,
            bottom_confirmation_count=bottom_confirmation_count,
            end_difference=end_difference,
            scroll_attempts=tuple(scroll_attempts),
            scroll_attempt_kinds=tuple(scroll_attempt_kinds),
            transitions=tuple(transitions),
        )

    def _is_target_card_selected(self, snapshot: RuntimeSnapshot) -> bool:
        return (
            _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)
            and self.selection_detector.measure(snapshot.frame).state
            is CharacterSelectionState.SELECTED
        )

    def _is_target_card_unselected(self, snapshot: RuntimeSnapshot) -> bool:
        return (
            _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)
            and self.selection_detector.measure(snapshot.frame).state
            is CharacterSelectionState.UNSELECTED
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
        transitions: tuple[RotationTransitionTrace, ...] = (),
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
            transitions=transitions,
        )


def _transition_trace(
    result: VerifiedTransitionResult,
    *,
    effect_state: str | None = None,
    effect_score: float | None = None,
) -> RotationTransitionTrace:
    return RotationTransitionTrace(
        name=result.name,
        outcome=result.outcome.value,
        attempt_count=result.attempt_count,
        grace_wait_count=result.grace_wait_count,
        effect_state=effect_state,
        effect_score=effect_score,
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


def _has_unexpected_character_selection_state(
    snapshot: RuntimeSnapshot,
) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_CHARACTER_SELECT
        )
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
    "RotationTransitionTrace",
    "StandardRotation",
)
