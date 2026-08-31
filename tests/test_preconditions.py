from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_WORLD_BOSS,
)
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


def test_no_navigation_when_guild_requirement_is_already_satisfied():
    calls = []
    ensurer = MinimalPreconditionEnsurer(
        lambda: SCREEN_GUILD,
        navigate_lobby_to_guild=lambda: calls.append("direct") or True,
        navigate_to_guild=lambda: calls.append("quick_menu") or True,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_GUILD))

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


def test_exact_guild_from_lobby_prioritizes_direct_verified_navigation():
    contexts = iter((SCREEN_LOBBY, SCREEN_GUILD))
    calls = []
    ensurer = MinimalPreconditionEnsurer(
        lambda: next(contexts),
        navigate_lobby_to_guild=lambda: calls.append("direct") or True,
        navigate_to_guild=lambda: calls.append("quick_menu") or True,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_GUILD))

    assert result.outcome is EnsureOutcome.NORMALIZED
    assert result.context_before == SCREEN_LOBBY
    assert result.context_after == SCREEN_GUILD
    assert calls == ["direct"]


def test_exact_guild_from_world_boss_uses_quick_menu_fallback():
    contexts = iter((SCREEN_WORLD_BOSS, SCREEN_GUILD))
    calls = []
    ensurer = MinimalPreconditionEnsurer(
        lambda: next(contexts),
        navigate_lobby_to_guild=lambda: calls.append("direct") or True,
        navigate_to_guild=lambda: calls.append("quick_menu") or True,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_GUILD))

    assert result.outcome is EnsureOutcome.NORMALIZED
    assert result.context_before == SCREEN_WORLD_BOSS
    assert result.context_after == SCREEN_GUILD
    assert calls == ["quick_menu"]


def test_guild_navigation_failure_is_not_accepted_without_postcondition():
    contexts = iter((SCREEN_LOBBY, SCREEN_LOBBY))
    calls = []
    ensurer = MinimalPreconditionEnsurer(
        lambda: next(contexts),
        navigate_lobby_to_guild=lambda: calls.append("direct") or True,
        navigate_to_guild=lambda: calls.append("quick_menu") or True,
    )

    result = ensurer.ensure(ComponentRequirement.exact_state(SCREEN_GUILD))

    assert result.outcome is EnsureOutcome.FAILED
    assert result.error == "direct_guild_postcondition_failed"
    assert calls == ["direct"]


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
