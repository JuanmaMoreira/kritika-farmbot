from collections import defaultdict
from pathlib import Path, PurePosixPath

import cv2

from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    INDICATOR_COMBINE_ROW_BOTTOM,
    INDICATOR_COMBINE_ROWS,
    INDICATOR_COMBINE_ROWS_UPPER,
    MODE_COMBINE_FUSE,
    MODE_COMBINE_TRANSMUTE,
    POPUP_EQUIPMENT_INVENTORY_FULL,
    SCREEN_COMBINE,
    SCREEN_WORLD_BOSS,
    STATUS_COMBINE_ETHEREAL_AVAILABLE,
    STATUS_COMBINE_FUSE_AVAILABLE,
    STATUS_COMBINE_TRANSMUTE_AVAILABLE,
    build_default_resolver,
)
from bot.observations import ObservationBatch
from bot.perception import build_default_perception
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/equipment_inventory_full_semantic_manifest.json"


def _representatives():
    grouped = defaultdict(list)
    for entry in load_manifest(MANIFEST):
        grouped[PurePosixPath(entry.path).parent.name].append(entry)
    return tuple(grouped[name][0] for name in sorted(grouped))


def _resolve(entry, sequence):
    frame = cv2.imread(str(ROOT / entry.path), cv2.IMREAD_COLOR)
    assert frame is not None
    observations = build_default_perception(ROOT).analyze(
        FrameSnapshot(frame, timestamp=float(sequence), sequence=sequence)
    ).observations
    state = build_default_resolver().resolve(
        ObservationBatch(sequence, float(sequence), observations)
    )
    return observations, state


def test_curated_representatives_resolve_the_confirmed_combine_states():
    engine = build_default_perception(ROOT)
    resolver = build_default_resolver()

    for sequence, entry in enumerate(_representatives(), start=1):
        frame = cv2.imread(str(ROOT / entry.path), cv2.IMREAD_COLOR)
        assert frame is not None
        batch = engine.analyze(
            FrameSnapshot(frame, timestamp=float(sequence), sequence=sequence)
        )
        state = resolver.resolve(
            ObservationBatch(sequence, float(sequence), batch.observations)
        )
        expected_base = None if entry.base_context == "unknown" else entry.base_context
        expected_status = (
            ResolutionStatus.RESOLVED
            if expected_base is not None
            else ResolutionStatus.UNKNOWN
        )

        assert state.status is expected_status, entry.path
        assert state.base_context == expected_base, entry.path
        assert state.overlays == entry.overlays, entry.path


def test_equipment_full_popup_is_global_over_the_only_confirmed_caller():
    popup = next(
        entry
        for entry in _representatives()
        if PurePosixPath(entry.path).parent.name == "popup"
    )
    _, state = _resolve(popup, 1)

    assert state.base_context == SCREEN_WORLD_BOSS
    assert state.overlays == (POPUP_EQUIPMENT_INVENTORY_FULL,)


def test_positional_indicators_gate_independent_statuses_and_postconditions():
    entries = {
        PurePosixPath(entry.path).parent.name: entry
        for entry in _representatives()
    }

    observations, transmute = _resolve(entries["transmute-available"], 1)
    names = {item.name for item in observations}
    assert {INDICATOR_COMBINE_ROWS, INDICATOR_COMBINE_ROWS_UPPER,
            INDICATOR_COMBINE_ROW_BOTTOM} <= names
    assert transmute.base_context == SCREEN_COMBINE
    assert {
        MODE_COMBINE_TRANSMUTE,
        STATUS_COMBINE_TRANSMUTE_AVAILABLE,
        STATUS_COMBINE_ETHEREAL_AVAILABLE,
    } <= set(transmute.overlays)

    _, transmute_cleared = _resolve(entries["transmute-cleared"], 2)
    assert STATUS_COMBINE_TRANSMUTE_AVAILABLE not in transmute_cleared.overlays
    assert STATUS_COMBINE_ETHEREAL_AVAILABLE in transmute_cleared.overlays

    _, ethereal_cleared = _resolve(entries["ethereal-cleared-base"], 3)
    assert STATUS_COMBINE_ETHEREAL_AVAILABLE not in ethereal_cleared.overlays

    _, fuse = _resolve(entries["fuse-available"], 4)
    assert MODE_COMBINE_FUSE in fuse.overlays
    assert STATUS_COMBINE_FUSE_AVAILABLE in fuse.overlays

    _, fuse_cleared = _resolve(entries["fuse-cleared"], 5)
    assert STATUS_COMBINE_FUSE_AVAILABLE not in fuse_cleared.overlays


def test_all_three_effects_emit_one_shared_tappable_activity():
    animation_entries = tuple(
        entry
        for entry in load_manifest(MANIFEST)
        if "/animation/" in entry.path
    )

    assert len(animation_entries) == 3
    engine = build_default_perception(ROOT)
    for entry in animation_entries:
        frame = cv2.imread(str(ROOT / entry.path), cv2.IMREAD_COLOR)
        assert frame is not None
        names = {
            item.name
            for item in engine.analyze(
                FrameSnapshot(frame, timestamp=1.0, sequence=1)
            ).observations
        }
        assert ACTIVITY_COMBINE_ANIMATION_TAPPABLE in names
