"""Rotation R1 scoped perception for predecessor-card verification only."""

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_CHARACTER_SELECT, build_default_resolver
from bot.character_select_layout import predecessor_center, tile_box
from bot.character_selection import (
    CharacterSelectionState,
    DEFAULT_CHARACTER_SELECTION_DETECTOR,
)
from bot.create_character_sentinel import DEFAULT_SENTINEL_DETECTOR
from bot.perception import (
    ROTATION_CHARACTER_SELECTION_SCOPE,
    ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.productive_runtime import ProductiveRuntime
from bot.rotation import (
    _has_unexpected_character_selection_state,
    _is_clean_base,
    _is_selected,
    replace_selection_region,
)
from bot.runtime_observer import RuntimeObserver
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]
FAILURE_EVIDENCE = (
    "failure_1297429c865f4d88925dfc4277a1ce6f",
    "failure_50aff0cc123f488ebb35ed26ffe17834",
    "failure_a65642f0e0204b10b7becb08a419d356",
    "failure_fb8201882b60453fb257bf5f25a16145",
)
SUCCESS_FRAMES = (
    "screencaps/semantic/character_select/20260823T025400_922432Z.png",
    "screencaps/semantic/character_select/sentinel/plus-col2-bottom.png",
)
QUICK_MENU_FRAME = "screencaps/semantic/guild/quick-menu-from-guild/01.png"


def _scoped(source=None):
    source = source or build_default_perception(ROOT)
    return select_detectors(source, ROTATION_CHARACTER_SELECTION_SCOPE)


def _snapshot(image, sequence=1, timestamp=1.0):
    return FrameSnapshot(image=image, sequence=sequence, timestamp=timestamp)


def _runtime_snapshot(image, engine, sequence=1, timestamp=1.0):
    frame = _snapshot(image, sequence, timestamp)
    batch = engine.analyze(frame)
    resolver = build_default_resolver()
    from bot.action_executor import FrameGeometry
    from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, _facts_from

    return RuntimeSnapshot(
        frame=frame,
        observations=batch,
        state=resolver.resolve(batch),
        facts=_facts_from(batch),
        geometry=FrameGeometry.from_frame(image),
    )


def test_rotation_scope_selects_exactly_two_existing_detectors_in_source_order():
    source = build_default_perception(ROOT)
    scoped = _scoped(source)

    assert len(source.detectors) == 96
    assert len(scoped.detectors) == 2
    assert {
        detector.spec.name for detector in scoped.detectors
    } == set(ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES)
    expected = tuple(
        detector
        for detector in source.detectors
        if getattr(getattr(detector, "spec", None), "name", None)
        in ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES
    )
    assert tuple(scoped.detectors) == expected
    assert all(actual is wanted for actual, wanted in zip(scoped.detectors, expected))


def test_rotation_scope_fails_fast_when_any_required_detector_is_missing():
    source = build_default_perception(ROOT)
    incomplete = PerceptionEngine(detectors=(source.detectors[1],))

    with pytest.raises(ValueError, match="quick_menu_lobby_tile"):
        _scoped(incomplete)


@pytest.mark.parametrize("failure_name", FAILURE_EVIDENCE)
def test_failure_evidence_keeps_context_and_local_selected_reader(failure_name):
    evidence = ROOT / "artifacts/failure_evidence" / failure_name
    failure = json.loads((evidence / "failure.json").read_text(encoding="utf-8"))
    assert failure["failure"]["message"].endswith(
        "late_expected_state_not_stable"
    )
    middle = failure["snapshots"][1]
    metadata = json.loads(
        (evidence / middle["snapshot"]).read_text(encoding="utf-8")
    )
    thumbnail = cv2.imread(str(evidence / middle["frame"]))
    assert thumbnail is not None
    image = cv2.resize(
        thumbnail,
        (metadata["geometry"]["width"], metadata["geometry"]["height"]),
        interpolation=cv2.INTER_LINEAR,
    )
    full_snapshot = _runtime_snapshot(
        image,
        build_default_perception(ROOT),
        metadata["sequence"],
        metadata["timestamp"],
    )
    scoped_snapshot = _runtime_snapshot(
        image,
        _scoped(),
        metadata["sequence"],
        metadata["timestamp"],
    )
    sentinel = DEFAULT_SENTINEL_DETECTOR.measure(scoped_snapshot.frame)
    assert sentinel.confirmed
    target = predecessor_center(sentinel.location)
    local_reader = replace_selection_region(
        DEFAULT_CHARACTER_SELECTION_DETECTOR, tile_box(target)
    )

    assert full_snapshot.state == scoped_snapshot.state
    assert _is_clean_base(scoped_snapshot, SCREEN_CHARACTER_SELECT)
    assert not _has_unexpected_character_selection_state(scoped_snapshot)
    assert _is_selected(scoped_snapshot, local_reader)
    assert local_reader.measure(scoped_snapshot.frame).state is CharacterSelectionState.SELECTED


@pytest.mark.parametrize("path", SUCCESS_FRAMES)
def test_full_size_character_select_frames_preserve_relevant_semantics(path):
    image = cv2.imread(str(ROOT / path))
    assert image is not None
    global_snapshot = _runtime_snapshot(image, build_default_perception(ROOT))
    scoped_snapshot = _runtime_snapshot(image, _scoped())

    assert scoped_snapshot.state == global_snapshot.state
    assert _is_clean_base(scoped_snapshot, SCREEN_CHARACTER_SELECT)
    assert not _has_unexpected_character_selection_state(scoped_snapshot)


def test_scope_preserves_quick_menu_as_an_abort_blocker():
    image = cv2.imread(str(ROOT / QUICK_MENU_FRAME))
    assert image is not None
    snapshot = _runtime_snapshot(image, _scoped())

    assert snapshot.state.overlays == ("menu.quick",)
    assert _has_unexpected_character_selection_state(snapshot)


class _Source:
    def __init__(self, frame):
        self.frame = frame

    def get_frame(self):
        return self.frame


class _Actions:
    def execute(self, action, geometry):
        pass


class _Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


class _Recovery:
    def attempt(self, snapshot, expected):
        return None


def test_productive_runtime_routes_only_card_selection_to_scoped_transition():
    frame = _snapshot(np.zeros((1224, 2712, 3), dtype=np.uint8))
    events = _Events()
    actions = _Actions()
    observer = RuntimeObserver(
        _Source(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
    )
    recovery = _Recovery()
    main = VerifiedTransition(observer, actions, events, recovery)
    dependencies = SimpleNamespace(
        observer=observer,
        actions=actions,
        events=events,
        build_verified_transition=lambda: main,
    )

    rotation = ProductiveRuntime.build_rotation(dependencies, 7)

    assert rotation.verified_transition is main
    assert rotation.selection_transition is not main
    assert len(rotation.selection_transition.observer.perception.detectors) == 2
    assert rotation.selection_transition.observer.source is observer.source
    assert rotation.selection_transition.observer.resolver is observer.resolver
    assert rotation.selection_transition.obstruction_recovery is recovery
    assert rotation.selection_settle_for == 0.25
    assert rotation.selection_policy.normal_timeout == 1.0
    assert rotation.selection_policy.grace_timeout == 0.75
    assert rotation.selection_policy.max_attempts == 2
    assert (
        "rotation.character_selection_scope_active",
        {"detector_count": 2},
    ) in events.records
