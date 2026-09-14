"""Scoped perception for the Send Stamina completion waits.

Covers only the two post-tap ``wait_until`` calls (completion + daily-active
fallback, Caso A: they share one coherent detector set and one abort
predicate): detector subset composition, expected/abort semantics, flow
routing of exactly those waits through the scoped observer, and the registry
wiring with its bounded fallback to the main observer.

The initial ``observe()`` (precondition/no-op check), close and
Lobby latency stay global on purpose. Batch B1 additionally routes the
``OpenFriends`` navigation wait through the same scope: its vocabulary
is exactly the completion scope, so no new scope was needed. This is the second scope created
directly on the generic infrastructure (``ScopeSpec`` + ``select_detectors``
+ ``scoped_observer_for``): no legacy builder, no custom hook.
"""

import inspect
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_FRIENDS,
    SCREEN_LOBBY,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.flow_contracts import FlowStatus
from bot.flow_registry import (
    _build_send_stamina,
    _send_stamina_completion_observer_for,
)
from bot.send_stamina_flow import (
    SEND_STAMINA_ALL_EXECUTED,
    SEND_STAMINA_COMPLETED,
    SendStaminaFlow,
    _has_incompatible_daily_transition,
    _is_daily_active,
    _is_daily_completed,
)
from bot.perception import (
    SEND_STAMINA_COMPLETION_SCOPE,
    SEND_STAMINA_COMPLETION_SCOPE_SPEC_NAMES,
    build_default_perception,
    select_detectors,
)
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
from bot.state import ResolutionStatus, ResolvedState
from bot.observations import ObservationBatch

ROOT = Path(__file__).resolve().parents[1]

# In-vocabulary frames: actionable, completed and transient Friends shells.
# The close-lobby frame is intentionally listed separately: Lobby is outside
# the scope vocabulary and degrades conservatively to timeout (same FAILED
# outcome, no input) instead of fast abort.
SEND_STAMINA_FRAMES = {
    "daily-active/01": "screencaps/semantic/daily_activity/friends/daily-active/01.png",
    "daily-active/02": "screencaps/semantic/daily_activity/friends/daily-active/02.png",
    "daily-active/03": "screencaps/semantic/daily_activity/friends/daily-active/03.png",
    "daily-inactive/01": "screencaps/semantic/daily_activity/friends/daily-inactive/01.png",
    "daily-inactive/02": "screencaps/semantic/daily_activity/friends/daily-inactive/02.png",
    "daily-inactive/03": "screencaps/semantic/daily_activity/friends/daily-inactive/03.png",
    "transition/last-active": "screencaps/semantic/daily_activity/friends/transition/01-last-active.png",
    "transition/first-inactive": "screencaps/semantic/daily_activity/friends/transition/02-first-inactive.png",
    "transition/inactive-stable": "screencaps/semantic/daily_activity/friends/transition/03-inactive-stable.png",
}

SEND_STAMINA_OBSERVATION_NAMES = frozenset(
    {
        "landmark.friends_title",
        "landmark.friends_all_button",
        "indicator.friends_send_stamina_daily_active",
    }
)


def _scoped_engine():
    return select_detectors(
        build_default_perception(ROOT), SEND_STAMINA_COMPLETION_SCOPE
    )


