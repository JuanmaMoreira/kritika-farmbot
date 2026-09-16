"""Strong scoped perception for verified transitions that end in Lobby.

These scopes deliberately preserve every catalog base and overlay dependency.
They are not discovery scopes: source/action lineage belongs to the caller,
while resolver ambiguity and blocker semantics stay observationally complete.
"""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    BASE_CONTEXT_RULES,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    OVERLAY_RULES,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception import (
    BLACK_MARKET_TO_LOBBY_SCOPE,
    DAILY_TO_LOBBY_SCOPE,
    FRIENDS_TO_LOBBY_SCOPE,
    MAILBOX_TO_LOBBY_SCOPE,
    PETS_TO_LOBBY_SCOPE,
    QUICK_MENU_TO_LOBBY_SCOPE,
    ROTATION_TO_LOBBY_SCOPE,
    STRONG_LOBBY_COMPLETION_SPEC_NAMES,
    STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.productive_runtime import ProductiveRuntime
from bot.runtime_observer import RuntimeSnapshot, _facts_from
from bot.runtime_observer import RuntimeObserver
from bot.action_executor import FrameGeometry
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition


ROOT = Path(__file__).resolve().parents[1]
LOBBY_FRAMES = (
    "artifacts/daily-semantics/friends-close-lobby/20260831T153734_625140Z_03.png",
    "artifacts/daily-mail-live/lobby-after-quests-close-human-confirmed/20260829T235621_886849Z_05.png",
    "artifacts/daily-mail-live/lobby-after-mailbox-close-human-confirmed/20260830T000428_614592Z_05.png",
    "artifacts/world-boss-live/battle-mode-back-to-lobby-after/20260827T231741_947736Z_04.png",
    "artifacts/eligibility-live/lobby-after/20260908T010232_053425Z_03.png",
)
SCOPES = (
    FRIENDS_TO_LOBBY_SCOPE,
    MAILBOX_TO_LOBBY_SCOPE,
    DAILY_TO_LOBBY_SCOPE,
    BLACK_MARKET_TO_LOBBY_SCOPE,
    PETS_TO_LOBBY_SCOPE,
    QUICK_MENU_TO_LOBBY_SCOPE,
    ROTATION_TO_LOBBY_SCOPE,
)


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


def _runtime_snapshot(image, engine):
    frame = FrameSnapshot(image=image, timestamp=1.0, sequence=1)
    batch = engine.analyze(frame)
    return RuntimeSnapshot(
        frame=frame,
        observations=batch,
        state=build_default_resolver().resolve(batch),
        facts=_facts_from(batch),
        geometry=FrameGeometry.from_frame(image),
    )


def _detector_name(detector):
    return getattr(getattr(detector, "spec", None), "name", None)


def _semantic_batch(*names):
    return ObservationBatch(
        sequence=1,
        timestamp=1.0,
        observations=tuple(
            Observation(name, 1.0, ObservationSource.SYSTEM) for name in names
        ),
    )


def test_strong_lobby_completion_scope_covers_every_catalog_context_dependency():
    local_names = {
        _detector_name(detector)
        for detector in build_default_perception(ROOT).detectors
        if _detector_name(detector) is not None
    }
    context_requirements = {
        requirement
        for rule in (*BASE_CONTEXT_RULES, *OVERLAY_RULES)
        for requirement in rule.requires
    }
    specialized_outputs = {
        "indicator.daily_quests_progress_reward_claimable",
        "indicator.guild_attendance_active",
        "indicator.guild_attendance_completed",
        "indicator.pet_epic_available",
        "indicator.pet_epic_unavailable",
        "landmark.combine_context",
        "landmark.pet_combine_result",
        "landmark.pet_mass_evolve_confirmation",
    }

    assert context_requirements <= (
        STRONG_LOBBY_COMPLETION_SPEC_NAMES | specialized_outputs
    )
    assert context_requirements & local_names <= STRONG_LOBBY_COMPLETION_SPEC_NAMES
    assert len(STRONG_LOBBY_COMPLETION_SPEC_NAMES) == 71
    assert len(STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES) == 6


@pytest.mark.parametrize("rule", OVERLAY_RULES, ids=lambda rule: rule.name)
def test_lobby_positive_plus_any_catalog_overlay_is_never_clean_lobby(rule):
    state = build_default_resolver().resolve(
        _semantic_batch(LANDMARK_LOBBY_TRADING_CENTER_LABEL, *rule.requires)
    )

    assert rule.name in state.overlays
    assert not (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_LOBBY
        and not state.overlays
    )


@pytest.mark.parametrize(
    "rule",
    tuple(rule for rule in BASE_CONTEXT_RULES if rule.name != SCREEN_LOBBY),
    ids=lambda rule: rule.name,
)
def test_lobby_positive_plus_any_foreign_base_is_ambiguous(rule):
    state = build_default_resolver().resolve(
        _semantic_batch(LANDMARK_LOBBY_TRADING_CENTER_LABEL, *rule.requires)
    )

    assert state.status is ResolutionStatus.AMBIGUOUS
    assert state.base_context is None


@pytest.mark.parametrize("scope", SCOPES, ids=lambda scope: scope.name)
def test_lobby_return_scopes_reuse_exact_source_instances_and_order(scope):
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, scope)
    expected = tuple(
        detector
        for detector in source.detectors
        if _detector_name(detector) in scope.spec_names
        or isinstance(detector, scope.specialized_types)
    )

    assert scoped.detectors == expected
    assert all(actual is original for actual, original in zip(scoped.detectors, expected))
    assert len(scoped.detectors) == 77
    assert len(scoped.detectors) < len(source.detectors) == 95


