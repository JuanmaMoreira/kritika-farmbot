"""Reusable visual scroll-to-edge operation over fresh A/T/B frames."""

from __future__ import annotations

import math
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable, Protocol, Sequence

import cv2
import numpy as np

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.geometry import (
    RelativeRegion,
    frame_dimensions,
    normalize_relative_region,
    relative_region_to_pixels,
)
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import Swipe


class ScrollAttemptKind(str, Enum):
    PROGRESS = "progress"
    EDGE_CANDIDATE = "edge_candidate"
    INEFFECTIVE = "ineffective"


class ObservedScrollOutcome(str, Enum):
    EDGE_REACHED = "edge_reached"
    INEFFECTIVE_GESTURE = "ineffective_gesture"
    LIMIT_REACHED = "limit_reached"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass(frozen=True)
class ScrollAttemptMeasurement:
    pre_sequence: int
    settled_sequence: int
    fresh_sample_count: int
    transient_peak_sequence: int
    max_transient_difference: float
    settled_difference: float


@dataclass(frozen=True)
class ViewportMotionDetector:
    """Measure motion and settled similarity inside one normalized viewport."""

    region: RelativeRegion
    thumbnail_width: int = 96
    thumbnail_height: int = 72
    unchanged_threshold: float = 0.0500

    def __post_init__(self) -> None:
        object.__setattr__(self, "region", normalize_relative_region(self.region))
        for name in ("thumbnail_width", "thumbnail_height"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a positive integer")
            object.__setattr__(self, name, int(value))
        object.__setattr__(
            self,
            "unchanged_threshold",
            _normalized_threshold(self.unchanged_threshold, "unchanged_threshold"),
        )

    def difference(self, first: np.ndarray, second: np.ndarray) -> float:
        left = self._thumbnail(first).astype(np.float32)
        right = self._thumbnail(second).astype(np.float32)
        return float(np.mean(np.abs(left - right)) / 255.0)

    def measure_transition(
        self,
        before: FrameSnapshot,
        samples: Sequence[FrameSnapshot],
        settled: FrameSnapshot,
    ) -> ScrollAttemptMeasurement:
        """Measure one settled A -> transient T -> settled B sequence."""

        if not isinstance(before, FrameSnapshot):
            raise ValueError("before must be a FrameSnapshot")
        if not isinstance(settled, FrameSnapshot):
            raise ValueError("settled must be a FrameSnapshot")
        fresh_samples = tuple(samples)
        if not fresh_samples:
            raise ValueError("samples must contain fresh post-swipe frames")

        previous_sequence = before.sequence
        differences: list[tuple[int, float]] = []
        for sample in fresh_samples:
            if not isinstance(sample, FrameSnapshot):
                raise ValueError("samples must contain FrameSnapshot values")
            if sample.sequence <= previous_sequence:
                raise ValueError("samples must have strictly increasing fresh sequences")
            differences.append(
                (sample.sequence, self.difference(before.image, sample.image))
            )
            previous_sequence = sample.sequence
        if settled.sequence != fresh_samples[-1].sequence:
            raise ValueError("settled must be the final fresh sample")

        peak_sequence, peak_difference = max(differences, key=lambda item: item[1])
        return ScrollAttemptMeasurement(
            pre_sequence=before.sequence,
            settled_sequence=settled.sequence,
            fresh_sample_count=len(fresh_samples),
            transient_peak_sequence=peak_sequence,
            max_transient_difference=peak_difference,
            settled_difference=self.difference(before.image, settled.image),
        )

    def classify(
        self,
        measurement: ScrollAttemptMeasurement,
        *,
        movement_threshold: float,
    ) -> ScrollAttemptKind:
        if not isinstance(measurement, ScrollAttemptMeasurement):
            raise ValueError("measurement must be ScrollAttemptMeasurement")
        movement = _normalized_threshold(movement_threshold, "movement_threshold")
        if measurement.max_transient_difference < movement:
            return ScrollAttemptKind.INEFFECTIVE
        if measurement.settled_difference <= self.unchanged_threshold:
            return ScrollAttemptKind.EDGE_CANDIDATE
        return ScrollAttemptKind.PROGRESS

    def _thumbnail(self, frame: np.ndarray) -> np.ndarray:
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("frame must be a non-empty NumPy array")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must contain exactly three BGR channels")
        width, height = frame_dimensions(frame)
        x1, y1, x2, y2 = relative_region_to_pixels(
            self.region, width, height
        )
        gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        return cv2.resize(
            gray,
            (self.thumbnail_width, self.thumbnail_height),
            interpolation=cv2.INTER_AREA,
        )


@dataclass(frozen=True)
class ObservedScrollConfig:
    """Generic bounded policy and gestures for a visual scroll operation."""

    progress_swipe: Swipe
    confirmation_swipe: Swipe
    movement_threshold: float = 0.0500
    required_confirmations: int = 1
    max_attempts: int = 10
    timeout: float = 6.0
    settle_for: float = 1.0
    abort_on_ineffective: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.progress_swipe, Swipe):
            raise ValueError("progress_swipe must be Swipe")
        if not isinstance(self.confirmation_swipe, Swipe):
            raise ValueError("confirmation_swipe must be Swipe")
        object.__setattr__(
            self,
            "movement_threshold",
            _normalized_threshold(self.movement_threshold, "movement_threshold"),
        )
        confirmations = _positive_integer(
            self.required_confirmations, "required_confirmations"
        )
        attempts = _positive_integer(self.max_attempts, "max_attempts")
        if confirmations > attempts:
            raise ValueError("required_confirmations must not exceed max_attempts")
        object.__setattr__(self, "required_confirmations", confirmations)
        object.__setattr__(self, "max_attempts", attempts)
        object.__setattr__(self, "timeout", _positive_duration(self.timeout, "timeout"))
        object.__setattr__(
            self,
            "settle_for",
            _non_negative_duration(self.settle_for, "settle_for"),
        )
        if not isinstance(self.abort_on_ineffective, bool):
            raise ValueError("abort_on_ineffective must be bool")


