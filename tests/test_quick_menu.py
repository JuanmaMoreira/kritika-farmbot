import pytest

from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
)
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.quick_menu import (
    DEFAULT_QUICK_MENU_POLICY,
    QuickMenuPolicy,
    QuickMenuHandoff,
    open_character_select_action,
    quick_menu_accessible,
    select_quick_menu_guild_action,
    select_quick_menu_trading_action,
)
from bot.treasure_center_semantics import SCREEN_TREASURE
from bot.catalog import MENU_QUICK
from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransitionResult, VerifiedTransitionOutcome
import numpy as np
import json
from pathlib import Path
import cv2

from bot.semantic_actions import (
    OpenCharacterSelect,
    QuickMenuLayout,
    SelectQuickMenuGuild,
    SelectQuickMenuTrading,
)


def test_declared_context_has_quick_menu_capability():
    assert quick_menu_accessible(SCREEN_LOBBY)
    assert quick_menu_accessible(SCREEN_WORLD_BOSS)
    assert quick_menu_accessible(SCREEN_GUILD)
    assert quick_menu_accessible(SCREEN_PETS_MANAGE)
    assert quick_menu_accessible(SCREEN_PET_SUMMON)
    assert quick_menu_accessible(SCREEN_TREASURE)


def test_undeclared_context_has_no_quick_menu_capability():
    assert not quick_menu_accessible(SCREEN_BATTLE_MODE_SELECT)
    assert not quick_menu_accessible(None)


def test_capability_is_not_a_semantic_screen():
    assert QUICK_MENU_ACCESSIBLE == "quick_menu_accessible"
    assert not QUICK_MENU_ACCESSIBLE.startswith("screen.")
    assert QUICK_MENU_ACCESSIBLE not in DEFAULT_QUICK_MENU_POLICY.accessible_from


def test_policy_can_be_extended_without_adding_a_synthetic_screen():
    policy = QuickMenuPolicy(
        frozenset({SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT})
    )

    assert policy.allows(SCREEN_BATTLE_MODE_SELECT)
    assert not policy.allows(QUICK_MENU_ACCESSIBLE)


def test_lobby_uses_base_quick_menu_geometry():
    assert open_character_select_action(SCREEN_LOBBY) == OpenCharacterSelect(
        QuickMenuLayout.LOBBY
    )


def test_non_lobby_capable_screen_uses_shifted_quick_menu_geometry():
    assert open_character_select_action(
        SCREEN_WORLD_BOSS
    ) == OpenCharacterSelect(QuickMenuLayout.SHIFTED)

    assert open_character_select_action(
        SCREEN_PETS_MANAGE
    ) == OpenCharacterSelect(QuickMenuLayout.SHIFTED)
    assert open_character_select_action(
        SCREEN_PET_SUMMON
    ) == OpenCharacterSelect(QuickMenuLayout.SHIFTED)


def test_guild_destination_uses_each_acquired_quick_menu_layout():
    assert select_quick_menu_guild_action(SCREEN_LOBBY) == SelectQuickMenuGuild(
        QuickMenuLayout.LOBBY
    )
    assert select_quick_menu_guild_action(SCREEN_GUILD) == SelectQuickMenuGuild(
        QuickMenuLayout.SHIFTED
    )


def test_trading_destination_is_only_exposed_for_verified_treasure_origin():
    assert select_quick_menu_trading_action(
        SCREEN_TREASURE
    ) == SelectQuickMenuTrading()
    with pytest.raises(ValueError, match="verified only from Treasure"):
        select_quick_menu_trading_action(SCREEN_LOBBY)


def test_geometry_is_not_selected_for_an_undeclared_context():
    with pytest.raises(ValueError, match="Quick Menu policy"):
        open_character_select_action(SCREEN_BATTLE_MODE_SELECT)


def _menu_snapshot(sequence, base=None, *, status=ResolutionStatus.RESOLVED, quick=False, image=None):
    if image is None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
    timestamp = float(sequence)
    return RuntimeSnapshot(
        frame=FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence),
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=status, sequence=sequence, timestamp=timestamp,
            base_context=base,
            overlays=frozenset({MENU_QUICK}) if quick else frozenset(),
            base_candidates=(SCREEN_LOBBY, SCREEN_GUILD)
            if status is ResolutionStatus.AMBIGUOUS else (),
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


def _open_result(source, menu):
    return VerifiedTransitionResult(
        "test.open_menu", VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        1, 0, menu, action_source_snapshot=source,
    )


@pytest.mark.parametrize("origin", [
    SCREEN_LOBBY, SCREEN_GUILD, SCREEN_WORLD_BOSS,
    SCREEN_PETS_MANAGE, SCREEN_PET_SUMMON,
    SCREEN_TREASURE,
])
def test_handoff_allows_fresh_unknown_menu_only_after_verified_origin(origin):
    source = _menu_snapshot(1, origin)
    menu = _menu_snapshot(2, status=ResolutionStatus.UNKNOWN, quick=True)
    handoff = QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: item is source,
    )
    assert handoff is not None
    assert handoff.origin == origin
    assert handoff.action_source_sequence == 1
    assert handoff.menu_sequence == 2
    assert handoff.allows(menu)
    assert handoff.layout is (
        QuickMenuLayout.LOBBY if origin == SCREEN_LOBBY else QuickMenuLayout.SHIFTED
    )


