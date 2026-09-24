"""Fast Gold Keys drain primitive (E2.2, Treasure-only).

Treasure-specific rapid drain over an already-opened repeat state. The
caller owns entry (Lobby -> Treasure -> first verified open via the E2
path) and return; this module only taps the RIGHT Gold button fast
while it stays Gold-backed, then classifies the boundary.

Semantics (amount-agnostic, no OCR of the number):

- ``RIGHT_GOLD_OPEN_MAX`` (``has_right_gold_open_max``): right button
  actionable and Gold-backed, opening whatever maximum the UI offers
  (1..10). The ``10``/``7``/``1`` label is never read.
- ``RIGHT_KARAT_OPEN`` (``has_right_karat_open``): same right-button
  role backed by Karats/premium. Normal termination, zero taps.
- Gold+Karat together: contradiction, zero input, fail closed.
- The LEFT ``1(Open)`` control is never a drain target.
- While Gold is actionable, the only input is the calibrated
  right-button point. The final outside tap belongs exclusively to the
  post-Karat animation finalizer.

Reward transient (``TREASURE_GOLD_REWARD_ACTIVE``, local only):

- HIL Round A proved the right button stays actionable through the
  reward animation/grid: one tap on ``10(Open)`` consumed a batch of 10
  (318->308) while the 10-reward grid covered the Treasure title, so
  the snapshot resolves UNKNOWN and the title-gated detector emits
  nothing. The bar pills stay Gold-backed in pixels
  (``bar_repeat_gold == bar_single_gold == 1.0``, every karat ``0.0``).
- The grid is therefore a KNOWN post-open transient of the same
  operation, never context loss and never a dismiss request. While it
  lasts, the same right button is the only correct target: a tap may
  cut/accelerate the animation or start the next batch (dual role, no
  a-priori labeling, never counted as opened batches).
- Local source contract (deliberately local, never globalized): after
  the verified entry, any fresh frame is drain-actionable when the
  title-independent local reading shows pair Gold (popup single+repeat
  or bar single+repeat icon gold) with zero Karat anywhere, no strong
  foreign base, and a timestamp newer than the previous input's frame.
  Sensing reuses ``TreasureContentDetector.measure`` ROIs/thresholds
  exactly (no new detector, no manifest, no evaluator); the caller
  injects it as ``measure_local`` (``None`` disables the transient
  path). Causal lineage (verified entry, no boundary seen) replaces the
  title gate; the watchdog's visual-progress bound caps residual
  foreign-pixel risk to ``watchdog_every`` inputs.

UI audit (E/E2/E2.1 raws, 2026-09-17/18 + Round A HIL):

- selector popup (initial): center overlay, right button bbox approx
  x 0.650-0.730 / y 0.395-0.565, point (0.693, 0.540) geometrically
  calibrated from the B1 popup (``TREASURE_PROFILE.repeat_point``).
  C2b HIL verified one 10(Open) selector tap (45->35 Gold Keys).
- result overlay (repeat): bottom bar, right icon ROI x 0.305-0.365 /
  y 0.78-0.86, centroid (0.335, 0.82). Different position from the
  selector popup: the target is resolved per snapshot/reading
  (result/bar-side -> bar, else selector). Bar tap HIL PASS (1 tap =
  1 batch-10, 318->308, cero premium).
- detector split: popup repeat needs the ``10(Open)`` label yellow +
  icon gold; bar repeat needs only the icon gold under a result gate.
  ``1..9`` right-button popup variants are therefore HIL_PENDING: the
  local pair-Gold reading already ignores the number, live 7/1 variants
  still pending.
- batch-10 reward grid: title occluded (UNKNOWN), bar pills Gold 1.0,
  karats 0.0, persistent without taps. Known transient, not loss.

Loop (fast path, no result wait per tap, no full scope per cycle):

- one fresh observation per tap decision (``observed_at`` strictly
  newer than the observation used for the previous input; resamples
  are skipped with zero input, never a second tap on one frame);
- ``tap_interval_s`` (default 0.15, HIL-stable) cadence slots via injected
  clock/sleeper (no busy loop);
- full watchdog every ``watchdog_every`` inputs (default 10): healthy
  states are (A) title Treasure + observed Gold, (B) known reward grid
  + local pair Gold, (C) known repeat overlay + observed Gold; any of
  them sustains the drain. Hidden title alone never stalls and never
  loses context. Verified: coherent right-button semantics, Gold/Karat
  split, fresh observations, no strong foreign, plus per-tap change
  marks (ROI fingerprint + observation names over the animation/result
  area): STALL_SUSPECTED only when no tap of the window changed
  anything observable, then stop touching. State churn between
  observed and transient frames is progress, so one static ROI alone
  never stalls a working loop;
- right Gold gone (observed and local) -> stop inputs immediately ->
  bounded classify: RIGHT_KARAT_OPEN (no Gold anywhere) leaves the fast
  loop with zero premium taps and runs the finalize: exactly the
  post-Karat contract below; otherwise bounded reobserve, fail closed
  on timeout. UNKNOWN without any positive right-button signal: zero
  input.

Post-Karat finalize (never while Gold remains, never between batches):

- on fresh RIGHT_KARAT_OPEN: latch ``gold_exhausted`` irreversibly,
  permanently blocking every right-button input of this drain, with
  zero Karat taps, and leave the fast loop. Stale Gold sightings
  after the latch never reactivate the loop; watchdogs and resumes
  cannot touch the right button either. The existing
  ``TapThroughAnimation`` primitive then owns the final reward
  animation only: ``DismissTreasureResult`` resolves the
  profile-owned safe lateral point, and each bounded tap is
  authorized under the latched lineage by the reward signal
  itself -- a fresh semantic result, or a positive
  title-independent local reward reading (``local_reward_present``:
  the glowing chest stays pixel-visible while the overlay covers
  the title, so base UNKNOWN never blocks a tap while reward is
  locally positive). Karat armed the latch and need not stay
  visible per tap; the title need not be visible either.
  ``TapThroughAnimation`` runs with its normal policy repeating
  lateral taps until the overlay is gone;
  ``dismiss_no_effect`` still fails closed, never silent SUCCESS.
- ``GOLD_KEYS_EXHAUSTED`` requires the dismiss postcondition: a
  posterior fresh snapshot must show Treasure stable, no reward
  result and no RIGHT_GOLD_OPEN_MAX. An isolated selector signal does
  not mean that the right economic control returned. If this stable
  state is already present at the Karat boundary, the postcondition
  holds with zero dismiss taps. RIGHT_GOLD_OPEN_MAX reappearing
  mid-finalize resolves INCOMPATIBLE_STATE: stop at once, no second
  outside tap.
- telemetry split: ``inputs_emitted`` (right button only) vs
  ``dismiss_inputs`` (finalize only).

Safety is a fuse, never policy: ``safety_deadline_s`` (default 300s)
plus a very high ``max_inputs`` technical fuse (default 10000). Tap
count never decides success and ``inputs_emitted`` is never reported
as opened batches (one tap may just cut an animation; the next starts
the next open).

No Trading/C6a/C6b/Craft/Relief/MW/planner/stage/scroll/ADB coupling:
``observe``/``tap``/``target`` are injected; separation is tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time
from numbers import Real

from bot.semantic_actions import (
    ConfirmRepeatGoldOpen, ContinueGoldDrainFromResult, DismissTreasureResult,
)
from bot.state import ResolutionStatus
from bot.tap_through_animation import TapThroughOutcome, TapThroughPolicy
from bot.treasure_center import (
    clean_treasure,
    has_gold_signal,
    has_karat_signal,
    has_local_reward_transient,
    has_result,
    has_right_button_contradiction,
    has_right_gold_open_max,
    has_right_karat_open,
    has_selector_popup,
    is_treasure_screen,
)
from bot.treasure_profile import RESULT_BAR_GOLD_POINT, TREASURE_PROFILE

#: Selector-popup right-button point (B1 geometry; repeat tap pending HIL).
SELECTOR_REPEAT_POINT: tuple[float, float] = TREASURE_PROFILE.repeat_point

#: Result bottom-bar right-button point: centroid of the bar repeat icon
#: ROI x 0.305-0.365 / y 0.78-0.86 (``TREASURE_BAR_REPEAT_ICON_REGION``).
#: Prior E2.2 drain HIL exercised the result-bar right Gold control.
BAR_REPEAT_POINT: tuple[float, float] = RESULT_BAR_GOLD_POINT

#: Animation/result ROI for the visual-progress fingerprint
#: (``TREASURE_RESULT_REGION`` provenance; numpy-only, no detector).
RESULT_FINGERPRINT_REGION: tuple[float, float, float, float] = (
    0.42,
    0.55,
    0.60,
    0.80,
)

#: Compatibility alias for the profile-owned safe lateral dismiss point.
#: Recalibrated 2026-09-18 from the live Karat reward overlay
#: (``artifacts/hil_e2_fastdrain/20260918T204217/dry_000.png``):
#: (0.08, 0.65) sits in the left dark corridor, outside the bottom
#: bar (x 0.148-0.568 / y 0.700-0.933), the reward grid and every
#: button bbox. The earlier user-approximated point lay inside the
#: reward grid and proved ``dismiss_no_effect`` on the productive path.
#: NEVER used while RIGHT_GOLD_OPEN_MAX exists.
DISMISS_POINT: tuple[float, float] = TREASURE_PROFILE.dismiss_point

#: Local pair-Gold confidence threshold for the reward-transient path.
#: Same contract as the detector's composite gate
#: (``TREASURE_CONTENT_CONFIDENCE_THRESHOLD`` in
#: ``bot.perception.treasure_center``); kept as a literal with provenance
#: so this module never imports the perception engine.
REWARD_TRANSIENT_GOLD_THRESHOLD: float = 0.50

#: Local sides for the dual-role right-button tap.
LOCAL_SIDE_POPUP: str = "popup"
LOCAL_SIDE_BAR: str = "bar"


class GoldKeyDrainOutcome(str, Enum):
    """Terminal taxonomy for one fast-drain visit (no routing meaning)."""

    GOLD_KEYS_EXHAUSTED = "gold_keys_exhausted"
    STALL_SUSPECTED = "stall_suspected"
    CONTEXT_LOST = "context_lost"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SAFETY_DEADLINE = "safety_deadline"


@dataclass(frozen=True)
class GoldKeyDrainConfig:
    """Explicit fast-loop tuning; no hidden policy.

    ``tap_interval_s`` is the minimum spacing between inputs (0.15:
    HIL Round B measured stable with zero loss/mis-taps; 0.20 Round A
    equivalent, both floor-bound by ~0.22s analyze+tap overhead, so
    0.10 adds queue risk for no gain).
    ``watchdog_every`` counts inputs between full watchdogs.
    ``safety_deadline_s`` is a generous fuse, not success criteria.
    ``max_inputs`` is a very high technical fuse, never a batch plan.
    ``transient_wait_s`` bounds the reappearance wait after the Gold
    button disappears while other Gold is still visible.
    ``reward_transient`` enables the local reward-grid contract (taps on
    title-independent pair-Gold frames after the verified entry);
    ``False`` restores the strict observed-only behavior.
    The post-Karat finalize uses ``TapThroughAnimation`` normal bounds.
    """

    tap_interval_s: float = 0.15
    watchdog_every: int = 10
    safety_deadline_s: float = 300.0
    max_inputs: int = 10000
    transient_wait_s: float = 5.0
    reward_transient: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.tap_interval_s, bool)
            or not isinstance(self.tap_interval_s, Real)
            or not 0.0 < float(self.tap_interval_s) <= 60.0
        ):
            raise ValueError("tap_interval_s must be a duration in (0, 60]")
        object.__setattr__(self, "tap_interval_s", float(self.tap_interval_s))
        if (
            isinstance(self.watchdog_every, bool)
            or not isinstance(self.watchdog_every, int)
            or int(self.watchdog_every) < 1
        ):
            raise ValueError("watchdog_every must be a positive integer")
        object.__setattr__(self, "watchdog_every", int(self.watchdog_every))
        if (
            isinstance(self.safety_deadline_s, bool)
            or not isinstance(self.safety_deadline_s, Real)
            or not float(self.safety_deadline_s) > 0.0
        ):
            raise ValueError("safety_deadline_s must be a positive duration")
        object.__setattr__(
            self, "safety_deadline_s", float(self.safety_deadline_s)
        )
        if (
            isinstance(self.max_inputs, bool)
            or not isinstance(self.max_inputs, int)
            or int(self.max_inputs) < 1
        ):
            raise ValueError("max_inputs must be a positive integer")
        object.__setattr__(self, "max_inputs", int(self.max_inputs))
        if (
            isinstance(self.transient_wait_s, bool)
            or not isinstance(self.transient_wait_s, Real)
            or not 0.0 <= float(self.transient_wait_s) <= 120.0
        ):
            raise ValueError("transient_wait_s must be a duration in [0, 120]")
        object.__setattr__(self, "transient_wait_s", float(self.transient_wait_s))
        if self.reward_transient not in (True, False):
            raise ValueError("reward_transient must be a boolean")
        object.__setattr__(self, "reward_transient", bool(self.reward_transient))


@dataclass(frozen=True)
class GoldKeyDrainResult:
    """Descriptive drain outcome; never a routing decision.

    Counts inputs and boundary sightings only. There is deliberately
    NO opened/batch count: taps are not batches (a tap may only cut an
    animation) and only real evidence could claim an open. Telemetry is
    split: ``inputs_emitted`` counts right-button inputs only;
    ``dismiss_inputs`` counts the post-Karat finalize taps only.
    """

    outcome: GoldKeyDrainOutcome
    inputs_emitted: int = 0
    dismiss_inputs: int = 0
    watchdogs_run: int = 0
    gold_button_observations: int = 0
    karat_boundary_seen: bool = False
    elapsed_s: float = 0.0
    reason: str | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, GoldKeyDrainOutcome):
            raise ValueError("outcome must be GoldKeyDrainOutcome")
        for name in (
            "inputs_emitted",
            "dismiss_inputs",
            "watchdogs_run",
            "gold_button_observations",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if int(value) < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, int(value))
        object.__setattr__(
            self, "karat_boundary_seen", bool(self.karat_boundary_seen)
        )
        if (
            isinstance(self.elapsed_s, bool)
            or not isinstance(self.elapsed_s, Real)
            or float(self.elapsed_s) < 0.0
        ):
            raise ValueError("elapsed_s must be a non-negative duration")
        object.__setattr__(self, "elapsed_s", float(self.elapsed_s))
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValueError("reason must be a string or None")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")


def check_fast_drain_entry(snapshot, *, initial_open_verified: bool) -> str | None:
    """Return None when the fast path may start, else a refusal reason.

    Pure and input-free: Treasure resolved, overlay/result repeat state
    identified, RIGHT_GOLD_OPEN_MAX fresh on this snapshot, no Karat
    contradiction, and the caller-observed initial causal open.
    """
    if initial_open_verified is not True:
        return "entry_not_verified"
    status = getattr(getattr(snapshot, "state", None), "status", None)
    if status is ResolutionStatus.UNKNOWN:
        return "unknown_state"
    if status is ResolutionStatus.AMBIGUOUS:
        return "ambiguous_state"
    if not is_treasure_screen(snapshot):
        return "not_treasure"
    if has_right_button_contradiction(snapshot):
        return "contradictory_state"
    try:
        float(snapshot.timestamp)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return "unreadable_timestamp"
    if not (has_selector_popup(snapshot) or has_result(snapshot)):
        return "no_repeat_state"
    if not has_right_gold_open_max(snapshot):
        if has_right_karat_open(snapshot):
            return "already_karat_boundary"
        return "right_gold_absent"
    return None


def resolve_right_button_target(
    snapshot,
    *,
    repeat_point: tuple[float, float] = SELECTOR_REPEAT_POINT,
    bar_repeat_point: tuple[float, float] = BAR_REPEAT_POINT,
) -> tuple[float, float]:
    """Return the calibrated RIGHT-button point for this snapshot.

    Result overlay -> bottom-bar repeat point; otherwise the selector
    popup repeat point. Never the left ``1(Open)`` control. Both points
    have separate HIL evidence (C2b selector and E2.2 result bar).
    """
    _require_point(repeat_point, "repeat_point")
    _require_point(bar_repeat_point, "bar_repeat_point")
    if has_result(snapshot):
        return (float(bar_repeat_point[0]), float(bar_repeat_point[1]))
    return (float(repeat_point[0]), float(repeat_point[1]))


def local_reward_side(reading) -> str | None:
    """Return the drainable side from a title-independent reading, else None.

    ``TREASURE_GOLD_REWARD_ACTIVE`` in one check: pair Gold on one
    surface (popup single+repeat or bar single+repeat icon gold, same
    0.50 contract as the detector) with zero Karat on every icon ROI.
    False negatives only delay (bounded wait, fail closed); a lone icon
    without its pair never authorizes. ``reading`` is the
    ``TreasureContentDetector.measure`` value (or a test double with
    the same confidence attributes); the title confidence is
    deliberately ignored here because lineage replaces the gate.
    """
    try:
        threshold = float(REWARD_TRANSIENT_GOLD_THRESHOLD)
        popup_single = float(reading.single_gold_confidence)  # type: ignore[attr-defined]
        popup_repeat = float(reading.repeat_gold_confidence)  # type: ignore[attr-defined]
        bar_single = float(reading.bar_single_gold_confidence)  # type: ignore[attr-defined]
        bar_repeat = float(reading.bar_repeat_gold_confidence)  # type: ignore[attr-defined]
        karats = (
            float(reading.single_karat_confidence),  # type: ignore[attr-defined]
            float(reading.repeat_karat_confidence),  # type: ignore[attr-defined]
            float(reading.bar_single_karat_confidence),  # type: ignore[attr-defined]
            float(reading.bar_repeat_karat_confidence),  # type: ignore[attr-defined]
        )
    except (AttributeError, TypeError, ValueError):
        return None
    if any(karat >= threshold for karat in karats):
        return None
    bar_pair = bar_single >= threshold and bar_repeat >= threshold
    popup_pair = popup_single >= threshold and popup_repeat >= threshold
    if bar_pair:
        return LOCAL_SIDE_BAR
    if popup_pair:
        return LOCAL_SIDE_POPUP
    return None


def local_reward_present(reading) -> bool:
    """Title-independent open-reward signal for the finalize taps.

    The glowing open chest (``TREASURE_RESULT_REGION`` provenance)
    stays pixel-visible while the reward overlay covers the title:
    HIL 20260918 measured ``result_confidence`` 1.00 with title 0.00
    on the Karat overlay and 0.00 on the clean grid. Any local Gold
    alongside it is a contradiction here, never a dismiss
    authorization. Same 0.50 contract as the detector composite
    gate; never imports the perception engine.
    """
    try:
        threshold = float(REWARD_TRANSIENT_GOLD_THRESHOLD)
        if float(reading.result_confidence) < threshold:  # type: ignore[attr-defined]
            return False
        golds = (
            float(reading.single_gold_confidence),  # type: ignore[attr-defined]
            float(reading.repeat_gold_confidence),  # type: ignore[attr-defined]
            float(reading.bar_single_gold_confidence),  # type: ignore[attr-defined]
            float(reading.bar_repeat_gold_confidence),  # type: ignore[attr-defined]
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return not any(gold >= threshold for gold in golds)


def local_karat_boundary(reading) -> bool:
    """Return True when the local reading shows premium backing, no Gold.

    Mirrors ``RIGHT_KARAT_OPEN`` without the title: repeat-side Karat
    (popup or bar) with no drainable Gold side and no Gold anywhere
    (any Gold+Karat mix is a contradiction, never a boundary).
    Authorizes zero taps; the caller confirms through resolvable
    observations before reporting exhaustion, and times out fail-closed
    otherwise.
    """
    if local_reward_side(reading) is not None:
        return False
    try:
        threshold = float(REWARD_TRANSIENT_GOLD_THRESHOLD)
        golds = (
            float(reading.single_gold_confidence),  # type: ignore[attr-defined]
            float(reading.repeat_gold_confidence),  # type: ignore[attr-defined]
            float(reading.bar_single_gold_confidence),  # type: ignore[attr-defined]
            float(reading.bar_repeat_gold_confidence),  # type: ignore[attr-defined]
        )
        repeat_karat = float(reading.repeat_karat_confidence)  # type: ignore[attr-defined]
        bar_repeat_karat = float(reading.bar_repeat_karat_confidence)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return False
    if any(gold >= threshold for gold in golds):
        return False
    return repeat_karat >= threshold or bar_repeat_karat >= threshold


def default_progress_fingerprint(snapshot) -> tuple:
    """Cheap visual-progress hash over the animation/result ROI.

    Downsamples the result region to a 4x4 luma grid (numpy only, no
    OCR, no detector). Identical fingerprints across a watchdog window
    mean no visible activity outside the persistent button. Falls back
    to semantic identity when the frame image is unavailable (tests).
    """
    try:
        image = snapshot.frame.image  # type: ignore[attr-defined]
        height, width = image.shape[:2]
        x0, y0, x1, y1 = RESULT_FINGERPRINT_REGION
        region = image[
            int(y0 * height) : int(y1 * height),
            int(x0 * width) : int(x1 * width),
        ]
        if region.size == 0:
            raise ValueError("empty roi")
        import numpy as _np

        small = region.reshape(4, max(1, region.shape[0] // 4), 4, -1).mean(
            axis=(1, 3)
        )
        return ("roi", tuple(int(value // 16) for value in small.flatten()))
    except Exception:
        try:
            names = tuple(
                sorted(
                    observation.name
                    for observation in snapshot.observations.observations  # type: ignore[attr-defined]
                )
            )
        except Exception:
            names = ()
        try:
            overlay = "result" if has_result(snapshot) else (
                "selector" if has_selector_popup(snapshot) else "none"
            )
        except Exception:
            overlay = "none"
        return ("semantic", overlay, names)


def drain_gold_keys_fast(
    *,
    initial_snapshot,
    observe,
    tap,
    act=None,
    config: GoldKeyDrainConfig | None = None,
    target: tuple[float, float] | None = None,
    target_for=None,
    repeat_point: tuple[float, float] = SELECTOR_REPEAT_POINT,
    bar_repeat_point: tuple[float, float] = BAR_REPEAT_POINT,
    initial_open_verified: bool = False,
    cancel_requested=lambda: False,
    clock=None,
    sleeper=None,
    fingerprint=None,
    measure_local=None,
    tap_through=None,
    allow_karat_entry: bool = False,
) -> GoldKeyDrainResult:
    """Drain Gold Keys through the right button until the Karat boundary.

    Injected I/O only: ``observe`` returns a fresh classified snapshot
    per call; production ``act`` emits semantic right-Gold intents through
    ActionExecutor, while legacy ``tap`` accepts a normalized point.
    ``measure_local`` (optional) returns a title-independent content
    reading for ``snapshot.frame.image`` (``TreasureContentDetector``
    ``.measure`` in production, a double in tests). Exactly one tap per
    fresh RIGHT_GOLD_OPEN_MAX observation -- observed or local reward
    transient -- with dual role (cut animation or start next batch,
    never labeled, never counted). Watchdog every ``watchdog_every``
    inputs, Karat boundary as the only normal end, then the verified
    finalize. ``tap_through`` is the existing bounded animation
    primitive and owns only that post-Karat step. Zero premium taps,
    zero left-button taps, and zero outside-button taps before the
    fresh Karat boundary. ``clock``/``sleeper`` make cadence injectable for
    tests; ``fingerprint`` makes the visual-progress check injectable.
    ``allow_karat_entry`` (default False) permits starting directly at
    an observed Karat boundary with caller-attested lineage, running
    only the finalize (HIL retry of a still-open boundary overlay).
    """
    if config is None:
        config = GoldKeyDrainConfig()
    if not isinstance(config, GoldKeyDrainConfig):
        raise ValueError("config must be GoldKeyDrainConfig")
    if not callable(observe) or callable(tap) == callable(act):
        raise ValueError("observe and exactly one input callback are required")
    if not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")
    if measure_local is not None and not callable(measure_local):
        raise ValueError("measure_local must be callable or None")
    if tap_through is not None and not callable(getattr(tap_through, "run", None)):
        raise ValueError("tap_through must provide run() or be None")
    if allow_karat_entry not in (True, False):
        raise ValueError("allow_karat_entry must be a boolean")
    now = clock if clock is not None else time.monotonic
    if not callable(now):
        raise ValueError("clock must be callable or None")
    sleep = sleeper if sleeper is not None else time.sleep
    if not callable(sleep):
        raise ValueError("sleeper must be callable or None")
    fingerprint_of = fingerprint if fingerprint is not None else (
        default_progress_fingerprint
    )
    if not callable(fingerprint_of):
        raise ValueError("fingerprint must be callable or None")
    if target is not None:
        target = _require_point(target, "target")
    if target_for is not None and not callable(target_for):
        raise ValueError("target_for must be callable or None")
    _require_point(repeat_point, "repeat_point")
    _require_point(bar_repeat_point, "bar_repeat_point")

    def _cancelled() -> bool:
        try:
            return cancel_requested() is True
        except Exception:
            return False

    start = now()
    deadline = start + config.safety_deadline_s
    evidence: list[str] = ["entry:initial_open_verified"]
    inputs = 0
    dismisses = 0
    watchdogs = 0
    gold_observations = 0
    karat_seen = False
    # Irreversible Gold-exhaustion latch: once a fresh Karat boundary
    # is seen, no right-button input of this drain may ever fire
    # again, whatever later frames claim.
    gold_exhausted = False

    def _latch_gold_exhausted(origin: str) -> None:
        nonlocal gold_exhausted
        if not gold_exhausted:
            gold_exhausted = True
            evidence.append(f"latch:gold_exhausted:{origin}")

    def _finish(outcome, *, reason=None, extra=()) -> GoldKeyDrainResult:
        return GoldKeyDrainResult(
            outcome=outcome,
            inputs_emitted=inputs,
            dismiss_inputs=dismisses,
            watchdogs_run=watchdogs,
            gold_button_observations=gold_observations,
            karat_boundary_seen=karat_seen,
            elapsed_s=max(0.0, now() - start),
            reason=reason,
            evidence=tuple([*evidence, *extra]),
        )

    if _cancelled():
        return _finish(
            GoldKeyDrainOutcome.CANCELLED,
            reason="user_cancelled",
            extra=("cancel_before_input",),
        )
    entry_reason = check_fast_drain_entry(
        initial_snapshot, initial_open_verified=initial_open_verified
    )
    karat_entry_pending = False
    if entry_reason is not None and (
        initial_open_verified is True
        and config.reward_transient
        and measure_local is not None
        and entry_reason
        in (
            "unknown_state",
            "ambiguous_state",
            "right_gold_absent",
            "no_repeat_state",
        )
    ):
        # Reward-transient entry: the verified open is caller-attested
        # lineage; the first frame only needs local pair Gold (same
        # contract as the loop). Karat/contradiction still refuse.
        try:
            entry_reading = measure_local(initial_snapshot.frame.image)  # type: ignore[attr-defined]
        except Exception:
            entry_reading = None
        if entry_reading is not None and (
            local_reward_side(entry_reading) is not None
        ):
            entry_reason = None
            evidence.append("entry:reward_transient_local")
        elif (
            allow_karat_entry
            and entry_reading is not None
            and local_karat_boundary(entry_reading)
        ):
            entry_reason = None
            karat_entry_pending = True
            evidence.append("entry:karat_boundary_local")
    if entry_reason is not None:
        if (
            entry_reason == "already_karat_boundary"
            and allow_karat_entry
            and initial_open_verified is True
        ):
            # Karat-boundary entry: caller-attested lineage of a drain
            # that already reached Karat; run only the finalize on the
            # still-open overlay (HIL retry). Handled after the helpers.
            karat_entry_pending = True
            evidence.append("entry:karat_boundary")
            entry_reason = None
        else:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason=entry_reason,
                extra=(f"entry:{entry_reason}",),
            )
    try:
        last_ts = float(initial_snapshot.timestamp)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return _finish(
            GoldKeyDrainOutcome.FAILED,
            reason="unreadable_timestamp",
            extra=("entry:unreadable_timestamp",),
        )
    gold_observations = 0 if karat_entry_pending else 1
    try:
        watchdog_fp = fingerprint_of(initial_snapshot)
    except Exception:
        watchdog_fp = None
    transient_deadline: float | None = None
    last_reading = None
    last_tap_mark = None
    progressed_since_watchdog = False

    def _tap_mark(snapshot):
        """Cheap per-tap change mark: ROI fingerprint + observation names."""
        try:
            mark_fp = fingerprint_of(snapshot)
        except Exception:
            mark_fp = None
        try:
            names = tuple(
                sorted(
                    observation.name
                    for observation in snapshot.observations.observations  # type: ignore[attr-defined]
                )
            )
        except Exception:
            names = ()
        return (mark_fp, names)

    def _point_for(snapshot) -> tuple[float, float]:
        if target is not None:
            return target
        if target_for is not None:
            return _require_point(target_for(snapshot), "target_for(snapshot)")
        return resolve_right_button_target(
            snapshot, repeat_point=repeat_point, bar_repeat_point=bar_repeat_point
        )

    def _local_point(side: str) -> tuple[float, float]:
        if target is not None:
            return target
        if side == LOCAL_SIDE_BAR:
            return _require_point(bar_repeat_point, "bar_repeat_point")
        return _require_point(repeat_point, "repeat_point")

    def _do_tap(point, tag: str, side: str):
        """Emit one right-button tap; return a terminal result or None.

        The Gold-exhaustion latch permanently forbids right-button
        input: any tap request after the latch fails closed instead
        of touching Karat-backed chrome.
        """
        nonlocal inputs, last_ts, transient_deadline, last_reading
        nonlocal last_tap_mark, progressed_since_watchdog
        if gold_exhausted:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="economic_after_latch",
                extra=("refused:latched",),
            )
        try:
            if act is not None:
                act(ContinueGoldDrainFromResult() if side == LOCAL_SIDE_BAR
                    else ConfirmRepeatGoldOpen())
            else:
                tap(point)
        except Exception as error:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason=f"tap_failed:{type(error).__name__}",
                extra=("tap_failed",),
            )
        inputs += 1
        last_ts = observed_ts
        transient_deadline = None
        if tag.startswith("local-"):
            last_reading = pending_reading
        else:
            last_reading = None
        mark = _tap_mark(snapshot)
        if last_tap_mark is not None and mark != last_tap_mark:
            progressed_since_watchdog = True
        last_tap_mark = mark
        evidence.append(f"tap_right:{inputs}:{tag}")
        sleep(config.tap_interval_s)
        return None

    def _do_watchdog(snapshot):
        """Corrected watchdog: A/B/C healthy, hidden title never stalls."""
        nonlocal watchdogs, watchdog_fp, karat_seen
        nonlocal last_tap_mark, progressed_since_watchdog
        watchdogs += 1
        if not is_treasure_screen(snapshot) and getattr(
            getattr(snapshot, "state", None), "status", None
        ) not in (ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS):
            return _finish(
                GoldKeyDrainOutcome.CONTEXT_LOST,
                reason="context_lost",
                extra=("watchdog:context_lost",),
            )
        if has_gold_signal(snapshot) and has_karat_signal(snapshot):
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="contradictory_state",
                extra=("watchdog:contradictory_state",),
            )
        healthy = has_right_gold_open_max(snapshot)
        if has_right_karat_open(snapshot) and not has_gold_signal(snapshot):
            terminal = _finalize_exhausted(snapshot)
            if terminal is not None:
                return terminal
            return None
        if not healthy and (
            last_reading is not None
            and local_reward_side(last_reading) is not None
        ):
            healthy = True
            evidence.append(f"watchdog:{watchdogs}:reward_transient")
        if not healthy:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="unexpected_state",
                extra=("watchdog:unexpected_state",),
            )
        try:
            current_fp = fingerprint_of(snapshot)
        except Exception:
            current_fp = None
        # STALL only when fresh taps changed nothing observable: same
        # ROI fingerprint AND same observation names on every tap of the
        # window. State churn (observed<->transient cycling) is progress,
        # so a static chest ROI alone never stalls a working loop.
        if not progressed_since_watchdog:
            return _finish(
                GoldKeyDrainOutcome.STALL_SUSPECTED,
                reason="visual_stall",
                extra=(f"watchdog:{watchdogs}", "visual_stall"),
            )
        watchdog_fp = current_fp
        last_tap_mark = _tap_mark(snapshot)
        progressed_since_watchdog = False
        evidence.append(f"watchdog:{watchdogs}")
        return None

    def _wait_bounded(label: str):
        """Bounded no-input wait; return a terminal result or None."""
        nonlocal transient_deadline
        if transient_deadline is None:
            transient_deadline = now() + config.transient_wait_s
            evidence.append(f"transient_wait_start:{label}")
        if now() >= transient_deadline:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason=f"{label}_timeout",
                extra=(f"{label}_timeout",),
            )
        sleep(min(0.05, config.tap_interval_s))
        return None

    def _finalize_exhausted(trigger):
        """Run the shared tap-through primitive only after fresh Karat."""
        nonlocal karat_seen, dismisses
        karat_seen = True
        _latch_gold_exhausted("karat_boundary")
        evidence.append("boundary:karat")

        def _final_tappable(snapshot) -> bool:
            """Lateral tap authorization under the latched lineage.

            Karat armed the latch; afterwards only the reward signal
            matters, never the title, never per-frame Karat. A fresh
            semantic result authorizes at once; otherwise a positive
            title-independent local reward reading on the fresh frame
            authorizes. A fresh RIGHT_GOLD_OPEN_MAX refuses the tap so
            the caller fails closed instead of a second outside tap.
            """
            if not gold_exhausted:
                return False
            if has_right_gold_open_max(snapshot):
                return False
            if has_local_reward_transient(snapshot):
                return True
            if measure_local is None:
                return False
            try:
                image = snapshot.frame.image  # type: ignore[attr-defined]
            except Exception:
                return False
            try:
                reading = measure_local(image)
            except Exception:
                return False
            return local_reward_present(reading)
        if _final_reward_cleared(trigger):
            return _finish(
                GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED,
                reason="karat_boundary",
                extra=("finalize:already_stable",),
            )
        if tap_through is None:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="finalizer_unavailable",
                extra=("finalize:unavailable",),
            )
        normal_policy = TapThroughPolicy()
        remaining = min(normal_policy.timeout, deadline - now())
        if remaining <= 0:
            return _finish(
                GoldKeyDrainOutcome.SAFETY_DEADLINE,
                reason="safety_deadline",
                extra=("finalize:safety_deadline",),
            )
        tapped = tap_through.run(
            trigger,
            action=DismissTreasureResult(),
            expected=_final_reward_cleared,
            tappable=_final_tappable,
            transient=_final_reward_transient,
            cancel_requested=cancel_requested,
            policy=(
                normal_policy
                if remaining == normal_policy.timeout
                else TapThroughPolicy(timeout=remaining)
            ),
        )
        dismisses += tapped.tap_count
        if tapped.tap_count:
            evidence.append(f"final_tap_through:{tapped.tap_count}")
        if tapped.outcome is TapThroughOutcome.CANCELLED:
            return _finish(
                GoldKeyDrainOutcome.CANCELLED,
                reason="user_cancelled",
                extra=("finalize:user_cancelled",),
            )
        if tapped.outcome is TapThroughOutcome.COMPLETED:
            if tapped.tap_count and tapped.final_snapshot.sequence <= trigger.sequence:
                return _finish(
                    GoldKeyDrainOutcome.FAILED,
                    reason="stale_final_postcondition",
                    extra=("finalize:stale_postcondition",),
                )
            return _finish(
                GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED,
                reason="karat_boundary",
                extra=("finalize:overlay_closed",),
            )
        return _finish(
            GoldKeyDrainOutcome.FAILED,
            reason="dismiss_no_effect",
            extra=(f"finalize:{tapped.outcome.value}",),
        )

    if karat_entry_pending:
        terminal = _finalize_exhausted(initial_snapshot)
        if terminal is not None:
            return terminal

    while True:
        if _cancelled():
            return _finish(
                GoldKeyDrainOutcome.CANCELLED,
                reason="user_cancelled",
                extra=("user_cancelled",),
            )
        if now() >= deadline:
            return _finish(
                GoldKeyDrainOutcome.SAFETY_DEADLINE,
                reason="safety_deadline",
                extra=("boundary:safety_deadline",),
            )
        if inputs >= config.max_inputs:
            return _finish(
                GoldKeyDrainOutcome.SAFETY_DEADLINE,
                reason="max_inputs_fuse",
                extra=("boundary:max_inputs_fuse",),
            )
        try:
            snapshot = observe()
        except Exception as error:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason=f"observe_failed:{type(error).__name__}",
                extra=("observe_failed",),
            )
        status = getattr(getattr(snapshot, "state", None), "status", None)
        if status is ResolutionStatus.RESOLVED and not is_treasure_screen(
            snapshot
        ):
            # Strong foreign context: positively resolved elsewhere.
            # Reward-grid UNKNOWN/AMBIGUOUS never reaches here.
            return _finish(
                GoldKeyDrainOutcome.CONTEXT_LOST,
                reason="context_lost",
                extra=("context_lost",),
            )
        if has_gold_signal(snapshot) and has_karat_signal(snapshot):
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="contradictory_state",
                extra=("contradictory_state",),
            )
        try:
            observed_ts = float(snapshot.timestamp)  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError):
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="unreadable_timestamp",
                extra=("unreadable_timestamp",),
            )
        pending_reading = None

        if has_right_gold_open_max(snapshot):
            transient_deadline = None
            gold_observations += 1
            if observed_ts <= last_ts:
                evidence.append("resample_skipped")
                sleep(config.tap_interval_s)
                continue
            if gold_exhausted:
                # Stale Gold sighting after the Karat latch: never
                # reactivate the fast loop. Bounded wait for the
                # resolvable boundary instead of any right-button tap.
                evidence.append("stale_gold_ignored")
                terminal = _wait_bounded("stale_gold")
                if terminal is not None:
                    return terminal
                continue
            side = "bar" if has_result(snapshot) else "popup"
            try:
                point = _point_for(snapshot) if act is None else None
            except Exception as error:
                return _finish(
                    GoldKeyDrainOutcome.FAILED,
                    reason=f"target_failed:{type(error).__name__}",
                    extra=("target_failed",),
                )
            terminal = _do_tap(point, f"observed-{side}", side)
            if terminal is not None:
                return terminal
            if inputs % config.watchdog_every == 0:
                terminal = _do_watchdog(snapshot)
                if terminal is not None:
                    return terminal
            continue

        # Observed Karat boundary with no observed Gold: leave the fast
        # loop with zero premium taps and finalize the overlay.
        if has_right_karat_open(snapshot) and not has_gold_signal(snapshot):
            if observed_ts <= last_ts:
                evidence.append("resample_skipped")
                sleep(config.tap_interval_s)
                continue
            terminal = _finalize_exhausted(snapshot)
            if terminal is not None:
                return terminal
            continue

        # Local reward-transient path: title-independent pair Gold on a
        # fresh frame under verified lineage. Dual-role tap (cuts the
        # animation or starts the next batch); never a dismiss, never
        # the left button, never counted as a batch.
        if (
            config.reward_transient
            and measure_local is not None
            and observed_ts > last_ts
        ):
            try:
                pending_reading = measure_local(snapshot.frame.image)  # type: ignore[attr-defined]
            except Exception:
                pending_reading = None
            side = (
                local_reward_side(pending_reading)
                if pending_reading is not None
                else None
            )
            if side is not None:
                if gold_exhausted:
                    evidence.append("stale_gold_ignored")
                    terminal = _wait_bounded("stale_gold")
                    if terminal is not None:
                        return terminal
                    continue
                gold_observations += 1
                evidence.append(f"local_gold:{side}")
                terminal = _do_tap(
                    _local_point(side) if act is None else None,
                    f"local-{side}", side,
                )
                if terminal is not None:
                    return terminal
                if inputs % config.watchdog_every == 0:
                    terminal = _do_watchdog(snapshot)
                    if terminal is not None:
                        return terminal
                continue
            if pending_reading is not None and local_karat_boundary(
                pending_reading
            ):
                # Premium backing seen locally: latch Gold exhaustion
                # at once, zero taps; confirm through resolvable
                # observations or time out closed.
                _latch_gold_exhausted("local_karat")
                evidence.append("local_karat_seen")
                terminal = _wait_bounded("local_karat")
                if terminal is not None:
                    return terminal
                continue

        # Bounded no-input wait: UNKNOWN/AMBIGUOUS animation frames,
        # transient Gold without the right button, or an empty repeat
        # state. Hidden title alone never taps, never loses context.
        if status is ResolutionStatus.UNKNOWN:
            label = "unknown_state"
        elif status is ResolutionStatus.AMBIGUOUS:
            label = "ambiguous_state"
        elif has_gold_signal(snapshot):
            label = "transient"
        else:
            label = "right_gold_absent"
        terminal = _wait_bounded(label)
        if terminal is not None:
            return terminal


def _final_reward_cleared(snapshot) -> bool:
    """Treasure is usable, reward is gone, and right Gold stayed absent."""

    return (
        clean_treasure(snapshot)
        and not has_result(snapshot)
        and not has_right_gold_open_max(snapshot)
    )


def _final_reward_transient(snapshot) -> bool:
    """Known no-input transition while waiting for final authorization."""

    status = getattr(getattr(snapshot, "state", None), "status", None)
    if status in (ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS):
        return True
    return (
        is_treasure_screen(snapshot)
        and not has_right_gold_open_max(snapshot)
        and has_result(snapshot)
    )


def _require_point(value: object, name: str) -> tuple[float, float]:
    try:
        first, second = value  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an (x, y) pair") from error
    for coordinate in (first, second):
        if isinstance(coordinate, bool) or not isinstance(coordinate, Real):
            raise ValueError(f"{name} must be an (x, y) pair in [0, 1]")
        if not 0.0 <= float(coordinate) <= 1.0:
            raise ValueError(f"{name} must be an (x, y) pair in [0, 1]")
    return (float(first), float(second))  # type: ignore[arg-type]


__all__ = (
    "BAR_REPEAT_POINT",
    "DISMISS_POINT",
    "LOCAL_SIDE_BAR",
    "LOCAL_SIDE_POPUP",
    "RESULT_FINGERPRINT_REGION",
    "REWARD_TRANSIENT_GOLD_THRESHOLD",
    "SELECTOR_REPEAT_POINT",
    "GoldKeyDrainConfig",
    "GoldKeyDrainOutcome",
    "GoldKeyDrainResult",
    "check_fast_drain_entry",
    "default_progress_fingerprint",
    "drain_gold_keys_fast",
    "local_karat_boundary",
    "local_reward_present",
    "local_reward_side",
    "resolve_right_button_target",
)
