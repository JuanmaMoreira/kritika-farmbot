"""Human-in-the-loop Perception Workbench v2.

This is a local development/teaching tool, not gameplay runtime. Importing the
module is inert: environment loading, asset IO, ADB, threads, session folders,
and OpenCV windows are created only from :func:`main`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import queue
import sys
import threading
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

import numpy as np

from bot.acquisition_vocabulary import (
    AcquisitionVocabulary,
    build_acquisition_vocabulary,
)
from bot.adb import AdbClient, AdbError
from bot.capture import CaptureError, FrameSnapshot, ScrcpyFrameSource
from bot.catalog import build_default_resolver
from bot.config import RuntimeConfig
from bot.human_input import (
    HumanGesture,
    HumanInputError,
    HumanInputObserver,
    HumanSwipe,
    HumanTap,
    UnknownGesture,
    relative_to_frame,
)
from bot.observations import ObservationBatch, validate_semantic_name
from bot.perception import LocalCvDetection, PerceptionEngine, build_default_perception
from bot.resolver import ContextResolver
from bot.runtime import build_adb_client, build_frame_source
from bot.state import ResolutionStatus, ResolvedState
from tools.smoke_perception import FrameAnalysis, analyze_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts" / "workbench"
SCHEMA_VERSION = "2.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0", SCHEMA_VERSION})
WORKBENCH_VERSION = "2"
WINDOW_NAME = "Perception Workbench v2"
UNKNOWN_LABEL = "UNKNOWN"
UNSET_LABEL = "UNSET"
OVERLAY_TOGGLE_KEY = "P"
WORKBENCH_VIDEO_BIT_RATE = 8_000_000
WORKBENCH_CAPTURE_FPS = 30
PREVIEW_WIDTH = 1356
PREVIEW_HEIGHT = 612
WORKBENCH_WINDOW_HEIGHT = 980


class Correctness(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    AMBIGUOUS = "ambiguous"
    UNLABELED = "unlabeled"


@dataclass(frozen=True)
class GroundTruthState:
    """Persistent human semantic declaration for the current screen."""

    base_confirmed: bool = False
    base_context: str | None = None
    overlays: frozenset[str] = frozenset()

    def select_base(self, label: str | None) -> "GroundTruthState":
        if label is not None:
            label = validate_semantic_name(label)
        return GroundTruthState(True, label, self.overlays)

    def clear(self) -> "GroundTruthState":
        return GroundTruthState()

    def toggle_overlay(self, label: str) -> "GroundTruthState":
        label = validate_semantic_name(label)
        overlays = set(self.overlays)
        overlays.symmetric_difference_update({label})
        return GroundTruthState(self.base_confirmed, self.base_context, frozenset(overlays))

    @property
    def display_base(self) -> str:
        if not self.base_confirmed:
            return UNSET_LABEL
        return self.base_context or UNKNOWN_LABEL

    def payload(self) -> dict[str, object]:
        return {
            "source": "human_confirmed" if self.base_confirmed else "unlabeled",
            "base_context": self.base_context,
            "base_is_unknown": self.base_confirmed and self.base_context is None,
            "overlays": sorted(self.overlays),
        }


def evaluate_correctness(
    human: GroundTruthState,
    predicted: ResolvedState,
) -> Correctness:
    """Derive correctness; predictions never become human labels."""

    if not human.base_confirmed:
        return Correctness.UNLABELED
    if predicted.status is ResolutionStatus.AMBIGUOUS:
        return Correctness.AMBIGUOUS
    predicted_base = (
        predicted.base_context
        if predicted.status is ResolutionStatus.RESOLVED
        else None
    )
    if predicted_base != human.base_context:
        return Correctness.MISMATCH
    if frozenset(predicted.overlays) != human.overlays:
        return Correctness.MISMATCH
    return Correctness.MATCH


def event_record(
    session_id: str,
    event_type: str,
    *,
    timestamp: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Build the common append-friendly event envelope."""

    if not session_id or not event_type or not timestamp:
        raise ValueError("session_id, event_type and timestamp are required")
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "payload": payload,
    }


def parse_event_record(record: object) -> dict[str, object]:
    """Validate the common envelope while accepting Workbench v1 sessions."""

    if not isinstance(record, dict):
        raise ValueError("Workbench event must be an object")
    if record.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError("unsupported Workbench event schema_version")
    if not all(record.get(field) for field in ("session_id", "event_type", "timestamp")):
        raise ValueError("Workbench event envelope is incomplete")
    if not isinstance(record.get("payload"), dict):
        raise ValueError("Workbench event payload must be an object")
    return record


def frame_fingerprint(frame: np.ndarray, *, sample_size: int = 32) -> np.ndarray:
    """Create a tiny grayscale fingerprint without ML or extra dependencies."""

    if (
        not isinstance(frame, np.ndarray)
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.size == 0
    ):
        raise ValueError("frame must be a non-empty HxWx3 ndarray")
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    y_indices = np.linspace(0, frame.shape[0] - 1, min(sample_size, frame.shape[0])).astype(int)
    x_indices = np.linspace(0, frame.shape[1] - 1, min(sample_size, frame.shape[1])).astype(int)
    sampled = frame[np.ix_(y_indices, x_indices)].astype(np.float32)
    return sampled.mean(axis=2)


