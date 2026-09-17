"""Trading Center tab and list-rows detectors over HIL-calibrated evidence.

Standalone construction only (not wired into the default perception
engine): a future flow promotes these to a scope once a runtime consumer
needs them every session. Gating mirrors the Daily precedent — Trading
title plus the active-tab signal — with color-fill tab discrimination
(text-only templates cannot separate the glowing active tab from the dim
inactive one: 0.93 vs 1.00 raw) and structural row-divider counts for
list-populated evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource
from bot.trading_center_semantics import (
    INDICATOR_TRADING_GENERAL_ACTIVE,
    INDICATOR_TRADING_KEYS_ACTIVE,
    INDICATOR_TRADING_KEYS_ROWS,
    INDICATOR_TRADING_MATERIAL_ROWS,
    LANDMARK_TRADING_CENTER_TITLE,
)

from .local_cv import LocalCvDetector
from .specs import LinearGapCalibration, LocalCvSpec


TRADING_CENTER_TITLE_SPEC = LocalCvSpec(
    LANDMARK_TRADING_CENTER_TITLE,
    Path("assets/ui/landmarks/trading-center/trading_center_title.png"),
    (0.28, 0.10, 0.44, 0.19),
    # 8/8 HIL Trading frames score 1.00; clean Lobby scores 0.52.
    LinearGapCalibration(0.55, 0.95),
)

# Full tab buttons (background fill discriminates, not the shared text).
TRADING_GENERAL_TAB_REGION: RelativeRegion = (0.248, 0.20, 0.322, 0.27)
TRADING_KEYS_TAB_REGION: RelativeRegion = (0.445, 0.20, 0.548, 0.27)

# Active buttons glow orange; inactive buttons and Lobby contribute little
# orange here. HIL fractions: general 0.528 active vs 0.130/0.000;
# keys 0.395 active vs 0.120/0.000.
TRADING_TAB_HSV_LOWER = (10, 110, 120)
TRADING_TAB_HSV_UPPER = (32, 255, 255)
TRADING_GENERAL_TAB_CALIBRATION = LinearGapCalibration(0.20, 0.45)
TRADING_KEYS_TAB_CALIBRATION = LinearGapCalibration(0.20, 0.32)
TRADING_TAB_CONFIDENCE_THRESHOLD = 0.50

# List area between the column headers and the panel bottom, clear of the
# Trade buttons on the right. Row dividers are the strongest horizontal
# edges here: HIL projection counts 5 on every Trading frame, 0 on clean
# Lobby. Band detection starts slightly higher to include the top divider.
TRADING_LIST_REGION: RelativeRegion = (0.22, 0.36, 0.60, 0.94)
TRADING_BANDS_REGION: RelativeRegion = (0.22, 0.34, 0.60, 0.95)
TRADING_ROWS_CALIBRATION = LinearGapCalibration(0.0, 5.0)
TRADING_ROWS_CONFIDENCE_THRESHOLD = 0.80

TRADING_CENTER_SPECS = (TRADING_CENTER_TITLE_SPEC,)


@dataclass(frozen=True)
class TradingTabsReading:
    general_orange_fraction: float
    keys_orange_fraction: float
    title_confidence: float
    general_confidence: float
    keys_confidence: float


class TradingTabsDetector:
    """Emit the glowing active tab; both labels feed contradiction checks."""

    evaluation_id = "indicator.trading_tab_active"

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._title = LocalCvDetector(
            TRADING_CENTER_TITLE_SPEC, asset_root=asset_root
        )
        self.asset_paths = (*self._title.asset_paths,)

    def measure(self, frame: np.ndarray) -> TradingTabsReading:
        _validate_frame(frame)
        title = self._title.measure(frame)
        general_fraction = _orange_fraction(frame, TRADING_GENERAL_TAB_REGION)
        keys_fraction = _orange_fraction(frame, TRADING_KEYS_TAB_REGION)
        if title.semantic_confidence <= 0.0:
            general_confidence = 0.0
            keys_confidence = 0.0
        else:
            general_confidence = TRADING_GENERAL_TAB_CALIBRATION.confidence(
                general_fraction
            )
            keys_confidence = TRADING_KEYS_TAB_CALIBRATION.confidence(
                keys_fraction
            )
        return TradingTabsReading(
            general_orange_fraction=general_fraction,
            keys_orange_fraction=keys_fraction,
            title_confidence=title.semantic_confidence,
            general_confidence=general_confidence,
            keys_confidence=keys_confidence,
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        found: list[Observation] = []
        if reading.general_confidence >= TRADING_TAB_CONFIDENCE_THRESHOLD:
            found.append(
                Observation(
                    name=INDICATOR_TRADING_GENERAL_ACTIVE,
                    confidence=reading.general_confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        if reading.keys_confidence >= TRADING_TAB_CONFIDENCE_THRESHOLD:
            found.append(
                Observation(
                    name=INDICATOR_TRADING_KEYS_ACTIVE,
                    confidence=reading.keys_confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        return tuple(found)


@dataclass(frozen=True)
class TradingRowsReading:
    divider_count: int
    title_confidence: float
    general_confidence: float
    keys_confidence: float
    semantic_confidence: float


class TradingRowsDetector:
    """Emit list-populated evidence labeled by the active tab.

    The structural signal (row dividers) cannot tell material rows from
    key rows; the co-observed active tab disambiguates, which is why one
    detector emits the tab-specific rows label.
    """

    evaluation_id = "indicator.trading_list_rows"

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._title = LocalCvDetector(
            TRADING_CENTER_TITLE_SPEC, asset_root=asset_root
        )
        self._tabs = TradingTabsDetector(asset_root=asset_root)
        self.asset_paths = (
            *self._title.asset_paths,
            *self._tabs.asset_paths,
        )

    def measure(self, frame: np.ndarray) -> TradingRowsReading:
        _validate_frame(frame)
        title = self._title.measure(frame)
        tabs = self._tabs.measure(frame)
        count = _divider_count(frame, TRADING_LIST_REGION)
        rows_confidence = TRADING_ROWS_CALIBRATION.confidence(count)
        if title.semantic_confidence <= 0.0:
            semantic_confidence = 0.0
        else:
            semantic_confidence = min(
                rows_confidence,
                max(tabs.general_confidence, tabs.keys_confidence),
            )
        return TradingRowsReading(
            divider_count=count,
            title_confidence=title.semantic_confidence,
            general_confidence=tabs.general_confidence,
            keys_confidence=tabs.keys_confidence,
            semantic_confidence=semantic_confidence,
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if reading.semantic_confidence < TRADING_ROWS_CONFIDENCE_THRESHOLD:
            return ()
        if reading.general_confidence >= reading.keys_confidence:
            name = INDICATOR_TRADING_MATERIAL_ROWS
            confidence = min(
                reading.semantic_confidence, reading.general_confidence
            )
        else:
            name = INDICATOR_TRADING_KEYS_ROWS
            confidence = min(
                reading.semantic_confidence, reading.keys_confidence
            )
        return (
            Observation(
                name=name,
                confidence=confidence,
                source=ObservationSource.LOCAL_CV,
            ),
        )


def _orange_fraction(frame: np.ndarray, region: RelativeRegion) -> float:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (
        int(region[0] * width),
        int(region[1] * height),
        int(region[2] * width),
        int(region[3] * height),
    )
    roi = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.array(TRADING_TAB_HSV_LOWER, dtype=np.uint8),
        np.array(TRADING_TAB_HSV_UPPER, dtype=np.uint8),
    )
    return float(np.count_nonzero(mask) / mask.size)


def _divider_positions(frame: np.ndarray, region: RelativeRegion) -> list[float]:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = (
        int(region[0] * width),
        int(region[1] * height),
        int(region[2] * width),
        int(region[3] * height),
    )
    roi = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    profile = edges.mean(axis=1) / 255.0
    min_distance = int(0.10 * roi.shape[0])
    peaks: list[int] = []
    for index in range(1, len(profile) - 1):
        if (
            profile[index] >= 0.35
            and profile[index] >= profile[index - 1]
            and profile[index] > profile[index + 1]
        ):
            if not peaks or index - peaks[-1] >= min_distance:
                peaks.append(index)
    top = region[1]
    span = region[3] - region[1]
    return [top + peak / roi.shape[0] * span for peak in peaks]


def _long_dividers(frame: np.ndarray) -> list[float]:
    """Position-accurate dividers from long horizontal edges (HIL tuned)."""
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=int(width * 0.15),
        minLineLength=int(width * 0.30),
        maxLineGap=10,
    )
    found: list[float] = []
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4).tolist():
            if (
                abs(y2 - y1) < 5
                and min(x1, x2) < width * 0.30
                and max(x1, x2) > width * 0.60
            ):
                found.append((y1 + y2) / 2 / height)
    found.sort()
    clustered = list(found[:1])
    for value in found[1:]:
        if value - clustered[-1] > 0.012:
            clustered.append(value)
    return clustered


def _divider_count(frame: np.ndarray, region: RelativeRegion) -> int:
    return len(_divider_positions(frame, region))


# Content zone edges: column-header bottom and panel bottom in normalized
# frame coordinates (HIL measured).
TRADING_LIST_TOP = 0.35
TRADING_LIST_BOTTOM = 0.95


# Calibrated row pitch (HIL: 0.1418 stable across captures and tabs).
TRADING_ROW_PITCH = 0.1418

# A complete row spans ~pitch of frame height. Bands below the complete
# threshold are partial rows cut by the content-zone edges; slivers below
# the visible threshold are padding or unreadable fragments ignored by
# both the bands and the row-title source, keeping the top-to-bottom
# correspondence deterministic.
TRADING_COMPLETE_BAND_HEIGHT = 0.12
TRADING_VISIBLE_BAND_HEIGHT = 0.03


def row_bands(frame: np.ndarray) -> tuple[tuple[float, float, float, bool], ...]:
    """Return (top, bottom, center_y, complete) bands for the list area.

    Divider positions are fitted to the calibrated pitch grid, so one
    missed divider cannot shift row indices: every visible fragment maps
    to exactly one grid row. Falls back to raw internal bands when fewer
    than two dividers are detected. Edge bands clipped by the content
    zone are partial; slivers below the visible threshold are dropped.
    """
    _validate_frame(frame)
    long_lines = [
        divider
        for divider in _long_dividers(frame)
        if TRADING_LIST_TOP - 0.03 <= divider <= TRADING_LIST_BOTTOM + 0.03
    ]
    if len(long_lines) >= 2:
        grid = _fit_grid(long_lines)
    else:
        grid = _fit_grid(
            [
                divider
                for divider in _divider_positions(frame, TRADING_BANDS_REGION)
                if TRADING_LIST_TOP - 0.03 <= divider <= TRADING_LIST_BOTTOM + 0.03
            ]
        )
    if grid is None:
        return _raw_bands(sorted(long_lines))
    bands: list[tuple[float, float, float, bool]] = []
    line = grid
    while line < TRADING_LIST_BOTTOM - TRADING_VISIBLE_BAND_HEIGHT:
        top = max(line, TRADING_LIST_TOP)
        bottom = min(line + TRADING_ROW_PITCH, TRADING_LIST_BOTTOM)
        height = bottom - top
        if height < TRADING_VISIBLE_BAND_HEIGHT:
            line += TRADING_ROW_PITCH
            continue
        complete = (
            height >= TRADING_COMPLETE_BAND_HEIGHT
            and top >= line - 0.005
            and bottom <= line + TRADING_ROW_PITCH + 0.005
        )
        bands.append((top, bottom, (top + bottom) / 2, complete))
        line += TRADING_ROW_PITCH
    return tuple(bands)


def _fit_grid(dividers: list[float]) -> float | None:
    """Fit divider phase to the pitch grid; None when underdetermined."""
    if len(dividers) < 2:
        return None
    reference = TRADING_LIST_TOP
    residuals = sorted(
        divider - (reference + round((divider - reference) / TRADING_ROW_PITCH)
                   * TRADING_ROW_PITCH)
        for divider in dividers
    )
    phase = reference + residuals[len(residuals) // 2]
    line = phase
    while line - TRADING_ROW_PITCH >= TRADING_LIST_TOP - TRADING_ROW_PITCH:
        line -= TRADING_ROW_PITCH
    while line < TRADING_LIST_TOP - TRADING_ROW_PITCH:
        line += TRADING_ROW_PITCH
    return line


def _raw_bands(dividers: list[float]) -> tuple[tuple[float, float, float, bool], ...]:
    edges = [TRADING_LIST_TOP, *sorted(dividers), TRADING_LIST_BOTTOM]
    bands: list[tuple[float, float, float, bool]] = []
    for top, bottom in zip(edges, edges[1:]):
        height = bottom - top
        if height < TRADING_VISIBLE_BAND_HEIGHT:
            continue
        bands.append(
            (top, bottom, (top + bottom) / 2, height >= TRADING_COMPLETE_BAND_HEIGHT)
        )
    return tuple(bands)


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
    "TRADING_BANDS_REGION",
    "TRADING_CENTER_SPECS",
    "TRADING_CENTER_TITLE_SPEC",
    "TRADING_COMPLETE_BAND_HEIGHT",
    "TRADING_GENERAL_TAB_CALIBRATION",
    "TRADING_GENERAL_TAB_REGION",
    "TRADING_KEYS_TAB_CALIBRATION",
    "TRADING_KEYS_TAB_REGION",
    "TRADING_LIST_BOTTOM",
    "TRADING_LIST_REGION",
    "TRADING_LIST_TOP",
    "TRADING_ROW_PITCH",
    "TRADING_ROWS_CALIBRATION",
    "TRADING_ROWS_CONFIDENCE_THRESHOLD",
    "TRADING_TAB_CONFIDENCE_THRESHOLD",
    "TRADING_VISIBLE_BAND_HEIGHT",
    "TradingRowsDetector",
    "TradingRowsReading",
    "TradingTabsDetector",
    "TradingTabsReading",
    "row_bands",
)
