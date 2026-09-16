"""Directed scroll over a known ordered list with observed positions.

Consumer-agnostic primitive: the caller owns the ordered catalog, the
viewport observations, the safe gesture geometry and the budgets. This
module only derives direction and a bounded displacement from catalog
order, executes one injected gesture at a time, reobserves, and proves
catalog progress before allowing another gesture.

Conventions:

- ``FORWARD`` means toward higher catalog indices. Physically it maps to
  an upward swipe (finger travels from a lower touchdown toward the top)
  so that rows with higher indices enter the viewport.
- ``BACKWARD`` means toward lower catalog indices (downward swipe).
- Gesture coordinates are normalized ``[0, 1]`` fractions, matching the
  ``Swipe`` convention used elsewhere in the repo. The safe touchdown
  lane and the vertical gesture limits always come from the caller-owned
  profile; this module never invents an interactive coordinate.
- Freshness is local only: a post-gesture observation must carry a
  strictly greater sequence than the pre-gesture one, and consensus
  samples must strictly increase. Stale evidence never proves progress
  or target stability. No cache or lifecycle is introduced here.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real


class ScrollDirection(str, Enum):
    FORWARD = "forward"
    BACKWARD = "backward"


class DirectedScrollOutcome(str, Enum):
    TARGET_READY = "target_ready"
    PROGRESSED = "progressed"
    NO_PROGRESS = "no_progress"
    UNREADABLE = "unreadable"
    GUARD_LOST = "guard_lost"
    TARGET_UNKNOWN = "target_unknown"
    BUDGET_EXHAUSTED = "budget_exhausted"


class DirectedScrollError(ValueError):
    """Base error for directed-scroll contract violations."""


class TargetUnknownError(DirectedScrollError):
    """Catalog or target identifier violates the known-list contract."""


class UnreadableViewportError(DirectedScrollError):
    """Visible viewport content cannot be trusted for directed motion."""


@dataclass(frozen=True)
class KnownListScrollProfile:
    """Caller-owned geometry and verification bounds for one list.

    ``row_pitch`` is the normalized vertical distance between consecutive
    row centers. ``visible_rows`` is the approximate number of rows used
    to derive the overlap-safe bound. ``lane_x`` plus ``top_y``/``bottom_y``
    delimit the caller-owned safe (non-interactive) gesture zone.
    Consensus fields bound the target-stability check.
    """

    row_pitch: float
    visible_rows: int
    lane_x: float
    top_y: float
    bottom_y: float
    overlap_factor: float = 0.95
    row_tolerance: float = 0.01
    consensus_required: int = 2
    consensus_max_samples: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "row_pitch", _positive_fraction(self.row_pitch, "row_pitch")
        )
        object.__setattr__(
            self, "visible_rows", _minimum_integer(self.visible_rows, "visible_rows", 2)
        )
        object.__setattr__(self, "lane_x", _unit(self.lane_x, "lane_x"))
        object.__setattr__(self, "top_y", _unit(self.top_y, "top_y"))
        object.__setattr__(self, "bottom_y", _unit(self.bottom_y, "bottom_y"))
        if not self.top_y < self.bottom_y:
            raise ValueError("top_y must be strictly below bottom_y")
        object.__setattr__(
            self,
            "overlap_factor",
            _closed_unit_positive(self.overlap_factor, "overlap_factor"),
        )
        object.__setattr__(
            self, "row_tolerance", _non_negative_fraction(self.row_tolerance, "row_tolerance")
        )
        object.__setattr__(
            self,
            "consensus_required",
            _minimum_integer(self.consensus_required, "consensus_required", 1),
        )
        object.__setattr__(
            self,
            "consensus_max_samples",
            _minimum_integer(
                self.consensus_max_samples, "consensus_max_samples", self.consensus_required
            ),
        )

    @property
    def max_delta(self) -> float:
        """Largest allowed gesture magnitude; keeps overlap for verification."""
        return (self.visible_rows - 1) * self.row_pitch * self.overlap_factor

    @property
    def span(self) -> float:
        return self.bottom_y - self.top_y


@dataclass(frozen=True)
class ViewportReading:
    """One fresh viewport observation owned and produced by the caller.

    ``visible_ids`` are catalog identifiers ordered top to bottom as
    displayed. ``target_row_y`` is the normalized vertical center of the
    target row; required whenever the target is among ``visible_ids``.
    ``sequence`` orders observations in time. ``readable`` is False when
    the viewport cannot be interpreted; ``guard_ok`` is False when the
    caller-owned context guard is lost.
    """

    visible_ids: tuple[Hashable, ...]
    sequence: int
    target_row_y: float | None = None
    readable: bool = True
    guard_ok: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_ids", tuple(self.visible_ids))
        for value in self.visible_ids:
            if not isinstance(value, Hashable):
                raise ValueError("visible_ids must contain hashable identifiers")
        object.__setattr__(self, "sequence", _any_integer(self.sequence, "sequence"))
        if self.target_row_y is not None:
            object.__setattr__(
                self, "target_row_y", _unit(self.target_row_y, "target_row_y")
            )
        if not isinstance(self.readable, bool):
            raise ValueError("readable must be bool")
        if not isinstance(self.guard_ok, bool):
            raise ValueError("guard_ok must be bool")


@dataclass(frozen=True)
class PlannedGesture:
    """One bounded scroll gesture derived from catalog order."""

    direction: ScrollDirection
    rows: int
    delta: float
    lane_x: float
    start_y: float
    end_y: float

    def __post_init__(self) -> None:
        if not isinstance(self.direction, ScrollDirection):
            raise ValueError("direction must be ScrollDirection")
        object.__setattr__(self, "rows", _minimum_integer(self.rows, "rows", 1))
        if (
            isinstance(self.delta, bool)
            or not isinstance(self.delta, Real)
            or not 0.0 < float(self.delta)
        ):
            raise ValueError("delta must be a positive finite number")
        object.__setattr__(self, "delta", float(self.delta))


@dataclass(frozen=True)
class DirectedScrollResult:
    """Outcome of a single step or of the bounded driver."""

    outcome: DirectedScrollOutcome
    gestures: tuple[PlannedGesture, ...] = ()
    stable_row_y: float | None = None
    stable_sequence: int | None = None
    last_sequence: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, DirectedScrollOutcome):
            raise ValueError("outcome must be DirectedScrollOutcome")
        object.__setattr__(self, "gestures", tuple(self.gestures))
        for gesture in self.gestures:
            if not isinstance(gesture, PlannedGesture):
                raise ValueError("gestures must contain PlannedGesture values")
        if self.outcome is DirectedScrollOutcome.TARGET_READY and (
            self.stable_row_y is None or self.stable_sequence is None
        ):
            raise ValueError("target_ready requires stable evidence")
        if self.last_sequence is not None:
            object.__setattr__(
                self, "last_sequence", _any_integer(self.last_sequence, "last_sequence")
            )

    @property
    def gesture_count(self) -> int:
        return len(self.gestures)


def plan_directed_gesture(
    *,
    catalog: Sequence[Hashable],
    target: Hashable,
    visible_ids: Sequence[Hashable],
    profile: KnownListScrollProfile,
) -> PlannedGesture | None:
    """Derive the next bounded gesture from known order, or None if visible.

    Returns None when the target is already among ``visible_ids`` (the
    caller path is consensus, not motion). Raises :class:`TargetUnknownError`
    for catalog/target contract violations and
    :class:`UnreadableViewportError` for untrustworthy viewport content.
    Pure: performs no IO.
    """
    if not isinstance(profile, KnownListScrollProfile):
        raise ValueError("profile must be KnownListScrollProfile")
    order = _validated_catalog(catalog)
    target_index = _target_index(order, target)
    first_index, last_index = _visible_range(order, tuple(visible_ids))
    if first_index <= target_index <= last_index:
        if target in tuple(visible_ids):
            return None
        # Target index inside the visible window but not observed: a partially
        # rendered row. Nudge one row toward the nearer edge to reveal it.
        if target_index - first_index <= last_index - target_index:
            return _bounded_gesture(profile, ScrollDirection.BACKWARD, 1)
        return _bounded_gesture(profile, ScrollDirection.FORWARD, 1)
    if target_index > last_index:
        return _bounded_gesture(
            profile, ScrollDirection.FORWARD, target_index - last_index
        )
    return _bounded_gesture(
        profile, ScrollDirection.BACKWARD, first_index - target_index
    )


def range_progressed(
    *,
    direction: ScrollDirection,
    pre_first: int,
    pre_last: int,
    post_first: int,
    post_last: int,
) -> bool:
    """Check catalog progress via the leading edge in the expected direction.

    Pure: compares index ranges before and after one gesture. Same range
    or motion against the expected direction is not progress.
    """
    if direction is ScrollDirection.FORWARD:
        return post_last > pre_last
    if direction is ScrollDirection.BACKWARD:
        return post_first < pre_first
    raise ValueError("direction must be ScrollDirection")


def advance_toward_target(
    *,
    catalog: Sequence[Hashable],
    target: Hashable,
    profile: KnownListScrollProfile,
    observe: Callable[[], ViewportReading],
    emit: Callable[[PlannedGesture], None],
    remaining_budget: int,
    after_sequence: int | None = None,
) -> DirectedScrollResult:
    """Perform at most one directed gesture step toward a known target.

    Budget gates gestures, never reads: with ``remaining_budget == 0`` a
    stable visible target still reports ``TARGET_READY`` while any needed
    motion reports ``BUDGET_EXHAUSTED`` without input. ``after_sequence``
    rejects a stale pre-gesture observation. Never taps the target; the
    only callable that produces physical motion is ``emit``.
    """
    if not isinstance(profile, KnownListScrollProfile):
        raise ValueError("profile must be KnownListScrollProfile")
    if not callable(observe) or not callable(emit):
        raise ValueError("observe and emit must be callable")
    remaining = _non_negative_integer(remaining_budget, "remaining_budget")
    if after_sequence is not None:
        after_sequence = _any_integer(after_sequence, "after_sequence")
    try:
        order = _validated_catalog(catalog)
        _target_index(order, target)  # membership proof before any IO
    except TargetUnknownError as error:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.TARGET_UNKNOWN,
            reason=str(error),
        )

    pre = observe()
    _check_reading_type(pre)
    if after_sequence is not None and pre.sequence <= after_sequence:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.NO_PROGRESS,
            last_sequence=pre.sequence,
            reason="stale_observation",
        )
    if not pre.guard_ok:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.GUARD_LOST,
            last_sequence=pre.sequence,
            reason="guard_lost",
        )
    if not pre.readable:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.UNREADABLE,
            last_sequence=pre.sequence,
            reason="viewport_unreadable",
        )
    try:
        first_index, last_index = _visible_range(order, pre.visible_ids)
        target_visible = target in pre.visible_ids
    except UnreadableViewportError as error:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.UNREADABLE,
            last_sequence=pre.sequence,
            reason=str(error),
        )

    if target_visible:
        try:
            pre_row_y = _target_row_y(pre)
        except UnreadableViewportError as error:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.UNREADABLE,
                last_sequence=pre.sequence,
                reason=str(error),
            )
        return _confirm_target(
            observe=observe,
            profile=profile,
            order=order,
            target=target,
            first_y=pre_row_y,
            first_sequence=pre.sequence,
        )

    if remaining <= 0:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.BUDGET_EXHAUSTED,
            last_sequence=pre.sequence,
            reason="budget_exhausted",
        )
    gesture = plan_directed_gesture(
        catalog=order, target=target, visible_ids=pre.visible_ids, profile=profile
    )
    assert gesture is not None  # target not visible implies a planned move
    emit(gesture)

    post = observe()
    _check_reading_type(post)
    if not post.guard_ok:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.GUARD_LOST,
            gestures=(gesture,),
            last_sequence=post.sequence,
            reason="guard_lost",
        )
    if not post.readable:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.UNREADABLE,
            gestures=(gesture,),
            last_sequence=post.sequence,
            reason="viewport_unreadable",
        )
    if post.sequence <= pre.sequence:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.NO_PROGRESS,
            gestures=(gesture,),
            last_sequence=post.sequence,
            reason="stale_observation",
        )
    try:
        post_first, post_last = _visible_range(order, post.visible_ids)
    except UnreadableViewportError as error:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.NO_PROGRESS,
            gestures=(gesture,),
            last_sequence=post.sequence,
            reason=str(error),
        )
    if not range_progressed(
        direction=gesture.direction,
        pre_first=first_index,
        pre_last=last_index,
        post_first=post_first,
        post_last=post_last,
    ):
        if (
            gesture.direction is ScrollDirection.FORWARD
            and post_last < last_index
            or gesture.direction is ScrollDirection.BACKWARD
            and post_first > first_index
        ):
            reason = "wrong_direction"
        else:
            reason = "no_progress"
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.NO_PROGRESS,
            gestures=(gesture,),
            last_sequence=post.sequence,
            reason=reason,
        )
    return DirectedScrollResult(
        outcome=DirectedScrollOutcome.PROGRESSED,
        gestures=(gesture,),
        last_sequence=post.sequence,
        reason="progressed",
    )


def scroll_to_target(
    *,
    catalog: Sequence[Hashable],
    target: Hashable,
    profile: KnownListScrollProfile,
    observe: Callable[[], ViewportReading],
    emit: Callable[[PlannedGesture], None],
    max_gestures: int,
) -> DirectedScrollResult:
    """Drive bounded observe-gesture-reobserve steps until a terminal outcome.

    Every gesture consumes one unit of ``max_gestures``. Progress without a
    stable target keeps iterating while budget remains; consuming the last
    unit without reaching the target reports ``BUDGET_EXHAUSTED`` with the
    demonstrated gestures preserved as evidence. No hidden retries exist
    outside the budget.
    """
    if not isinstance(profile, KnownListScrollProfile):
        raise ValueError("profile must be KnownListScrollProfile")
    if not callable(observe) or not callable(emit):
        raise ValueError("observe and emit must be callable")
    remaining = _minimum_integer(max_gestures, "max_gestures", 1)
    gestures: list[PlannedGesture] = []
    after_sequence: int | None = None
    while True:
        step = advance_toward_target(
            catalog=catalog,
            target=target,
            profile=profile,
            observe=observe,
            emit=emit,
            remaining_budget=remaining,
            after_sequence=after_sequence,
        )
        gestures.extend(step.gestures)
        if step.outcome is DirectedScrollOutcome.PROGRESSED:
            remaining -= len(step.gestures)
            after_sequence = step.last_sequence
            if remaining <= 0:
                return DirectedScrollResult(
                    outcome=DirectedScrollOutcome.BUDGET_EXHAUSTED,
                    gestures=tuple(gestures),
                    last_sequence=step.last_sequence,
                    reason="budget_exhausted",
                )
            continue
        return DirectedScrollResult(
            outcome=step.outcome,
            gestures=tuple(gestures),
            stable_row_y=step.stable_row_y,
            stable_sequence=step.stable_sequence,
            last_sequence=step.last_sequence,
            reason=step.reason,
        )


def _confirm_target(
    *,
    observe: Callable[[], ViewportReading],
    profile: KnownListScrollProfile,
    order: tuple[Hashable, ...],
    target: Hashable,
    first_y: float,
    first_sequence: int,
) -> DirectedScrollResult:
    """Bounded consensus over consecutive agreeing target observations."""
    last_y = first_y
    last_sequence = first_sequence
    agreements = 1
    samples = 1
    while samples < profile.consensus_max_samples:
        sample = observe()
        _check_reading_type(sample)
        samples += 1
        if sample.sequence <= last_sequence:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.NO_PROGRESS,
                last_sequence=sample.sequence,
                reason="stale_observation",
            )
        last_sequence = sample.sequence
        if not sample.guard_ok:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.GUARD_LOST,
                last_sequence=sample.sequence,
                reason="guard_lost",
            )
        if not sample.readable:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.UNREADABLE,
                last_sequence=sample.sequence,
                reason="viewport_unreadable",
            )
        try:
            _visible_range(order, sample.visible_ids)
        except UnreadableViewportError as error:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.UNREADABLE,
                last_sequence=sample.sequence,
                reason=str(error),
            )
        if target not in sample.visible_ids:
            agreements = 1
            continue
        try:
            sample_y = _target_row_y(sample)
        except UnreadableViewportError as error:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.UNREADABLE,
                last_sequence=sample.sequence,
                reason=str(error),
            )
        if abs(sample_y - last_y) > profile.row_tolerance:
            agreements = 1
            last_y = sample_y
            continue
        agreements += 1
        last_y = sample_y
        if agreements >= profile.consensus_required:
            return DirectedScrollResult(
                outcome=DirectedScrollOutcome.TARGET_READY,
                stable_row_y=last_y,
                stable_sequence=sample.sequence,
                last_sequence=sample.sequence,
                reason="target_ready",
            )
    return DirectedScrollResult(
        outcome=DirectedScrollOutcome.NO_PROGRESS,
        last_sequence=last_sequence,
        reason="target_unstable",
    )


def _bounded_gesture(
    profile: KnownListScrollProfile, direction: ScrollDirection, rows: int
) -> PlannedGesture:
    wanted = max(int(rows), 1) * profile.row_pitch
    delta = min(wanted, profile.max_delta, profile.span)
    if direction is ScrollDirection.FORWARD:
        start_y = profile.bottom_y
        end_y = profile.bottom_y - delta
    else:
        start_y = profile.top_y
        end_y = profile.top_y + delta
    return PlannedGesture(
        direction=direction,
        rows=max(int(rows), 1),
        delta=delta,
        lane_x=profile.lane_x,
        start_y=start_y,
        end_y=end_y,
    )


def _validated_catalog(catalog: Sequence[Hashable]) -> tuple[Hashable, ...]:
    order = tuple(catalog)
    if not order:
        raise TargetUnknownError("catalog_empty")
    for value in order:
        if not isinstance(value, Hashable):
            raise TargetUnknownError("catalog_has_unhashable_id")
    if len(set(order)) != len(order):
        raise TargetUnknownError("catalog_has_duplicates")
    return order


def _target_index(order: tuple[Hashable, ...], target: Hashable) -> int:
    if not isinstance(target, Hashable):
        raise TargetUnknownError("target_not_in_catalog")
    try:
        return order.index(target)
    except ValueError:
        raise TargetUnknownError("target_not_in_catalog") from None


def _visible_range(
    order: tuple[Hashable, ...], visible_ids: Sequence[Hashable]
) -> tuple[int, int]:
    visible = tuple(visible_ids)
    if not visible:
        raise UnreadableViewportError("visible_empty")
    try:
        indices = [order.index(value) for value in visible]
    except ValueError:
        raise UnreadableViewportError("visible_has_unknown_ids") from None
    if any(later <= earlier for earlier, later in zip(indices, indices[1:])):
        raise UnreadableViewportError("visible_order_inconsistent")
    return indices[0], indices[-1]


def _target_row_y(reading: ViewportReading) -> float:
    if reading.target_row_y is None:
        raise UnreadableViewportError("target_row_missing")
    return reading.target_row_y


def _check_reading_type(reading: object) -> None:
    if not isinstance(reading, ViewportReading):
        raise ValueError("observe must return ViewportReading")


def _positive_fraction(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not 0.0 < result <= 1.0:
        raise ValueError(f"{name} must be within (0, 1]")
    return result


def _non_negative_fraction(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not 0.0 <= result < 1.0:
        raise ValueError(f"{name} must be within [0, 1)")
    return result


def _unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return result


def _closed_unit_positive(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in (0, 1]")
    result = float(value)
    if not 0.0 < result <= 1.0:
        raise ValueError(f"{name} must be a real number in (0, 1]")
    return result


def _any_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def _non_negative_integer(value: object, name: str) -> int:
    result = _any_integer(value, name)
    if result < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _minimum_integer(value: object, name: str, minimum: int) -> int:
    result = _any_integer(value, name)
    if result < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return result


__all__ = (
    "DirectedScrollError",
    "DirectedScrollOutcome",
    "DirectedScrollResult",
    "KnownListScrollProfile",
    "PlannedGesture",
    "ScrollDirection",
    "TargetUnknownError",
    "UnreadableViewportError",
    "ViewportReading",
    "advance_toward_target",
    "plan_directed_gesture",
    "range_progressed",
    "scroll_to_target",
)