@pytest.mark.parametrize("scope", SCOPES, ids=lambda scope: scope.name)
def test_lobby_return_scopes_fail_fast_when_lobby_detector_is_missing(scope):
    source = build_default_perception(ROOT)
    without_lobby = PerceptionEngine(detectors=source.detectors[1:])

    with pytest.raises(ValueError, match="missing detectors"):
        select_detectors(without_lobby, scope)


@pytest.mark.parametrize("path", LOBBY_FRAMES)
@pytest.mark.parametrize("scope", SCOPES, ids=lambda scope: scope.name)
def test_real_clean_lobby_frames_preserve_global_success(scope, path):
    image = cv2.imread(str(ROOT / path))
    assert image is not None
    global_snapshot = _runtime_snapshot(image, build_default_perception(ROOT))
    scoped_snapshot = _runtime_snapshot(
        image,
        select_detectors(build_default_perception(ROOT), scope),
    )

    assert scoped_snapshot.state == global_snapshot.state
    assert scoped_snapshot.state.status is ResolutionStatus.RESOLVED
    assert scoped_snapshot.state.base_context == SCREEN_LOBBY
    assert not scoped_snapshot.state.overlays


@pytest.mark.parametrize("scope", SCOPES, ids=lambda scope: scope.name)
def test_blank_unknown_frame_never_becomes_lobby_success(scope):
    image = np.zeros((1224, 2712, 3), dtype=np.uint8)
    snapshot = _runtime_snapshot(
        image,
        select_detectors(build_default_perception(ROOT), scope),
    )

    assert snapshot.state.status is ResolutionStatus.UNKNOWN
    assert snapshot.state.base_context is None
    assert not snapshot.state.overlays


def test_productive_registry_routes_direct_lobby_returns_to_scoped_observation():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    events = _Events()
    actions = _Actions()
    observer = RuntimeObserver(
        _Source(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
    )
    main = VerifiedTransition(observer, actions, events)
    dependencies = SimpleNamespace(
        observer=observer,
        actions=actions,
        events=events,
        cancel_requested=lambda: False,
        build_verified_transition=lambda: main,
    )

    friends = DEFAULT_FLOW_REGISTRY.get("send_stamina").build(dependencies)
    daily = DEFAULT_FLOW_REGISTRY.get("daily_quests").build(dependencies)
    mailbox = DEFAULT_FLOW_REGISTRY.get("mailbox").build(dependencies)
    market = DEFAULT_FLOW_REGISTRY.get("black_market").build(dependencies)

    for scoped in (
        friends.lobby_observer,
        daily.lobby_observer,
        mailbox.lobby_observer,
        market.close_transition.observer,
    ):
        assert scoped is not observer
        assert len(scoped.perception.detectors) == 77
        assert scoped.source is observer.source
        assert scoped.resolver is observer.resolver
    assert market.verified_transition is main
    assert market.close_transition is not main


def test_productive_rotation_routes_only_confirmation_to_lobby_scope():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    events = _Events()
    actions = _Actions()
    observer = RuntimeObserver(
        _Source(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
    )
    main = VerifiedTransition(observer, actions, events)
    dependencies = SimpleNamespace(
        observer=observer,
        actions=actions,
        events=events,
        cancel_requested=lambda: False,
        build_verified_transition=lambda: main,
    )

    rotation = ProductiveRuntime.build_rotation(dependencies, 7)

    assert rotation.verified_transition is main
    assert rotation.confirmation_transition is not main
    assert len(rotation.confirmation_transition.observer.perception.detectors) == 77
    assert rotation.confirmation_transition.observer.source is observer.source
    assert rotation.confirmation_transition.observer.resolver is observer.resolver
