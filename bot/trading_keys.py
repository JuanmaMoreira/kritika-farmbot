"""Avatar & Keys trading capability over the generic verified primitive.

Executor/adapter, not planner: the caller already decided which key
operation to run and with what quantity intent. This module confirms
Avatar & Keys readiness (C1), selects the causal Keys row fact (C3),
builds a ``TradeRequest`` and delegates exactly once to the generic
verified trade primitive (C4), returning its ``TradeResult`` with only
added operation metadata. It never decides order, amounts globally,
routing, sinks, Treasure/Craft/Relief navigation, Monster Wave, route
plans or stages.

Real rows (HIL ground truth, ``screencaps/semantic/trading-center/`` +
``datasets/trading_row_pairs_manifest.json`` keys-top/01.png, 2712x1220;
layout "Item to acquire" left = output, "Item to trade" right = input):

- ``BRONZE_TO_SILVER`` consumes Bronze Keys to acquire Silver Keys.
  Causal row is the ``silver_key`` output row ("Silver Key 2"); its
  fact ``have``/``need`` are Bronze counts (HIL 5/10, need 10 observed,
  never hardcoded as a gate). No ``bronze_key`` output row exists in
  the catalog or HIL: Bronze is input-only here, observed through the
  Silver output row. There is nothing to scroll to find it.
- ``SILVER_TO_GOLD`` consumes Silver Keys to acquire Gold Keys.
  Causal row is the ``gold_key`` output row ("Gold Key 2"); its fact
  ``have``/``need`` are Silver counts (HIL 9/10).

Other visible Keys rows (``silver_gem_key``, ``gold_gem_chest_key``)
belong to a separate Gem chain and have no operation in this module.
No ``Gold -> X`` operation is defined: none exists in the UI.

Keys never scroll (Astra ``024ff8e`` + HIL C1/C2: Keys at the beginning,
zero scroll). This module has no scroll import, no swipe callback, no
directed-scroll fallback. When rows are not ready the caller waits
bounded and input-free (no swipe); this module itself performs no wait
and no input before C4 authorizes it. Lost tab/context fails closed.

Gold Key capacity is NOT OBSERVABLE anywhere in Trading: no reader
reports it and no fact contains it. It is never inferred from 499,
row counts, popup absence or arithmetic (no ``_key_counts``).

Second costs: Keys rows observed with zero second-cost lines (key for
key). The allowlist ``{"gold"}`` follows the C4 materials precedent:
empty costs pass, any premium (karats, ...) fails closed before
confirm. No premium is ever added by inference.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from bot.state import ResolutionStatus
from bot.trading_center import (
    TradingTab,
    clean_trading,
    is_keys_content_ready,
    is_trading_screen,
    trading_tab,
)
from bot.trading_operation import (
    TradeOutcome,
    TradePanelTargets,
    TradePreconditionContext,
    TradeQuantity,
    TradeRequest,
    TradeResult,
    execute_verified_trade,
)
from bot.trading_panel_profile import ROW_TAP_X
from bot.trading_row_facts import KEYS_SECTION, TradingRowFact

KEY_SECTION = KEYS_SECTION

#: Fixed second-cost allowlist for Keys operations. Empty panel costs
#: pass; any kind outside this set fails closed in C4 before confirm.
KEY_ALLOWED_COST_KINDS = frozenset({"gold"})


class KeyTradeOperation(str, Enum):
    """Explicit domain operations; the caller picks one, never an order."""

    BRONZE_TO_SILVER = "bronze_to_silver"
    SILVER_TO_GOLD = "silver_to_gold"


#: Causal output row per operation. ``have``/``need`` on each fact are
#: INPUT counts (Bronze for silver_key, Silver for gold_key).
_KEY_OPERATION_ROW: dict[KeyTradeOperation, str] = {
    KeyTradeOperation.BRONZE_TO_SILVER: "silver_key",
    KeyTradeOperation.SILVER_TO_GOLD: "gold_key",
}

_KEY_ROW_OPERATION: dict[str, KeyTradeOperation] = {
    item_id: operation for operation, item_id in _KEY_OPERATION_ROW.items()
}


def expected_item_for(operation: KeyTradeOperation) -> str:
    """Return the causal output row id for an operation, else raise."""
    if not isinstance(operation, KeyTradeOperation):
        raise ValueError("operation must be KeyTradeOperation")
    return _KEY_OPERATION_ROW[operation]


def operation_for_item(item_id: str) -> KeyTradeOperation:
    """Return the operation owning an output row id, else raise."""
    try:
        return _KEY_ROW_OPERATION[item_id]
    except KeyError as error:
        raise ValueError(f"no key operation for row: {item_id!r}") from error


def check_keys_ready(snapshot) -> str | None:
    """Return None when Avatar & Keys authorizes a trade, else a reason.

    Pure and input-free. Reuses C1 predicates: Trading screen resolved,
    Avatar & Keys exclusively active, positive Keys rows signal, no
    overlays. ``UNKNOWN``/``AMBIGUOUS``/foreign/contradictory never
    authorize input. No scroll, no wait, no fallback lives here: a
    non-None return means zero input.
    """
    status = getattr(getattr(snapshot, "state", None), "status", None)
    if status is ResolutionStatus.UNKNOWN:
        return "unknown_state"
    if status is ResolutionStatus.AMBIGUOUS:
        return "ambiguous_state"
    if not is_trading_screen(snapshot):
        return "not_trading"
    tab = trading_tab(snapshot)
    if tab is TradingTab.CONTRADICTORY:
        return "contradictory_state"
    if tab is not TradingTab.KEYS:
        return "tab_not_keys"
    if not clean_trading(snapshot):
        return "overlays_present"
    if not is_keys_content_ready(snapshot):
        return "rows_not_ready"
    return None


def is_keys_ready(snapshot) -> bool:
    """Return True only when :func:`check_keys_ready` passes."""
    return check_keys_ready(snapshot) is None


def build_keys_context(snapshot) -> TradePreconditionContext:
    """Build the C4 precondition context for the Keys section.

    Pure: translates snapshot truth (screen, overlays, resolver status,
    tab exclusivity, capture sequence) into ``TradePreconditionContext``
    with fixed ``section="keys"``. Never authorizes input by itself;
    C4 still enforces freshness, section match and cleanliness.
    """
    state = getattr(snapshot, "state", None)
    status = getattr(state, "status", None)
    tab = trading_tab(snapshot)
    try:
        sequence = int(snapshot.sequence)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("snapshot must expose an integer sequence") from error
    return TradePreconditionContext(
        is_trading_screen=is_trading_screen(snapshot),
        section=KEY_SECTION,
        clean=clean_trading(snapshot),
        unknown=status is ResolutionStatus.UNKNOWN,
        ambiguous=status is ResolutionStatus.AMBIGUOUS,
        contradictory=tab is TradingTab.CONTRADICTORY,
        sequence=sequence,
    )


def execute_key_trade(
    *,
    operation: KeyTradeOperation,
    snapshot,
    row_fact: TradingRowFact,
    quantity: TradeQuantity,
    targets: TradePanelTargets | None,
    tap: Callable[[tuple[float, float]], None] | None,
    read_panel,
    read_row,
    act: Callable[[object], None] | None = None,
    cancel_requested: Callable[[], bool] = lambda: False,
    max_fact_age: int = 2,
) -> TradeResult:
    """Execute exactly one caller-chosen key operation via C4.

    Zero input unless Avatar & Keys readiness holds on ``snapshot`` and
    ``row_fact`` is the fresh causal row for ``operation``. Single
    delegation to :func:`execute_verified_trade`: no tap causal, panel
    validation, costs, ``>>``, confirm, postcondition or boundary logic
    is duplicated here. Boundaries (including ``OUTPUT_FULL`` on
    Silver->Gold) are returned as-is: no Treasure navigation, no retry,
    no routing. Quantity modes (``EXACT``/``UP_TO``/``MAX_ALLOWED``)
    pass through from the caller; no ``_key_counts`` arithmetic exists
    here and Gold capacity is never inferred.
    """
    if not isinstance(operation, KeyTradeOperation):
        raise ValueError("operation must be KeyTradeOperation")
    if not isinstance(row_fact, TradingRowFact):
        raise ValueError("row_fact must be TradingRowFact")
    if not isinstance(quantity, TradeQuantity):
        raise ValueError("quantity must be TradeQuantity")
    if tap is not None and not isinstance(targets, TradePanelTargets):
        raise ValueError("targets must be TradePanelTargets for legacy tap")
    if (callable(tap) == callable(act)) or not callable(read_panel) or not callable(read_row):
        raise ValueError("exactly one input callback and both readers are required")
    if not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")

    expected = expected_item_for(operation)
    if row_fact.item_id != expected or row_fact.section != KEY_SECTION:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=row_fact,
            reason="row_operation_mismatch",
            evidence=(
                f"operation:{operation.value}",
                f"expected:{expected}",
            ),
        )

    ready_reason = check_keys_ready(snapshot)
    if ready_reason is not None:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=row_fact,
            reason=ready_reason,
            evidence=(
                f"operation:{operation.value}",
                f"readiness:{ready_reason}",
            ),
        )

    context = build_keys_context(snapshot)
    request = TradeRequest(
        row_fact=row_fact,
        quantity=quantity,
        allowed_cost_kinds=KEY_ALLOWED_COST_KINDS,
        row_tap_x=ROW_TAP_X if tap is not None else None,
        expected_item_id=expected,
        max_fact_age=max_fact_age,
    )
    result = execute_verified_trade(
        request=request,
        context=context,
        targets=targets,
        tap=tap,
        read_panel=read_panel,
        read_row=read_row,
        act=act,
        cancel_requested=cancel_requested,
    )
    return TradeResult(
        outcome=result.outcome,
        before_fact=result.before_fact,
        after_fact=result.after_fact,
        boundary=result.boundary,
        reason=result.reason,
        inputs=result.inputs,
        evidence=tuple([*result.evidence, f"operation:{operation.value}"]),
    )


__all__ = (
    "KEY_ALLOWED_COST_KINDS",
    "KEY_SECTION",
    "KeyTradeOperation",
    "build_keys_context",
    "check_keys_ready",
    "execute_key_trade",
    "expected_item_for",
    "is_keys_ready",
    "operation_for_item",
)
