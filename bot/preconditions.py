"""Minimal requirement checking and normalization for component composition."""

from __future__ import annotations

from dataclasses import dataclass
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeWaitCancelled
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from bot.catalog import SCREEN_GUILD, SCREEN_LOBBY, SCREEN_PETS_MANAGE, SCREEN_BATTLE_MODE_SELECT
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.component_contracts import (
    ComponentRequirement,
    QUICK_MENU_ACCESSIBLE,
    RequirementKind,
)
from bot.quick_menu import DEFAULT_QUICK_MENU_POLICY, QuickMenuPolicy


class EnsureOutcome(str, Enum):
    ALREADY_SATISFIED = "already_satisfied"
    NORMALIZED = "normalized"
    FAILED = "failed"


@dataclass(frozen=True)
class EnsureResult:
    outcome: EnsureOutcome
    requirement: ComponentRequirement
    context_before: str | None
    context_after: str | None
    error: str | None = None
    snapshot: Any = None
    route: str | None = None
    failure: FailureCause | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome is not EnsureOutcome.FAILED


@runtime_checkable
class PreconditionEnsurer(Protocol):
    def ensure(self, requirement: ComponentRequirement) -> EnsureResult: ...

    def current_satisfies_any(
        self, requirements: tuple[ComponentRequirement, ...]
    ) -> bool: ...