def test_scope_selects_exactly_the_three_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, SEND_STAMINA_COMPLETION_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 3
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(SEND_STAMINA_COMPLETION_SCOPE_SPEC_NAMES)
    assert SEND_STAMINA_COMPLETION_SCOPE.specialized_types == ()
    # Same instances in source order: calibration and assets are unchanged.
    expected_order = tuple(
        detector
        for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_scope_fails_fast_on_missing_detectors():
    with pytest.raises(ValueError):
        select_detectors(
            PerceptionEngine(detectors=()), SEND_STAMINA_COMPLETION_SCOPE
        )


def _snapshot(
    sequence,
    timestamp,
    *,
    status,
    base=SCREEN_FRIENDS,
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
    completed = _snapshot(1, 1.0, status=ResolutionStatus.RESOLVED, overlays=())
    assert _is_daily_completed(completed)
    assert not _is_daily_active(completed)
    assert not _has_incompatible_daily_transition(completed)

    active = _snapshot(
        1,
        1.0,
        status=ResolutionStatus.RESOLVED,
        overlays=(STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,),
    )
    assert _is_daily_active(active)
    assert not _is_daily_completed(active)
    assert not _has_incompatible_daily_transition(active)

    ambiguous = _snapshot(
        1,
        1.0,
        status=ResolutionStatus.AMBIGUOUS,
        base_candidates=(SCREEN_FRIENDS, SCREEN_LOBBY),
    )
    assert _has_incompatible_daily_transition(ambiguous)
    assert not _is_daily_completed(ambiguous)
    assert not _is_daily_active(ambiguous)

    lobby = _snapshot(1, 1.0, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    assert _has_incompatible_daily_transition(lobby)

    # UNKNOWN never fabricates success nor authorizes abort/input.
    unknown = _snapshot(1, 1.0, status=ResolutionStatus.UNKNOWN)
    assert not _is_daily_completed(unknown)
    assert not _is_daily_active(unknown)
    assert not _has_incompatible_daily_transition(unknown)


def test_carry_none_final_snapshot_feeds_no_semantic_decision():
    # The post-completion snapshot only supplies geometry for CloseFriends;
    # the daily branch is already encoded in the flow flags. Documented as
    # carry: none (same precedent as Guild).
    source = inspect.getsource(SendStaminaFlow._run)
    assert "completion_observer.wait_until" in source
    # Close still waits on the main observer, not the scoped one.
    assert source.count("completion_observer.wait_until") == 2


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
        self.wait_calls.append((after_sequence, timeout, stable_for))
        script = self.script.pop(0)
        if isinstance(script, BaseException):
            raise script
        stable_since = None
        last = None
        for item in script:
            if isinstance(item, BaseException):
                raise item
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


def _friends(sequence, timestamp, *, daily_active):
    from bot.send_stamina_flow import _FRIENDS_STATES  # noqa: F401 (contract anchor)

    overlays = (
        (STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,) if daily_active else ()
    )
    return _snapshot(
        sequence, timestamp, status=ResolutionStatus.RESOLVED, overlays=overlays
    )


def test_only_completion_waits_use_scoped_observer():
    lobby = _snapshot(1, 1.0, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    opened_a = _friends(2, 2.0, daily_active=True)
    opened_b = _friends(3, 2.3, daily_active=True)
    settled_a = _friends(4, 2.9, daily_active=False)
    settled_b = _friends(5, 3.7, daily_active=False)
    returned_a = _snapshot(
        6, 4.0, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY
    )
    returned_b = _snapshot(
        7, 4.3, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY
    )

    # Batch B1: the flow routes open + completion through the injected
    # observer and only close through main: open (scoped) -> completion
    # (scoped) -> close (main). The open vocabulary is exactly the
    # completion scope, so no new scope was needed.
    main = RecordingObserver(lobby, [[returned_a, returned_b]])
    scoped = RecordingObserver(lobby, [[opened_a, opened_b], [settled_a, settled_b]])

    flow = SendStaminaFlow(main, Actions(), Events(), completion_observer=scoped)
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.all_executed and result.daily_completed
    assert result.event_count(SEND_STAMINA_ALL_EXECUTED) == 1
    assert result.event_count(SEND_STAMINA_COMPLETED) == 1
    assert main.observe_calls == 1
    assert main.wait_calls == [(5, 6.0, 0.25)]
    assert scoped.observe_calls == 0
    assert scoped.wait_calls == [(1, 6.0, 0.25), (3, 3.0, 0.75)]


def test_both_completion_waits_share_the_same_scoped_observer():
    lobby = _snapshot(1, 1.0, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY)
    opened_a = _friends(2, 2.0, daily_active=True)
    opened_b = _friends(3, 2.3, daily_active=True)
    still_active = _friends(4, 4.0, daily_active=True)
    confirmed_a = _friends(5, 4.2, daily_active=True)
    confirmed_b = _friends(6, 5.0, daily_active=True)
    returned_a = _snapshot(
        7, 5.5, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY
    )
    returned_b = _snapshot(
        8, 5.8, status=ResolutionStatus.RESOLVED, base=SCREEN_LOBBY
    )

    main = RecordingObserver(lobby, [[returned_a, returned_b]])
    scoped = RecordingObserver(
        lobby,
        [
            [opened_a, opened_b],
            RuntimeWaitTimeout(
                after_sequence=3, timeout=3.0, last_snapshot=still_active
            ),
            [confirmed_a, confirmed_b],
        ],
    )

    flow = SendStaminaFlow(main, Actions(), Events(), completion_observer=scoped)
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.daily_pending and result.all_no_effect
    # Open plus both completion waits (initial + fallback) ran on the same
    # observer; only the Lobby close stayed global.
    assert main.observe_calls == 1
    assert main.wait_calls == [(6, 6.0, 0.25)]
    assert scoped.observe_calls == 0
    assert scoped.wait_calls == [(1, 6.0, 0.25), (3, 3.0, 0.75), (4, 3.0, 0.75)]


def test_completion_observer_defaults_to_main_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, status=ResolutionStatus.UNKNOWN), []
    )
    flow = SendStaminaFlow(observer, Actions(), Events())
    assert flow.completion_observer is observer


def test_completion_observer_rejects_non_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, status=ResolutionStatus.UNKNOWN), []
    )
    with pytest.raises(ValueError):
        SendStaminaFlow(
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

    scoped = _send_stamina_completion_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 3
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert (
        "send_stamina.completion_scope_active",
        {"detector_count": 3},
    ) in [(name, fields) for name, fields in events.items]


def test_registry_falls_back_to_main_observer():
    events = Events()
    main = _real_observer(events, PerceptionEngine(detectors=()))
    deps = FakeDependencies(main, Actions(), events)
    assert _send_stamina_completion_observer_for(deps, main) is main
    assert any(
        name == "send_stamina.completion_scope_unavailable"
        for name, _ in events.items
    )
    main_obj = object()
    deps = FakeDependencies(object(), Actions(), Events())
    assert _send_stamina_completion_observer_for(deps, main_obj) is main_obj


def test_registry_builds_send_stamina_with_completion_observer():
    events = Events()
    observer = _real_observer(events, build_default_perception(ROOT))
    deps = FakeDependencies(observer, Actions(), events)

    flow = _build_send_stamina(deps)

    assert isinstance(flow, SendStaminaFlow)
    assert flow.completion_observer is not observer
    assert len(flow.completion_observer.perception.detectors) == 3


def test_wiring_uses_generic_infra_only():
    source_text = inspect.getsource(_send_stamina_completion_observer_for)
    assert "scoped_observer_for(" in source_text
    for forbidden in (
        "_send_stamina_scope_builder",
        "_send_stamina_select_detectors",
        "_send_stamina_scoped_transition_custom",
        "send_stamina_perception",
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
        if item.name in SEND_STAMINA_OBSERVATION_NAMES
    )


def test_scoped_matches_global_on_send_stamina_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in SEND_STAMINA_FRAMES.items():
        global_snapshot, global_batch = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, scoped_batch = _wrap(path, scoped, resolver, sequence=1)
        assert (
            scoped_snapshot.state.status,
            scoped_snapshot.state.base_context,
        ) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context,
        ), name
        assert tuple(scoped_snapshot.state.overlays) == tuple(
            global_snapshot.state.overlays
        ), name
        assert _relevant_facts(scoped_batch) == _relevant_facts(global_batch), name
        assert _is_daily_completed(scoped_snapshot) == _is_daily_completed(
            global_snapshot
        ), name
        assert _is_daily_active(scoped_snapshot) == _is_daily_active(
            global_snapshot
        ), name
        assert _has_incompatible_daily_transition(
            scoped_snapshot
        ) == _has_incompatible_daily_transition(global_snapshot), name


def test_active_frames_require_action_and_inactive_frames_satisfy_expected():
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in SEND_STAMINA_FRAMES.items():
        snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        if "daily-active" in name or name == "transition/last-active":
            assert (
                STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE
                in snapshot.state.overlays
            ), name
            assert not _is_daily_completed(snapshot), name
        else:
            assert _is_daily_completed(snapshot), name
        assert not _has_incompatible_daily_transition(snapshot), name
