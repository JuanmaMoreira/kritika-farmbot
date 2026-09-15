"""Daily Quests content readiness: rows/loading detectors, READY gate, OpenQuests re-scope.

The Batch B1 false noop came from satisfying the ``OpenQuests`` wait on
panel chrome before the mission list populated. The open wait now requires
content readiness (Quests chrome plus rows-populated without the loading
ring) while ``ClaimAll`` keeps its untouched scoped wait.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_DAILY_QUESTS_LOADING,
    INDICATOR_DAILY_QUESTS_ROWS_POPULATED,
    MODE_DAILY_QUESTS,
    SCREEN_LOBBY,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
    STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE,
    build_default_resolver,
)
from bot.daily_quests_flow import DailyQuestsFlow
from bot.flow_contracts import FlowStatus
from bot.flow_registry import (
    _build_daily_quests,
    _daily_open_observer_for,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.perception import (
    DAILY_OPEN_SCOPE,
    DAILY_OPEN_SCOPE_SPEC_NAMES,
    DailyQuestsProgressRewardDetector,
    build_default_perception,
    select_detectors,
)
from bot.perception.daily_quests import (
    DailyQuestsLoadingDetector,
    DailyQuestsRowsDetector,
)
from bot.perception.engine import PerceptionEngine
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
    ClaimDailyQuestsProgressReward,
    CloseDailyQuests,
    OpenQuests,
)
from bot.state import ResolutionStatus, ResolvedState
from tools.incremental_perception_evaluation import (
    evaluate_detector_frame_pairs,
)
from tools.semantic_slice_evaluation import load_manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/daily_quests_readiness_manifest.json"
_LOCAL_TMP = Path("C:/Users/Draken/AppData/Local/Temp/opencode")

READINESS_FRAMES = {
    "loading/a": "screencaps/semantic/daily-quests-readiness/rows-loading/phase-a.png",
    "loading/b": "screencaps/semantic/daily-quests-readiness/rows-loading/phase-b.png",
    "loading/c": "screencaps/semantic/daily-quests-readiness/rows-loading/phase-c.png",
    "loading/d": "screencaps/semantic/daily-quests-readiness/rows-loading/phase-d.png",
    "clear": "screencaps/semantic/daily-quests-readiness/rows-clear/clear-0016.png",
    "ready/first": "screencaps/semantic/daily-quests-readiness/rows-ready/first-ready-0017.png",
    "ready/mid": "screencaps/semantic/daily-quests-readiness/rows-ready/mid-ready-0060.png",
    "ready/settled": "screencaps/semantic/daily-quests-readiness/rows-ready/settled-ready-0109.png",
    "warm/first": "screencaps/semantic/daily-quests-readiness/rows-warm/warm-first-0001.png",
    "warm/mid": "screencaps/semantic/daily-quests-readiness/rows-warm/warm-mid-0032.png",
    "warm/last": "screencaps/semantic/daily-quests-readiness/rows-warm/warm-last-0064.png",
}

MAILBOX_CORPUS_FRAMES = {
    "claimable": "screencaps/semantic/daily-quests-mailbox/daily-claimable/01.png",
    "settled": "screencaps/semantic/daily-quests-mailbox/daily-settled/01.png",
    "noop": "screencaps/semantic/daily-quests-mailbox/daily-settled/03-noop.png",
    "progress": "screencaps/semantic/daily-quests-mailbox/daily-progress-claim/01.png",
    "claimed": "screencaps/semantic/daily-quests-mailbox/daily-progress-claimed/01.png",
    "lobby/before": "screencaps/semantic/daily-quests-mailbox/lobby/before-daily.png",
    "lobby/after": "screencaps/semantic/daily-quests-mailbox/lobby/after-mailbox.png",
}

def _read(path):
    image = cv2.imread(str(ROOT / path))
    assert image is not None, path
    return image


def _detect(detector, path):
    return {item.name for item in detector.detect(_read(path))}


def test_rows_detector_fires_on_every_populated_frame():
    detector = DailyQuestsRowsDetector(asset_root=ROOT)
    populated = [
        name
        for name in READINESS_FRAMES
        if not name.startswith("clear")
    ] + ["claimable", "settled", "noop", "progress", "claimed"]
    paths = {
        **READINESS_FRAMES,
        **{key: MAILBOX_CORPUS_FRAMES[key] for key in (
            "claimable", "settled", "noop", "progress", "claimed"
        )},
    }
    for name in populated:
        assert INDICATOR_DAILY_QUESTS_ROWS_POPULATED in _detect(
            detector, paths[name]
        ), name


def test_rows_detector_silent_on_clear_and_lobby():
    detector = DailyQuestsRowsDetector(asset_root=ROOT)
    assert _detect(detector, READINESS_FRAMES["clear"]) == set()
    # The Lobby sea is bright inside the rows ROI; the Daily chrome gate
    # inside the detector must suppress it. Rows never identify a screen.
    for name in ("lobby/before", "lobby/after"):
        assert _detect(detector, MAILBOX_CORPUS_FRAMES[name]) == set(), name


def test_loading_detector_fires_on_every_acquired_phase():
    detector = DailyQuestsLoadingDetector(asset_root=ROOT)
    for name in ("loading/a", "loading/b", "loading/c", "loading/d"):
        assert ACTIVITY_DAILY_QUESTS_LOADING in _detect(
            detector, READINESS_FRAMES[name]
        ), name


def test_loading_detector_silent_on_clear_ready_warm_and_corpus():
    detector = DailyQuestsLoadingDetector(asset_root=ROOT)
    negatives = [
        name
        for name in READINESS_FRAMES
        if not name.startswith("loading/")
    ] + list(MAILBOX_CORPUS_FRAMES)
    paths = {**READINESS_FRAMES, **MAILBOX_CORPUS_FRAMES}
    for name in negatives:
        assert _detect(detector, paths[name]) == set(), name


def test_manifest_entries_resolve_with_confirmed_readiness_labels():
    entries = {entry.path: entry for entry in load_manifest(MANIFEST)}
    assert len(entries) == len(READINESS_FRAMES)
    engine = build_default_perception(ROOT)
    resolver = build_default_resolver()
    for name, path in READINESS_FRAMES.items():
        entry = entries[path]
        batch = engine.analyze(
            FrameSnapshot(_read(path), timestamp=1.0, sequence=1)
        )
        state = resolver.resolve(
            ObservationBatch(1, 1.0, batch.observations)
        )
        assert state.status is ResolutionStatus.RESOLVED, name
        assert state.base_context == entry.base_context, name
        assert state.overlays == entry.overlays, name
        detected = {item.name for item in batch.observations}
        assert set(entry.observations) <= detected, name


def _obs(*names):
    return ObservationBatch(
        sequence=1,
        timestamp=1.0,
        observations=tuple(
            Observation(name, 0.95, ObservationSource.LOCAL_CV)
            for name in names
        ),
    )


def _snapshot(sequence, timestamp, *, base, overlays=(), observations=()):
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    batch = (
        observations
        if isinstance(observations, ObservationBatch)
        else ObservationBatch(sequence, timestamp, tuple(observations))
    )
    status = (
        ResolutionStatus.RESOLVED
        if base is not None
        else ResolutionStatus.UNKNOWN
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        batch,
        ResolvedState(status, sequence, timestamp, base, tuple(overlays)),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _quests(overlays=(), observations=()):
    return _snapshot(
        2, 2.0, base=SCREEN_QUESTS, overlays=overlays, observations=observations
    )


def _rows():
    return (
        Observation(
            INDICATOR_DAILY_QUESTS_ROWS_POPULATED,
            0.95,
            ObservationSource.LOCAL_CV,
        ),
    )


def _loading():
    return (
        Observation(
            ACTIVITY_DAILY_QUESTS_LOADING, 0.95, ObservationSource.LOCAL_CV
        ),
    )


def test_content_ready_matrix():
    ready = _quests(
        overlays=(MODE_DAILY_QUESTS,), observations=_rows()
    )
    assert DailyQuestsFlow._is_content_ready(ready)

    rows_loading = _quests(
        overlays=(MODE_DAILY_QUESTS,),
        observations=(*_rows(), *_loading()),
    )
    assert not DailyQuestsFlow._is_content_ready(rows_loading)

    clear = _quests(overlays=(MODE_DAILY_QUESTS,))
    assert not DailyQuestsFlow._is_content_ready(clear)

    # Black list with a loading ring is a unit-level combination only: no
    # acquired frame shows it, and rows=0 already withholds readiness.
    clear_loading = _quests(
        overlays=(MODE_DAILY_QUESTS,), observations=_loading()
    )
    assert not DailyQuestsFlow._is_content_ready(clear_loading)

    lobby_rows = _snapshot(
        2, 2.0, base=SCREEN_LOBBY, observations=_rows()
    )
    assert not DailyQuestsFlow._is_content_ready(lobby_rows)

    unknown = _snapshot(2, 2.0, base=None)
    assert not DailyQuestsFlow._is_content_ready(unknown)

    foreign = _snapshot(2, 2.0, base="screen.friends")
    assert not DailyQuestsFlow._is_content_ready(foreign)


class RecordingObserver:
    def __init__(self, initial, scripts, observe_sequence=None):
        self.initial = initial
        self.scripts = list(scripts)
        self.observe_sequence = list(observe_sequence or [])
        self.wait_calls = []
        self._initial_returned = False

    def observe(self):
        if not self._initial_returned:
            self._initial_returned = True
            return self.initial
        if self.observe_sequence:
            return self.observe_sequence.pop(0)
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


def _ready(sequence, timestamp, *, claimable=True, progress=False):
    overlays = [MODE_DAILY_QUESTS]
    if claimable:
        overlays.append(STATUS_DAILY_QUESTS_CLAIMABLE)
    if progress:
        overlays.append(STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE)
    return _snapshot(
        sequence, timestamp, base=SCREEN_QUESTS, overlays=overlays,
        observations=_rows(),
    )


def _not_ready(sequence, timestamp, *, loading=True):
    observations = (*_rows(), *_loading()) if loading else ()
    return _snapshot(
        sequence, timestamp, base=SCREEN_QUESTS,
        overlays=(MODE_DAILY_QUESTS,), observations=observations,
    )


def test_open_wait_blocks_loading_then_claims_on_ready_carry():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_script = [
        _not_ready(2, 2.0, loading=False),
        _not_ready(3, 2.1, loading=True),
        _ready(4, 2.5),
        _ready(5, 2.8),
    ]
    settled = [
        _snapshot(6, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
                  observations=_rows()),
        _snapshot(7, 3.6, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
                  observations=_rows()),
    ]
    closed = [
        _snapshot(8, 4.0, base=SCREEN_LOBBY),
        _snapshot(9, 4.3, base=SCREEN_LOBBY),
    ]
    main = RecordingObserver(lobby, [closed])
    open_observer = RecordingObserver(lobby, [open_script])
    claim_observer = RecordingObserver(lobby, [settled])
    actions = Actions()
    flow = DailyQuestsFlow(
        main, actions, Events(), claim_observer=claim_observer,
        open_observer=open_observer,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.claim_all_executed and result.claim_all_completed
    assert not result.progress_reward_executed
    assert actions.items == [
        OpenQuests(), ClaimAllDailyQuests(), CloseDailyQuests(),
    ]
    assert open_observer.wait_calls == [(6.0, 0.25)]
    assert claim_observer.wait_calls == [(8.0, 0.5)]
    assert main.wait_calls == [(6.0, 0.25)]


def test_ready_without_claimable_is_a_legitimate_noop():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_script = [_ready(2, 2.0, claimable=False), _ready(3, 2.4, claimable=False)]
    closed = [
        _snapshot(4, 3.0, base=SCREEN_LOBBY),
        _snapshot(5, 3.3, base=SCREEN_LOBBY),
    ]
    main = RecordingObserver(lobby, [closed])
    open_observer = RecordingObserver(lobby, [open_script])
    claim_observer = RecordingObserver(lobby, [])
    actions = Actions()
    flow = DailyQuestsFlow(
        main, actions, Events(), claim_observer=claim_observer,
        open_observer=open_observer,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert actions.items == [OpenQuests(), CloseDailyQuests()]
    assert claim_observer.wait_calls == []


def test_ready_carries_progress_reward_through_the_open_snapshot():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_script = [_ready(2, 2.0, claimable=False, progress=True),
                   _ready(3, 2.4, claimable=False, progress=True)]
    progressed = [
        _snapshot(4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
                  observations=_rows()),
        _snapshot(5, 3.6, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
                  observations=_rows()),
    ]
    closed = [
        _snapshot(6, 4.0, base=SCREEN_LOBBY),
        _snapshot(7, 4.3, base=SCREEN_LOBBY),
    ]
    # The progress-reward wait runs on the main observer today (only the
    # ClaimAll wait is claim-scoped); the open snapshot only carries the
    # progress decision into it.
    main = RecordingObserver(lobby, [progressed, closed])
    open_observer = RecordingObserver(lobby, [open_script])
    claim_observer = RecordingObserver(lobby, [])
    actions = Actions()
    flow = DailyQuestsFlow(
        main, actions, Events(), claim_observer=claim_observer,
        open_observer=open_observer,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.progress_reward_executed and result.progress_reward_completed
    assert ClaimDailyQuestsProgressReward() in actions.items
    assert claim_observer.wait_calls == []


def test_open_done_matrix():
    off_daily = _snapshot(2, 2.0, base=SCREEN_QUESTS)
    assert DailyQuestsFlow._is_open_done(off_daily)

    on_daily_bare = _snapshot(
        2, 2.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,)
    )
    assert not DailyQuestsFlow._is_open_done(on_daily_bare)

    on_daily_ready = _snapshot(
        2, 2.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
        observations=_rows(),
    )
    assert DailyQuestsFlow._is_open_done(on_daily_ready)

    assert not DailyQuestsFlow._is_open_done(
        _snapshot(2, 2.0, base=SCREEN_LOBBY)
    )
    assert not DailyQuestsFlow._is_open_done(_snapshot(2, 2.0, base=None))


def test_off_daily_open_selects_tab_then_waits_for_post_tab_readiness():
    from bot.semantic_actions import SelectDailyQuests

    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    off_daily_a = _snapshot(2, 2.0, base=SCREEN_QUESTS)
    off_daily_b = _snapshot(3, 2.3, base=SCREEN_QUESTS)
    # Post-tap: Daily active but still loading, then ready with a claim.
    loading = _snapshot(
        4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
        observations=(*_rows(), *_loading()),
    )
    ready = _ready(5, 3.5)
    ready_stable = _ready(6, 3.8)
    settled = [
        _snapshot(7, 4.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
                  observations=_rows()),
        _snapshot(8, 4.6, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,),
                  observations=_rows()),
    ]
    closed = [
        _snapshot(9, 5.0, base=SCREEN_LOBBY),
        _snapshot(10, 5.3, base=SCREEN_LOBBY),
    ]
    main = RecordingObserver(
        lobby, [closed],
        observe_sequence=[loading, ready],
    )
    open_observer = RecordingObserver(lobby, [[off_daily_a, off_daily_b]])
    claim_observer = RecordingObserver(lobby, [settled])
    actions = Actions()
    flow = DailyQuestsFlow(
        main, actions, Events(), claim_observer=claim_observer,
        open_observer=open_observer,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.claim_all_executed and result.claim_all_completed
    assert [type(item) for item in actions.items] == [
        OpenQuests, SelectDailyQuests, ClaimAllDailyQuests, CloseDailyQuests,
    ]


def test_never_ready_open_never_noops():
    # The Batch B1 defect read chrome-without-rows as a valid noop. A wait
    # that never reaches readiness must fail bounded instead of completing.
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_script = [
        _not_ready(2, 2.0, loading=False),
        _not_ready(3, 2.5, loading=True),
    ]
    open_observer = RecordingObserver(lobby, [open_script])
    actions = Actions()
    flow = DailyQuestsFlow(
        RecordingObserver(lobby, []), actions, Events(),
        claim_observer=RecordingObserver(lobby, []),
        open_observer=open_observer,
    )
    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert actions.items == [OpenQuests()]


def test_unknown_open_authorizes_no_input():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    open_script = [
        _snapshot(2, 2.0, base=None),
        _snapshot(3, 2.5, base=None),
    ]
    open_observer = RecordingObserver(lobby, [open_script])
    actions = Actions()
    flow = DailyQuestsFlow(
        RecordingObserver(lobby, []), actions, Events(),
        claim_observer=RecordingObserver(lobby, []),
        open_observer=open_observer,
    )
    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert actions.items == [OpenQuests()]


def test_open_scope_selects_exactly_the_six_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, DAILY_OPEN_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 6
    assert len(source.detectors) > len(scoped.detectors)
    assert set(DAILY_OPEN_SCOPE_SPEC_NAMES) == {
        "landmark.daily_quests_title",
        "landmark.daily_quests_tab_active",
        "landmark.daily_quests_row_claim_button",
    }
    assert DAILY_OPEN_SCOPE.specialized_types == (
        DailyQuestsProgressRewardDetector,
        DailyQuestsRowsDetector,
        DailyQuestsLoadingDetector,
    )


def test_open_scope_fails_fast_when_a_detector_is_missing():
    source = build_default_perception(ROOT)
    assert len(source.detectors) > 6
    reduced = PerceptionEngine(
        detectors=tuple(
            item
            for item in source.detectors
            if not isinstance(item, DailyQuestsLoadingDetector)
        )
    )
    with pytest.raises(ValueError, match="missing detector"):
        select_detectors(reduced, DAILY_OPEN_SCOPE)


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


def test_registry_wires_open_scope_with_readiness_carry():
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

    scoped = _daily_open_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 6
    assert ("daily_quests.open_scope_active", {"detector_count": 6}) in [
        (name, fields) for name, fields in events.items
    ]


def test_registry_builds_daily_quests_with_open_and_claim_observers():
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
    assert flow.open_observer is not observer
    assert len(flow.open_observer.perception.detectors) == 6
    assert flow.claim_observer is not observer
    assert len(flow.claim_observer.perception.detectors) == 4


def _wrap(frame_path, engine, resolver, *, sequence):
    image = _read(frame_path)
    frame = FrameSnapshot(image=image, timestamp=float(sequence), sequence=sequence)
    batch = engine.analyze(frame)
    return RuntimeSnapshot(
        frame=frame,
        observations=batch,
        state=resolver.resolve(batch),
        facts=_facts_from(batch),
        geometry=FrameGeometry.from_frame(image),
    )


def test_open_scope_matches_global_on_ready_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, DAILY_OPEN_SCOPE)
    resolver = build_default_resolver()

    ready_paths = {
        **{name: READINESS_FRAMES[name] for name in READINESS_FRAMES
           if name.startswith(("ready/", "warm/"))},
        "claimable": MAILBOX_CORPUS_FRAMES["claimable"],
        "settled": MAILBOX_CORPUS_FRAMES["settled"],
        "progress": MAILBOX_CORPUS_FRAMES["progress"],
    }
    for name, path in ready_paths.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
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
        assert DailyQuestsFlow._is_content_ready(
            scoped_snapshot
        ) == DailyQuestsFlow._is_content_ready(global_snapshot) is True, name
        assert DailyQuestsFlow._has_incompatible_daily_navigation(
            scoped_snapshot
        ) == DailyQuestsFlow._has_incompatible_daily_navigation(
            global_snapshot
        ), name
        assert (
            STATUS_DAILY_QUESTS_CLAIMABLE in scoped_snapshot.state.overlays
        ) == (
            STATUS_DAILY_QUESTS_CLAIMABLE in global_snapshot.state.overlays
        ), name
        assert (
            STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE
            in scoped_snapshot.state.overlays
        ) == (
            STATUS_DAILY_QUESTS_PROGRESS_REWARD_CLAIMABLE
            in global_snapshot.state.overlays
        ), name


def test_loading_and_clear_frames_are_never_ready_in_either_engine():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, DAILY_OPEN_SCOPE)
    resolver = build_default_resolver()

    for name in ("loading/a", "loading/b", "loading/c", "loading/d", "clear"):
        for engine in (full, scoped):
            snapshot = _wrap(READINESS_FRAMES[name], engine, resolver, sequence=1)
            assert DailyQuestsFlow._is_quests(snapshot), (name, engine)
            assert not DailyQuestsFlow._is_content_ready(snapshot), (name, engine)


def test_incremental_evaluator_scores_only_new_pairs_then_reuses_them():
    import shutil
    import tempfile

    # NOTE: pytest tmp_path is unusable in this sandbox (pre-existing
    # permission failure), so the hermetic cache lives under the
    # machine-local pre-approved temp dir with a unique name per run.
    cache_dir = Path(
        tempfile.mkdtemp(prefix="readiness-eval-", dir=_LOCAL_TMP)
    )
    try:
        detectors = [
            DailyQuestsRowsDetector(asset_root=ROOT),
            DailyQuestsLoadingDetector(asset_root=ROOT),
        ]
        frames = sorted(READINESS_FRAMES.values())
        cache = cache_dir / "pairs.json"

        first, first_stats = evaluate_detector_frame_pairs(
            ROOT, frames, detectors, cache_path=cache
        )
        assert first_stats.total_pairs == len(frames) * len(detectors)
        assert first_stats.cache_hits == 0
        assert first_stats.evaluated_pairs == first_stats.total_pairs

        emitted = {
            frame.path: {item.name for item in frame.observations}
            for frame in first
        }
        entries = {entry.path: entry for entry in load_manifest(MANIFEST)}
        for path in frames:
            assert set(entries[path].observations) <= emitted[path], path

        rerun_detectors = [
            DailyQuestsRowsDetector(asset_root=ROOT),
            DailyQuestsLoadingDetector(asset_root=ROOT),
        ]
        _, second_stats = evaluate_detector_frame_pairs(
            ROOT, frames, rerun_detectors, cache_path=cache
        )
        assert second_stats.cache_hits == second_stats.total_pairs
        assert second_stats.evaluated_pairs == 0
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
