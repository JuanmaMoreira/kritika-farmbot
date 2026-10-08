"""Portable pixel equivalence for the verified Stages modal family."""
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.perception import (
    ScopeSpec, STRONG_LOBBY_COMPLETION_SPEC_NAMES,
    STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES, build_default_perception,
    select_detectors,
)
from bot.perception.stages import StagesDetector
from bot.stages_wiring import STAGES_RESULTS_RETURN_SCOPE
from test_stages_episode_replay import frame as episode_frame, manifest as episodes
from test_stages_no_ads_replay import frame as alert_frame, manifest as alerts
from test_stages_start_replay import portal_frame


@pytest.fixture(scope="module")
def profiles():
    full = select_detectors(build_default_perception(), ScopeSpec(
        "stages_daily", STRONG_LOBBY_COMPLETION_SPEC_NAMES,
        (*STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES, StagesDetector),
    ))
    return full, select_detectors(full, STAGES_RESULTS_RETURN_SCOPE), build_default_resolver()


@pytest.mark.parametrize("kind,label", [
    *[("episode", label) for label in episodes],
    *[("alert", label) for label in alerts],
    ("portal", "start"),
])
def test_scoped_pixels_preserve_stage_facts_and_resolved_layers(profiles, kind, label):
    image = episode_frame(label) if kind == "episode" else (
        alert_frame(label) if kind == "alert" else portal_frame()
    )
    snapshot = FrameSnapshot(image, 100., 1)
    full, scoped, resolver = profiles
    before, after = full.analyze(snapshot), scoped.analyze(snapshot)
    stage_facts = lambda batch: tuple(
        (fact.name, fact.value, fact.confidence)
        for fact in batch.observations if fact.name.startswith("stages.")
    )
    assert stage_facts(before) == stage_facts(after)
    a, b = resolver.resolve(before), resolver.resolve(after)
    assert (a.status, a.base_context, a.overlays) == (b.status, b.base_context, b.overlays)
