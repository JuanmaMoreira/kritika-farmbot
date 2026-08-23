import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.perception import LocalCvDetection, PerceptionEngine
from bot.resolver import ContextResolver
from bot.state import ResolutionStatus, ResolvedState
from tools.perception_workbench import (
    Correctness,
    EvidenceDeduplicator,
    FrameRingBuffer,
    GroundTruthState,
    LiveMetrics,
    OVERLAY_TOGGLE_KEY,
    SCHEMA_VERSION,
    SessionStore,
    WorkbenchFrame,
    compare_snapshot_paths,
    evaluate_correctness,
    event_record,
    is_overlay_toggle_key,
    preview_dimensions,
    render_ui,
)


def state(status, *, base=None, overlays=(), candidates=(), sequence=1, timestamp=1.0):
    return ResolvedState(
        status=status,
        sequence=sequence,
        timestamp=timestamp,
        base_context=base,
        overlays=overlays,
        base_candidates=candidates,
    )


def workbench_frame(sequence, timestamp, human=None):
    snapshot = FrameSnapshot(
        image=np.full((4, 8, 3), sequence, dtype=np.uint8),
        timestamp=timestamp,
        sequence=sequence,
    )
    batch = ObservationBatch(sequence=sequence, timestamp=timestamp)
    resolved = state(
        ResolutionStatus.RESOLVED,
        base="screen.lobby",
        sequence=sequence,
        timestamp=timestamp,
    )
    return WorkbenchFrame(snapshot, batch, resolved, (), human or GroundTruthState())


