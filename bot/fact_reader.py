"""Bounded fresh/context-correct acquisition of semantic runtime facts."""

from __future__ import annotations

import math
import time
from collections import Counter
from numbers import Integral, Real
from typing import Callable, Iterable, cast

from bot.event_log import EventSink
from bot.observations import ObservationSource, validate_semantic_name
from bot.ocr import OcrEngineError
from bot.ocr_extractors import (
    BATTLE_TIMER_REMAINING,
    RESOURCE_SAPPHIRES,
    SOCKET_SELL_ITEM_LEVEL,
    ExtractionStatus,
    OcrFactExtractor,
)
from bot.runtime_facts import (
    FactEvidence,
    FactQuality,
    FactReadResult,
    FactReadStatus,
    RuntimeFact,
)
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.state import ResolutionStatus


class RuntimeFactReader:
    """Consumer-facing fact registry; ROI/OCR/parser details stay internal."""

    def __init__(
        self,
        observer: RuntimeObserver,
        extractors: Iterable[OcrFactExtractor],
        *,
        clock: Callable[[], float] = time.monotonic,
        events: EventSink | None = None,
    ) -> None:
        if not isinstance(observer, RuntimeObserver):
            raise ValueError("observer must be a RuntimeObserver")
        registry: dict[str, OcrFactExtractor] = {}
        for extractor in extractors:
            if not isinstance(extractor, OcrFactExtractor):
                raise ValueError("extractors must contain OcrFactExtractor instances")
            if extractor.name in registry:
                raise ValueError(f"duplicate fact extractor: {extractor.name}")
            registry[extractor.name] = extractor
        if not registry:
            raise ValueError("at least one extractor is required")
        self.observer = observer
        self._extractors = registry
        self._clock = clock
        self.events = events

    @property
    def fact_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._extractors))

    def read_fact(
        self,
        name: str,
        *,
        after_sequence: int,
        timeout: float,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> FactReadResult[int]:
        name = validate_semantic_name(name)
        if name not in self._extractors:
            raise KeyError(f"no extractor registered for {name}")
        after = _sequence(after_sequence)
        duration = _positive_duration(timeout)
        deadline = self._clock() + duration
        extractor = self._extractors[name]
        cursor = after
        evidence: list[FactEvidence] = []
        values: list[int] = []
        readable: list[tuple[int, FactEvidence]] = []

        for _ in range(extractor.max_observations):
            remaining = deadline - self._clock()
            if remaining <= 0:
                return FactReadResult(
                    FactReadStatus.TIMEOUT,
                    evidence=tuple(evidence),
                    detail="fact acquisition deadline expired",
                )
            try:
                snapshot = self.observer.wait_until(
                    lambda item: (
                        item.state.status is ResolutionStatus.RESOLVED
                        and (
                            not evidence
                            or item.timestamp - evidence[-1].timestamp
                            >= extractor.sample_interval
                        )
                    ),
                    after_sequence=cursor,
                    timeout=remaining,
                    cancel_requested=cancel_requested,
                )
            except RuntimeWaitCancelled:
                return FactReadResult(
                    FactReadStatus.CANCELLED,
                    evidence=tuple(evidence),
                )
            except RuntimeWaitTimeout:
                return FactReadResult(
                    FactReadStatus.TIMEOUT,
                    evidence=tuple(evidence),
                    detail="no fresh resolved frame arrived before the deadline",
                )
            cursor = snapshot.sequence

            try:
                extracted = extractor.extract(snapshot)
            except OcrEngineError as error:
                return FactReadResult(
                    FactReadStatus.FAILURE,
                    evidence=tuple(evidence),
                    detail=str(error),
                )
            evidence.append(extracted.evidence)
            self._record(
                "fact.observed",
                fact=name,
                parsed_value=extracted.value,
                extraction_status=extracted.status.value,
                confidence=extracted.evidence.ocr_confidence,
                observation_count=len(evidence),
                sequence=snapshot.sequence,
                resolution_status=snapshot.state.status.value,
                base_context=snapshot.state.base_context,
                overlays=snapshot.state.overlays,
            )
            if extracted.status == ExtractionStatus.CONTEXT_MISMATCH:
                return FactReadResult(
                    FactReadStatus.CONTEXT_MISMATCH,
                    evidence=tuple(evidence),
                    detail="fresh frame does not satisfy fact context requirements",
                )
            if extracted.status == ExtractionStatus.UNREADABLE:
                continue
            parsed_value = cast(int, extracted.value)
            values.append(parsed_value)
            readable.append((parsed_value, extracted.evidence))
            counts = Counter(values)
            value, support = counts.most_common(1)[0]
            if support >= extractor.confirmations:
                selected = tuple(
                    item
                    for parsed, item in readable
                    if parsed == value
                )
                confidence = (
                    sum(item.ocr_confidence for item in selected) / len(selected)
                ) * (support / len(evidence))
                quality = (
                    FactQuality.CONSENSUS
                    if extractor.confirmations > 1
                    else FactQuality.VALIDATED_SINGLE
                )
                fact = RuntimeFact(
                    name=extractor.name,
                    value=value,
                    confidence=confidence,
                    quality=quality,
                    source=ObservationSource.OCR,
                    context=extractor.context,
                    evidence=selected,
                )
                self._record(
                    "fact.confirmed",
                    fact=name,
                    parsed_value=value,
                    consensus=support,
                    observations=len(evidence),
                    quality=quality.value,
                    confidence=confidence,
                )
                return FactReadResult(
                    FactReadStatus.CONFIRMED,
                    fact=fact,
                    evidence=tuple(evidence),
                )

        if not values:
            status = FactReadStatus.UNREADABLE
            detail = "all fresh context-correct OCR readings were unreadable"
        else:
            status = FactReadStatus.UNCERTAIN
            detail = "bounded readings did not reach value consensus"
        return FactReadResult(
            status,
            evidence=tuple(evidence),
            detail=detail,
        )

    def read_sapphires(self, **kwargs) -> FactReadResult[int]:
        return self.read_fact(RESOURCE_SAPPHIRES, **kwargs)

    def read_timer_remaining(self, **kwargs) -> FactReadResult[int]:
        return self.read_fact(BATTLE_TIMER_REMAINING, **kwargs)

    def read_socket_sell_item_level(self, **kwargs) -> FactReadResult[int]:
        return self.read_fact(SOCKET_SELL_ITEM_LEVEL, **kwargs)

    def _record(self, event: str, **fields: object) -> None:
        if self.events is None:
            return
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("after_sequence must be a non-negative integer")
    return int(value)


def _positive_duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("timeout must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError("timeout must be a positive finite number")
    return result


__all__ = ("RuntimeFactReader",)
