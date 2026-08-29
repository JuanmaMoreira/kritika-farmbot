"""Operation-scoped Socket observations with no navigation or sale policy."""

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


SOCKET_INCOMPATIBLE_OPAL_OBSERVATION = "item.socket.incompatible_opal"
SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION = (
    "activity.socket.enhance_animation_tappable"
)
SOCKET_OPAL_GRID_ROWS = 4
SOCKET_OPAL_GRID_COLUMNS = 4
SOCKET_OPAL_SLOT_COUNT = SOCKET_OPAL_GRID_ROWS * SOCKET_OPAL_GRID_COLUMNS
SOCKET_INCOMPATIBLE_OPAL_ASSET = Path("assets/ui/opal-blocked.png")
SOCKET_INCOMPATIBLE_OPAL_SELECTED_ASSET = Path(
    "assets/ui/opal-blocked-selected.png"
)
SOCKET_INCOMPATIBLE_OPAL_VARIANT_ASSETS = (
    SOCKET_INCOMPATIBLE_OPAL_SELECTED_ASSET,
)
SOCKET_INCOMPATIBLE_OPAL_CONFIDENCE_THRESHOLD = 0.80
SOCKET_ENHANCE_ANIMATION_CONFIDENCE_THRESHOLD = 0.80
SOCKET_ENHANCE_ANIMATION_MAX_CENTER_MEAN = 26.0

_OPAL_COLUMN_CENTERS = (0.583, 0.650, 0.718, 0.785)
_OPAL_ROW_CENTERS = (0.400, 0.540, 0.680, 0.820)


def _opal_slot_regions() -> tuple[RelativeRegion, ...]:
    return tuple(
        normalize_relative_region(
            (center_x - 0.040, center_y - 0.085,
             center_x + 0.040, center_y + 0.085)
        )
        for center_y in _OPAL_ROW_CENTERS
        for center_x in _OPAL_COLUMN_CENTERS
    )


SOCKET_OPAL_SLOT_REGIONS = _opal_slot_regions()
SOCKET_INCOMPATIBLE_OPAL_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.5263,
    positive_anchor=0.9501,
)

# The dark-stage observation is intentionally incomplete: bright flash frames
# remain UNKNOWN and therefore cannot authorize input. Within a future
# state-guarded Enhance All operation, the acquired black periphery separates
# tappable animation stages from the modal, no-material and stable Socket UI.
SOCKET_ENHANCE_ANIMATION_CALIBRATION = LinearGapCalibration(
    negative_anchor=0.612,
    positive_anchor=0.930,
)

TemplateLoader = Callable[[str, int], np.ndarray | None]


@dataclass(frozen=True)
class SocketIncompatibleOpalReading:
    slot_index: int
    row: int
    column: int
    raw_match_score: float
    semantic_confidence: float
    search_region: RelativeRegion


class SocketIncompatibleOpalDetector:
    """Emit only visible 4x4 slots carrying the full red incompatibility veil."""

    def __init__(
        self,
        *,
        asset_root: str | Path | None = None,
        asset_path: str | Path = SOCKET_INCOMPATIBLE_OPAL_ASSET,
        variant_asset_paths: tuple[
            str | Path, ...
        ] = SOCKET_INCOMPATIBLE_OPAL_VARIANT_ASSETS,
        template_loader: TemplateLoader | None = None,
    ) -> None:
        root = Path(asset_root) if asset_root is not None else Path.cwd()
        loader = template_loader or cv2.imread
        paths = []
        templates = []
        for configured_path in (asset_path, *variant_asset_paths):
            path = Path(configured_path)
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            if not path.is_file():
                raise FileNotFoundError(
                    "Socket incompatible-opal template is unavailable: "
                    f"{path}"
                )
            template = loader(str(path), cv2.IMREAD_GRAYSCALE)
            if (
                template is None
                or not isinstance(template, np.ndarray)
                or template.ndim != 2
                or template.size == 0
                or template.dtype != np.uint8
            ):
                raise ValueError(
                    "Socket incompatible-opal template must be non-empty "
                    f"uint8 grayscale: {path}"
                )
            paths.append(path)
            templates.append(template.copy())
        self.asset_paths = tuple(paths)
        self.asset_path = self.asset_paths[0]
        self._templates = tuple(templates)

    @property
    def template_shape(self) -> tuple[int, int]:
        return self._templates[0].shape

    @property
    def template_shapes(self) -> tuple[tuple[int, int], ...]:
        return tuple(item.shape for item in self._templates)

    def measure(
        self, frame: np.ndarray
    ) -> tuple[SocketIncompatibleOpalReading, ...]:
        _validate_frame(frame)
        readings = []
        for slot_index, region in enumerate(SOCKET_OPAL_SLOT_REGIONS):
            scores = tuple(
                template_match_score(frame, template, region=region)
                for template in self._templates
            )
            if any(score is None for score in scores):
                raise ValueError(
                    f"templates {self.template_shapes} do not fit slot {region}"
                )
            raw_score = max(
                float(score) for score in scores if score is not None
            )
            readings.append(
                SocketIncompatibleOpalReading(
                    slot_index=slot_index,
                    row=slot_index // SOCKET_OPAL_GRID_COLUMNS,
                    column=slot_index % SOCKET_OPAL_GRID_COLUMNS,
                    raw_match_score=raw_score,
                    semantic_confidence=(
                        SOCKET_INCOMPATIBLE_OPAL_CALIBRATION.confidence(raw_score)
                    ),
                    search_region=region,
                )
            )
        return tuple(readings)

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        return tuple(
            Observation(
                name=SOCKET_INCOMPATIBLE_OPAL_OBSERVATION,
                confidence=reading.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
                value=reading.slot_index,
                region=reading.search_region,
            )
            for reading in self.measure(frame)
            if reading.semantic_confidence
            >= SOCKET_INCOMPATIBLE_OPAL_CONFIDENCE_THRESHOLD
        )


@dataclass(frozen=True)
class SocketEnhanceAnimationReading:
    outer_dark_fraction: float
    center_mean: float
    semantic_confidence: float


class SocketEnhanceAnimationDetector:
    """Emit only conservative dark stages of the observed Enhance animation."""

    def measure(self, frame: np.ndarray) -> SocketEnhanceAnimationReading:
        _validate_frame(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        y1, y2 = int(0.12 * height), int(0.90 * height)
        left = gray[y1:y2, : int(0.18 * width)].reshape(-1)
        right = gray[y1:y2, int(0.82 * width) :].reshape(-1)
        center = gray[
            int(0.18 * height) : int(0.82 * height),
            int(0.22 * width) : int(0.78 * width),
        ]
        outer_dark_fraction = float(
            np.count_nonzero(np.concatenate((left, right)) < 25)
            / (left.size + right.size)
        )
        return SocketEnhanceAnimationReading(
            outer_dark_fraction=outer_dark_fraction,
            center_mean=float(center.mean()),
            semantic_confidence=SOCKET_ENHANCE_ANIMATION_CALIBRATION.confidence(
                outer_dark_fraction
            ),
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        reading = self.measure(frame)
        if (
            reading.semantic_confidence
            < SOCKET_ENHANCE_ANIMATION_CONFIDENCE_THRESHOLD
            or reading.center_mean > SOCKET_ENHANCE_ANIMATION_MAX_CENTER_MEAN
        ):
            return ()
        return (
            Observation(
                name=SOCKET_ENHANCE_ANIMATION_TAPPABLE_OBSERVATION,
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
