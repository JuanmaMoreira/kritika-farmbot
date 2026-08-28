"""Typed dynamic facts and bounded read outcomes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real
from typing import Generic, TypeVar

from bot.observations import ObservationSource, validate_semantic_name


T = TypeVar("T")


class FactQuality(str, Enum):
    CONSENSUS = "consensus"
    VALIDATED_SINGLE = "validated_single"


class FactReadStatus(str, Enum):
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    UNREADABLE = "unreadable"
    CONTEXT_MISMATCH = "context_mismatch"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILURE = "failure"


@dataclass(frozen=True)
class FactEvidence:
    sequence: int
    timestamp: float
    raw_text: str
    ocr_confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, Integral):
            raise ValueError("sequence must be a non-negative integer")
        if self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, Real):
            raise ValueError("timestamp must be a non-negative finite real number")
        timestamp = float(self.timestamp)
        if not math.isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("timestamp must be a non-negative finite real number")
        if not isinstance(self.raw_text, str):
            raise ValueError("raw_text must be a string")
        confidence = _confidence(self.ocr_confidence)
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "ocr_confidence", confidence)


@dataclass(frozen=True)
class RuntimeFact(Generic[T]):
    name: str
    value: T
    confidence: float
    quality: FactQuality
    source: ObservationSource
    context: str
    evidence: tuple[FactEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        object.__setattr__(self, "context", validate_semantic_name(self.context))
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        if not isinstance(self.quality, FactQuality):
            raise ValueError("quality must be a FactQuality")
        if not isinstance(self.source, ObservationSource):
            raise ValueError("source must be an ObservationSource")
        evidence = tuple(self.evidence)
        if not evidence or not all(isinstance(item, FactEvidence) for item in evidence):
            raise ValueError("evidence must contain at least one FactEvidence")
        if any(
            current.sequence <= previous.sequence
            for previous, current in zip(evidence, evidence[1:])
        ):
            raise ValueError("evidence sequences must be strictly increasing")
        object.__setattr__(self, "evidence", evidence)

    @property
    def sequence(self) -> int:
        return self.evidence[-1].sequence

    @property
    def timestamp(self) -> float:
        return self.evidence[-1].timestamp


@dataclass(frozen=True)
class FactReadResult(Generic[T]):
    status: FactReadStatus
    fact: RuntimeFact[T] | None = None
    evidence: tuple[FactEvidence, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, FactReadStatus):
            raise ValueError("status must be a FactReadStatus")
        if self.status is FactReadStatus.CONFIRMED and self.fact is None:
            raise ValueError("CONFIRMED requires a fact")
        if self.status is not FactReadStatus.CONFIRMED and self.fact is not None:
            raise ValueError("only CONFIRMED may contain a fact")
        evidence = tuple(self.evidence)
        if not all(isinstance(item, FactEvidence) for item in evidence):
            raise ValueError("evidence must contain only FactEvidence instances")
        object.__setattr__(self, "evidence", evidence)


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("confidence must be a real number in [0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return result


__all__ = (
    "FactEvidence",
    "FactQuality",
    "FactReadResult",
    "FactReadStatus",
    "RuntimeFact",
)
