"""Fresh-frame runtime observation over Capture -> Perception -> Resolver."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Callable, Protocol

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.perception.black_market import (
    BLACK_MARKET_GOLD_OBSERVATION,
    BLACK_MARKET_PURCHASED_OBSERVATION,
    BLACK_MARKET_SLOT_COUNT,
)
from bot.state import ResolvedState


class FrameSource(Protocol):
    def get_frame(self) -> FrameSnapshot: ...


class Perception(Protocol):
    def analyze(self, snapshot: FrameSnapshot) -> ObservationBatch: ...


class Resolver(Protocol):
    def resolve(self, observations: ObservationBatch) -> ResolvedState: ...


@dataclass(frozen=True)
class RuntimeFacts:
    """Flow-facing semantic facts extracted from one observation batch."""

    gold_slots: frozenset[int] = frozenset()
    purchased_slots: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        for name in ("gold_slots", "purchased_slots"):
            values = frozenset(getattr(self, name))
            if any(
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or not 0 <= value < BLACK_MARKET_SLOT_COUNT
                for value in values
            ):
                raise ValueError(f"{name} must contain slot indices in [0, 9]")
            object.__setattr__(self, name, frozenset(int(value) for value in values))


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Resolved state, semantic evidence and facts from the same fresh frame."""

    frame: FrameSnapshot
    observations: ObservationBatch
    state: ResolvedState
    facts: RuntimeFacts
    geometry: FrameGeometry

    def __post_init__(self) -> None:
        if not isinstance(self.frame, FrameSnapshot):
            raise ValueError("frame must be a FrameSnapshot")
        if not isinstance(self.observations, ObservationBatch):
            raise ValueError("observations must be ObservationBatch")
        if not isinstance(self.state, ResolvedState):
            raise ValueError("state must be ResolvedState")
        if not isinstance(self.facts, RuntimeFacts):
            raise ValueError("facts must be RuntimeFacts")
        if not isinstance(self.geometry, FrameGeometry):
            raise ValueError("geometry must be FrameGeometry")
        if (
            self.frame.sequence != self.observations.sequence
            or self.frame.timestamp != self.observations.timestamp
            or self.observations.sequence != self.state.sequence
            or self.observations.timestamp != self.state.timestamp
        ):
            raise ValueError("frame, observations and state must identify the same frame")
        if FrameGeometry.from_frame(self.frame.image) != self.geometry:
            raise ValueError("geometry must be derived from the same frame")

    @property
    def sequence(self) -> int:
        return self.observations.sequence

    @property
    def timestamp(self) -> float:
        return self.observations.timestamp


class RuntimeWaitTimeout(TimeoutError):
    """A bounded wait ended without a matching fresh snapshot."""

    def __init__(
        self,
        *,
        after_sequence: int,
        timeout: float,
        last_snapshot: RuntimeSnapshot | None,
    ) -> None:
        self.after_sequence = after_sequence
        self.timeout = timeout
        self.last_snapshot = last_snapshot
        super().__init__(
            f"no matching runtime snapshot after sequence {after_sequence} "
            f"within {timeout:g}s"
        )


class RuntimeWaitAborted(RuntimeError):
    """A fresh snapshot matched an explicitly incompatible condition."""

    def __init__(self, snapshot: RuntimeSnapshot) -> None:
        self.snapshot = snapshot
        super().__init__(
            f"runtime wait aborted by incompatible sequence {snapshot.sequence}"
        )


class RuntimeObserver:
    """Analyze current frames and provide bounded waits that reject stale identity."""

    def __init__(
        self,
        source: FrameSource,
        perception: Perception,
        resolver: Resolver,
        *,
        poll_interval: float = 0.02,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(getattr(source, "get_frame", None)):
            raise ValueError("source must provide get_frame()")
        if not callable(getattr(perception, "analyze", None)):
            raise ValueError("perception must provide analyze(snapshot)")
        if not callable(getattr(resolver, "resolve", None)):
            raise ValueError("resolver must provide resolve(batch)")
        self.source = source
        self.perception = perception
        self.resolver = resolver
        self.poll_interval = _positive_duration(poll_interval, "poll_interval")
        self._clock = clock
        self._sleeper = sleeper

    def observe(self) -> RuntimeSnapshot:
        """Observe exactly one latest frame without sending device input."""

        frame = self.source.get_frame()
        batch = self.perception.analyze(frame)
        state = self.resolver.resolve(batch)
        return RuntimeSnapshot(
            frame=frame,
            observations=batch,
            state=state,
            facts=_facts_from(batch),
            geometry=FrameGeometry.from_frame(frame.image),
        )

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot:
        """Wait for a condition only on sequences newer than an action baseline.

        ``stable_for`` requires the condition to remain true across distinct
        fresh snapshots for the requested capture-timestamp duration. This is
        runtime readiness, not resolver hysteresis or voting.
        """

        if not callable(condition):
            raise ValueError("condition must be callable")
        if abort_if is not None and not callable(abort_if):
            raise ValueError("abort_if must be callable")
        after = _sequence(after_sequence)
        duration = _positive_duration(timeout, "timeout")
        stability = _non_negative_duration(stable_for, "stable_for")
        deadline = self._clock() + duration
        last_fresh: RuntimeSnapshot | None = None
        stable_since: float | None = None
        last_evaluated_sequence: int | None = None

        while True:
            snapshot = self.observe()
            if snapshot.sequence > after and (
                last_evaluated_sequence is None
                or snapshot.sequence > last_evaluated_sequence
            ):
                last_fresh = snapshot
                last_evaluated_sequence = snapshot.sequence
                if abort_if is not None and abort_if(snapshot):
                    raise RuntimeWaitAborted(snapshot)
                if condition(snapshot):
                    if stable_since is None:
                        stable_since = snapshot.timestamp
                    if snapshot.timestamp - stable_since >= stability:
                        return snapshot
                else:
                    stable_since = None

            remaining = deadline - self._clock()
            if remaining <= 0:
                raise RuntimeWaitTimeout(
                    after_sequence=after,
                    timeout=duration,
                    last_snapshot=last_fresh,
                )
            self._sleeper(min(self.poll_interval, remaining))


def _facts_from(batch: ObservationBatch) -> RuntimeFacts:
    return RuntimeFacts(
        gold_slots=_slot_values(batch, BLACK_MARKET_GOLD_OBSERVATION),
        purchased_slots=_slot_values(
            batch, BLACK_MARKET_PURCHASED_OBSERVATION
        ),
    )


def _slot_values(batch: ObservationBatch, name: str) -> frozenset[int]:
    values = []
    for observation in batch.find(name):
        value = observation.value
        if (
            isinstance(value, bool)
            or not isinstance(value, Integral)
            or not 0 <= value < BLACK_MARKET_SLOT_COUNT
        ):
            raise ValueError(f"{name} observations must carry a valid slot index")
        values.append(int(value))
    return frozenset(values)


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


def _sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("after_sequence must be a non-negative integer")
    return int(value)


__all__ = (
    "RuntimeFacts",
    "RuntimeObserver",
    "RuntimeSnapshot",
    "RuntimeWaitAborted",
    "RuntimeWaitTimeout",
)
