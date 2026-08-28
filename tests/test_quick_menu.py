import pytest

from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, SCREEN_WORLD_BOSS
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.quick_menu import (
    DEFAULT_QUICK_MENU_POLICY,
    QuickMenuPolicy,
    open_character_select_action,
    quick_menu_accessible,
)
from bot.semantic_actions import OpenCharacterSelect, QuickMenuLayout


def test_declared_context_has_quick_menu_capability():
    assert quick_menu_accessible(SCREEN_LOBBY)
    assert quick_menu_accessible(SCREEN_WORLD_BOSS)


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


def test_geometry_is_not_selected_for_an_undeclared_context():
    with pytest.raises(ValueError, match="Quick Menu policy"):
        open_character_select_action(SCREEN_BATTLE_MODE_SELECT)
