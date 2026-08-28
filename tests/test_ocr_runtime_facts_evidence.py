import json
from pathlib import Path

import cv2
import pytest

from bot.action_executor import FrameGeometry
from bot.catalog import SCREEN_LOBBY, SCREEN_WORLD_BOSS_BATTLE
from bot.capture import FrameSnapshot
from bot.ocr import RapidOcrEngine
from bot.ocr_extractors import build_sapphires_extractor, build_timer_extractor
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "datasets/ocr_runtime_facts_evidence_manifest.json"


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_sapphires_evidence_uses_survival_counter_and_preserves_real_variation():
    payload = load_manifest()
    curation = payload["curation"]
    live = payload["sapphires_live"]
    prior = payload["sapphires_prior_evidence"]

    assert curation["sapphires_roi"] == [0.77, 0.43, 0.855, 0.505]
    assert curation["rejected_sapphires_candidate"]["roi"] == [
        0.845,
        0.59,
        0.945,
        0.68,
    ]
    assert len(live) == 3
    assert all(item["value"] == 247 for item in live)
    assert all(item["raw_texts"] == ["247/66", "247/66"] for item in live)
    assert all(item["review_status"] == "human_confirmed" for item in live)
    assert {item["value"] for item in prior} == {257}
    assert "No resource was spent" in curation["dataset_limitation"]


def test_timer_evidence_is_human_confirmed_and_strictly_decreasing():
    entries = load_manifest()["timer_live"]

    assert len(entries) == 5
    assert [item["raw_text"] for item in entries] == [
        "0:55.4",
        "0:52.0",
        "0:50.4",
        "0.48.8",
        "0:47.3",
    ]
    values = [item["value_seconds"] for item in entries]
    assert values == sorted(values, reverse=True)
    assert len(values) == len(set(values))
    assert all(item["review_status"] == "human_confirmed" for item in entries)


def test_product_ocr_extractors_replay_curated_live_evidence_when_present():
    payload = load_manifest()
    cases = [
        *(
            (item["paths"][0], SCREEN_LOBBY, item["value"], "sapphires")
            for item in payload["sapphires_live"]
        ),
        *(
            (
                item["path"],
                SCREEN_WORLD_BOSS_BATTLE,
                item["value_seconds"],
                "timer",
            )
            for item in payload["timer_live"]
        ),
    ]
    missing = [path for path, _, _, _ in cases if not (REPOSITORY_ROOT / path).is_file()]
    if missing:
        pytest.skip("local OCR live evidence corpus is not present")

    engine = RapidOcrEngine()
    extractors = {
        "sapphires": build_sapphires_extractor(engine),
        "timer": build_timer_extractor(engine),
    }
    for sequence, (path, context, expected, kind) in enumerate(cases, start=1):
        image = cv2.imread(str(REPOSITORY_ROOT / path), cv2.IMREAD_COLOR)
        assert image is not None
        frame = FrameSnapshot(image, float(sequence), sequence)
        batch = ObservationBatch(sequence, float(sequence))
        state = ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=context,
        )
        snapshot = RuntimeSnapshot(
            frame,
            batch,
            state,
            RuntimeFacts(),
            FrameGeometry.from_frame(image),
        )

        result = extractors[kind].extract(snapshot)

        assert result.value == expected, path
