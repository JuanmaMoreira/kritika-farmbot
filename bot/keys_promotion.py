"""Pure deterministic Keys promotion policy (C6a).

Stateless ordering over fresh Trading Keys row facts. Decides ONE next
step per call for the C5 Avatar & Keys capability; never executes UI,
never calls C5/C4, never navigates, never opens Treasure, never touches
Craft/Relief, Monster Wave, planners or stages.

Domain facts (C5-confirmed, HIL-backed):

- ``BRONZE_TO_SILVER`` consumes Bronze Keys; its causal row is
  ``silver_key`` ("Silver Key 2"). Fact ``have``/``need`` are BRONZE
  counts (HIL 5/10).
- ``SILVER_TO_GOLD`` consumes Silver Keys; its causal row is
  ``gold_key`` ("Gold Key 2"). Fact ``have``/``need`` are SILVER counts
  (HIL 9/10).
- Bronze has no output row of its own: it is observed only through the
  Silver output row. There is nothing to scroll to find it.
- Gold capacity is NOT OBSERVABLE anywhere in Trading: no reader
  reports it and no fact contains it. This policy never infers it,
  never counts rows, and never computes output-capacity arithmetic.

Adaptive order (deterministic, observable inputs only):

- When the Silver input covers its need (gold fact ``have >= need``),
  the Silver->Gold promotion is available: request it FIRST, before
  minting more Silver from Bronze.
- Otherwise, when the Bronze input covers its need (silver fact
  ``have >= need``), request Bronze->Silver.
- When neither input covers its need, report ``NO_MORE_PROMOTIONS``.
- After every executed trade the caller supplies a fresh fact-set;
  this module never chains a second trade on a pre-trade snapshot.

This order is NOT claimed to optimize Silver capacity: it is simply
the deterministic rule "consume available Silver toward Gold before
minting more Silver", re-decided from fresh state after each step.
History ordered Keys with inferred-capacity arithmetic without ground
truth of Gold capacity; that arithmetic is discarded here by design
(see ``docs/POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md``).

Quantity: every ``NEXT_OPERATION`` carries ``MAX_ALLOWED``. C4 already
bounds the confirmed amount by the observed panel cap and ``have//need``,
so the policy must not compute output capacity, must not scale by an
inferred cap, and never touches the panel ``>>`` control (C4 owns it).

Freshness: each ``TradingRowFact`` carries a capture sequence.
:func:`decide_next_keys_operation` validates shape/identity only.
:func:`decide_after_trade` requires, on any path that could authorize
another trade (``SUCCESS``, ``INSUFFICIENT_INPUT``, ``NO_MORE_INPUT``),
a fact-set strictly newer than the decided one on BOTH rows; reuse of
the pre-trade snapshot fails closed as stale. Terminal paths
(``OUTPUT_FULL``, ``LIMIT_REACHED``, ``NO_EFFECT``, ``FAILED``,
``CANCELLED``) preserve evidence and never authorize another trade, so
they need no fresh reads. The ``after_fact`` of one row is never used
to invent the fact of the other row.

Budget: every emitted ``NEXT_OPERATION`` is one bounded step. Callers
pass an explicit non-negative ``budget_remaining`` (no default); zero
yields ``BUDGET_EXHAUSTED`` and authorizes nothing. The policy keeps no
counters and runs no loops: after each executed trade the caller
decrements the budget and threads the remainder into
:func:`decide_after_trade`.

Gold-full boundary: ``OUTPUT_FULL`` from ``SILVER_TO_GOLD`` becomes
``GOLD_CAPACITY_BLOCKED`` with the pending causal operation preserved
(operation, original quantity intent, executed before-fact, boundary
evidence, sequence metadata). No Treasure opening is computed here, no
Gold-Key amount is derived, and no automatic second attempt is armed:
C6b decides that later with a complete Treasure runtime. ``OUTPUT_FULL``
from ``BRONZE_TO_SILVER`` is unexpected (that trade outputs Silver,
whose availability is observed through tradeability, not through a full
popup): it fails closed as ``FAILED`` with the boundary preserved in
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from numbers import Integral

from bot.trading_keys import KeyTradeOperation
from bot.trading_operation import (
    TradeOutcome,
    TradeQuantity,
    TradeQuantityMode,
    TradeResult,
)
from bot.trading_row_facts import KEYS_SECTION, TradingRowFact

#: Causal Bronze-input row ("Silver Key 2" output; have/need = Bronze).
SILVER_ROW_ID = "silver_key"

#: Causal Silver-input row ("Gold Key 2" output; have/need = Silver).
GOLD_ROW_ID = "gold_key"


class KeysPromotionKind(str, Enum):
    """Small descriptive taxonomy for one policy step."""

    NEXT_OPERATION = "next_operation"
    NO_MORE_PROMOTIONS = "no_more_promotions"
    GOLD_CAPACITY_BLOCKED = "gold_capacity_blocked"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class PendingCausalOperation:
    """Preserved Silver->Gold request blocked by a full Gold output.

    Descriptive only, for C6b: which operation was executing, with what
    quantity intent, from which before-fact, stopped by which boundary.
    Carries no Treasure route, no Gold-Key relief amount, and no
    automatic second-attempt flag.
    """

    operation: KeyTradeOperation
    quantity: TradeQuantity
    before_fact: TradingRowFact
    boundary: str
    reason: str | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.operation is not KeyTradeOperation.SILVER_TO_GOLD:
            raise ValueError(
                "pending causal operation is only defined for silver_to_gold"
            )
        if not isinstance(self.quantity, TradeQuantity):
            raise ValueError("quantity must be TradeQuantity")
        if self.quantity.mode is not TradeQuantityMode.MAX_ALLOWED:
            raise ValueError("pending quantity must be max_allowed")
        if not isinstance(self.before_fact, TradingRowFact):
            raise ValueError("before_fact must be TradingRowFact")
        if (
            self.before_fact.item_id != GOLD_ROW_ID
            or self.before_fact.section != KEYS_SECTION
        ):
            raise ValueError("before_fact must be the gold_key causal row")
        if not isinstance(self.boundary, str) or not self.boundary:
            raise ValueError("boundary must be a non-empty string")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("reason must be a string or None")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


@dataclass(frozen=True)
class KeysPromotionDecision:
    """One stateless policy step: a next operation or a terminal state."""

    kind: KeysPromotionKind
    operation: KeyTradeOperation | None = None
    quantity: TradeQuantity | None = None
    silver_fact: TradingRowFact | None = None
    gold_fact: TradingRowFact | None = None
    pending: PendingCausalOperation | None = None
    reason: str | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, KeysPromotionKind):
            raise ValueError("kind must be KeysPromotionKind")
        if self.kind is KeysPromotionKind.NEXT_OPERATION:
            if not isinstance(self.operation, KeyTradeOperation):
                raise ValueError("next_operation requires a key operation")
            if not isinstance(self.quantity, TradeQuantity):
                raise ValueError("next_operation requires a quantity")
            if self.quantity.mode is not TradeQuantityMode.MAX_ALLOWED:
                raise ValueError("next_operation quantity must be max_allowed")
            if not isinstance(self.silver_fact, TradingRowFact):
                raise ValueError("next_operation requires the silver fact")
            if not isinstance(self.gold_fact, TradingRowFact):
                raise ValueError("next_operation requires the gold fact")
            if self.pending is not None:
                raise ValueError("next_operation carries no pending boundary")
        elif self.kind is KeysPromotionKind.GOLD_CAPACITY_BLOCKED:
            if self.operation is not None or self.quantity is not None:
                raise ValueError("gold_capacity_blocked authorizes no operation")
            if not isinstance(self.pending, PendingCausalOperation):
                raise ValueError("gold_capacity_blocked requires pending")
            if not isinstance(self.silver_fact, TradingRowFact):
                raise ValueError("gold_capacity_blocked requires silver fact")
            if not isinstance(self.gold_fact, TradingRowFact):
                raise ValueError("gold_capacity_blocked requires gold fact")
        else:
            if self.operation is not None or self.quantity is not None:
                raise ValueError(f"{self.kind.value} authorizes no operation")
            if self.pending is not None:
                raise ValueError(f"{self.kind.value} carries no pending")
            for name in ("silver_fact", "gold_fact"):
                value = getattr(self, name)
                if value is not None and not isinstance(value, TradingRowFact):
                    raise ValueError(f"{name} must be TradingRowFact or None")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("reason must be a string or None")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


def is_tradeable(fact: TradingRowFact) -> bool:
    """Return True when an input covers its need on a causal row.

    Pure: ``have``/``need`` are INPUT counts riding the output row.
    ``need <= 0`` is incoherent and never tradeable.
    """
    if not isinstance(fact, TradingRowFact):
        raise ValueError("fact must be TradingRowFact")
    return fact.need > 0 and fact.have >= fact.need


def default_keys_quantity() -> TradeQuantity:
    """Return the explicit quantity intent for every promotion step.

    Always ``MAX_ALLOWED``: C4 bounds the confirmed amount by the
    observed panel cap and ``have//need``, so the policy computes no
    output capacity and scales by no inferred cap.
    """
    return TradeQuantity(mode=TradeQuantityMode.MAX_ALLOWED)


def decide_next_keys_operation(
    *,
    silver_fact: TradingRowFact,
    gold_fact: TradingRowFact,
    budget_remaining: int,
) -> KeysPromotionDecision:
    """Decide ONE next Keys step from fresh observable facts.

    Pure and stateless: no input, no cache, no loops. ``silver_fact``
    is the ``silver_key`` row (Bronze input), ``gold_fact`` the
    ``gold_key`` row (Silver input). ``budget_remaining`` is required
    and explicit (no default); zero authorizes nothing.
    """
    if not isinstance(silver_fact, TradingRowFact) or not isinstance(
        gold_fact, TradingRowFact
    ):
        raise ValueError("silver_fact and gold_fact must be TradingRowFact")
    mismatch = _check_facts(silver_fact, gold_fact)
    if mismatch is not None:
        return KeysPromotionDecision(
            kind=KeysPromotionKind.FAILED,
            silver_fact=silver_fact,
            gold_fact=gold_fact,
            reason=mismatch,
            evidence=(
                mismatch,
                f"bronze:{silver_fact.have}/{silver_fact.need}",
                f"silver:{gold_fact.have}/{gold_fact.need}",
            ),
        )
    budget = _require_budget(budget_remaining)
    base = (
        f"bronze:{silver_fact.have}/{silver_fact.need}",
        f"silver:{gold_fact.have}/{gold_fact.need}",
        f"budget:{budget}",
        f"seq:silver@{silver_fact.sequence},gold@{gold_fact.sequence}",
    )
    if budget == 0:
        return KeysPromotionDecision(
            kind=KeysPromotionKind.BUDGET_EXHAUSTED,
            silver_fact=silver_fact,
            gold_fact=gold_fact,
            reason="budget_exhausted",
            evidence=("budget_exhausted", *base),
        )
    if is_tradeable(gold_fact):
        return KeysPromotionDecision(
            kind=KeysPromotionKind.NEXT_OPERATION,
            operation=KeyTradeOperation.SILVER_TO_GOLD,
            quantity=default_keys_quantity(),
            silver_fact=silver_fact,
            gold_fact=gold_fact,
            reason="silver_tradeable_first",
            evidence=("order:silver_first", *base),
        )
    if is_tradeable(silver_fact):
        return KeysPromotionDecision(
            kind=KeysPromotionKind.NEXT_OPERATION,
            operation=KeyTradeOperation.BRONZE_TO_SILVER,
            quantity=default_keys_quantity(),
            silver_fact=silver_fact,
            gold_fact=gold_fact,
            reason="silver_short_bronze_tradeable",
            evidence=("order:bronze_next", *base),
        )
    return KeysPromotionDecision(
        kind=KeysPromotionKind.NO_MORE_PROMOTIONS,
        silver_fact=silver_fact,
        gold_fact=gold_fact,
        reason="no_tradeable_input",
        evidence=("order:none", *base),
    )


def decide_after_trade(
    *,
    previous: KeysPromotionDecision,
    result: TradeResult,
    budget_remaining: int,
    silver_fact: TradingRowFact | None = None,
    gold_fact: TradingRowFact | None = None,
) -> KeysPromotionDecision:
    """Fold one C5 ``TradeResult`` into the next stateless policy step.

    Pure: never executes, never invents the other row's fact from
    ``result.after_fact``. Paths that could authorize another trade
    (``SUCCESS``, ``INSUFFICIENT_INPUT``, ``NO_MORE_INPUT``) require a
    fact-set strictly newer than the decided one on BOTH rows and then
    re-decide via :func:`decide_next_keys_operation`. Terminal paths
    (``OUTPUT_FULL``, ``LIMIT_REACHED``, ``NO_EFFECT``, ``FAILED``,
    ``CANCELLED``) preserve evidence, authorize nothing further, and
    need no fresh reads. ``budget_remaining`` is the caller-decremented
    remainder after the executed operation (required, no default);
    terminal boundaries ignore it since they authorize no new input.
    """
    if not isinstance(previous, KeysPromotionDecision):
        raise ValueError("previous must be KeysPromotionDecision")
    if previous.kind is not KeysPromotionKind.NEXT_OPERATION:
        raise ValueError("previous must be a next_operation decision")
    if not isinstance(result, TradeResult):
        raise ValueError("result must be TradeResult")
    budget = _require_budget(budget_remaining)
    outcome = result.outcome
    prev_silver = previous.silver_fact
    prev_gold = previous.gold_fact
    assert isinstance(prev_silver, TradingRowFact)
    assert isinstance(prev_gold, TradingRowFact)

    if outcome is TradeOutcome.OUTPUT_FULL:
        return _after_output_full(previous, result)
    if outcome is TradeOutcome.LIMIT_REACHED:
        return KeysPromotionDecision(
            kind=KeysPromotionKind.FAILED,
            silver_fact=prev_silver,
            gold_fact=prev_gold,
            reason="limit_reached",
            evidence=(
                "limit_reached",
                f"outcome:{outcome.value}",
                *result.evidence,
            ),
        )
    if outcome in (
        TradeOutcome.NO_EFFECT,
        TradeOutcome.FAILED,
        TradeOutcome.CANCELLED,
    ):
        reason = result.reason or outcome.value
        return KeysPromotionDecision(
            kind=KeysPromotionKind.FAILED,
            silver_fact=prev_silver,
            gold_fact=prev_gold,
            reason=reason,
            evidence=(
                f"outcome:{outcome.value}",
                "no_second_trade",
                *result.evidence,
            ),
        )
    if silver_fact is None or gold_fact is None:
        return KeysPromotionDecision(
            kind=KeysPromotionKind.FAILED,
            silver_fact=prev_silver,
            gold_fact=prev_gold,
            reason="missing_facts",
            evidence=(
                "missing_facts",
                f"outcome:{outcome.value}",
                f"prev_seq:silver@{prev_silver.sequence}"
                f",gold@{prev_gold.sequence}",
            ),
        )
    if not isinstance(silver_fact, TradingRowFact) or not isinstance(
        gold_fact, TradingRowFact
    ):
        raise ValueError("silver_fact and gold_fact must be TradingRowFact")
    mismatch = _check_facts(silver_fact, gold_fact)
    if mismatch is not None:
        return KeysPromotionDecision(
            kind=KeysPromotionKind.FAILED,
            silver_fact=silver_fact,
            gold_fact=gold_fact,
            reason=mismatch,
            evidence=(
                mismatch,
                f"outcome:{outcome.value}",
                f"bronze:{silver_fact.have}/{silver_fact.need}",
                f"silver:{gold_fact.have}/{gold_fact.need}",
            ),
        )
    if (
        silver_fact.sequence <= prev_silver.sequence
        or gold_fact.sequence <= prev_gold.sequence
    ):
        return KeysPromotionDecision(
            kind=KeysPromotionKind.FAILED,
            silver_fact=silver_fact,
            gold_fact=gold_fact,
            reason="stale_facts",
            evidence=(
                "stale_facts",
                f"outcome:{outcome.value}",
                f"prev_seq:silver@{prev_silver.sequence}"
                f",gold@{prev_gold.sequence}",
                f"new_seq:silver@{silver_fact.sequence}"
                f",gold@{gold_fact.sequence}",
            ),
        )
    return decide_next_keys_operation(
        silver_fact=silver_fact,
        gold_fact=gold_fact,
        budget_remaining=budget,
    )


def _after_output_full(
    previous: KeysPromotionDecision,
    result: TradeResult,
) -> KeysPromotionDecision:
    """Map ``OUTPUT_FULL``: Gold boundary only for Silver->Gold."""
    prev_silver = previous.silver_fact
    prev_gold = previous.gold_fact
    assert isinstance(prev_silver, TradingRowFact)
    assert isinstance(prev_gold, TradingRowFact)
    boundary = result.boundary or "output_full"
    if previous.operation is KeyTradeOperation.SILVER_TO_GOLD:
        before = result.before_fact
        if (
            not isinstance(before, TradingRowFact)
            or before.item_id != GOLD_ROW_ID
            or before.section != KEYS_SECTION
        ):
            return KeysPromotionDecision(
                kind=KeysPromotionKind.FAILED,
                silver_fact=prev_silver,
                gold_fact=prev_gold,
                reason="before_fact_mismatch",
                evidence=(
                    "before_fact_mismatch",
                    f"boundary:{boundary}",
                    *result.evidence,
                ),
            )
        assert isinstance(previous.quantity, TradeQuantity)
        pending = PendingCausalOperation(
            operation=KeyTradeOperation.SILVER_TO_GOLD,
            quantity=previous.quantity,
            before_fact=before,
            boundary=boundary,
            reason=result.reason,
            evidence=(
                "operation:silver_to_gold",
                f"boundary:{boundary}",
                f"before:{before.have}/{before.need}",
                f"prev_seq:silver@{prev_silver.sequence}"
                f",gold@{prev_gold.sequence}",
                *result.evidence,
            ),
        )
        return KeysPromotionDecision(
            kind=KeysPromotionKind.GOLD_CAPACITY_BLOCKED,
            silver_fact=prev_silver,
            gold_fact=prev_gold,
            pending=pending,
            reason="gold_capacity_blocked",
            evidence=(
                "gold_capacity_blocked",
                f"boundary:{boundary}",
                *result.evidence,
            ),
        )
    return KeysPromotionDecision(
        kind=KeysPromotionKind.FAILED,
        silver_fact=prev_silver,
        gold_fact=prev_gold,
        reason="unexpected_output_full",
        evidence=(
            "unexpected_output_full",
            f"boundary:{boundary}",
            *result.evidence,
        ),
    )


def _check_facts(
    silver_fact: TradingRowFact, gold_fact: TradingRowFact
) -> str | None:
    """Return None when both facts are the compatible causal rows."""
    if (
        silver_fact.item_id != SILVER_ROW_ID
        or silver_fact.section != KEYS_SECTION
    ):
        return "silver_fact_mismatch"
    if gold_fact.item_id != GOLD_ROW_ID or gold_fact.section != KEYS_SECTION:
        return "gold_fact_mismatch"
    if silver_fact.need <= 0 or gold_fact.need <= 0:
        return "incoherent_need"
    return None


def _require_budget(value: object) -> int:
    """Validate the explicit bound; zero is allowed (exhausted)."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("budget_remaining must be an integer")
    result = int(value)
    if result < 0:
        raise ValueError("budget_remaining must be non-negative")
    return result


def pending_field_names() -> tuple[str, ...]:
    """Return the descriptive fields of a pending causal operation."""
    return tuple(field.name for field in fields(PendingCausalOperation))


__all__ = (
    "GOLD_ROW_ID",
    "KEYS_SECTION",
    "KeysPromotionDecision",
    "KeysPromotionKind",
    "PendingCausalOperation",
    "SILVER_ROW_ID",
    "decide_after_trade",
    "decide_next_keys_operation",
    "default_keys_quantity",
    "is_tradeable",
    "pending_field_names",
)
