"""Clean-screen Guild Attendance state from the acquired button rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.catalog import (
    INDICATOR_GUILD_ATTENDANCE_ACTIVE,
    INDICATOR_GUILD_ATTENDANCE_COMPLETED,
    SEMANTIC_CONFIDENCE_THRESHOLD,
)
from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource

from .local_cv import LocalCvDetector
from .specs import (
    GUILD_MESSAGE_TAB_SPEC,
    LinearGapCalibration,
    QUICK_MENU_LOBBY_TILE_SPEC,
)


GUILD_ATTENDANCE_REGION: RelativeRegion = (0.448, 0.39, 0.46, 0.45)
GUILD_ATTENDANCE_CONFIDENCE_THRESHOLD = SEMANTIC_CONFIDENCE_THRESHOLD

# The narrow fill strip avoids the check mark, label, active badge and the
# transient check-in bubble. Pending positives measure V=167.163553..168.405978;
# completed positives measure V=81.891656..84.584060 in the curated corpus.
GUILD_ATTENDANCE_ACTIVE_CALIBRATION = LinearGapCalibration(
    negative_anchor=84.5840597758406,
    positive_anchor=167.16355334163552,
)
GUILD_ATTENDANCE_COMPLETED_CALIBRATION = LinearGapCalibration(
    negative_anchor=87.83644665836448,
    positive_anchor=170.4159402241594,
)


@dataclass(frozen=True)
class GuildAttendanceReading:
    value_mean: float
    guild_confidence: float
    quick_menu_confidence: float
    active_confidence: float
    completed_confidence: float


class GuildAttendanceDetector:
    """Emit exactly one acquired Attendance state on a clean Guild screen.

    Quick Menu deliberately suppresses both state observations. Its overlay
    covers part of the control and future navigation must not inherit a Guild
    business status alongside ``menu.quick``.
    """

    evaluation_id = "indicator.guild_attendance_state"

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self.region = GUILD_ATTENDANCE_REGION
        self.active_calibration = GUILD_ATTENDANCE_ACTIVE_CALIBRATION
        self.completed_calibration = GUILD_ATTENDANCE_COMPLETED_CALIBRATION
        self.confidence_threshold = GUILD_ATTENDANCE_CONFIDENCE_THRESHOLD
        self.quick_menu_confidence_threshold = SEMANTIC_CONFIDENCE_THRESHOLD
        self._guild = LocalCvDetector(
            GUILD_MESSAGE_TAB_SPEC, asset_root=asset_root
        )
        self._quick_menu = LocalCvDetector(
            QUICK_MENU_LOBBY_TILE_SPEC, asset_root=asset_root
        )
        self.asset_paths = tuple(
            dict.fromkeys(
                (*self._guild.asset_paths, *self._quick_menu.asset_paths)
            )
        )

    def measure(self, frame: np.ndarray) -> GuildAttendanceReading:
        _validate_frame(frame)
        guild = self._guild.measure(frame).semantic_confidence
        quick_menu = self._quick_menu.measure(frame).semantic_confidence
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = self.region
        roi = frame[
            int(y1 * height) : int(y2 * height),
            int(x1 * width) : int(x2 * width),
        ]
        value_mean = float(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 2].mean())

        if quick_menu >= self.quick_menu_confidence_threshold:
            active = completed = 0.0
        else:
            active = min(
                guild,
                self.active_calibration.confidence(value_mean),
            )
            completed = min(
                guild,
                self.completed_calibration.confidence(
                    255.0 - value_mean
                ),
            )
        return GuildAttendanceReading(
            value_mean=value_mean,
            guild_confidence=guild,
            quick_menu_confidence=quick_menu,
            active_confidence=active,
            completed_confidence=completed,
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        emitted = []
        for name, confidence in (
            (
                INDICATOR_GUILD_ATTENDANCE_ACTIVE,
                reading.active_confidence,
            ),
            (
                INDICATOR_GUILD_ATTENDANCE_COMPLETED,
                reading.completed_confidence,
            ),
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
    "GUILD_ATTENDANCE_ACTIVE_CALIBRATION",
    "GUILD_ATTENDANCE_COMPLETED_CALIBRATION",
    "GUILD_ATTENDANCE_CONFIDENCE_THRESHOLD",
    "GUILD_ATTENDANCE_REGION",
    "GuildAttendanceDetector",
    "GuildAttendanceReading",
)
