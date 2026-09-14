"""Experimental claim-scoped perception for the Mailbox ``ClaimAll`` waits.

Covers only the claim-processing phase (onset + completion/fallback):
detector subset composition, resolution equivalence against the global
engine on curated Mailbox frames, flow routing of exactly those waits
through the scoped observer, the ``RuntimeObserver.scoped`` seam and the
registry wiring with its bounded fallback to the main observer.

Mailbox open, Character Mail navigation, Delete Read, close, timeouts and
stable_for values are intentionally out of scope: the only experimental
variable is which perception runs per frame.
"""

from pathlib import Path

import inspect

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MODE_MAILBOX_CHARACTER_MAIL,
    SCREEN_LOBBY,
    SCREEN_MAILBOX,
    STATUS_MAILBOX_CLAIMABLE,
    STATUS_MAILBOX_READ_MAIL_PRESENT,
    build_default_resolver,
)
from bot.flow_contracts import FlowStatus
from bot.flow_registry import _build_mailbox, _mailbox_claim_observer_for
from bot.mailbox_flow import (
    MailboxFlow,
    _has_claim_processing_activity,
    _has_incompatible_processing_state,
    _is_character_mail_without_activity,
)
from bot.observations import ObservationBatch
from bot.perception import (
    MAILBOX_CLAIM_SCOPE,
    MAILBOX_CLAIM_SCOPE_SPEC_NAMES,
    build_default_perception,
    mailbox_claim_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector
from bot.perception.mailbox import MailboxClaimProcessingDetector
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
    _facts_from,
)
from bot.semantic_actions import (
    ClaimAllCharacterMail,
    CloseMailbox,
    DeleteReadCharacterMail,
    OpenMailbox,
    SelectCharacterMail,
)
from bot.state import ResolutionStatus, ResolvedState

ROOT = Path(__file__).resolve().parents[1]

