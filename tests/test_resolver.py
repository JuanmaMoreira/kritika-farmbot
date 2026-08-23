from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import subprocess
import sys

import pytest

from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resolver import ContextResolver, ContextRule, RuleMatch, match_rule
from bot.state import ResolutionStatus


def observation(
    name,
    confidence=0.9,
    source=ObservationSource.LOCAL_CV,
    region=None,
):
    return Observation(name, confidence, source, region=region)


def batch(*observations, sequence=7, timestamp=42.5):
    return ObservationBatch(sequence, timestamp, observations)


def rule(name="screen.lobby", requires=("element.lobby_title",), threshold=0.8):
    return ContextRule(name, requires, threshold)


def test_rule_is_validated_normalized_and_immutable():
    context_rule = rule(
        requires=["element.start", "element.lobby_title"], threshold=0.75
    )

    assert context_rule.name == "screen.lobby"
    assert context_rule.requires == ("element.lobby_title", "element.start")
    assert context_rule.min_confidence == 0.75
    with pytest.raises(FrozenInstanceError):
        context_rule.min_confidence = 0.5


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_rule_accepts_confidence_boundaries(threshold):
    assert rule(threshold=threshold).min_confidence == threshold


@pytest.mark.parametrize(
    "threshold", [-0.01, 1.01, float("nan"), float("inf"), True]
)
def test_rule_rejects_invalid_confidence(threshold):
    with pytest.raises(ValueError, match="confidence"):
        rule(threshold=threshold)


def test_rule_rejects_empty_requirements():
    with pytest.raises(ValueError, match="empty"):
        rule(requires=())


def test_rule_rejects_duplicate_requirements():
    with pytest.raises(ValueError, match="duplicates"):
        rule(requires=("element.start", "element.start"))


@pytest.mark.parametrize(
    ("name", "requires"),
    [("lobby", ("element.start",)), ("screen.lobby", ("start",))],
)
def test_rule_rejects_invalid_semantic_names(name, requires):
    with pytest.raises(ValueError):
        rule(name=name, requires=requires)


@pytest.mark.parametrize("category", ["base", "overlay"])
def test_resolver_rejects_duplicate_rule_names_per_category(category):
    duplicate_rules = (
        rule(requires=("element.first",)),
        rule(requires=("element.second",)),
    )
    kwargs = {f"{category}_rules": duplicate_rules}

    with pytest.raises(ValueError, match="duplicate rule names"):
        ContextResolver(**kwargs)


def test_no_base_candidate_resolves_unknown_without_error():
    resolver = ContextResolver(base_rules=(rule(),))

    state = resolver.resolve(batch())

    assert state.status is ResolutionStatus.UNKNOWN
    assert state.base_context is None
    assert state.base_candidates == ()


def test_exactly_one_base_candidate_resolves():
    resolver = ContextResolver(base_rules=(rule(),))

    state = resolver.resolve(batch(observation("element.lobby_title")))

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == "screen.lobby"
    assert state.base_candidates == ()


def test_multiple_distinct_base_candidates_are_ambiguous():
    resolver = ContextResolver(
        base_rules=(
            rule("screen.lobby", ("element.lobby_title",)),
            rule("screen.inventory", ("element.inventory_title",)),
        )
    )

    state = resolver.resolve(
        batch(
            observation("element.lobby_title"),
            observation("element.inventory_title"),
        )
    )

    assert state.status is ResolutionStatus.AMBIGUOUS
    assert state.base_context is None
    assert state.base_candidates == ("screen.inventory", "screen.lobby")


def test_rule_order_never_breaks_base_context_ties():
    inventory = rule("screen.inventory", ("element.inventory_title",))
    lobby = rule("screen.lobby", ("element.lobby_title",))
    evidence = batch(
        observation("element.inventory_title", 0.81),
        observation("element.lobby_title", 0.99),
    )

    forward = ContextResolver((inventory, lobby)).resolve(evidence)
    reverse = ContextResolver((lobby, inventory)).resolve(evidence)

    assert forward == reverse
    assert forward.status is ResolutionStatus.AMBIGUOUS
    assert forward.base_candidates == ("screen.inventory", "screen.lobby")