class MinimalPreconditionEnsurer:
    """Ensure existing surface contracts with explicit acquired routes.

    The navigation callbacks are interaction boundaries. A production
    adapter must implement observed, verified transitions; the runner never
    receives actions, coordinates, or ADB.

    ``current_context`` may return a plain context name (legacy: no
    reusable evidence) or a ``(context, snapshot)`` pair produced by a
    single observation. On success the returned snapshot is attached to
    :class:`EnsureResult`: for ``ALREADY_SATISFIED`` the entry observation
    itself, after navigation the final re-probe that verified the
    destination. It is the only evidence the runner may offer back as a
    flow's initial snapshot, and only while no input occurred since.
    """

    def __init__(
        self,
        current_context: Callable[[], str | None | tuple[str | None, Any]],
        *,
        navigate_to_lobby: Callable[[], bool] | None = None,
        navigate_to_battle_mode: Callable[[], bool] | None = None,
        navigate_to_pets_manage: Callable[[], bool] | None = None,
        navigate_lobby_to_guild: Callable[[], bool] | None = None,
        navigate_to_guild: Callable[[], bool] | None = None,
        quick_menu_policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
    ) -> None:
        if not callable(current_context):
            raise ValueError("current_context must be callable")
        if navigate_to_lobby is not None and not callable(navigate_to_lobby):
            raise ValueError("navigate_to_lobby must be callable or None")
        if navigate_to_battle_mode is not None and not callable(navigate_to_battle_mode):
            raise ValueError("navigate_to_battle_mode must be callable or None")
        if navigate_to_pets_manage is not None and not callable(
            navigate_to_pets_manage
        ):
            raise ValueError("navigate_to_pets_manage must be callable or None")
        if navigate_lobby_to_guild is not None and not callable(
            navigate_lobby_to_guild
        ):
            raise ValueError("navigate_lobby_to_guild must be callable or None")
        if navigate_to_guild is not None and not callable(navigate_to_guild):
            raise ValueError("navigate_to_guild must be callable or None")
        if not isinstance(quick_menu_policy, QuickMenuPolicy):
            raise ValueError("quick_menu_policy must be QuickMenuPolicy")
        self.current_context = current_context
        self.last_context = None
        self.navigate_to_battle_mode = navigate_to_battle_mode
        self.navigate_to_lobby = navigate_to_lobby
        self.navigate_to_pets_manage = navigate_to_pets_manage
        self.navigate_lobby_to_guild = navigate_lobby_to_guild
        self.navigate_to_guild = navigate_to_guild
        self.quick_menu_policy = quick_menu_policy

    def ensure(self, requirement: ComponentRequirement) -> EnsureResult:
        if not isinstance(requirement, ComponentRequirement):
            raise ValueError("requirement must be ComponentRequirement")
        before, before_snapshot = self._current_entry()
        if self._satisfies(before, requirement):
            return EnsureResult(
                EnsureOutcome.ALREADY_SATISFIED,
                requirement,
                before,
                before,
                snapshot=before_snapshot,
            )

        if before == 'screen.meteorites' and requirement.name in {
                SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT, SCREEN_GUILD, SCREEN_PETS_MANAGE, QUICK_MENU_ACCESSIBLE}:
            lobby = self._navigate_and_verify(ComponentRequirement.exact_state(SCREEN_LOBBY),
                before, self.navigate_to_lobby, 'exit_meteorites')
            if not lobby.succeeded:
                return self._failed(requirement, before, lobby.context_after, lobby.error)
            if requirement.name == SCREEN_LOBBY:
                return lobby
            reached = self.ensure(requirement)
            from dataclasses import replace
            return replace(reached, context_before=before, route='exit_meteorites_then_' + (reached.route or reached.outcome.value))

        if requirement.kind is RequirementKind.EXACT_STATE:
            if requirement.name == SCREEN_BATTLE_MODE_SELECT and (
                before in {SCREEN_LOBBY, SCREEN_MONSTER_WAVE}
                or self.quick_menu_policy.allows(before)
            ):
                return self._navigate_and_verify(
                    requirement, before, self.navigate_to_battle_mode,
                    'back_battle_mode' if before == SCREEN_MONSTER_WAVE else
                    'enter_battle_mode' if before == SCREEN_LOBBY else 'quick_menu_lobby_then_battle_mode',
                )
            if requirement.name == SCREEN_LOBBY and before == SCREEN_BATTLE_MODE_SELECT:
                return self._navigate_and_verify(
                    requirement, before, self.navigate_to_lobby, 'back_lobby',
                )
            if (
                requirement.name == SCREEN_LOBBY
                and self.quick_menu_policy.allows(before)
            ):
                return self._navigate_and_verify(
                    requirement,
                    before,
                    self.navigate_to_lobby,
                    "quick_menu_lobby",
                )
            if requirement.name == SCREEN_GUILD and before == SCREEN_LOBBY:
                return self._navigate_and_verify(
                    requirement,
                    before,
                    self.navigate_lobby_to_guild,
                    "direct_guild",
                )
            if (
                requirement.name == SCREEN_PETS_MANAGE
                and (
                    self.quick_menu_policy.allows(before)
                )
            ):
                return self._navigate_and_verify(
                    requirement,
                    before,
                    self.navigate_to_pets_manage,
                    "direct_pets" if before == SCREEN_LOBBY else
                    "quick_menu_pets",
                )
            if (
                requirement.name == SCREEN_GUILD
                and self.quick_menu_policy.allows(before)
            ):
                return self._navigate_and_verify(
                    requirement,
                    before,
                    self.navigate_to_guild,
                    "quick_menu_guild",
                )

        return self._failed(
            requirement,
            before,
            before,
            "requirement_not_satisfied",
        )

    def current_satisfies_any(
        self, requirements: tuple[ComponentRequirement, ...]
    ) -> bool:
        values = tuple(requirements)
        if not values or any(
            not isinstance(item, ComponentRequirement) for item in values
        ):
            raise ValueError("requirements must contain ComponentRequirement values")
        context = self._current_context()
        self.last_context = context
        return any(self._satisfies(context, requirement) for requirement in values)

    def _current_context(self) -> str | None:
        context, _ = self._current_entry()
        return context

    def _current_entry(self) -> tuple[str | None, Any]:
        """Read one entry observation as a context/snapshot pair.

        A single adapter invocation backs both values, so a returned
        snapshot is always the evidence its context was derived from.
        Plain string returns keep legacy adapters working with no
        reusable evidence.
        """

        try:
            value = self.current_context()
        except (KeyboardInterrupt, SystemExit):
            raise
        except RuntimeWaitCancelled:
            raise
        except Exception:
            return None, None
        if isinstance(value, tuple):
            context, snapshot = value
            if context is not None and not isinstance(context, str):
                return None, None
            return (context if isinstance(context, str) and context else None), snapshot
        return (value if isinstance(value, str) and value else None), None

    def _satisfies(
        self,
        context: str | None,
        requirement: ComponentRequirement,
    ) -> bool:
        if requirement.kind is RequirementKind.EXACT_STATE:
            return context == requirement.name
        if requirement.name == QUICK_MENU_ACCESSIBLE:
            return self.quick_menu_policy.allows(context)
        return False

    def _navigate_and_verify(
        self,
        requirement: ComponentRequirement,
        before: str | None,
        callback: Callable[[], bool] | None,
        navigation: str,
    ) -> EnsureResult:
        if callback is None:
            return self._failed(
                requirement,
                before,
                before,
                f"{navigation}_navigation_unavailable",
            )
        try:
            navigated = callback() is True
        except (KeyboardInterrupt, SystemExit):
            raise
        except RuntimeWaitCancelled:
            raise
        except Exception as error:
            return EnsureResult(EnsureOutcome.FAILED, requirement, before, None,
                f"{navigation}_navigation_failed: {type(error).__name__}: {error}",
                route=navigation, failure=getattr(error, 'failure', None))
        after, after_snapshot = self._current_entry()
        if navigated and self._satisfies(after, requirement):
            return EnsureResult(
                EnsureOutcome.NORMALIZED,
                requirement,
                before,
                after,
                snapshot=after_snapshot,
                route=navigation,
            )
        return self._failed(
            requirement,
            before,
            after,
            f"{navigation}_postcondition_failed",
        )

    @staticmethod
    def _failed(
        requirement: ComponentRequirement,
        before: str | None,
        after: str | None,
        error: str,
    ) -> EnsureResult:
        return EnsureResult(
            EnsureOutcome.FAILED,
            requirement,
            before,
            after,
            error,
        )


__all__ = (
    "EnsureOutcome",
    "EnsureResult",
    "MinimalPreconditionEnsurer",
    "PreconditionEnsurer",
)
