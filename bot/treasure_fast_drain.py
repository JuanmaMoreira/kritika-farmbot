"""Fast Gold Keys drain primitive (E2.2, Treasure-only).

Treasure-specific rapid drain over an already-opened repeat state. The
caller owns entry (Lobby -> Treasure -> first verified open via the E2
path) and return (dismiss/leave); this module only taps the RIGHT Gold
button fast while it stays Gold-backed, then classifies the boundary.

Semantics (amount-agnostic, no OCR of the number):

- ``RIGHT_GOLD_OPEN_MAX`` (``has_right_gold_open_max``): right button
  actionable and Gold-backed, opening whatever maximum the UI offers
  (1..10). The ``10``/``7``/``1`` label is never read.
- ``RIGHT_KARAT_OPEN`` (``has_right_karat_open``): same right-button
  role backed by Karats/premium. Normal termination, zero taps.
- Gold+Karat together: contradiction, zero input, fail closed.
- The LEFT ``1(Open)`` control is never a drain target.

UI audit (E/E2/E2.1 raws, 2026-09-17/18):

- selector popup (initial): center overlay, right button bbox approx
  x 0.650-0.730 / y 0.395-0.565, point (0.693, 0.540) geometrically
  calibrated from the B1 popup (``TREASURE_PROFILE.repeat_point``).
  Repeat tap itself HIL_NOT_EXERCISED.
- result overlay (repeat): bottom bar, right icon ROI x 0.305-0.365 /
  y 0.78-0.86, centroid (0.335, 0.82). Different position from the
  selector popup: the target is resolved per snapshot
  (result -> bar, else selector). Bar repeat tap HIL_NOT_EXERCISED.
- detector split: popup repeat needs the ``10(Open)`` label yellow +
  icon gold; bar repeat needs only the icon gold under a result gate.
  ``1..9`` right-button popup variants are therefore HIL_PENDING: if a
  small-number right button ever stops emitting the repeat signal, the
  detector needs the minimal icon-over-label relaxation (this module
  does not change detection, it only refuses to read the number).

Loop (fast path, no result wait per tap, no full scope per cycle):

- one fresh observation per tap decision (``observed_at`` strictly
  newer than the observation used for the previous input; resamples
  are skipped with zero input, never a second tap on one frame);
- ``tap_interval_s`` (default 0.20) cadence slots via injected
  clock/sleeper (no busy loop);
- full watchdog every ``watchdog_every`` inputs (default 10): Treasure
  context, open/result compatibility, Gold/Karat coherence, no
  foreign, no UNKNOWN/AMBIGUOUS, plus a cheap visual-progress
  fingerprint over the animation/result ROI (default: downsampled
  result-region hash; identical button + identical ROI across a
  watchdog window -> STALL_SUSPECTED, stop touching);
- gold gone -> stop inputs immediately -> full classify:
  RIGHT_KARAT_OPEN (no Gold anywhere) -> GOLD_KEYS_EXHAUSTED with zero
  premium taps; transient Gold still visible -> bounded wait for
  reappearance; UNKNOWN/AMBIGUOUS/foreign/contradiction -> fail closed.

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

from bot.state import ResolutionStatus
from bot.treasure_center import (
    has_gold_signal,
    has_karat_signal,
    has_result,
    has_right_button_contradiction,
    has_right_gold_open_max,
    has_right_karat_open,
    has_selector_popup,
    is_treasure_screen,
)

#: Selector-popup right-button point (B1 geometry; repeat tap pending HIL).
SELECTOR_REPEAT_POINT: tuple[float, float] = (0.693, 0.540)

#: Result bottom-bar right-button point: centroid of the bar repeat icon
#: ROI x 0.305-0.365 / y 0.78-0.86 (``TREASURE_BAR_REPEAT_ICON_REGION``).
#: Derived geometrically, HIL_NOT_EXERCISED for live taps.
BAR_REPEAT_POINT: tuple[float, float] = (0.335, 0.82)

#: Animation/result ROI for the visual-progress fingerprint
#: (``TREASURE_RESULT_REGION`` provenance; numpy-only, no detector).
RESULT_FINGERPRINT_REGION: tuple[float, float, float, float] = (
    0.42,
    0.55,
    0.60,
    0.80,
)


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

    ``tap_interval_s`` is the minimum spacing between inputs (initial
    0.20 from the E2.2 brief; HIL characterizes the stable minimum).
    ``watchdog_every`` counts inputs between full watchdogs.
    ``safety_deadline_s`` is a generous fuse, not success criteria.
    ``max_inputs`` is a very high technical fuse, never a batch plan.
    ``transient_wait_s`` bounds the reappearance wait after the Gold
    button disappears while other Gold is still visible.
    """

    tap_interval_s: float = 0.20
    watchdog_every: int = 10
    safety_deadline_s: float = 300.0
    max_inputs: int = 10000
    transient_wait_s: float = 5.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.tap_interval_s, bool)
            or not isinstance(self.tap_interval_s, Real)
            or not 0.0 <= float(self.tap_interval_s) <= 60.0
        ):
            raise ValueError("tap_interval_s must be a duration in [0, 60]")
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


