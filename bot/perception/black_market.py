"""Minimal fixed-grid GOLD perception for Black Market offers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from bot.geometry import RelativeRegion, normalize_relative_region
from bot.observations import Observation, ObservationSource
from bot.screen import template_match_score

from .specs import LinearGapCalibration


BLACK_MARKET_GOLD_OBSERVATION = "currency.black_market.gold"
BLACK_MARKET_GRID_ROWS = 5
BLACK_MARKET_GRID_COLUMNS = 2
BLACK_MARKET_SLOT_COUNT = BLACK_MARKET_GRID_ROWS * BLACK_MARKET_GRID_COLUMNS
BLACK_MARKET_GOLD_ASSET = Path("assets/ui/gold-coin-bm.png")
BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD = 0.80

# The two narrow x ranges are the useful part of the legacy column regions.
# Five equal row steps were then measured against historical and current-season
# 2712x1224 frames. Each region contains only the offer's currency icon area,
# not the item icon, item text, numeric price or account balances.
_COLUMN_RANGES = ((0.4355, 0.4628), (0.7459, 0.7736))
_ROW_ORIGIN = 0.285
_ROW_PITCH = 0.1328
_ROW_HEIGHT = 0.066


def _slot_regions() -> tuple[RelativeRegion, ...]:
    return tuple(
        normalize_relative_region(
            (
                _COLUMN_RANGES[column][0],
                _ROW_ORIGIN + row * _ROW_PITCH,
                _COLUMN_RANGES[column][1],
                _ROW_ORIGIN + row * _ROW_PITCH + _ROW_HEIGHT,
            )
        )
        for row in range(BLACK_MARKET_GRID_ROWS)
        for column in range(BLACK_MARKET_GRID_COLUMNS)
    )


BLACK_MARKET_GOLD_SLOT_REGIONS = _slot_regions()

# The anchors are provisional empirical bounds from the reviewed slot corpus.
# The negative anchor is its strongest reviewed negative slot-region match;
# the positive anchor is its weakest human-confirmed live GOLD match.
# Confidence remains a gap position, not a probability.
BLACK_MARKET_GOLD_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.5731779932975769,
    positive_anchor=0.9343795776367188,
)

TemplateLoader = Callable[[str, int], np.ndarray | None]


@dataclass(frozen=True)
class BlackMarketGoldReading:
    """Raw and calibrated GOLD evidence for one row-major offer slot."""

    slot_index: int
    row: int
    column: int
    raw_match_score: float
    semantic_confidence: float
    search_region: RelativeRegion


class BlackMarketGoldDetector:
    """Emit only confidently GOLD Black Market slots from a fixed 5x2 grid."""

    def __init__(
        self,
        *,
        asset_root: str | Path | None = None,
        asset_path: str | Path = BLACK_MARKET_GOLD_ASSET,
        template_loader: TemplateLoader | None = None,
    ) -> None:
        root = Path(asset_root) if asset_root is not None else Path.cwd()
        configured_path = Path(asset_path)
        if not configured_path.is_absolute():
            configured_path = root / configured_path
        self.asset_path = configured_path.resolve()
        if not self.asset_path.is_file():
            raise FileNotFoundError(
                f"Black Market GOLD template is unavailable: {self.asset_path}"
            )

        loader = template_loader or cv2.imread
        template = loader(str(self.asset_path), cv2.IMREAD_GRAYSCALE)
        if (
            template is None
            or not isinstance(template, np.ndarray)
            or template.ndim != 2
            or template.size == 0
            or template.dtype != np.uint8
        ):
            raise ValueError(
                "Black Market GOLD template must be a non-empty uint8 "
                f"grayscale image: {self.asset_path}"
            )
        self._template = template.copy()

    @property
    def template_shape(self) -> tuple[int, int]:
        return self._template.shape

    def measure(self, frame: np.ndarray) -> tuple[BlackMarketGoldReading, ...]:
        """Measure all ten slots without turning absence into positive evidence."""

        _validate_frame(frame)
        readings = []
        for slot_index, region in enumerate(BLACK_MARKET_GOLD_SLOT_REGIONS):
            raw_score = template_match_score(frame, self._template, region=region)
            if raw_score is None:
                raise ValueError(
                    f"GOLD template {self.template_shape} does not fit slot "
                    f"region {region} for frame {frame.shape}"
                )
            readings.append(
                BlackMarketGoldReading(
                    slot_index=slot_index,
                    row=slot_index // BLACK_MARKET_GRID_COLUMNS,
                    column=slot_index % BLACK_MARKET_GRID_COLUMNS,
                    raw_match_score=raw_score,
                    semantic_confidence=(
                        BLACK_MARKET_GOLD_CALIBRATION.confidence(raw_score)
                    ),
                    search_region=region,
                )
            )
        return tuple(readings)

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        """Emit row-major slot observations only above the safe GOLD threshold."""

        return tuple(
            Observation(
                name=BLACK_MARKET_GOLD_OBSERVATION,
                confidence=reading.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
                value=reading.slot_index,
                region=reading.search_region,
            )
            for reading in self.measure(frame)
            if reading.semantic_confidence
            >= BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD
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
