"""Rotation R2-A: scoped post-swipe wait, with R2-B kept global."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_CHARACTER_SELECT, build_default_resolver
from bot.perception import (
    ROTATION_CHARACTER_SELECTION_SCOPE,
    ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.productive_runtime import ProductiveRuntime
from bot.rotation import _is_clean_base, _is_contradictory_character_select
from bot.runtime_observer import RuntimeObserver
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]
CHARACTER_SELECT = "screencaps/semantic/character_select/20260823T025400_922432Z.png"
QUICK_MENU = "screencaps/semantic/guild/quick-menu-from-guild/01.png"
FOREIGN = "screencaps/semantic/battle_mode_select/20260823T025716_783619Z.png"


def _frame(path):
    image = cv2.imread(str(ROOT / path))
    assert image is not None
    return FrameSnapshot(image=image, sequence=1, timestamp=1.0)


def _state(frame, engine):
    return build_default_resolver().resolve(engine.analyze(frame))


def test_post_swipe_subset_is_exact_source_instances_in_order_and_fails_fast():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, ROTATION_CHARACTER_SELECTION_SCOPE)
    expected = tuple(
        item for item in source.detectors
        if getattr(getattr(item, "spec", None), "name", None)
        in ROTATION_CHARACTER_SELECTION_SCOPE_SPEC_NAMES
    )
    assert len(source.detectors) == 97
    assert len(scoped.detectors) == 2
    assert tuple(scoped.detectors) == expected
    assert all(actual is wanted for actual, wanted in zip(scoped.detectors, expected))
    without_header = tuple(item for item in expected if item.spec.name != "landmark.character_select_header")
    with pytest.raises(ValueError, match="character_select_header"):
        select_detectors(PerceptionEngine(detectors=without_header), ROTATION_CHARACTER_SELECTION_SCOPE)


@pytest.mark.parametrize("path,expected_clean,expected_abort", (
    (CHARACTER_SELECT, True, False),
    (QUICK_MENU, False, False),
    (FOREIGN, False, False),
))
def test_post_swipe_semantics_authorize_only_clean_character_select(path, expected_clean, expected_abort):
    state = _state(_frame(path), select_detectors(build_default_perception(ROOT), ROTATION_CHARACTER_SELECTION_SCOPE))
    snapshot = SimpleNamespace(state=state)
    assert _is_clean_base(snapshot, SCREEN_CHARACTER_SELECT) is expected_clean
    assert _is_contradictory_character_select(snapshot) is expected_abort
    if path == QUICK_MENU:
        assert state.overlays == ("menu.quick",)
    if path == FOREIGN:
        assert state.status.value == "unknown"
    # A foreign screen may lose its global abort and time out, but never
    # satisfies the clean-screen predicate that authorizes the next swipe/tap.


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


def test_productive_rotation_scopes_only_post_swipe_and_r1_card_selection():
    events = _Events()
    frame = FrameSnapshot(image=np.zeros((1224, 2712, 3), dtype=np.uint8), sequence=1, timestamp=1.0)
    observer = RuntimeObserver(
        _Source(frame), build_default_perception(ROOT), build_default_resolver(), events=events,
    )
    actions = _Actions()
    recovery = _Recovery()
    main = VerifiedTransition(observer, actions, events, recovery)
    dependencies = SimpleNamespace(
        observer=observer, actions=actions, events=events,
        build_verified_transition=lambda: main,
    )
    rotation = ProductiveRuntime.build_rotation(dependencies, 28)
    assert rotation.observer is observer
    assert rotation.post_swipe_observer is not observer
    assert len(rotation.post_swipe_observer.perception.detectors) == 2
    assert rotation.post_swipe_observer.source is observer.source
    assert rotation.post_swipe_observer.resolver is observer.resolver
    assert rotation.post_swipe_observer.poll_interval == observer.poll_interval
    assert rotation.selection_transition.observer is not rotation.post_swipe_observer
    assert len(rotation.selection_transition.observer.perception.detectors) == 2
    assert rotation.selection_transition.obstruction_recovery is recovery
    # ConfirmCharacterSelection remains on this global transition (R2-B).
    assert rotation.verified_transition is main
    assert len(rotation.verified_transition.observer.perception.detectors) == 97
    assert rotation.scroll_profile.settle_for == 1.0
    assert ("rotation.post_swipe_scope_active", {"detector_count": 2}) in events.records
    assert ("rotation.character_selection_scope_active", {"detector_count": 2}) in events.records
