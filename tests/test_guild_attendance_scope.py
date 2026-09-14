"""Scoped perception for the Guild Attendance completion wait.

Covers only the post-tap ``wait_until(_is_attendance_completed)``: detector
subset composition, expected/abort semantics, flow routing of exactly that
wait through the scoped observer, and the registry wiring with its bounded
fallback to the main observer.

The initial ``observe()`` (precondition/no-op check) stays global on purpose.
This is the first scope created directly on the generic infrastructure
(``ScopeSpec`` + ``select_detectors`` + ``scoped_observer_for``): no legacy
builder, no custom hook.
"""

import inspect
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.flow_contracts import FlowStatus
from bot.flow_registry import (
    _build_guild_check_in,
    _guild_attendance_observer_for,
)
from bot.guild_check_in_flow import (
    GUILD_CHECK_IN_COMPLETED,
    GUILD_CHECK_IN_TAP_EXECUTED,
    GuildCheckInFlow,
    _has_incompatible_attendance_transition,
    _is_attendance_completed,
)
from bot.observations import ObservationBatch
from bot.perception import (
    GUILD_ATTENDANCE_SCOPE,
    GUILD_ATTENDANCE_SCOPE_SPEC_NAMES,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.perception.guild import GuildAttendanceDetector
from bot.perception.local_cv import LocalCvDetector
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
    _facts_from,
)
from bot.semantic_actions import CheckInGuildAttendance
from bot.state import ResolutionStatus, ResolvedState

ROOT = Path(__file__).resolve().parents[1]

# In-vocabulary frames: pending, transition and completed Guild shells. The
# quick-menu/lobby-route frames are intentionally excluded: menu.quick and
# foreign bases are outside the scope vocabulary and degrade conservatively
# to timeout (same FAILED outcome, no input) instead of fast abort.
GUILD_FRAMES = {
    "pending/01": "screencaps/semantic/guild/pending/01.png",
    "pending/02": "screencaps/semantic/guild/pending/02.png",
    "pending/03": "screencaps/semantic/guild/pending/03.png",
    "transition/pending": "screencaps/semantic/guild/transition/01-pending.png",
    "transition/onset": (
        "screencaps/semantic/guild/transition/02-completed-bubble-onset.png"
    ),
    "transition/stable": (
        "screencaps/semantic/guild/transition/03-completed-bubble-stable.png"
    ),
    "transition/settled": (
        "screencaps/semantic/guild/transition/04-completed-settled.png"
    ),
    "completed/01": "screencaps/semantic/guild/completed/01.png",
    "completed/02": "screencaps/semantic/guild/completed/02.png",
    "completed/03": "screencaps/semantic/guild/completed/03.png",
}

GUILD_OBSERVATION_NAMES = frozenset(
    {
        "landmark.guild_message_tab",
        "indicator.guild_attendance_active",
        "indicator.guild_attendance_completed",
        "indicator.guild_attendance_daily_active",
    }
)


def _scoped_engine():
    return select_detectors(build_default_perception(ROOT), GUILD_ATTENDANCE_SCOPE)


def test_scope_selects_exactly_the_three_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, GUILD_ATTENDANCE_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 3
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(GUILD_ATTENDANCE_SCOPE_SPEC_NAMES)
    assert (
        sum(
            isinstance(item, GuildAttendanceDetector)
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


def test_scope_fails_fast_on_missing_detectors():
    source = build_default_perception(ROOT)
    with pytest.raises(ValueError):
        select_detectors(PerceptionEngine(detectors=()), GUILD_ATTENDANCE_SCOPE)
    local_only = PerceptionEngine(
        detectors=tuple(
            detector
            for detector in source.detectors
            if isinstance(detector, LocalCvDetector)
            and detector.spec.name in GUILD_ATTENDANCE_SCOPE_SPEC_NAMES
        )
    )
    assert len(local_only.detectors) == 2
    with pytest.raises(ValueError):
        select_detectors(local_only, GUILD_ATTENDANCE_SCOPE)


def _snapshot(
    sequence,
    timestamp,
    *,
    status,
    base=SCREEN_GUILD,
    overlays=(),
    base_candidates=(),
):
    if status is not ResolutionStatus.RESOLVED:
        base = None
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence=sequence, timestamp=timestamp),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(base_candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def test_expected_and_abort_semantics():
    completed = _snapshot(
        1,
        1.0,
        status=ResolutionStatus.RESOLVED,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )
    assert _is_attendance_completed(completed)
    assert not _has_incompatible_attendance_transition(completed)

    active = _snapshot(
        1,
        1.0,
        status=ResolutionStatus.RESOLVED,
        overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,),
    )
    assert not _is_attendance_completed(active)
    assert not _has_incompatible_attendance_transition(active)

    contradictory = _snapshot(
        1,
        1.0,
        status=ResolutionStatus.RESOLVED,
        overlays=(
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_COMPLETED,
        ),
    )
    assert _has_incompatible_attendance_transition(contradictory)

    ambiguous = _snapshot(
        1,
        1.0,
        status=ResolutionStatus.AMBIGUOUS,
        base_candidates=(SCREEN_GUILD, SCREEN_LOBBY),
    )
    assert _has_incompatible_attendance_transition(ambiguous)
    assert not _is_attendance_completed(ambiguous)

    lobby = _snapshot(1, 1.0, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    assert _has_incompatible_attendance_transition(lobby)

    # UNKNOWN never fabricates success nor authorizes abort.
    unknown = _snapshot(1, 1.0, status=ResolutionStatus.UNKNOWN)
    assert not _is_attendance_completed(unknown)
    assert not _has_incompatible_attendance_transition(unknown)


class RecordingObserver:
    def __init__(self, initial, script=()):
        self.initial = initial
        self.script = list(script)
        self.observe_calls = 0
        self.wait_calls = []

    def observe(self):
        self.observe_calls += 1
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
        self.wait_calls.append((timeout, stable_for))
        stable_since = None
        last = None
        for item in self.script:
            last = item
            if abort_if is not None and abort_if(item):
                raise RuntimeWaitAborted(item)
            if condition(item):
                if stable_since is None:
                    stable_since = item.timestamp
                if item.timestamp - stable_since >= stable_for:
                    return item
            else:
                stable_since = None
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence, timeout=timeout, last_snapshot=last
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


def test_only_completion_wait_uses_scoped_observer():
    active = _snapshot(1, 1.0, status=ResolutionStatus.RESOLVED,
                       overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,))
    completed_a = _snapshot(2, 2.0, status=ResolutionStatus.RESOLVED,
                            overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,))
    completed_b = _snapshot(3, 2.8, status=ResolutionStatus.RESOLVED,
                            overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,))

    main = RecordingObserver(active, [])
    scoped = RecordingObserver(active, [completed_a, completed_b])
    flow = GuildCheckInFlow(
        main, Actions(), Events(), completion_observer=scoped
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.tap_executed
    assert result.event_count(GUILD_CHECK_IN_TAP_EXECUTED) == 1
    assert result.event_count(GUILD_CHECK_IN_COMPLETED) == 1
    assert main.observe_calls == 1
    assert main.wait_calls == []
    assert scoped.wait_calls == [(10.0, 0.75)]


def test_completion_observer_defaults_to_main_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, status=ResolutionStatus.UNKNOWN), []
    )
    flow = GuildCheckInFlow(observer, Actions(), Events())
    assert flow.completion_observer is observer


