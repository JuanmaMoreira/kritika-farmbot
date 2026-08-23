"""Immutable semantic evidence produced for one captured frame."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

from bot.geometry import RelativeRegion, normalize_relative_region

ObservationValue = bool | int | float | str | None

_SEMANTIC_NAME = re.compile(
    r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"
)


class ObservationSource(str, Enum):
    """Implementation-independent category that reported an observation."""

    LOCAL_CV = "local_cv"
    OCR = "ocr"
    VLM = "vlm"
    SYSTEM = "system"


@dataclass(frozen=True)
class Observation:
    """One semantic fact reported by a perception source."""

    name: str
    confidence: float
    source: ObservationSource
    value: ObservationValue = None
    region: RelativeRegion | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        object.__setattr__(
            self, "confidence", normalize_confidence(self.confidence)
        )
        if not isinstance(self.source, ObservationSource):
            raise ValueError("source must be an ObservationSource")
        _validate_value(self.value)
        if self.region is not None:
            object.__setattr__(
                self, "region", normalize_relative_region(self.region)
            )


@dataclass(frozen=True)
class ObservationBatch:
    """Semantic observations associated with one logical captured frame."""

    sequence: int
    timestamp: float
    observations: tuple[Observation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _sequence(self.sequence))
        object.__setattr__(self, "timestamp", _timestamp(self.timestamp))
        observations = tuple(self.observations)
        if not all(isinstance(item, Observation) for item in observations):
            raise ValueError("observations must contain only Observation instances")
        object.__setattr__(self, "observations", observations)

    def find(self, name: str) -> tuple[Observation, ...]:
        """Return every matching observation, preserving detector order."""

        name = validate_semantic_name(name)
        return tuple(item for item in self.observations if item.name == name)

    def best(self, name: str) -> Observation | None:
        """Return the highest-confidence match without applying fusion policy."""

        matches = self.find(name)
        return max(matches, key=lambda item: item.confidence, default=None)


def validate_semantic_name(name: object) -> str:
    """Return a lightly validated, namespaced semantic identifier."""

    if not isinstance(name, str) or _SEMANTIC_NAME.fullmatch(name) is None:
        raise ValueError(
            "name must be a lowercase namespaced identifier such as 'screen.lobby'"
        )
    return name


def normalize_confidence(value: object) -> float:
    """Validate and return a finite confidence normalized to ``[0, 1]``."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("confidence must be a real number in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return result


def _validate_value(value: object) -> None:
    if value is not None and not isinstance(value, (bool, int, float, str)):
        raise ValueError("value must be bool, int, float, str, or None")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("numeric observation values must be finite")


def _sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("sequence must be a non-negative integer")
    return int(value)


def _timestamp(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("timestamp must be a non-negative finite real number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError("timestamp must be a non-negative finite real number")
    return result
