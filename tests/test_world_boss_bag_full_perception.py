import json
from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_WORLD_BOSS_BAG_FULL,
    SCREEN_WORLD_BOSS,
    build_default_resolver,
)
from bot.perception import build_default_perception
from bot.state import ResolutionStatus


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/world_boss_bag_full_evidence_manifest.json"


def test_manifest_preserves_human_confirmed_close_branch_and_deferred_cleanup():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(payload["entries"]) == 6
    assert len(payload["postcondition_entries"]) == 6
    assert payload["curation"]["semantic_state"] == {
        "base_context": SCREEN_WORLD_BOSS,
        "overlays": [POPUP_WORLD_BOSS_BAG_FULL],
    }
    assert payload["curation"]["action"]["normalized_target"] == [0.67, 0.31]
    assert "inventory cleanup" in payload["curation"]["deferred"]


def test_live_frames_resolve_bag_full_then_clean_world_boss_after_close():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    positive_paths = [ROOT / entry["path"] for entry in payload["entries"]]
    postcondition_paths = [
        ROOT / entry["path"] for entry in payload["postcondition_entries"]
    ]
    if not all(path.is_file() for path in (*positive_paths, *postcondition_paths)):
        pytest.skip("local World Boss bag-full evidence is not present")
    perception = build_default_perception(ROOT)
    resolver = build_default_resolver()

    for sequence, path in enumerate(positive_paths, start=1):
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        state = resolver.resolve(
            perception.analyze(FrameSnapshot(frame, float(sequence), sequence))
        )
        assert state.status is ResolutionStatus.RESOLVED
        assert state.base_context == SCREEN_WORLD_BOSS
        assert state.overlays == (POPUP_WORLD_BOSS_BAG_FULL,)

    offset = len(positive_paths)
    for sequence, path in enumerate(postcondition_paths, start=offset + 1):
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        state = resolver.resolve(
            perception.analyze(FrameSnapshot(frame, float(sequence), sequence))
        )
        assert state.status is ResolutionStatus.RESOLVED
        assert state.base_context == SCREEN_WORLD_BOSS
        assert state.overlays == ()