def test_discovered_unknown_or_ambiguous_menu_has_no_handoff():
    source = _menu_snapshot(1, SCREEN_LOBBY)
    unknown = _menu_snapshot(2, status=ResolutionStatus.UNKNOWN, quick=True)
    ambiguous = _menu_snapshot(3, status=ResolutionStatus.AMBIGUOUS, quick=True)
    discovered = VerifiedTransitionResult(
        "test.no_input", VerifiedTransitionOutcome.PRECONDITION_REJECTED,
        0, 0, unknown,
    )
    assert QuickMenuHandoff.from_open_result(
        discovered, lambda item: True,
    ) is None
    assert QuickMenuHandoff.from_open_result(
        _open_result(source, ambiguous), lambda item: True,
    ) is None


def test_foreign_resolved_menu_invalidates_verified_origin():
    source = _menu_snapshot(1, SCREEN_PETS_MANAGE)
    foreign = _menu_snapshot(2, SCREEN_GUILD, quick=True)
    assert QuickMenuHandoff.from_open_result(
        _open_result(source, foreign), lambda item: True,
    ) is None


def test_handoff_invalidates_on_recovery_or_menu_loss_before_retry():
    source = _menu_snapshot(1, SCREEN_LOBBY)
    menu = _menu_snapshot(2, status=ResolutionStatus.UNKNOWN, quick=True)
    handoff = QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: True,
    )
    assert handoff is not None
    assert not handoff.observe(_menu_snapshot(3, status=ResolutionStatus.UNKNOWN))
    assert not handoff.allows(_menu_snapshot(4, status=ResolutionStatus.UNKNOWN, quick=True))
    handoff = QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: True,
    )
    handoff.invalidate()
    assert not handoff.allows(menu)


def test_handoff_aborts_on_ambiguous_or_foreign_menu_during_tile_wait():
    source = _menu_snapshot(1, SCREEN_LOBBY)
    menu = _menu_snapshot(2, status=ResolutionStatus.UNKNOWN, quick=True)
    handoff = QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: True,
    )
    assert handoff is not None
    assert handoff.observe(_menu_snapshot(3, SCREEN_GUILD, quick=True))
    assert not handoff.valid
    handoff = QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: True,
    )
    assert handoff.observe(_menu_snapshot(3, status=ResolutionStatus.AMBIGUOUS, quick=True))
    assert not handoff.valid


@pytest.mark.parametrize(("manifest_name", "menu_path", "origin"), [
    (
        "quick_menu_evidence_manifest.json",
        "screencaps/semantic/workbench/20260825T193046_517947Z-76b5e238/frame-00002478.png",
        SCREEN_LOBBY,
    ),
    (
        "world_boss_quick_menu_evidence_manifest.json",
        "screencaps/semantic/world_boss/quick_menu/20260827T231126_760280Z_01.png",
        SCREEN_WORLD_BOSS,
    ),
    (
        "world_boss_eligibility_return_manifest.json",
        "screencaps/semantic/eligibility/world-boss-return/quick-menu-open/01.png",
        SCREEN_BATTLE_MODE_SELECT,
    ),
    (
        "guild_semantic_manifest.json",
        "screencaps/semantic/guild/quick-menu-from-guild/01.png",
        SCREEN_GUILD,
    ),
])
def test_handoff_overlay_semantics_on_curated_real_frames(
    manifest_name, menu_path, origin,
):
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "datasets" / manifest_name).read_text())
    entry = next(item for item in manifest["entries"] if item["path"] == menu_path)
    assert entry["review_status"] == "confirmed"
    path = root / menu_path
    if not path.exists():
        pytest.skip("curated local screencaps unavailable")
    image = cv2.imread(str(path))
    assert image is not None and np.count_nonzero(image) > 0
    source = _menu_snapshot(1, origin)
    status = (
        ResolutionStatus.UNKNOWN if entry["base_context"] == "unknown"
        else ResolutionStatus.RESOLVED
    )
    menu = _menu_snapshot(
        2, origin if status is ResolutionStatus.RESOLVED else None,
        status=status, quick=entry["overlays"] == [MENU_QUICK], image=image,
    )
    policy = (
        QuickMenuPolicy(frozenset({SCREEN_BATTLE_MODE_SELECT}))
        if origin == SCREEN_BATTLE_MODE_SELECT else DEFAULT_QUICK_MENU_POLICY
    )
    handoff = QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: item is source, policy=policy,
    )
    assert handoff is not None and handoff.allows(menu)
    assert menu.geometry.width == image.shape[1]
    assert menu.geometry.height == image.shape[0]


def test_handoff_rejects_source_layout_mismatch_and_nonfresh_sequence():
    with pytest.raises(ValueError, match="layout_origin_mismatch"):
        QuickMenuHandoff(SCREEN_LOBBY, 1, 2, QuickMenuLayout.SHIFTED)
    with pytest.raises(ValueError, match="sequence_not_fresh"):
        QuickMenuHandoff(SCREEN_GUILD, 2, 2, QuickMenuLayout.SHIFTED)


def test_handoff_requires_operation_source_guard_even_with_visible_menu():
    source = _menu_snapshot(1, SCREEN_GUILD)
    menu = _menu_snapshot(2, SCREEN_GUILD, quick=True)
    assert QuickMenuHandoff.from_open_result(
        _open_result(source, menu), lambda item: False,
    ) is None


def test_menu_opened_only_after_post_input_recovery_has_no_handoff():
    source = _menu_snapshot(1, SCREEN_LOBBY)
    menu = _menu_snapshot(2, status=ResolutionStatus.UNKNOWN, quick=True)
    result = VerifiedTransitionResult(
        "test.open", VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY,
        1, 1, menu, action_source_snapshot=source,
        recovery_after_action=True,
    )
    assert result.succeeded
    assert QuickMenuHandoff.from_open_result(
        result, lambda item: item is source,
    ) is None
