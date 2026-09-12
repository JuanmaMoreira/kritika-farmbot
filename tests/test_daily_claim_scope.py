"""Experimental claim-scoped perception for the Daily Quests ``ClaimAll`` wait.

Covers only the ClaimAll claim+settle wait: detector subset composition,
resolution equivalence against the global engine on curated Daily frames,
flow routing of exactly that wait through the scoped observer, the
``RuntimeObserver.scoped`` seam and the registry wiring with its bounded
fallback to the main observer.

The independent progress-reward wait is intentionally out of scope.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MODE_DAILY_QUESTS,
    SCREEN_LOBBY,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
    STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    build_default_resolver,
)
from bot.daily_quests_flow import DailyQuestsFlow
from bot.flow_contracts import FlowStatus
from bot.flow_registry import _build_daily_quests, _daily_claim_observer_for
from bot.observations import ObservationBatch
from bot.perception import (
    DAILY_CLAIM_SCOPE_SPEC_NAMES,
    build_default_perception,
    daily_claim_perception,
)
from bot.perception.daily_quests import DailyQuestsProgressRewardDetector
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
    _facts_from,
)
from bot.semantic_actions import (
    ClaimAllDailyQuests,
    CloseDailyQuests,
    OpenQuests,
)
from bot.state import ResolutionStatus, ResolvedState

ROOT = Path(__file__).resolve().parents[1]

CLAIM_FRAMES = {
    "claimable/01": (
        "screencaps/semantic/daily-quests-mailbox/daily-claimable/01.png"
    ),
    "claimable/02": (
        "screencaps/semantic/daily-quests-mailbox/daily-claimable/02.png"
    ),
    "claimable/03": (
        "screencaps/semantic/daily-quests-mailbox/daily-claimable/03.png"
    ),
    "settled/01": (
        "screencaps/semantic/daily-quests-mailbox/daily-settled/01.png"
    ),
    "settled/02": (
        "screencaps/semantic/daily-quests-mailbox/daily-settled/02.png"
    ),
    "settled/noop": (
        "screencaps/semantic/daily-quests-mailbox/daily-settled/03-noop.png"
    ),
    "progress/01": (
        "screencaps/semantic/daily-quests-mailbox/daily-progress-claim/01.png"
    ),
    "progress/02": (
        "screencaps/semantic/daily-quests-mailbox/daily-progress-claim/02.png"
    ),
    "progress/03": (
        "screencaps/semantic/daily-quests-mailbox/daily-progress-claim/03.png"
    ),
    "claimed/01": (
        "screencaps/semantic/daily-quests-mailbox/daily-progress-claimed/01.png"
    ),
    "claimed/02": (
        "screencaps/semantic/daily-quests-mailbox/daily-progress-claimed/02.png"
    ),
    "claimed/03": (
        "screencaps/semantic/daily-quests-mailbox/daily-progress-claimed/03.png"
    ),
}

LOBBY_FRAMES = {
    "lobby/before": (
        "screencaps/semantic/daily-quests-mailbox/lobby/before-daily.png"
    ),
    "lobby/after": (
        "screencaps/semantic/daily-quests-mailbox/lobby/after-mailbox.png"
    ),
}

DAILY_OBSERVATION_NAMES = frozenset(
    {
        "landmark.daily_quests_title",
        "landmark.daily_quests_tab_active",
        "landmark.daily_quests_row_claim_button",
        "indicator.daily_quests_progress_reward_claimable",
    }
)


def _scoped_engine():
    return daily_claim_perception(build_default_perception(ROOT))


def test_claim_scope_selects_exactly_the_four_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = daily_claim_perception(source)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 4
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(DAILY_CLAIM_SCOPE_SPEC_NAMES)
    assert (
        sum(
            isinstance(item, DailyQuestsProgressRewardDetector)
            for item in scoped.detectors
        )
        == 1
    )
    # Same instances in source order: calibration and assets are unchanged.
    expected_order = tuple(
        detector
        for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_claim_scope_rejects_non_engine_source():
    with pytest.raises(ValueError):
        daily_claim_perception(object())


def test_claim_scope_fails_fast_when_a_detector_is_missing():
    with pytest.raises(ValueError):
        daily_claim_perception(PerceptionEngine(detectors=()))


def test_claim_scope_fails_fast_without_progress_reward_detector():
    source = build_default_perception(ROOT)
    local_only = PerceptionEngine(
        detectors=tuple(
            detector
            for detector in source.detectors
            if isinstance(detector, LocalCvDetector)
            and detector.spec.name in DAILY_CLAIM_SCOPE_SPEC_NAMES
        )
    )
    assert len(local_only.detectors) == 3
    with pytest.raises(ValueError):
        daily_claim_perception(local_only)


def _resolve(frame_path, engine, resolver):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None
    snapshot = FrameSnapshot(image=image, timestamp=1.0, sequence=1)
    batch = engine.analyze(snapshot)
    return resolver.resolve(batch), batch


def test_scoped_resolution_matches_global_on_claim_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        global_state, _ = _resolve(path, full, resolver)
        scoped_state, _ = _resolve(path, scoped, resolver)
        assert (scoped_state.status, scoped_state.base_context) == (
            global_state.status,
            global_state.base_context,
        ), name
        assert tuple(scoped_state.overlays) == tuple(
            global_state.overlays
        ), name


def test_scoped_daily_observations_match_global_on_claim_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        _, global_batch = _resolve(path, full, resolver)
        _, scoped_batch = _resolve(path, scoped, resolver)
        assert _daily_facts(scoped_batch) == _daily_facts(global_batch), name


def _daily_facts(batch):
    return sorted(
        (item.name, item.confidence)
        for item in batch.observations
        if item.name in DAILY_OBSERVATION_NAMES
    )


def test_specialized_indicator_participates_inside_the_scope():
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    _, progress_batch = _resolve(
        CLAIM_FRAMES["progress/01"], scoped, resolver
    )
    _, claimed_batch = _resolve(CLAIM_FRAMES["claimed/01"], scoped, resolver)
    progress_names = {item.name for item in progress_batch.observations}
    claimed_names = {item.name for item in claimed_batch.observations}
    assert (
        "indicator.daily_quests_progress_reward_claimable" in progress_names
    )
    assert (
        "indicator.daily_quests_progress_reward_claimable"
        not in claimed_names
    )


def _wrap(frame_path, engine, resolver, *, sequence):
    image = cv2.imread(str(ROOT / frame_path))
    frame = FrameSnapshot(
        image=image, timestamp=float(sequence), sequence=sequence
    )
    batch = engine.analyze(frame)
    return RuntimeSnapshot(
        frame=frame,
        observations=batch,
        state=resolver.resolve(batch),
        facts=_facts_from(batch),
        geometry=FrameGeometry.from_frame(image),
    )


def test_scoped_predicates_agree_with_global_on_claim_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert DailyQuestsFlow._is_daily_quests_settled(
            scoped_snapshot
        ) == DailyQuestsFlow._is_daily_quests_settled(global_snapshot), name
        assert DailyQuestsFlow._is_daily_quests_fully_settled(
            scoped_snapshot
        ) == DailyQuestsFlow._is_daily_quests_fully_settled(
            global_snapshot
        ), name
        assert DailyQuestsFlow._has_incompatible_daily_state(
            scoped_snapshot
        ) == DailyQuestsFlow._has_incompatible_daily_state(
            global_snapshot
        ), name


def test_claimable_frames_require_claim_and_settled_frames_satisfy_it():
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        snapshot = _wrap(path, scoped, resolver, sequence=1)
        if name.startswith("claimable"):
            assert (
                STATUS_DAILY_QUESTS_CLAIMABLE in snapshot.state.overlays
            ), name
            assert not DailyQuestsFlow._is_daily_quests_settled(
                snapshot
            ), name
        else:
            assert DailyQuestsFlow._is_daily_quests_settled(snapshot), name


def _synthetic_snapshot(*, status, base=None, overlays=()):
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    batch = ObservationBatch(sequence=1, timestamp=1.0)
    return RuntimeSnapshot(
        FrameSnapshot(image, 1.0, 1),
        batch,
        ResolvedState(status, 1, 1.0, base, tuple(overlays)),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def test_unknown_frame_never_fabricates_claim_success():
    snapshot = _synthetic_snapshot(
        status=ResolutionStatus.UNKNOWN, base=None, overlays=()
    )
    assert not DailyQuestsFlow._is_daily_quests_settled(snapshot)
    assert not DailyQuestsFlow._is_daily_quests_fully_settled(snapshot)


def test_foreign_screen_divergence_stays_bounded_without_input():
    """A Lobby screen resolves UNKNOWN under the scope.

    Global perception would abort fast (RESOLVED lobby); the scope keeps
    waiting instead. Both paths stay bounded, authorize no input and fail
    the flow the same way, so no fallback machinery is warranted.
    """

    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in LOBBY_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert global_snapshot.state.base_context == SCREEN_LOBBY, name
        assert scoped_snapshot.state.status is ResolutionStatus.UNKNOWN, name
        assert not DailyQuestsFlow._is_daily_quests_settled(
            scoped_snapshot
        ), name
        assert not DailyQuestsFlow._has_incompatible_daily_state(
            scoped_snapshot
        ), name


class RecordingObserver:
    def __init__(self, initial, scripts):
        self.initial = initial
        self.scripts = list(scripts)
        self.calls = []
        self._initial_returned = False

    def observe(self):
        if not self._initial_returned:
            self._initial_returned = True
            return self.initial
        return self.initial

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        cancel_requested=None,
        stable_for=0.0,
    ):
        self.calls.append((timeout, stable_for))
        script = self.scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        stable_since = None
        last = None
        for snapshot in script:
            last = snapshot
            assert snapshot.sequence > after_sequence
            if cancel_requested is not None and cancel_requested():
                from bot.runtime_observer import RuntimeWaitCancelled

                raise RuntimeWaitCancelled("cancelled")
            if abort_if is not None and abort_if(snapshot):
                raise RuntimeWaitAborted(snapshot)
            if condition(snapshot):
                if stable_since is None:
                    stable_since = snapshot.timestamp
                if snapshot.timestamp - stable_since >= stable_for:
                    return snapshot
            else:
                stable_since = None
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence,
            timeout=timeout,
            last_snapshot=last,
        )


class Actions:
    def __init__(self):
        self.items = []

    def execute(self, action, geometry):
        self.items.append(action)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


def _snapshot(sequence, timestamp, *, base, overlays=()):
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp),
        ResolvedState(
            ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN,
            sequence,
            timestamp,
            base,
            tuple(overlays),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def test_claim_wait_routes_through_claim_observer_only():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_a = _snapshot(
        2,
        2.0,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE),
    )
    open_b = _snapshot(
        3,
        2.3,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE),
    )
    settled_a = _snapshot(
        4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,)
    )
    settled_b = _snapshot(
        5, 3.6, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,)
    )
    closed_a = _snapshot(6, 4.0, base=SCREEN_LOBBY)
    closed_b = _snapshot(7, 4.3, base=SCREEN_LOBBY)

    main = RecordingObserver(lobby, [[open_a, open_b], [closed_a, closed_b]])
    claim = RecordingObserver(lobby, [[settled_a, settled_b]])
    flow = DailyQuestsFlow(
        main, Actions(), Events(), claim_observer=claim
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.claim_all_executed and result.claim_all_completed
    assert not result.progress_reward_executed
    assert flow.actions.items == [
        OpenQuests(),
        ClaimAllDailyQuests(),
        CloseDailyQuests(),
    ]
    # Same contract as the global wait: one shot, 8 s timeout, 0.5 s settle.
    assert claim.calls == [(8.0, 0.5)]
    assert main.calls == [(6.0, 0.25), (6.0, 0.25)]


def test_claim_wait_abort_fails_bounded_without_further_input():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_a = _snapshot(
        2,
        2.0,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE),
    )
    open_b = _snapshot(
        3,
        2.3,
        base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE),
    )
    incompatible = _snapshot(4, 3.0, base=SCREEN_LOBBY)

    main = RecordingObserver(lobby, [[open_a, open_b]])
    claim = RecordingObserver(lobby, [[incompatible]])
    actions = Actions()
    flow = DailyQuestsFlow(main, actions, Events(), claim_observer=claim)
    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert actions.items == [OpenQuests(), ClaimAllDailyQuests()]
    assert claim.calls == [(8.0, 0.5)]


def test_claim_observer_defaults_to_main_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, base=SCREEN_LOBBY), []
    )
    flow = DailyQuestsFlow(observer, Actions(), Events())
    assert flow.claim_observer is observer


def test_claim_observer_rejects_non_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, base=SCREEN_LOBBY), []
    )
    with pytest.raises(ValueError):
        DailyQuestsFlow(observer, Actions(), Events(), claim_observer=object())


class FakeSource:
    def __init__(self, frame):
        self.frame = frame

    def get_frame(self):
        return self.frame


class FakeDependencies:
    def __init__(self, observer, actions, events):
        self.observer = observer
        self.actions = actions
        self.events = events
        self.cancel_requested = lambda: False


def test_registry_falls_back_to_main_without_scoped_observer():
    main = object()
    deps = FakeDependencies(object(), Actions(), Events())
    assert _daily_claim_observer_for(deps, main) is main


def test_registry_wires_scoped_observer_for_real_observer():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    events = Events()
    observer = RuntimeObserver(
        FakeSource(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
    )
    deps = FakeDependencies(observer, Actions(), events)

    scoped = _daily_claim_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 4
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert ("daily_quests.claim_scope_active", {"detector_count": 4}) in [
        (name, fields) for name, fields in events.items
    ]


def test_registry_falls_back_when_scope_detectors_are_missing():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    events = Events()
    observer = RuntimeObserver(
        FakeSource(frame),
        PerceptionEngine(detectors=()),
        build_default_resolver(),
        events=events,
    )
    deps = FakeDependencies(observer, Actions(), events)

    assert _daily_claim_observer_for(deps, observer) is observer
    assert any(
        name == "daily_quests.claim_scope_unavailable"
        for name, _ in events.items
    )


def test_registry_builds_daily_quests_with_claim_observer():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    events = Events()
    observer = RuntimeObserver(
        FakeSource(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
    )
    deps = FakeDependencies(observer, Actions(), events)

    flow = _build_daily_quests(deps)

    assert isinstance(flow, DailyQuestsFlow)
    assert flow.claim_observer is not observer
    assert len(flow.claim_observer.perception.detectors) == 4
