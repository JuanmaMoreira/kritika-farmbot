"""Temporal Auto Battle fact and conservative ensure-on operation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable

import cv2
import numpy as np

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.catalog import OVERLAY_WORLD_BOSS_RAID_COMPLETE, SCREEN_WORLD_BOSS_BATTLE
from bot.geometry import RelativeRegion, normalize_relative_region, relative_region_to_pixels
from bot.observations import ObservationSource
from bot.runtime_facts import (
    FactQuality,
    FactReadResult,
    FactReadStatus,
    RuntimeFact,
    TemporalFactEvidence,
)
from bot.runtime_observer import RuntimeObserver
from bot.semantic_actions import ToggleAutoBattle
from bot.state import ResolutionStatus
from bot.temporal_observation import (
    TemporalObserver,
    TemporalWindowStatus,
    harvest_frame_window,
)


AUTO_BATTLE_SETTING = "setting.auto_battle"

#: Default budget for the single-pass quick check. Healthy acquisitions
#: complete 10 frames in 1.188-1.875 s across the 17 curated live windows
#: (datasets/auto_battle_temporal_calibration_manifest.json), so 3.0 s keeps
#: ~60% margin while abandoning starved perception quickly. Abandoning only
#: forfeits a tap (benign: the persistent setting is re-checked next battle);
#: a tap still requires the full 9-10 frame window with median <= off bar.
QUICK_AUTO_BATTLE_TIMEOUT = 3.0

#: Minimum median green-pill fraction in the control ROI for the button to
#: count as visible. 26/26 button-visible frames (live OFF/ON plus curated)
#: measure 0.450-0.477 while 2/2 controls-hidden cinematic frames measure
#: exactly 0.0, so 0.20 keeps >2x margin below the observed visible minimum.
#: The gate only ever converts a would-be OFF into UNKNOWN (fewer taps), so
#: a conservative value here errs toward a missed tap, never a false one.
AUTO_BATTLE_VISIBLE_GREEN_MIN = 0.20


class AutoBattleState(str, Enum):
    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AutoBattleCalibration:
    roi: RelativeRegion = (0.8350, 0.0180, 0.8900, 0.0780)
    border_fraction: float = 0.22
    off_threshold: float = 2.0
    on_threshold: float = 5.0
    frame_count: int = 10
    minimum_frame_count: int = 9
    sample_interval: float = 0.10
    timeout: float = 12.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "roi", normalize_relative_region(self.roi))
        for name in (
            "border_fraction",
            "off_threshold",
            "on_threshold",
            "sample_interval",
            "timeout",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{name} must be a finite real number")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite real number")
            object.__setattr__(self, name, value)
        if not 0.0 < self.border_fraction < 0.5:
            raise ValueError("border_fraction must be in (0, 0.5)")
        if not 0.0 <= self.off_threshold < self.on_threshold:
            raise ValueError("thresholds must satisfy 0 <= off < on")
        if self.sample_interval < 0.0 or self.timeout <= 0.0:
            raise ValueError("sample_interval must be non-negative and timeout positive")
        for name in ("frame_count", "minimum_frame_count"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 2
            ):
                raise ValueError(f"{name} must be an integer >= 2")
            object.__setattr__(self, name, int(value))
        if self.minimum_frame_count > self.frame_count:
            raise ValueError("minimum_frame_count cannot exceed frame_count")


DEFAULT_AUTO_BATTLE_CALIBRATION = AutoBattleCalibration()


class AutoBattleDetector:
    def __init__(
        self,
        observer: RuntimeObserver,
        *,
        calibration: AutoBattleCalibration = DEFAULT_AUTO_BATTLE_CALIBRATION,
        temporal: TemporalObserver | None = None,
    ) -> None:
        if not isinstance(observer, RuntimeObserver):
            raise ValueError("observer must be a RuntimeObserver")
        if not isinstance(calibration, AutoBattleCalibration):
            raise ValueError("calibration must be AutoBattleCalibration")
        self.observer = observer
        self.calibration = calibration
        self.temporal = temporal or TemporalObserver(observer)

    def observe(
        self,
        *,
        after_sequence: int,
        cancel_requested: Callable[[], bool] | None = None,
        timeout: float | None = None,
    ) -> FactReadResult[AutoBattleState]:
        budget = (
            self.calibration.timeout if timeout is None else _positive_timeout(timeout)
        )
        window = self.temporal.collect(
            after_sequence=after_sequence,
            context=SCREEN_WORLD_BOSS_BATTLE,
            frame_count=self.calibration.frame_count,
            sample_interval=self.calibration.sample_interval,
            timeout=budget,
            interrupt_overlays=frozenset((OVERLAY_WORLD_BOSS_RAID_COMPLETE,)),
            cancel_requested=cancel_requested,
        )
        status_map = {
            TemporalWindowStatus.CONTEXT_MISMATCH: FactReadStatus.CONTEXT_MISMATCH,
            TemporalWindowStatus.INTERRUPTED: FactReadStatus.CONTEXT_MISMATCH,
            TemporalWindowStatus.INSUFFICIENT: FactReadStatus.UNREADABLE,
            TemporalWindowStatus.TIMEOUT: FactReadStatus.TIMEOUT,
            TemporalWindowStatus.CANCELLED: FactReadStatus.CANCELLED,
            TemporalWindowStatus.FAILURE: FactReadStatus.FAILURE,
        }
        classifiable_timeout = (
            window.status is TemporalWindowStatus.TIMEOUT
            and len(window.snapshots) >= self.calibration.minimum_frame_count
        )
        if (
            window.status is not TemporalWindowStatus.COMPLETE
            and not classifiable_timeout
        ):
            return FactReadResult(status_map[window.status], detail=window.detail)
        return self.classify_frames(tuple(item.frame for item in window.snapshots))

    def classify_frames(
        self, snapshots: tuple[FrameSnapshot, ...]
    ) -> FactReadResult[AutoBattleState]:
        """Classify an acquired frame window with the temporal rule.

        Acquisition-agnostic: the same window/frame count, OFF/ON thresholds
        and visibility gate apply whether frames came from the full temporal
        observer or the fast harvest. No input is authorized here.
        """

        if len(snapshots) < self.calibration.minimum_frame_count:
            return FactReadResult(
                FactReadStatus.UNREADABLE,
                detail="insufficient frames for temporal classification",
            )
        try:
            frames = tuple(item.image for item in snapshots)
            activities = measure_auto_battle_activities(frames, self.calibration)
            activity = float(np.median(activities[1:]))
            state, confidence = self._classify(activity)
            if state is AutoBattleState.OFF:
                green = control_green_fractions(frames, self.calibration)
                green_median = float(np.median(green))
                if green_median < AUTO_BATTLE_VISIBLE_GREEN_MIN:
                    # Stillness without the control on screen (cinematic
                    # close-up, transition) is not OFF evidence: a hidden
                    # button yields ~0 border activity and would otherwise
                    # confirm OFF falsely and authorize a blind tap. Abstain
                    # as UNKNOWN so no tap is ever sent for a button that is
                    # not visible. This only removes tap authorizations; it
                    # can never create one.
                    state = AutoBattleState.UNKNOWN
                    confidence = min(
                        1.0,
                        (AUTO_BATTLE_VISIBLE_GREEN_MIN - green_median)
                        / AUTO_BATTLE_VISIBLE_GREEN_MIN,
                    )
            evidence = tuple(
                TemporalFactEvidence(
                    sequence=snapshot.sequence,
                    timestamp=snapshot.timestamp,
                    activity=sample_activity,
                    region=self.calibration.roi,
                )
                for snapshot, sample_activity in zip(snapshots, activities)
            )
        except Exception as error:
            return FactReadResult(FactReadStatus.FAILURE, detail=str(error))
        fact = RuntimeFact(
            name=AUTO_BATTLE_SETTING,
            value=state,
            confidence=confidence,
            quality=FactQuality.TEMPORAL,
            source=ObservationSource.LOCAL_CV,
            context=SCREEN_WORLD_BOSS_BATTLE,
            evidence=evidence,
        )
        return FactReadResult(FactReadStatus.CONFIRMED, fact=fact, evidence=evidence)

    def observe_fast(
        self,
        *,
        after_sequence: int,
        timeout: float,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> FactReadResult[AutoBattleState]:
        """Classify a fast raw harvest with the identical temporal rule.

        Harvested frames carry no resolved state, so the caller owns context
        verification (a fresh full observation plus the pre-tap guard). The
        window size, thresholds and visibility gate are exactly the ones in
        :meth:`classify_frames`; only the acquisition is cheaper.
        """

        budget = _positive_timeout(timeout, "timeout")
        harvested = harvest_frame_window(
            self.observer.source,
            after_sequence=after_sequence,
            frame_count=self.calibration.frame_count,
            sample_interval=self.calibration.sample_interval,
            timeout=budget,
            cancel_requested=cancel_requested,
        )
        if harvested.status is not TemporalWindowStatus.COMPLETE:
            status = {
                TemporalWindowStatus.TIMEOUT: FactReadStatus.TIMEOUT,
                TemporalWindowStatus.CANCELLED: FactReadStatus.CANCELLED,
            }.get(harvested.status, FactReadStatus.FAILURE)
            return FactReadResult(status, detail=harvested.detail)
        return self.classify_frames(harvested.frames)

    def _activities(self, frames: tuple[np.ndarray, ...]) -> tuple[float, ...]:
        return measure_auto_battle_activities(frames, self.calibration)

    def control_visible(self, frame: FrameSnapshot) -> bool:
        """Confirm the control still exists on the fresh pre-input guard."""
        return control_green_fractions((frame.image,), self.calibration)[0] >= AUTO_BATTLE_VISIBLE_GREEN_MIN

    def _border_pixels(self, frame: np.ndarray) -> np.ndarray:
        return _auto_battle_border_pixels(frame, self.calibration)

    def _classify(self, activity: float) -> tuple[AutoBattleState, float]:
        off = self.calibration.off_threshold
        on = self.calibration.on_threshold
        if activity <= off:
            margin = 1.0 if off == 0.0 else (off - activity) / off
            return AutoBattleState.OFF, 0.5 + 0.5 * min(1.0, margin)
        if activity >= on:
            margin = min(1.0, (activity - on) / max(on, 1e-9))
            return AutoBattleState.ON, 0.5 + 0.5 * margin
        midpoint = (off + on) / 2.0
        half_gap = (on - off) / 2.0
        confidence = 1.0 - abs(activity - midpoint) / half_gap
        return AutoBattleState.UNKNOWN, confidence


def measure_auto_battle_activities(
    frames: tuple[np.ndarray, ...],
    calibration: AutoBattleCalibration = DEFAULT_AUTO_BATTLE_CALIBRATION,
) -> tuple[float, ...]:
    """Return per-frame border activity; the first sample has no predecessor."""

    if len(frames) < 2:
        raise ValueError("at least two frames are required")
    crops = [_auto_battle_border_pixels(frame, calibration) for frame in frames]
    values = [0.0]
    values.extend(
        float(np.mean(cv2.absdiff(previous, current)))
        for previous, current in zip(crops, crops[1:])
    )
    return tuple(values)


def control_green_fractions(
    frames: tuple[np.ndarray, ...],
    calibration: AutoBattleCalibration = DEFAULT_AUTO_BATTLE_CALIBRATION,
) -> tuple[float, ...]:
    """Return the green-pill fraction per frame inside the control ROI.

    The Auto pill is green whether ON (plus animated glow) or OFF, so its
    presence only proves the control is on screen -- never its state. A
    controls-hidden frame (cinematic close-up, transition) measures ~0.0.
    """

    if not frames:
        raise ValueError("at least one frame is required")
    fractions = []
    for frame in frames:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = relative_region_to_pixels(calibration.roi, width, height)
        hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        green = (
            (hsv[:, :, 0] >= 35)
            & (hsv[:, :, 0] <= 90)
            & (hsv[:, :, 1] >= 80)
            & (hsv[:, :, 2] >= 80)
        )
        fractions.append(float(green.mean()))
    return tuple(fractions)


def _auto_battle_border_pixels(
    frame: np.ndarray, calibration: AutoBattleCalibration
) -> np.ndarray:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = relative_region_to_pixels(calibration.roi, width, height)
    gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    border_y = max(1, round(gray.shape[0] * calibration.border_fraction))
    border_x = max(1, round(gray.shape[1] * calibration.border_fraction))
    mask = np.zeros(gray.shape, dtype=bool)
    mask[:border_y, :] = True
    mask[-border_y:, :] = True
    mask[:, :border_x] = True
    mask[:, -border_x:] = True
    return gray[mask]


class EnsureAutoBattleStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CONTEXT_MISMATCH = "context_mismatch"
    INTERRUPTED = "interrupted"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class EnsureAutoBattleResult:
    status: EnsureAutoBattleStatus
    observations: tuple[RuntimeFact[AutoBattleState], ...]
    tap_count: int
    detail: str | None = None


class AutoBattleEnsurer:
    """Ensure ON without ever treating UNKNOWN as permission to tap."""

    def __init__(
        self,
        detector: AutoBattleDetector,
        actions: ActionExecutor,
        *,
        max_taps: int = 2,
        max_unknown_observations: int = 2,
    ) -> None:
        if not isinstance(detector, AutoBattleDetector):
            raise ValueError("detector must be an AutoBattleDetector")
        if not isinstance(actions, ActionExecutor):
            raise ValueError("actions must be an ActionExecutor")
        if (
            isinstance(max_taps, bool)
            or not isinstance(max_taps, Integral)
            or max_taps < 1
            or isinstance(max_unknown_observations, bool)
            or not isinstance(max_unknown_observations, Integral)
            or max_unknown_observations < 1
        ):
            raise ValueError("retry limits must be positive")
        self.detector = detector
        self.actions = actions
        self.max_taps = int(max_taps)
        self.max_unknown_observations = int(max_unknown_observations)

    def _execute_verified_tap(
        self, guard
    ) -> tuple[EnsureAutoBattleStatus | None, int, object | None, str | None]:
        """Execute one tap against an already verified guard snapshot.

        Returns ``(status, taps_made, baseline, detail)`` where ``status`` is
        ``None`` when the tap was sent and ``baseline`` is the fresh
        post-input snapshot. Any non-``None`` status already accounts for its
        taps and aborts the caller: context loss, Raid Complete, or failure.
        Shared single tap implementation of every ensure path.
        """

        if guard.state.status is not ResolutionStatus.RESOLVED or guard.state.overlays:
            return (EnsureAutoBattleStatus.TIMEOUT, 0, None,
                    "Auto Battle tap guard is not clean and resolved")
        try:
            if not self.detector.control_visible(guard.frame):
                return (EnsureAutoBattleStatus.TIMEOUT, 0, None,
                        "Auto Battle control hidden before tap")
            self.actions.execute(ToggleAutoBattle(), guard.geometry)
        except Exception as error:
            return (EnsureAutoBattleStatus.FAILURE, 0, None, str(error))
        # The new baseline is captured after input; its frame is never classified.
        try:
            baseline = self.detector.observer.observe()
        except Exception as error:
            return (EnsureAutoBattleStatus.FAILURE, 1, None, str(error))
        if baseline.sequence <= guard.sequence:
            return (
                EnsureAutoBattleStatus.TIMEOUT,
                1,
                None,
                "no fresh frame immediately after Auto Battle tap",
            )
        if OVERLAY_WORLD_BOSS_RAID_COMPLETE in baseline.state.overlays:
            return (
                EnsureAutoBattleStatus.INTERRUPTED,
                1,
                None,
                "Raid Complete appeared after Auto Battle tap",
            )
        if baseline.state.status is not ResolutionStatus.RESOLVED:
            return (EnsureAutoBattleStatus.TIMEOUT, 1, None,
                    "battle context unconfirmed immediately after Auto Battle tap")
        if baseline.state.base_context != SCREEN_WORLD_BOSS_BATTLE:
            return (EnsureAutoBattleStatus.CONTEXT_MISMATCH, 1, None,
                    "context changed immediately after Auto Battle tap")
        return (None, 1, baseline, None)

    def ensure_on(
        self,
        *,
        after_sequence: int,
        cancel_requested: Callable[[], bool] | None = None,
        timeout: float | None = None,
        max_taps: int | None = None,
        max_unknown_observations: int | None = None,
    ) -> EnsureAutoBattleResult:
        budget = (
            None if timeout is None else _positive_timeout(timeout)
        )
        tap_limit = (
            self.max_taps
            if max_taps is None
            else _positive_limit(max_taps, "max_taps")
        )
        unknown_limit = (
            self.max_unknown_observations
            if max_unknown_observations is None
            else _positive_limit(max_unknown_observations, "max_unknown_observations")
        )
        cursor = after_sequence
        taps = 0
        unknowns = 0
        retry_allowed = True
        facts: list[RuntimeFact[AutoBattleState]] = []
        while True:
            reading = self.detector.observe(
                after_sequence=cursor,
                cancel_requested=cancel_requested,
                timeout=budget,
            )
            if reading.fact is None:
                status = {
                    FactReadStatus.CONTEXT_MISMATCH: EnsureAutoBattleStatus.CONTEXT_MISMATCH,
                    FactReadStatus.TIMEOUT: EnsureAutoBattleStatus.TIMEOUT,
                    FactReadStatus.CANCELLED: EnsureAutoBattleStatus.CANCELLED,
                }.get(reading.status, EnsureAutoBattleStatus.FAILURE)
                if reading.detail and OVERLAY_WORLD_BOSS_RAID_COMPLETE in reading.detail:
                    status = EnsureAutoBattleStatus.INTERRUPTED
                return EnsureAutoBattleResult(status, tuple(facts), taps, reading.detail)
            fact = reading.fact
            facts.append(fact)
            cursor = fact.sequence
            if fact.value is AutoBattleState.ON:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.SUCCESS, tuple(facts), taps
                )
            if fact.value is AutoBattleState.UNKNOWN:
                unknowns += 1
                if taps:
                    retry_allowed = False
                if unknowns >= unknown_limit:
                    return EnsureAutoBattleResult(
                        EnsureAutoBattleStatus.FAILURE,
                        tuple(facts),
                        taps,
                        "Auto Battle remained UNKNOWN; no input sent",
                    )
                continue
            unknowns = 0
            if not retry_allowed:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.FAILURE,
                    tuple(facts),
                    taps,
                    "OFF followed an UNKNOWN post-observation; tap retry suppressed",
                )
            if taps >= tap_limit:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.FAILURE,
                    tuple(facts),
                    taps,
                    "Auto Battle remained OFF after bounded taps",
                )
            try:
                guard = self.detector.observer.observe()
            except Exception as error:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.FAILURE, tuple(facts), taps, str(error)
                )
            if guard.state.base_context != SCREEN_WORLD_BOSS_BATTLE:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.CONTEXT_MISMATCH,
                    tuple(facts),
                    taps,
                    "context changed before Auto Battle tap",
                )
            if OVERLAY_WORLD_BOSS_RAID_COMPLETE in guard.state.overlays:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.INTERRUPTED,
                    tuple(facts),
                    taps,
                    "Raid Complete appeared before Auto Battle tap",
                )
            tap_status, made, baseline, detail = self._execute_verified_tap(guard)
            taps += made
            if tap_status is not None:
                return EnsureAutoBattleResult(
                    tap_status, tuple(facts), taps, detail
                )
            cursor = baseline.sequence

    def ensure_on_quick(
        self,
        *,
        after_sequence: int,
        quick_timeout: float = QUICK_AUTO_BATTLE_TIMEOUT,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> EnsureAutoBattleResult:
        """Single-pass per-battle check: tap at most once, only on OFF.

        OFF is static, but stillness over a short window is weak evidence (an
        ON glow gap looks identical), while a missed tap is benign and a
        false-OFF tap would switch the persistent setting OFF. Classification
        therefore uses the identical temporal rule as :meth:`ensure_on`
        (full 9-10 frame window, median below the OFF threshold, visibility
        gate); only the acquisition is a fast raw harvest instead of full
        semantic observations per frame:

        * Harvested frames carry no resolved state, so one fresh full
          observation confirms the battle context (Raid Complete, resolved
          incompatible base, or unconfirmed) before any verdict is trusted.
        * CONFIRMED OFF on confirmed battle -> exactly one guarded tap, then
          one fast best-effort re-verification; if it stays inconclusive the
          caller continues with the tap counted.
        * Anything inconclusive (harvest timeout, UNKNOWN, unconfirmed
          context) -> no tap; the caller continues.
        * CONTEXT_MISMATCH / INTERRUPTED / CANCELLED keep their meaning, so a
          resolved incompatible context still aborts at the caller.
        """

        budget = _positive_timeout(quick_timeout, "quick_timeout")
        facts: list[RuntimeFact[AutoBattleState]] = []
        reading = self.detector.observe_fast(
            after_sequence=after_sequence,
            timeout=budget,
            cancel_requested=cancel_requested,
        )
        if reading.fact is None:
            status = {
                FactReadStatus.TIMEOUT: EnsureAutoBattleStatus.TIMEOUT,
                FactReadStatus.CANCELLED: EnsureAutoBattleStatus.CANCELLED,
            }.get(reading.status, EnsureAutoBattleStatus.FAILURE)
            return EnsureAutoBattleResult(status, (), 0, reading.detail)
        fact = reading.fact
        facts.append(fact)
        try:
            context = self.detector.observer.observe()
        except Exception as error:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.FAILURE, tuple(facts), 0, str(error)
            )
        if context.sequence <= max(after_sequence, fact.sequence):
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.TIMEOUT, tuple(facts), 0,
                "no fresh context after fast harvest; no input sent",
            )
        if OVERLAY_WORLD_BOSS_RAID_COMPLETE in context.state.overlays:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.INTERRUPTED,
                tuple(facts),
                0,
                "Raid Complete observed after fast harvest",
            )
        if (
            context.state.status is ResolutionStatus.RESOLVED
            and context.state.base_context != SCREEN_WORLD_BOSS_BATTLE
        ):
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.CONTEXT_MISMATCH,
                tuple(facts),
                0,
                "fresh resolved frame outside Auto Battle context after fast harvest",
            )
        if context.state.status is not ResolutionStatus.RESOLVED:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.TIMEOUT,
                tuple(facts),
                0,
                "battle context unconfirmed after fast harvest; no input sent",
            )
        if fact.value is AutoBattleState.ON:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.SUCCESS, tuple(facts), 0
            )
        if fact.value is AutoBattleState.UNKNOWN:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.FAILURE,
                tuple(facts),
                0,
                "Auto Battle remained UNKNOWN; no input sent",
            )
        if cancel_requested is not None and cancel_requested():
            return EnsureAutoBattleResult(EnsureAutoBattleStatus.CANCELLED, tuple(facts), 0)
        tap_status, made, baseline, detail = self._execute_verified_tap(context)
        taps = made
        if tap_status is not None:
            return EnsureAutoBattleResult(
                tap_status, tuple(facts), taps, detail
            )
        recheck = self.detector.observe_fast(
            after_sequence=baseline.sequence,
            timeout=budget,
            cancel_requested=cancel_requested,
        )
        if recheck.status is FactReadStatus.CANCELLED:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.CANCELLED, tuple(facts), taps, recheck.detail
            )
        if recheck.fact is not None:
            facts.append(recheck.fact)
        if recheck.fact is None or recheck.fact.value is not AutoBattleState.ON:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.TIMEOUT,
                tuple(facts),
                taps,
                recheck.detail or "post-tap fast verification inconclusive",
            )
        try:
            after = self.detector.observer.observe()
        except Exception as error:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.TIMEOUT, tuple(facts), taps, str(error)
            )
        if OVERLAY_WORLD_BOSS_RAID_COMPLETE in after.state.overlays:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.INTERRUPTED,
                tuple(facts),
                taps,
                "Raid Complete observed after post-tap verification",
            )
        if (
            after.state.status is ResolutionStatus.RESOLVED
            and after.state.base_context != SCREEN_WORLD_BOSS_BATTLE
        ):
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.CONTEXT_MISMATCH,
                tuple(facts),
                taps,
                "fresh resolved frame outside Auto Battle context after post-tap verification",
            )
        if after.state.status is not ResolutionStatus.RESOLVED:
            return EnsureAutoBattleResult(
                EnsureAutoBattleStatus.TIMEOUT,
                tuple(facts),
                taps,
                "battle context unconfirmed after post-tap verification",
            )
        return EnsureAutoBattleResult(
            EnsureAutoBattleStatus.SUCCESS, tuple(facts), taps
        )


def _positive_timeout(value: object, name: str = "timeout") -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _positive_limit(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


__all__ = (
    "AUTO_BATTLE_SETTING",
    "AUTO_BATTLE_VISIBLE_GREEN_MIN",
    "AutoBattleCalibration",
    "AutoBattleDetector",
    "AutoBattleEnsurer",
    "AutoBattleState",
    "DEFAULT_AUTO_BATTLE_CALIBRATION",
    "EnsureAutoBattleResult",
    "EnsureAutoBattleStatus",
    "QUICK_AUTO_BATTLE_TIMEOUT",
    "control_green_fractions",
    "measure_auto_battle_activities",
)
