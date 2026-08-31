from dataclasses import fields

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.catalog import POPUP_SOCKET_SELL, SCREEN_LOBBY, SCREEN_SOCKET, SCREEN_WORLD_BOSS_BATTLE
from bot.capture import FrameSnapshot
from bot.ocr import OcrResult
from bot.ocr_extractors import (
    BATTLE_TIMER_MAX_SECONDS,
    BATTLE_TIMER_REMAINING,
    RESOURCE_SAPPHIRES,
    SOCKET_SELL_ITEM_LEVEL,
    SOCKET_SELL_LEVEL_ROI,
    SAPPHIRES_ROI,
    WORLD_BOSS_TIMER_ROI,
    ExtractionStatus,
    build_sapphires_extractor,
    build_socket_sell_level_extractor,
    build_timer_extractor,
    parse_duration_seconds,
    parse_integer,
    parse_socket_sell_level,
    parse_world_boss_timer_seconds,
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


def snapshot(context, *, sequence=3, fill=0, overlays=()):
    image = np.full((100, 200, 3), fill, dtype=np.uint8)
    frame = FrameSnapshot(image=image, timestamp=float(sequence), sequence=sequence)
    observations = ObservationBatch(sequence=sequence, timestamp=float(sequence))
    state = ResolvedState(
        status=ResolutionStatus.RESOLVED,
        sequence=sequence,
        timestamp=float(sequence),
        base_context=context,
        overlays=overlays,
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("00:00", 0),
        ("01:30", 90),
        ("01:31", None),
        ("41:19", None),
    ],
)
def test_world_boss_timer_parser_rejects_values_above_business_limit(text, expected):
    assert BATTLE_TIMER_MAX_SECONDS == 90
    assert parse_world_boss_timer_seconds(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(Skill)+0] for 6 K", 0),
        ("Skill)+10] for 6 K", 10),
        ("[Opal (Skill)+0] for 6 K Coins.", 0),
        ("(Skill)+O] for 6 K", None),
        ("(Skill)+0] for 8 K", None),
        ("Gem (Skill)+0] for 6 K", None),
        ("(Skill)+", None),
    ],
)
def test_parse_socket_sell_level_requires_exact_opal_sale_context(text, expected):
    assert parse_socket_sell_level(text) == expected


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


def test_socket_sell_level_requires_screen_and_sell_overlay_before_ocr():
    engine = Engine(OcrResult("(Skill)+0] for 6 K", 0.98))
    extractor = build_socket_sell_level_extractor(engine)

    missing_overlay = extractor.extract(snapshot(SCREEN_SOCKET))
    accepted = extractor.extract(
        snapshot(SCREEN_SOCKET, overlays=(POPUP_SOCKET_SELL,))
    )

    assert extractor.name == SOCKET_SELL_ITEM_LEVEL
    assert extractor.region == SOCKET_SELL_LEVEL_ROI
    assert missing_overlay.status is ExtractionStatus.CONTEXT_MISMATCH
    assert accepted.status is ExtractionStatus.VALUE
    assert accepted.value == 0
    assert len(engine.images) == 1


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
    assert timer.sample_interval == 0.50
    assert timer.max_observations == 10


def test_dynamic_runtime_fact_contract_is_separate_from_character_context():
    runtime_fields = {item.name for item in fields(RuntimeFact)}
    character_fields = {item.name for item in fields(CharacterContext)}

    assert {"value", "confidence", "quality", "source", "context", "evidence"} <= (
        runtime_fields
    )
    assert character_fields == {"name", "name_confidence"}
    assert "name_confidence" not in runtime_fields
    assert {"value", "context", "evidence"}.isdisjoint(character_fields)
