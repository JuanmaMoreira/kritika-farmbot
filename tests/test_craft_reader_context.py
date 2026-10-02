"""Craft identity proves presence; unreadable economics must not veto it."""

from unittest.mock import Mock

import numpy as np

from bot.craft_reader import CraftReader
from bot.craft_semantics import CraftContextFact, consensus_craft_facts
from bot.ocr import OcrResult


_BLANK_MENU = (("", 0.0), ("", 0.0), ("", 0.0))


def _sample(
    *,
    title=("+Craft", 0.84),
    rate=("2Rate", 0.88),
    expert=("Expert Craft", 0.98),
    menu_reads=_BLANK_MENU,
    weapon_count=("999/999", 0.94),
    armor_count=("546/999", 0.99),
    accessory_count=("445/999", 0.99),
    weapon_cost=("49", 0.83),
    armor_cost=("49", 0.99),
    accessory_cost=("49", 0.99),
    sequence=10,
):
    values = (
        title, rate, expert, *menu_reads,
        weapon_count, armor_count, accessory_count,
        weapon_cost, armor_cost, accessory_cost,
    )
    engine = Mock()
    engine.recognize.side_effect = [OcrResult(*value) for value in values]
    reader = CraftReader(engine)
    frame = np.zeros((433, 960, 3), dtype=np.uint8)
    fact = reader.context_sample(frame, sequence=sequence, observed_at=100.0)
    return fact, reader


def test_live_weapon_cost_confidence_produces_fresh_craft_consensus():
    first, _ = _sample(sequence=10)
    second, _ = _sample(sequence=11)

    assert first is not None and second is not None
    fact = consensus_craft_facts((first, second))
    assert fact is not None and fact.confirmed
    assert fact.sample_sequences == (10, 11)
    assert fact.weapon_hero_cost == 49


def test_chat_occluded_title_still_proves_craft_identity():
    first, _ = _sample(title=("+Cratt", 0.58), sequence=10)
    second, _ = _sample(title=("+Cra", 0.44), sequence=11)

    assert first is not None and second is not None
    fact = consensus_craft_facts((first, second))
    assert fact is not None and fact.confirmed


def test_foreign_title_is_auxiliary_once_identity_is_proven():
    fact, _ = _sample(title=("Monster Wave", 0.95))

    assert fact is not None and fact.complete


def test_identity_does_not_require_all_family_economics():
    fact, _ = _sample(
        weapon_count=("ge 999/999", 0.75),
        armor_count=("", 0.0),
        accessory_count=("", 0.0),
        armor_cost=("", 0.0),
        accessory_cost=("", 0.0),
    )

    assert fact is not None and fact.complete
    assert fact.weapon_material is None
    assert fact.armor_material is None
    assert fact.accessory_material is None
    assert fact.weapon_hero_cost == 49


def test_unproven_expert_identity_cannot_prove_craft():
    assert _sample(expert=("S", 0.36))[0] is None
    assert _sample(expert=("50+29", 0.985))[0] is None
    assert _sample(expert=("Hero", 0.971))[0] is None


def test_quick_menu_overlay_is_not_clean_craft_context():
    fact, reader = _sample(
        menu_reads=(("Lobby", 0.90), ("Craft", 0.90), ("Guild", 0.90)),
    )

    assert fact is None
    assert reader.last_context_diagnostic["rejection"] == "quick_menu_overlay"


def test_contradictory_fact_never_counts_as_complete():
    fact, _ = _sample()

    assert fact is not None
    assert CraftContextFact(
        **{**fact.__dict__, "contradictory": True},
    ).complete is False
