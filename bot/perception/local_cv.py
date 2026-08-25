"""Native-scale OpenCV template detector with preloaded assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from bot.geometry import RelativeRegion
from bot.observations import Observation, ObservationSource
from bot.screen import template_match_score

from .specs import LocalCvSpec

TemplateLoader = Callable[[str, int], np.ndarray | None]


@dataclass(frozen=True)
class LocalCvDetection:
    """Raw OpenCV evidence and its separately calibrated semantic confidence."""

    observation_name: str
    raw_match_score: float
    semantic_confidence: float
    search_region: RelativeRegion


class LocalCvDetector:
    """Detect one landmark using preloaded native-size rendering variants."""

    def __init__(
        self,
        spec: LocalCvSpec,
        *,
        asset_root: str | Path | None = None,
        template_loader: TemplateLoader | None = None,
    ) -> None:
        if not isinstance(spec, LocalCvSpec):
            raise ValueError("spec must be a LocalCvSpec")
        root = Path(asset_root) if asset_root is not None else Path.cwd()
        loader = template_loader or cv2.imread
        asset_paths = []
        templates = []
        for configured_path in (spec.asset_path, *spec.variant_asset_paths):
            asset_path = configured_path
            if not asset_path.is_absolute():
                asset_path = root / asset_path
            asset_path = asset_path.resolve()
            if not asset_path.is_file():
                raise FileNotFoundError(
                    f"Local CV template is unavailable: {asset_path}"
                )

            template = loader(str(asset_path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                raise ValueError(
                    f"Local CV template could not be decoded: {asset_path}"
                )
            if (
                not isinstance(template, np.ndarray)
                or template.ndim != 2
                or template.size == 0
                or template.dtype != np.uint8
            ):
                raise ValueError(
                    "Local CV template must be a non-empty uint8 grayscale "
                    f"image: {asset_path}"
                )
            asset_paths.append(asset_path)
            templates.append(template.copy())

        self.spec = spec
        self.asset_paths = tuple(asset_paths)
        self.asset_path = self.asset_paths[0]
        self._templates = tuple(templates)

    @property
    def template_shape(self) -> tuple[int, int]:
        return self._templates[0].shape

    @property
    def template_shapes(self) -> tuple[tuple[int, int], ...]:
        return tuple(template.shape for template in self._templates)

    def measure(self, frame: np.ndarray) -> LocalCvDetection:
        """Measure raw evidence and calibrate it without applying resolver policy."""

        _validate_frame(frame)
        raw_scores = tuple(
            template_match_score(frame, template, region=self.spec.region)
            for template in self._templates
        )
        compatible_scores = tuple(
            score for score in raw_scores if score is not None
        )
        if not compatible_scores:
            raise ValueError(
                f"Template set {self.template_shapes} does not fit search region "
                f"{self.spec.region} for frame {frame.shape}"
            )
        raw_score = max(compatible_scores)
        return LocalCvDetection(
            observation_name=self.spec.name,
            raw_match_score=raw_score,
            semantic_confidence=self.spec.calibration.confidence(raw_score),
            search_region=self.spec.region,
        )

    def detect(self, frame: np.ndarray) -> tuple[Observation, ...]:
        """Emit presence evidence only when calibrated confidence is non-zero."""

        detection = self.measure(frame)
        if detection.semantic_confidence == 0.0:
            return ()
        return (
            Observation(
                name=detection.observation_name,
                confidence=detection.semantic_confidence,
                source=ObservationSource.LOCAL_CV,
                value=None,
                region=None,
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
