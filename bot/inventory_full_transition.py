"""Verified acknowledgement of Black Market inventory-cap popups."""

from __future__ import annotations

from bot.catalog import POPUP_INVENTORY_FULL, SCREEN_BLACK_MARKET
from bot.runtime_observer import RuntimeSnapshot
from bot.semantic_actions import AcknowledgeInventoryFull
from bot.state import ResolutionStatus
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionPolicy,
    VerifiedTransitionResult,
)


def acknowledge_inventory_full(
    transition: VerifiedTransition,
    before: RuntimeSnapshot,
    *,
    policy: VerifiedTransitionPolicy,
    stable_for: float = 0.0,
) -> VerifiedTransitionResult:
    """Tap OK and require a fresh clean Black Market postcondition."""

    return transition.execute(
        "black_market.acknowledge_inventory_full",
        AcknowledgeInventoryFull(),
        before,
        expected=is_clean_black_market,
        precondition=is_inventory_full_popup,
        retryable_from=is_inventory_full_popup,
        abort_if=_has_unexpected_ack_state,
        stable_for=stable_for,
        policy=policy,
    )


def is_inventory_full_popup(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_BLACK_MARKET
        and set(state.overlays) == {POPUP_INVENTORY_FULL}
    )


def is_clean_black_market(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_BLACK_MARKET
        and not state.overlays
    )


def _has_unexpected_ack_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_BLACK_MARKET
        )
        or bool(set(state.overlays) - {POPUP_INVENTORY_FULL})
    )


__all__ = (
    "acknowledge_inventory_full",
    "is_clean_black_market",
    "is_inventory_full_popup",
)
