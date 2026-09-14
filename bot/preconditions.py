"""Minimal requirement checking and normalization for component composition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from bot.catalog import SCREEN_GUILD, SCREEN_LOBBY, SCREEN_PETS_MANAGE
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
    """Normalize exact Lobby or Guild using only acquired transitions.

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
        navigate_to_pets_manage: Callable[[], bool] | None = None,
        navigate_lobby_to_guild: Callable[[], bool] | None = None,
        navigate_to_guild: Callable[[], bool] | None = None,
        quick_menu_policy: QuickMenuPolicy = DEFAULT_QUICK_MENU_POLICY,
    ) -> None:
        if not callable(current_context):
            raise ValueError("current_context must be callable")
        if navigate_to_lobby is not None and not callable(navigate_to_lobby):
            raise ValueError("navigate_to_lobby must be callable or None")
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

        if requirement.kind is RequirementKind.EXACT_STATE:
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
                    before == SCREEN_LOBBY
                    or self.quick_menu_policy.allows(before)
                )
            ):
                return self._navigate_and_verify(
                    requirement,
                    before,
                    self.navigate_to_pets_manage,
                    "pets_manage",
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
        except Exception as error:
            return self._failed(
                requirement,
                before,
                None,
                f"{navigation}_navigation_failed: "
                f"{type(error).__name__}: {error}",
            )
        after, after_snapshot = self._current_entry()
        if navigated and self._satisfies(after, requirement):
            return EnsureResult(
                EnsureOutcome.NORMALIZED,
                requirement,
                before,
                after,
                snapshot=after_snapshot,
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
