"""Generic verified trading operation over one fresh Trading row.

Executor, not planner: the caller already decided which row to trade and
how much to request. This module consumes a fresh ``TradingRowFact``,
taps exactly that row once, verifies the opened panel against the fact,
models second costs as data/guards, selects a bounded quantity with a
single causal ``>>`` tap, confirms once, and proves the effect with a
fresh postcondition. It never decides item order, routing, sinks,
Treasure/Craft/Relief navigation, Monster Wave, route plans or stages.

Astra reconstruction (read-only, ``024ff8e``) informs the contract but
no coordinate, ROI, arithmetic or retry exception is copied blindly:

- row tap x belongs to the Trading consumer/profile, never to this
  module (Astra ``(.706, center_y)`` vs current ``x~=0.75`` disagree);
- panel ``>>``/confirm/cancel points arrive caller-supplied in
  ``TradePanelTargets``; nothing here hardcodes a button position;
- quantity caps/denominators are observed per panel (Astra ``n/20``
  is a reference, not a constant);
- ``>>`` is non-idempotent: one causal tap, effect observed, no
  re-tap on generic timeout. The old ``20/20``-vs-``1/20`` single
  re-tap exception is NOT rescued without current-HIL proof;
- popup-vs-row mismatch blocks confirmation (Astra principle kept);
- success requires fresh ``after.have < before.have`` (minimum; no
  exact-amount arithmetic).

Current-UI panel layout (controls, quantity widgets, second-cost
placement, cancel geometry) has no capture in the repo corpus; HIL A
must audit it before any economic confirm. This module is therefore
layout-agnostic: panel facts are injected reads, never detectors.
Perception is untouched: C4 reuses the existing ``TRADING_SCOPE``
(title spec + tabs/rows specialized detectors) for Trading context
gates and promotes zero new detectors in this task.

Boundary vocabulary: ``OUTPUT_FULL`` means only "the trade could not
complete because the output is full". It never navigates to Treasure
nor triggers relief; the specific consumer decides afterwards.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

from bot.trading_row_facts import TradingRowFact


class TradeOutcome(str, Enum):
    """Small descriptive taxonomy for one bounded trade operation."""

    SUCCESS = "success"
    INSUFFICIENT_INPUT = "insufficient_input"
    OUTPUT_FULL = "output_full"
    LIMIT_REACHED = "limit_reached"
    NO_MORE_INPUT = "no_more_input"
    NO_EFFECT = "no_effect"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TradeQuantityMode(str, Enum):
    """What the caller asks the panel to confirm."""

    EXACT = "exact"
    UP_TO = "up_to"
    MAX_ALLOWED = "max_allowed"


@dataclass(frozen=True)
class TradeQuantity:
    """Explicit quantity intent; no hidden MAX assumption.

    ``EXACT``/``UP_TO`` carry a positive ``amount``. ``MAX_ALLOWED``
    carries none and accepts whatever single ``>>`` fill the panel
    proves. Decrement/increment controls are out of scope until HIL
    demonstrates them: after one ``>>`` tap, ``EXACT`` requires the
    panel-selected amount to equal ``amount`` and ``UP_TO`` requires
    it to be ``<= amount``; otherwise fail closed without confirm.
    """

    mode: TradeQuantityMode
    amount: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, TradeQuantityMode):
            raise ValueError("mode must be TradeQuantityMode")
        if self.mode is TradeQuantityMode.MAX_ALLOWED:
            if self.amount is not None:
                raise ValueError("max_allowed carries no amount")
            return
        if isinstance(self.amount, bool) or not isinstance(
            self.amount, Integral
        ):
            raise ValueError("amount must be a positive integer")
        if int(self.amount) < 1:
            raise ValueError("amount must be a positive integer")
        object.__setattr__(self, "amount", int(self.amount))


@dataclass(frozen=True)
class TradeCostFact:
    """One observed second cost as data, never routing.

    ``kind`` names the visible currency/resource (for example
    ``"gold"``). ``amount`` is the visible cost or None when
    illegible. ``sufficient`` is True/False only when explicitly
    observable, else None. The caller allowlist decides which kinds
    may proceed; anything else fails closed before confirm.
    """

    kind: str
    amount: int | None = None
    sufficient: bool | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("kind must be a non-empty string")
        object.__setattr__(self, "kind", self.kind.strip())
        if self.amount is not None:
            if isinstance(self.amount, bool) or not isinstance(
                self.amount, Integral
            ):
                raise ValueError("amount must be an integer or None")
            if int(self.amount) < 0:
                raise ValueError("amount must be non-negative")
            object.__setattr__(self, "amount", int(self.amount))
        if self.sufficient is not None and not isinstance(
            self.sufficient, bool
        ):
            raise ValueError("sufficient must be bool or None")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


@dataclass(frozen=True)
class TradePanelFact:
    """Injected read of the opened trade panel/popup.

    All numeric fields are observed values or None when unreadable;
    unreadable never reads as zero. ``quantity`` is the observed
    ``(selected, cap)`` pair or None. Boundary flags are True only on
    explicit observable signals. ``sequence`` must be strictly greater
    than the authorizing row-tap evidence to prove freshness.
    """

    item_id: str | None
    input_have: int | None
    input_need: int | None
    quantity: tuple[int, int] | None
    costs: tuple[TradeCostFact, ...] = ()
    sequence: int = 0
    panel_open: bool = True
    shows_insufficient: bool = False
    shows_output_full: bool = False
    shows_limit: bool = False
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.item_id is not None and (
            not isinstance(self.item_id, str) or not self.item_id
        ):
            raise ValueError("item_id must be a non-empty string or None")
        for name in ("input_have", "input_need"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(
                    value, Integral
                ):
                    raise ValueError(f"{name} must be an integer or None")
                if int(value) < 0:
                    raise ValueError(f"{name} must be non-negative")
                object.__setattr__(self, name, int(value))
        if self.quantity is not None:
            selected, cap = self.quantity
            for value in (selected, cap):
                if isinstance(value, bool) or not isinstance(
                    value, Integral
                ):
                    raise ValueError("quantity must hold integers")
                if int(value) < 0:
                    raise ValueError("quantity must be non-negative")
            object.__setattr__(
                self, "quantity", (int(selected), int(cap))
            )
        object.__setattr__(self, "costs", tuple(self.costs))
        for cost in self.costs:
            if not isinstance(cost, TradeCostFact):
                raise ValueError("costs must contain TradeCostFact values")
        if isinstance(self.sequence, bool) or not isinstance(
            self.sequence, Integral
        ):
            raise ValueError("sequence must be an integer")
        object.__setattr__(self, "sequence", int(self.sequence))
        for name in (
            "panel_open",
            "shows_insufficient",
            "shows_output_full",
            "shows_limit",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


@dataclass(frozen=True)
class TradePreconditionContext:
    """Minimal Trading context gate owned by the caller.

    The caller builds this from a fresh snapshot (Trading screen,
    tab/section, overlays, resolver status). ``section`` is
    ``"materials"``/``"keys"`` or any other string for unknown;
    ``contradictory`` covers exclusive-tab violations. ``sequence``
    shares the capture-sequence domain with ``TradingRowFact`` and
    panel facts.
    """

    is_trading_screen: bool
    section: str
    clean: bool
    unknown: bool = False
    ambiguous: bool = False
    contradictory: bool = False
    sequence: int = 0

    def __post_init__(self) -> None:
        for name in (
            "is_trading_screen",
            "clean",
            "unknown",
            "ambiguous",
            "contradictory",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if not isinstance(self.section, str) or not self.section:
            raise ValueError("section must be a non-empty string")
        if isinstance(self.sequence, bool) or not isinstance(
            self.sequence, Integral
        ):
            raise ValueError("sequence must be an integer")
        object.__setattr__(self, "sequence", int(self.sequence))


@dataclass(frozen=True)
class TradePanelTargets:
    """Caller-supplied normalized panel points; no defaults.

    Every point is an ``(x, y)`` pair in ``[0, 1]`` owned by the
    Trading consumer/profile (HIL-calibrated). This module never
    invents an interactive coordinate.
    """

    max_point: tuple[float, float]
    confirm_point: tuple[float, float]
    cancel_point: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        for name in ("max_point", "confirm_point"):
            point = getattr(self, name)
            object.__setattr__(self, name, _require_point(point, name))
        cancel = self.cancel_point
        if cancel is not None:
            object.__setattr__(
                self, "cancel_point", _require_point(cancel, "cancel_point")
            )


@dataclass(frozen=True)
class TradeRequest:
    """Already-decided intention for exactly one bounded operation.

    ``allowed_cost_kinds`` is an explicit non-empty allowlist: any
    observed cost kind outside it aborts before confirm. Premium
    currencies must never be added by inference; the caller lists
    only what the current task explicitly permits.
    """

    row_fact: TradingRowFact
    quantity: TradeQuantity
    allowed_cost_kinds: frozenset[str]
    row_tap_x: float | None = None
    expected_item_id: str | None = None
    max_fact_age: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.row_fact, TradingRowFact):
            raise ValueError("row_fact must be TradingRowFact")
        if not isinstance(self.quantity, TradeQuantity):
            raise ValueError("quantity must be TradeQuantity")
        try:
            kinds = frozenset(self.allowed_cost_kinds)
        except TypeError as error:
            raise ValueError(
                "allowed_cost_kinds must be a collection of strings"
            ) from error
        if not kinds or not all(
            isinstance(kind, str) and kind.strip() for kind in kinds
        ):
            raise ValueError(
                "allowed_cost_kinds must be a non-empty set of strings"
            )
        object.__setattr__(
            self, "allowed_cost_kinds", frozenset(k.strip() for k in kinds)
        )
        if self.row_tap_x is not None:
            object.__setattr__(
                self, "row_tap_x", _require_unit(self.row_tap_x, "row_tap_x")
            )
        expected = self.expected_item_id
        if expected is None:
            object.__setattr__(self, "expected_item_id", self.row_fact.item_id)
        else:
            if not isinstance(expected, str) or not expected:
                raise ValueError(
                    "expected_item_id must be a non-empty string or None"
                )
            object.__setattr__(self, "expected_item_id", expected)
        if (
            isinstance(self.max_fact_age, bool)
            or not isinstance(self.max_fact_age, Integral)
            or int(self.max_fact_age) < 0
        ):
            raise ValueError("max_fact_age must be a non-negative integer")
        object.__setattr__(self, "max_fact_age", int(self.max_fact_age))


@dataclass(frozen=True)
class TradeResult:
    """Descriptive outcome; never a routing decision."""

    outcome: TradeOutcome
    before_fact: TradingRowFact
    after_fact: TradingRowFact | None = None
    boundary: str | None = None
    reason: str | None = None
    inputs: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, TradeOutcome):
            raise ValueError("outcome must be TradeOutcome")
        if not isinstance(self.before_fact, TradingRowFact):
            raise ValueError("before_fact must be TradingRowFact")
        if self.after_fact is not None and not isinstance(
            self.after_fact, TradingRowFact
        ):
            raise ValueError("after_fact must be TradingRowFact or None")
        if self.boundary is not None and (
            not isinstance(self.boundary, str) or not self.boundary
        ):
            raise ValueError("boundary must be a non-empty string or None")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("reason must be a string or None")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        for item in self.inputs:
            if not isinstance(item, str):
                raise ValueError("inputs must contain strings")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


def check_precondition(
    request: TradeRequest,
    context: TradePreconditionContext,
) -> str | None:
    """Return None when a row tap is authorized, else a fail reason.

    Pure and input-free: any non-None return means zero input.
    ``NO_MORE_INPUT`` for ``have < need`` is a boundary, not a
    failure, but likewise authorizes zero input here.
    """
    fact = request.row_fact
    if request.expected_item_id != fact.item_id:
        return "row_mismatch"
    if context.unknown:
        return "unknown_state"
    if context.ambiguous:
        return "ambiguous_state"
    if context.contradictory:
        return "contradictory_state"
    if not context.is_trading_screen:
        return "not_trading"
    if not context.clean:
        return "overlays_present"
    if context.section != fact.section:
        return "section_mismatch"
    age = context.sequence - fact.sequence
    if age < 0 or age > request.max_fact_age:
        return "stale_fact"
    if fact.need <= 0:
        return "incoherent_need"
    if fact.have < fact.need:
        return "no_more_input"
    return None


def check_panel_matches_row(
    panel: TradePanelFact,
    row_fact: TradingRowFact,
) -> str | None:
    """Return None when the panel proves the causal row, else a reason."""
    if panel.item_id != row_fact.item_id:
        return "popup_row_mismatch"
    if panel.input_need != row_fact.need:
        return "second_cost_mismatch"
    if panel.input_have != row_fact.have:
        return "popup_row_mismatch"
    return None


def check_costs(
    panel: TradePanelFact,
    allowed: frozenset[str],
) -> str | None:
    """Return None when every observed cost is allowed, else a reason."""
    for cost in panel.costs:
        if cost.kind not in allowed:
            return "unexpected_currency"
        if cost.amount is None:
            return "unreadable_cost"
    return None


def resolve_quantity_target(
    quantity: TradeQuantity,
    panel: TradePanelFact,
    row_fact: TradingRowFact,
) -> tuple[int | None, str | None]:
    """Derive the confirmable target from one fresh panel read.

    Returns ``(target, None)`` or ``(None, reason)``. The cap comes
    from the observed panel pair only; no historic denominator is
    assumed. ``have // need`` bounds the target independently so a
    lying panel cap cannot oversell the input.
    """
    if panel.quantity is None:
        return None, "unreadable_quantity"
    _selected, cap = panel.quantity
    if cap <= 0:
        return None, "impossible_amount"
    affordable = row_fact.have // row_fact.need if row_fact.need > 0 else 0
    if affordable <= 0:
        return None, "no_more_input"
    if quantity.mode is TradeQuantityMode.MAX_ALLOWED:
        return min(cap, affordable), None
    assert quantity.amount is not None
    wanted = int(quantity.amount)
    if wanted < 1:
        return None, "impossible_amount"
    if quantity.mode is TradeQuantityMode.UP_TO:
        return min(wanted, cap, affordable), None
    if wanted > cap or wanted > affordable:
        return None, "impossible_amount"
    return wanted, None


def quantity_satisfied(
    quantity: TradeQuantity, target: int, selected: int
) -> bool:
    """Check one observed selection against the intent and target."""
    if quantity.mode is TradeQuantityMode.EXACT:
        return selected == target == quantity.amount
    if quantity.mode is TradeQuantityMode.UP_TO:
        return selected <= int(quantity.amount or 0) and selected == target
    return selected == target


def execute_verified_trade(
    *,
    request: TradeRequest,
    context: TradePreconditionContext,
    targets: TradePanelTargets | None,
    tap: Callable[[tuple[float, float]], None] | None,
    read_panel: Callable[[], TradePanelFact | None],
    read_row: Callable[[], TradingRowFact | None],
    act: Callable[[object], None] | None = None,
    cancel_requested: Callable[[], bool] = lambda: False,
) -> TradeResult:
    """Execute one bounded trade; single causal tap per control.

    Injected I/O only: production ``act`` emits typed ActionExecutor intents;
    legacy ``tap`` remains for standalone callers. ``read_panel``/``read_row``
    return fresh domain facts or None. No
    navigation, no retry, no double inputs: ``>>`` fires at most
    once and confirm fires at most once, each only after all guards
    hold on the freshest panel fact. Any abort before confirm taps
    cancel exactly once when ``targets.cancel_point`` is set,
    otherwise returns with zero further input (still zero spend).
    Boundary popups (insufficient/output-full/limit) are returned,
    never resolved: no Treasure/Craft/Relief navigation happens here.
    """
    before = request.row_fact
    if (callable(tap) == callable(act)) or not callable(read_panel) or not callable(
        read_row
    ):
        raise ValueError("exactly one input callback and both readers are required")
    if not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")
    if tap is not None and not isinstance(targets, TradePanelTargets):
        raise ValueError("targets must be TradePanelTargets for legacy tap")
    if tap is not None and request.row_tap_x is None:
        raise ValueError("legacy tap requires row_tap_x")

    if act is not None:
        from bot.semantic_actions import (
            CancelTradingTrade, ConfirmTradingTrade, SelectTradingMaximum,
            SelectTradingRow,
        )

    def input_row() -> None:
        if act is not None:
            act(SelectTradingRow(before))
        else:
            tap((request.row_tap_x, before.row_y))

    def input_max() -> None:
        if act is not None:
            act(SelectTradingMaximum())
        else:
            tap(targets.max_point)

    def input_confirm() -> None:
        if act is not None:
            act(ConfirmTradingTrade())
        else:
            tap(targets.confirm_point)

    def input_cancel() -> None:
        if act is not None:
            act(CancelTradingTrade())
        else:
            tap(targets.cancel_point)

    def _cancel_once(inputs: list[str], reason: str) -> None:
        if act is not None or targets.cancel_point is not None:
            input_cancel()
            inputs.append("tap_cancel")

    try:
        cancelled = cancel_requested() is True
    except Exception:
        cancelled = False
    if cancelled:
        return TradeResult(
            outcome=TradeOutcome.CANCELLED,
            before_fact=before,
            reason="user_cancelled",
            evidence=("cancel_before_input",),
        )

    blocked = check_precondition(request, context)
    if blocked is not None:
        if blocked == "no_more_input":
            return TradeResult(
                outcome=TradeOutcome.NO_MORE_INPUT,
                before_fact=before,
                reason="have_below_need",
                evidence=(f"precondition:{blocked}",),
            )
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=blocked,
            evidence=(f"precondition:{blocked}",),
        )

    inputs: list[str] = []
    evidence: list[str] = [f"before:{before.have}/{before.need}"]

    try:
        input_row()
    except Exception as error:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=f"row_tap_failed:{type(error).__name__}",
            evidence=tuple(evidence),
        )
    inputs.append("tap_row")

    panel = read_panel()
    if panel is None or not panel.panel_open:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="panel_not_open",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "panel_not_open"]),
        )
    if panel.sequence <= before.sequence:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="stale_panel",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "stale_panel"]),
        )
    if panel.shows_output_full:
        return TradeResult(
            outcome=TradeOutcome.OUTPUT_FULL,
            before_fact=before,
            boundary="output_full",
            reason="output_full_on_open",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:output_full"]),
        )
    if panel.shows_insufficient:
        return TradeResult(
            outcome=TradeOutcome.INSUFFICIENT_INPUT,
            before_fact=before,
            boundary="insufficient_input",
            reason="insufficient_on_open",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:insufficient_input"]),
        )
    if panel.shows_limit:
        return TradeResult(
            outcome=TradeOutcome.LIMIT_REACHED,
            before_fact=before,
            boundary="limit_reached",
            reason="limit_on_open",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:limit_reached"]),
        )

    mismatch = check_panel_matches_row(panel, before)
    if mismatch is not None:
        _cancel_once(inputs, mismatch)
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=mismatch,
            inputs=tuple(inputs),
            evidence=tuple([*evidence, mismatch]),
        )
    costs_blocked = check_costs(panel, request.allowed_cost_kinds)
    if costs_blocked is not None:
        if any(
            cost.sufficient is False for cost in panel.costs
        ) and costs_blocked != "unexpected_currency":
            _cancel_once(inputs, costs_blocked)
            return TradeResult(
                outcome=TradeOutcome.INSUFFICIENT_INPUT,
                before_fact=before,
                boundary="insufficient_input",
                reason="second_cost_insufficient",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "second_cost_insufficient"]),
            )
        _cancel_once(inputs, costs_blocked)
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=costs_blocked,
            inputs=tuple(inputs),
            evidence=tuple([*evidence, costs_blocked]),
        )
    if any(cost.sufficient is False for cost in panel.costs):
        _cancel_once(inputs, "second_cost_insufficient")
        return TradeResult(
            outcome=TradeOutcome.INSUFFICIENT_INPUT,
            before_fact=before,
            boundary="insufficient_input",
            reason="second_cost_insufficient",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "second_cost_insufficient"]),
        )

    target, qty_error = resolve_quantity_target(
        request.quantity, panel, before
    )
    if qty_error is not None:
        if qty_error == "no_more_input":
            _cancel_once(inputs, qty_error)
            return TradeResult(
                outcome=TradeOutcome.NO_MORE_INPUT,
                before_fact=before,
                reason="have_below_need",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, qty_error]),
            )
        _cancel_once(inputs, qty_error)
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=qty_error,
            inputs=tuple(inputs),
            evidence=tuple([*evidence, qty_error]),
        )
    assert target is not None and target >= 1

    # No inputs "por las dudas": when the fresh panel selection already
    # satisfies the intent (HIL-proven: >> from an already-maxed
    # selection summons the quantity-limit popup instead of selecting),
    # the >> tap is skipped and the same fresh fact authorizes confirm.
    # Otherwise exactly one causal >> tap follows, never a blind second.
    selected_now, _cap_now = panel.quantity
    max_tapped = False
    if quantity_satisfied(request.quantity, target, selected_now):
        filled = panel
        evidence.append("max_skipped:already_selected")
    else:
        try:
            input_max()
        except Exception as error:
            return TradeResult(
                outcome=TradeOutcome.FAILED,
                before_fact=before,
                reason=f"max_tap_failed:{type(error).__name__}",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "max_tap_failed"]),
            )
        inputs.append("tap_max")
        max_tapped = True

        filled = read_panel()
    if filled is None or not filled.panel_open:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="panel_lost_after_max",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "panel_lost_after_max"]),
        )
    if max_tapped and filled.sequence <= panel.sequence:
        _cancel_once(inputs, "stale_panel")
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="stale_panel_after_max",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "stale_panel_after_max"]),
        )
    if filled.shows_output_full:
        return TradeResult(
            outcome=TradeOutcome.OUTPUT_FULL,
            before_fact=before,
            boundary="output_full",
            reason="output_full_after_max",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:output_full"]),
        )
    if filled.shows_insufficient:
        return TradeResult(
            outcome=TradeOutcome.INSUFFICIENT_INPUT,
            before_fact=before,
            boundary="insufficient_input",
            reason="insufficient_after_max",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:insufficient_input"]),
        )
    if filled.shows_limit:
        return TradeResult(
            outcome=TradeOutcome.LIMIT_REACHED,
            before_fact=before,
            boundary="limit_reached",
            reason="limit_after_max",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:limit_reached"]),
        )
    rematch = check_panel_matches_row(filled, before)
    if rematch is not None:
        _cancel_once(inputs, rematch)
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=rematch,
            inputs=tuple(inputs),
            evidence=tuple([*evidence, rematch]),
        )
    recosts = check_costs(filled, request.allowed_cost_kinds)
    if recosts is not None:
        _cancel_once(inputs, recosts)
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=recosts,
            inputs=tuple(inputs),
            evidence=tuple([*evidence, recosts]),
        )
    if filled.quantity is None:
        _cancel_once(inputs, "unreadable_quantity")
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="unreadable_quantity",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "unreadable_quantity"]),
        )
    selected, _cap = filled.quantity
    # Single causal >>: no second tap on timeout. If the observed
    # selection does not satisfy the intent, fail closed here.
    if not quantity_satisfied(request.quantity, target, selected):
        _cancel_once(inputs, "max_no_effect")
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="max_no_effect",
            inputs=tuple(inputs),
            evidence=tuple(
                [*evidence, f"max_no_effect:selected={selected}"]
            ),
        )

    try:
        cancelled = cancel_requested() is True
    except Exception:
        cancelled = False
    if cancelled:
        _cancel_once(inputs, "user_cancelled")
        return TradeResult(
            outcome=TradeOutcome.CANCELLED,
            before_fact=before,
            reason="user_cancelled",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "user_cancelled"]),
        )

    try:
        input_confirm()
    except Exception as error:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason=f"confirm_failed:{type(error).__name__}",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "confirm_failed"]),
        )
    inputs.append("tap_confirm")

    closing = read_panel()
    if closing is not None and closing.panel_open:
        if closing.sequence > filled.sequence:
            if closing.shows_output_full:
                return TradeResult(
                    outcome=TradeOutcome.OUTPUT_FULL,
                    before_fact=before,
                    boundary="output_full",
                    reason="output_full_on_confirm",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "boundary:output_full"]),
                )
            if closing.shows_insufficient:
                return TradeResult(
                    outcome=TradeOutcome.INSUFFICIENT_INPUT,
                    before_fact=before,
                    boundary="insufficient_input",
                    reason="insufficient_on_confirm",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "boundary:insufficient_input"]),
                )
            if closing.shows_limit:
                return TradeResult(
                    outcome=TradeOutcome.LIMIT_REACHED,
                    before_fact=before,
                    boundary="limit_reached",
                    reason="limit_on_confirm",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "boundary:limit_reached"]),
                )

    after = read_row()
    if after is None:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            reason="after_fact_unreadable",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "after_fact_unreadable"]),
        )
    if after.item_id != before.item_id or after.section != before.section:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            after_fact=after,
            reason="after_identity_mismatch",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "after_identity_mismatch"]),
        )
    if after.sequence <= filled.sequence:
        return TradeResult(
            outcome=TradeOutcome.FAILED,
            before_fact=before,
            after_fact=after,
            reason="stale_after_fact",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "stale_after_fact"]),
        )
    if after.have < before.have:
        return TradeResult(
            outcome=TradeOutcome.SUCCESS,
            before_fact=before,
            after_fact=after,
            inputs=tuple(inputs),
            evidence=tuple(
                [*evidence, f"after:{after.have}/{after.need}"]
            ),
        )
    return TradeResult(
        outcome=TradeOutcome.NO_EFFECT,
        before_fact=before,
        after_fact=after,
        reason="have_unchanged",
        inputs=tuple(inputs),
        evidence=tuple([*evidence, f"after:{after.have}/{after.need}"]),
    )


def _require_point(value: object, name: str) -> tuple[float, float]:
    try:
        first, second = value  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an (x, y) pair") from error
    return (_require_unit(first, name), _require_unit(second, name))


def _require_unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return result


__all__ = (
    "TradeCostFact",
    "TradeOutcome",
    "TradePanelFact",
    "TradePanelTargets",
    "TradePreconditionContext",
    "TradeQuantity",
    "TradeQuantityMode",
    "TradeRequest",
    "TradeResult",
    "check_costs",
    "check_panel_matches_row",
    "check_precondition",
    "execute_verified_trade",
    "quantity_satisfied",
    "resolve_quantity_target",
)
