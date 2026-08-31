from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    INDICATOR_GUILD_ATTENDANCE_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_COMPLETED,
    MENU_QUICK,
    SCREEN_GUILD,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    build_default_resolver,
)
from bot.perception import GuildAttendanceDetector, build_default_perception
from bot.state import ResolutionStatus
from tools.guild_semantic_evaluation import evaluate_guild_semantics
from tools.semantic_slice_evaluation import load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/guild_semantic_manifest.json"


def _read(relative_path):
    frame = cv2.imread(str(ROOT / relative_path), cv2.IMREAD_COLOR)
    assert frame is not None, relative_path
    return frame


def _resolve(relative_path, sequence=1):
    frame = _read(relative_path)
    batch = build_default_perception(ROOT).analyze(
        FrameSnapshot(frame, float(sequence), sequence)
    )
    return batch, build_default_resolver().resolve(batch)


def test_curated_guild_evaluator_confirms_all_states_and_navigation_evidence():
    report = evaluate_guild_semantics(ROOT, MANIFEST)

    assert report.entries == 19
    assert report.correct == report.entries
    assert report.wrong_paths == ()
    assert report.active_value_min > report.completed_value_max
    assert report.completed_bubble_frames == 2
    assert report.completed_bubble_frames_correct == 2
    assert report.quick_menu_from_guild_frames == 3
    assert report.quick_menu_from_guild_frames_correct == 3
    assert report.lobby_quick_menu_guild_route_confirmed
    assert report.transition_upper_bound_seconds == pytest.approx(0.74814)


def test_attendance_detector_emits_one_explicit_state_on_clean_guild():
    entries = load_manifest(MANIFEST)
    pending = next(entry for entry in entries if "/pending/" in entry.path)
    completed = next(entry for entry in entries if "/completed/" in entry.path)
    detector = GuildAttendanceDetector(asset_root=ROOT)

    pending_names = {item.name for item in detector.detect(_read(pending.path))}
    completed_names = {item.name for item in detector.detect(_read(completed.path))}

    assert pending_names == {INDICATOR_GUILD_ATTENDANCE_ACTIVE}
    assert completed_names == {INDICATOR_GUILD_ATTENDANCE_COMPLETED}


def test_bubble_does_not_occlude_guild_or_completed_attendance_signal():
    entries = load_manifest(MANIFEST)
    bubble_entries = [
        entry for entry in entries if "completed-bubble" in entry.path
    ]

    for sequence, entry in enumerate(bubble_entries, start=1):
        _, state = _resolve(entry.path, sequence)
        assert state.status is ResolutionStatus.RESOLVED
        assert state.base_context == SCREEN_GUILD
        assert state.overlays == (STATUS_GUILD_ATTENDANCE_COMPLETED,)


def test_quick_menu_from_guild_suppresses_business_status_but_preserves_base():
    entries = load_manifest(MANIFEST)
    quick = next(
        entry for entry in entries if "/quick-menu-from-guild/" in entry.path
    )

    batch, state = _resolve(quick.path)
    names = {item.name for item in batch.observations}

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_GUILD
    assert state.overlays == (MENU_QUICK,)
    assert INDICATOR_GUILD_ATTENDANCE_ACTIVE not in names
    assert INDICATOR_GUILD_ATTENDANCE_COMPLETED not in names


def test_active_and_completed_statuses_are_mutually_exclusive_in_manifest():
    for sequence, entry in enumerate(load_manifest(MANIFEST), start=1):
        if entry.base_context != SCREEN_GUILD or entry.overlays == (MENU_QUICK,):
            continue
        _, state = _resolve(entry.path, sequence)
        statuses = set(state.overlays) & {
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_COMPLETED,
        }
        assert len(statuses) == 1, entry.path
