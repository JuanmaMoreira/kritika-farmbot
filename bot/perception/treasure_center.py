"""Treasure Center title and Gold/Karat content detectors over HIL evidence.

Standalone construction plus one promoted title spec (same split as the
Trading precedent): the base landmark joins the default engine so
``screen.treasure`` resolves in normal runtime, while the tab-like
content signals (popup labels/icons, grid gold, result state and the
bottom-bar currency) join standalone in ``TREASURE_SCOPE`` and promote
with the E2 runtime consumer.

E2 calibration (frames under ``artifacts/hil_treasure_a/``, archival
``artifacts/acquisition-inventory-relief-chain/treasure-*`` and
``screencaps/batch`` Treasure positives):

- title: LocalCvSpec over three human-confirmed renderings of the same
  top banner (bright Sept grid ``treasure_title.png``, dimmed single
  result ``treasure_title_dimmed.png``, April grid
  ``treasure_title_april.png``). Max raw over variants: current
  grid/popup/result 1.00, April grid 1.00, April weapon-row result
  1.00; same-plate banners (Combine/Guild Battle) <= 0.49, Lobby and
  Trading <= 0.23. Calibration (0.52, 0.90): every confirmed
  non-Treasure frame emits nothing, every in-scope Treasure state
  emits with confidence 1.0. Known limits (documented, fail-closed):
  gem-row results and the archival fully-covered karat banner stay
  below anchor and never resolve; absence of title never authorizes
  input.
- grid gold: yellow HSV fraction in the Gold tile Needs row
  (T0 0.118, T1 0.110 with popup overlap; dimmed result 0.002,
  archival dimmed grid 0.000, Lobby 0.000). Calibration (0.02, 0.08),
  title-gated (Trading frames show 0.073 here but carry no title).
- selector popup: yellow fraction of the ``1(Open)`` label
  (T1 0.207; every titled non-popup frame 0.000). Calibration
  (0.05, 0.12), title-gated. Repeat label ``10(Open)`` (T1 0.197;
  grid spillover 0.092) is the repeat-availability signal,
  calibration (0.12, 0.16), title- and popup-gated.
- button currency: gold-key yellow vs karat magenta in the icon ROIs.
  Gold positives (T1 center icons 0.090, T2 bottom bar 0.133);
  karat positives (archival K bottom bar 0.122-0.172, gold 0.004);
  titled negatives show 0.000 purple everywhere. Gold calibration
  (0.05, 0.08); karat calibration (0.03, 0.09). Center-popup karat
  has no live positive (HIL_NOT_EXERCISED); the same icon ROIs apply
  once a popup is present, and missing Gold alone already blocks.
- result: yellow fraction of the open-chest region (T2 0.390,
  archival K 0.426; titled non-result <= 0.029). Calibration
  (0.08, 0.25), title-gated (current-device results keep the title
  at 1.00 via the dimmed variant).

All content signals require a positive title reading first (same gate
as Trading rows): without the base landmark nothing is emitted, so a
foreign screen can never borrow Treasure currency vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource
from bot.treasure_center_semantics import (
    INDICATOR_TREASURE_GOLD_KEY_REPEAT,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    INDICATOR_TREASURE_KARAT_BASE,
    INDICATOR_TREASURE_KARAT_REPEAT,
    INDICATOR_TREASURE_RESULT,
    INDICATOR_TREASURE_SELECTOR_POPUP,
    LANDMARK_TREASURE_TITLE,
)

from .local_cv import LocalCvDetector
from .specs import LinearGapCalibration, LocalCvSpec


TREASURE_TITLE_REGION: RelativeRegion = (0.38, 0.07, 0.62, 0.19)

TREASURE_TITLE_SPEC = LocalCvSpec(
    LANDMARK_TREASURE_TITLE,
    Path("assets/ui/landmarks/treasure/treasure_title.png"),
    TREASURE_TITLE_REGION,
    # Same-plate banners <= 0.49; in-scope states 1.00 (April grid 1.00
    # via its variant, current result 1.00 via the dimmed variant).
    LinearGapCalibration(0.52, 0.90),
    variant_asset_paths=(
        Path("assets/ui/landmarks/treasure/treasure_title_dimmed.png"),
        Path("assets/ui/landmarks/treasure/treasure_title_april.png"),
    ),
)

TREASURE_CENTER_SPECS = (TREASURE_TITLE_SPEC,)

# Gold tile Needs row (3rd chest tile) in grid state.
TREASURE_GRID_GOLD_REGION: RelativeRegion = (0.575, 0.43, 0.69, 0.52)
TREASURE_GRID_GOLD_CALIBRATION = LinearGapCalibration(0.02, 0.08)

# Center popup ``1(Open)`` / ``10(Open)`` labels.
TREASURE_SINGLE_LABEL_REGION: RelativeRegion = (0.575, 0.515, 0.645, 0.56)
TREASURE_REPEAT_LABEL_REGION: RelativeRegion = (0.66, 0.525, 0.715, 0.56)
TREASURE_SINGLE_LABEL_CALIBRATION = LinearGapCalibration(0.05, 0.12)
TREASURE_REPEAT_LABEL_CALIBRATION = LinearGapCalibration(0.12, 0.16)

# Center popup key/gem icons above each label.
TREASURE_SINGLE_ICON_REGION: RelativeRegion = (0.585, 0.42, 0.635, 0.51)
TREASURE_REPEAT_ICON_REGION: RelativeRegion = (0.655, 0.42, 0.705, 0.51)

# Result bottom bar (Video / 1(Open) / 10(Open)) icons.
TREASURE_BAR_SINGLE_ICON_REGION: RelativeRegion = (0.235, 0.78, 0.295, 0.86)
TREASURE_BAR_REPEAT_ICON_REGION: RelativeRegion = (0.305, 0.78, 0.365, 0.86)

TREASURE_GOLD_CALIBRATION = LinearGapCalibration(0.05, 0.08)
TREASURE_KARAT_CALIBRATION = LinearGapCalibration(0.03, 0.09)

# Open glowing chest at result center.
TREASURE_RESULT_REGION: RelativeRegion = (0.42, 0.55, 0.60, 0.80)
TREASURE_RESULT_CALIBRATION = LinearGapCalibration(0.08, 0.25)

TREASURE_GOLD_HSV_LOWER = (15, 120, 120)
TREASURE_GOLD_HSV_UPPER = (35, 255, 255)
TREASURE_KARAT_HSV_LOWER = (135, 80, 80)
TREASURE_KARAT_HSV_UPPER = (165, 255, 255)

TREASURE_CONTENT_CONFIDENCE_THRESHOLD = 0.50


@dataclass(frozen=True)
class TreasureContentReading:
    title_confidence: float
    grid_gold_confidence: float
    popup_confidence: float
    repeat_label_confidence: float
    single_gold_confidence: float
    single_karat_confidence: float
    repeat_gold_confidence: float
    repeat_karat_confidence: float
    bar_single_gold_confidence: float
    bar_single_karat_confidence: float
    bar_repeat_gold_confidence: float
    bar_repeat_karat_confidence: float
    result_confidence: float
    semantic_confidence: float


class TreasureContentDetector:
    """Emit Treasure popup/result/currency evidence under a title gate.

    The title detector owns the only asset paths; every content signal
    additionally requires ``title_confidence > 0`` so foreign screens
    never borrow Treasure vocabulary. Confidence of a composite signal
    is the minimum of its gated components (Trading rows idiom).
    """

    evaluation_id = "indicator.treasure_content"

    def __init__(self, *, asset_root: str | Path | None = None) -> None:
        self._title = LocalCvDetector(
            TREASURE_TITLE_SPEC, asset_root=asset_root
        )
        self.asset_paths = (*self._title.asset_paths,)

    def measure(self, frame: np.ndarray) -> TreasureContentReading:
        _validate_frame(frame)
        title = self._title.measure(frame).semantic_confidence
        grid_gold = _gold_fraction(frame, TREASURE_GRID_GOLD_REGION)
        popup = _gold_fraction(frame, TREASURE_SINGLE_LABEL_REGION)
        repeat_label = _gold_fraction(frame, TREASURE_REPEAT_LABEL_REGION)
        single_gold = _gold_fraction(frame, TREASURE_SINGLE_ICON_REGION)
        single_karat = _karat_fraction(frame, TREASURE_SINGLE_ICON_REGION)
        repeat_gold = _gold_fraction(frame, TREASURE_REPEAT_ICON_REGION)
        repeat_karat = _karat_fraction(frame, TREASURE_REPEAT_ICON_REGION)
        bar_single_gold = _gold_fraction(
            frame, TREASURE_BAR_SINGLE_ICON_REGION
        )
        bar_single_karat = _karat_fraction(
            frame, TREASURE_BAR_SINGLE_ICON_REGION
        )
        bar_repeat_gold = _gold_fraction(
            frame, TREASURE_BAR_REPEAT_ICON_REGION
        )
        bar_repeat_karat = _karat_fraction(
            frame, TREASURE_BAR_REPEAT_ICON_REGION
        )
        result = _gold_fraction(frame, TREASURE_RESULT_REGION)
        reading = TreasureContentReading(
            title_confidence=title,
            grid_gold_confidence=TREASURE_GRID_GOLD_CALIBRATION.confidence(
                grid_gold
            ),
            popup_confidence=TREASURE_SINGLE_LABEL_CALIBRATION.confidence(
                popup
            ),
            repeat_label_confidence=TREASURE_REPEAT_LABEL_CALIBRATION.confidence(
                repeat_label
            ),
            single_gold_confidence=TREASURE_GOLD_CALIBRATION.confidence(
                single_gold
            ),
            single_karat_confidence=TREASURE_KARAT_CALIBRATION.confidence(
                single_karat
            ),
            repeat_gold_confidence=TREASURE_GOLD_CALIBRATION.confidence(
                repeat_gold
            ),
            repeat_karat_confidence=TREASURE_KARAT_CALIBRATION.confidence(
                repeat_karat
            ),
            bar_single_gold_confidence=TREASURE_GOLD_CALIBRATION.confidence(
                bar_single_gold
            ),
            bar_single_karat_confidence=TREASURE_KARAT_CALIBRATION.confidence(
                bar_single_karat
            ),
            bar_repeat_gold_confidence=TREASURE_GOLD_CALIBRATION.confidence(
                bar_repeat_gold
            ),
            bar_repeat_karat_confidence=TREASURE_KARAT_CALIBRATION.confidence(
                bar_repeat_karat
            ),
            result_confidence=TREASURE_RESULT_CALIBRATION.confidence(result),
            semantic_confidence=title,
        )
        return reading

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if reading.title_confidence <= 0.0:
            return ()
        found: list[Observation] = []
        popup = (
            reading.popup_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        result = (
            reading.result_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        if popup:
            found.append(
                Observation(
                    name=INDICATOR_TREASURE_SELECTOR_POPUP,
                    confidence=reading.popup_confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        if result:
            found.append(
                Observation(
                    name=INDICATOR_TREASURE_RESULT,
                    confidence=reading.result_confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        single_gold = (
            reading.single_gold_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
            and reading.single_karat_confidence
            < TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        repeat_gold = (
            reading.repeat_label_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
            and reading.repeat_gold_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
            and reading.repeat_karat_confidence
            < TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        bar_single_gold = (
            result
            and reading.bar_single_gold_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
            and reading.bar_single_karat_confidence
            < TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        bar_repeat_gold = (
            result
            and reading.bar_repeat_gold_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
            and reading.bar_repeat_karat_confidence
            < TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        grid_gold = (
            reading.grid_gold_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        selector_parts: list[float] = []
        if grid_gold:
            selector_parts.append(reading.grid_gold_confidence)
        if popup and single_gold:
            selector_parts.append(
                min(
                    reading.popup_confidence,
                    reading.single_gold_confidence,
                )
            )
        if bar_single_gold:
            selector_parts.append(
                min(
                    reading.result_confidence,
                    reading.bar_single_gold_confidence,
                )
            )
        if selector_parts:
            found.append(
                Observation(
                    name=INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
                    confidence=max(selector_parts),
                    source=ObservationSource.LOCAL_CV,
                )
            )
        if (popup and repeat_gold) or bar_repeat_gold:
            if popup and repeat_gold:
                confidence = min(
                    reading.popup_confidence,
                    reading.repeat_label_confidence,
                    reading.repeat_gold_confidence,
                )
            else:
                confidence = min(
                    reading.result_confidence,
                    reading.bar_repeat_gold_confidence,
                )
            found.append(
                Observation(
                    name=INDICATOR_TREASURE_GOLD_KEY_REPEAT,
                    confidence=confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        single_karat = (
            reading.single_karat_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        repeat_karat = (
            popup
            and reading.repeat_karat_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        bar_single_karat = (
            result
            and reading.bar_single_karat_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        bar_repeat_karat = (
            result
            and reading.bar_repeat_karat_confidence
            >= TREASURE_CONTENT_CONFIDENCE_THRESHOLD
        )
        if (popup and single_karat) or bar_single_karat:
            if popup and single_karat:
                confidence = min(
                    reading.popup_confidence,
                    reading.single_karat_confidence,
                )
            else:
                confidence = min(
                    reading.result_confidence,
                    reading.bar_single_karat_confidence,
                )
            found.append(
                Observation(
                    name=INDICATOR_TREASURE_KARAT_BASE,
                    confidence=confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        if repeat_karat or bar_repeat_karat:
            if repeat_karat:
                confidence = min(
                    reading.popup_confidence,
                    reading.repeat_karat_confidence,
                )
            else:
                confidence = min(
                    reading.result_confidence,
                    reading.bar_repeat_karat_confidence,
                )
            found.append(
                Observation(
                    name=INDICATOR_TREASURE_KARAT_REPEAT,
                    confidence=confidence,
                    source=ObservationSource.LOCAL_CV,
                )
            )
        return tuple(found)


def _gold_fraction(frame: np.ndarray, region: RelativeRegion) -> float:
    return _hsv_fraction(
        frame, region, TREASURE_GOLD_HSV_LOWER, TREASURE_GOLD_HSV_UPPER
    )


def _karat_fraction(frame: np.ndarray, region: RelativeRegion) -> float:
    return _hsv_fraction(
        frame, region, TREASURE_KARAT_HSV_LOWER, TREASURE_KARAT_HSV_UPPER
    )


def _hsv_fraction(
    frame: np.ndarray,
    region: RelativeRegion,
    lower: tuple[int, int, int],
    upper: tuple[int, int, int],
) -> float:
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
        np.array(lower, dtype=np.uint8),
        np.array(upper, dtype=np.uint8),
    )
    return float(np.count_nonzero(mask) / mask.size)


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
    "TREASURE_BAR_REPEAT_ICON_REGION",
    "TREASURE_BAR_SINGLE_ICON_REGION",
    "TREASURE_CENTER_SPECS",
    "TREASURE_CONTENT_CONFIDENCE_THRESHOLD",
    "TREASURE_GOLD_CALIBRATION",
    "TREASURE_GRID_GOLD_CALIBRATION",
    "TREASURE_GRID_GOLD_REGION",
    "TREASURE_KARAT_CALIBRATION",
    "TREASURE_REPEAT_ICON_REGION",
    "TREASURE_REPEAT_LABEL_CALIBRATION",
    "TREASURE_REPEAT_LABEL_REGION",
    "TREASURE_RESULT_CALIBRATION",
    "TREASURE_RESULT_REGION",
    "TREASURE_SINGLE_ICON_REGION",
    "TREASURE_SINGLE_LABEL_CALIBRATION",
    "TREASURE_SINGLE_LABEL_REGION",
    "TREASURE_TITLE_REGION",
    "TREASURE_TITLE_SPEC",
    "TreasureContentDetector",
    "TreasureContentReading",
)
