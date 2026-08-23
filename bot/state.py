"""Immutable result contracts for future semantic context resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

from bot.observations import validate_semantic_name


class ResolutionStatus(str, Enum):
    """Outcome category reported by a future context resolver."""

    RESOLVED = "resolved"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class ResolvedState:
    """Semantic state derived from one observation batch."""

    status: ResolutionStatus
    sequence: int
    timestamp: float
    base_context: str | None = None
    overlays: tuple[str, ...] = ()
    subcontext: str | None = None
    base_candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, ResolutionStatus):
            raise ValueError("status must be a ResolutionStatus")
        object.__setattr__(self, "sequence", _sequence(self.sequence))
        object.__setattr__(self, "timestamp", _timestamp(self.timestamp))

        base_context = _optional_name(self.base_context, "base_context")
        subcontext = _optional_name(self.subcontext, "subcontext")
        overlays = _names(self.overlays, "overlays")
        candidates = _names(self.base_candidates, "base_candidates")
        object.__setattr__(self, "base_context", base_context)
        object.__setattr__(self, "subcontext", subcontext)
        object.__setattr__(self, "overlays", overlays)
        object.__setattr__(self, "base_candidates", candidates)

        if len(set(overlays)) != len(overlays):
            raise ValueError("overlays must not contain duplicates")
        if len(set(candidates)) != len(candidates):
            raise ValueError("base_candidates must not contain duplicates")

        if self.status is ResolutionStatus.RESOLVED:
            if base_context is None:
                raise ValueError("RESOLVED requires base_context")
            if candidates:
                raise ValueError("RESOLVED cannot contain base_candidates")
        elif self.status is ResolutionStatus.UNKNOWN:
            if base_context is not None or subcontext is not None or candidates:
                raise ValueError(
                    "UNKNOWN cannot contain a base context, subcontext, or candidates"
                )
        else:
            if base_context is not None or subcontext is not None:
                raise ValueError(
                    "AMBIGUOUS cannot select a base context or subcontext"
                )
            if len(candidates) < 2:
                raise ValueError(
                    "AMBIGUOUS requires at least two base_candidates"
                )


def _optional_name(value: object, field: str) -> str | None:
    if value is None:
        return None
    try:
        return validate_semantic_name(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a semantic name or None") from error


def _names(values: object, field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field} must be a collection of semantic names")
    try:
        result = tuple(values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(f"{field} must be a collection of semantic names") from error
    try:
        return tuple(validate_semantic_name(value) for value in result)
    except ValueError as error:
        raise ValueError(f"{field} must contain semantic names") from error


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
