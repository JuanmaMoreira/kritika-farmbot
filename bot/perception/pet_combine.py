"""Pet Combine semantics acquired for a future bounded space relief."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    CANDIDATE_PET_LOW_TIER,
    LANDMARK_PET_COMBINE_RESULT,
    LANDMARK_PET_MASS_EVOLVE_CONFIRMATION,
    SEMANTIC_CONFIDENCE_THRESHOLD,
)
from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource

from .local_cv import LocalCvDetector
from .specs import (
    LinearGapCalibration,
    PET_COMBINE_ACTIVE_SPEC,
    PET_COMBINE_ALL_CONFIRM_SPEC,
    PET_COMBINE_EVOLVE_PROMPT_SPEC,
    PET_COMBINE_NO_MATERIAL_SPEC,
    PET_COMBINE_RESULT_TAPPABLE_SPEC,
    PET_EPIC_RUNES_FULL_SPEC,
    PET_MASS_EVOLVE_NORMAL_CONFIRM_SPEC,
    PET_MASS_EVOLVE_RARE_CONFIRM_SPEC,
    PET_MASS_EVOLVE_SELECTION_SPEC,
)


PET_LOW_TIER_SLOT_REGIONS: tuple[RelativeRegion, ...] = tuple(
    (x1, y1, x2, y2)
    for y1, y2 in (
        (0.330, 0.441),
        (0.469, 0.580),
        (0.607, 0.718),
        (0.746, 0.857),
    )
    for x1, x2 in (
        (0.555, 0.607),
        (0.622, 0.674),
        (0.690, 0.742),
        (0.757, 0.809),
    )
)
PET_LOW_TIER_NORMAL = "normal"
PET_LOW_TIER_RARE = "rare"
PET_LOW_TIER_NORMAL_CALIBRATION = LinearGapCalibration(0.05, 0.09)
PET_LOW_TIER_RARE_CALIBRATION = LinearGapCalibration(0.10, 0.17)
PET_LOW_TIER_MAX_BLUE_FOR_NORMAL = 0.10
PET_LOW_TIER_MAX_GREEN_FOR_RARE = 0.08
PET_MASS_EVOLVE_TIER_MARGIN = 0.20


@dataclass(frozen=True)
class PetLowTierSlotReading:
    slot: int
    region: RelativeRegion
    green_fraction: float
    blue_fraction: float
    tier: str | None
    confidence: float


@dataclass(frozen=True)
class PetMassEvolveConfirmationReading:
    normal_confidence: float
    rare_confidence: float
    tier: str | None
    confidence: float


class PetLowTierCandidateDetector:
    """Locate only unambiguous Normal/Rare primary candidates on a clean grid."""

    evaluation_id = CANDIDATE_PET_LOW_TIER

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._combine = LocalCvDetector(
            PET_COMBINE_ACTIVE_SPEC, asset_root=asset_root
        )
        self._prompt = LocalCvDetector(
            PET_COMBINE_EVOLVE_PROMPT_SPEC, asset_root=asset_root
        )
        self._blockers = tuple(
            LocalCvDetector(spec, asset_root=asset_root)
            for spec in (
                PET_MASS_EVOLVE_SELECTION_SPEC,
                PET_COMBINE_ALL_CONFIRM_SPEC,
                PET_COMBINE_NO_MATERIAL_SPEC,
                PET_EPIC_RUNES_FULL_SPEC,
                PET_MASS_EVOLVE_NORMAL_CONFIRM_SPEC,
                PET_MASS_EVOLVE_RARE_CONFIRM_SPEC,
            )
        )
        self.asset_paths = tuple(
            path
            for detector in (self._combine, self._prompt, *self._blockers)
            for path in detector.asset_paths
        )

    def measure(self, frame: np.ndarray) -> tuple[PetLowTierSlotReading, ...]:
        _validate_frame(frame)
        combine = self._combine.measure(frame).semantic_confidence
        prompt = self._prompt.measure(frame).semantic_confidence
        blocked = max(
            detector.measure(frame).semantic_confidence
            for detector in self._blockers
        )
        gate = min(combine, prompt)
        if blocked >= SEMANTIC_CONFIDENCE_THRESHOLD:
            gate = 0.0

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        height, width = frame.shape[:2]
        readings = []
        for slot, region in enumerate(PET_LOW_TIER_SLOT_REGIONS):
            x1, y1, x2, y2 = region
            roi = hsv[
                int(y1 * height) : int(y2 * height),
                int(x1 * width) : int(x2 * width),
            ]
            hue, saturation, value = cv2.split(roi)
            vivid = (saturation >= 100) & (value >= 70)
            green_fraction = float(
                np.mean(vivid & (hue >= 40) & (hue <= 85))
            )
            blue_fraction = float(
                np.mean(vivid & (hue >= 90) & (hue <= 130))
            )
            normal = PET_LOW_TIER_NORMAL_CALIBRATION.confidence(
                green_fraction
            )
            rare = PET_LOW_TIER_RARE_CALIBRATION.confidence(blue_fraction)
            if blue_fraction >= PET_LOW_TIER_MAX_BLUE_FOR_NORMAL:
                normal = 0.0
            if green_fraction >= PET_LOW_TIER_MAX_GREEN_FOR_RARE:
                rare = 0.0

            tier = None
            confidence = 0.0
            if normal >= SEMANTIC_CONFIDENCE_THRESHOLD and rare == 0.0:
                tier = PET_LOW_TIER_NORMAL
                confidence = min(gate, normal)
            elif rare >= SEMANTIC_CONFIDENCE_THRESHOLD and normal == 0.0:
                tier = PET_LOW_TIER_RARE
                confidence = min(gate, rare)
            readings.append(
                PetLowTierSlotReading(
                    slot=slot,
                    region=region,
                    green_fraction=green_fraction,
                    blue_fraction=blue_fraction,
                    tier=tier,
                    confidence=confidence,
                )
            )
        return tuple(readings)

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        return tuple(
            Observation(
                name=CANDIDATE_PET_LOW_TIER,
                confidence=reading.confidence,
                source=ObservationSource.LOCAL_CV,
                value=reading.tier,
                region=reading.region,
            )
            for reading in self.measure(frame)
            if reading.tier is not None
            and reading.confidence >= SEMANTIC_CONFIDENCE_THRESHOLD
        )


class PetMassEvolveConfirmationDetector:
    """Emit one confirmation semantic carrying its explicit safe tier."""

    evaluation_id = LANDMARK_PET_MASS_EVOLVE_CONFIRMATION

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._normal = LocalCvDetector(
            PET_MASS_EVOLVE_NORMAL_CONFIRM_SPEC, asset_root=asset_root
        )
        self._rare = LocalCvDetector(
            PET_MASS_EVOLVE_RARE_CONFIRM_SPEC, asset_root=asset_root
        )
        self.asset_paths = (
            *self._normal.asset_paths,
            *self._rare.asset_paths,
        )

    def measure(self, frame: np.ndarray) -> PetMassEvolveConfirmationReading:
        normal = self._normal.measure(frame).semantic_confidence
        rare = self._rare.measure(frame).semantic_confidence
        tier = None
        confidence = 0.0
        if (
            normal >= SEMANTIC_CONFIDENCE_THRESHOLD
            and normal - rare >= PET_MASS_EVOLVE_TIER_MARGIN
        ):
            tier = PET_LOW_TIER_NORMAL
            confidence = normal
        elif (
            rare >= SEMANTIC_CONFIDENCE_THRESHOLD
            and rare - normal >= PET_MASS_EVOLVE_TIER_MARGIN
        ):
            tier = PET_LOW_TIER_RARE
            confidence = rare
        return PetMassEvolveConfirmationReading(
            normal_confidence=normal,
            rare_confidence=rare,
            tier=tier,
            confidence=confidence,
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if reading.tier is None:
            return ()
        return (
            Observation(
                name=LANDMARK_PET_MASS_EVOLVE_CONFIRMATION,
                confidence=reading.confidence,
                source=ObservationSource.LOCAL_CV,
                value=reading.tier,
                region=PET_MASS_EVOLVE_NORMAL_CONFIRM_SPEC.region,
            ),
        )


class PetCombineResultDetector:
    """Resolve the shared Pet RESULT and expose its generic tappable activity."""

    evaluation_id = LANDMARK_PET_COMBINE_RESULT

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._result = LocalCvDetector(
            PET_COMBINE_RESULT_TAPPABLE_SPEC, asset_root=asset_root
        )
        self.asset_paths = self._result.asset_paths

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self._result.measure(frame)
        if reading.semantic_confidence < SEMANTIC_CONFIDENCE_THRESHOLD:
            return ()
        return tuple(
            Observation(
                name=name,
                confidence=reading.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
                region=PET_COMBINE_RESULT_TAPPABLE_SPEC.region,
            )
            for name in (
                LANDMARK_PET_COMBINE_RESULT,
                ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
            )
        )


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
    "PET_LOW_TIER_MAX_BLUE_FOR_NORMAL",
    "PET_LOW_TIER_MAX_GREEN_FOR_RARE",
    "PET_LOW_TIER_NORMAL",
    "PET_LOW_TIER_NORMAL_CALIBRATION",
    "PET_LOW_TIER_RARE",
    "PET_LOW_TIER_RARE_CALIBRATION",
    "PET_LOW_TIER_SLOT_REGIONS",
    "PET_MASS_EVOLVE_TIER_MARGIN",
    "PetLowTierCandidateDetector",
    "PetLowTierSlotReading",
    "PetMassEvolveConfirmationDetector",
    "PetMassEvolveConfirmationReading",
    "PetCombineResultDetector",
)