def fingerprint_difference(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        return 255.0
    return float(np.mean(np.abs(first.astype(np.float32) - second.astype(np.float32))))


class EvidenceDeduplicator:
    """Cooldown + visual-difference gate with a bounded refresh interval."""

    def __init__(
        self,
        *,
        cooldown_seconds: float = 2.0,
        difference_threshold: float = 3.0,
        refresh_seconds: float = 8.0,
        max_per_key: int = 12,
    ) -> None:
        if cooldown_seconds <= 0 or difference_threshold < 0:
            raise ValueError("deduplication durations/threshold are invalid")
        if refresh_seconds < cooldown_seconds:
            raise ValueError("refresh_seconds must be >= cooldown_seconds")
        if max_per_key <= 0:
            raise ValueError("max_per_key must be positive")
        self.cooldown_seconds = float(cooldown_seconds)
        self.difference_threshold = float(difference_threshold)
        self.refresh_seconds = float(refresh_seconds)
        self.max_per_key = int(max_per_key)
        self._accepted: dict[str, tuple[float, np.ndarray]] = {}
        self._counts: Counter[str] = Counter()

    def should_accept(
        self,
        key: str,
        frame: np.ndarray,
        *,
        timestamp: float,
        force: bool = False,
    ) -> bool:
        fingerprint = frame_fingerprint(frame)
        if not force and self._counts[key] >= self.max_per_key:
            return False
        previous = self._accepted.get(key)
        accepted = force or previous is None
        if previous is not None and not accepted:
            previous_time, previous_fingerprint = previous
            elapsed = timestamp - previous_time
            accepted = elapsed >= self.refresh_seconds or (
                elapsed >= self.cooldown_seconds
                and fingerprint_difference(fingerprint, previous_fingerprint)
                >= self.difference_threshold
            )
        if accepted:
            self._accepted[key] = (float(timestamp), fingerprint)
            self._counts[key] += 1
        return accepted


@dataclass(frozen=True)
class WorkbenchFrame:
    snapshot: FrameSnapshot
    batch: ObservationBatch
    state: ResolvedState
    readings: tuple[LocalCvDetection, ...]
    human: GroundTruthState
    perception_seconds: float = 0.0
    resolver_seconds: float = 0.0
    analyzed_at: float = 0.0


@dataclass
class LiveMetrics:
    frame_age_ms: float = 0.0
    perception_ms: float = 0.0
    ui_display_ms: float = 0.0


@dataclass(frozen=True)
class PathComparison:
    input_unchanged: bool
    raw_scores_equal: bool
    smoke_readings: tuple[tuple[str, float], ...]
    workbench_readings: tuple[tuple[str, float], ...]


class FrameRingBuffer:
    """Small analyzed-frame ring used for deterministic gesture association."""

    def __init__(self, capacity: int = 24) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._frames: deque[WorkbenchFrame] = deque(maxlen=capacity)

    def add(self, frame: WorkbenchFrame) -> None:
        if not isinstance(frame, WorkbenchFrame):
            raise ValueError("frame must be a WorkbenchFrame")
        self._frames.append(frame)

    def before(self, timestamp: float) -> WorkbenchFrame | None:
        candidates = [item for item in self._frames if item.snapshot.timestamp <= timestamp]
        return max(candidates, key=lambda item: item.snapshot.timestamp, default=None)

    def after(self, timestamp: float) -> WorkbenchFrame | None:
        candidates = [item for item in self._frames if item.snapshot.timestamp >= timestamp]
        return min(candidates, key=lambda item: item.snapshot.timestamp, default=None)

    @property
    def latest(self) -> WorkbenchFrame | None:
        return self._frames[-1] if self._frames else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _state_payload(state: ResolvedState) -> dict[str, object]:
    return {
        "status": state.status.value,
        "base_context": state.base_context,
        "overlays": list(state.overlays),
        "base_candidates": list(state.base_candidates),
    }


def _observations_payload(batch: ObservationBatch) -> list[dict[str, object]]:
    return [
        {
            "name": item.name,
            "confidence": item.confidence,
            "source": item.source.value,
        }
        for item in batch.observations
    ]


def _readings_payload(readings: tuple[LocalCvDetection, ...]) -> list[dict[str, object]]:
    return [
        {
            "name": item.observation_name,
            "raw_score": item.raw_match_score,
            "semantic_confidence": item.semantic_confidence,
        }
        for item in readings
    ]


@dataclass(frozen=True)
class _FrameSaveRequest:
    frame: WorkbenchFrame
    reason: str
    relative_path: str
    write_image: bool


class SessionStore:
    """Local JSONL + PNG storage with one bounded evidence writer.

    PNG encoding measured about 155 ms for a 2712x1224 diagnostic frame. The
    single worker keeps that cost off the capture/UI loop; the bounded queue
    refuses excess evidence instead of accumulating an unbounded stale stream.
    """

    def __init__(
        self,
        root: Path,
        *,
        detector_names: tuple[str, ...],
        writer_queue_size: int = 16,
    ) -> None:
        if writer_queue_size <= 0:
            raise ValueError("writer_queue_size must be positive")
        self.session_id = _session_id()
        self.path = root / self.session_id
        self.frames_path = self.path / "frames"
        self.frames_path.mkdir(parents=True, exist_ok=False)
        self._events_file = (self.path / "events.jsonl").open("a", encoding="utf-8")
        self._lock = threading.RLock()
        self._frame_paths: dict[int, str] = {}
        self._write_queue: queue.Queue[_FrameSaveRequest | None] = queue.Queue(
            maxsize=writer_queue_size
        )
        self._writer_failure: OSError | None = None
        self._last_save_ms = 0.0
        self._max_queue_depth = 0
        self._dropped_evidence = 0
        self.event_counts: Counter[str] = Counter()
        self.evidence_counts: Counter[str] = Counter()
        self.frame_count = 0
        self.evidence_count = 0
        self.started_at = _utc_now()
        self.finished_at: str | None = None
        self.detector_names = detector_names
        self._writer = threading.Thread(
            target=self._writer_loop,
            name="workbench-evidence-writer",
            daemon=True,
        )
        self._writer.start()

    @property
    def failure(self) -> OSError | None:
        with self._lock:
            return self._writer_failure

    @property
    def last_save_ms(self) -> float:
        with self._lock:
            return self._last_save_ms

    @property
    def queue_depth(self) -> int:
        return self._write_queue.qsize()

    def append(self, event_type: str, payload: dict[str, object]) -> None:
        record = event_record(
            self.session_id,
            event_type,
            timestamp=_utc_now(),
            payload=payload,
        )
        with self._lock:
            self._events_file.write(json.dumps(record, sort_keys=True) + "\n")
            self._events_file.flush()
            self.event_counts[event_type] += 1

    def save_frame(self, frame: WorkbenchFrame, *, reason: str) -> str | None:
        """Enqueue evidence without waiting for PNG compression or disk IO."""

        with self._lock:
            relative_path = self._frame_paths.get(frame.snapshot.sequence)
            write_image = relative_path is None
            if relative_path is None:
                relative_path = f"frames/frame-{frame.snapshot.sequence:08d}.png"
                self._frame_paths[frame.snapshot.sequence] = relative_path
        request = _FrameSaveRequest(frame, reason, relative_path, write_image)
        try:
            self._write_queue.put_nowait(request)
        except queue.Full:
            with self._lock:
                if write_image:
                    self._frame_paths.pop(frame.snapshot.sequence, None)
                self._dropped_evidence += 1
            self.append(
                "evidence.skipped",
                {
                    "reason": reason,
                    "sequence": frame.snapshot.sequence,
                    "cause": "writer_queue_full",
                },
            )
            return None
        with self._lock:
            self.evidence_count += 1
            self.evidence_counts[reason] += 1
            self._max_queue_depth = max(self._max_queue_depth, self.queue_depth)
        return relative_path

    def finalize(self, *, metadata: dict[str, object], exit_reason: str) -> None:
        if self.finished_at is not None:
            return
        self._write_queue.join()
        self._write_queue.put(None)
        self._writer.join(timeout=5.0)
        if self._writer.is_alive():
            raise OSError("Evidence writer did not stop")
        self.finished_at = _utc_now()
        self.append(
            "session.ended",
            {"exit_reason": exit_reason, "end_time": self.finished_at},
        )
        with self._lock:
            summary = {
                "schema_version": SCHEMA_VERSION,
                "workbench_version": WORKBENCH_VERSION,
                "curation_status": "raw_unreviewed",
                "curated": False,
                "session_id": self.session_id,
                "start_time": self.started_at,
                "end_time": self.finished_at,
                "detector_semantic_names": list(self.detector_names),
                "event_counts": dict(sorted(self.event_counts.items())),
                "evidence_counts": dict(sorted(self.evidence_counts.items())),
                "evidence_examples": self.evidence_count,
                "unique_frames": self.frame_count,
                "evidence_writer": {
                    "max_queue_depth": self._max_queue_depth,
                    "dropped": self._dropped_evidence,
                    "last_save_ms": self._last_save_ms,
                    "failure": str(self._writer_failure) if self._writer_failure else None,
                },
                **metadata,
            }
            (self.path / "summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self._events_file.close()
        if self._writer_failure is not None:
            raise self._writer_failure

    def _writer_loop(self) -> None:
        import cv2

        while True:
            request = self._write_queue.get()
            try:
                if request is None:
                    return
                started = time.perf_counter()
                if request.write_image:
                    if not cv2.imwrite(
                        str(self.path / request.relative_path),
                        request.frame.snapshot.image,
                    ):
                        raise OSError(
                            f"Could not write evidence frame {request.relative_path}"
                        )
                    with self._lock:
                        self.frame_count += 1
                frame = request.frame
                correctness = evaluate_correctness(frame.human, frame.state)
                self.append(
                    "evidence.frame",
                    {
                        "reason": request.reason,
                        "frame": request.relative_path,
                        "sequence": frame.snapshot.sequence,
                        "monotonic_timestamp": frame.snapshot.timestamp,
                        "frame_shape": list(frame.snapshot.image.shape),
                        "human_ground_truth": frame.human.payload(),
                        "predicted": _state_payload(frame.state),
                        "correctness": correctness.value,
                        "observations": _observations_payload(frame.batch),
                        "detector_readings": _readings_payload(frame.readings),
                    },
                )
                if request.write_image:
                    with self._lock:
                        self._last_save_ms = (
                            time.perf_counter() - started
                        ) * 1000.0
            except Exception as error:
                with self._lock:
                    self._writer_failure = OSError(
                        f"Evidence writer failed: {error}"
                    )
            finally:
                self._write_queue.task_done()


@dataclass
class PendingInteraction:
    interaction_id: str
    gesture: HumanGesture
    before: WorkbenchFrame | None
    ready_at: float


@dataclass(frozen=True)
class ObservedInteraction:
    """Identity of the latest raw gesture still lacking semantic after GT."""

    interaction_id: str


def analyze_frame(
    snapshot: FrameSnapshot,
    perception: PerceptionEngine,
    resolver: ContextResolver,
    human: GroundTruthState,
) -> WorkbenchFrame:
    """Use the exact Phase 3D analysis path on the original snapshot image."""

    analysis = analyze_snapshot(snapshot, perception, resolver)
    return _workbench_frame(analysis, human)


def _workbench_frame(
    analysis: FrameAnalysis,
    human: GroundTruthState,
) -> WorkbenchFrame:
    return WorkbenchFrame(
        snapshot=analysis.snapshot,
        batch=analysis.batch,
        state=analysis.state,
        readings=analysis.readings,
        human=human,
        perception_seconds=analysis.perception_seconds,
        resolver_seconds=analysis.resolver_seconds,
        analyzed_at=time.monotonic(),
    )


def compare_snapshot_paths(
    snapshot: FrameSnapshot,
    *,
    smoke_perception: PerceptionEngine,
    workbench_perception: PerceptionEngine,
    resolver: ContextResolver,
) -> PathComparison:
    """Evaluate one original ndarray through both tool paths and prove equality."""

    before = hashlib.sha256(snapshot.image.tobytes()).digest()
    smoke = analyze_snapshot(snapshot, smoke_perception, resolver)
    workbench = analyze_frame(
        snapshot,
        workbench_perception,
        resolver,
        GroundTruthState(),
    )
    after = hashlib.sha256(snapshot.image.tobytes()).digest()
    smoke_readings = tuple(
        (item.observation_name, item.raw_match_score) for item in smoke.readings
    )
    workbench_readings = tuple(
        (item.observation_name, item.raw_match_score) for item in workbench.readings
    )
    return PathComparison(
        input_unchanged=before == after,
        raw_scores_equal=smoke_readings == workbench_readings,
        smoke_readings=smoke_readings,
        workbench_readings=workbench_readings,
    )


def _interaction_payload(
    pending: PendingInteraction,
    after: WorkbenchFrame | None,
    store: SessionStore,
) -> tuple[str, dict[str, object]]:
    gesture, before = pending.gesture, pending.before
    before_path = store.save_frame(before, reason="interaction.before") if before else None
    after_path = store.save_frame(after, reason="interaction.after") if after else None
    common: dict[str, object] = {
        "interaction_id": pending.interaction_id,
        "monotonic_timestamp": gesture.timestamp,
        "started_at": gesture.started_at,
        "frame_before_sequence": before.snapshot.sequence if before else None,
        "frame_after_sequence": after.snapshot.sequence if after else None,
        "frame_before": before_path,
        "frame_after": after_path,
        "predicted_state_before": _state_payload(before.state) if before else None,
        "predicted_state_after": _state_payload(after.state) if after else None,
        "human_ground_truth_before": before.human.payload() if before else None,
        "frame_after_role": "temporal_observation_only",
    }
    if isinstance(gesture, HumanTap):
        common.update(
            {
                "x_relative": gesture.position[0],
                "y_relative": gesture.position[1],
                "raw_coordinates": list(gesture.raw_position),
                "duration": gesture.duration,
            }
        )
        return "human.tap", common
    if isinstance(gesture, HumanSwipe):
        common.update(
            {
                "start_relative": list(gesture.start),
                "end_relative": list(gesture.end),
                "raw_start": list(gesture.raw_start),
                "raw_end": list(gesture.raw_end),
                "duration": gesture.duration,
                "path": [list(point) for point in gesture.path],
            }
        )
        return "human.swipe", common
    common["reason"] = gesture.reason
    return "human.unknown_gesture", common


def confirm_transition(
    interaction: ObservedInteraction,
    *,
    human: GroundTruthState,
    confirmation_frame: WorkbenchFrame,
    store: SessionStore,
) -> dict[str, object]:
    """Explicitly bind human after-GT to an observed gesture and frame.

    Neither the temporal frame stored with the gesture nor its prediction can
    call this operation.  The Workbench UI invokes it only via the human ``T``
    confirmation hotkey.
    """

    if not human.base_confirmed:
        raise ValueError("after ground truth must be explicitly human-confirmed")
    confirmed = replace(confirmation_frame, human=human)
    frame_path = store.save_frame(confirmed, reason="transition.confirmed_after")
    return {
        "interaction_id": interaction.interaction_id,
        "confirmation_method": "human_hotkey",
        "after_ground_truth": human.payload(),
        "confirmation_frame": frame_path,
        "confirmation_frame_sequence": confirmation_frame.snapshot.sequence,
        "confirmation_monotonic_timestamp": confirmation_frame.snapshot.timestamp,
    }


def _touch_marker(
    image: np.ndarray,
    gesture: HumanGesture | None,
    *,
    now: float,
) -> None:
    if gesture is None or now - gesture.timestamp > 3.0:
        return
    import cv2

    if isinstance(gesture, HumanTap):
        point = relative_to_frame(gesture.position, image.shape)
        cv2.circle(image, point, 28, (0, 255, 255), 5)
        cv2.drawMarker(image, point, (0, 255, 255), cv2.MARKER_CROSS, 44, 4)
    elif isinstance(gesture, HumanSwipe):
        start = relative_to_frame(gesture.start, image.shape)
        end = relative_to_frame(gesture.end, image.shape)
        cv2.arrowedLine(image, start, end, (255, 255, 0), 6, tipLength=0.08)


def preview_dimensions(
    width: int,
    height: int,
    *,
    max_width: int = PREVIEW_WIDTH,
    max_height: int = 650,
) -> tuple[int, int]:
    """Fit an integer multiple of the reduced ratio whenever possible."""

    if min(width, height, max_width, max_height) <= 0:
        raise ValueError("preview dimensions must be positive")
    divisor = math.gcd(width, height)
    unit_width, unit_height = width // divisor, height // divisor
    multiplier = min(
        divisor,
        max_width // unit_width,
        max_height // unit_height,
    )
    if multiplier >= 1:
        return unit_width * multiplier, unit_height * multiplier
    scale = min(max_width / width, max_height / height, 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))


def render_ui(
    frame: WorkbenchFrame,
    *,
    human: GroundTruthState,
    correctness: Correctness,
    representative: bool,
    last_gesture: HumanGesture | None,
    evidence_count: int,
    base_mapping: tuple[str | None, ...],
    overlay_names: tuple[str, ...],
    selected_overlay: int,
    label_origins: dict[str, str],
    pending_transition_count: int,
    metrics: LiveMetrics,
    evidence_save_ms: float,
    writer_queue_depth: int,
) -> np.ndarray:
    """Render diagnostics on a copy; saved ground-truth PNGs remain clean."""

    import cv2

    source = frame.snapshot.image.copy()
    _touch_marker(source, last_gesture, now=time.monotonic())
    preview_width, preview_height = preview_dimensions(
        source.shape[1], source.shape[0]
    )
    display = cv2.resize(
        source,
        (preview_width, preview_height),
        interpolation=cv2.INTER_AREA,
    )
    panel_width = 540
    canvas = np.zeros(
        (
            max(display.shape[0], WORKBENCH_WINDOW_HEIGHT),
            display.shape[1] + panel_width,
            3,
        ),
        dtype=np.uint8,
    )
    canvas[: display.shape[0], : display.shape[1]] = display
    x = display.shape[1] + 18
    y = 30

    def line(text: str, color=(230, 230, 230), size=0.55) -> None:
        nonlocal y
        cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)
        y += 23

    line(f"source sequence: {frame.snapshot.sequence}", (120, 255, 255), 0.60)
    line(f"frame: {frame.snapshot.width}x{frame.snapshot.height} BGR original")
    line(f"frame age ms: {metrics.frame_age_ms:.1f}")
    line(f"perception ms: {metrics.perception_ms:.1f}")
    line(f"UI/display ms: {metrics.ui_display_ms:.1f}")
    line(f"evidence-save ms: {evidence_save_ms:.1f}  queue={writer_queue_depth}")
    line(f"PREDICTION: {frame.state.status.value.upper()}", (255, 220, 120), 0.62)
    line(f"base={frame.state.base_context or UNKNOWN_LABEL}")
    line(f"overlays={list(frame.state.overlays)}")
    if frame.state.base_candidates:
        line(f"candidates={list(frame.state.base_candidates)}", (100, 180, 255))
    line(f"HUMAN CONFIRMED: {human.display_base}", (120, 255, 120), 0.62)
    line(f"human overlays={sorted(human.overlays)}")
    outcome_color = (100, 255, 100) if correctness is Correctness.MATCH else (80, 80, 255)
    line(f"CORRECTNESS: {correctness.value.upper()}", outcome_color, 0.67)
    line(f"RECORD REPRESENTATIVE: {'ON' if representative else 'OFF'}")
    line(f"evidence examples saved: {evidence_count}")
    line("Observations / semantic confidence", (255, 255, 255), 0.58)
    if frame.batch.observations:
        for observation in frame.batch.observations:
            line(f"  {observation.name} = {observation.confidence:.3f}", size=0.48)
    else:
        line("  none", size=0.48)
    line("Raw detector diagnostics", (255, 255, 255), 0.58)
    for reading in frame.readings:
        short_name = reading.observation_name.removeprefix("landmark.")
        line(
            f"  {short_name}: raw={reading.raw_match_score:.4f} conf={reading.semantic_confidence:.3f}",
            size=0.43,
        )
    line("Acquisition bases (persistent human GT)", (255, 255, 255), 0.58)
    selected_base_index = (
        base_mapping.index(human.base_context)
        if human.base_confirmed and human.base_context in base_mapping
        else 0
    )
    visible_indices = set(range(min(10, len(base_mapping))))
    if selected_base_index >= 10:
        visible_indices.add(selected_base_index)
    for index in sorted(visible_indices):
        label = base_mapping[index]
        origin = label_origins.get(label, "special") if label else "special"
        marker = ">" if human.base_confirmed and human.base_context == label else " "
        shortcut = str(index) if index < 10 else "-"
        line(f"{marker} {shortcut}: {label or UNKNOWN_LABEL} [{origin}]", size=0.43)
    line("  J/K: cycle all acquisition labels", size=0.46)
    selected = overlay_names[selected_overlay] if overlay_names else "none"
    selected_origin = label_origins.get(selected, "special")
    line(f"Overlay selected: {selected} [{selected_origin}]", (255, 255, 255), 0.54)
    line(f"gestures awaiting explicit after GT: {pending_transition_count}")
    line("[/] select overlay | P toggle overlay | U unset")
    line("T confirm GT after latest gesture | R representative")
    line("S manual save | Q quit")
    if last_gesture is not None:
        line(f"last gesture: {type(last_gesture).__name__}", (100, 255, 255))
    return canvas


