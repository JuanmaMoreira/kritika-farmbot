"""Transversal character rotation strategies, independent from gameplay flows."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from numbers import Integral, Real
from typing import Callable, Protocol, runtime_checkable

from bot.action_executor import ActionExecutor
from bot.catalog import (
    MENU_QUICK,
    SCREEN_CHARACTER_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
)
from bot.component_contracts import (
    ComponentContract,
    ComponentRequirement,
    QUICK_MENU_ACCESS_REQUIREMENT,
)
from bot.character_select_layout import (
    predecessor_center,
    tile_box,
)
from bot.character_select_scroll import (
    CharacterSelectScrollProfile,
    DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE,
)
from bot.character_selection import (
    CharacterSelectionDetector,
    CharacterSelectionState,
    DEFAULT_CHARACTER_SELECTION_DETECTOR,
)
from bot.create_character_sentinel import (
    DEFAULT_SENTINEL_DETECTOR,
    CreateCharacterSentinelDetector,
)
from bot.config import DEFAULT_CHARACTER_COUNT
from bot.event_log import EventSink
from bot.failure_cause import FailureCause
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.quick_menu import (
    DEFAULT_QUICK_MENU_POLICY,
    QuickMenuPolicy,
    open_character_select_action,
    quick_menu_accessible,
    QuickMenuHandoff, quick_menu_matches_origin,
)
from bot.semantic_actions import (
    ConfirmCharacterSelection,
    OpenQuickMenu,
    SelectCharacterCard,
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
    error: str | None = None
    transitions: tuple["RotationTransitionTrace", ...] = ()
    failure: FailureCause | None = field(default=None, kw_only=True)

    def __post_init__(self):
        if self.error is not None and self.failure is None:
            object.__setattr__(self, "failure", FailureCause.from_error(self.error, kind="rotation_failure"))

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
    contract: ComponentContract

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
    """Advance once by locating the Create Character (+) sentinel tile."""

    contract = ComponentContract(
        precondition=QUICK_MENU_ACCESS_REQUIREMENT,
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
        ),
    )

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
        max_swipes: int = 6,
        coarse_swipes: int = 2,
        scroll_profile: CharacterSelectScrollProfile = (
            DEFAULT_CHARACTER_SELECT_SCROLL_PROFILE
        ),
        sentinel_detector: CreateCharacterSentinelDetector = (
            DEFAULT_SENTINEL_DETECTOR
        ),
        verified_transition: VerifiedTransition | None = None,
        selection_transition: VerifiedTransition | None = None,
        confirmation_transition: VerifiedTransition | None = None,
        post_swipe_observer: RuntimeObserver | None = None,
        quick_menu_policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
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
        self.max_swipes = _positive_integer(max_swipes, "max_swipes")
        self.coarse_swipes = _non_negative_integer(
            coarse_swipes, "coarse_swipes"
        )
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
        if not isinstance(quick_menu_policy, QuickMenuPolicy):
            raise ValueError("quick_menu_policy must be QuickMenuPolicy")
        if not isinstance(scroll_profile, CharacterSelectScrollProfile):
            raise ValueError("scroll_profile must be CharacterSelectScrollProfile")
        if not callable(getattr(sentinel_detector, "measure", None)):
            raise ValueError("sentinel_detector must provide measure(frame)")
        if verified_transition is None:
            verified_transition = VerifiedTransition(observer, actions, events)
        if not callable(getattr(verified_transition, "execute", None)):
            raise ValueError("verified_transition must provide execute()")
        if selection_transition is None:
            selection_transition = verified_transition
        if not callable(getattr(selection_transition, "execute", None)):
            raise ValueError("selection_transition must provide execute()")
        if confirmation_transition is None:
            confirmation_transition = verified_transition
        if not callable(getattr(confirmation_transition, "execute", None)):
            raise ValueError("confirmation_transition must provide execute()")
        if post_swipe_observer is None:
            post_swipe_observer = observer
        if not callable(getattr(post_swipe_observer, "wait_until", None)):
            raise ValueError("post_swipe_observer must provide wait_until()")
        self.observer: _Observer = observer
        self.post_swipe_observer: _Observer = post_swipe_observer
        self.actions = actions
        self.events = events
        self.scroll_profile = scroll_profile
        self.sentinel_detector = sentinel_detector
        self.verified_transition = verified_transition
        self.selection_transition = selection_transition
        self.confirmation_transition = confirmation_transition
        self.quick_menu_policy = quick_menu_policy
        self.selection_detector = selection_detector

    def advance(self) -> RotationResult:
        """Advance from a declared Quick Menu-capable context to Lobby."""

        try:
            return self._advance()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._abort(f"{type(error).__name__}: {error}")

    def _advance(self) -> RotationResult:
        transitions: list[RotationTransitionTrace] = []
        capable = lambda snapshot: _is_clean_quick_menu_capable(
            snapshot, self.quick_menu_policy
        )
        initial = self.observer.observe()
        if not capable(initial):
            if not _can_wait_for_quick_menu_precondition(initial):
                return self._abort("precondition_quick_menu_accessible_failed")
            try:
                initial = self.observer.wait_until(
                    capable,
                    after_sequence=initial.sequence,
                    timeout=self.timeout,
                    abort_if=lambda snapshot: (
                        _has_incompatible_quick_menu_precondition(
                            snapshot, self.quick_menu_policy
                        )
                    ),
                    stable_for=self.precondition_settle_for,
                )
            except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
                return self._abort(
                    f"precondition_quick_menu_accessible_failed: {error}"
                )

        origin = initial.state.base_context
        same_origin = lambda snapshot: (
            snapshot.state.base_context == origin and capable(snapshot)
        )
        menu_from_origin = lambda snapshot: quick_menu_matches_origin(
            snapshot, origin
        )
        quick_menu_result = self.verified_transition.execute(
            "rotation.open_quick_menu",
            OpenQuickMenu(),
            initial,
            expected=menu_from_origin,
            precondition=same_origin,
            retryable_from=same_origin,
            abort_if=lambda snapshot: (
                snapshot.state.status is ResolutionStatus.RESOLVED
                and snapshot.state.base_context != origin
            ) or _has_unexpected_quick_menu_state(
                snapshot, self.quick_menu_policy
            ),
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
        handoff = QuickMenuHandoff.from_open_result(
            quick_menu_result, same_origin, policy=self.quick_menu_policy,
        )
        if handoff is None:
            return self._abort(
                "quick_menu_origin_handoff_invalid",
                transitions=tuple(transitions),
            )
        character_select_result = self.verified_transition.execute(
            "rotation.open_character_select",
            open_character_select_action(
                handoff.origin, policy=self.quick_menu_policy,
            ),
            quick_menu,
            expected=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            precondition=handoff.allows,
            retryable_from=handoff.allows,
            on_recovery=handoff.invalidate,
            abort_if=lambda snapshot: (
                handoff.observe(
                    snapshot, lambda item: _is_clean_base(
                        item, SCREEN_CHARACTER_SELECT
                    )
                )
                or _has_unexpected_character_select_transition(
                    snapshot, self.quick_menu_policy
                )
            ),
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

        swipe_count = 0
        while True:
            if _is_clean_base(character_select, SCREEN_CHARACTER_SELECT):
                reading = self.sentinel_detector.measure(character_select.frame)
                if reading.confirmed and reading.location is not None:
                    break
                if swipe_count >= self.max_swipes:
                    return self._abort(
                        "sentinel_not_found_after_max_swipes",
                        swipe_count=swipe_count,
                        transitions=tuple(transitions),
                    )
                # Sentinel absent on a clean screen: coarse strong swipes
                # first, then short controlled ones to finish positioning a
                # partial card. An ineffective swipe proves nothing about the
                # list end; only the swipe budget bounds this search.
                if swipe_count < self.coarse_swipes:
                    gesture = self.scroll_profile.progress_swipe
                else:
                    gesture = self.scroll_profile.fine_swipe
                self.actions.execute(gesture, character_select.geometry)
                swipe_count += 1
                try:
                    character_select = self.post_swipe_observer.wait_until(
                        lambda snapshot: _is_clean_base(
                            snapshot, SCREEN_CHARACTER_SELECT
                        ),
                        after_sequence=character_select.sequence,
                        timeout=self.timeout,
                        abort_if=_is_contradictory_character_select,
                        stable_for=self.scroll_profile.settle_for,
                    )
                except RuntimeWaitAborted as error:
                    return self._abort(
                        f"character_select_unexpected_state: {error}",
                        swipe_count=swipe_count,
                        transitions=tuple(transitions),
                    )
                except RuntimeWaitTimeout as error:
                    return self._abort(
                        f"character_select_settle_failed: {error}",
                        swipe_count=swipe_count,
                        transitions=tuple(transitions),
                    )
                continue
            if _is_contradictory_character_select(character_select):
                return self._abort(
                    "character_select_unexpected_state",
                    swipe_count=swipe_count,
                    transitions=tuple(transitions),
                )
            # UNKNOWN/AMBIGUOUS authorizes no input: bounded reobservation.
            try:
                character_select = self.observer.wait_until(
                    lambda snapshot: _is_clean_base(
                        snapshot, SCREEN_CHARACTER_SELECT
                    ),
                    after_sequence=character_select.sequence,
                    timeout=self.timeout,
                    abort_if=_is_contradictory_character_select,
                )
            except RuntimeWaitAborted as error:
                return self._abort(
                    f"character_select_unexpected_state: {error}",
                    swipe_count=swipe_count,
                    transitions=tuple(transitions),
                )
            except RuntimeWaitTimeout as error:
                return self._abort(
                    f"character_select_unresolved: {error}",
                    swipe_count=swipe_count,
                    transitions=tuple(transitions),
                )

        try:
            target = predecessor_center(reading.location)
            target_detector = replace_selection_region(
                self.selection_detector, tile_box(target)
            )
        except ValueError as error:
            return self._abort(
                f"invalid_sentinel_location: {error}",
                swipe_count=swipe_count,
                transitions=tuple(transitions),
            )

        selection_result = self.selection_transition.execute(
            "rotation.select_predecessor_character",
            SelectCharacterCard(target),
            character_select,
            expected=lambda snapshot: _is_selected(snapshot, target_detector),
            # The tap is authorized by clean Character Select plus the already
            # confirmed sentinel and valid geometry behind `target`. The
            # pre-tap selection state is never a gate: an already-selected or
            # uncertain card is safe to tap, and only the post-tap SELECTED
            # reading declares success.
            precondition=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_CHARACTER_SELECT
            ),
            abort_if=_has_unexpected_character_selection_state,
            stable_for=self.selection_settle_for,
            policy=self.selection_policy,
        )
        selection_reading = target_detector.measure(
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
                "predecessor_selection_failed: "
                f"{selection_result.outcome.value}: "
                f"{selection_result.error}",
                swipe_count=swipe_count,
                transitions=tuple(transitions),
            )
        selected = selection_result.final_snapshot

        confirmation_result = self.confirmation_transition.execute(
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
                transitions=tuple(transitions),
            )

        return RotationResult(
            outcome=RotationOutcome.SUCCESS,
            swipe_count=swipe_count,
            transitions=tuple(transitions),
        )

    def _abort(
        self,
        reason: str,
        *,
        swipe_count: int = 0,
        transitions: tuple[RotationTransitionTrace, ...] = (),
    ) -> RotationResult:
        try:
            self.events.record("rotation.standard.unexpected_state")
        except Exception:
            pass
        return RotationResult(
            outcome=RotationOutcome.ABORTED,
            swipe_count=swipe_count,
            error=reason,
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


def _is_contradictory_character_select(snapshot: RuntimeSnapshot) -> bool:
    """RESOLVED snapshots that rule out continuing the sentinel search."""

    state = snapshot.state
    return state.status is ResolutionStatus.RESOLVED and (
        state.base_context != SCREEN_CHARACTER_SELECT or bool(state.overlays)
    )


def _is_selected(
    snapshot: RuntimeSnapshot, detector: CharacterSelectionDetector
) -> bool:
    return (
        _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)
        and detector.measure(snapshot.frame).state
        is CharacterSelectionState.SELECTED
    )


def replace_selection_region(
    detector: CharacterSelectionDetector, region
) -> CharacterSelectionDetector:
    """Reuse the calibrated yellow-border classifier on a target tile box."""

    return replace(detector, region=region)


def _is_clean_quick_menu_capable(
    snapshot: RuntimeSnapshot,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and _has_compatible_origin_overlays(state.base_context, state.overlays)
        and quick_menu_accessible(state.base_context, policy=policy)
    )


def _has_quick_menu(
    snapshot: RuntimeSnapshot,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    state = snapshot.state
    return (
        set(state.overlays) == {MENU_QUICK}
        and (
            state.status is ResolutionStatus.UNKNOWN
            or (
                state.status is ResolutionStatus.RESOLVED
                and quick_menu_accessible(state.base_context, policy=policy)
            )
        )
    )


def _can_wait_for_quick_menu_precondition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return state.status is ResolutionStatus.UNKNOWN and not state.overlays


def _has_incompatible_quick_menu_precondition(
    snapshot: RuntimeSnapshot,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    state = snapshot.state
    if _is_clean_quick_menu_capable(snapshot, policy):
        return False
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and not quick_menu_accessible(state.base_context, policy=policy)
        )
    )


def _has_unexpected_quick_menu_state(
    snapshot: RuntimeSnapshot,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    state = snapshot.state
    if _has_quick_menu(snapshot, policy) or _is_clean_quick_menu_capable(
        snapshot, policy
    ):
        return False
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
    )


def _has_compatible_origin_overlays(
    base_context: str | None,
    overlays,
) -> bool:
    values = set(overlays)
    if base_context == SCREEN_GUILD:
        return len(values) == 1 and values <= {
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_COMPLETED,
        }
    return not values


def _has_unexpected_character_select_transition(
    snapshot: RuntimeSnapshot,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    state = snapshot.state
    if (
        _has_quick_menu(snapshot, policy)
        or _is_clean_quick_menu_capable(snapshot, policy)
        or _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT)
    ):
        return False
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
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


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
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
    "replace_selection_region",
)
