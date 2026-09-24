"""Gold Keys Treasure capability over fresh currency evidence.

Executor/adapter, not planner: the caller already decided to open a
bounded amount of Gold Keys and with what budget. This module confirms
Treasure readiness, observes fresh Gold-Key currency before every
single tap, opens at most ``max_actions`` times with caller-supplied
points, proves consumption with fresh postconditions and stops before
any premium currency. It never decides when Treasure must be called,
order, routing, sinks, Trading/Craft/Relief navigation, Monster Wave,
route plans or stages.

Astra reconstruction (read-only ``024ff8e``, no wholesale copy):

| concepto | evidencia historica | sigue valido? | necesita HIL? | diseno nuevo |
|---|---|---|---|---|
| entrada/salida | ``TreasureOperations.enter/leave`` via ``OPEN_TREASURE`` Lobby->Treasure y ``BACK`` + ``TREASURE_DISMISS`` | coords NO, patron SI | SI (tap + llegada + retorno) | capability no navega: caller entra/sale; aqui solo readiness + contrato source/return descriptivo; HIL A lo valida manual |
| gold_key_boundary | ``gold_key_boundary`` fresco por accion, ``key==karat`` fail-closed, ``(currency, amount, sequence)`` con 10 si repeat sino 1 | SI | SI (iconos actuales) | ``TreasureCurrencyFact`` + ``check_currency`` puro + stop-before-premium por accion |
| selector/open controls | ``GOLD_CHEST`` + ``OpenGoldTreasure(amount, repeat)`` en 4 puntos segun amount/repeat | patron SI, puntos NO | SI | ``TreasureOpenTargets`` caller-supplied (single/repeat), sin hardcode; UNCALIBRATED hasta HIL |
| open_gold_once | guard selector+key+no-karat, departure de la tira + resultado estable exclusivo | SI | SI (animacion/tap-through) | postcondicion fresca por accion: count disminuye preferido, sino result exclusivo minimo demostrado; animacion sola nunca SUCCESS |
| repeat/batch | ``TreasureSink`` loop con ``repeat`` flag y deadline 900s sin contar aperturas | bound SI, 900s NO | parcial (x10 existe?) | loop acotado por ``quantity`` + ``max_actions`` explicitos; 1/10 por evidencia fresca, sin asumir x10 siempre |
| currency freshness | ``rt.fresh`` + ``sequence`` estrictamente creciente, stale raise | NO (sequence es contador-decoder a video-rate, no edad) | NO (mecanismo) | ``observed_at`` (capture monotonic) + barrier causal del snapshot autorizador + ``max_fact_age_s``; stale nunca SUCCESS; sequence queda sólo para orden lógico/dedup |
| Gold-vs-Karat | oferta Karats rechazada, Karat corta sin tocar premium | SI | SI (senales actuales) | allowlist exacta ``{"gold_key"}``; otro premium => PREMIUM_CURRENCY_BOUNDARY cero confirm |
| budget temporal | deadline 900s acota repeticion | concepto SI | NO | ``max_actions`` requerido + ``cancel_requested``; sin loops ocultos |
| postcondition consumo | departure + resultado estable exclusivo (sin counts) | parcial | SI (counts observables?) | count disminuye preferido; fallback result exclusivo minimo; unchanged fresco => NO_EFFECT sin retry |
| dismiss/return | dismiss result + BACK a Lobby | patron SI | SI | caller own return; resultado expone ``after`` + evidencia para verificacion externa |

NO rescatado: ``ReliefRuntime``, sinks/orquestador viejos, Trading
coupling, Inventory Relief coupling, lifecycle framework, planner
PASS1/PASS2, aritmetica ``499-silver``/balances por calculo.

Domain corrections (closed): Treasure NO necesita scroll; abrir Gold
Keys con Equipment Inventory lleno esta permitido y NO provoca
equipment-full; Treasure NO consume Inventory Relief; Treasure NO
conoce Trading ni OUTPUT_FULL; Treasure NO decide cuando ser llamado;
Gold Key capacity sigue NOT OBSERVABLE desde Trading/board y NO se
resuelve aqui.

Entry audit (hoy): unica fuente soportada documentada es Lobby via
tile Treasure (``bot/constants.py`` ``treasure`` ~(0.722, 0.9167) y
quick-menu ~(0.142, 0.5188)). Esas coords son legacy NO canonicas:
ningun modulo nuevo las hardcodea. La entrada termina en
Treasure resolved + Gold Keys ready + fresh currency evidence
(``check_gold_ready`` + primer ``read_state`` fresco). HIL A debe
validar tap + llegada + retorno; sin HIL no se afirma navegacion.
No scroll en ningun camino (imports probados en tests).

Equipment separation: este modulo no importa ni consulta Equipment,
Combine, Relief, Inventory ni Craft; equipment-full nunca bloquea
(tests de separacion). Routing separation: cero imports Trading,
OUTPUT_FULL consumer, planner, MW, stages, scroll/swipe/gestos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math
import time
from numbers import Integral, Real


GOLD_KEY_KIND = "gold_key"

GOLD_ALLOWED_CURRENCY_KINDS = frozenset({GOLD_KEY_KIND})


class TreasureOutcome(str, Enum):
    """Small descriptive taxonomy for one bounded Gold Keys opening."""

    SUCCESS = "success"
    NO_KEYS = "no_keys"
    PREMIUM_CURRENCY_BOUNDARY = "premium_currency_boundary"
    NO_EFFECT = "no_effect"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"


class GoldKeyQuantityMode(str, Enum):
    """What the caller asks the Treasure capability to open."""

    OPEN_ONCE = "open_once"
    EXACT = "exact"
    UP_TO = "up_to"
    MAX_WITHIN_BUDGET = "max_within_budget"


@dataclass(frozen=True)
class GoldKeyQuantity:
    """Explicit bounded intent; never 'empty everything' by default.

    ``OPEN_ONCE``/``MAX_WITHIN_BUDGET`` carry no amount (one verified
    opening vs as many as ``max_actions``/boundary allow).
    ``EXACT``/``UP_TO`` carry a positive ``amount`` of keys. Overshoot
    never confirms: when the fresh ``amount_offered`` (1/10) exceeds the
    remaining need, EXACT fails closed and UP_TO stops with what is
    already verified (or fails closed when nothing was opened).
    """

    mode: GoldKeyQuantityMode
    amount: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, GoldKeyQuantityMode):
            raise ValueError("mode must be GoldKeyQuantityMode")
        if self.mode in (
            GoldKeyQuantityMode.OPEN_ONCE,
            GoldKeyQuantityMode.MAX_WITHIN_BUDGET,
        ):
            if self.amount is not None:
                raise ValueError("open_once/max_within_budget carry no amount")
            return
        if isinstance(self.amount, bool) or not isinstance(
            self.amount, Integral
        ):
            raise ValueError("amount must be a positive integer")
        if int(self.amount) < 1:
            raise ValueError("amount must be a positive integer")
        object.__setattr__(self, "amount", int(self.amount))


@dataclass(frozen=True)
class TreasureCurrencyFact:
    """One fresh read of the Gold Keys currency/selector state.

    ``currency`` is the observed kind (``"gold_key"`` allowed;
    ``"karat"`` or any other premium string is a premium boundary;
    ``"empty"`` is positively observed no-keys; ``"unknown"`` is
    unreadable/contradictory and never authorizes input).
    ``amount_offered`` is 1/10 when gold (Astra contract; any other
    value is a redesign stop, not a heuristic), else None.
    ``count`` is the readable Gold Key balance or None when
    illegible (never zero by default). ``overlay`` names the observed
    surface (``"selector"``/``"result"`` expected) or None when
    unreadable. ``sequence`` shares the capture-sequence domain with
    the authorizing snapshot and must strictly increase per read
    (logical ordering/dedup only, never physical age: the decode
    counter advances at video rate while reads sample at analyze
    cadence). ``observed_at`` is the monotonic capture timestamp of
    the frame this fact was read from (``time.monotonic`` domain from
    Capture through Observation into the snapshot; builders copy it,
    readers must never stamp it with "now"). A fact without a valid
    ``observed_at`` never authorizes input (fail-closed).
    """

    currency: str
    amount_offered: int | None
    count: int | None
    overlay: str | None
    sequence: int
    observed_at: float | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("currency must be a non-empty string")
        object.__setattr__(self, "currency", self.currency.strip())
        if self.currency == GOLD_KEY_KIND:
            if self.amount_offered not in (1, 10):
                raise ValueError("gold_key amount_offered must be 1 or 10")
        else:
            if self.amount_offered is not None:
                raise ValueError("non-gold amount_offered must be None")
        if self.count is not None:
            if isinstance(self.count, bool) or not isinstance(
                self.count, Integral
            ):
                raise ValueError("count must be an integer or None")
            if int(self.count) < 0:
                raise ValueError("count must be non-negative")
            object.__setattr__(self, "count", int(self.count))
        if self.overlay is not None and (
            not isinstance(self.overlay, str) or not self.overlay.strip()
        ):
            raise ValueError("overlay must be a non-empty string or None")
        if isinstance(self.overlay, str):
            object.__setattr__(self, "overlay", self.overlay.strip())
        if isinstance(self.sequence, bool) or not isinstance(
            self.sequence, Integral
        ):
            raise ValueError("sequence must be an integer")
        object.__setattr__(self, "sequence", int(self.sequence))
        if self.observed_at is not None:
            if isinstance(self.observed_at, bool) or not isinstance(
                self.observed_at, Real
            ):
                raise ValueError("observed_at must be a real number or None")
            observed = float(self.observed_at)
            if not math.isfinite(observed) or observed < 0.0:
                raise ValueError("observed_at must be a non-negative finite time")
            object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


@dataclass(frozen=True)
class TreasureOpenTargets:
    """Caller-supplied normalized open points; no defaults.

    HIL-UNCALIBRATED: Astra points disagree with the current UI until
    HIL B/C measure them. The capability never invents a coordinate.
    ``open_single_point`` taps the amount-1 control, ``open_repeat_point``
    the amount-10 control observed on the fresh currency fact.
    """

    open_single_point: tuple[float, float]
    open_repeat_point: tuple[float, float]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "open_single_point",
            _require_point(self.open_single_point, "open_single_point"),
        )
        object.__setattr__(
            self,
            "open_repeat_point",
            _require_point(self.open_repeat_point, "open_repeat_point"),
        )


@dataclass(frozen=True)
class GoldKeyOpenRequest:
    """Already-decided bounded intention for Gold Keys.

    ``allowed_currency_kinds`` is fixed to exactly ``{"gold_key"}``:
    any premium must never be added by inference. ``max_actions``
    bounds taps (no hidden loop).     ``max_fact_age_s`` bounds the first
    currency read against the authorizing snapshot in seconds of frame
    capture time (``barrier_ts < fact.observed_at <= barrier_ts +
    max_fact_age_s``), never in decode-counter sequences.
    ``post_action_timeout_s`` bounds the observation window after each
    single tap: the game animation outlives one poll (HIL E2.1 showed
    the selector popup still up ~0.9s after the tap and the result at
    ~3-3.5s on two nights), so fresh reads are polled until
    consumption/result evidence, a boundary, cancellation, or this
    deadline. 5.0s covers ~1.4x the observed latency with a small
    margin for device load; far below any blind-retry scale.
    ``post_action_max_polls`` is a pure safety net against a broken
    clock and must never bind in practice: live polls run ~50ms
    (measured 2026-09-18: 48 polls in ~2.5s truncated the window
    before the ~3.5s result), so the count sits at 1000 and the
    deadline always governs. The economic input is emitted exactly
    once per iteration either way: the window only observes.
    ``source`` /
    ``return_to`` are descriptive contracts only (this module never
    navigates): entry must have ended in Treasure ready and return is
    verified externally from ``GoldKeyOpenResult.after``.
    """

    quantity: GoldKeyQuantity
    allowed_currency_kinds: frozenset[str]
    targets: TreasureOpenTargets | None = None
    max_actions: int = 10
    max_fact_age_s: float = 2.0
    post_action_timeout_s: float = 5.0
    post_action_max_polls: int = 1000
    source: str = "lobby"
    return_to: str | None = "lobby"

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, GoldKeyQuantity):
            raise ValueError("quantity must be GoldKeyQuantity")
        try:
            kinds = frozenset(self.allowed_currency_kinds)
        except TypeError as error:
            raise ValueError(
                "allowed_currency_kinds must be a collection of strings"
            ) from error
        if kinds != GOLD_ALLOWED_CURRENCY_KINDS:
            raise ValueError('allowed_currency_kinds must be exactly {"gold_key"}')
        object.__setattr__(self, "allowed_currency_kinds", kinds)
        if self.targets is not None and not isinstance(self.targets, TreasureOpenTargets):
            raise ValueError("targets must be TreasureOpenTargets or None")
        if (
            isinstance(self.max_actions, bool)
            or not isinstance(self.max_actions, Integral)
            or int(self.max_actions) < 1
        ):
            raise ValueError("max_actions must be a positive integer")
        object.__setattr__(self, "max_actions", int(self.max_actions))
        if (
            isinstance(self.max_fact_age_s, bool)
            or not isinstance(self.max_fact_age_s, Real)
            or not math.isfinite(float(self.max_fact_age_s))
            or float(self.max_fact_age_s) < 0.0
        ):
            raise ValueError("max_fact_age_s must be a non-negative duration")
        object.__setattr__(self, "max_fact_age_s", float(self.max_fact_age_s))
        if (
            isinstance(self.post_action_timeout_s, bool)
            or not isinstance(self.post_action_timeout_s, Real)
            or not math.isfinite(float(self.post_action_timeout_s))
            or float(self.post_action_timeout_s) < 0.0
        ):
            raise ValueError(
                "post_action_timeout_s must be a non-negative duration"
            )
        object.__setattr__(
            self, "post_action_timeout_s", float(self.post_action_timeout_s)
        )
        if (
            isinstance(self.post_action_max_polls, bool)
            or not isinstance(self.post_action_max_polls, Integral)
            or int(self.post_action_max_polls) < 1
        ):
            raise ValueError("post_action_max_polls must be a positive integer")
        object.__setattr__(
            self, "post_action_max_polls", int(self.post_action_max_polls)
        )
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        object.__setattr__(self, "source", self.source.strip())
        if self.return_to is not None and (
            not isinstance(self.return_to, str) or not self.return_to.strip()
        ):
            raise ValueError("return_to must be a non-empty string or None")
        if isinstance(self.return_to, str):
            object.__setattr__(self, "return_to", self.return_to.strip())


@dataclass(frozen=True)
class GoldKeyOpenResult:
    """Descriptive outcome; never a routing decision."""

    outcome: TreasureOutcome
    before: TreasureCurrencyFact | None
    after: TreasureCurrencyFact | None = None
    opened: int = 0
    boundary: str | None = None
    reason: str | None = None
    inputs: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, TreasureOutcome):
            raise ValueError("outcome must be TreasureOutcome")
        if self.before is not None and not isinstance(
            self.before, TreasureCurrencyFact
        ):
            raise ValueError("before must be TreasureCurrencyFact or None")
        if self.after is not None and not isinstance(
            self.after, TreasureCurrencyFact
        ):
            raise ValueError("after must be TreasureCurrencyFact or None")
        if (
            isinstance(self.opened, bool)
            or not isinstance(self.opened, Integral)
            or int(self.opened) < 0
        ):
            raise ValueError("opened must be a non-negative integer")
        object.__setattr__(self, "opened", int(self.opened))
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


def check_gold_ready(snapshot) -> str | None:
    """Return None when Treasure authorizes an open, else a reason.

    Pure and input-free. Reuses ``bot.treasure_center`` predicates:
    Treasure resolved, clean, positive Gold signal, no Karat
    contradiction. ``UNKNOWN``/``AMBIGUOUS``/foreign/contradictory
    never authorize input. No scroll, no wait, no fallback lives here.
    """
    from bot.state import ResolutionStatus
    from bot.treasure_center import (
        clean_treasure,
        has_gold_signal,
        has_karat_signal,
        is_treasure_screen,
    )

    status = getattr(getattr(snapshot, "state", None), "status", None)
    if status is ResolutionStatus.UNKNOWN:
        return "unknown_state"
    if status is ResolutionStatus.AMBIGUOUS:
        return "ambiguous_state"
    if not is_treasure_screen(snapshot):
        return "not_treasure"
    if getattr(snapshot.state, "overlays", ()):
        if not clean_treasure(snapshot):
            return "overlays_present"
    gold = has_gold_signal(snapshot)
    karat = has_karat_signal(snapshot)
    if gold and karat:
        return "contradictory_state"
    if not gold:
        return "gold_not_ready"
    if not clean_treasure(snapshot):
        return "overlays_present"
    return None


def is_gold_ready(snapshot) -> bool:
    """Return True only when :func:`check_gold_ready` passes."""
    return check_gold_ready(snapshot) is None


def check_currency(
    fact: TreasureCurrencyFact | None,
    allowed: frozenset[str],
) -> str | None:
    """Return None when the fresh fact authorizes a tap, else a reason."""
    if fact is None or not isinstance(fact, TreasureCurrencyFact):
        return "unreadable_currency"
    if fact.currency not in allowed:
        if fact.currency == "empty":
            return "no_keys"
        if fact.currency == "unknown":
            return "unreadable_currency"
        return "premium_currency"
    return None


def check_fact_fresh(
    fact: TreasureCurrencyFact | None,
    barrier_ts: float,
    max_age_s: float,
) -> str | None:
    """Return None when the fact is physically fresh, else ``"stale_fact"``.

    Pure physical-freshness gate over frame capture timestamps
    (``time.monotonic`` domain from Capture; no reader clock involved,
    so a reader can never manufacture freshness): the fact must carry
    a valid ``observed_at`` strictly newer than the causal ``barrier_ts``
    (the authorizing transition's snapshot timestamp) and within
    ``max_age_s`` seconds after it. Sequence is deliberately not
    consulted here: the decode counter advances at video rate while
    reads sample at analyze cadence, so a sequence gap measures
    pipeline latency, not content age (HIL 2026-09-18 Smoke B).
    """
    if (
        isinstance(barrier_ts, bool)
        or not isinstance(barrier_ts, Real)
        or not math.isfinite(float(barrier_ts))
        or float(barrier_ts) < 0.0
    ):
        raise ValueError("barrier_ts must be a non-negative finite time")
    if (
        isinstance(max_age_s, bool)
        or not isinstance(max_age_s, Real)
        or not math.isfinite(float(max_age_s))
        or float(max_age_s) < 0.0
    ):
        raise ValueError("max_age_s must be a non-negative finite duration")
    if fact is None or not isinstance(fact, TreasureCurrencyFact):
        return "stale_fact"
    observed = fact.observed_at
    if (
        observed is None
        or isinstance(observed, bool)
        or not isinstance(observed, Real)
    ):
        return "stale_fact"
    if float(observed) <= float(barrier_ts):
        return "stale_fact"
    if float(observed) - float(barrier_ts) > float(max_age_s):
        return "stale_fact"
    return None


def execute_gold_key_open(
    *,
    snapshot,
    request: GoldKeyOpenRequest,
    tap: Callable[[tuple[float, float]], None] | None,
    read_state: Callable[[], TreasureCurrencyFact | None],
    act: Callable[[object], None] | None = None,
    cancel_requested: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] | None = None,
) -> GoldKeyOpenResult:
    """Execute one bounded Gold Keys opening; single causal tap per open.

    Injected I/O only: production ``act`` emits typed ActionExecutor intents;
    legacy ``tap`` performs one normalized tap per call.
    ``read_state`` returns a fresh ``TreasureCurrencyFact`` or None. No
    navigation, no retry, no double inputs: each iteration reads fresh
    currency, taps at most once (single for 1, repeat for 10), then
    observes the bounded post-action window for consumption evidence.
    Any abort before a tap performs zero further input (still zero
    spend). Premium currency stops before confirm with zero additional
    taps. Equipment state is never consulted; Trading is never touched.
    ``clock`` (monotonic, ``time.monotonic`` by default) bounds the
    post-action window only; freshness itself comes from frame capture
    timestamps, never from this clock.
    """
    if not isinstance(request, GoldKeyOpenRequest):
        raise ValueError("request must be GoldKeyOpenRequest")
    if callable(tap) == callable(act) or not callable(read_state):
        raise ValueError("exactly one input callback and read_state are required")
    if tap is not None and request.targets is None:
        raise ValueError("legacy tap requires targets")
    if not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")
    if clock is not None and not callable(clock):
        raise ValueError("clock must be callable or None")
    now = clock if clock is not None else time.monotonic
    try:
        barrier_ts = float(snapshot.timestamp)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(
            "snapshot must expose a numeric capture timestamp"
        ) from error

    def _cancelled() -> bool:
        try:
            return cancel_requested() is True
        except Exception:
            return False

    if _cancelled():
        return GoldKeyOpenResult(
            outcome=TreasureOutcome.CANCELLED,
            before=None,
            reason="user_cancelled",
            evidence=("cancel_before_input",),
        )

    ready_reason = check_gold_ready(snapshot)
    if ready_reason is not None:
        return GoldKeyOpenResult(
            outcome=TreasureOutcome.FAILED,
            before=None,
            reason=ready_reason,
            evidence=(f"readiness:{ready_reason}",),
        )

    allowed = request.allowed_currency_kinds
    quantity = request.quantity
    targets = request.targets
    inputs: list[str] = []
    evidence: list[str] = [f"source:{request.source}"]
    before_first: TreasureCurrencyFact | None = None
    after_last: TreasureCurrencyFact | None = None
    opened = 0
    actions = 0

    def _target_total() -> int | None:
        if quantity.mode in (
            GoldKeyQuantityMode.OPEN_ONCE,
            GoldKeyQuantityMode.MAX_WITHIN_BUDGET,
        ):
            return None
        assert quantity.amount is not None
        return int(quantity.amount)

    def _satisfied() -> bool:
        total = _target_total()
        if quantity.mode is GoldKeyQuantityMode.OPEN_ONCE:
            return actions >= 1 and opened > 0
        if quantity.mode is GoldKeyQuantityMode.MAX_WITHIN_BUDGET:
            return False
        assert total is not None
        return opened == total

    target_total = _target_total()

    while actions < request.max_actions:
        if _cancelled():
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.CANCELLED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason="user_cancelled",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "user_cancelled"]),
            )
        if _satisfied():
            break
        try:
            before = read_state()
        except Exception:
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason="read_failed_before",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "read_failed_before"]),
            )
        if before is None or not isinstance(before, TreasureCurrencyFact):
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason="unreadable_currency",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "unreadable_currency"]),
            )
        if before_first is None:
            before_first = before
            if (
                check_fact_fresh(
                    before, barrier_ts, request.max_fact_age_s
                )
                is not None
            ):
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.FAILED,
                    before=before_first,
                    reason="stale_fact",
                    evidence=tuple([*evidence, "stale_fact"]),
                )
            evidence.append(
                f"before:{before.currency}/{before.amount_offered}"
            )
        else:
            assert after_last is not None
            if before.sequence <= after_last.sequence:
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.FAILED,
                    before=before_first,
                    after=after_last,
                    opened=opened,
                    reason="stale_currency",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "stale_currency"]),
                )

        currency_reason = check_currency(before, allowed)
        if currency_reason == "no_keys":
            if opened == 0:
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.NO_KEYS,
                    before=before_first,
                    after=before,
                    opened=0,
                    boundary="no_keys",
                    reason="no_keys_observed",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "boundary:no_keys"]),
                )
            if quantity.mode is GoldKeyQuantityMode.EXACT:
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.FAILED,
                    before=before_first,
                    after=before,
                    opened=opened,
                    boundary="no_keys",
                    reason="incomplete_exact",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "boundary:no_keys"]),
                )
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.SUCCESS,
                before=before_first,
                after=before,
                opened=opened,
                boundary="no_keys",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "boundary:no_keys"]),
            )
        if currency_reason == "premium_currency":
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.PREMIUM_CURRENCY_BOUNDARY,
                before=before_first,
                after=before,
                opened=opened,
                boundary="premium_currency",
                reason="premium_before_confirm",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "boundary:premium_currency"]),
            )
        if currency_reason is not None:
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason=currency_reason,
                inputs=tuple(inputs),
                evidence=tuple([*evidence, currency_reason]),
            )

        assert before.currency == GOLD_KEY_KIND
        offered = int(before.amount_offered or 0)
        if offered not in (1, 10):
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason="unreadable_currency",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "unreadable_currency"]),
            )
        if target_total is not None:
            remaining = int(target_total) - opened
            if offered > remaining:
                if quantity.mode is GoldKeyQuantityMode.EXACT:
                    return GoldKeyOpenResult(
                        outcome=TreasureOutcome.FAILED,
                        before=before_first,
                        after=after_last,
                        opened=opened,
                        reason="impossible_amount",
                        inputs=tuple(inputs),
                        evidence=tuple(
                            [*evidence, f"impossible_amount:offered={offered}"]
                        ),
                    )
                if opened == 0:
                    return GoldKeyOpenResult(
                        outcome=TreasureOutcome.FAILED,
                        before=before_first,
                        after=after_last,
                        opened=opened,
                        reason="impossible_amount",
                        inputs=tuple(inputs),
                        evidence=tuple(
                            [*evidence, f"impossible_amount:offered={offered}"]
                        ),
                    )
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.SUCCESS,
                    before=before_first,
                    after=after_last,
                    opened=opened,
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "capped_before_overshoot"]),
                )

        try:
            if act is not None:
                from bot.semantic_actions import (
                    ConfirmRepeatGoldOpen, ConfirmSingleGoldOpen,
                )
                act(ConfirmSingleGoldOpen() if offered == 1 else ConfirmRepeatGoldOpen())
            else:
                point = (
                    targets.open_single_point if offered == 1
                    else targets.open_repeat_point
                )
                tap(point)
        except Exception as error:
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason=f"tap_failed:{type(error).__name__}",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "tap_failed"]),
            )
        inputs.append(
            "tap_open_single" if offered == 1 else "tap_open_repeat"
        )
        actions += 1

        # Bounded post-action window (HIL E2.1 2026-09-18): the game
        # animation outlives a single poll (selector popup still up
        # ~0.9s after the tap, result only later), so fresh reads are
        # polled until consumption/result evidence, a boundary, user
        # cancel, or the deadline/poll bound. The economic input above
        # is never repeated here: exactly one tap per iteration.
        tap_barrier = before.observed_at  # valid: first-fact gate
        if (
            tap_barrier is None
            or isinstance(tap_barrier, bool)
            or not isinstance(tap_barrier, Real)
        ):
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.FAILED,
                before=before_first,
                after=after_last,
                opened=opened,
                reason="stale_fact",
                inputs=tuple(inputs),
                evidence=tuple([*evidence, "stale_fact"]),
            )
        tap_barrier = float(tap_barrier)
        deadline = now() + request.post_action_timeout_s
        polls = 0
        after: TreasureCurrencyFact | None = None
        last_usable: TreasureCurrencyFact | None = None
        while True:
            if _cancelled():
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.CANCELLED,
                    before=before_first,
                    after=after_last,
                    opened=opened,
                    reason="user_cancelled",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "user_cancelled"]),
                )
            if polls >= request.post_action_max_polls or now() > deadline:
                break
            polls += 1
            try:
                candidate = read_state()
            except Exception:
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.FAILED,
                    before=before_first,
                    after=after_last,
                    opened=opened,
                    reason="read_failed_after",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "read_failed_after"]),
                )
            if candidate is None or not isinstance(
                candidate, TreasureCurrencyFact
            ):
                continue
            observed = candidate.observed_at
            if (
                observed is None
                or isinstance(observed, bool)
                or not isinstance(observed, Real)
                or float(observed) <= tap_barrier
                or candidate.sequence <= before.sequence
            ):
                # Pre-tap, resampled, or unreadable frame: no evidence
                # yet, never a failure and never a new tap.
                continue
            last_usable = candidate
            if before.count is not None and candidate.count is not None:
                if candidate.count < before.count:
                    after = candidate
                    break
                if candidate.count == before.count:
                    continue
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.FAILED,
                    before=before_first,
                    after=candidate,
                    opened=opened,
                    reason="incoherent_count",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "incoherent_count"]),
                )
            if (
                candidate.currency == "unknown"
                or candidate.overlay is None
            ):
                continue
            if (
                candidate.overlay == before.overlay
                and candidate.currency == before.currency
            ):
                continue
            if candidate.overlay == "result" and candidate.currency in (
                "gold_key",
                "empty",
                "karat",
            ):
                after = candidate
                break
            if candidate.currency in ("empty", "karat") and (
                candidate.currency != before.currency
            ):
                after = candidate
                break
            continue

        if after is None:
            if (
                last_usable is not None
                and last_usable.overlay == before.overlay
                and last_usable.currency == before.currency
            ):
                reason = "state_unchanged"
            else:
                reason = "no_evidence"
            return GoldKeyOpenResult(
                outcome=TreasureOutcome.NO_EFFECT,
                before=before_first,
                after=last_usable if last_usable is not None else after_last,
                opened=opened,
                reason=reason,
                inputs=tuple(inputs),
                evidence=tuple([*evidence, reason]),
            )
        after_last = after

        consumed: int | None = None
        if before.count is not None and after.count is not None:
            consumed = int(before.count) - int(after.count)
            assert consumed >= 1
        else:
            consumed = offered

        assert consumed is not None and consumed >= 1
        opened += int(consumed)
        evidence.append(f"consumed:{consumed}")
        if quantity.mode is GoldKeyQuantityMode.EXACT and target_total is not None:
            if opened > int(target_total):
                return GoldKeyOpenResult(
                    outcome=TreasureOutcome.FAILED,
                    before=before_first,
                    after=after,
                    opened=opened,
                    reason="over_consumed",
                    inputs=tuple(inputs),
                    evidence=tuple([*evidence, "over_consumed"]),
                )
        if _satisfied():
            break

    if _satisfied() or (
        quantity.mode is GoldKeyQuantityMode.MAX_WITHIN_BUDGET and opened > 0
    ):
        boundary = None
        if after_last is not None and after_last.currency in (
            "empty",
            "karat",
        ):
            boundary = (
                "no_keys"
                if after_last.currency == "empty"
                else "premium_currency"
            )
        return GoldKeyOpenResult(
            outcome=TreasureOutcome.SUCCESS,
            before=before_first,
            after=after_last,
            opened=opened,
            boundary=boundary,
            inputs=tuple(inputs),
            evidence=tuple([*evidence, f"after_opened:{opened}"]),
        )
    if actions >= request.max_actions:
        return GoldKeyOpenResult(
            outcome=TreasureOutcome.BUDGET_EXHAUSTED,
            before=before_first,
            after=after_last,
            opened=opened,
            boundary="budget_exhausted",
            reason="budget_exhausted",
            inputs=tuple(inputs),
            evidence=tuple([*evidence, "boundary:budget_exhausted"]),
        )
    return GoldKeyOpenResult(
        outcome=TreasureOutcome.FAILED,
        before=before_first,
        after=after_last,
        opened=opened,
        reason="unsatisfied_without_boundary",
        inputs=tuple(inputs),
        evidence=tuple([*evidence, "unsatisfied_without_boundary"]),
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
    "GOLD_ALLOWED_CURRENCY_KINDS",
    "GOLD_KEY_KIND",
    "GoldKeyOpenRequest",
    "GoldKeyOpenResult",
    "GoldKeyQuantity",
    "GoldKeyQuantityMode",
    "TreasureCurrencyFact",
    "TreasureOpenTargets",
    "TreasureOutcome",
    "check_currency",
    "check_fact_fresh",
    "check_gold_ready",
    "execute_gold_key_open",
    "is_gold_ready",
)
