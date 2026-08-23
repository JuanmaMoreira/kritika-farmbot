"""Manual, opt-in end-to-end smoke test for live perception hardware.

Importing this module is deliberately inert. Environment loading, asset IO,
ADB operations and capture startup only happen from :func:`main`.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from bot.adb import AdbError, AdbClient
from bot.capture import CaptureError, FrameSnapshot, ScrcpyFrameSource
from bot.catalog import build_default_resolver
from bot.config import RuntimeConfig
from bot.observations import ObservationBatch
from bot.perception import LocalCvDetection, PerceptionEngine, build_default_perception
from bot.resolver import ContextResolver
from bot.runtime import build_adb_client, build_frame_source
from bot.state import ResolvedState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSES_PER_SECOND = 3.0
DEFAULT_HEARTBEAT_SECONDS = 5.0
NEW_FRAME_TIMEOUT_SECONDS = 5.0
POLL_SECONDS = 0.02

STAGES = {
    "1": "Lobby",
    "2": "Character Select",
    "3": "Lobby reentry",
    "4": "Black Market",
    "5": "Purchase Confirmation",
    "6": "Unsupported / expected UNKNOWN",
}


@dataclass(frozen=True)
class DistributionSummary:
    count: int
    minimum: float
    median: float
    mean: float
    maximum: float


@dataclass
class MetricAccumulator:
    """Small in-memory accumulator suitable for one diagnostic session."""

    samples: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.samples.append(float(value))

    def summary(self) -> DistributionSummary | None:
        if not self.samples:
            return None
        return DistributionSummary(
            count=len(self.samples),
            minimum=min(self.samples),
            median=statistics.median(self.samples),
            mean=statistics.fmean(self.samples),
            maximum=max(self.samples),
        )


StateSignature = tuple[str, str | None, tuple[str, ...], tuple[str, ...]]


def state_signature(state: ResolvedState) -> StateSignature:
    """Return state identity without frame-specific sequence or timestamp."""

    return (
        state.status.value,
        state.base_context,
        state.overlays,
        state.base_candidates,
    )


def observation_signature(batch: ObservationBatch) -> tuple[str, ...]:
    """Represent the emitted observation set without noisy confidence changes."""

    return tuple(sorted({observation.name for observation in batch.observations}))


EventSignature = tuple[StateSignature, tuple[str, ...]]


def should_emit_event(
    previous: EventSignature | None,
    current: EventSignature,
    *,
    now: float,
    last_emitted_at: float | None,
    heartbeat_seconds: float,
) -> bool:
    """Emit on semantic change or after a bounded quiet heartbeat."""

    return (
        previous != current
        or last_emitted_at is None
        or now - last_emitted_at >= heartbeat_seconds
    )


@dataclass
class StageStability:
    analyses: int = 0
    longest_consecutive: int = 0
    current_consecutive: int = 0
    current_signature: StateSignature | None = None
    counts: Counter[StateSignature] = field(default_factory=Counter)

    def record(self, signature: StateSignature) -> int:
        self.analyses += 1
        self.counts[signature] += 1
        if signature == self.current_signature:
            self.current_consecutive += 1
        else:
            self.current_signature = signature
            self.current_consecutive = 1
        self.longest_consecutive = max(
            self.longest_consecutive, self.current_consecutive
        )
        return self.current_consecutive

    @property
    def dominant_signature(self) -> StateSignature | None:
        if not self.counts:
            return None
        return self.counts.most_common(1)[0][0]


@dataclass(frozen=True)
class FrameAnalysis:
    snapshot: FrameSnapshot
    batch: ObservationBatch
    state: ResolvedState
    readings: tuple[LocalCvDetection, ...]
    perception_seconds: float
    resolver_seconds: float
    snapshot_to_state_seconds: float


@dataclass(frozen=True)
class CleanupReport:
    source_stopped: bool
    forward_removed: bool


@dataclass
class SessionReport:
    adb_state: str
    started_at: float
    finished_at: float = 0.0
    frame_width: int = 0
    frame_height: int = 0
    first_sequence: int | None = None
    last_sequence: int | None = None
    analysis_count: int = 0
    exit_reason: str = "normal"
    cleanup: CleanupReport | None = None
    perception_latency: MetricAccumulator = field(default_factory=MetricAccumulator)
    resolver_latency: MetricAccumulator = field(default_factory=MetricAccumulator)
    total_latency: MetricAccumulator = field(default_factory=MetricAccumulator)
    confidence: dict[str, MetricAccumulator] = field(default_factory=dict)
    raw_scores: dict[str, MetricAccumulator] = field(default_factory=dict)
    stages: dict[str, StageStability] = field(default_factory=dict)
    stage_confidence: dict[str, dict[str, MetricAccumulator]] = field(
        default_factory=dict
    )
    stage_raw_scores: dict[str, dict[str, MetricAccumulator]] = field(
        default_factory=dict
    )


def analyze_snapshot(
    snapshot: FrameSnapshot,
    perception: PerceptionEngine,
    resolver: ContextResolver,
    *,
    perf_clock: Callable[[], float] = time.perf_counter,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> FrameAnalysis:
    """Run the production pipeline, then gather optional detector diagnostics."""

    perception_started = perf_clock()
    batch = perception.analyze(snapshot)
    perception_finished = perf_clock()
    state = resolver.resolve(batch)
    resolved_at = perf_clock()

    readings: list[LocalCvDetection] = []
    for detector in perception.detectors:
        measure = getattr(detector, "measure", None)
        if callable(measure):
            reading = measure(snapshot.image)
            if isinstance(reading, LocalCvDetection):
                readings.append(reading)

    return FrameAnalysis(
        snapshot=snapshot,
        batch=batch,
        state=state,
        readings=tuple(readings),
        perception_seconds=perception_finished - perception_started,
        resolver_seconds=resolved_at - perception_finished,
        snapshot_to_state_seconds=max(0.0, monotonic_clock() - snapshot.timestamp),
    )


def _wait_for_newest_frame(
    source: ScrcpyFrameSource,
    previous_sequence: int | None,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> FrameSnapshot:
    deadline = clock() + NEW_FRAME_TIMEOUT_SECONDS
    while True:
        snapshot = source.get_frame()
        if previous_sequence is None or snapshot.sequence > previous_sequence:
            return snapshot
        if clock() >= deadline:
            raise CaptureError(
                f"No frame newer than sequence {previous_sequence} arrived within "
                f"{NEW_FRAME_TIMEOUT_SECONDS:g}s"
            )
        sleeper(POLL_SECONDS)


def _read_key() -> str | None:
    """Read one console key without blocking on Windows; inert elsewhere."""

    if sys.platform != "win32":
        return None
    import msvcrt

    if not msvcrt.kbhit():
        return None
    key = msvcrt.getwch()
    if key in {"\x00", "\xe0"} and msvcrt.kbhit():
        msvcrt.getwch()
        return None
    return key.lower()


def _handle_key(
    key: str | None,
    current_stage: str,
    emit: Callable[[str], None],
) -> tuple[str, bool]:
    if key == "q":
        return current_stage, True
    if key in STAGES:
        selected = STAGES[key]
        if selected != current_stage:
            emit(f"\n[stage] {selected}")
        return selected, False
    return current_stage, False


def _sleep_until_analysis(
    target: float,
    current_stage: str,
    *,
    key_reader: Callable[[], str | None],
    emit: Callable[[str], None],
    clock: Callable[[], float] = time.monotonic,
) -> tuple[str, bool]:
    while True:
        current_stage, quit_requested = _handle_key(
            key_reader(), current_stage, emit
        )
        if quit_requested:
            return current_stage, True
        remaining = target - clock()
        if remaining <= 0:
            return current_stage, False
        time.sleep(min(0.05, remaining))


def _record_analysis(
    report: SessionReport, analysis: FrameAnalysis, stage: str
) -> int:
    snapshot = analysis.snapshot
    if report.first_sequence is None:
        report.first_sequence = snapshot.sequence
        report.frame_width = snapshot.width
        report.frame_height = snapshot.height
    report.last_sequence = snapshot.sequence
    report.analysis_count += 1
    report.perception_latency.add(analysis.perception_seconds)
    report.resolver_latency.add(analysis.resolver_seconds)
    report.total_latency.add(analysis.snapshot_to_state_seconds)
    for reading in analysis.readings:
        report.confidence.setdefault(
            reading.observation_name, MetricAccumulator()
        ).add(reading.semantic_confidence)
        report.raw_scores.setdefault(
            reading.observation_name, MetricAccumulator()
        ).add(reading.raw_match_score)
        report.stage_confidence.setdefault(stage, {}).setdefault(
            reading.observation_name, MetricAccumulator()
        ).add(reading.semantic_confidence)
        report.stage_raw_scores.setdefault(stage, {}).setdefault(
            reading.observation_name, MetricAccumulator()
        ).add(reading.raw_match_score)
    stability = report.stages.setdefault(stage, StageStability())
    return stability.record(state_signature(analysis.state))


def _format_state(signature: StateSignature) -> str:
    status, base, overlays, candidates = signature
    parts = [status.upper(), f"base={base or '-'}"]
    parts.append(f"overlays={list(overlays)}")
    if candidates:
        parts.append(f"candidates={list(candidates)}")
    return " ".join(parts)


def _emit_analysis(
    analysis: FrameAnalysis,
    *,
    elapsed: float,
    stage: str,
    consecutive: int,
    emit: Callable[[str], None],
) -> None:
    emitted = ", ".join(
        f"{item.name}={item.confidence:.3f}"
        for item in analysis.batch.observations
    ) or "none"
    emit(f"\n[{elapsed:8.3f}] seq={analysis.snapshot.sequence} stage={stage}")
    emit(f"  observations: {emitted}")
    for reading in analysis.readings:
        emit(
            f"  score: {reading.observation_name} "
            f"raw={reading.raw_match_score:.4f} "
            f"confidence={reading.semantic_confidence:.3f}"
        )
    emit(
        f"  resolved: {_format_state(state_signature(analysis.state))} "
        f"consecutive={consecutive}"
    )
    emit(
        "  latency_ms: "
        f"perception={analysis.perception_seconds * 1000:.2f} "
        f"resolver={analysis.resolver_seconds * 1000:.3f} "
        f"snapshot_to_state={analysis.snapshot_to_state_seconds * 1000:.2f}"
    )


def _source_forward_present(adb: AdbClient, source: ScrcpyFrameSource) -> bool:
    for rule in adb.list_forwards():
        fields = rule.split()
        if (
            len(fields) >= 2
            and fields[0] == adb.serial
            and fields[1] == source.local_endpoint
        ):
            return True
    return False


def run_session(
    *,
    adb: AdbClient,
    source: ScrcpyFrameSource,
    perception: PerceptionEngine,
    resolver: ContextResolver,
    adb_state: str,
    analyses_per_second: float,
    heartbeat_seconds: float,
    duration_seconds: float | None,
    key_reader: Callable[[], str | None] = _read_key,
    emit: Callable[[str], None] = print,
) -> SessionReport:
    """Run a bounded-rate live diagnostic until q, Ctrl+C or duration expiry."""

    interval = 1.0 / analyses_per_second
    started_at = time.monotonic()
    report = SessionReport(adb_state=adb_state, started_at=started_at)
    current_stage = STAGES["1"]
    previous_sequence: int | None = None
    previous_event: EventSignature | None = None
    last_emitted_at: float | None = None
    next_analysis_at = started_at

    emit("Live perception smoke (manual / opt-in; no Android input is sent)")
    emit("  1. Start on Lobby")
    emit("  2. Navigate manually; press 1-6 when each stage is stable")
    emit("  3. Observe event-driven output and occasional heartbeats")
    emit("  4. Press q or Ctrl+C to exit")
    emit("  keys: 1 Lobby | 2 Character Select | 3 Lobby reentry")
    emit("        4 Black Market | 5 Purchase popup | 6 unsupported / UNKNOWN")
    emit(f"\n[stage] {current_stage}")

    try:
        with source:
            while True:
                current_stage, quit_requested = _sleep_until_analysis(
                    next_analysis_at,
                    current_stage,
                    key_reader=key_reader,
                    emit=emit,
                )
                if quit_requested:
                    report.exit_reason = "q"
                    break
                now = time.monotonic()
                if duration_seconds is not None and now - started_at >= duration_seconds:
                    report.exit_reason = "duration"
                    break

                snapshot = _wait_for_newest_frame(source, previous_sequence)
                if previous_sequence is not None and snapshot.sequence <= previous_sequence:
                    raise CaptureError("Frame sequence did not increase")
                previous_sequence = snapshot.sequence
                analysis = analyze_snapshot(snapshot, perception, resolver)
                consecutive = _record_analysis(report, analysis, current_stage)
                event = (
                    state_signature(analysis.state),
                    observation_signature(analysis.batch),
                )
                now = time.monotonic()
                if should_emit_event(
                    previous_event,
                    event,
                    now=now,
                    last_emitted_at=last_emitted_at,
                    heartbeat_seconds=heartbeat_seconds,
                ):
                    _emit_analysis(
                        analysis,
                        elapsed=now - started_at,
                        stage=current_stage,
                        consecutive=consecutive,
                        emit=emit,
                    )
                    last_emitted_at = now
                previous_event = event
                next_analysis_at = max(next_analysis_at + interval, now)
    except KeyboardInterrupt:
        report.exit_reason = "ctrl_c"

    report.finished_at = time.monotonic()
    report.cleanup = CleanupReport(
        source_stopped=not source.is_running,
        forward_removed=not _source_forward_present(adb, source),
    )
    if not report.cleanup.source_stopped:
        raise CaptureError("Capture source still reports running after shutdown")
    if not report.cleanup.forward_removed:
        raise CaptureError(f"Forward {source.local_endpoint} remains after shutdown")
    return report


def _format_distribution(summary: DistributionSummary | None, scale: float) -> str:
    if summary is None:
        return "no samples"
    return (
        f"n={summary.count} min={summary.minimum * scale:.3f} "
        f"median={summary.median * scale:.3f} mean={summary.mean * scale:.3f} "
        f"max={summary.maximum * scale:.3f}"
    )


def print_report(report: SessionReport, emit: Callable[[str], None] = print) -> None:
    duration = max(0.0, report.finished_at - report.started_at)
    emit("\n=== Live perception smoke summary ===")
    emit(f"ADB state: {report.adb_state}")
    emit(f"scrcpy-server protocol: {ScrcpyFrameSource.SCRCPY_VERSION}")
    emit(f"duration: {duration:.2f}s")
    emit(f"frame: {report.frame_width}x{report.frame_height}")
    emit(
        f"analyses: {report.analysis_count}; sequence: "
        f"{report.first_sequence} -> {report.last_sequence}; exit={report.exit_reason}"
    )
    emit("latency ms:")
    emit(
        "  perception: "
        + _format_distribution(report.perception_latency.summary(), 1000.0)
    )
    emit(
        "  resolver: "
        + _format_distribution(report.resolver_latency.summary(), 1000.0)
    )
    emit(
        "  snapshot_to_state: "
        + _format_distribution(report.total_latency.summary(), 1000.0)
    )
    emit("detector confidence (semantic; raw score follows):")
    for name in sorted(report.confidence):
        confidence = _format_distribution(report.confidence[name].summary(), 1.0)
        raw = _format_distribution(report.raw_scores[name].summary(), 1.0)
        emit(f"  {name}: confidence {confidence}; raw {raw}")
    emit("manual stage stability:")
    for stage, stability in report.stages.items():
        dominant = stability.dominant_signature
        rendered = "no result" if dominant is None else _format_state(dominant)
        emit(
            f"  {stage}: analyses={stability.analyses} "
            f"longest_consecutive={stability.longest_consecutive} "
            f"dominant={rendered}"
        )
        for name in sorted(report.stage_confidence.get(stage, {})):
            confidence = _format_distribution(
                report.stage_confidence[stage][name].summary(), 1.0
            )
            raw = _format_distribution(
                report.stage_raw_scores[stage][name].summary(), 1.0
            )
            emit(f"    {name}: confidence {confidence}; raw {raw}")
    cleanup = report.cleanup
    emit(
        "cleanup: receiver thread/socket/process released by context manager; "
        f"source_stopped={cleanup.source_stopped if cleanup else False}; "
        f"forward_removed={cleanup.forward_removed if cleanup else False}"
    )


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a number") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the production perception pipeline on live scrcpy frames."
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="dotenv file loaded explicitly by main (default: project .env)",
    )
    parser.add_argument(
        "--hz",
        type=_positive_float,
        default=DEFAULT_ANALYSES_PER_SECOND,
        help=f"analyses per second (default: {DEFAULT_ANALYSES_PER_SECOND:g})",
    )
    parser.add_argument(
        "--heartbeat",
        type=_positive_float,
        default=DEFAULT_HEARTBEAT_SECONDS,
        help=f"quiet heartbeat seconds (default: {DEFAULT_HEARTBEAT_SECONDS:g})",
    )
    parser.add_argument(
        "--duration",
        type=_positive_float,
        default=None,
        help="optional maximum session duration in seconds",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
        source = build_frame_source(config, adb_client=adb)
        perception = build_default_perception()
        resolver = build_default_resolver()

        adb_state = adb.get_state()
        if adb_state != "device":
            raise RuntimeError(f"ADB state is {adb_state!r}, expected 'device'")
        report = run_session(
            adb=adb,
            source=source,
            perception=perception,
            resolver=resolver,
            adb_state=adb_state,
            analyses_per_second=args.hz,
            heartbeat_seconds=args.heartbeat,
            duration_seconds=args.duration,
        )
    except (AdbError, CaptureError, RuntimeError, ValueError, OSError) as error:
        print(f"[smoke] FAILED: {error}", file=sys.stderr)
        return 1

    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
