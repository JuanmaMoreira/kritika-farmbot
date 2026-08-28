import json
from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_WORLD_BOSS_INVENTORY_FULL,
    SCREEN_WORLD_BOSS,
    build_default_resolver,
)
from bot.perception import build_default_perception
from bot.state import ResolutionStatus


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/world_boss_inventory_full_evidence_manifest.json"


def test_manifest_preserves_human_confirmed_branch_and_deferred_resolution():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(payload["entries"]) == 2
    assert payload["curation"]["semantic_state"] == {
        "base_context": SCREEN_WORLD_BOSS,
        "overlays": [POPUP_WORLD_BOSS_INVENTORY_FULL],
    }
    assert payload["curation"]["action"]["normalized_target"] == [0.569, 0.6307]
    assert "resuming WorldBossFlow" in payload["curation"]["deferred"]


def test_live_frames_resolve_world_boss_plus_inventory_full_popup():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = [ROOT / entry["path"] for entry in payload["entries"]]
    if not all(path.is_file() for path in paths):
        pytest.skip("local World Boss inventory-full evidence is not present")
    perception = build_default_perception(ROOT)
    resolver = build_default_resolver()

    for sequence, path in enumerate(paths, start=1):
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        state = resolver.resolve(
            perception.analyze(FrameSnapshot(frame, float(sequence), sequence))
        )
        assert state.status is ResolutionStatus.RESOLVED
        assert state.base_context == SCREEN_WORLD_BOSS
        assert state.overlays == (POPUP_WORLD_BOSS_INVENTORY_FULL,)
