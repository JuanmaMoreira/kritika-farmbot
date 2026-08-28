import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from bot.catalog import (
    BASE_CONTEXT_RULES,
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_BAG_FULL_PROMPT,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_INVENTORY_FULL_PROMPT,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    MENU_QUICK,
    OVERLAY_WORLD_BOSS_RAID_COMPLETE,
    OVERLAY_WORLD_BOSS_SELECT_BOSS,
    OVERLAY_RULES,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_INVENTORY_FULL,
    POPUP_PURCHASE_CONFIRMATION,
    POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
    POPUP_WORLD_BOSS_INVENTORY_FULL,
    POPUP_WORLD_BOSS_BAG_FULL,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_BLACK_MARKET,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
    SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE,
    SEMANTIC_CONFIDENCE_THRESHOLD,
    SEMANTIC_OBSERVATION_NAMES,
    build_default_resolver,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resolver import ContextResolver, match_rule
from bot.state import ResolutionStatus


def observation(name, confidence=SEMANTIC_CONFIDENCE_THRESHOLD):
    return Observation(name, confidence, ObservationSource.SYSTEM)


def batch(*names, confidence=SEMANTIC_CONFIDENCE_THRESHOLD):
    return ObservationBatch(
        sequence=17,
        timestamp=91.5,
        observations=tuple(observation(name, confidence) for name in names),
    )


@pytest.mark.parametrize("context_rule", BASE_CONTEXT_RULES)
def test_each_catalog_base_rule_resolves_individually(context_rule):
    state = build_default_resolver().resolve(batch(*context_rule.requires))

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == context_rule.name
    assert state.subcontext is None


@pytest.mark.parametrize("overlay_rule", OVERLAY_RULES)
def test_each_catalog_overlay_rule_resolves_individually(overlay_rule):
    state = build_default_resolver().resolve(batch(*overlay_rule.requires))

    expected_base = {
        POPUP_INVENTORY_FULL: SCREEN_BLACK_MARKET,
        POPUP_WORLD_BOSS_BAG_FULL: SCREEN_WORLD_BOSS,
    }.get(overlay_rule.name)
    expected_status = (
        ResolutionStatus.RESOLVED
        if expected_base is not None
        else ResolutionStatus.UNKNOWN
    )
    assert state.status is expected_status
    assert state.base_context == expected_base
    assert state.overlays == (overlay_rule.name,)


def test_raid_complete_overlay_is_preserved_without_a_resolved_base():
    state = build_default_resolver().resolve(
        batch(LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE)
    )

    assert state.status is ResolutionStatus.UNKNOWN
    assert state.base_context is None
    assert state.overlays == (OVERLAY_WORLD_BOSS_RAID_COMPLETE,)


@pytest.mark.parametrize("context_rule", (*BASE_CONTEXT_RULES, *OVERLAY_RULES))
def test_missing_a_catalog_requirement_does_not_match(context_rule):
    assert match_rule(
        context_rule, batch(*context_rule.requires[:-1])
    ) is None


def test_catalog_uses_one_uniform_provisional_threshold():
    all_rules = (*BASE_CONTEXT_RULES, *OVERLAY_RULES)

    assert SEMANTIC_CONFIDENCE_THRESHOLD == 0.80
    assert {
        context_rule.min_confidence for context_rule in all_rules
    } == {SEMANTIC_CONFIDENCE_THRESHOLD}


def test_catalog_threshold_is_inclusive():
    context_rule = BASE_CONTEXT_RULES[0]
    resolver = ContextResolver(base_rules=(context_rule,))

    below = resolver.resolve(
        batch(
            *context_rule.requires,
            confidence=SEMANTIC_CONFIDENCE_THRESHOLD - 0.001,
        )
    )
    exact = resolver.resolve(
        batch(
            *context_rule.requires,
            confidence=SEMANTIC_CONFIDENCE_THRESHOLD,
        )
    )

    assert below.status is ResolutionStatus.UNKNOWN
    assert exact.status is ResolutionStatus.RESOLVED


def test_base_rules_do_not_share_the_same_minimal_evidence_set():
    evidence_sets = [frozenset(rule.requires) for rule in BASE_CONTEXT_RULES]

    assert len(evidence_sets) == len(set(evidence_sets))


def test_catalog_resolves_black_market_with_its_purchase_overlay():
    resolver = build_default_resolver()
    black_market_rule = next(
        rule for rule in BASE_CONTEXT_RULES if rule.name == SCREEN_BLACK_MARKET
    )
    purchase_rule = next(
        rule for rule in OVERLAY_RULES if rule.name == POPUP_PURCHASE_CONFIRMATION
    )

    state = resolver.resolve(
        batch(*black_market_rule.requires, *purchase_rule.requires)
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_BLACK_MARKET
    assert state.overlays == (POPUP_PURCHASE_CONFIRMATION,)


def test_catalog_resolves_black_market_with_insufficient_gold_overlay():
    state = build_default_resolver().resolve(
        batch(
            "landmark.black_market_title",
            LANDMARK_INSUFFICIENT_GOLD_PROMPT,
        )
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_BLACK_MARKET
    assert state.overlays == (POPUP_INSUFFICIENT_GOLD,)


def test_inventory_full_requires_ok_button_and_black_market_context_gate():
    resolver = build_default_resolver()

    ungated = resolver.resolve(batch(LANDMARK_INVENTORY_FULL_OK_BUTTON))
    gated = resolver.resolve(
        batch(
            "landmark.black_market_title",
            LANDMARK_INVENTORY_FULL_OK_BUTTON,
        )
    )

    assert ungated.status is ResolutionStatus.UNKNOWN
    assert ungated.overlays == ()
    assert gated.base_context == SCREEN_BLACK_MARKET
    assert gated.overlays == (POPUP_INVENTORY_FULL,)


def test_world_boss_inventory_full_is_distinct_and_resolves_over_world_boss():
    state = build_default_resolver().resolve(
        batch(
            LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
            LANDMARK_WORLD_BOSS_INVENTORY_FULL_PROMPT,
        )
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_WORLD_BOSS
    assert state.overlays == (POPUP_WORLD_BOSS_INVENTORY_FULL,)


def test_world_boss_bag_full_requires_world_boss_context_and_resolves_distinctly():
    resolver = build_default_resolver()

    ungated = resolver.resolve(batch(LANDMARK_WORLD_BOSS_BAG_FULL_PROMPT))
    gated = resolver.resolve(
        batch(
            LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
            LANDMARK_WORLD_BOSS_BAG_FULL_PROMPT,
        )
    )

    assert ungated.status is ResolutionStatus.UNKNOWN
    assert ungated.overlays == ()
    assert gated.status is ResolutionStatus.RESOLVED
    assert gated.base_context == SCREEN_WORLD_BOSS
    assert gated.overlays == (POPUP_WORLD_BOSS_BAG_FULL,)


def test_catalog_returns_unknown_for_insufficient_evidence():
    state = build_default_resolver().resolve(batch("element.unrelated"))

    assert state.status is ResolutionStatus.UNKNOWN
    assert state.base_context is None
    assert state.overlays == ()


def test_catalog_exposes_deliberate_conflict_as_ambiguous():
    first, second = BASE_CONTEXT_RULES[:2]

    state = build_default_resolver().resolve(
        batch(*first.requires, *second.requires)
    )

    assert state.status is ResolutionStatus.AMBIGUOUS
    assert state.base_candidates == tuple(sorted((first.name, second.name)))


def test_reversing_catalog_rules_does_not_change_unique_resolution():
    target = BASE_CONTEXT_RULES[-1]
    evidence = batch(*target.requires)

    normal = build_default_resolver().resolve(evidence)
    reversed_rules = ContextResolver(
        base_rules=tuple(reversed(BASE_CONTEXT_RULES)),
        overlay_rules=tuple(reversed(OVERLAY_RULES)),
    ).resolve(evidence)

    assert normal == reversed_rules
    assert normal.base_context == target.name


def test_reversing_catalog_rules_does_not_hide_conflicts():
    first, second = BASE_CONTEXT_RULES[:2]
    evidence = batch(*first.requires, *second.requires)

    normal = build_default_resolver().resolve(evidence)
    reversed_rules = ContextResolver(
        base_rules=tuple(reversed(BASE_CONTEXT_RULES)),
        overlay_rules=OVERLAY_RULES,
    ).resolve(evidence)

    assert normal == reversed_rules
    assert normal.status is ResolutionStatus.AMBIGUOUS


def test_catalog_semantic_names_are_unique_and_implementation_independent():
    rule_names = tuple(
        rule.name for rule in (*BASE_CONTEXT_RULES, *OVERLAY_RULES)
    )
    all_names = (*rule_names, *SEMANTIC_OBSERVATION_NAMES)
    forbidden_fragments = (
        "asset",
        "template",
        ".png",
        "/",
        "\\",
        "opencv",
        "matchtemplate",
        "ocr",
        "vlm",
        "tesseract",
        "yolo",
        "gpt",
        "coords",
        "coordinate",
        "region",
        "pixel",
    )

    assert len(rule_names) == len(set(rule_names))
    assert len(SEMANTIC_OBSERVATION_NAMES) == len(
        set(SEMANTIC_OBSERVATION_NAMES)
    )
    assert all(
        re.fullmatch(r"[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+", name)
        for name in all_names
    )
    assert all(
        fragment not in name
        for name in all_names
        for fragment in forbidden_fragments
    )


def test_catalog_contains_only_the_deliberate_minimal_slice():
    assert len(BASE_CONTEXT_RULES) == 6
    assert len(OVERLAY_RULES) == 9
    assert len(SEMANTIC_OBSERVATION_NAMES) == 15
    assert "landmark.gold_currency_icon" not in SEMANTIC_OBSERVATION_NAMES


def test_quick_menu_is_an_overlay_with_its_own_landmark():
    quick_rule = next(rule for rule in OVERLAY_RULES if rule.name == MENU_QUICK)

    assert quick_rule.requires == (LANDMARK_QUICK_MENU_LOBBY_TILE,)


def test_lobby_requires_only_the_trading_center_label():
    lobby_rule = next(
        rule for rule in BASE_CONTEXT_RULES if rule.name == SCREEN_LOBBY
    )

    assert lobby_rule.requires == (LANDMARK_LOBBY_TRADING_CENTER_LABEL,)


def test_character_select_keeps_its_single_header_requirement():
    character_rule = next(
        rule
        for rule in BASE_CONTEXT_RULES
        if rule.name == SCREEN_CHARACTER_SELECT
    )

    assert character_rule.requires == (LANDMARK_CHARACTER_SELECT_HEADER,)


@pytest.mark.parametrize(
    ("context", "landmark"),
    (
        (SCREEN_BATTLE_MODE_SELECT, LANDMARK_BATTLE_MODE_SELECT_HEADER),
        (SCREEN_WORLD_BOSS, LANDMARK_WORLD_BOSS_SAPPHIRES_USED),
        (SCREEN_WORLD_BOSS_BATTLE, LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE),
    ),
)
def test_world_boss_base_contexts_use_one_structural_landmark(context, landmark):
    rule = next(item for item in BASE_CONTEXT_RULES if item.name == context)

    assert rule.requires == (landmark,)


@pytest.mark.parametrize(
    ("context", "landmark"),
    (
        (OVERLAY_WORLD_BOSS_SELECT_BOSS, LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER),
        (
            POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
            LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
        ),
        (
            OVERLAY_WORLD_BOSS_RAID_COMPLETE,
            LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
        ),
    ),
)
def test_world_boss_overlays_use_one_specific_landmark(context, landmark):
    rule = next(item for item in OVERLAY_RULES if item.name == context)

    assert rule.requires == (landmark,)


def test_default_resolver_builder_does_not_create_a_singleton():
    first = build_default_resolver()
    second = build_default_resolver()

    assert first == second
    assert first is not second


def test_catalog_imports_without_legacy_assets_or_perception(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import bot.catalog; "
                "assert 'numpy' not in sys.modules; "
                "assert 'cv2' not in sys.modules; "
                "assert 'av' not in sys.modules; "
                "assert 'bot.adb' not in sys.modules; "
                "assert 'bot.capture' not in sys.modules; "
                "assert 'bot.screen' not in sys.modules; "
                "assert 'bot.constants' not in sys.modules"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
