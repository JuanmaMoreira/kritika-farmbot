from dataclasses import fields

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.catalog import SCREEN_LOBBY, SCREEN_WORLD_BOSS_BATTLE
from bot.capture import FrameSnapshot
from bot.ocr import OcrResult
from bot.ocr_extractors import (
    BATTLE_TIMER_REMAINING,
    RESOURCE_SAPPHIRES,
    SAPPHIRES_ROI,
    WORLD_BOSS_TIMER_ROI,
    ExtractionStatus,
    build_sapphires_extractor,
    build_timer_extractor,
    parse_duration_seconds,
    parse_integer,
)
from bot.observations import ObservationBatch
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.runtime_facts import RuntimeFact
from bot.session import CharacterContext
from bot.state import ResolutionStatus, ResolvedState


class Engine:
    def __init__(self, result):
        self.result = result
        self.images = []

    def recognize(self, image):
        self.images.append(image.copy())
        return self.result


def snapshot(context, *, sequence=3, fill=0):
    image = np.full((100, 200, 3), fill, dtype=np.uint8)
    frame = FrameSnapshot(image=image, timestamp=float(sequence), sequence=sequence)
    observations = ObservationBatch(sequence=sequence, timestamp=float(sequence))
    state = ResolvedState(
        status=ResolutionStatus.RESOLVED,
        sequence=sequence,
        timestamp=float(sequence),
        base_context=context,
    )
    return RuntimeSnapshot(
        frame=frame,
        observations=observations,
        state=state,
        facts=RuntimeFacts(),
        geometry=FrameGeometry(width=200, height=100),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5", 5),
        ("0", 0),
        ("12,345", 12345),
        ("  42  ", 42),
        ("[ 32/32 ]", 32),
        ("O", 0),
        ("", None),
        ("five", None),
        ("5 8", 58),
        ("5/unknown", None),
    ],
)
def test_parse_integer(text, expected):
    assert parse_integer(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01:30", 90),
        ("00:59", 59),
        ("10:00", 600),
        ("0:39.5", 40),
        ("0.38.4", 39),
        ("00:60", None),
        ("037.0", None),
        ("not a timer", None),
    ],
)
def test_parse_duration_seconds(text, expected):
    assert parse_duration_seconds(text) == expected


def test_sapphires_extractor_owns_roi_preprocessing_and_typed_value():
    engine = Engine(OcrResult("32/32", 0.99))
    extractor = build_sapphires_extractor(engine)

    result = extractor.extract(snapshot(SCREEN_LOBBY))

    assert extractor.name == RESOURCE_SAPPHIRES
    assert extractor.region == SAPPHIRES_ROI
    assert result.status == ExtractionStatus.VALUE
    assert result.value == 32
    assert engine.images[0].shape == (14, 34, 3)


def test_timer_extractor_returns_semantic_seconds_and_keeps_raw_text():
    engine = Engine(OcrResult("01:07", 0.95))
    extractor = build_timer_extractor(engine)

    result = extractor.extract(snapshot(SCREEN_WORLD_BOSS_BATTLE))

    assert extractor.name == BATTLE_TIMER_REMAINING
    assert extractor.region == WORLD_BOSS_TIMER_ROI
    assert result.value == 67
    assert result.evidence.raw_text == "01:07"


def test_extractor_rejects_wrong_context_before_ocr():
    engine = Engine(OcrResult("5", 1.0))
    extractor = build_sapphires_extractor(engine)

    result = extractor.extract(snapshot(SCREEN_WORLD_BOSS_BATTLE))

    assert result.status == ExtractionStatus.CONTEXT_MISMATCH
    assert result.value is None
    assert engine.images == []


def test_extractor_does_not_accept_parseable_low_confidence_text():
    engine = Engine(OcrResult("5", 0.2))

    result = build_sapphires_extractor(engine).extract(snapshot(SCREEN_LOBBY))

    assert result.status is ExtractionStatus.UNREADABLE
    assert result.value is None


def test_product_extractors_space_independent_fresh_observations():
    engine = Engine(OcrResult("5", 1.0))

    sapphires = build_sapphires_extractor(engine)
    timer = build_timer_extractor(engine)

    assert sapphires.sample_interval == 0.20
    assert timer.sample_interval == 0.05


def test_dynamic_runtime_fact_contract_is_separate_from_character_context():
    runtime_fields = {item.name for item in fields(RuntimeFact)}
    character_fields = {item.name for item in fields(CharacterContext)}

    assert {"value", "confidence", "quality", "source", "context", "evidence"} <= (
        runtime_fields
    )
    assert character_fields == {"name", "name_confidence"}
    assert "name_confidence" not in runtime_fields
    assert {"value", "context", "evidence"}.isdisjoint(character_fields)
