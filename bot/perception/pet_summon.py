"""Epic summon availability from the acquired bright/dim card rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.catalog import (
    INDICATOR_PET_EPIC_AVAILABLE,
    INDICATOR_PET_EPIC_UNAVAILABLE,
    SEMANTIC_CONFIDENCE_THRESHOLD,
)
from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource

from .local_cv import LocalCvDetector
from .specs import (
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    LinearGapCalibration,
    PET_EPIC_INSUFFICIENT_FRAGMENTS_SPEC,
    PET_EPIC_SELECTOR_SPEC,
    PET_INVENTORY_FULL_PROMPT_SPEC,
    PET_PREMIUM_GOLD_SELECTOR_SPEC,
    PET_PREMIUM_TICKET_SELECTOR_SPEC,
    PET_SUMMON_ACTIVE_SPEC,
)


PET_EPIC_AVAILABILITY_REGION: RelativeRegion = (0.55, 0.46, 0.61, 0.68)
PET_EPIC_AVAILABILITY_CONFIDENCE_THRESHOLD = SEMANTIC_CONFIDENCE_THRESHOLD

# Human-confirmed clean Summon frames separate the same Epic egg rendering by
# luminance: available V=185.11..186.48; unavailable V=86.80..86.89.  Reading
# no quantity avoids coupling business semantics to OCR of the 0..9 numerator.
PET_EPIC_AVAILABLE_CALIBRATION = LinearGapCalibration(
    negative_anchor=86.89,
    positive_anchor=185.11,
)
PET_EPIC_UNAVAILABLE_CALIBRATION = LinearGapCalibration(
    negative_anchor=69.89,
    positive_anchor=168.11,
)


@dataclass(frozen=True)
class PetEpicAvailabilityReading:
    value_mean: float
    summon_confidence: float
    blocked_confidence: float
    available_confidence: float
    unavailable_confidence: float


class PetEpicAvailabilityDetector:
    """Emit one explicit Epic state only while the Summon tab is active."""

    evaluation_id = "indicator.pet_epic_availability"

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self.region = PET_EPIC_AVAILABILITY_REGION
        self.available_calibration = PET_EPIC_AVAILABLE_CALIBRATION
        self.unavailable_calibration = PET_EPIC_UNAVAILABLE_CALIBRATION
        self.confidence_threshold = PET_EPIC_AVAILABILITY_CONFIDENCE_THRESHOLD
        self._summon = LocalCvDetector(
            PET_SUMMON_ACTIVE_SPEC,
            asset_root=asset_root,
        )
        self._blockers = tuple(
            LocalCvDetector(spec, asset_root=asset_root)
            for spec in (
                PET_EPIC_SELECTOR_SPEC,
                PET_PREMIUM_TICKET_SELECTOR_SPEC,
                PET_PREMIUM_GOLD_SELECTOR_SPEC,
                PET_EPIC_INSUFFICIENT_FRAGMENTS_SPEC,
                PET_INVENTORY_FULL_PROMPT_SPEC,
                INSUFFICIENT_GOLD_PROMPT_SPEC,
            )
        )
        self.asset_paths = tuple(
            path
            for detector in (self._summon, *self._blockers)
            for path in detector.asset_paths
        )

    def measure(self, frame: np.ndarray) -> PetEpicAvailabilityReading:
        _validate_frame(frame)
        summon = self._summon.measure(frame).semantic_confidence
        blocked = max(
            detector.measure(frame).semantic_confidence
            for detector in self._blockers
        )
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = self.region
        roi = frame[
            int(y1 * height) : int(y2 * height),
            int(x1 * width) : int(x2 * width),
        ]
        value_mean = float(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
        gate = summon if blocked < self.confidence_threshold else 0.0
        return PetEpicAvailabilityReading(
            value_mean=value_mean,
            summon_confidence=summon,
            blocked_confidence=blocked,
            available_confidence=min(
                gate,
                self.available_calibration.confidence(value_mean),
            ),
            unavailable_confidence=min(
                gate,
                self.unavailable_calibration.confidence(255.0 - value_mean),
            ),
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        emitted = []
        for name, confidence in (
            (INDICATOR_PET_EPIC_AVAILABLE, reading.available_confidence),
            (INDICATOR_PET_EPIC_UNAVAILABLE, reading.unavailable_confidence),
        ):
            if confidence >= self.confidence_threshold:
                emitted.append(
                    Observation(
                        name=name,
                        confidence=confidence,
                        source=ObservationSource.LOCAL_CV,
                        region=self.region,
                    )
                )
        return tuple(emitted)


def _validate_frame(frame: object) -> None:
    if (
        not isinstance(frame, np.ndarray)
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.size == 0
        or frame.dtype != np.uint8
    ):
        raise ValueError("frame must be a non-empty HxWx3 uint8 BGR image")


__all__ = (
    "PET_EPIC_AVAILABILITY_CONFIDENCE_THRESHOLD",
    "PET_EPIC_AVAILABILITY_REGION",
    "PET_EPIC_AVAILABLE_CALIBRATION",
    "PET_EPIC_UNAVAILABLE_CALIBRATION",
    "PetEpicAvailabilityDetector",
    "PetEpicAvailabilityReading",
)
