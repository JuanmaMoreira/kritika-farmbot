"""Operation-scoped visual activity for Character Mail Claim All."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.catalog import ACTIVITY_MAILBOX_CLAIM_PROCESSING
from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource

from .local_cv import LocalCvDetector
from .specs import LinearGapCalibration, MAILBOX_TITLE_SPEC


MAILBOX_CLAIM_PROCESSING_REGION: RelativeRegion = (0.47, 0.43, 0.53, 0.58)
MAILBOX_CLAIM_PROCESSING_CONFIDENCE_THRESHOLD = 0.80
MAILBOX_CLAIM_PROCESSING_HSV_LOWER = (75, 100, 80)
MAILBOX_CLAIM_PROCESSING_HSV_UPPER = (105, 255, 255)

# The bright cyan phase occupies at least 3.5% of the acquired spinner ROI;
# stable Mailbox frames contribute no pixels in this range. Dark rotation
# phases are deliberately passive false negatives, so completion must require
# stable absence across fresh frames rather than one negative sample.
MAILBOX_CLAIM_PROCESSING_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.0,
    positive_anchor=0.035,
)


@dataclass(frozen=True)
class MailboxClaimProcessingReading:
    cyan_fraction: float
    mailbox_title_confidence: float
    semantic_confidence: float


class MailboxClaimProcessingDetector:
    """Emit the acquired cyan spinner phase only inside a visible Mailbox."""

    evaluation_id = ACTIVITY_MAILBOX_CLAIM_PROCESSING

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._mailbox_title = LocalCvDetector(
            MAILBOX_TITLE_SPEC, asset_root=asset_root
        )
        self.asset_paths = self._mailbox_title.asset_paths

    def measure(self, frame: np.ndarray) -> MailboxClaimProcessingReading:
        _validate_frame(frame)
        title = self._mailbox_title.measure(frame)
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = MAILBOX_CLAIM_PROCESSING_REGION
        roi = frame[
            int(y1 * height) : int(y2 * height),
            int(x1 * width) : int(x2 * width),
        ]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.asarray(MAILBOX_CLAIM_PROCESSING_HSV_LOWER, dtype=np.uint8),
            np.asarray(MAILBOX_CLAIM_PROCESSING_HSV_UPPER, dtype=np.uint8),
        )
        cyan_fraction = float(np.count_nonzero(mask) / mask.size)
        activity_confidence = MAILBOX_CLAIM_PROCESSING_CALIBRATION.confidence(
            cyan_fraction
        )
        return MailboxClaimProcessingReading(
            cyan_fraction=cyan_fraction,
            mailbox_title_confidence=title.semantic_confidence,
            semantic_confidence=min(
                title.semantic_confidence, activity_confidence
            ),
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if (
            reading.semantic_confidence
            < MAILBOX_CLAIM_PROCESSING_CONFIDENCE_THRESHOLD
        ):
            return ()
        return (
            Observation(
                name=ACTIVITY_MAILBOX_CLAIM_PROCESSING,
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


__all__ = (
    "MAILBOX_CLAIM_PROCESSING_CALIBRATION",
    "MAILBOX_CLAIM_PROCESSING_CONFIDENCE_THRESHOLD",
    "MAILBOX_CLAIM_PROCESSING_HSV_LOWER",
    "MAILBOX_CLAIM_PROCESSING_HSV_UPPER",
    "MAILBOX_CLAIM_PROCESSING_REGION",
    "MailboxClaimProcessingDetector",
    "MailboxClaimProcessingReading",
)