@dataclass(frozen=True)
class ObservedScrollResult:
    outcome: ObservedScrollOutcome
    final_snapshot: RuntimeSnapshot
    attempts: tuple[ScrollAttemptMeasurement, ...] = ()
    attempt_kinds: tuple[ScrollAttemptKind, ...] = ()
    effective_gesture_count: int = 0
    confirmation_count: int = 0
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.final_snapshot, RuntimeSnapshot):
            raise ValueError("final_snapshot must be RuntimeSnapshot")
        if len(self.attempts) != len(self.attempt_kinds):
            raise ValueError("attempts and attempt_kinds must have equal length")
        effective = _non_negative_integer(
            self.effective_gesture_count, "effective_gesture_count"
        )
        confirmations = _non_negative_integer(
            self.confirmation_count, "confirmation_count"
        )
        if confirmations > effective:
            raise ValueError(
                "confirmation_count must not exceed effective_gesture_count"
            )
        if self.outcome is ObservedScrollOutcome.EDGE_REACHED and (
            effective == 0 or confirmations == 0
        ):
            raise ValueError("edge_reached requires effective confirmed movement")
        object.__setattr__(self, "effective_gesture_count", effective)
        object.__setattr__(self, "confirmation_count", confirmations)

    @property
    def edge_reached(self) -> bool:
        return self.outcome is ObservedScrollOutcome.EDGE_REACHED


class _Observer(Protocol):
    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class _SwipeExecutor(Protocol):
    def submit(self, function: Callable, *args: object) -> Future: ...

    def __enter__(self) -> "_SwipeExecutor": ...

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None: ...


