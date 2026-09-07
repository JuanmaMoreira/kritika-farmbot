"""Small bounded primitives for fresh multi-frame runtime observations."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable

from bot.capture import FrameSnapshot
from bot.runtime_observer import (
    FrameSource,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.state import ResolutionStatus


class TemporalWindowStatus(str, Enum):
    COMPLETE = "complete"
    CONTEXT_MISMATCH = "context_mismatch"
    INTERRUPTED = "interrupted"
    INSUFFICIENT = "insufficient"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILURE = "failure"


@dataclass(frozen=True)
class TemporalWindow:
    status: TemporalWindowStatus
    snapshots: tuple[RuntimeSnapshot, ...] = ()
    detail: str | None = None

    @property
    def last_sequence(self) -> int | None:
        return self.snapshots[-1].sequence if self.snapshots else None

    @property
    def duration(self) -> float:
        if len(self.snapshots) < 2:
            return 0.0
        return self.snapshots[-1].timestamp - self.snapshots[0].timestamp


class TemporalObserver:
    """Acquire a fixed-size sequence through RuntimeObserver only."""

    def __init__(
        self,
        observer: RuntimeObserver,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(observer, RuntimeObserver):
            raise ValueError("observer must be a RuntimeObserver")
        self.observer = observer
        self._clock = clock

    def collect(
        self,
        *,
        after_sequence: int,
        context: str,
        frame_count: int,
        sample_interval: float,
        timeout: float,
        interrupt_overlays: frozenset[str] = frozenset(),
        cancel_requested: Callable[[], bool] | None = None,
    ) -> TemporalWindow:
        after = _sequence(after_sequence)
        count = _frame_count(frame_count)
        interval = _non_negative(sample_interval, "sample_interval")
        duration = _positive(timeout, "timeout")
        started = self._clock()
        deadline = started + duration
        snapshots: list[RuntimeSnapshot] = []
        cursor = after
        try:
            while len(snapshots) < count:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return TemporalWindow(
                        TemporalWindowStatus.TIMEOUT,
                        tuple(snapshots),
                        _timeout_detail(
                            "temporal observation deadline expired",
                            snapshots,
                            count,
                            duration,
                            self._clock() - started,
                        ),
                    )
                snapshot = self.observer.wait_until(
                    lambda item: (
                        (
                            not snapshots
                            or item.timestamp - snapshots[-1].timestamp >= interval
                        )
                        and (
                            item.state.status is ResolutionStatus.RESOLVED
                            or bool(interrupt_overlays.intersection(item.state.overlays))
                        )
                    ),
                    after_sequence=cursor,
                    timeout=remaining,
                    cancel_requested=cancel_requested,
                )
                cursor = snapshot.sequence
                interruption = interrupt_overlays.intersection(snapshot.state.overlays)
                if interruption:
                    snapshots.append(snapshot)
                    return TemporalWindow(
                        TemporalWindowStatus.INTERRUPTED,
                        tuple(snapshots),
                        f"observation interrupted by {sorted(interruption)[0]}",
                    )
                if snapshot.state.status is not ResolutionStatus.RESOLVED:
                    # A transient UNKNOWN/AMBIGUOUS frame consumes time but is
                    # never evidence for the temporal fact or permission for input.
                    continue
                snapshots.append(snapshot)
                if snapshot.state.base_context != context:
                    return TemporalWindow(
                        TemporalWindowStatus.CONTEXT_MISMATCH,
                        tuple(snapshots),
                        "fresh resolved frame is "
                        f"{snapshot.state.base_context}, expected {context}",
                    )
        except RuntimeWaitCancelled:
            return TemporalWindow(TemporalWindowStatus.CANCELLED, tuple(snapshots))
        except RuntimeWaitTimeout:
            return TemporalWindow(
                TemporalWindowStatus.TIMEOUT,
                tuple(snapshots),
                _timeout_detail(
                    "no fresh frame arrived before the deadline",
                    snapshots,
                    count,
                    duration,
                    self._clock() - started,
                ),
            )
        except Exception as error:
            return TemporalWindow(
                TemporalWindowStatus.FAILURE, tuple(snapshots), str(error)
            )
        if len(snapshots) < 2:
            return TemporalWindow(
                TemporalWindowStatus.INSUFFICIENT,
                tuple(snapshots),
                "at least two fresh frames are required",
            )
        return TemporalWindow(TemporalWindowStatus.COMPLETE, tuple(snapshots))


@dataclass(frozen=True)
class FrameHarvest:
    """Raw frames harvested straight from the source, without semantics.

    Unlike :class:`TemporalWindow`, frames here carry no resolved state: the
    caller owns context verification (bracketing full observations plus a
    fresh guard before any input). Only strictly increasing sequences are
    ever collected, so a stalled decoder can never inject zero-diff
    duplicates.
    """

    status: TemporalWindowStatus
    frames: tuple[FrameSnapshot, ...] = ()
    detail: str | None = None


def harvest_frame_window(
    source: FrameSource,
    *,
    after_sequence: int,
    frame_count: int,
    sample_interval: float,
    timeout: float,
    poll_interval: float = 0.02,
    cancel_requested: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> FrameHarvest:
    """Collect fresh raw frames spaced by capture timestamps, bounded.

    Frames with a repeated or older sequence (decoder stall) never count
    toward ``frame_count`` nor toward the timestamp spacing: counting them
    would fabricate ~0 diffs and bias motion classifiers.
    """

    if not callable(getattr(source, "get_frame", None)):
        raise ValueError("source must provide get_frame()")
    if cancel_requested is not None and not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")
    after = _sequence(after_sequence)
    count = _frame_count(frame_count)
    interval = _non_negative(sample_interval, "sample_interval")
    duration = _positive(timeout, "timeout")
    poll = _positive(poll_interval, "poll_interval")
    started = clock()
    deadline = started + duration
    frames: list[FrameSnapshot] = []
    cursor = after
    while len(frames) < count:
        if cancel_requested is not None and cancel_requested():
            return FrameHarvest(TemporalWindowStatus.CANCELLED, tuple(frames))
        remaining = deadline - clock()
        if remaining <= 0:
            return FrameHarvest(
                TemporalWindowStatus.TIMEOUT,
                tuple(frames),
                _timeout_detail(
                    "frame harvest deadline expired",
                    frames,
                    count,
                    duration,
                    clock() - started,
                ),
            )
        try:
            frame = source.get_frame()
        except Exception as error:
            return FrameHarvest(
                TemporalWindowStatus.FAILURE, tuple(frames), str(error)
            )
        if not isinstance(frame, FrameSnapshot):
            return FrameHarvest(
                TemporalWindowStatus.FAILURE,
                tuple(frames),
                "source must emit FrameSnapshot instances",
            )
        if frame.sequence <= cursor:
            # Stale or duplicate delivery: never evidence, never spacing.
            sleeper(min(poll, remaining))
            continue
        if frames and frame.timestamp - frames[-1].timestamp < interval:
            # Fresh but too close in capture time: skip without consuming the
            # cursor so the spacing baseline stays intact.
            sleeper(min(poll, remaining))
            continue
        frames.append(frame)
        cursor = frame.sequence
        if len(frames) < count:
            sleeper(min(poll, remaining))
    return FrameHarvest(TemporalWindowStatus.COMPLETE, tuple(frames))


def _sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("after_sequence must be a non-negative integer")
    return int(value)


def _timeout_detail(
    reason: str,
    snapshots: list[RuntimeSnapshot],
    expected_count: int,
    timeout: float,
    elapsed: float,
) -> str:
    last_sequence = snapshots[-1].sequence if snapshots else None
    frame_span = (
        snapshots[-1].timestamp - snapshots[0].timestamp
        if len(snapshots) >= 2
        else 0.0
    )
    return (
        f"{reason}; frames_collected={len(snapshots)}/{expected_count}; "
        f"last_sequence={last_sequence}; frame_span={frame_span:.3f}; "
        f"elapsed={max(0.0, elapsed):.3f}; timeout={timeout:.3f}"
    )


def _frame_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 2:
        raise ValueError("frame_count must be an integer >= 2")
    return int(value)


def _positive(value: object, name: str) -> float:
    result = _non_negative(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


__all__ = (
    "FrameHarvest",
    "TemporalObserver",
    "TemporalWindow",
    "TemporalWindowStatus",
    "harvest_frame_window",
)