def test_workbench_import_is_inert(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )
    result = subprocess.run(
        [sys.executable, "-c", "import tools.perception_workbench"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_ground_truth_is_persistent_explicit_and_overlay_dynamic():
    truth = GroundTruthState()
    assert truth.display_base == "UNSET"
    assert not truth.base_confirmed

    truth = truth.select_base("screen.black_market")
    truth = truth.toggle_overlay("popup.purchase_confirmation")
    assert truth.display_base == "screen.black_market"
    assert truth.overlays == frozenset({"popup.purchase_confirmation"})
    assert truth.payload()["source"] == "human_confirmed"

    truth = truth.select_base(None)
    assert truth.display_base == "UNKNOWN"
    assert truth.base_confirmed


def test_overlay_toggle_hotkey_is_not_visually_ambiguous_with_unknown_zero():
    assert OVERLAY_TOGGLE_KEY == "P"
    assert is_overlay_toggle_key(ord("P"))
    assert is_overlay_toggle_key(ord("p"))
    assert is_overlay_toggle_key(ord("O"))  # Legacy compatibility.
    assert not is_overlay_toggle_key(ord("0"))


def test_correctness_is_derived_for_match_mismatch_unknown_and_ambiguous():
    unlabelled = GroundTruthState()
    lobby = state(ResolutionStatus.RESOLVED, base="screen.lobby")
    assert evaluate_correctness(unlabelled, lobby) is Correctness.UNLABELED

    human_lobby = unlabelled.select_base("screen.lobby")
    assert evaluate_correctness(human_lobby, lobby) is Correctness.MATCH
    assert evaluate_correctness(
        human_lobby, state(ResolutionStatus.UNKNOWN)
    ) is Correctness.MISMATCH

    human_unknown = unlabelled.select_base(None)
    assert evaluate_correctness(
        human_unknown, state(ResolutionStatus.UNKNOWN)
    ) is Correctness.MATCH
    assert evaluate_correctness(
        human_lobby,
        state(
            ResolutionStatus.AMBIGUOUS,
            candidates=("screen.lobby", "screen.black_market"),
        ),
    ) is Correctness.AMBIGUOUS


def test_overlay_false_negative_is_automatic_mismatch():
    human = GroundTruthState().select_base("screen.black_market")
    human = human.toggle_overlay("popup.purchase_confirmation")
    predicted = state(ResolutionStatus.RESOLVED, base="screen.black_market")
    assert evaluate_correctness(human, predicted) is Correctness.MISMATCH


def test_deduplication_uses_cooldown_visual_difference_and_bounded_refresh():
    dedup = EvidenceDeduplicator(
        cooldown_seconds=2.0,
        difference_threshold=3.0,
        refresh_seconds=8.0,
    )
    black = np.zeros((64, 64, 3), dtype=np.uint8)
    white = np.full((64, 64, 3), 255, dtype=np.uint8)

    assert dedup.should_accept("mismatch", black, timestamp=10.0)
    assert not dedup.should_accept("mismatch", white, timestamp=11.0)
    assert dedup.should_accept("mismatch", white, timestamp=12.1)
    assert not dedup.should_accept("mismatch", white, timestamp=14.2)
    assert dedup.should_accept("mismatch", white, timestamp=20.2)
    assert dedup.should_accept("mismatch", white, timestamp=20.3, force=True)


def test_deduplication_caps_automatic_examples_per_stable_key():
    dedup = EvidenceDeduplicator(
        cooldown_seconds=1.0,
        difference_threshold=0.0,
        refresh_seconds=1.0,
        max_per_key=2,
    )
    frame = np.zeros((8, 8, 3), dtype=np.uint8)

    assert dedup.should_accept("stable", frame, timestamp=1.0)
    assert dedup.should_accept("stable", frame, timestamp=2.0)
    assert not dedup.should_accept("stable", frame, timestamp=3.0)
    assert dedup.should_accept("stable", frame, timestamp=3.0, force=True)


def test_event_serialization_has_extensible_common_envelope():
    record = event_record(
        "session-1",
        "human.tap",
        timestamp="2026-08-23T00:00:00Z",
        payload={"x_relative": 0.25, "y_relative": 0.75},
    )
    assert record == {
        "schema_version": SCHEMA_VERSION,
        "session_id": "session-1",
        "event_type": "human.tap",
        "timestamp": "2026-08-23T00:00:00Z",
        "payload": {"x_relative": 0.25, "y_relative": 0.75},
    }


def test_ring_buffer_associates_nearest_before_and_delayed_after_frames():
    ring = FrameRingBuffer(capacity=3)
    for sequence, timestamp in ((1, 10.0), (2, 10.4), (3, 10.8), (4, 11.2)):
        ring.add(workbench_frame(sequence, timestamp))

    assert ring.before(10.9).snapshot.sequence == 3
    assert ring.after(10.9).snapshot.sequence == 4
    assert ring.before(9.0) is None
    assert ring.after(12.0) is None
    assert ring.latest.snapshot.sequence == 4
    assert ring.before(10.1) is None  # sequence 1 was evicted


def test_preview_preserves_exact_2712_by_1224_aspect_ratio_without_upscaling():
    assert preview_dimensions(2712, 1224) == (1356, 612)
    width, height = preview_dimensions(2712, 1224)
    assert width / height == 2712 / 1224
    assert preview_dimensions(226, 102) == (226, 102)


def test_render_uses_a_copy_and_never_mutates_original_perception_image():
    frame = workbench_frame(1, time.monotonic())
    before = frame.snapshot.image.copy()

    rendered = render_ui(
        frame,
        human=GroundTruthState(),
        correctness=Correctness.UNLABELED,
        representative=False,
        last_gesture=None,
        evidence_count=0,
        base_mapping=(None,),
        overlay_names=(),
        selected_overlay=0,
        metrics=LiveMetrics(),
        evidence_save_ms=0.0,
        writer_queue_depth=0,
    )

    np.testing.assert_array_equal(frame.snapshot.image, before)
    assert not np.shares_memory(rendered, frame.snapshot.image)


class DiagnosticDetector:
    def detect(self, frame):
        return ()

    def measure(self, frame):
        return LocalCvDetection(
            observation_name="landmark.diagnostic",
            raw_match_score=float(frame[0, 0, 0]) / 255.0,
            semantic_confidence=0.0,
            search_region=(0.0, 0.0, 1.0, 1.0),
        )


def test_phase3d_and_workbench_paths_use_same_original_ndarray_and_raw_scores():
    image = np.full((12, 24, 3), 127, dtype=np.uint8)
    snapshot = FrameSnapshot(image=image, timestamp=time.monotonic(), sequence=7)

    comparison = compare_snapshot_paths(
        snapshot,
        smoke_perception=PerceptionEngine((DiagnosticDetector(),)),
        workbench_perception=PerceptionEngine((DiagnosticDetector(),)),
        resolver=ContextResolver(),
    )

    assert comparison.input_unchanged
    assert comparison.raw_scores_equal
    assert comparison.smoke_readings == comparison.workbench_readings
    np.testing.assert_array_equal(image, np.full((12, 24, 3), 127, dtype=np.uint8))


def test_evidence_png_encoding_runs_off_the_caller_thread(tmp_path, monkeypatch):
    write_started = threading.Event()
    release_write = threading.Event()

    def delayed_write(path, image):
        write_started.set()
        assert release_write.wait(1.0)
        Path(path).write_bytes(b"png")
        return True

    monkeypatch.setattr(cv2, "imwrite", delayed_write)
    store = SessionStore(tmp_path, detector_names=(), writer_queue_size=2)
    started = time.perf_counter()
    relative_path = store.save_frame(workbench_frame(1, 1.0), reason="mismatch")
    caller_ms = (time.perf_counter() - started) * 1000.0

    assert relative_path == "frames/frame-00000001.png"
    assert caller_ms < 50.0
    assert write_started.wait(1.0)
    release_write.set()
    store.finalize(metadata={}, exit_reason="test")

    summary = json.loads((store.path / "summary.json").read_text())
    assert summary["unique_frames"] == 1
    assert summary["evidence_writer"]["dropped"] == 0
    assert not store._writer.is_alive()