@dataclass(frozen=True)
class GoldKeyDrainResult:
    """Descriptive drain outcome; never a routing decision.

    Counts inputs and boundary sightings only. There is deliberately
    NO opened/batch count: taps are not batches (a tap may only cut an
    animation) and only real evidence could claim an open.
    """

    outcome: GoldKeyDrainOutcome
    inputs_emitted: int = 0
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
    are HIL_PENDING for live repeat taps.
    """
    _require_point(repeat_point, "repeat_point")
    _require_point(bar_repeat_point, "bar_repeat_point")
    if has_result(snapshot):
        return (float(bar_repeat_point[0]), float(bar_repeat_point[1]))
    return (float(repeat_point[0]), float(repeat_point[1]))


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
) -> GoldKeyDrainResult:
    """Drain Gold Keys through the right button until the Karat boundary.

    Injected I/O only: ``observe`` returns a fresh classified snapshot
    per call, ``tap`` performs one normalized tap at the given point.
    Exactly one tap per fresh RIGHT_GOLD_OPEN_MAX observation, watchdog
    every ``watchdog_every`` inputs, Karat boundary as the only normal
    end. Zero premium taps, zero left-button taps, zero tap-count
    termination. ``clock``/``sleeper`` make cadence injectable for
    tests; ``fingerprint`` makes the visual-progress check injectable.
    """
    if config is None:
        config = GoldKeyDrainConfig()
    if not isinstance(config, GoldKeyDrainConfig):
        raise ValueError("config must be GoldKeyDrainConfig")
    if not callable(observe) or not callable(tap):
        raise ValueError("observe and tap must be callable")
    if not callable(cancel_requested):
        raise ValueError("cancel_requested must be callable")
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
    watchdogs = 0
    gold_observations = 0
    karat_seen = False

    def _finish(outcome, *, reason=None, extra=()) -> GoldKeyDrainResult:
        return GoldKeyDrainResult(
            outcome=outcome,
            inputs_emitted=inputs,
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
    if entry_reason is not None:
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
    gold_observations = 1
    try:
        watchdog_fp = fingerprint_of(initial_snapshot)
    except Exception:
        watchdog_fp = None
    transient_deadline: float | None = None

    def _point_for(snapshot) -> tuple[float, float]:
        if target is not None:
            return target
        if target_for is not None:
            return _require_point(target_for(snapshot), "target_for(snapshot)")
        return resolve_right_button_target(
            snapshot, repeat_point=repeat_point, bar_repeat_point=bar_repeat_point
        )

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
        if status is ResolutionStatus.UNKNOWN or (
            status is ResolutionStatus.AMBIGUOUS
        ):
            # Animation frames lose the title anchor (known detector
            # limit): stop inputs, wait bounded for the repeat state to
            # come back, fail closed on timeout. Never a tap here.
            label = (
                "unknown_state"
                if status is ResolutionStatus.UNKNOWN
                else "ambiguous_state"
            )
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
            continue
        if not is_treasure_screen(snapshot):
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

        if has_right_gold_open_max(snapshot):
            transient_deadline = None
            gold_observations += 1
            if observed_ts <= last_ts:
                evidence.append("resample_skipped")
                sleep(config.tap_interval_s)
                continue
            try:
                point = _point_for(snapshot)
            except Exception as error:
                return _finish(
                    GoldKeyDrainOutcome.FAILED,
                    reason=f"target_failed:{type(error).__name__}",
                    extra=("target_failed",),
                )
            try:
                tap(point)
            except Exception as error:
                return _finish(
                    GoldKeyDrainOutcome.FAILED,
                    reason=f"tap_failed:{type(error).__name__}",
                    extra=("tap_failed",),
                )
            inputs += 1
            last_ts = observed_ts
            evidence.append(f"tap_right:{inputs}")
            sleep(config.tap_interval_s)
            if inputs % config.watchdog_every == 0:
                watchdogs += 1
                if not is_treasure_screen(snapshot):
                    return _finish(
                        GoldKeyDrainOutcome.CONTEXT_LOST,
                        reason="context_lost",
                        extra=("watchdog:context_lost",),
                    )
                if not (
                    has_selector_popup(snapshot) or has_result(snapshot)
                ):
                    return _finish(
                        GoldKeyDrainOutcome.FAILED,
                        reason="unexpected_state",
                        extra=("watchdog:unexpected_state",),
                    )
                try:
                    current_fp = fingerprint_of(snapshot)
                except Exception:
                    current_fp = None
                if (
                    current_fp is not None
                    and watchdog_fp is not None
                    and current_fp == watchdog_fp
                ):
                    return _finish(
                        GoldKeyDrainOutcome.STALL_SUSPECTED,
                        reason="visual_stall",
                        extra=(
                            f"watchdog:{watchdogs}",
                            "visual_stall",
                        ),
                    )
                watchdog_fp = current_fp
                evidence.append(f"watchdog:{watchdogs}")
            continue

        # Right Gold absent: stop inputs immediately, classify fully.
        if has_right_karat_open(snapshot):
            karat_seen = True
            return _finish(
                GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED,
                reason="karat_boundary",
                extra=("boundary:karat",),
            )
        if has_gold_signal(snapshot):
            # Transient (animation/single-gold) with Gold still around:
            # bounded wait for RIGHT_GOLD_OPEN_MAX to reappear.
            if transient_deadline is None:
                transient_deadline = now() + config.transient_wait_s
                evidence.append("transient_wait_start")
            if now() >= transient_deadline:
                return _finish(
                    GoldKeyDrainOutcome.FAILED,
                    reason="transient_timeout",
                    extra=("transient_timeout",),
                )
            sleep(min(0.05, config.tap_interval_s))
            continue
        if transient_deadline is None:
            transient_deadline = now() + config.transient_wait_s
            evidence.append("transient_wait_start")
        if now() >= transient_deadline:
            return _finish(
                GoldKeyDrainOutcome.FAILED,
                reason="right_gold_absent",
                extra=("right_gold_absent",),
            )
        sleep(min(0.05, config.tap_interval_s))


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
    "RESULT_FINGERPRINT_REGION",
    "SELECTOR_REPEAT_POINT",
    "GoldKeyDrainConfig",
    "GoldKeyDrainOutcome",
    "GoldKeyDrainResult",
    "check_fast_drain_entry",
    "default_progress_fingerprint",
    "drain_gold_keys_fast",
    "resolve_right_button_target",
)
