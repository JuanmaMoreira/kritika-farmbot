"""Visual eligibility for the independent Daily Quests progress reward."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.catalog import (
    ACTIVITY_DAILY_QUESTS_LOADING,
    INDICATOR_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    INDICATOR_DAILY_QUESTS_ROWS_POPULATED,
)
from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource

from .local_cv import LocalCvDetector
from .specs import (
    DAILY_QUESTS_TAB_ACTIVE_SPEC,
    DAILY_QUESTS_TITLE_SPEC,
    LinearGapCalibration,
)


DAILY_QUESTS_PROGRESS_REWARD_REGION: RelativeRegion = (
    0.62,
    0.25,
    0.78,
    0.39,
)
DAILY_QUESTS_PROGRESS_REWARD_CONFIDENCE_THRESHOLD = 0.80
DAILY_QUESTS_PROGRESS_REWARD_HSV_LOWER = (75, 100, 80)
DAILY_QUESTS_PROGRESS_REWARD_HSV_UPPER = (105, 255, 255)

# The acquired active 30-Karat button fills at least 26.29% of this exclusive
# upper reward ROI with cyan. Claimed, settled and row-claimable Daily states
# contribute no pixels in the same range.
DAILY_QUESTS_PROGRESS_REWARD_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.0,
    positive_anchor=0.2629,
)


@dataclass(frozen=True)
class DailyQuestsProgressRewardReading:
    cyan_fraction: float
    title_confidence: float
    daily_tab_confidence: float
    semantic_confidence: float


class DailyQuestsProgressRewardDetector:
    """Emit progress-reward eligibility only on the active Daily tab."""

    evaluation_id = INDICATOR_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._title = LocalCvDetector(
            DAILY_QUESTS_TITLE_SPEC, asset_root=asset_root
        )
        self._daily_tab = LocalCvDetector(
            DAILY_QUESTS_TAB_ACTIVE_SPEC, asset_root=asset_root
        )
        self.asset_paths = (
            *self._title.asset_paths,
            *self._daily_tab.asset_paths,
        )

    def measure(self, frame: np.ndarray) -> DailyQuestsProgressRewardReading:
        _validate_frame(frame)
        title = self._title.measure(frame)
        daily_tab = self._daily_tab.measure(frame)
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = DAILY_QUESTS_PROGRESS_REWARD_REGION
        roi = frame[
            int(y1 * height) : int(y2 * height),
            int(x1 * width) : int(x2 * width),
        ]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.asarray(
                DAILY_QUESTS_PROGRESS_REWARD_HSV_LOWER, dtype=np.uint8
            ),
            np.asarray(
                DAILY_QUESTS_PROGRESS_REWARD_HSV_UPPER, dtype=np.uint8
            ),
        )
        cyan_fraction = float(np.count_nonzero(mask) / mask.size)
        reward_confidence = (
            DAILY_QUESTS_PROGRESS_REWARD_CALIBRATION.confidence(cyan_fraction)
        )
        return DailyQuestsProgressRewardReading(
            cyan_fraction=cyan_fraction,
            title_confidence=title.semantic_confidence,
            daily_tab_confidence=daily_tab.semantic_confidence,
            semantic_confidence=min(
                title.semantic_confidence,
                daily_tab.semantic_confidence,
                reward_confidence,
            ),
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if (
            reading.semantic_confidence
            < DAILY_QUESTS_PROGRESS_REWARD_CONFIDENCE_THRESHOLD
        ):
            return ()
        return (
            Observation(
                name=INDICATOR_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
                confidence=reading.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
            ),
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


# List region below the completion-rate header and above the panel bottom,
# clear of the upper dynamic chat band. Cream parchment rows are bright;
# the cleared/loading list background is near black.
DAILY_QUESTS_ROWS_REGION: RelativeRegion = (
    0.22,
    0.35,
    0.74,
    0.93,
)
DAILY_QUESTS_ROWS_BRIGHT_VALUE = 180
DAILY_QUESTS_ROWS_CONFIDENCE_THRESHOLD = 0.80

# Acquired cold-open evidence: populated lists measure 0.4510..0.4742
# (pre-ready with spinner, final ready, warm ready and curated settled
# frames); the content-clear frame measures 0.0003. The Lobby sea renders
# brighter than the negative anchor, so this observation is only meaningful
# together with the Daily chrome gate enforced below; it never identifies a
# screen on its own.
DAILY_QUESTS_ROWS_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.0003,
    positive_anchor=0.4510,
)


@dataclass(frozen=True)
class DailyQuestsRowsReading:
    bright_fraction: float
    title_confidence: float
    daily_tab_confidence: float
    semantic_confidence: float


class DailyQuestsRowsDetector:
    """Emit list-populated evidence only on the active Daily tab."""

    evaluation_id = INDICATOR_DAILY_QUESTS_ROWS_POPULATED

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._title = LocalCvDetector(
            DAILY_QUESTS_TITLE_SPEC, asset_root=asset_root
        )
        self._daily_tab = LocalCvDetector(
            DAILY_QUESTS_TAB_ACTIVE_SPEC, asset_root=asset_root
        )
        self.asset_paths = (
            *self._title.asset_paths,
            *self._daily_tab.asset_paths,
        )

    def measure(self, frame: np.ndarray) -> DailyQuestsRowsReading:
        _validate_frame(frame)
        title = self._title.measure(frame)
        daily_tab = self._daily_tab.measure(frame)
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = DAILY_QUESTS_ROWS_REGION
        roi = frame[
            int(y1 * height) : int(y2 * height),
            int(x1 * width) : int(x2 * width),
        ]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        bright_fraction = float(
            np.count_nonzero(gray > DAILY_QUESTS_ROWS_BRIGHT_VALUE)
            / gray.size
        )
        rows_confidence = DAILY_QUESTS_ROWS_CALIBRATION.confidence(
            bright_fraction
        )
        return DailyQuestsRowsReading(
            bright_fraction=bright_fraction,
            title_confidence=title.semantic_confidence,
            daily_tab_confidence=daily_tab.semantic_confidence,
            semantic_confidence=min(
                title.semantic_confidence,
                daily_tab.semantic_confidence,
                rows_confidence,
            ),
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if (
            reading.semantic_confidence
            < DAILY_QUESTS_ROWS_CONFIDENCE_THRESHOLD
        ):
            return ()
        return (
            Observation(
                name=INDICATOR_DAILY_QUESTS_ROWS_POPULATED,
                confidence=reading.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
            ),
        )


# Tight ring ROI around the acquired loading-annulus location. It excludes
# the row action buttons, the K-coin reward icon, the progress-reward Claim
# and the top chrome, so only the spinner ring contributes cyan here.
DAILY_QUESTS_LOADING_REGION: RelativeRegion = (
    0.42,
    0.41,
    0.52,
    0.58,
)
DAILY_QUESTS_LOADING_CONFIDENCE_THRESHOLD = 0.80
DAILY_QUESTS_LOADING_HSV_LOWER = (75, 100, 80)
DAILY_QUESTS_LOADING_HSV_UPPER = (105, 255, 255)

# Seven acquired ring phases spanning ~0.7 s hold 0.0371..0.0389 with no
# phase modulation (the ROI contains the full annulus); 160+ ready, warm,
# settled and content-clear frames contribute no pixels in this range.
DAILY_QUESTS_LOADING_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.0,
    positive_anchor=0.0371,
)


@dataclass(frozen=True)
class DailyQuestsLoadingReading:
    cyan_fraction: float
    title_confidence: float
    daily_tab_confidence: float
    semantic_confidence: float


class DailyQuestsLoadingDetector:
    """Emit the loading ring only on the active Daily tab."""

    evaluation_id = ACTIVITY_DAILY_QUESTS_LOADING

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._title = LocalCvDetector(
            DAILY_QUESTS_TITLE_SPEC, asset_root=asset_root
        )
        self._daily_tab = LocalCvDetector(
            DAILY_QUESTS_TAB_ACTIVE_SPEC, asset_root=asset_root
        )
        self.asset_paths = (
            *self._title.asset_paths,
            *self._daily_tab.asset_paths,
        )

    def measure(self, frame: np.ndarray) -> DailyQuestsLoadingReading:
        _validate_frame(frame)
        title = self._title.measure(frame)
        daily_tab = self._daily_tab.measure(frame)
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = DAILY_QUESTS_LOADING_REGION
        roi = frame[
            int(y1 * height) : int(y2 * height),
            int(x1 * width) : int(x2 * width),
        ]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.asarray(
                DAILY_QUESTS_LOADING_HSV_LOWER, dtype=np.uint8
            ),
            np.asarray(
                DAILY_QUESTS_LOADING_HSV_UPPER, dtype=np.uint8
            ),
        )
        cyan_fraction = float(np.count_nonzero(mask) / mask.size)
        loading_confidence = DAILY_QUESTS_LOADING_CALIBRATION.confidence(
            cyan_fraction
        )
        return DailyQuestsLoadingReading(
            cyan_fraction=cyan_fraction,
            title_confidence=title.semantic_confidence,
            daily_tab_confidence=daily_tab.semantic_confidence,
            semantic_confidence=min(
                title.semantic_confidence,
                daily_tab.semantic_confidence,
                loading_confidence,
            ),
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if (
            reading.semantic_confidence
            < DAILY_QUESTS_LOADING_CONFIDENCE_THRESHOLD
        ):
            return ()
        return (
            Observation(
                name=ACTIVITY_DAILY_QUESTS_LOADING,
                confidence=reading.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
            ),
        )


__all__ = (
    "DAILY_QUESTS_PROGRESS_REWARD_CALIBRATION",
    "DAILY_QUESTS_PROGRESS_REWARD_CONFIDENCE_THRESHOLD",
    "DAILY_QUESTS_PROGRESS_REWARD_HSV_LOWER",
    "DAILY_QUESTS_PROGRESS_REWARD_HSV_UPPER",
    "DAILY_QUESTS_PROGRESS_REWARD_REGION",
    "DailyQuestsProgressRewardDetector",
    "DailyQuestsProgressRewardReading",
    "DAILY_QUESTS_ROWS_REGION",
    "DAILY_QUESTS_ROWS_BRIGHT_VALUE",
    "DAILY_QUESTS_ROWS_CALIBRATION",
    "DAILY_QUESTS_ROWS_CONFIDENCE_THRESHOLD",
    "DailyQuestsRowsDetector",
    "DailyQuestsRowsReading",
    "DAILY_QUESTS_LOADING_REGION",
    "DAILY_QUESTS_LOADING_CALIBRATION",
    "DAILY_QUESTS_LOADING_CONFIDENCE_THRESHOLD",
    "DAILY_QUESTS_LOADING_HSV_LOWER",
    "DAILY_QUESTS_LOADING_HSV_UPPER",
    "DailyQuestsLoadingDetector",
    "DailyQuestsLoadingReading",
)
