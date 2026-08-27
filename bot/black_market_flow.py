"""Single-character Black Market vertical slice over semantic runtime APIs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.catalog import (
    POPUP_INSUFFICIENT_GOLD,
    POPUP_INVENTORY_FULL,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BLACK_MARKET,
    SCREEN_LOBBY,
)
from bot.event_log import EventSink
from bot.inventory_full_transition import acknowledge_inventory_full
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    CloseBlackMarket,
    OpenBlackMarket,
    RejectInsufficientGold,
    SelectBlackMarketSlot,
)
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


class FlowOutcome(str, Enum):
    SUCCESS = "success"
    NOOP = "noop"
    ABORTED = "aborted"


@dataclass(frozen=True)
class FlowResult:
    """Reusable minimal outcome for a future SessionRunner."""

    outcome: FlowOutcome
    initial_gold_slots: tuple[int, ...] = ()
    initial_purchased_slots: tuple[int, ...] = ()
    attempted_slots: tuple[int, ...] = ()
    verified_purchases: tuple[int, ...] = ()
    insufficient_gold_count: int = 0
    inventory_full_count: int = 0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome in (FlowOutcome.SUCCESS, FlowOutcome.NOOP)


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class BlackMarketFlow:
    """Process GOLD offers for the active character only, starting at Lobby."""

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink,
        *,
        timeout: float = 5.0,
        transition_grace_timeout: float = 2.0,
        transition_max_attempts: int = 2,
        verified_transition: VerifiedTransition | None = None,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute(intent, geometry)")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record(event)")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.timeout = float(timeout)
        self.inventory_full_policy = VerifiedTransitionPolicy(
            normal_timeout=self.timeout,
            grace_timeout=transition_grace_timeout,
            max_attempts=transition_max_attempts,
        )
        if verified_transition is None:
            verified_transition = VerifiedTransition(observer, actions)
        if not callable(getattr(verified_transition, "execute", None)):
            raise ValueError("verified_transition must provide execute()")
        self.verified_transition = verified_transition

    def run(self, *, max_slot_attempts: int | None = None) -> FlowResult:
        """Run the flow, optionally bounded by an explicit debug attempt limit.

        A limit of zero performs the validated Lobby -> Black Market entry and
        initial fact read without selecting an offer. Normal production policy
        remains the unbounded ``None`` case.
        """

        limit = _attempt_limit(max_slot_attempts)
        try:
            return self._run(limit)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            self._record_best_effort("black_market.unexpected_state")
            return FlowResult(
                outcome=FlowOutcome.ABORTED,
                error=f"{type(error).__name__}: {error}",
            )

    def _run(self, limit: int | None) -> FlowResult:
        initial = self.observer.observe()
        if not _is_clean_base(initial, SCREEN_LOBBY):
            return self._abort("precondition_lobby_failed")

        self.actions.execute(OpenBlackMarket(), initial.geometry)
        try:
            market = self.observer.wait_until(
                lambda snapshot: _is_clean_base(snapshot, SCREEN_BLACK_MARKET),
                after_sequence=initial.sequence,
                timeout=self.timeout,
                abort_if=_has_incompatible_state,
                stable_for=0.75,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._abort(f"navigation_failed: {error}")

        initial_gold = tuple(sorted(market.facts.gold_slots))
        initial_purchased = tuple(sorted(market.facts.purchased_slots))
        if not initial_gold:
            self.events.record("black_market.no_gold")
            return self._finish(
                market,
                FlowOutcome.NOOP,
                initial_gold=(),
                initial_purchased=initial_purchased,
            )

        selected = initial_gold if limit is None else initial_gold[:limit]
        attempted: list[int] = []
        verified: list[int] = []
        insufficient = 0
        inventory_full = 0

        for slot in selected:
            current = self.observer.observe()
            if not _is_clean_base(current, SCREEN_BLACK_MARKET):
                return self._abort(
                    "unexpected_state_before_slot",
                    initial_gold,
                    attempted,
                    verified,
                    insufficient,
                    inventory_full,
                )

            attempted.append(slot)
            self.actions.execute(
                SelectBlackMarketSlot(slot), current.geometry
            )
            try:
                branch = self.observer.wait_until(
                    _is_expected_purchase_branch,
                    after_sequence=current.sequence,
                    timeout=self.timeout,
                    abort_if=_has_incompatible_branch,
                )
            except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
                return self._abort(
                    f"unexpected_purchase_branch: {error}",
                    initial_gold,
                    attempted,
                    verified,
                    insufficient,
                    inventory_full,
                )

            overlays = set(branch.state.overlays)
            if overlays == {POPUP_PURCHASE_CONFIRMATION}:
                self.actions.execute(
                    AcceptPurchaseConfirmation(), branch.geometry
                )
                try:
                    completed = self.observer.wait_until(
                        lambda snapshot, expected=slot: (
                            _is_clean_base(snapshot, SCREEN_BLACK_MARKET)
                            and expected in snapshot.facts.purchased_slots
                        ),
                        after_sequence=branch.sequence,
                        timeout=self.timeout,
                        abort_if=_has_incompatible_post_purchase,
                    )
                except RuntimeWaitTimeout as error:
                    if (
                        error.last_snapshot is not None
                        and _is_clean_base(
                            error.last_snapshot, SCREEN_BLACK_MARKET
                        )
                        and slot
                        not in error.last_snapshot.facts.purchased_slots
                    ):
                        return self._abort(
                            "purchase_unverified",
                            initial_gold,
                            attempted,
                            verified,
                            insufficient,
                            inventory_full,
                            event="black_market.purchase_unverified",
                        )
                    return self._abort(
                        f"unexpected_state_after_purchase: {error}",
                        initial_gold,
                        attempted,
                        verified,
                        insufficient,
                        inventory_full,
                    )
                except RuntimeWaitAborted as error:
                    return self._abort(
                        f"unexpected_state_after_purchase: {error}",
                        initial_gold,
                        attempted,
                        verified,
                        insufficient,
                        inventory_full,
                    )
                verified.append(slot)
                market = completed
                continue

            if overlays == {POPUP_INSUFFICIENT_GOLD}:
                insufficient += 1
                self.events.record("black_market.low_gold")
                self.actions.execute(RejectInsufficientGold(), branch.geometry)
                try:
                    market = self.observer.wait_until(
                        lambda snapshot: _is_clean_base(
                            snapshot, SCREEN_BLACK_MARKET
                        ),
                        after_sequence=branch.sequence,
                        timeout=self.timeout,
                        abort_if=_has_incompatible_after_reject,
                    )
                except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
                    return self._abort(
                        f"unexpected_state_after_low_gold: {error}",
                        initial_gold,
                        attempted,
                        verified,
                        insufficient,
                        inventory_full,
                    )
                continue

            inventory_full += 1
            self.events.record("black_market.inventory_full")
            acknowledged = acknowledge_inventory_full(
                self.verified_transition,
                branch,
                policy=self.inventory_full_policy,
            )
            if not acknowledged.succeeded:
                return self._abort(
                    "inventory_full_ack_failed: "
                    f"{acknowledged.outcome.value}: {acknowledged.error}",
                    initial_gold,
                    attempted,
                    verified,
                    insufficient,
                    inventory_full,
                )
            market = acknowledged.final_snapshot

        return self._finish(
            market,
            FlowOutcome.SUCCESS,
            initial_gold=initial_gold,
            initial_purchased=initial_purchased,
            attempted=attempted,
            verified=verified,
            insufficient=insufficient,
            inventory_full=inventory_full,
        )

    def _finish(
        self,
        market: RuntimeSnapshot,
        outcome: FlowOutcome,
        *,
        initial_gold: tuple[int, ...],
        initial_purchased: tuple[int, ...],
        attempted: list[int] | tuple[int, ...] = (),
        verified: list[int] | tuple[int, ...] = (),
        insufficient: int = 0,
        inventory_full: int = 0,
    ) -> FlowResult:
        """Close Black Market and require a fresh clean Lobby postcondition."""

        self.actions.execute(CloseBlackMarket(), market.geometry)
        try:
            self.observer.wait_until(
                lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
                after_sequence=market.sequence,
                timeout=self.timeout,
                abort_if=_has_incompatible_state,
            )
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._abort(
                f"return_to_lobby_failed: {error}",
                initial_gold,
                attempted,
                verified,
                insufficient,
                inventory_full,
                initial_purchased=initial_purchased,
            )

        return FlowResult(
            outcome=outcome,
            initial_gold_slots=initial_gold,
            initial_purchased_slots=initial_purchased,
            attempted_slots=tuple(attempted),
            verified_purchases=tuple(verified),
            insufficient_gold_count=insufficient,
            inventory_full_count=inventory_full,
        )

    def _abort(
        self,
        reason: str,
        initial_gold: tuple[int, ...] = (),
        attempted: list[int] | tuple[int, ...] = (),
        verified: list[int] | tuple[int, ...] = (),
        insufficient: int = 0,
        inventory_full: int = 0,
        *,
        initial_purchased: tuple[int, ...] = (),
        event: str = "black_market.unexpected_state",
    ) -> FlowResult:
        self._record_best_effort(event)
        return FlowResult(
            outcome=FlowOutcome.ABORTED,
            initial_gold_slots=tuple(initial_gold),
            initial_purchased_slots=tuple(initial_purchased),
            attempted_slots=tuple(attempted),
            verified_purchases=tuple(verified),
            insufficient_gold_count=insufficient,
            inventory_full_count=inventory_full,
            error=reason,
        )

    def _record_best_effort(self, event: str) -> None:
        try:
            self.events.record(event)
        except Exception:
            # A logging failure must not trigger gameplay recovery or more input.
            pass


def _is_clean_base(snapshot: RuntimeSnapshot, base: str) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == base
        and not state.overlays
    )


def _is_expected_purchase_branch(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_BLACK_MARKET
        and set(state.overlays)
        in (
            {POPUP_PURCHASE_CONFIRMATION},
            {POPUP_INSUFFICIENT_GOLD},
            {POPUP_INVENTORY_FULL},
        )
    )


def _has_incompatible_state(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or bool(snapshot.state.overlays)
    )


def _has_incompatible_branch(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    expected = {
        POPUP_PURCHASE_CONFIRMATION,
        POPUP_INSUFFICIENT_GOLD,
        POPUP_INVENTORY_FULL,
    }
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or bool(overlays - expected)
        or len(overlays & expected) > 1
    )


def _has_incompatible_post_purchase(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or POPUP_INSUFFICIENT_GOLD in overlays
        or POPUP_INVENTORY_FULL in overlays
        or bool(
            overlays
            - {
                POPUP_PURCHASE_CONFIRMATION,
                POPUP_INSUFFICIENT_GOLD,
                POPUP_INVENTORY_FULL,
            }
        )
    )


def _has_incompatible_after_reject(snapshot: RuntimeSnapshot) -> bool:
    overlays = set(snapshot.state.overlays)
    return (
        snapshot.state.status is ResolutionStatus.AMBIGUOUS
        or POPUP_PURCHASE_CONFIRMATION in overlays
        or POPUP_INVENTORY_FULL in overlays
        or bool(
            overlays
            - {
                POPUP_PURCHASE_CONFIRMATION,
                POPUP_INSUFFICIENT_GOLD,
                POPUP_INVENTORY_FULL,
            }
        )
    )


def _attempt_limit(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("max_slot_attempts must be a non-negative integer or None")
    return int(value)


__all__ = ("BlackMarketFlow", "FlowOutcome", "FlowResult")
