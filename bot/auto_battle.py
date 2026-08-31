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
from bot.temporal_observation import TemporalObserver, TemporalWindowStatus


AUTO_BATTLE_SETTING = "setting.auto_battle"


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
    sample_interval: float = 0.10
    timeout: float = 8.0

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
        if (
            isinstance(self.frame_count, bool)
            or not isinstance(self.frame_count, Integral)
            or self.frame_count < 2
        ):
            raise ValueError("frame_count must be an integer >= 2")
        object.__setattr__(self, "frame_count", int(self.frame_count))


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
    ) -> FactReadResult[AutoBattleState]:
        window = self.temporal.collect(
            after_sequence=after_sequence,
            context=SCREEN_WORLD_BOSS_BATTLE,
            frame_count=self.calibration.frame_count,
            sample_interval=self.calibration.sample_interval,
            timeout=self.calibration.timeout,
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
        if window.status is not TemporalWindowStatus.COMPLETE:
            return FactReadResult(status_map[window.status], detail=window.detail)

        try:
            activities = measure_auto_battle_activities(
                tuple(item.frame.image for item in window.snapshots), self.calibration
            )
            activity = float(np.median(activities[1:]))
            state, confidence = self._classify(activity)
            evidence = tuple(
                TemporalFactEvidence(
                    sequence=snapshot.sequence,
                    timestamp=snapshot.timestamp,
                    activity=sample_activity,
                    region=self.calibration.roi,
                )
                for snapshot, sample_activity in zip(window.snapshots, activities)
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

    def _activities(self, frames: tuple[np.ndarray, ...]) -> tuple[float, ...]:
        return measure_auto_battle_activities(frames, self.calibration)

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

    def ensure_on(
        self,
        *,
        after_sequence: int,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> EnsureAutoBattleResult:
        cursor = after_sequence
        taps = 0
        unknowns = 0
        retry_allowed = True
        facts: list[RuntimeFact[AutoBattleState]] = []
        while True:
            reading = self.detector.observe(
                after_sequence=cursor, cancel_requested=cancel_requested
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
                if unknowns >= self.max_unknown_observations:
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
            if taps >= self.max_taps:
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
            try:
                self.actions.execute(ToggleAutoBattle(), guard.geometry)
            except Exception as error:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.FAILURE, tuple(facts), taps, str(error)
                )
            taps += 1
            # The new baseline is captured after input; its frame is never classified.
            try:
                baseline = self.detector.observer.observe()
            except Exception as error:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.FAILURE, tuple(facts), taps, str(error)
                )
            if baseline.state.base_context != SCREEN_WORLD_BOSS_BATTLE:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.CONTEXT_MISMATCH,
                    tuple(facts),
                    taps,
                    "context changed immediately after Auto Battle tap",
                )
            if OVERLAY_WORLD_BOSS_RAID_COMPLETE in baseline.state.overlays:
                return EnsureAutoBattleResult(
                    EnsureAutoBattleStatus.INTERRUPTED,
                    tuple(facts),
                    taps,
                    "Raid Complete appeared after Auto Battle tap",
                )
            cursor = baseline.sequence


__all__ = (
    "AUTO_BATTLE_SETTING",
    "AutoBattleCalibration",
    "AutoBattleDetector",
    "AutoBattleEnsurer",
    "AutoBattleState",
    "DEFAULT_AUTO_BATTLE_CALIBRATION",
    "EnsureAutoBattleResult",
    "EnsureAutoBattleStatus",
    "measure_auto_battle_activities",
)
