"""OCR preprocessing, parsers and extractors for dynamic runtime facts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Callable

import cv2
import numpy as np

from bot.catalog import (
    POPUP_SOCKET_SELL,
    SCREEN_LOBBY,
    SCREEN_SOCKET,
    SCREEN_WORLD_BOSS_BATTLE,
)
from bot.geometry import (
    RelativeRegion,
    normalize_relative_region,
    relative_region_to_pixels,
)
from bot.ocr import OcrEngine, OcrEngineError, OcrResult
from bot.observations import validate_semantic_name
from bot.runtime_facts import FactEvidence
from bot.runtime_observer import RuntimeSnapshot
from bot.state import ResolutionStatus


RESOURCE_SAPPHIRES = "resource.sapphires"
BATTLE_TIMER_REMAINING = "battle.timer_remaining"
BATTLE_TIMER_MAX_SECONDS = 90
SOCKET_SELL_ITEM_LEVEL = "item.socket.sell_level"

# Survival's blue counter. The earlier candidate (0.845, 0.59, 0.945, 0.68)
# covered Battle's violet melee tickets and was rejected during live HIL review.
SAPPHIRES_ROI = normalize_relative_region((0.77, 0.43, 0.855, 0.505))
WORLD_BOSS_TIMER_ROI = normalize_relative_region((0.36, 0.12, 0.59, 0.23))
SOCKET_SELL_LEVEL_ROI = normalize_relative_region((0.47, 0.39, 0.58, 0.45))

IntegerParser = Callable[[str], int | None]


@dataclass(frozen=True)
class RoiPreprocessing:
    """Small reproducible preprocessing recipe owned by an extractor."""

    inner_region: RelativeRegion = (0.0, 0.0, 1.0, 1.0)
    scale: float = 1.0
    grayscale: bool = False
    threshold: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "inner_region", normalize_relative_region(self.inner_region)
        )
        if isinstance(self.scale, bool) or not isinstance(self.scale, Real):
            raise ValueError("scale must be a positive finite number")
        scale = float(self.scale)
        if not math.isfinite(scale) or scale <= 0.0:
            raise ValueError("scale must be a positive finite number")
        if self.threshold is not None and (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, Integral)
            or not 0 <= self.threshold <= 255
        ):
            raise ValueError("threshold must be None or an integer in [0, 255]")
        object.__setattr__(self, "scale", scale)

    def apply(self, image: np.ndarray) -> np.ndarray:
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("image must be a non-empty NumPy array")
        height, width = image.shape[:2]
        x1, y1, x2, y2 = relative_region_to_pixels(
            self.inner_region, width, height
        )
        result = image[y1:y2, x1:x2]
        if self.grayscale and result.ndim == 3:
            result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        if self.threshold is not None:
            if result.ndim == 3:
                result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            _, result = cv2.threshold(
                result, self.threshold, 255, cv2.THRESH_BINARY
            )
        if self.scale != 1.0:
            result = cv2.resize(
                result,
                None,
                fx=self.scale,
                fy=self.scale,
                interpolation=cv2.INTER_CUBIC,
            )
        return result


SAPPHIRES_PREPROCESSING = RoiPreprocessing(scale=2.0)
TIMER_PREPROCESSING = RoiPreprocessing(
    inner_region=(0.45, 0.05, 1.0, 0.80),
    scale=2.0,
)
SOCKET_SELL_LEVEL_PREPROCESSING = RoiPreprocessing(scale=4.0)


class ExtractionStatus(str, Enum):
    VALUE = "value"
    UNREADABLE = "unreadable"
    CONTEXT_MISMATCH = "context_mismatch"


@dataclass(frozen=True)
class FactExtraction:
    status: ExtractionStatus
    evidence: FactEvidence
    value: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ExtractionStatus):
            raise ValueError("status must be an ExtractionStatus")
        if not isinstance(self.evidence, FactEvidence):
            raise ValueError("evidence must be a FactEvidence")
        if self.status is ExtractionStatus.VALUE:
            if (
                isinstance(self.value, bool)
                or not isinstance(self.value, Integral)
                or self.value < 0
            ):
                raise ValueError("VALUE requires a non-negative integer")
            object.__setattr__(self, "value", int(self.value))
        elif self.value is not None:
            raise ValueError("non-value extraction cannot contain a value")


@dataclass(frozen=True)
class OcrFactExtractor:
    name: str
    context: str
    region: RelativeRegion
    engine: OcrEngine
    parser: IntegerParser
    required_overlays: tuple[str, ...] = ()
    preprocessing: RoiPreprocessing = RoiPreprocessing()
    confirmations: int = 1
    max_observations: int = 3
    min_ocr_confidence: float = 0.50
    sample_interval: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        object.__setattr__(self, "context", validate_semantic_name(self.context))
        object.__setattr__(self, "region", normalize_relative_region(self.region))
        overlays = tuple(
            validate_semantic_name(item) for item in self.required_overlays
        )
        if len(set(overlays)) != len(overlays):
            raise ValueError("required_overlays must not contain duplicates")
        object.__setattr__(self, "required_overlays", overlays)
        if not callable(getattr(self.engine, "recognize", None)):
            raise ValueError("engine must provide recognize(image)")
        if not callable(self.parser):
            raise ValueError("parser must be callable")
        if (
            isinstance(self.confirmations, bool)
            or not isinstance(self.confirmations, Integral)
            or self.confirmations <= 0
        ):
            raise ValueError("confirmations must be a positive integer")
        if (
            isinstance(self.max_observations, bool)
            or not isinstance(self.max_observations, Integral)
            or self.max_observations < self.confirmations
        ):
            raise ValueError("max_observations must cover confirmations")
        if isinstance(self.min_ocr_confidence, bool) or not isinstance(
            self.min_ocr_confidence, Real
        ):
            raise ValueError("min_ocr_confidence must be in [0, 1]")
        minimum = float(self.min_ocr_confidence)
        if not math.isfinite(minimum) or not 0.0 <= minimum <= 1.0:
            raise ValueError("min_ocr_confidence must be in [0, 1]")
        if isinstance(self.sample_interval, bool) or not isinstance(
            self.sample_interval, Real
        ):
            raise ValueError("sample_interval must be non-negative and finite")
        interval = float(self.sample_interval)
        if not math.isfinite(interval) or interval < 0.0:
            raise ValueError("sample_interval must be non-negative and finite")
        object.__setattr__(self, "confirmations", int(self.confirmations))
        object.__setattr__(self, "max_observations", int(self.max_observations))
        object.__setattr__(self, "min_ocr_confidence", minimum)
        object.__setattr__(self, "sample_interval", interval)

    def extract(self, snapshot: RuntimeSnapshot) -> FactExtraction:
        state = snapshot.state
        if (
            state.status is not ResolutionStatus.RESOLVED
            or state.base_context != self.context
            or not set(self.required_overlays).issubset(state.overlays)
        ):
            return FactExtraction(
                status=ExtractionStatus.CONTEXT_MISMATCH,
                evidence=FactEvidence(
                    sequence=snapshot.sequence,
                    timestamp=snapshot.timestamp,
                    raw_text="",
                    ocr_confidence=0.0,
                ),
            )

        frame = snapshot.frame.image
        x1, y1, x2, y2 = relative_region_to_pixels(
            self.region, snapshot.geometry.width, snapshot.geometry.height
        )
        prepared = self.preprocessing.apply(frame[y1:y2, x1:x2])
        result = self.engine.recognize(prepared)
        value = (
            self.parser(result.text)
            if result.confidence >= self.min_ocr_confidence
            else None
        )
        evidence = FactEvidence(
            sequence=snapshot.sequence,
            timestamp=snapshot.timestamp,
            raw_text=result.text,
            ocr_confidence=result.confidence,
        )
        return FactExtraction(
            status=(
                ExtractionStatus.VALUE
                if value is not None
                else ExtractionStatus.UNREADABLE
            ),
            evidence=evidence,
            value=value,
        )


def parse_integer(text: str) -> int | None:
    """Parse one non-negative integer, optionally shown as ``value/max``."""

    if not isinstance(text, str):
        raise ValueError("text must be a string")
    cleaned = text.strip().translate(str.maketrans({"O": "0", "o": "0"}))
    match = re.fullmatch(
        r"[\[\](){}\s]*([0-9][0-9,\s]*)(?:\s*/\s*[0-9][0-9,\s]*)?"
        r"[\[\](){}\s.,;:_-]*",
        cleaned,
    )
    if match is None:
        return None
    digits = re.sub(r"[,\s]", "", match.group(1))
    return int(digits) if digits else None


def parse_duration_seconds(text: str) -> int | None:
    """Parse ``MM:SS`` plus the observed optional tenths, returning ceil seconds."""

    if not isinstance(text, str):
        raise ValueError("text must be a string")
    cleaned = re.sub(r"\s+", "", text).translate(
        str.maketrans({"O": "0", "o": "0", ",": ".", ";": ":"})
    )
    match = re.fullmatch(r"(\d{1,2})([:.])([0-5]\d)(?:\.(\d+))?", cleaned)
    if match is None:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(3))
    fraction = match.group(4)
    total = minutes * 60 + seconds
    if fraction is not None and int(fraction) > 0:
        total += 1
    return total


def parse_world_boss_timer_seconds(text: str) -> int | None:
    """Parse only countdown values valid for a World Boss battle."""

    value = parse_duration_seconds(text)
    if value is None or value > BATTLE_TIMER_MAX_SECONDS:
        return None
    return value


def parse_socket_sell_level(text: str) -> int | None:
    """Parse only the Socket Sell sentence carrying an Opal (Skill) level."""

    if not isinstance(text, str):
        raise ValueError("text must be a string")
    match = re.fullmatch(
        r"\s*(?:\[?Opal\s*)?\(?Skill\)\s*\+\s*([0-9]{1,3})\]"
        r"\s*for\s*6\s*K(?:\s*Coins?\.?)?\s*",
        text,
    )
    return int(match.group(1)) if match is not None else None


def build_sapphires_extractor(engine: OcrEngine) -> OcrFactExtractor:
    return OcrFactExtractor(
        name=RESOURCE_SAPPHIRES,
        context=SCREEN_LOBBY,
        region=SAPPHIRES_ROI,
        engine=engine,
        parser=parse_integer,
        preprocessing=SAPPHIRES_PREPROCESSING,
        confirmations=2,
        max_observations=3,
        sample_interval=0.20,
    )


def build_timer_extractor(engine: OcrEngine) -> OcrFactExtractor:
    return OcrFactExtractor(
        name=BATTLE_TIMER_REMAINING,
        context=SCREEN_WORLD_BOSS_BATTLE,
        region=WORLD_BOSS_TIMER_ROI,
        engine=engine,
        parser=parse_world_boss_timer_seconds,
        preprocessing=TIMER_PREPROCESSING,
        confirmations=1,
        # The chat may temporarily cover the only visible timer location.
        # Retry passively over fresh frames; caller timeout/cancellation remain
        # the outer bound and no unreadable reading authorizes input.
        max_observations=10,
        sample_interval=0.50,
    )


def build_socket_sell_level_extractor(engine: OcrEngine) -> OcrFactExtractor:
    return OcrFactExtractor(
        name=SOCKET_SELL_ITEM_LEVEL,
        context=SCREEN_SOCKET,
        required_overlays=(POPUP_SOCKET_SELL,),
        region=SOCKET_SELL_LEVEL_ROI,
        engine=engine,
        parser=parse_socket_sell_level,
        preprocessing=SOCKET_SELL_LEVEL_PREPROCESSING,
        confirmations=2,
        max_observations=3,
        min_ocr_confidence=0.90,
        sample_interval=0.15,
    )


__all__ = (
    "BATTLE_TIMER_MAX_SECONDS",
    "BATTLE_TIMER_REMAINING",
    "RESOURCE_SAPPHIRES",
    "SOCKET_SELL_ITEM_LEVEL",
    "FactExtraction",
    "ExtractionStatus",
    "OcrFactExtractor",
    "OcrEngineError",
    "OcrResult",
    "RoiPreprocessing",
    "SAPPHIRES_PREPROCESSING",
    "SAPPHIRES_ROI",
    "TIMER_PREPROCESSING",
    "SOCKET_SELL_LEVEL_PREPROCESSING",
    "SOCKET_SELL_LEVEL_ROI",
    "WORLD_BOSS_TIMER_ROI",
    "build_sapphires_extractor",
    "build_socket_sell_level_extractor",
    "build_timer_extractor",
    "parse_duration_seconds",
    "parse_integer",
    "parse_socket_sell_level",
    "parse_world_boss_timer_seconds",
)