@pytest.mark.parametrize(
    ("confidence", "expected_status"),
    [
        (0.7999, ResolutionStatus.UNKNOWN),
        (0.8, ResolutionStatus.RESOLVED),
        (0.8001, ResolutionStatus.RESOLVED),
    ],
)
def test_threshold_is_inclusive(confidence, expected_status):
    resolver = ContextResolver((rule(threshold=0.8),))

    state = resolver.resolve(batch(observation("element.lobby_title", confidence)))

    assert state.status is expected_status


def test_every_required_signal_must_satisfy_threshold():
    resolver = ContextResolver(
        (rule(requires=("element.lobby_title", "element.start")),)
    )

    partial = resolver.resolve(batch(observation("element.lobby_title", 0.95)))
    weak = resolver.resolve(
        batch(
            observation("element.lobby_title", 0.95),
            observation("element.start", 0.79),
        )
    )
    complete = resolver.resolve(
        batch(
            observation("element.lobby_title", 0.95),
            observation("element.start", 0.80),
        )
    )

    assert partial.status is ResolutionStatus.UNKNOWN
    assert weak.status is ResolutionStatus.UNKNOWN
    assert complete.status is ResolutionStatus.RESOLVED


@pytest.mark.parametrize(
    "source",
    [ObservationSource.LOCAL_CV, ObservationSource.VLM, ObservationSource.SYSTEM],
)
def test_source_does_not_change_confidence_or_matching(source):
    resolver = ContextResolver((rule(threshold=0.85),))

    state = resolver.resolve(
        batch(observation("element.lobby_title", 0.85, source))
    )

    assert state.status is ResolutionStatus.RESOLVED


def test_repeated_observations_use_highest_confidence_without_fusion():
    context_rule = rule(threshold=0.8)
    evidence = batch(
        observation("element.lobby_title", 0.72, ObservationSource.LOCAL_CV),
        observation("element.lobby_title", 0.91, ObservationSource.VLM),
    )

    matched = match_rule(context_rule, evidence)

    assert matched is not None
    assert len(matched.evidence) == 1
    assert matched.evidence[0].confidence == 0.91
    assert matched.evidence[0].source is ObservationSource.VLM
    assert matched.confidence == 0.91


def test_repeated_weak_observations_are_not_combined_to_cross_threshold():
    context_rule = rule(threshold=0.8)
    evidence = batch(
        observation("element.lobby_title", 0.60, ObservationSource.LOCAL_CV),
        observation("element.lobby_title", 0.60, ObservationSource.VLM),
    )

    assert match_rule(context_rule, evidence) is None


def test_repeated_localized_evidence_counts_once_and_region_is_ignored():
    context_rule = rule(requires=("element.close",), threshold=0.8)
    evidence = batch(
        observation("element.close", 0.70, region=(0.1, 0.1, 0.2, 0.2)),
        observation("element.close", 0.90, region=(0.8, 0.8, 0.9, 0.9)),
    )

    matched = match_rule(context_rule, evidence)

    assert matched is not None
    assert len(matched.evidence) == 1
    assert matched.evidence[0].confidence == 0.90
    assert matched.confidence == 0.90


def test_rule_match_confidence_is_weakest_selected_requirement():
    context_rule = rule(
        requires=("element.lobby_title", "element.start"), threshold=0.8
    )

    matched = match_rule(
        context_rule,
        batch(
            observation("element.lobby_title", 0.95),
            observation("element.start", 0.82),
        ),
    )

    assert isinstance(matched, RuleMatch)
    assert matched.confidence == 0.82
    assert tuple(item.name for item in matched.evidence) == context_rule.requires


