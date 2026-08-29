import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.production_perception_evaluation import (
    load_workbench_evidence_manifest,
    materialize_workbench_evidence,
)
from tools.incremental_perception_evaluation import (
    evaluate_detector_frame_pairs,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resolver import ContextResolver, ContextRule
from bot.state import ResolutionStatus


SESSION_ID = "20260823T010203_000000Z-example"
SEQUENCE = 17
EVENT_TIMESTAMP = "2026-08-23T01:02:04.000000Z"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class CountingDetector:
    def __init__(
        self,
        evaluation_id,
        *names,
        confidence=0.95,
        config="v1",
        asset_path=None,
    ):
        self.evaluation_id = evaluation_id
        self.names = names or ("landmark.incremental",)
        self.confidence = confidence
        self.config = config
        self.asset_path = asset_path
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        return tuple(
            Observation(name, self.confidence, ObservationSource.LOCAL_CV)
            for name in self.names
        )


class AlternateCountingDetector(CountingDetector):
    pass


def _write_frame(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(
        str(path), np.full((16, 24, 3), value, dtype=np.uint8)
    )


def _incremental_evaluate(
    root, paths, detectors, *, full_rebuild=False, cache_name="pairs.json"
):
    return evaluate_detector_frame_pairs(
        root,
        paths,
        detectors,
        cache_path=Path("artifacts") / cache_name,
        full_rebuild=full_rebuild,
    )


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


def test_incremental_evaluation_executes_uncached_then_reuses_unchanged_pairs(
    tmp_path,
):
    frame = tmp_path / "frames/a.png"
    _write_frame(frame, 10)
    first_detector = CountingDetector("detector.a")

    first, first_stats = _incremental_evaluate(
        tmp_path, ["frames/a.png"], [first_detector]
    )
    second_detector = CountingDetector("detector.a")
    second, second_stats = _incremental_evaluate(
        tmp_path, ["frames/a.png"], [second_detector]
    )

    assert first_detector.calls == 1
    assert first_stats.total_pairs == 1
    assert first_stats.cache_hits == 0
    assert first_stats.evaluated_pairs == 1
    assert second_detector.calls == 0
    assert second_stats.cache_hits == 1
    assert second_stats.evaluated_pairs == 0
    assert second == first


def test_changed_frame_invalidates_only_its_existing_detector_pair(tmp_path):
    first = tmp_path / "frames/a.png"
    second = tmp_path / "frames/b.png"
    _write_frame(first, 10)
    _write_frame(second, 20)
    _incremental_evaluate(
        tmp_path,
        ["frames/a.png", "frames/b.png"],
        [CountingDetector("detector.a")],
    )
    _write_frame(second, 30)
    detector = CountingDetector("detector.a")

    _, stats = _incremental_evaluate(
        tmp_path,
        ["frames/a.png", "frames/b.png"],
        [detector],
    )

    assert detector.calls == 1
    assert stats.cache_hits == 1
    assert stats.evaluated_pairs == 1
    assert stats.invalidations == 1


def test_new_frame_runs_against_each_existing_detector(tmp_path):
    _write_frame(tmp_path / "frames/a.png", 10)
    _incremental_evaluate(
        tmp_path, ["frames/a.png"], [CountingDetector("detector.a")]
    )
    _write_frame(tmp_path / "frames/b.png", 20)
    detector = CountingDetector("detector.a")

    _, stats = _incremental_evaluate(
        tmp_path,
        ["frames/a.png", "frames/b.png"],
        [detector],
    )

    assert detector.calls == 1
    assert stats.cache_hits == 1
    assert stats.evaluated_pairs == 1


def test_new_detector_runs_against_the_whole_existing_corpus(tmp_path):
    paths = ["frames/a.png", "frames/b.png"]
    _write_frame(tmp_path / paths[0], 10)
    _write_frame(tmp_path / paths[1], 20)
    _incremental_evaluate(
        tmp_path, paths, [CountingDetector("detector.a")]
    )
    existing = CountingDetector("detector.a")
    added = CountingDetector("detector.b")

    _, stats = _incremental_evaluate(tmp_path, paths, [existing, added])

    assert existing.calls == 0
    assert added.calls == 2
    assert stats.cache_hits == 2
    assert stats.evaluated_pairs == 2


@pytest.mark.parametrize(
    "replacement",
    [
        lambda asset: CountingDetector("detector.a", config="v2"),
        lambda asset: AlternateCountingDetector("detector.a"),
    ],
    ids=("config", "detector-code"),
)
def test_changed_config_or_detector_invalidates_its_pair(tmp_path, replacement):
    _write_frame(tmp_path / "frames/a.png", 10)
    _incremental_evaluate(
        tmp_path, ["frames/a.png"], [CountingDetector("detector.a")]
    )
    detector = replacement(None)

    _, stats = _incremental_evaluate(
        tmp_path, ["frames/a.png"], [detector]
    )

    assert detector.calls == 1
    assert stats.cache_hits == 0
    assert stats.evaluated_pairs == 1
    assert stats.invalidations == 1


def test_changed_asset_content_invalidates_its_detector_pair(tmp_path):
    _write_frame(tmp_path / "frames/a.png", 10)
    asset = tmp_path / "assets/template.png"
    _write_frame(asset, 40)
    _incremental_evaluate(
        tmp_path,
        ["frames/a.png"],
        [CountingDetector("detector.a", asset_path=asset)],
    )
    _write_frame(asset, 50)
    detector = CountingDetector("detector.a", asset_path=asset)

    _, stats = _incremental_evaluate(
        tmp_path, ["frames/a.png"], [detector]
    )

    assert detector.calls == 1
    assert stats.invalidations == 1


def test_full_rebuild_ignores_valid_cached_pairs(tmp_path):
    _write_frame(tmp_path / "frames/a.png", 10)
    _incremental_evaluate(
        tmp_path, ["frames/a.png"], [CountingDetector("detector.a")]
    )
    detector = CountingDetector("detector.a")

    _, stats = _incremental_evaluate(
        tmp_path,
        ["frames/a.png"],
        [detector],
        full_rebuild=True,
    )

    assert detector.calls == 1
    assert stats.cache_hits == 0
    assert stats.evaluated_pairs == 1
    assert stats.cache_rebuilt is True


def test_cached_observations_preserve_wrong_and_ambiguous_resolution(tmp_path):
    _write_frame(tmp_path / "frames/a.png", 10)
    resolver = ContextResolver(
        base_rules=(
            ContextRule("screen.actual", ("landmark.actual",), 0.8),
            ContextRule("screen.other", ("landmark.other",), 0.8),
        )
    )

    cases = (
        ("wrong", ("landmark.actual",), ResolutionStatus.RESOLVED),
        (
            "ambiguous",
            ("landmark.actual", "landmark.other"),
            ResolutionStatus.AMBIGUOUS,
        ),
    )
    for cache_name, names, expected_status in cases:
        _incremental_evaluate(
            tmp_path,
            ["frames/a.png"],
            [CountingDetector("detector.a", *names)],
            cache_name=cache_name + ".json",
        )
        cached, stats = _incremental_evaluate(
            tmp_path,
            ["frames/a.png"],
            [CountingDetector("detector.a", *names)],
            cache_name=cache_name + ".json",
        )
        batch = ObservationBatch(1, 1.0, cached[0].observations)
        state = resolver.resolve(batch)

        assert stats.cache_hits == 1
        assert state.status is expected_status
        assert not (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context == "screen.expected"
        )


@pytest.mark.parametrize(
    "payload", ["not-json", json.dumps({"version": 999, "pairs": {}})]
)
def test_corrupt_or_incompatible_cache_rebuilds_conservatively(tmp_path, payload):
    _write_frame(tmp_path / "frames/a.png", 10)
    cache = tmp_path / "artifacts/pairs.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(payload, encoding="utf-8")
    detector = CountingDetector("detector.a")

    _, stats = _incremental_evaluate(
        tmp_path, ["frames/a.png"], [detector]
    )

    assert detector.calls == 1
    assert stats.cache_hits == 0
    assert stats.evaluated_pairs == 1
    assert stats.cache_rebuilt is True
    assert json.loads(cache.read_text(encoding="utf-8"))["version"] == 1


def test_multiple_missing_detectors_decode_each_frame_only_once(tmp_path, monkeypatch):
    _write_frame(tmp_path / "frames/a.png", 10)
    real_imdecode = cv2.imdecode
    calls = []

    def counted_imdecode(*args, **kwargs):
        calls.append(1)
        return real_imdecode(*args, **kwargs)

    monkeypatch.setattr(cv2, "imdecode", counted_imdecode)

    _incremental_evaluate(
        tmp_path,
        ["frames/a.png"],
        [CountingDetector("detector.a"), CountingDetector("detector.b")],
    )

    assert len(calls) == 1
