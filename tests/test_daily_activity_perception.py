from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE,
    INDICATOR_WORLD_BOSS_DAILY_ACTIVE,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_FRIENDS,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.perception import build_default_perception
from bot.state import ResolutionStatus
from tools.daily_activity_semantic_evaluation import (
    evaluate_daily_activity_semantics,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/daily_activity_semantic_manifest.json"


def _resolve(path: str):
    frame = cv2.imread(str(ROOT / path), cv2.IMREAD_COLOR)
    assert frame is not None, path
    batch = build_default_perception(ROOT).analyze(FrameSnapshot(frame, 1.0, 1))
    return batch, build_default_resolver().resolve(batch)


def test_daily_activity_evaluator_confirms_curated_semantics_and_transitions():
    report = evaluate_daily_activity_semantics(ROOT, MANIFEST)

    assert report.entries == 22
    assert report.correct == report.entries
    assert report.wrong_paths == ()
    assert report.friends_daily_active_frames == 4
    assert report.friends_daily_inactive_frames == 5
    assert report.friends_transition_verified
    assert report.friends_close_to_lobby_verified
    assert report.guild_daily_active_frames == 3
    assert report.guild_completed_daily_absent_frames == 3
    assert report.guild_actionable_daily_absent_frames == 0
    assert report.world_boss_daily_active_frames == 3
    assert report.world_boss_daily_inactive_frames == 3
    assert report.shared_daily_asset == (
        "assets/ui/indicators/daily-mission-badge-current.png"
    )
    assert report.sampled_friends_transition_upper_bound_seconds == pytest.approx(
        0.201022
    )
    assert report.curated_friends_absence_stability_seconds == pytest.approx(
        0.797902
    )


def test_friends_daily_indicator_disappears_while_friends_remains_resolved():
    active_batch, active = _resolve(
        "screencaps/semantic/daily_activity/friends/daily-active/01.png"
    )
    inactive_batch, inactive = _resolve(
        "screencaps/semantic/daily_activity/friends/daily-inactive/01.png"
    )

    assert active.status is ResolutionStatus.RESOLVED
    assert active.base_context == SCREEN_FRIENDS
    assert active.overlays == (STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,)
    assert active_batch.best(INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE)
    assert inactive.status is ResolutionStatus.RESOLVED
    assert inactive.base_context == SCREEN_FRIENDS
    assert inactive.overlays == ()
    assert inactive_batch.best(INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE) is None


def test_friends_close_returns_to_lobby_without_daily_observations():
    batch, state = _resolve(
        "screencaps/semantic/daily_activity/friends/close-lobby/01.png"
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_LOBBY
    assert state.overlays == ()
    assert not {
        item.name for item in batch.observations
    } & {
        INDICATOR_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
        INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE,
        INDICATOR_WORLD_BOSS_DAILY_ACTIVE,
    }


def test_guild_daily_is_independent_from_existing_attendance_state():
    active_batch, active = _resolve(
        "screencaps/semantic/daily_activity/guild/daily-active/01.png"
    )
    completed_batch, completed = _resolve(
        "screencaps/semantic/guild/completed/01.png"
    )

    assert active.base_context == SCREEN_GUILD
    assert set(active.overlays) == {
        STATUS_GUILD_ATTENDANCE_ACTIVE,
        STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    }
    assert active_batch.best(INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE)
    assert completed.base_context == SCREEN_GUILD
    assert completed.overlays == (STATUS_GUILD_ATTENDANCE_COMPLETED,)
    assert completed_batch.best(INDICATOR_GUILD_ATTENDANCE_DAILY_ACTIVE) is None


def test_world_boss_daily_uses_only_its_card_badge():
    active_batch, active = _resolve(
        "screencaps/semantic/daily_activity/world-boss/daily-active/01.png"
    )
    inactive_batch, inactive = _resolve(
        "screencaps/semantic/daily_activity/world-boss/daily-inactive/01.png"
    )

    assert active.base_context == SCREEN_BATTLE_MODE_SELECT
    assert active.overlays == (STATUS_WORLD_BOSS_DAILY_ACTIVE,)
    assert active_batch.best(INDICATOR_WORLD_BOSS_DAILY_ACTIVE)
    assert inactive.base_context == SCREEN_BATTLE_MODE_SELECT
    assert inactive.overlays == ()
    assert inactive_batch.best(INDICATOR_WORLD_BOSS_DAILY_ACTIVE) is None
