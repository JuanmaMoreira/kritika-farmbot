"""Conservative policy for semantic contexts that can open Quick Menu."""

from __future__ import annotations

from dataclasses import dataclass

from bot.catalog import SCREEN_LOBBY, SCREEN_WORLD_BOSS
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.observations import validate_semantic_name
from bot.semantic_actions import OpenCharacterSelect, QuickMenuLayout


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


# Both contexts opened and safely closed the same Quick Menu overlay live using
# the shared header target. No other context is inferred from legacy metadata.
DEFAULT_QUICK_MENU_POLICY = QuickMenuPolicy(
    frozenset({SCREEN_LOBBY, SCREEN_WORLD_BOSS})
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

    if not policy.allows(origin_context):
        raise ValueError(
            "origin_context must be allowed by the Quick Menu policy"
        )
    layout = (
        QuickMenuLayout.LOBBY
        if origin_context == SCREEN_LOBBY
        else QuickMenuLayout.SHIFTED
    )
    return OpenCharacterSelect(layout)


__all__ = (
    "DEFAULT_QUICK_MENU_POLICY",
    "QUICK_MENU_ACCESSIBLE",
    "QuickMenuPolicy",
    "open_character_select_action",
    "quick_menu_accessible",
)
