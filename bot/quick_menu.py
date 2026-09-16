"""Conservative policy for semantic contexts that can open Quick Menu."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from bot.catalog import (
    MENU_QUICK,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
)
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.observations import validate_semantic_name
from bot.runtime_observer import RuntimeSnapshot
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionResult
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


@dataclass
class QuickMenuHandoff:
    """One local open-menu-to-tile lineage; never a discovered overlay token."""

    origin: str
    action_source_sequence: int
    menu_sequence: int
    layout: QuickMenuLayout
    valid: bool = True

    def __post_init__(self) -> None:
        expected_layout = (
            QuickMenuLayout.LOBBY
            if self.origin == SCREEN_LOBBY else QuickMenuLayout.SHIFTED
        )
        if self.layout is not expected_layout:
            raise ValueError("quick_menu_layout_origin_mismatch")
        if self.menu_sequence <= self.action_source_sequence:
            raise ValueError("quick_menu_sequence_not_fresh")

    @classmethod
    def from_open_result(
        cls,
        result: VerifiedTransitionResult,
        source_guard: Callable[[RuntimeSnapshot], bool],
        *,
        policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
    ) -> QuickMenuHandoff | None:
        source = result.action_source_snapshot
        menu = result.final_snapshot
        if (
            not result.succeeded
            or result.recovery_after_action
            or source is None
            or source.state.status is not ResolutionStatus.RESOLVED
            or not policy.allows(source.state.base_context)
            or not source_guard(source)
            or menu.sequence <= source.sequence
            or not quick_menu_matches_origin(menu, source.state.base_context)
        ):
            return None
        return cls(
            source.state.base_context, source.sequence, menu.sequence,
            _layout_for(source.state.base_context, policy),
        )

    def allows(self, snapshot: RuntimeSnapshot) -> bool:
        return (
            self.valid
            and snapshot.sequence >= self.menu_sequence
            and quick_menu_matches_origin(snapshot, self.origin)
        )

    def invalidate(self) -> None:
        self.valid = False

    def observe(
        self, snapshot: RuntimeSnapshot,
        destination: Callable[[RuntimeSnapshot], bool] | None = None,
    ) -> bool:
        """Invalidate on menu loss/contradiction; allow passive destination wait."""
        if destination is not None and destination(snapshot):
            self.invalidate()
            return False
        if not self.allows(snapshot):
            self.invalidate()
            state = snapshot.state
            return (
                state.status is ResolutionStatus.AMBIGUOUS
                or (
                    state.status is ResolutionStatus.RESOLVED
                    and state.base_context != self.origin
                )
                or bool(set(state.overlays) - {MENU_QUICK})
            )
        return False


def quick_menu_matches_origin(snapshot: RuntimeSnapshot, origin: str) -> bool:
    state = snapshot.state
    return (
        set(state.overlays) == {MENU_QUICK}
        and (
            state.status is ResolutionStatus.UNKNOWN
            or (
                state.status is ResolutionStatus.RESOLVED
                and state.base_context == origin
            )
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
    "QuickMenuHandoff",
    "quick_menu_matches_origin",
    "open_character_select_action",
    "quick_menu_accessible",
    "select_quick_menu_guild_action",
)
