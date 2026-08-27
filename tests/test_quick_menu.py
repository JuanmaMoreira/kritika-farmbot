from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.quick_menu import (
    DEFAULT_QUICK_MENU_POLICY,
    QuickMenuPolicy,
    quick_menu_accessible,
)


def test_declared_context_has_quick_menu_capability():
    assert quick_menu_accessible(SCREEN_LOBBY)


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
