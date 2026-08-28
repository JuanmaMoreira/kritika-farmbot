import json
from pathlib import Path

import cv2
import pytest

from bot.catalog import (
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    OVERLAY_WORLD_BOSS_RAID_COMPLETE,
    OVERLAY_WORLD_BOSS_SELECT_BOSS,
    POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE,
    build_default_resolver,
)
from bot.capture import FrameSnapshot
from bot.perception import build_default_perception
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "datasets/world_boss_semantic_manifest.json"
QUICK_MENU_MANIFEST_PATH = (
    REPOSITORY_ROOT / "datasets/world_boss_quick_menu_evidence_manifest.json"
)
TEMPORAL_MANIFEST_PATH = (
    REPOSITORY_ROOT / "datasets/world_boss_temporal_evidence_manifest.json"
)
NEW_LANDMARKS = {
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
}


@pytest.fixture(scope="module")
def evaluated_entries():
    engine = build_default_perception(REPOSITORY_ROOT)
    resolver = build_default_resolver()
    results = []
    entries = load_manifest(MANIFEST_PATH)
    missing = [
        entry.path
        for entry in entries
        if not (REPOSITORY_ROOT / entry.path).is_file()
    ]
    if missing:
        pytest.skip("local World Boss evidence corpus is not present")
    for sequence, entry in enumerate(entries, start=1):
        frame = cv2.imread(str(REPOSITORY_ROOT / entry.path), cv2.IMREAD_COLOR)
        assert frame is not None
        batch = engine.analyze(
            FrameSnapshot(frame, timestamp=float(sequence), sequence=sequence)
        )
        results.append((entry, batch, resolver.resolve(batch)))
    return tuple(results)


def test_manifest_preserves_multiple_confirmed_frames_for_every_context():
    entries = load_manifest(MANIFEST_PATH)

    assert len(entries) == 44
    assert all(entry.review_status == "confirmed" for entry in entries)
    assert sum(entry.base_context == SCREEN_BATTLE_MODE_SELECT for entry in entries) == 6
    assert sum(OVERLAY_WORLD_BOSS_SELECT_BOSS in entry.overlays for entry in entries) == 4
    assert sum(
        POPUP_WORLD_BOSS_PREVIOUS_REWARDS in entry.overlays for entry in entries
    ) == 5
    assert sum(entry.base_context == SCREEN_WORLD_BOSS for entry in entries) == 8
    assert sum(entry.base_context == SCREEN_WORLD_BOSS_BATTLE for entry in entries) == 21
    assert sum(OVERLAY_WORLD_BOSS_RAID_COMPLETE in entry.overlays for entry in entries) == 8


def test_every_world_boss_frame_resolves_to_its_confirmed_semantics(evaluated_entries):
    for entry, _, state in evaluated_entries:
        expected_base = None if entry.base_context == "unknown" else entry.base_context
        expected_status = (
            ResolutionStatus.UNKNOWN
            if expected_base is None
            else ResolutionStatus.RESOLVED
        )
        assert state.status is expected_status, entry.path
        assert state.base_context == expected_base, entry.path
        assert state.overlays == entry.overlays, entry.path


def test_world_boss_landmarks_have_no_cross_context_emissions(evaluated_entries):
    expected_counts = {
        LANDMARK_BATTLE_MODE_SELECT_HEADER: 6,
        LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER: 4,
        LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE: 5,
        LANDMARK_WORLD_BOSS_SAPPHIRES_USED: 8,
        LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE: 21,
        LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE: 8,
    }
    actual_counts = {name: 0 for name in NEW_LANDMARKS}

    for _, batch, _ in evaluated_entries:
        emitted = {item.name for item in batch.observations} & NEW_LANDMARKS
        for name in emitted:
            actual_counts[name] += 1

    assert actual_counts == expected_counts


def test_manifest_keeps_future_fact_rois_without_implementing_ocr():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rois = payload["curation"]["candidate_rois"]
    evidence = payload["curation"]["candidate_roi_evidence"]

    assert {
        "lobby_sapphires",
        "battle_mode_world_boss_total_rank",
        "world_boss_my_rank",
        "world_boss_sapphires_cost",
        "world_boss_start",
        "world_boss_auto_repeat",
        "world_boss_battle_auto",
        "world_boss_battle_timer",
        "previous_rewards_ok",
        "raid_complete_safe_tap",
    } == set(rois)
    assert all(
        0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0
        for x1, y1, x2, y2 in rois.values()
    )
    assert len(evidence["lobby_sapphires"]) == 3
    assert len(evidence["battle_mode_world_boss_total_rank"]) == 3
    assert len(evidence["world_boss_main_controls_and_facts"]) == 3
    assert len(evidence["previous_rewards_ok"]) == 3
    assert len(evidence["world_boss_battle_timer"]) == 5
    assert len(evidence["raid_complete_safe_tap"]) == 3


def test_quick_menu_evidence_does_not_invent_an_obscured_base_context():
    entries = load_manifest(QUICK_MENU_MANIFEST_PATH)

    assert len(entries) == 4
    assert all(entry.base_context == "unknown" for entry in entries)
    assert all(entry.overlays == ("menu.quick",) for entry in entries)
    assert all(entry.review_status == "confirmed" for entry in entries)


def test_temporal_evidence_preserves_auto_off_and_on_sequences():
    payload = json.loads(TEMPORAL_MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]
    metrics = payload["curation"]["sequence_metrics"]

    assert len(entries) == 8
    assert sum(entry["state"] == "auto_off" for entry in entries) == 4
    assert sum(entry["state"] == "auto_on" for entry in entries) == 4
    assert all(entry["review_status"] == "confirmed" for entry in entries)
    paths = [entry["path"] for entry in entries]
    assert len(paths) == len(set(paths))
    assert all(
        path.startswith("screencaps/semantic/world_boss/battle/")
        for path in paths
    )
    assert (
        metrics["auto_on"]["mean_consecutive_absolute_difference"]
        > metrics["auto_off"]["mean_consecutive_absolute_difference"] * 5
    )
    assert "no product detector" in payload["curation"]["scope"]
