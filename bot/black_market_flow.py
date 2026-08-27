"""Single-character Black Market vertical slice over semantic runtime APIs."""

from __future__ import annotations

from dataclasses import dataclass
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
from bot.flow_contracts import FlowEvent, FlowResult, FlowScope, FlowStatus
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


@dataclass(frozen=True)
class BlackMarketFlowResult(FlowResult):
    """FlowResult enriched with useful Black Market diagnostic evidence."""

    initial_gold_slots: tuple[int, ...] = ()
    initial_purchased_slots: tuple[int, ...] = ()
    attempted_slots: tuple[int, ...] = ()
    verified_purchases: tuple[int, ...] = ()

    @property
    def insufficient_gold_count(self) -> int:
        return self.event_count("low_gold")

    @property
    def inventory_full_count(self) -> int:
        return self.event_count("inventory_full")


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

    name = "black_market"
    scope = FlowScope.PER_CHARACTER

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink,
        *,
        timeout: float = 5.0,
        lobby_precondition_settle_for: float = 0.25,
        post_branch_settle_for: float = 0.5,
        empty_gold_confirmation_timeout: float = 2.0,
        slot_selection_timeout: float = 1.0,
        slot_selection_grace_timeout: float = 2.0,
        transition_retry_guard_timeout: float = 1.0,
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
        if lobby_precondition_settle_for < 0:
            raise ValueError("lobby_precondition_settle_for must be non-negative")
        if post_branch_settle_for < 0:
            raise ValueError("post_branch_settle_for must be non-negative")
        if empty_gold_confirmation_timeout <= 0:
            raise ValueError("empty_gold_confirmation_timeout must be positive")
        if slot_selection_timeout <= 0:
            raise ValueError("slot_selection_timeout must be positive")
        if slot_selection_grace_timeout <= 0:
            raise ValueError("slot_selection_grace_timeout must be positive")
        if transition_retry_guard_timeout <= 0:
            raise ValueError("transition_retry_guard_timeout must be positive")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.timeout = float(timeout)
        self.lobby_precondition_settle_for = float(
            lobby_precondition_settle_for
        )
        self.post_branch_settle_for = float(post_branch_settle_for)
        self.empty_gold_confirmation_timeout = float(
            empty_gold_confirmation_timeout
        )
        self.navigation_policy = VerifiedTransitionPolicy(
            normal_timeout=self.timeout,
            grace_timeout=transition_grace_timeout,
            retry_guard_timeout=transition_retry_guard_timeout,
            max_attempts=transition_max_attempts,
        )
        self.inventory_full_policy = VerifiedTransitionPolicy(
            normal_timeout=self.timeout,
            grace_timeout=transition_grace_timeout,
            max_attempts=transition_max_attempts,
        )
        self.slot_selection_policy = VerifiedTransitionPolicy(
            normal_timeout=slot_selection_timeout,
            grace_timeout=slot_selection_grace_timeout,
            retry_guard_timeout=transition_retry_guard_timeout,
            max_attempts=transition_max_attempts,
        )
        if verified_transition is None:
            verified_transition = VerifiedTransition(observer, actions)
        if not callable(getattr(verified_transition, "execute", None)):
            raise ValueError("verified_transition must provide execute()")
        self.verified_transition = verified_transition

    def run(self, *, max_slot_attempts: int | None = None) -> BlackMarketFlowResult:
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
            return BlackMarketFlowResult(
                status=FlowStatus.FAILED,
                error=f"{type(error).__name__}: {error}",
            )

    def _run(self, limit: int | None) -> BlackMarketFlowResult:
        initial = self.observer.observe()
        if not _is_clean_base(initial, SCREEN_LOBBY):
            if not _can_wait_for_lobby_precondition(initial):
                return self._abort("precondition_lobby_failed")
            try:
                initial = self.observer.wait_until(
                    lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
                    after_sequence=initial.sequence,
                    timeout=self.timeout,
                    abort_if=_has_incompatible_lobby_precondition,
                    stable_for=self.lobby_precondition_settle_for,
                )
            except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
                return self._abort(f"precondition_lobby_failed: {error}")

        opened = self.verified_transition.execute(
            "black_market.open",
            OpenBlackMarket(),
            initial,
            expected=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_BLACK_MARKET
            ),
            precondition=lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
            retryable_from=lambda snapshot: _is_clean_base(
                snapshot, SCREEN_LOBBY
            ),
            abort_if=_has_incompatible_state,
            stable_for=0.75,
            policy=self.navigation_policy,
        )
        if not opened.succeeded:
            return self._abort(
                "navigation_failed: "
                f"{opened.outcome.value}: {opened.error}"
            )
        market = opened.final_snapshot

        if not market.facts.gold_slots:
            try:
                market = self.observer.wait_until(
                    lambda snapshot: (
                        _is_clean_base(snapshot, SCREEN_BLACK_MARKET)
                        and bool(snapshot.facts.gold_slots)
                    ),
                    after_sequence=market.sequence,
                    timeout=self.empty_gold_confirmation_timeout,
                    abort_if=_has_incompatible_state,
                )
            except RuntimeWaitTimeout as error:
                last = error.last_snapshot
                if last is None or not _is_clean_base(last, SCREEN_BLACK_MARKET):
                    return self._abort(
                        f"initial_gold_read_failed: {error}"
                    )
                market = last
            except RuntimeWaitAborted as error:
                return self._abort(f"initial_gold_read_failed: {error}")

        initial_gold = tuple(sorted(market.facts.gold_slots))
        initial_purchased = tuple(sorted(market.facts.purchased_slots))
        if not initial_gold:
            self.events.record("black_market.no_gold")
            return self._finish(
                market,
                initial_gold=(),
                initial_purchased=initial_purchased,
            )

        selected = initial_gold if limit is None else initial_gold[:limit]
        attempted: list[int] = []
        verified: list[int] = []
        flow_events: list[FlowEvent] = []

        for slot in selected:
            current = self.observer.observe()
            if not _is_clean_base(current, SCREEN_BLACK_MARKET):
                return self._abort(
                    "unexpected_state_before_slot",
                    initial_gold,
                    attempted,
                    verified,
                    flow_events=flow_events,
                )

            attempted.append(slot)
            selected_slot = self.verified_transition.execute(
                "black_market.select_slot",
                SelectBlackMarketSlot(slot),
                current,
                expected=_is_expected_purchase_branch,
                precondition=lambda snapshot: _is_clean_base(
                    snapshot, SCREEN_BLACK_MARKET
                ),
                retryable_from=lambda snapshot: _is_clean_base(
                    snapshot, SCREEN_BLACK_MARKET
                ),
                abort_if=_has_incompatible_branch,
                policy=self.slot_selection_policy,
            )
            if not selected_slot.succeeded:
                return self._abort(
                    "unexpected_purchase_branch: "
                    f"{selected_slot.outcome.value}: {selected_slot.error}",
                    initial_gold,
                    attempted,
                    verified,
                    flow_events=flow_events,
                )
            branch = selected_slot.final_snapshot

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
                        stable_for=self.post_branch_settle_for,
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
                            flow_events=flow_events,
                            event="black_market.purchase_unverified",
                        )
                    return self._abort(
                        f"unexpected_state_after_purchase: {error}",
                        initial_gold,
                        attempted,
                        verified,
                        flow_events=flow_events,
                    )
                except RuntimeWaitAborted as error:
                    return self._abort(
                        f"unexpected_state_after_purchase: {error}",
                        initial_gold,
                        attempted,
                        verified,
                        flow_events=flow_events,
                    )
                verified.append(slot)
                market = completed
                continue

            if overlays == {POPUP_INSUFFICIENT_GOLD}:
                flow_events.append(FlowEvent("low_gold"))
                self.actions.execute(RejectInsufficientGold(), branch.geometry)
                try:
                    market = self.observer.wait_until(
                        lambda snapshot: _is_clean_base(
                            snapshot, SCREEN_BLACK_MARKET
                        ),
                        after_sequence=branch.sequence,
                        timeout=self.timeout,
                        abort_if=_has_incompatible_after_reject,
                        stable_for=self.post_branch_settle_for,
                    )
                except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
                    return self._abort(
                        f"unexpected_state_after_low_gold: {error}",
                        initial_gold,
                        attempted,
                        verified,
                        flow_events=flow_events,
                    )
                continue

            flow_events.append(FlowEvent("inventory_full"))
            acknowledged = acknowledge_inventory_full(
                self.verified_transition,
                branch,
                policy=self.inventory_full_policy,
                stable_for=self.post_branch_settle_for,
            )
            if not acknowledged.succeeded:
                return self._abort(
                    "inventory_full_ack_failed: "
                    f"{acknowledged.outcome.value}: {acknowledged.error}",
                    initial_gold,
                    attempted,
                    verified,
                    flow_events=flow_events,
                )
            market = acknowledged.final_snapshot

        return self._finish(
            market,
            initial_gold=initial_gold,
            initial_purchased=initial_purchased,
            attempted=attempted,
            verified=verified,
            flow_events=flow_events,
        )

    def _finish(
        self,
        market: RuntimeSnapshot,
        *,
        initial_gold: tuple[int, ...],
        initial_purchased: tuple[int, ...],
        attempted: list[int] | tuple[int, ...] = (),
        verified: list[int] | tuple[int, ...] = (),
        flow_events: list[FlowEvent] | tuple[FlowEvent, ...] = (),
    ) -> BlackMarketFlowResult:
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
                initial_purchased=initial_purchased,
                flow_events=flow_events,
            )

        return BlackMarketFlowResult(
            status=FlowStatus.COMPLETED,
            events=tuple(flow_events),
            initial_gold_slots=initial_gold,
            initial_purchased_slots=initial_purchased,
            attempted_slots=tuple(attempted),
            verified_purchases=tuple(verified),
        )

    def _abort(
        self,
        reason: str,
        initial_gold: tuple[int, ...] = (),
        attempted: list[int] | tuple[int, ...] = (),
        verified: list[int] | tuple[int, ...] = (),
        *,
        initial_purchased: tuple[int, ...] = (),
        flow_events: list[FlowEvent] | tuple[FlowEvent, ...] = (),
        event: str = "black_market.unexpected_state",
    ) -> BlackMarketFlowResult:
        self._record_best_effort(event)
        return BlackMarketFlowResult(
            status=FlowStatus.FAILED,
            events=tuple(flow_events),
            initial_gold_slots=tuple(initial_gold),
            initial_purchased_slots=tuple(initial_purchased),
            attempted_slots=tuple(attempted),
            verified_purchases=tuple(verified),
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


def _can_wait_for_lobby_precondition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return state.status is ResolutionStatus.UNKNOWN and not state.overlays


def _has_incompatible_lobby_precondition(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_LOBBY
        )
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
        or (
            snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context != SCREEN_BLACK_MARKET
        )
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


__all__ = ("BlackMarketFlow", "BlackMarketFlowResult")
