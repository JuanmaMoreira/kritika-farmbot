"""Minimal requirement checking and normalization for component composition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

from bot.catalog import SCREEN_GUILD, SCREEN_LOBBY
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
    """Normalize exact Lobby or Guild requirements through Quick Menu.

    The two navigation callbacks are interaction boundaries. A production
    adapter must implement observed, verified transitions; the runner never
    receives actions, coordinates, or ADB.
    """

    def __init__(
        self,
        current_context: Callable[[], str | None],
        *,
        navigate_to_lobby: Callable[[], bool] | None = None,
        navigate_to_guild: Callable[[], bool] | None = None,
        quick_menu_policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
    ) -> None:
        if not callable(current_context):
            raise ValueError("current_context must be callable")
        if navigate_to_lobby is not None and not callable(navigate_to_lobby):
            raise ValueError("navigate_to_lobby must be callable or None")
        if navigate_to_guild is not None and not callable(navigate_to_guild):
            raise ValueError("navigate_to_guild must be callable or None")
        if not isinstance(quick_menu_policy, QuickMenuPolicy):
            raise ValueError("quick_menu_policy must be QuickMenuPolicy")
        self.current_context = current_context
        self.navigate_to_lobby = navigate_to_lobby
        self.navigate_to_guild = navigate_to_guild
        self.quick_menu_policy = quick_menu_policy

    def ensure(self, requirement: ComponentRequirement) -> EnsureResult:
        if not isinstance(requirement, ComponentRequirement):
            raise ValueError("requirement must be ComponentRequirement")
        before = self._current_context()
        if self._satisfies(before, requirement):
            return EnsureResult(
                EnsureOutcome.ALREADY_SATISFIED,
                requirement,
                before,
                before,
            )

        if requirement.kind is RequirementKind.EXACT_STATE:
            navigation = {
                SCREEN_LOBBY: (self.navigate_to_lobby, "lobby"),
                SCREEN_GUILD: (self.navigate_to_guild, "guild"),
            }.get(requirement.name)
            if navigation is not None and self.quick_menu_policy.allows(before):
                callback, destination = navigation
                return self._navigate_and_verify(
                    requirement,
                    before,
                    callback,
                    destination,
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
        return any(self._satisfies(context, requirement) for requirement in values)

    def _current_context(self) -> str | None:
        try:
            value = self.current_context()
            return value if isinstance(value, str) and value else None
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            return None

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
        destination: str,
    ) -> EnsureResult:
        if callback is None:
            return self._failed(
                requirement,
                before,
                before,
                f"quick_menu_{destination}_navigation_unavailable",
            )
        try:
            navigated = callback() is True
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(
                requirement,
                before,
                None,
                f"quick_menu_{destination}_navigation_failed: "
                f"{type(error).__name__}: {error}",
            )
        after = self._current_context()
        if navigated and self._satisfies(after, requirement):
            return EnsureResult(
                EnsureOutcome.NORMALIZED,
                requirement,
                before,
                after,
            )
        return self._failed(
            requirement,
            before,
            after,
            f"quick_menu_{destination}_postcondition_failed",
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
