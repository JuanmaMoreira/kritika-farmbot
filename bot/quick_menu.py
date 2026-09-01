"""Conservative policy for semantic contexts that can open Quick Menu."""

from __future__ import annotations

from dataclasses import dataclass

from bot.catalog import (
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
)
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.observations import validate_semantic_name
from bot.semantic_actions import (
    OpenCharacterSelect,
    QuickMenuLayout,
    SelectQuickMenuGuild,
)


@dataclass(frozen=True)
class QuickMenuPolicy:
    """Explicit allow-list; capability is policy, never a synthetic screen."""

    accessible_from: frozenset[str]

    def __post_init__(self) -> None:
        contexts = frozenset(
            validate_semantic_name(context) for context in self.accessible_from
        )
        object.__setattr__(self, "accessible_from", contexts)

    def allows(self, semantic_context: str | None) -> bool:
        return semantic_context in self.accessible_from


# These contexts opened the same Quick Menu overlay live using the shared header
# target. Every non-Lobby origin uses the acquired shifted layout.
DEFAULT_QUICK_MENU_POLICY = QuickMenuPolicy(
    frozenset(
        {
            SCREEN_GUILD,
            SCREEN_LOBBY,
            SCREEN_PET_SUMMON,
            SCREEN_PETS_MANAGE,
            SCREEN_WORLD_BOSS,
        }
    )
)


def quick_menu_accessible(
    semantic_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    return policy.allows(semantic_context)


def open_character_select_action(
    origin_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> OpenCharacterSelect:
    """Select the Quick Menu geometry for a capability-approved origin.

    Lobby owns the base layout. Every other explicitly allowed screen uses
    the laterally shifted layout observed outside Lobby.
    """

    return OpenCharacterSelect(_layout_for(origin_context, policy))


def select_quick_menu_guild_action(
    origin_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> SelectQuickMenuGuild:
    """Select Guild using the acquired layout for the approved origin."""

    return SelectQuickMenuGuild(_layout_for(origin_context, policy))


def _layout_for(
    origin_context: str | None,
    policy: QuickMenuPolicy,
) -> QuickMenuLayout:
    if not policy.allows(origin_context):
        raise ValueError(
            "origin_context must be allowed by the Quick Menu policy"
        )
    return (
        QuickMenuLayout.LOBBY
        if origin_context == SCREEN_LOBBY
        else QuickMenuLayout.SHIFTED
    )


__all__ = (
    "DEFAULT_QUICK_MENU_POLICY",
    "QUICK_MENU_ACCESSIBLE",
    "QuickMenuPolicy",
    "open_character_select_action",
    "quick_menu_accessible",
    "select_quick_menu_guild_action",
)