def test_completion_observer_rejects_non_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, status=ResolutionStatus.UNKNOWN), []
    )
    with pytest.raises(ValueError):
        GuildCheckInFlow(
            observer, Actions(), Events(), completion_observer=object()
        )


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


def test_registry_wires_scoped_observer_for_real_observer():
    events = Events()
    observer = _real_observer(events, build_default_perception(ROOT))
    deps = FakeDependencies(observer, Actions(), events)

    scoped = _guild_attendance_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 3
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert ("guild_check_in.attendance_scope_active", {"detector_count": 3}) in [
        (name, fields) for name, fields in events.items
    ]


def test_registry_falls_back_to_main_observer():
    for perception in (PerceptionEngine(detectors=()),):
        events = Events()
        main = _real_observer(events, perception)
        deps = FakeDependencies(main, Actions(), events)
        assert _guild_attendance_observer_for(deps, main) is main
        assert any(
            name == "guild_check_in.attendance_scope_unavailable"
            for name, _ in events.items
        )
    events = Events()
    main = object()
    deps = FakeDependencies(object(), Actions(), events)
    assert _guild_attendance_observer_for(deps, main) is main


def test_registry_builds_guild_check_in_with_completion_observer():
    events = Events()
    observer = _real_observer(events, build_default_perception(ROOT))
    deps = FakeDependencies(observer, Actions(), events)

    flow = _build_guild_check_in(deps)

    assert isinstance(flow, GuildCheckInFlow)
    assert flow.completion_observer is not observer
    assert len(flow.completion_observer.perception.detectors) == 3


def test_wiring_uses_generic_infra_only():
    source_text = inspect.getsource(_guild_attendance_observer_for)
    assert "scoped_observer_for(" in source_text
    for forbidden in (
        "_guild_scope_builder",
        "_guild_select_detectors",
        "_guild_scoped_transition_custom",
        "guild_attendance_perception",
    ):
        assert forbidden not in source_text


def _wrap(frame_path, engine, resolver, *, sequence):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None
    frame = FrameSnapshot(
        image=image, timestamp=float(sequence), sequence=sequence
    )
    batch = engine.analyze(frame)
    return (
        RuntimeSnapshot(
            frame=frame,
            observations=batch,
            state=resolver.resolve(batch),
            facts=_facts_from(batch),
            geometry=FrameGeometry.from_frame(image),
        ),
        batch,
    )


def _relevant_facts(batch):
    return sorted(
        (item.name, item.confidence)
        for item in batch.observations
        if item.name in GUILD_OBSERVATION_NAMES
    )


def test_scoped_matches_global_on_guild_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in GUILD_FRAMES.items():
        global_snapshot, global_batch = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, scoped_batch = _wrap(path, scoped, resolver, sequence=1)
        assert (scoped_snapshot.state.status, scoped_snapshot.state.base_context) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context,
        ), name
        assert tuple(scoped_snapshot.state.overlays) == tuple(
            global_snapshot.state.overlays
        ), name
        assert _relevant_facts(scoped_batch) == _relevant_facts(global_batch), name
        assert _is_attendance_completed(scoped_snapshot) == _is_attendance_completed(
            global_snapshot
        ), name
        assert _has_incompatible_attendance_transition(
            scoped_snapshot
        ) == _has_incompatible_attendance_transition(global_snapshot), name


def test_pending_frames_require_tap_and_completed_frames_satisfy_expected():
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in GUILD_FRAMES.items():
        snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        if name.startswith("pending") or name == "transition/pending":
            assert STATUS_GUILD_ATTENDANCE_ACTIVE in snapshot.state.overlays, name
            assert not _is_attendance_completed(snapshot), name
        else:
            assert _is_attendance_completed(snapshot), name
        assert not _has_incompatible_attendance_transition(snapshot), name
