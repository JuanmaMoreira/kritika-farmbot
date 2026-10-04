"""Conservative policy for semantic contexts that can open Quick Menu."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from bot.catalog import (
    MENU_QUICK,
    SCREEN_BATTLE_MODE_SELECT,
    STATUS_WORLD_BOSS_DAILY_ACTIVE, STATUS_MONSTER_WAVE_DAILY_ACTIVE,
    STATUS_GUILD_ATTENDANCE_ACTIVE, STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE, STATUS_PET_SUMMON_DAILY_ACTIVE,
    STATUS_PET_EPIC_AVAILABLE, STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD, STATUS_PET_PREMIUM_TICKET_AVAILABLE,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    SCREEN_PET_SUMMON,
    SCREEN_PETS_MANAGE,
    SCREEN_WORLD_BOSS,
)
from bot.component_contracts import QUICK_MENU_ACCESSIBLE
from bot.observations import validate_semantic_name
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionResult, VerifiedTransitionOutcome
from bot.semantic_actions import (
    OpenCharacterSelect, OpenQuickMenu,
    SelectQuickMenuQuests, SelectQuickMenuMailbox,
    QuickMenuLayout,
    SelectQuickMenuCraft,
    SelectQuickMenuGuild,
    SelectQuickMenuPets,
    SelectQuickMenuTrading,
    SelectQuickMenuTreasure,
)
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.treasure_center_semantics import SCREEN_TREASURE


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


# Acquired evidence and USER_GT credit these contexts (Battle Mode Select:
# USER_GT 2026-10-04). Every non-Lobby origin uses the acquired shifted layout.
DEFAULT_QUICK_MENU_POLICY = QuickMenuPolicy(
    frozenset(
        {
            SCREEN_BATTLE_MODE_SELECT,
            SCREEN_GUILD,
            SCREEN_LOBBY,
            SCREEN_PET_SUMMON,
            SCREEN_PETS_MANAGE,
            SCREEN_TREASURE,
            SCREEN_WORLD_BOSS,
            SCREEN_MONSTER_WAVE,
        }
    )
)


def is_clean_quick_menu_base(
    snapshot: RuntimeSnapshot, policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> bool:
    """Explicitly credited BASE with no modal or active gameplay above it."""
    state = snapshot.state
    if (state.status is not ResolutionStatus.RESOLVED
            or not policy.allows(state.base_context)):
        return False
    overlays = set(state.overlays)
    if state.base_context == SCREEN_BATTLE_MODE_SELECT:
        return overlays <= {STATUS_WORLD_BOSS_DAILY_ACTIVE, STATUS_MONSTER_WAVE_DAILY_ACTIVE}
    if state.base_context == SCREEN_GUILD:
        attendance = {STATUS_GUILD_ATTENDANCE_ACTIVE, STATUS_GUILD_ATTENDANCE_COMPLETED}
        return (len(overlays & attendance) == 1
                and overlays <= attendance | {STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE})
    if state.base_context == SCREEN_PETS_MANAGE:
        return overlays <= {STATUS_PET_SUMMON_DAILY_ACTIVE}
    if state.base_context == SCREEN_PET_SUMMON:
        epic = {STATUS_PET_EPIC_AVAILABLE, STATUS_PET_EPIC_UNAVAILABLE}
        return len(overlays & epic) == 1 and overlays <= epic | {
            STATUS_PET_PREMIUM_GOLD, STATUS_PET_PREMIUM_TICKET_AVAILABLE,
            STATUS_PET_SUMMON_DAILY_ACTIVE,
        }
    return not overlays


def open_quick_menu_destination(initial, transition, policy, *, action,
                                selection, expected, source_guard=None,
                                destination_guard=None, destination_transition=None,
                                stable_for=0.25, cancel_requested=lambda: False,
                                prefix='navigation'):
    """Execute a known QM route through the shared executor and local lineage.

    The destination owner supplies its panel/content guard. Navigation owns
    menu inputs; neither an unknown BASE nor a discovered menu authorizes them.
    """
    if cancel_requested():
        raise RuntimeWaitCancelled('quick_menu_handoff_cancelled')
    origin = initial.state.base_context
    source_guard = source_guard or (
        lambda s: s.state.base_context == origin and is_clean_quick_menu_base(s)
    )
    destination_guard = destination_guard or expected
    if not is_clean_quick_menu_base(initial) or not source_guard(initial):
        raise ValueError('quick_menu_source_unverified')

    def incompatible_open(s):
        if source_guard(s) or quick_menu_matches_origin(s, origin):
            return False
        return (s.state.status in {ResolutionStatus.RESOLVED, ResolutionStatus.AMBIGUOUS}
                or bool(s.state.overlays))
    opened = transition.execute(
        f'{prefix}.open_quick_menu', OpenQuickMenu(), initial,
        expected=lambda s: quick_menu_matches_origin(s, origin),
        precondition=lambda s: not cancel_requested() and source_guard(s),
        retryable_from=lambda s: not cancel_requested() and source_guard(s),
        abort_if=incompatible_open, policy=policy,
    )
    if cancel_requested():
        raise RuntimeWaitCancelled('quick_menu_handoff_cancelled')
    if not opened.succeeded:
        return opened
    handoff = QuickMenuHandoff.from_open_result(opened, source_guard)
    if handoff is None:
        return replace(opened, outcome=VerifiedTransitionOutcome.PRECONDITION_REJECTED,
                       error='quick_menu_origin_handoff_invalid')

    def incompatible_destination(s):
        if destination_guard(s):
            handoff.invalidate()
            return False
        if source_guard(s):
            handoff.invalidate()
            return False  # passive wait is safe; lineage can no longer send inputs
        return handoff.observe(s, destination_guard)
    event_sink = getattr(transition, 'events', None)
    if event_sink is not None:
        try:
            event_sink.record('navigation.handoff', current_surface=origin,
                underlying_base=origin, route='quick_menu', destination=selection,
                reason='rotation' if selection == 'character_select' else 'entry_requirement')
        except Exception:
            pass
    return (destination_transition or transition).execute(
        f'{prefix}.select_{selection}', action, opened.final_snapshot,
        expected=expected,
        precondition=lambda s: not cancel_requested() and handoff.allows(s),
        retryable_from=lambda s: not cancel_requested() and handoff.allows(s),
        on_recovery=handoff.invalidate, abort_if=incompatible_destination,
        stable_for=stable_for, policy=policy,
    )


def select_quick_menu_panel_action(origin, destination):
    if _layout_for(origin, DEFAULT_QUICK_MENU_POLICY) is not QuickMenuLayout.SHIFTED:
        raise ValueError('Lobby uses its existing direct panel shortcuts')
    if destination == 'daily_quests':
        return SelectQuickMenuQuests()
    if destination == 'mailbox':
        return SelectQuickMenuMailbox()
    raise ValueError('unsupported Quick Menu panel')


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


def select_quick_menu_pets_action(origin_context: str) -> SelectQuickMenuPets:
    if _layout_for(origin_context, DEFAULT_QUICK_MENU_POLICY) is not QuickMenuLayout.SHIFTED:
        raise ValueError('pets_quick_menu_requires_shifted_origin')
    return SelectQuickMenuPets()


def select_quick_menu_trading_action(
    origin_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> SelectQuickMenuTrading:
    """Select Trading from a HIL-verified shifted Treasure or MW menu."""

    layout = _layout_for(origin_context, policy)
    if (
        origin_context not in (SCREEN_TREASURE, SCREEN_MONSTER_WAVE)
        or layout is not QuickMenuLayout.SHIFTED
    ):
        raise ValueError(
            "Trading Quick Menu target is verified only from Treasure or Monster Wave"
        )
    return SelectQuickMenuTrading()


def select_quick_menu_craft_action(
    origin_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> SelectQuickMenuCraft:
    """Select Craft only from the HIL-verified shifted MW menu."""

    layout = _layout_for(origin_context, policy)
    if origin_context != SCREEN_MONSTER_WAVE or layout is not QuickMenuLayout.SHIFTED:
        raise ValueError("Craft Quick Menu target is verified only from Monster Wave")
    return SelectQuickMenuCraft()


def select_quick_menu_treasure_action(
    origin_context: str | None,
    *,
    policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
) -> SelectQuickMenuTreasure:
    """Select Treasure only from the HIL-verified shifted MW menu."""

    layout = _layout_for(origin_context, policy)
    if origin_context != SCREEN_MONSTER_WAVE or layout is not QuickMenuLayout.SHIFTED:
        raise ValueError("Treasure Quick Menu target is verified only from Monster Wave")
    return SelectQuickMenuTreasure()


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
    "is_clean_quick_menu_base",
    "open_quick_menu_destination",
    "select_quick_menu_panel_action",
    "QuickMenuPolicy",
    "QuickMenuHandoff",
    "quick_menu_matches_origin",
    "open_character_select_action",
    "quick_menu_accessible",
    "select_quick_menu_craft_action",
    "select_quick_menu_guild_action",
    "select_quick_menu_pets_action",
    "select_quick_menu_trading_action",
    "select_quick_menu_treasure_action",
)
