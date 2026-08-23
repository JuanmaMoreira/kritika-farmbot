import datetime as dt
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_CHARACTER_SELECT, SCREEN_LOBBY
from tools.capture_semantic_dataset import (
    AcquisitionRecord,
    CaptureMetadata,
    capture_path,
    load_acquisition_manifest,
    mean_frame_difference,
    record_snapshot,
    write_acquisition_manifest,
)
from tools.semantic_slice_evaluation import CONFIRMED, ManifestEntry, load_manifest


def test_capture_path_is_labelled_relative_and_deterministic(tmp_path):
    captured_at = dt.datetime(2026, 8, 22, 12, 34, 56, 123456, dt.timezone.utc)

    path, relative = capture_path(
        tmp_path, "screencaps/semantic", SCREEN_LOBBY, captured_at
    )

    assert path == (
        tmp_path
        / "screencaps"
        / "semantic"
        / "lobby"
        / "20260822T123456_123456Z.png"
    )
    assert relative == "screencaps/semantic/lobby/20260822T123456_123456Z.png"


def test_capture_path_rejects_unsupported_label_and_external_output(tmp_path):
    now = dt.datetime.now(dt.timezone.utc)
    with pytest.raises(ValueError, match="unsupported"):
        capture_path(tmp_path, "screencaps", "screen.automatic", now)
    with pytest.raises(ValueError, match="inside"):
        capture_path(tmp_path, tmp_path.parent / "outside", SCREEN_LOBBY, now)


def test_frame_difference_reports_identical_and_changed_frames():
    black = np.zeros((80, 120, 3), dtype=np.uint8)
    white = np.full((160, 240, 3), 255, dtype=np.uint8)

    assert mean_frame_difference(black, black.copy()) == 0.0
    assert mean_frame_difference(black, white) == 1.0


def test_record_snapshot_keeps_full_lossless_frame_and_human_label(tmp_path):
    image = np.zeros((48, 96, 3), dtype=np.uint8)
    image[4:20, 7:30] = (10, 120, 240)
    snapshot = FrameSnapshot(image, timestamp=1.5, sequence=7)
    captured_at = dt.datetime(2026, 8, 22, tzinfo=dt.timezone.utc)

    record = record_snapshot(
        tmp_path,
        "screencaps/semantic",
        snapshot,
        SCREEN_CHARACTER_SELECT,
        captured_at,
        image.copy(),
    )
    saved = cv2.imread(str(tmp_path / record.entry.path), cv2.IMREAD_COLOR)

    assert np.array_equal(saved, image)
    assert record.entry == ManifestEntry(
        record.entry.path, SCREEN_CHARACTER_SELECT, (), CONFIRMED
    )
    assert record.metadata.width == 96
    assert record.metadata.height == 48
    assert record.metadata.source_sequence == 7
    assert record.metadata.previous_label_difference == 0.0


def test_acquisition_manifest_round_trip_is_core_manifest_compatible(tmp_path):
    manifest = tmp_path / "datasets" / "semantic_acquisition_manifest.json"
    records = (
        AcquisitionRecord(
            ManifestEntry(
                "screencaps/semantic/lobby/b.png",
                SCREEN_LOBBY,
                (),
                CONFIRMED,
            ),
            CaptureMetadata("2026-08-22T12:00:00+00:00", 2712, 1224, 12, previous_label_difference=0.02),
        ),
        AcquisitionRecord(
            ManifestEntry(
                "screencaps/semantic/lobby/a.png",
                SCREEN_LOBBY,
                (),
                CONFIRMED,
            ),
            CaptureMetadata("2026-08-22T11:00:00+00:00", 2712, 1224, 8),
        ),
    )

    write_acquisition_manifest(manifest, records)

    assert load_acquisition_manifest(manifest) == tuple(reversed(records))
    assert load_manifest(manifest) == tuple(
        record.entry for record in reversed(records)
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["entries"][0]["metadata"]["capture_method"] == "human_keyboard"
    serialized = json.dumps(payload)
    assert "serial" not in serialized.lower()
    assert str(tmp_path) not in serialized


def test_capture_module_is_import_safe(tmp_path, monkeypatch):
    import importlib
    import tools.capture_semantic_dataset as module

    monkeypatch.chdir(tmp_path)
    importlib.reload(module)

    assert not (tmp_path / "screencaps").exists()
    assert not (tmp_path / "datasets").exists()