def test_base_and_overlay_resolve_independently():
    resolver = ContextResolver(
        base_rules=(rule(),),
        overlay_rules=(
            rule("popup.reward", ("element.reward_title",), 0.85),
        ),
    )

    state = resolver.resolve(
        batch(
            observation("element.lobby_title"),
            observation("element.reward_title"),
        )
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == "screen.lobby"
    assert state.overlays == ("popup.reward",)


def test_overlay_can_resolve_with_unknown_base_context():
    resolver = ContextResolver(
        overlay_rules=(rule("popup.reward", ("element.reward_title",), 0.8),)
    )

    state = resolver.resolve(batch(observation("element.reward_title")))

    assert state.status is ResolutionStatus.UNKNOWN
    assert state.base_context is None
    assert state.overlays == ("popup.reward",)


def test_overlay_can_resolve_with_ambiguous_base_context():
    resolver = ContextResolver(
        base_rules=(
            rule("screen.inventory", ("element.inventory_title",)),
            rule("screen.lobby", ("element.lobby_title",)),
        ),
        overlay_rules=(
            rule("popup.reward", ("element.reward_title",), 0.8),
        ),
    )

    state = resolver.resolve(
        batch(
            observation("element.inventory_title"),
            observation("element.lobby_title"),
            observation("element.reward_title"),
        )
    )

    assert state.status is ResolutionStatus.AMBIGUOUS
    assert state.overlays == ("popup.reward",)


def test_multiple_overlays_are_preserved_in_stable_semantic_order():
    reward = rule("popup.reward", ("element.reward_title",), 0.8)
    connection = rule(
        "popup.connection_warning", ("element.connection_message",), 0.8
    )
    evidence = batch(
        observation("element.reward_title"),
        observation("element.connection_message"),
    )

    forward = ContextResolver(overlay_rules=(reward, connection)).resolve(evidence)
    reverse = ContextResolver(overlay_rules=(connection, reward)).resolve(evidence)

    assert forward == reverse
    assert forward.overlays == ("popup.connection_warning", "popup.reward")


def test_overlay_below_threshold_is_absent():
    resolver = ContextResolver(
        overlay_rules=(rule("popup.reward", ("element.reward_title",), 0.9),)
    )

    state = resolver.resolve(batch(observation("element.reward_title", 0.899)))

    assert state.overlays == ()


def test_resolution_preserves_batch_metadata_and_leaves_subcontext_unresolved():
    resolver = ContextResolver((rule(),))

    state = resolver.resolve(
        batch(observation("element.lobby_title"), sequence=31, timestamp=125.75)
    )

    assert state.sequence == 31
    assert state.timestamp == 125.75
    assert state.subcontext is None


def test_resolution_is_repeatable_and_does_not_mutate_inputs():
    context_rule = rule()
    evidence = batch(observation("element.lobby_title"))
    resolver = ContextResolver([context_rule])
    original_observations = evidence.observations

    first = resolver.resolve(evidence)
    second = resolver.resolve(evidence)

    assert first == second
    assert evidence.observations is original_observations
    assert resolver.base_rules == (context_rule,)
    assert not hasattr(resolver, "current_context")


def test_public_diagnostics_expose_selected_evidence_for_registered_rules():
    base_rule = rule()
    overlay_rule = rule("popup.reward", ("element.reward_title",), 0.8)
    resolver = ContextResolver((base_rule,), (overlay_rule,))
    evidence = batch(
        observation("element.lobby_title", 0.88),
        observation("element.reward_title", 0.92),
    )

    base_matches = resolver.matching_base_rules(evidence)
    overlay_matches = resolver.matching_overlay_rules(evidence)

    assert base_matches[0].rule is base_rule
    assert base_matches[0].confidence == 0.88
    assert overlay_matches[0].rule is overlay_rule
    assert overlay_matches[0].confidence == 0.92


def test_resolver_contract_imports_without_perception_or_infrastructure(tmp_path):
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
                "import sys; import bot.resolver; "
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
