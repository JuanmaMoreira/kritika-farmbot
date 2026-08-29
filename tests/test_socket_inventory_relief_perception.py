import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE,
    POPUP_SOCKET_ENHANCE_ALL,
    POPUP_SOCKET_NO_MATERIAL,
    POPUP_SOCKET_SELL,
    SCREEN_SOCKET,
    build_default_resolver,
)
from bot.perception import (
    SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION,
    SOCKET_INCOMPATIBLE_OPAL_ASSET,
    SOCKET_INCOMPATIBLE_OPAL_OBSERVATION,
    SOCKET_OPAL_SLOT_REGIONS,
    SocketEnhanceAnimationDetector,
    SocketIncompatibleOpalDetector,
    build_default_perception,
)
from bot.state import ResolutionStatus


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/socket_inventory_relief_semantic_manifest.json"


def _payload():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _entry(suffix):
    item = next(
        entry for entry in _payload()["entries"]
        if entry["path"].endswith(suffix)
    )
    path = ROOT / item["path"]
    if not path.is_file():
        pytest.skip("local curated Socket evidence is not present")
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert frame is not None
    return frame


def _state(frame, sequence=1):
    observations = build_default_perception(ROOT).analyze(
        FrameSnapshot(frame, float(sequence), sequence)
    )
    return observations, build_default_resolver().resolve(observations)


def test_manifest_preserves_destructive_guard_and_karats_prohibition():
    payload = _payload()

    assert payload["curation"]["safety"]["karats_used"] is False
    assert payload["curation"]["acquired_targets"]["gold_enhance"] != (
        payload["curation"]["acquired_targets"]["karat_enhance_forbidden"]
    )
    assert "+0" in payload["curation"]["safety"]["single_real_sale"]
    assert payload["curation"]["safety"]["level_10_disposition"] == "Cancel"
    assert any(
        transition["to"] == "popup.socket_no_material"
        and transition["meaning"] == "NO_EFFECT"
        for transition in payload["transitions"]
    )
    assert any(
        transition["from"]
        == "screen.world_boss + popup.socket_inventory_full"
        and transition["to"] == "screen.socket"
        for transition in payload["transitions"]
    )
    assert any(
        transition["from"] == "screen.socket"
        and transition["to"] == "screen.world_boss"
        for transition in payload["transitions"]
    )


@pytest.mark.parametrize(
    ("suffix", "expected_overlays"),
    (
        ("socket/stable.png", ()),
        ("enhance/modal.png", (POPUP_SOCKET_ENHANCE_ALL,)),
        ("enhance/after-safe-tap-socket.png", ()),
        (
            "enhance/no-material.png",
            (POPUP_SOCKET_ENHANCE_ALL, POPUP_SOCKET_NO_MATERIAL),
        ),
        ("sell/level-0-popup.png", (POPUP_SOCKET_SELL,)),
        ("sell/level-10-popup.png", (POPUP_SOCKET_SELL,)),
    ),
)
def test_curated_socket_states_resolve_base_and_expected_overlay(
    suffix, expected_overlays
):
    _, state = _state(_entry(suffix))

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_SOCKET
    assert state.overlays == expected_overlays


def test_equipment_home_emits_active_tab_and_only_red_veil_slots():
    detector = SocketIncompatibleOpalDetector(asset_root=ROOT)
    red_frame = _entry("equipment_home/red-grid.png")
    empty_frame = _entry("equipment_home/no-red-candidates.png")
    red_observations, red_state = _state(red_frame)
    empty_observations, empty_state = _state(empty_frame, sequence=2)

    red_slots = tuple(item.value for item in detector.detect(red_frame))

    assert red_state.base_context == SCREEN_SOCKET
    assert empty_state.base_context == SCREEN_SOCKET
    assert red_observations.best(LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE)
    assert empty_observations.best(LANDMARK_SOCKET_EQUIPMENT_HOME_ACTIVE)
    assert red_slots == tuple(range(4, 16))
    assert detector.detect(empty_frame) == ()
    assert red_observations.find(SOCKET_INCOMPATIBLE_OPAL_OBSERVATION)
    assert empty_observations.find(SOCKET_INCOMPATIBLE_OPAL_OBSERVATION) == ()


def test_bulk_sale_stable_postcondition_removes_prior_red_slot_without_frame_equality():
    detector = SocketIncompatibleOpalDetector(asset_root=ROOT)
    before = _entry("equipment_home/red-grid.png")
    after = _entry("sell/bulk-stable-after.png")

    before_slots = {item.value for item in detector.detect(before)}
    after_slots = {item.value for item in detector.detect(after)}
    _, after_state = _state(after)

    assert 4 in before_slots
    assert 4 not in after_slots
    assert after_state.base_context == SCREEN_SOCKET
    assert POPUP_SOCKET_SELL not in after_state.overlays
    assert not np.array_equal(before, after)


def test_animation_dark_stages_authorize_observation_but_bright_flash_does_not():
    detector = SocketEnhanceAnimationDetector()
    dark = _entry("enhance/dark-stage.png")
    success = _entry("enhance/success-stage.png")
    flash = _entry("enhance/bright-flash.png")
    stable = _entry("socket/stable.png")

    assert detector.detect(dark)[0].name == (
        SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION
    )
    assert detector.detect(success)[0].name == (
        SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION
    )
    assert detector.detect(flash) == ()
    assert detector.detect(stable) == ()


def test_animation_gate_rejects_dark_periphery_with_bright_center():
    detector = SocketEnhanceAnimationDetector()
    frame = np.zeros((200, 400, 3), dtype=np.uint8)
    frame[36:164, 88:312] = 160

    assert detector.detect(frame) == ()


def test_incompatible_opal_detector_preserves_row_major_slot_identity():
    detector = SocketIncompatibleOpalDetector(asset_root=ROOT)
    asset = cv2.imread(
        str(ROOT / SOCKET_INCOMPATIBLE_OPAL_ASSET), cv2.IMREAD_COLOR
    )
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    region = SOCKET_OPAL_SLOT_REGIONS[6]
    x1, y1, x2, y2 = (
        int(region[0] * frame.shape[1]),
        int(region[1] * frame.shape[0]),
        int(region[2] * frame.shape[1]),
        int(region[3] * frame.shape[0]),
    )
    top = y1 + (y2 - y1 - asset.shape[0]) // 2
    left = x1 + (x2 - x1 - asset.shape[1]) // 2
    frame[top : top + asset.shape[0], left : left + asset.shape[1]] = asset

    observations = detector.detect(frame)

    assert tuple(item.value for item in observations) == (6,)
    assert observations[0].region == SOCKET_OPAL_SLOT_REGIONS[6]
