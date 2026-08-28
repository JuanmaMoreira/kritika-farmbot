import numpy as np

from bot.catalog import (
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    SCREEN_LOBBY,
    SCREEN_WORLD_BOSS_BATTLE,
)
from bot.capture import FrameSnapshot
from bot.fact_reader import RuntimeFactReader
from bot.ocr import OcrEngineError, OcrResult
from bot.ocr_extractors import RESOURCE_SAPPHIRES, build_sapphires_extractor
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resolver import ContextResolver, ContextRule
from bot.runtime_facts import FactQuality, FactReadStatus
from bot.runtime_observer import RuntimeObserver


class Source:
    def __init__(self, sequences):
        self.sequences = list(sequences)
        self.index = 0

    def get_frame(self):
        index = min(self.index, len(self.sequences) - 1)
        sequence = self.sequences[index]
        self.index += 1
        return FrameSnapshot(
            image=np.zeros((100, 200, 3), dtype=np.uint8),
            timestamp=float(sequence),
            sequence=sequence,
        )


class Perception:
    def __init__(self, context=SCREEN_LOBBY):
        self.context = context

    def analyze(self, snapshot):
        name = (
            LANDMARK_LOBBY_TRADING_CENTER_LABEL
            if self.context == SCREEN_LOBBY
            else "landmark.other_context"
        )
        return ObservationBatch(
            sequence=snapshot.sequence,
            timestamp=snapshot.timestamp,
            observations=(
                Observation(name, 1.0, ObservationSource.LOCAL_CV),
            ),
        )


class Engine:
    def __init__(self, texts):
        self.texts = list(texts)

    def recognize(self, image):
        value = self.texts.pop(0)
        if isinstance(value, Exception):
            raise value
        return OcrResult(value, 0.9 if value else 0.0)


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


def reader(sequences, texts, *, context=SCREEN_LOBBY):
    clock = Clock()
    resolver = ContextResolver(
        base_rules=(
            ContextRule(
                SCREEN_LOBBY,
                (LANDMARK_LOBBY_TRADING_CENTER_LABEL,),
                0.8,
            ),
            ContextRule(
                SCREEN_WORLD_BOSS_BATTLE,
                ("landmark.other_context",),
                0.8,
            ),
        )
    )
    observer = RuntimeObserver(
        Source(sequences),
        Perception(context),
        resolver,
        poll_interval=0.1,
        clock=clock,
        sleeper=clock.sleep,
    )
    extractor = build_sapphires_extractor(Engine(texts))
    return RuntimeFactReader(observer, (extractor,), clock=clock)


def test_same_fresh_readings_confirm_a_zero_value_without_defaulting():
    result = reader([1, 2], ["0", "0"]).read_sapphires(
        after_sequence=0, timeout=1.0
    )

    assert result.status is FactReadStatus.CONFIRMED
    assert result.fact.value == 0
    assert result.fact.context == SCREEN_LOBBY
    assert result.fact.quality is FactQuality.CONSENSUS
    assert tuple(item.sequence for item in result.fact.evidence) == (1, 2)


def test_discrepancy_retries_bounded_until_later_consensus():
    result = reader([1, 2, 3], ["5", "8", "5"]).read_fact(
        RESOURCE_SAPPHIRES, after_sequence=0, timeout=1.0
    )

    assert result.status is FactReadStatus.CONFIRMED
    assert result.fact.value == 5
    assert tuple(item.sequence for item in result.fact.evidence) == (1, 3)
    assert result.fact.confidence == 0.6


def test_disagreement_without_consensus_is_uncertain():
    result = reader([1, 2, 3], ["5", "8", "9"]).read_sapphires(
        after_sequence=0, timeout=1.0
    )

    assert result.status is FactReadStatus.UNCERTAIN
    assert result.fact is None


def test_all_empty_or_invalid_readings_are_unreadable_not_zero():
    result = reader([1, 2, 3], ["", "?", "five"]).read_sapphires(
        after_sequence=0, timeout=1.0
    )

    assert result.status is FactReadStatus.UNREADABLE
    assert result.fact is None


def test_unreadable_retry_reduces_consensus_confidence():
    result = reader([1, 2, 3], ["5", "?", "5"]).read_sapphires(
        after_sequence=0, timeout=1.0
    )

    assert result.status is FactReadStatus.CONFIRMED
    assert result.fact.value == 5
    assert result.fact.confidence == 0.6


def test_stale_frames_time_out_without_reusing_old_evidence():
    result = reader([4], ["5"]).read_sapphires(after_sequence=4, timeout=0.25)

    assert result.status is FactReadStatus.TIMEOUT
    assert result.evidence == ()


def test_fresh_wrong_context_aborts_before_ocr():
    result = reader(
        [1], ["5"], context=SCREEN_WORLD_BOSS_BATTLE
    ).read_sapphires(after_sequence=0, timeout=1.0)

    assert result.status is FactReadStatus.CONTEXT_MISMATCH
    assert result.fact is None


def test_cancellation_is_reported_distinctly():
    result = reader([1], ["5"]).read_sapphires(
        after_sequence=0,
        timeout=1.0,
        cancel_requested=lambda: True,
    )

    assert result.status is FactReadStatus.CANCELLED


def test_ocr_failure_is_controlled():
    result = reader(
        [1], [OcrEngineError("inference failed")]
    ).read_sapphires(after_sequence=0, timeout=1.0)

    assert result.status is FactReadStatus.FAILURE
    assert "inference failed" in result.detail
