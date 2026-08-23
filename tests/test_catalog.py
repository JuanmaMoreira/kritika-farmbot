import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from bot.catalog import (
    BASE_CONTEXT_RULES,
    OVERLAY_RULES,
    POPUP_BLACK_MARKET_PURCHASE_CONFIRMATION,
    SCREEN_BLACK_MARKET,
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

    assert state.status is ResolutionStatus.UNKNOWN
    assert state.base_context is None
    assert state.overlays == (overlay_rule.name,)


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
    purchase_rule = OVERLAY_RULES[0]

    state = resolver.resolve(
        batch(*black_market_rule.requires, *purchase_rule.requires)
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_BLACK_MARKET
    assert state.overlays == (POPUP_BLACK_MARKET_PURCHASE_CONFIRMATION,)


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
    assert len(BASE_CONTEXT_RULES) == 4
    assert len(OVERLAY_RULES) == 1
    assert len(SEMANTIC_OBSERVATION_NAMES) == 5


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