CLAIM_FRAMES = {
    "claimable/01": (
        "screencaps/semantic/daily-quests-mailbox/"
        "mailbox-character-claimable/01.png"
    ),
    "claimable/02": (
        "screencaps/semantic/daily-quests-mailbox/"
        "mailbox-character-claimable/02.png"
    ),
    "claimable/03": (
        "screencaps/semantic/daily-quests-mailbox/"
        "mailbox-character-claimable/03.png"
    ),
    "processing/01": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-processing/01.png"
    ),
    "processing/02": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-processing/02.png"
    ),
    "processing/03": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-processing/03.png"
    ),
    "processing/04": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-processing/04.png"
    ),
    "read/01": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-read/01.png"
    ),
    "read/02": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-read/02.png"
    ),
    "read/03": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-read/03.png"
    ),
    "leftovers/01": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-leftovers/01.png"
    ),
    "leftovers/02": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-leftovers/02.png"
    ),
    "leftovers/03": (
        "screencaps/semantic/daily-quests-mailbox/mailbox-leftovers/03.png"
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

MAILBOX_OBSERVATION_NAMES = frozenset(
    {
        "landmark.mailbox_title",
        "landmark.mailbox_character_mail_active",
        "landmark.mailbox_row_claim_button",
        "landmark.mailbox_row_delete_button",
        "activity.mailbox_claim_processing",
    }
)


def _scoped_engine():
    return mailbox_claim_perception(build_default_perception(ROOT))


def test_claim_scope_selects_exactly_the_five_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = mailbox_claim_perception(source)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 5
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(MAILBOX_CLAIM_SCOPE_SPEC_NAMES)
    assert (
        sum(
            isinstance(item, MailboxClaimProcessingDetector)
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
        mailbox_claim_perception(object())


def test_claim_scope_fails_fast_when_a_detector_is_missing():
    with pytest.raises(ValueError):
        mailbox_claim_perception(PerceptionEngine(detectors=()))


def test_claim_scope_fails_fast_without_processing_detector():
    source = build_default_perception(ROOT)
    local_only = PerceptionEngine(
        detectors=tuple(
            detector
            for detector in source.detectors
            if isinstance(detector, LocalCvDetector)
            and detector.spec.name in MAILBOX_CLAIM_SCOPE_SPEC_NAMES
        )
    )
    assert len(local_only.detectors) == 4
    with pytest.raises(ValueError):
        mailbox_claim_perception(local_only)


def _resolve(frame_path, engine, resolver):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None
    snapshot = FrameSnapshot(image=image, timestamp=1.0, sequence=1)
    batch = engine.analyze(snapshot)
    return resolver.resolve(batch), batch


def test_scoped_resolution_matches_global_on_mailbox_frames():
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


def test_scoped_mailbox_observations_match_global_on_mailbox_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        _, global_batch = _resolve(path, full, resolver)
        _, scoped_batch = _resolve(path, scoped, resolver)
        assert _mailbox_facts(scoped_batch) == _mailbox_facts(
            global_batch
        ), name


def _mailbox_facts(batch):
    return sorted(
        (item.name, item.confidence)
        for item in batch.observations
        if item.name in MAILBOX_OBSERVATION_NAMES
    )


def test_specialized_detector_participates_inside_the_scope():
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        _, batch = _resolve(path, scoped, resolver)
        names = {item.name for item in batch.observations}
        if name.startswith("processing"):
            assert "activity.mailbox_claim_processing" in names, name
        else:
            assert "activity.mailbox_claim_processing" not in names, name


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


def test_scoped_predicates_agree_with_global_on_mailbox_frames():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert _has_claim_processing_activity(
            scoped_snapshot
        ) == _has_claim_processing_activity(global_snapshot), name
        assert _is_character_mail_without_activity(
            scoped_snapshot
        ) == _is_character_mail_without_activity(global_snapshot), name
        assert _has_incompatible_processing_state(
            scoped_snapshot
        ) == _has_incompatible_processing_state(global_snapshot), name


def test_completion_semantics_hold_under_the_scope():
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        snapshot = _wrap(path, scoped, resolver, sequence=1)
        if name.startswith("read"):
            # Settled with read mail present: completion, Delete Read next.
            assert _is_character_mail_without_activity(snapshot), name
            assert STATUS_MAILBOX_READ_MAIL_PRESENT in snapshot.state.overlays
            assert STATUS_MAILBOX_CLAIMABLE not in snapshot.state.overlays
        elif name.startswith(("claimable", "leftovers")):
            # Claimable frames also satisfy the quiescence predicate (mode
            # present, no activity); the leftover/no-effect distinction is
            # the CLAIMABLE overlay the fallback branch reads afterwards.
            assert _is_character_mail_without_activity(snapshot), name
            assert STATUS_MAILBOX_CLAIMABLE in snapshot.state.overlays
        else:
            # Any processing activity (or bubble-occluded mode) is transit,
            # never completion.
            assert not _is_character_mail_without_activity(snapshot), name
            assert _has_claim_processing_activity(snapshot), name


def test_bubble_frames_neither_complete_nor_abort():
    """Bubble-occluded processing frames keep base mailbox + activity.

    Mode may be missing, but the wait must stay pending (no fabricated
    completion, no incorrect abort) exactly as the global runtime does.
    """

    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name in ("processing/01", "processing/02", "processing/03",
                 "processing/04"):
        snapshot = _wrap(
            CLAIM_FRAMES[name], scoped, resolver, sequence=1
        )
        assert not _is_character_mail_without_activity(snapshot), name
        assert not _has_incompatible_processing_state(snapshot), name


def _synthetic_snapshot(
    *, status, base=None, overlays=(), activity=False, candidates=()
):
    from bot.observations import Observation, ObservationSource

    image = np.zeros((120, 240, 3), dtype=np.uint8)
    observations = ()
    if activity:
        observations = (
            Observation(
                "activity.mailbox_claim_processing",
                1.0,
                ObservationSource.LOCAL_CV,
            ),
        )
    batch = ObservationBatch(
        sequence=1, timestamp=1.0, observations=observations
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, 1.0, 1),
        batch,
        ResolvedState(
            status,
            1,
            1.0,
            base,
            tuple(overlays),
            base_candidates=tuple(candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def test_unknown_frame_never_fabricates_onset_or_completion():
    snapshot = _synthetic_snapshot(
        status=ResolutionStatus.UNKNOWN, base=None, overlays=()
    )
    assert not _has_claim_processing_activity(snapshot)
    assert not _is_character_mail_without_activity(snapshot)
    assert not _has_incompatible_processing_state(snapshot)


def test_ambiguous_frame_aborts_but_never_completes():
    snapshot = _synthetic_snapshot(
        status=ResolutionStatus.AMBIGUOUS,
        base=None,
        overlays=(),
        candidates=(SCREEN_LOBBY, SCREEN_MAILBOX),
    )
    assert not _has_claim_processing_activity(snapshot)
    assert not _is_character_mail_without_activity(snapshot)
    assert _has_incompatible_processing_state(snapshot)


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
        assert not _has_claim_processing_activity(scoped_snapshot), name
        assert not _is_character_mail_without_activity(
            scoped_snapshot
        ), name
        assert not _has_incompatible_processing_state(
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


def _snapshot(sequence, timestamp, *, base, overlays=(), activity=False):
    from bot.observations import Observation, ObservationSource

    image = np.zeros((120, 240, 3), dtype=np.uint8)
    observations = ()
    if activity:
        observations = (
            Observation(
                "activity.mailbox_claim_processing",
                1.0,
                ObservationSource.LOCAL_CV,
            ),
        )
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, observations),
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


def _character(*statuses):
    return (MODE_MAILBOX_CHARACTER_MAIL, *statuses)


def test_claim_waits_route_through_claim_observer_only():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = _snapshot(2, 2.0, base=SCREEN_MAILBOX)
    character = _snapshot(
        3, 3.0, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_CLAIMABLE
        ),
    )
    active = _snapshot(4, 4.0, base=SCREEN_MAILBOX, activity=True)
    settled_a = _snapshot(
        5, 4.6, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_READ_MAIL_PRESENT
        ),
    )
    settled_b = _snapshot(
        6, 5.4, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_READ_MAIL_PRESENT
        ),
    )
    deleted_a = _snapshot(
        7, 6.2, base=SCREEN_MAILBOX, overlays=_character()
    )
    deleted_b = _snapshot(
        8, 6.8, base=SCREEN_MAILBOX, overlays=_character()
    )
    closed = _snapshot(9, 7.2, base=SCREEN_LOBBY)

    main = RecordingObserver(
        lobby, [[account], [character], [deleted_a, deleted_b], [closed]]
    )
    claim = RecordingObserver(lobby, [[active], [settled_a, settled_b]])
    flow = MailboxFlow(
        main,
        Actions(),
        Events(),
        claim_observer=claim,
        navigation_stable_for=0.0,
        processing_stable_for=0.75,
        no_effect_stable_for=0.5,
        delete_stable_for=0.5,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.processing_observed and result.processing_completed
    assert flow.actions.items == [
        OpenMailbox(),
        SelectCharacterMail(),
        ClaimAllCharacterMail(),
        DeleteReadCharacterMail(),
        CloseMailbox(),
    ]
    # Same contract as the global waits: 2 s onset without stability,
    # then 30 s completion with 0.75 s stability.
    assert claim.calls == [(2.0, 0.0), (30.0, 0.75)]
    assert main.calls == [(6.0, 0.0), (6.0, 0.0), (12.0, 0.5), (6.0, 0.0)]


def test_onset_fallback_routes_through_claim_observer_with_same_contract():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = _snapshot(2, 2.0, base=SCREEN_MAILBOX)
    claims = _character(STATUS_MAILBOX_CLAIMABLE)
    character = _snapshot(3, 3.0, base=SCREEN_MAILBOX, overlays=claims)
    after_claim = _snapshot(
        4, 4.0, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_READ_MAIL_PRESENT
        ),
    )
    settled_a = _snapshot(
        5, 5.0, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_READ_MAIL_PRESENT
        ),
    )
    settled_b = _snapshot(
        6, 5.8, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_READ_MAIL_PRESENT
        ),
    )
    deleted_a = _snapshot(
        7, 6.2, base=SCREEN_MAILBOX, overlays=_character()
    )
    deleted_b = _snapshot(
        8, 6.8, base=SCREEN_MAILBOX, overlays=_character()
    )
    closed = _snapshot(9, 7.2, base=SCREEN_LOBBY)
    onset_timeout = RuntimeWaitTimeout(
        after_sequence=3, timeout=2.0, last_snapshot=after_claim
    )

    main = RecordingObserver(
        lobby, [[account], [character], [deleted_a, deleted_b], [closed]]
    )
    claim = RecordingObserver(
        lobby, [onset_timeout, [settled_a, settled_b]]
    )
    flow = MailboxFlow(
        main,
        Actions(),
        Events(),
        claim_observer=claim,
        navigation_stable_for=0.0,
        processing_stable_for=0.75,
        no_effect_stable_for=0.5,
        delete_stable_for=0.5,
    )
    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert not result.processing_observed
    assert result.processing_completed
    # Fallback keeps the functional contract: 30 s with
    # max(no_effect, processing) stability = 0.75 s.
    assert claim.calls == [(2.0, 0.0), (30.0, 0.75)]


