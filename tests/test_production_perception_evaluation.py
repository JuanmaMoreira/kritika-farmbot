import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.production_perception_evaluation import (
    load_workbench_evidence_manifest,
    materialize_workbench_evidence,
)


SESSION_ID = "20260823T010203_000000Z-example"
SEQUENCE = 17
EVENT_TIMESTAMP = "2026-08-23T01:02:04.000000Z"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_workbench_fixture(tmp_path, *, curation_status="raw_unreviewed"):
    session = tmp_path / "artifacts" / "workbench" / SESSION_ID
    frame = np.full((24, 40, 3), 127, dtype=np.uint8)
    frame_path = session / "frames" / "frame-00000017.png"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(frame_path), frame)
    summary = {
        "session_id": SESSION_ID,
        "curation_status": curation_status,
        "curated": False,
    }
    _write_json(session / "summary.json", summary)
    event = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "event_type": "evidence.frame",
        "timestamp": EVENT_TIMESTAMP,
        "payload": {
            "sequence": SEQUENCE,
            "frame": "frames/frame-00000017.png",
            "frame_shape": [24, 40, 3],
            "reason": "mismatch",
            "human_ground_truth": {
                "base_context": "screen.black_market",
                "base_is_unknown": False,
                "overlays": ["popup.purchase_confirmation"],
                "source": "human_confirmed",
            },
        },
    }
    (session / "events.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8"
    )
    manifest_path = tmp_path / "datasets" / "workbench_evidence_manifest.json"
    _write_json(
        manifest_path,
        {
            "version": 1,
            "entries": [
                {
                    "path": (
                        "screencaps/semantic/workbench/"
                        f"{SESSION_ID}/frame-00000017.png"
                    ),
                    "base_context": "screen.black_market",
                    "overlays": ["popup.purchase_confirmation"],
                    "review_status": "confirmed",
                    "metadata": {
                        "source": "workbench",
                        "session_id": SESSION_ID,
                        "sequence": SEQUENCE,
                        "event_timestamp_utc": EVENT_TIMESTAMP,
                        "evidence_reason": "mismatch",
                        "frame_shape": [24, 40, 3],
                    },
                }
            ],
        },
    )
    return session, frame_path, manifest_path


def test_workbench_manifest_parsing_preserves_safe_provenance(tmp_path):
    _, _, manifest_path = _build_workbench_fixture(tmp_path)

    records = load_workbench_evidence_manifest(manifest_path)

    assert len(records) == 1
    assert records[0].metadata.source == "workbench"
    assert records[0].metadata.session_id == SESSION_ID
    assert records[0].metadata.sequence == SEQUENCE
    assert records[0].entry.review_status == "confirmed"


def test_curated_workbench_manifest_contains_only_reviewed_phase3f_selection():
    repository_root = Path(__file__).resolve().parents[1]

    records = load_workbench_evidence_manifest(
        repository_root / "datasets" / "workbench_evidence_manifest.json"
    )

    assert {
        (record.metadata.session_id, record.metadata.sequence)
        for record in records
    } == {
        ("20260823T061544_647270Z-11461340", 1706),
        ("20260823T061544_647270Z-11461340", 1946),
        ("20260823T064721_367331Z-addb7117", 905),
        ("20260823T064721_367331Z-addb7117", 1145),
        ("20260823T064721_367331Z-addb7117", 1214),
    }
    assert all(record.metadata.source == "workbench" for record in records)
    assert all(not Path(record.entry.path).is_absolute() for record in records)


def test_workbench_promotion_validates_and_copies_untouched_png(tmp_path):
    _, source, manifest_path = _build_workbench_fixture(tmp_path)

    records = materialize_workbench_evidence(
        tmp_path,
        manifest_path=manifest_path,
        artifacts_root="artifacts/workbench",
    )

    destination = tmp_path / records[0].entry.path
    assert destination.read_bytes() == source.read_bytes()


def test_workbench_promotion_accepts_current_v2_evidence_schema(tmp_path):
    session, source, manifest_path = _build_workbench_fixture(tmp_path)
    event_path = session / "events.jsonl"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["schema_version"] = "2.0"
    event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    records = materialize_workbench_evidence(
        tmp_path,
        manifest_path=manifest_path,
        artifacts_root="artifacts/workbench",
    )

    assert (tmp_path / records[0].entry.path).read_bytes() == source.read_bytes()


@pytest.mark.parametrize("curation_status", ["diagnostic", None])
def test_workbench_promotion_excludes_non_promotable_sessions(
    tmp_path, curation_status
):
    session, _, manifest_path = _build_workbench_fixture(
        tmp_path, curation_status=curation_status
    )
    if curation_status is None:
        summary_path = session / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.pop("curation_status")
        _write_json(summary_path, summary)

    with pytest.raises(ValueError, match="not promotable"):
        materialize_workbench_evidence(
            tmp_path,
            manifest_path=manifest_path,
            artifacts_root="artifacts/workbench",
        )


def test_workbench_promotion_rejects_label_contradictions(tmp_path):
    session, _, manifest_path = _build_workbench_fixture(tmp_path)
    event_path = session / "events.jsonl"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["payload"]["human_ground_truth"]["overlays"] = []
    event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="contradict"):
        materialize_workbench_evidence(
            tmp_path,
            manifest_path=manifest_path,
            artifacts_root="artifacts/workbench",
        )


@pytest.mark.parametrize(
    ("field", "candidate", "message"),
    [
        ("base_context", "screen.guild_shop", "valid base_context"),
        ("overlays", ["popup.unsupported"], "unsupported overlay"),
    ],
)
def test_phase3f_promotion_rejects_acquisition_candidates(
    tmp_path, field, candidate, message
):
    session, _, manifest_path = _build_workbench_fixture(tmp_path)
    event_path = session / "events.jsonl"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    event["payload"]["human_ground_truth"][field] = candidate
    manifest["entries"][0][field] = candidate
    event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match=message):
        materialize_workbench_evidence(
            tmp_path,
            manifest_path=manifest_path,
            artifacts_root="artifacts/workbench",
        )
