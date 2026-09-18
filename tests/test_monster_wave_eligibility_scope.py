"""Scoped perception for the Monster Wave daily eligibility check.

The Battle Mode hub badge decision shares the World Boss eligibility
detector set exactly: the hub header, both daily badges and the overlays
that can obscure the prepared hub. The check therefore reuses
``WORLD_BOSS_ELIGIBILITY_SCOPE`` through the generic
``scoped_observer_for`` seam instead of growing a second scope.
"""

import inspect
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.eligibility import EligibilityStatus
from bot.monster_wave_eligibility import (
    MonsterWaveDailyEligibility,
    monster_wave_daily_status,
)
from bot.monster_wave_semantics import STATUS_MONSTER_WAVE_DAILY_ACTIVE
from bot.perception import (
    WORLD_BOSS_ELIGIBILITY_SCOPE,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.productive_runtime import ProductiveRuntime
from bot.runtime_observer import RuntimeObserver
from tools.semantic_slice_evaluation import load_manifest

ROOT = Path(__file__).resolve().parents[1]


class FakeSource:
    def __init__(self, frame):
        self.frame = frame

    def get_frame(self):
        return self.frame


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


def _real_observer(events, perception):
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    return RuntimeObserver(
        FakeSource(frame),
        perception,
        build_default_resolver(),
        events=events,
    )


def _hub_entries():
    entries = load_manifest(ROOT / "datasets/monster_wave_semantic_manifest.json")
    hub = [entry for entry in entries if "/battle-mode-select" in entry.path]
    foreign = [entry for entry in entries if "/battle-mode-select" not in entry.path]
    assert len(hub) == 19, [entry.path for entry in hub]
    assert len(foreign) > 0
    return hub, foreign[:6]


def test_scoped_monster_wave_decision_matches_global_on_hub_and_foreign_frames():
    global_engine = build_default_perception(ROOT)
    scoped_engine = select_detectors(global_engine, WORLD_BOSS_ELIGIBILITY_SCOPE)
    resolver = build_default_resolver()
    assert len(global_engine.detectors) == 97
    assert len(scoped_engine.detectors) == 5

    hub, foreign = _hub_entries()
    for i, entry in enumerate((*hub, *foreign), 1):
        frame = cv2.imread(str(ROOT / entry.path))
        assert frame is not None, entry.path
        snapshot = FrameSnapshot(frame, float(i), i)
        global_state = resolver.resolve(global_engine.analyze(snapshot))
        scoped_state = resolver.resolve(scoped_engine.analyze(snapshot))
        global_decision = monster_wave_daily_status(SimpleNamespace(state=global_state))
        scoped_decision = monster_wave_daily_status(SimpleNamespace(state=scoped_state))
        assert scoped_decision is global_decision, entry.path
        if entry in hub:
            expected = (
                EligibilityStatus.ELIGIBLE
                if STATUS_MONSTER_WAVE_DAILY_ACTIVE in entry.overlays
                else EligibilityStatus.NOT_ELIGIBLE
            )
            assert scoped_decision is expected, entry.path
            assert scoped_state.base_context == SCREEN_BATTLE_MODE_SELECT, entry.path
            assert set(scoped_state.overlays) == set(entry.overlays), entry.path
        else:
            assert scoped_decision is EligibilityStatus.UNKNOWN, entry.path


def test_runtime_builds_monster_wave_eligibility_on_shared_hub_scope():
    events = Events()
    observer = _real_observer(events, build_default_perception(ROOT))
    runtime = SimpleNamespace(
        observer=observer, events=events, cancel_requested=lambda: False
    )

    check = ProductiveRuntime.build_monster_wave_daily_eligibility(runtime)

    assert isinstance(check, MonsterWaveDailyEligibility)
    assert isinstance(check.observer, RuntimeObserver)
    assert check.observer is not observer
    assert len(check.observer.perception.detectors) == 5
    assert check.observer.source is observer.source
    assert check.observer.resolver is observer.resolver
    assert (
        "monster_wave.eligibility_scope_active",
        {"detector_count": 5},
    ) in [(name, fields) for name, fields in events.items]


def test_runtime_falls_back_to_main_observer():
    events = Events()
    main = _real_observer(events, PerceptionEngine(detectors=()))
    runtime = SimpleNamespace(
        observer=main, events=events, cancel_requested=lambda: False
    )
    assert ProductiveRuntime.build_monster_wave_daily_eligibility(runtime).observer is main
    assert any(
        name == "monster_wave.eligibility_scope_unavailable" for name, _ in events.items
    )


def test_wiring_uses_generic_infra_only():
    source_text = inspect.getsource(
        ProductiveRuntime.build_monster_wave_daily_eligibility
    )
    assert "scoped_observer_for(" in source_text
    assert "WORLD_BOSS_ELIGIBILITY_SCOPE" in source_text
    for forbidden in (
        "_monster_wave_scope_builder",
        "_monster_wave_select_detectors",
        "monster_wave_perception",
    ):
        assert forbidden not in source_text
