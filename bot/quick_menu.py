"""Conservative policy for semantic contexts that can open Quick Menu."""

from __future__ import annotations

from dataclasses import dataclass

from bot.catalog import SCREEN_LOBBY
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.observations import validate_semantic_name


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


# Only contexts with productive evidence belong here. World Boss is intentionally
# absent until its semantic acquisition and Quick Menu behavior are validated live.
DEFAULT_QUICK_MENU_POLICY = QuickMenuPolicy(frozenset({SCREEN_LOBBY}))


def quick_menu_accessible(
    semantic_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    return policy.allows(semantic_context)


__all__ = (
    "DEFAULT_QUICK_MENU_POLICY",
    "QUICK_MENU_ACCESSIBLE",
    "QuickMenuPolicy",
    "quick_menu_accessible",
)
