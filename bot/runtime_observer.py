"""Fresh-frame runtime observation over Capture -> Perception -> Resolver."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Callable, Protocol

from bot.action_executor import FrameGeometry
from bot.event_context import event_context, operation_scope
from bot.event_log import EventSink, record_best_effort
from bot.failure_cause import FailureCause
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.perception.black_market import (
    BLACK_MARKET_GOLD_OBSERVATION,
    BLACK_MARKET_PURCHASED_OBSERVATION,
    BLACK_MARKET_SLOT_COUNT,
)
from bot.state import ResolvedState
from bot.operation_control import (
    RuntimeWaitCancelled, OperationControl, OperationBudgetExpired, check_operation,
    current_control, operation_phase, control_scope,
)


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
        state = snapshot.state
        super().__init__(
            f"runtime wait aborted by incompatible sequence {snapshot.sequence}: "
            f"status={state.status.value} base={state.base_context} "
            f"overlays={list(state.overlays)}"
        )


class RuntimeEvidenceRejected(RuntimeError):
    """Evidence lost an explicitly required provenance or freshness contract."""


@dataclass(frozen=True)
class RuntimeEvidenceRequirements:
    """Opt-in provenance/age/coverage gates, checked before and after use.

    Capture timestamps and ``now`` must share the dispatch monotonic clock.
    Coverage names are supplied by the perception owner, never inferred from
    missing observations. Missing required metadata fails closed.
    """

    source_id: str | None = None
    captured_after: float | None = None
    max_age: float | None = None
    required_coverage: frozenset[str] = frozenset()

    def __post_init__(self):
        if self.source_id is not None and (not isinstance(self.source_id, str) or not self.source_id):
            raise ValueError("source_id must be a non-empty string or None")
        if self.captured_after is not None:
            _non_negative_duration(self.captured_after, "captured_after")
        if self.max_age is not None:
            _positive_duration(self.max_age, "max_age")
        if isinstance(self.required_coverage, (str, bytes)):
            raise ValueError("required_coverage must be a collection of capability names")
        object.__setattr__(self, "required_coverage", frozenset(self.required_coverage))
        if any(not isinstance(name, str) or not name for name in self.required_coverage):
            raise ValueError("required_coverage must contain non-empty capability names")

    def accepts(self, snapshot: RuntimeSnapshot, now: float) -> bool:
        return (
            (self.source_id is None or snapshot.frame.source_id == self.source_id)
            and (self.captured_after is None or snapshot.timestamp > self.captured_after)
            and (self.max_age is None or 0 <= now - snapshot.timestamp <= self.max_age)
            and (not self.required_coverage or (
                snapshot.observations.coverage is not None
                and self.required_coverage <= snapshot.observations.coverage
            ))
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
        events: EventSink | None = None,
        metrics_clock: Callable[[], float] = time.perf_counter,
        snapshot_consumer: Callable[[RuntimeSnapshot], None] | None = None,
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
        self.events = events
        self._metrics_clock = metrics_clock
        self._snapshot_consumer = snapshot_consumer
        self._analysis_context = None
        self._analysis_count = 0
        self._analysis_elapsed = 0.0
        self._analysis_max = 0.0
        self._analysis_errors = 0
        self._analysis_first_sequence = None
        self._analysis_last_sequence = None

    def observe(self) -> RuntimeSnapshot:
        """Observe exactly one latest frame without sending device input."""

        with operation_phase("observation"):
            return self._observe()

    def _observe(self) -> RuntimeSnapshot:
        frame = self.source.get_frame()
        check_operation()
        started = self._metrics_now()
        failed = False
        try:
            batch = self.perception.analyze(frame)
            check_operation()
        except BaseException:
            failed = True
            raise
        finally:
            self._record_analysis(frame.sequence, max(0.0, self._metrics_now() - started), failed)
        state = self.resolver.resolve(batch)
        check_operation()
        snapshot = RuntimeSnapshot(
            frame=frame,
            observations=batch,
            state=state,
            facts=_facts_from(batch),
            geometry=FrameGeometry.from_frame(frame.image),
        )
        try:
            if self._snapshot_consumer is not None:
                self._snapshot_consumer(snapshot)
        except Exception:
            pass
        return snapshot

    def _metrics_now(self) -> float:
        try:
            return self._metrics_clock()
        except Exception:
            return 0.0

    def _record_analysis(self, sequence, elapsed, failed):
        context = event_context()
        if context != self._analysis_context:
            self.flush_analysis_metrics()
            self._analysis_context = context
        if self._analysis_count == 0:
            self._analysis_first_sequence = sequence
        self._analysis_last_sequence = sequence
        self._analysis_count += 1
        self._analysis_elapsed += elapsed
        self._analysis_max = max(self._analysis_max, elapsed)
        self._analysis_errors += int(failed)
        if self._analysis_count >= 64:
            self.flush_analysis_metrics()

    def flush_analysis_metrics(self):
        """Flush a bounded aggregate, retaining the context where work occurred."""
        if self._analysis_count:
            record_best_effort(
                self.events, "perception.analyze_summary",
                **(self._analysis_context or {}),
                analyze_count=self._analysis_count, analyze_elapsed=self._analysis_elapsed,
                analyze_max_elapsed=self._analysis_max, analyze_error_count=self._analysis_errors,
                first_sequence=self._analysis_first_sequence, last_sequence=self._analysis_last_sequence,
            )
        self._analysis_count = self._analysis_errors = 0
        self._analysis_elapsed = self._analysis_max = 0.0

    def scoped(self, perception: Perception) -> RuntimeObserver:
        """Share source/resolver/timing while narrowing the perception engine.

        Experimental seam for single-transition scoping: the returned
        observer reads the same frames with the same waits and emits the
        same event names through the same sink and snapshot consumer.
        Only the detector set per analyzed frame changes.
        """

        if not callable(getattr(perception, "analyze", None)):
            raise ValueError("perception must provide analyze(snapshot)")
        return RuntimeObserver(
            self.source,
            perception,
            self.resolver,
            poll_interval=self.poll_interval,
            clock=self._clock,
            sleeper=self._sleeper,
            events=self.events,
            metrics_clock=self._metrics_clock,
            snapshot_consumer=self._snapshot_consumer,
        )

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        stable_for: float = 0.0,
        evidence: RuntimeEvidenceRequirements | None = None,
        deadline: float | None = None,
    ) -> RuntimeSnapshot:
        control = OperationControl(
            cancel_requested=cancel_requested, clock=self._clock, parent=current_control(),
        )
        with control_scope(control):
            return self._wait_until(
                condition, after_sequence=after_sequence, timeout=timeout,
                abort_if=abort_if, cancel_requested=cancel_requested,
                stable_for=stable_for, evidence=evidence, deadline=deadline,
            )

    def _wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        stable_for: float = 0.0,
        evidence: RuntimeEvidenceRequirements | None = None,
        deadline: float | None = None,
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
        if cancel_requested is not None and not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        if evidence is not None and not isinstance(evidence, RuntimeEvidenceRequirements):
            raise ValueError("evidence must be RuntimeEvidenceRequirements or None")
        if deadline is not None:
            _non_negative_duration(deadline, "deadline")
        after = _sequence(after_sequence)
        duration = _positive_duration(timeout, "timeout")
        stability = _non_negative_duration(stable_for, "stable_for")
        strict_deadline = deadline is not None
        deadline = min(self._clock() + duration, deadline) if deadline is not None else self._clock() + duration
        last_fresh: RuntimeSnapshot | None = None
        stable_since: float | None = None
        last_evaluated_sequence: int | None = None

        polls = fresh_count = 0
        started = self._metrics_now()
        outcome = "failed"
        failure = None
        with operation_scope("runtime_wait"):
            try:
                with operation_phase("observation"):
                    while True:
                        check_operation()
                        if strict_deadline and self._clock() >= deadline:
                            raise RuntimeWaitTimeout(after_sequence=after, timeout=duration, last_snapshot=last_fresh)
                        polls += 1
                        snapshot = self.observe()
                        check_operation()
                        if snapshot.sequence > after and (
                            last_evaluated_sequence is None
                            or snapshot.sequence > last_evaluated_sequence
                        ) and (evidence is None or evidence.accepts(snapshot, self._clock())):
                            fresh_count += 1
                            last_fresh = snapshot
                            last_evaluated_sequence = snapshot.sequence
                            aborted = abort_if is not None and abort_if(snapshot)
                            check_operation()
                            if aborted and (evidence is None or evidence.accepts(snapshot, self._clock())):
                                raise RuntimeWaitAborted(snapshot)
                            eligible = evidence is None or evidence.accepts(snapshot, self._clock())
                            matched = condition(snapshot) if eligible else False
                            check_operation()
                            if evidence is not None and not evidence.accepts(snapshot, self._clock()):
                                matched = False
                                last_fresh = None
                            if matched and (not strict_deadline or self._clock() < deadline):
                                if stable_since is None:
                                    stable_since = snapshot.timestamp
                                if snapshot.timestamp - stable_since >= stability:
                                    outcome = "completed"
                                    return snapshot
                            else:
                                stable_since = None
                        elif evidence is not None and not evidence.accepts(snapshot, self._clock()):
                            stable_since = None

                        remaining = deadline - self._clock()
                        if remaining <= 0:
                            raise RuntimeWaitTimeout(
                                after_sequence=after,
                                timeout=duration,
                                last_snapshot=last_fresh,
                            )
                        control = current_control()
                        if control is not None:
                            check_operation()
                            remaining = min(remaining, control.remaining())
                        self._sleeper(min(self.poll_interval, remaining))
            except BaseException as error:
                outcome = (
                    "timeout" if isinstance(error, (RuntimeWaitTimeout, OperationBudgetExpired)) else
                    "cancelled" if isinstance(error, RuntimeWaitCancelled) else
                    "aborted" if isinstance(error, RuntimeWaitAborted) else "failed"
                )
                failure = FailureCause.from_error(
                    error, kind=outcome,
                    sequence=last_fresh.sequence if last_fresh else None,
                )
                # Exception metadata is additive; successful callers still get a snapshot.
                if isinstance(error, (RuntimeWaitTimeout, RuntimeWaitAborted, RuntimeWaitCancelled)):
                    error.failure = failure
                    error.poll_count = polls
                    error.elapsed = max(0.0, self._metrics_now() - started)
                raise
            finally:
                self.flush_analysis_metrics()
                record_best_effort(
                    self.events, "runtime_wait.completed", outcome=outcome,
                    elapsed=max(0.0, self._metrics_now() - started),
                    poll_count=polls, fresh_count=fresh_count,
                    after_sequence=after, final_sequence=last_fresh.sequence if last_fresh else None,
                    timeout=duration, stable_for=stability,
                    failure=failure.payload() if failure else None,
                )


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
    "RuntimeEvidenceRequirements",
    "RuntimeEvidenceRejected",
    "RuntimeObserver",
    "RuntimeSnapshot",
    "RuntimeWaitAborted",
    "RuntimeWaitCancelled",
    "RuntimeWaitTimeout",
)
