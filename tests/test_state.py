from dataclasses import FrozenInstanceError

import pytest

from bot.state import ResolutionStatus, ResolvedState


def test_resolved_state_requires_and_preserves_base_context():
    state = ResolvedState(
        ResolutionStatus.RESOLVED,
        sequence=8,
        timestamp=50.25,
        base_context="screen.black_market",
    )

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == "screen.black_market"
    assert state.sequence == 8
    assert state.timestamp == 50.25


def test_unknown_is_a_valid_first_class_result():
    state = ResolvedState(ResolutionStatus.UNKNOWN, sequence=9, timestamp=51.0)

    assert state.base_context is None
    assert state.base_candidates == ()


def test_ambiguous_preserves_conflicting_semantic_candidates():
    state = ResolvedState(
        ResolutionStatus.AMBIGUOUS,
        sequence=10,
        timestamp=52.0,
        base_candidates=("screen.lobby", "screen.black_market"),
    )

    assert state.base_context is None
    assert state.base_candidates == ("screen.lobby", "screen.black_market")


def test_resolved_state_represents_base_subcontext_and_overlays_separately():
    state = ResolvedState(
        ResolutionStatus.RESOLVED,
        sequence=11,
        timestamp=53.0,
        base_context="screen.black_market",
        subcontext="tab.daily_items",
        overlays=("popup.daily_reward", "popup.network_error"),
    )

    assert state.base_context == "screen.black_market"
    assert state.subcontext == "tab.daily_items"
    assert state.overlays == ("popup.daily_reward", "popup.network_error")


def test_unknown_base_can_coexist_with_a_known_overlay():
    state = ResolvedState(
        ResolutionStatus.UNKNOWN,
        sequence=12,
        timestamp=54.0,
        overlays=("popup.network_error",),
    )

    assert state.base_context is None
    assert state.overlays == ("popup.network_error",)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": ResolutionStatus.RESOLVED},
        {"status": ResolutionStatus.UNKNOWN, "base_context": "screen.lobby"},
        {"status": ResolutionStatus.UNKNOWN, "subcontext": "tab.events"},
        {
            "status": ResolutionStatus.UNKNOWN,
            "base_candidates": ("screen.lobby", "screen.shop"),
        },
        {"status": ResolutionStatus.AMBIGUOUS},
        {
            "status": ResolutionStatus.AMBIGUOUS,
            "base_context": "screen.lobby",
            "base_candidates": ("screen.lobby", "screen.shop"),
        },
        {
            "status": ResolutionStatus.RESOLVED,
            "base_context": "screen.lobby",
            "base_candidates": ("screen.lobby", "screen.shop"),
        },
        {
            "status": ResolutionStatus.RESOLVED,
            "base_context": "screen.lobby",
            "overlays": ("popup.reward", "popup.reward"),
        },
    ],
)
def test_rejects_invalid_status_combinations(kwargs):
    with pytest.raises(ValueError):
        ResolvedState(sequence=1, timestamp=1.0, **kwargs)


def test_rejects_invalid_status_type_and_frame_identity():
    with pytest.raises(ValueError, match="status"):
        ResolvedState("unknown", sequence=1, timestamp=1.0)
    with pytest.raises(ValueError, match="sequence"):
        ResolvedState(ResolutionStatus.UNKNOWN, sequence=-1, timestamp=1.0)
    with pytest.raises(ValueError, match="timestamp"):
        ResolvedState(ResolutionStatus.UNKNOWN, sequence=1, timestamp=float("nan"))


def test_state_and_collections_are_immutable():
    state = ResolvedState(
        ResolutionStatus.RESOLVED,
        sequence=1,
        timestamp=1.0,
        base_context="screen.lobby",
        overlays=["popup.reward"],
    )

    assert state.overlays == ("popup.reward",)
    with pytest.raises(FrozenInstanceError):
        state.status = ResolutionStatus.UNKNOWN
