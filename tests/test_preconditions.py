from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY
from bot.component_contracts import (
    ComponentRequirement,
    QUICK_MENU_ACCESS_REQUIREMENT,
)
from bot.preconditions import EnsureOutcome, MinimalPreconditionEnsurer
from bot.quick_menu import QuickMenuPolicy


def test_no_navigation_when_exact_requirement_is_already_satisfied():
    calls = []
    ensurer = MinimalPreconditionEnsurer(
        lambda: SCREEN_LOBBY,
        navigate_to_lobby=lambda: calls.append(True) or True,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_LOBBY))

    assert result.outcome is EnsureOutcome.ALREADY_SATISFIED
    assert calls == []


def test_capability_requirement_does_not_force_lobby_normalization():
    calls = []
    policy = QuickMenuPolicy(
        frozenset({SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT})
    )
    ensurer = MinimalPreconditionEnsurer(
        lambda: SCREEN_BATTLE_MODE_SELECT,
        navigate_to_lobby=lambda: calls.append(True) or True,
        quick_menu_policy=policy,
    )

    result = ensurer.ensure(QUICK_MENU_ACCESS_REQUIREMENT)

    assert result.outcome is EnsureOutcome.ALREADY_SATISFIED
    assert calls == []


def test_exact_lobby_uses_injected_quick_menu_normalization_and_verifies_result():
    contexts = iter((SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY))
    calls = []
    policy = QuickMenuPolicy(
        frozenset({SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT})
    )
    ensurer = MinimalPreconditionEnsurer(
        lambda: next(contexts),
        navigate_to_lobby=lambda: calls.append(True) or True,
        quick_menu_policy=policy,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_LOBBY))

    assert result.outcome is EnsureOutcome.NORMALIZED
    assert result.context_before == SCREEN_BATTLE_MODE_SELECT
    assert result.context_after == SCREEN_LOBBY
    assert calls == [True]


def test_incapable_context_is_rejected_without_navigation():
    calls = []
    ensurer = MinimalPreconditionEnsurer(
        lambda: SCREEN_BATTLE_MODE_SELECT,
        navigate_to_lobby=lambda: calls.append(True) or True,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_LOBBY))

    assert result.outcome is EnsureOutcome.FAILED
    assert result.error == "requirement_not_satisfied"
    assert calls == []