def test_claim_wait_abort_through_scope_fails_bounded_without_further_input():
    lobby = _snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = _snapshot(2, 2.0, base=SCREEN_MAILBOX)
    character = _snapshot(
        3, 3.0, base=SCREEN_MAILBOX, overlays=_character(
            STATUS_MAILBOX_CLAIMABLE
        ),
    )
    incompatible = _snapshot(4, 4.0, base=SCREEN_LOBBY)

    main = RecordingObserver(lobby, [[account], [character]])
    claim = RecordingObserver(lobby, [[incompatible]])
    actions = Actions()
    flow = MailboxFlow(
        main,
        actions,
        Events(),
        claim_observer=claim,
        navigation_stable_for=0.0,
        processing_stable_for=0.75,
        no_effect_stable_for=0.5,
        delete_stable_for=0.5,
    )
    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert actions.items == [
        OpenMailbox(),
        SelectCharacterMail(),
        ClaimAllCharacterMail(),
    ]
    assert claim.calls == [(2.0, 0.0)]


def test_claim_observer_defaults_to_main_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, base=SCREEN_LOBBY), []
    )
    flow = MailboxFlow(observer, Actions(), Events())
    assert flow.claim_observer is observer


def test_claim_observer_rejects_non_observer():
    observer = RecordingObserver(
        _snapshot(1, 1.0, base=SCREEN_LOBBY), []
    )
    with pytest.raises(ValueError):
        MailboxFlow(observer, Actions(), Events(), claim_observer=object())


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
    assert _mailbox_claim_observer_for(deps, main) is main


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

    scoped = _mailbox_claim_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 5
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert ("mailbox.claim_scope_active", {"detector_count": 5}) in [
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

    assert _mailbox_claim_observer_for(deps, observer) is observer
    assert any(
        name == "mailbox.claim_scope_unavailable" for name, _ in events.items
    )


def test_registry_builds_mailbox_with_claim_observer():
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

    flow = _build_mailbox(deps)

    assert isinstance(flow, MailboxFlow)
    assert flow.claim_observer is not observer
    assert len(flow.claim_observer.perception.detectors) == 5


def test_claim_rehost_matches_legacy_builder_exactly():
    source = build_default_perception(ROOT)

    generic = select_detectors(source, MAILBOX_CLAIM_SCOPE)
    legacy = mailbox_claim_perception(source)

    assert len(generic.detectors) == 5
    assert tuple(generic.detectors) == tuple(legacy.detectors)


def test_generic_scope_matches_legacy_on_mailbox_frames():
    source = build_default_perception(ROOT)
    generic = select_detectors(source, MAILBOX_CLAIM_SCOPE)
    legacy = mailbox_claim_perception(source)
    resolver = build_default_resolver()

    for name, path in CLAIM_FRAMES.items():
        generic_snapshot = _wrap(path, generic, resolver, sequence=1)
        legacy_snapshot = _wrap(path, legacy, resolver, sequence=1)
        assert (
            generic_snapshot.observations
            == legacy_snapshot.observations
        ), name
        assert generic_snapshot.state == legacy_snapshot.state, name
        assert _has_claim_processing_activity(
            generic_snapshot
        ) == _has_claim_processing_activity(legacy_snapshot), name
        assert _is_character_mail_without_activity(
            generic_snapshot
        ) == _is_character_mail_without_activity(legacy_snapshot), name
        assert _has_incompatible_processing_state(
            generic_snapshot
        ) == _has_incompatible_processing_state(legacy_snapshot), name


def test_generic_scope_preserves_row_delete_carry():
    source = build_default_perception(ROOT)
    generic = select_detectors(source, MAILBOX_CLAIM_SCOPE)
    resolver = build_default_resolver()

    snapshot = _wrap(CLAIM_FRAMES["read/01"], generic, resolver, sequence=1)
    assert _is_character_mail_without_activity(snapshot)
    assert STATUS_MAILBOX_READ_MAIL_PRESENT in snapshot.state.overlays


def test_claim_wiring_uses_generic_infra():
    source_text = inspect.getsource(_mailbox_claim_observer_for)
    assert "scoped_observer_for(" in source_text
    assert "mailbox_claim_perception" not in source_text