def _key_code(delay_ms: int = 10) -> int:
    import cv2

    return cv2.waitKey(delay_ms) & 0xFF


def is_overlay_toggle_key(key: int) -> bool:
    """Use only unambiguous P; the old O/0 pair is intentionally retired."""
    return key in {ord("p"), ord("P")}


def _forward_present(adb: AdbClient, source: ScrcpyFrameSource) -> bool:
    return any(
        len(fields := rule.split()) >= 2
        and fields[0] == adb.serial
        and fields[1] == source.local_endpoint
        for rule in adb.list_forwards()
    )


def _print_controls(
    base_mapping: tuple[str | None, ...],
    overlays: tuple[str, ...],
    vocabulary: AcquisitionVocabulary,
) -> None:
    origins = {
        label.name: label.origin.value
        for label in (*vocabulary.bases, *vocabulary.overlays)
    }
    print("Human acquisition base label mapping:")
    for index, label in enumerate(base_mapping[:10]):
        origin = origins.get(label, "special") if label else "special"
        print(f"  {index}: {label or UNKNOWN_LABEL} [{origin}]")
    print("Controls: digits/J/K base | [/ ] overlay | P toggle overlay | U unset")
    print("          T confirm GT after latest gesture | R representative")
    print("          S manual save | Q quit / Ctrl+C")
    print(f"Acquisition overlays: {[(name, origins[name]) for name in overlays]}")