class ObservedScroll:
    """Drive and observe a bounded scroll without knowing the owning screen."""

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        *,
        swipe_executor_factory: Callable[[], _SwipeExecutor] | None = None,
    ) -> None:
        if not callable(getattr(observer, "wait_until", None)):
            raise ValueError("observer must provide wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute(intent, geometry)")
        if swipe_executor_factory is None:
            swipe_executor_factory = lambda: ThreadPoolExecutor(max_workers=1)
        if not callable(swipe_executor_factory):
            raise ValueError("swipe_executor_factory must be callable")
        self.observer: _Observer = observer
        self.actions = actions
        self._swipe_executor_factory = swipe_executor_factory

    def scroll_to_edge(
        self,
        before: RuntimeSnapshot,
        *,
        detector: ViewportMotionDetector,
        config: ObservedScrollConfig,
        is_compatible: Callable[[RuntimeSnapshot], bool],
        abort_if: Callable[[RuntimeSnapshot], bool],
    ) -> ObservedScrollResult:
        if not isinstance(before, RuntimeSnapshot):
            raise ValueError("before must be RuntimeSnapshot")
        if not isinstance(detector, ViewportMotionDetector):
            raise ValueError("detector must be ViewportMotionDetector")
        if not isinstance(config, ObservedScrollConfig):
            raise ValueError("config must be ObservedScrollConfig")
        if not callable(is_compatible) or not callable(abort_if):
            raise ValueError("is_compatible and abort_if must be callable")

        current = before
        measurements: list[ScrollAttemptMeasurement] = []
        kinds: list[ScrollAttemptKind] = []
        effective_count = 0
        confirmations = 0
        try:
            with self._swipe_executor_factory() as executor:
                for _ in range(config.max_attempts):
                    swipe = (
                        config.progress_swipe
                        if effective_count == 0
                        else config.confirmation_swipe
                    )
                    current, measurement = self._measure_attempt(
                        current,
                        swipe,
                        detector=detector,
                        is_compatible=is_compatible,
                        abort_if=abort_if,
                        timeout=config.timeout,
                        settle_for=config.settle_for,
                        executor=executor,
                    )
                    kind = detector.classify(
                        measurement,
                        movement_threshold=config.movement_threshold,
                    )
                    measurements.append(measurement)
                    kinds.append(kind)
                    if kind is ScrollAttemptKind.INEFFECTIVE:
                        confirmations = 0
                        if config.abort_on_ineffective:
                            return ObservedScrollResult(
                                outcome=ObservedScrollOutcome.INEFFECTIVE_GESTURE,
                                final_snapshot=current,
                                attempts=tuple(measurements),
                                attempt_kinds=tuple(kinds),
                                effective_gesture_count=effective_count,
                                confirmation_count=confirmations,
                                error="ineffective_gesture",
                            )
                        continue
                    effective_count += 1
                    if kind is ScrollAttemptKind.EDGE_CANDIDATE:
                        confirmations += 1
                    else:
                        confirmations = 0
                    if confirmations >= config.required_confirmations:
                        return ObservedScrollResult(
                            outcome=ObservedScrollOutcome.EDGE_REACHED,
                            final_snapshot=current,
                            attempts=tuple(measurements),
                            attempt_kinds=tuple(kinds),
                            effective_gesture_count=effective_count,
                            confirmation_count=confirmations,
                        )
        except RuntimeWaitTimeout as error:
            return self._failure_result(
                ObservedScrollOutcome.TIMEOUT,
                current,
                measurements,
                kinds,
                effective_count,
                confirmations,
                error,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failure_result(
                ObservedScrollOutcome.FAILED,
                current,
                measurements,
                kinds,
                effective_count,
                confirmations,
                error,
            )

        return ObservedScrollResult(
            outcome=ObservedScrollOutcome.LIMIT_REACHED,
            final_snapshot=current,
            attempts=tuple(measurements),
            attempt_kinds=tuple(kinds),
            effective_gesture_count=effective_count,
            confirmation_count=confirmations,
            error="scroll_limit_reached",
        )

    def _measure_attempt(
        self,
        before: RuntimeSnapshot,
        swipe: Swipe,
        *,
        detector: ViewportMotionDetector,
        is_compatible: Callable[[RuntimeSnapshot], bool],
        abort_if: Callable[[RuntimeSnapshot], bool],
        timeout: float,
        settle_for: float,
        executor: _SwipeExecutor,
    ) -> tuple[RuntimeSnapshot, ScrollAttemptMeasurement]:
        samples: list[FrameSnapshot] = []
        future = executor.submit(self.actions.execute, swipe, before.geometry)

        def action_finished_in_context(snapshot: RuntimeSnapshot) -> bool:
            samples.append(snapshot.frame)
            if future.done():
                error = future.exception()
                if error is not None:
                    raise error
            return future.done() and is_compatible(snapshot)

        settled = self.observer.wait_until(
            action_finished_in_context,
            after_sequence=before.sequence,
            timeout=timeout,
            abort_if=abort_if,
            stable_for=settle_for,
        )
        future.result()
        return (
            settled,
            detector.measure_transition(before.frame, samples, settled.frame),
        )

    @staticmethod
    def _failure_result(
        outcome: ObservedScrollOutcome,
        current: RuntimeSnapshot,
        measurements: list[ScrollAttemptMeasurement],
        kinds: list[ScrollAttemptKind],
        effective_count: int,
        confirmations: int,
        error: Exception,
    ) -> ObservedScrollResult:
        return ObservedScrollResult(
            outcome=outcome,
            final_snapshot=current,
            attempts=tuple(measurements),
            attempt_kinds=tuple(kinds),
            effective_gesture_count=effective_count,
            confirmation_count=confirmations,
            error=f"{type(error).__name__}: {error}",
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


def _normalized_threshold(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return float(value)


__all__ = (
    "ObservedScroll",
    "ObservedScrollConfig",
    "ObservedScrollOutcome",
    "ObservedScrollResult",
    "ScrollAttemptKind",
    "ScrollAttemptMeasurement",
    "ViewportMotionDetector",
)