def run_workbench(
    *,
    adb: AdbClient,
    source: ScrcpyFrameSource,
    observer: HumanInputObserver,
    perception: PerceptionEngine,
    resolver: ContextResolver,
    artifacts_root: Path,
    analyses_per_second: float,
    after_delay: float,
) -> Path:
    import cv2

    detector_names = tuple(
        spec.name
        for detector in perception.detectors
        if (spec := getattr(detector, "spec", None)) is not None
    )
    store = SessionStore(artifacts_root, detector_names=detector_names)
    vocabulary = build_acquisition_vocabulary(
        production_base_labels=(rule.name for rule in resolver.base_rules),
        production_overlay_labels=(rule.name for rule in resolver.overlay_rules),
    )
    base_mapping: tuple[str | None, ...] = (
        None,
        *vocabulary.base_names,
    )
    overlay_names = vocabulary.overlay_names
    label_origins = {
        label.name: label.origin.value
        for label in (*vocabulary.bases, *vocabulary.overlays)
    }
    _print_controls(base_mapping, overlay_names, vocabulary)
    human = GroundTruthState()
    representative = False
    selected_overlay = 0
    ring = FrameRingBuffer()
    dedup = EvidenceDeduplicator()
    pending: list[PendingInteraction] = []
    awaiting_confirmation: ObservedInteraction | None = None
    interaction_sequence = 0
    latest: WorkbenchFrame | None = None
    last_gesture: HumanGesture | None = None
    last_sequence: int | None = None
    next_analysis = 0.0
    metrics = LiveMetrics()
    display_dirty = False
    exit_reason = "normal"
    frame_shape: list[int] | None = None
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, PREVIEW_WIDTH + 540, WORKBENCH_WINDOW_HEIGHT)
    try:
        with source, observer:
            device = observer.device
            store.append(
                "session.started",
                {
                    "start_time": store.started_at,
                    "workbench_version": WORKBENCH_VERSION,
                    "scrcpy_protocol_version": ScrcpyFrameSource.SCRCPY_VERSION,
                    "capture_video_bit_rate": source.video_bit_rate,
                    "capture_max_fps": source.max_fps,
                    "detector_semantic_names": list(detector_names),
                    "acquisition_vocabulary": {
                        "bases": [
                            {"name": label.name, "origin": label.origin.value}
                            for label in vocabulary.bases
                        ],
                        "overlays": [
                            {"name": label.name, "origin": label.origin.value}
                            for label in vocabulary.overlays
                        ],
                        "unknown_available": True,
                    },
                    "touch_axis_ranges": {
                        "x": [device.x_axis.minimum, device.x_axis.maximum],
                        "y": [device.y_axis.minimum, device.y_axis.maximum],
                    }
                    if device
                    else None,
                    "touch_rotation": observer.rotation,
                },
            )
            interval = 1.0 / analyses_per_second
            while True:
                if store.failure is not None:
                    raise store.failure
                now = time.monotonic()
                if now >= next_analysis:
                    # ScrcpyFrameSource owns only its newest decoded snapshot;
                    # skipped sequence numbers are intentionally discarded.
                    snapshot = source.get_frame()
                    if snapshot.sequence != last_sequence:
                        analysis_started = time.monotonic()
                        latest = analyze_frame(snapshot, perception, resolver, human)
                        metrics.frame_age_ms = max(
                            0.0, (analysis_started - snapshot.timestamp) * 1000.0
                        )
                        metrics.perception_ms = latest.perception_seconds * 1000.0
                        ring.add(latest)
                        last_sequence = snapshot.sequence
                        frame_shape = list(snapshot.image.shape)
                        display_dirty = True
                        correctness = evaluate_correctness(human, latest.state)
                        if correctness in {Correctness.MISMATCH, Correctness.AMBIGUOUS}:
                            key = f"mismatch:{human.display_base}:{sorted(human.overlays)}:{correctness.value}"
                            if dedup.should_accept(key, snapshot.image, timestamp=snapshot.timestamp):
                                store.save_frame(latest, reason=correctness.value)
                        if representative and human.base_confirmed:
                            key = f"representative:{human.display_base}:{sorted(human.overlays)}"
                            if dedup.should_accept(key, snapshot.image, timestamp=snapshot.timestamp):
                                store.save_frame(latest, reason="representative")
                    next_analysis = now + interval

                for gesture in observer.poll():
                    last_gesture = gesture
                    before = ring.before(gesture.started_at)
                    if before is not None:
                        before = replace(before, human=human)
                    interaction_sequence += 1
                    interaction_id = f"interaction-{interaction_sequence:06d}"
                    pending.append(
                        PendingInteraction(
                            interaction_id,
                            gesture,
                            before,
                            gesture.timestamp + after_delay,
                        )
                    )
                    display_dirty = True

                remaining: list[PendingInteraction] = []
                for interaction in pending:
                    after = ring.after(interaction.ready_at)
                    if after is None:
                        remaining.append(interaction)
                        continue
                    event_type, payload = _interaction_payload(interaction, after, store)
                    store.append(event_type, payload)
                    # Only the newest gesture can be explicitly confirmed.
                    # Older events remain raw and correctly have no after GT.
                    awaiting_confirmation = ObservedInteraction(
                        interaction.interaction_id
                    )
                pending = remaining

                if latest is not None and display_dirty:
                    correctness = evaluate_correctness(human, latest.state)
                    metrics.frame_age_ms = max(
                        0.0,
                        (time.monotonic() - latest.snapshot.timestamp) * 1000.0,
                    )
                    display_started = time.perf_counter()
                    cv2.imshow(
                        WINDOW_NAME,
                        render_ui(
                            latest,
                            human=human,
                            correctness=correctness,
                            representative=representative,
                            last_gesture=last_gesture,
                            evidence_count=store.evidence_count,
                            base_mapping=base_mapping,
                            overlay_names=overlay_names,
                            selected_overlay=selected_overlay,
                            label_origins=label_origins,
                            pending_transition_count=int(awaiting_confirmation is not None),
                            metrics=metrics,
                            evidence_save_ms=store.last_save_ms,
                            writer_queue_depth=store.queue_depth,
                        ),
                    )
                    metrics.ui_display_ms = (
                        time.perf_counter() - display_started
                    ) * 1000.0
                    display_dirty = False

                key = _key_code()
                if key in {ord("q"), ord("Q")}:
                    exit_reason = "q"
                    break
                if ord("0") <= key <= ord("9"):
                    index = key - ord("0")
                    if index < len(base_mapping):
                        human = human.select_base(base_mapping[index])
                        store.append("human.ground_truth_changed", human.payload())
                        if latest is not None:
                            latest = replace(latest, human=human)
                        display_dirty = True
                elif key in {ord("j"), ord("J"), ord("k"), ord("K")}:
                    current = base_mapping.index(human.base_context) if human.base_confirmed else 0
                    delta = -1 if key in {ord("j"), ord("J")} else 1
                    human = human.select_base(base_mapping[(current + delta) % len(base_mapping)])
                    store.append("human.ground_truth_changed", human.payload())
                    display_dirty = True
                elif key in {ord("u"), ord("U")}:
                    human = human.clear()
                    store.append("human.ground_truth_changed", human.payload())
                    display_dirty = True
                elif key == ord("[") and overlay_names:
                    selected_overlay = (selected_overlay - 1) % len(overlay_names)
                    display_dirty = True
                elif key == ord("]") and overlay_names:
                    selected_overlay = (selected_overlay + 1) % len(overlay_names)
                    display_dirty = True
                elif is_overlay_toggle_key(key) and overlay_names:
                    human = human.toggle_overlay(overlay_names[selected_overlay])
                    store.append("human.ground_truth_changed", human.payload())
                    display_dirty = True
                elif key in {ord("t"), ord("T")}:
                    if (
                        latest is not None
                        and human.base_confirmed
                        and awaiting_confirmation is not None
                    ):
                        interaction = awaiting_confirmation
                        awaiting_confirmation = None
                        store.append(
                            "human.transition_confirmed",
                            confirm_transition(
                                interaction,
                                human=human,
                                confirmation_frame=latest,
                                store=store,
                            ),
                        )
                    else:
                        store.append(
                            "human.transition_confirmation_skipped",
                            {
                                "cause": (
                                    "no_human_ground_truth"
                                    if not human.base_confirmed
                                    else "no_observed_interaction"
                                )
                            },
                        )
                    display_dirty = True
                elif key in {ord("r"), ord("R")}:
                    representative = not representative
                    store.append("recording.representative", {"enabled": representative})
                    display_dirty = True
                elif key in {ord("s"), ord("S")} and latest is not None:
                    latest = replace(latest, human=human)
                    store.save_frame(latest, reason="manual")
                    display_dirty = True

                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    exit_reason = "window_closed"
                    break
    except KeyboardInterrupt:
        exit_reason = "ctrl_c"
    finally:
        if pending:
            final_after = ring.latest
            for interaction in pending:
                event_type, payload = _interaction_payload(interaction, final_after, store)
                store.append(event_type, payload)
        cv2.destroyAllWindows()
        cleanup = {
            "frame_shape": frame_shape,
            "scrcpy_protocol_version": ScrcpyFrameSource.SCRCPY_VERSION,
            "cleanup": {
                "scrcpy_source_stopped": not source.is_running,
                "human_input_observer_stopped": not observer.is_running,
                "adb_forward_removed": not _forward_present(adb, source),
            },
        }
        store.finalize(metadata=cleanup, exit_reason=exit_reason)
    if source.is_running or observer.is_running or _forward_present(adb, source):
        raise RuntimeError("Workbench cleanup is incomplete")
    return store.path


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return result


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def run_compare_once(
    source: ScrcpyFrameSource,
    *,
    resolver: ContextResolver,
) -> PathComparison:
    """Capture one original frame and compare Phase 3D/Workbench evaluation."""

    with source:
        snapshot = source.get_frame()
        comparison = compare_snapshot_paths(
            snapshot,
            smoke_perception=build_default_perception(),
            workbench_perception=build_default_perception(),
            resolver=resolver,
        )
        age_ms = max(0.0, (time.monotonic() - snapshot.timestamp) * 1000.0)
        print(
            f"compare source sequence={snapshot.sequence} "
            f"shape={snapshot.image.shape} dtype={snapshot.image.dtype} "
            f"frame_age_ms={age_ms:.1f}"
        )
        for (name, smoke_score), (_, workbench_score) in zip(
            comparison.smoke_readings,
            comparison.workbench_readings,
            strict=True,
        ):
            print(
                f"  {name}: smoke_raw={smoke_score:.6f} "
                f"workbench_raw={workbench_score:.6f}"
            )
        print(f"input_unchanged={comparison.input_unchanged}")
        print(f"raw_scores_equal={comparison.raw_scores_equal}")
    if source.is_running or _forward_present(source.adb, source):
        raise RuntimeError("Compare-once capture cleanup is incomplete")
    if not comparison.input_unchanged or not comparison.raw_scores_equal:
        raise RuntimeError("Phase 3D and Workbench image paths differ")
    return comparison


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Human-in-the-loop Perception Workbench v1")
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    parser.add_argument("--hz", type=_positive_float, default=4.0)
    parser.add_argument("--after-delay", type=_positive_float, default=0.5)
    parser.add_argument(
        "--video-bit-rate",
        type=_positive_int,
        default=WORKBENCH_VIDEO_BIT_RATE,
        help=f"scrcpy video bitrate (default: {WORKBENCH_VIDEO_BIT_RATE})",
    )
    parser.add_argument(
        "--capture-fps",
        type=_positive_int,
        default=WORKBENCH_CAPTURE_FPS,
        help=f"scrcpy max fps to avoid decoder backlog (default: {WORKBENCH_CAPTURE_FPS})",
    )
    parser.add_argument(
        "--compare-once",
        action="store_true",
        help="compare Phase 3D and Workbench raw scores on one original live frame",
    )
    parser.add_argument(
        "--rotation",
        type=int,
        choices=range(4),
        default=None,
        help="override Android rotation discovery (0, 1, 2, or 3)",
    )
    parser.add_argument("--tap-tolerance", type=_positive_float, default=0.025)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
        if adb.get_state() != "device":
            raise RuntimeError("ADB device is not authorized/ready")
        source = build_frame_source(
            config,
            adb_client=adb,
            video_bit_rate=args.video_bit_rate,
            max_fps=args.capture_fps,
        )
        resolver = build_default_resolver()
        if args.compare_once:
            run_compare_once(source, resolver=resolver)
            return 0
        observer = HumanInputObserver(
            adb,
            rotation=args.rotation,
            tap_tolerance=args.tap_tolerance,
        )
        session_path = run_workbench(
            adb=adb,
            source=source,
            observer=observer,
            perception=build_default_perception(),
            resolver=resolver,
            artifacts_root=args.artifacts_root,
            analyses_per_second=args.hz,
            after_delay=args.after_delay,
        )
    except (AdbError, CaptureError, HumanInputError, RuntimeError, ValueError, OSError) as error:
        print(f"[workbench] FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Workbench session saved: {session_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
