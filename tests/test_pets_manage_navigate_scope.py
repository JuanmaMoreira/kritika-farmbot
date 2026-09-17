"""Scoped-first Lobby -> Pets Manage navigation (``precondition.open_pets``).

Migrates one positive known transition to scoped perception, keeping
every retry/policy/timing identical:

- source: clean Lobby
- expected: clean Pets Manage (daily badge allowed)
- retryable_from: clean Lobby
- abort: incompatible destination (Quick Menu excused, AMBIGUOUS/foreign abort)
- scope: PETS_MANAGE_NAVIGATE_SCOPE (new, 5 LocalCv, no specialized)

Initial observes stay global (discovery). Closes to Lobby stay global.
Recovery/discovery stays global: no scoped->global fallback inside a wait;
foreign states degrade to bounded timeout with no input authorized.
"""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MENU_QUICK,
    SCREEN_LOBBY,
    SCREEN_MAILBOX,
    SCREEN_PETS_MANAGE,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.observations import ObservationBatch
from bot.perception import (
    PETS_MANAGE_NAVIGATE_SCOPE,
    PETS_MANAGE_NAVIGATE_SCOPE_SPEC_NAMES,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector
from bot.productive_runtime import (
    ProductiveRuntime,
    _has_incompatible_destination_state,
    _has_quick_menu,
    _is_clean_base as _runtime_is_clean_base,
)
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
    _facts_from,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(sequence, timestamp, *, status, base=SCREEN_LOBBY,
              overlays=(), facts=None, candidates=()):
    if status is ResolutionStatus.RESOLVED:
        pass
    elif status is ResolutionStatus.AMBIGUOUS:
        base = None
    else:
        base = None
        candidates = ()
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence=sequence, timestamp=timestamp,
                         observations=()),
        ResolvedState(status, sequence, timestamp, base_context=base,
                      overlays=tuple(overlays),
                      base_candidates=tuple(candidates)),
        facts if facts is not None else RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _lobby(sequence=1, timestamp=1.0):
    return _snapshot(sequence, timestamp, status=ResolutionStatus.RESOLVED,
                     base=SCREEN_LOBBY)


def _pets(sequence=2, timestamp=2.0, overlays=()):
    return _snapshot(sequence, timestamp, status=ResolutionStatus.RESOLVED,
                     base=SCREEN_PETS_MANAGE, overlays=tuple(overlays))


class RecordingObserver:
    def __init__(self, initial, script=()):
        self.initial = initial
        self.script = list(script)
        self.observe_calls = 0
        self.wait_calls = []

    def observe(self):
        self.observe_calls += 1
        return self.initial

    def wait_until(self, condition, *, after_sequence, timeout,
                   abort_if=None, cancel_requested=None, stable_for=0.0):
        self.wait_calls.append((timeout, stable_for))
        stable_since = None
        last = None
        for item in self.script:
            last = item
            assert item.sequence > after_sequence
            if abort_if is not None and abort_if(item):
                raise RuntimeWaitAborted(item)
            if condition(item):
                if stable_since is None:
                    stable_since = item.timestamp
                if item.timestamp - stable_since >= stable_for:
                    return item
            else:
                stable_since = None
        raise RuntimeWaitTimeout(after_sequence=after_sequence,
                                 timeout=timeout, last_snapshot=last)


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


# ---------------------------------------------------------------------------
# Composition: the new scope selects exactly its declared vocabulary.
# ---------------------------------------------------------------------------


def test_pets_manage_navigate_scope_selects_exactly_five_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, PETS_MANAGE_NAVIGATE_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 5
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(PETS_MANAGE_NAVIGATE_SCOPE_SPEC_NAMES)
    assert "landmark.lobby_trading_center_label" in local_names
    assert "landmark.pets_manage_active" in local_names
    assert "landmark.pets_shell_summon_package" in local_names
    assert "landmark.quick_menu_lobby_tile" in local_names
    assert PETS_MANAGE_NAVIGATE_SCOPE.specialized_types == ()
    expected_order = tuple(
        detector for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_pets_manage_navigate_scope_fails_fast():
    source = build_default_perception(ROOT)
    assert len(source.detectors) == 96
    with pytest.raises(ValueError):
        select_detectors(PerceptionEngine(detectors=()),
                         PETS_MANAGE_NAVIGATE_SCOPE)
    with pytest.raises(ValueError):
        select_detectors(object(), PETS_MANAGE_NAVIGATE_SCOPE)
    local_only_missing_quick = PerceptionEngine(
        detectors=tuple(
            detector for detector in source.detectors
            if isinstance(detector, LocalCvDetector)
            and detector.spec.name in PETS_MANAGE_NAVIGATE_SCOPE_SPEC_NAMES
            and detector.spec.name != "landmark.quick_menu_lobby_tile"
        )
    )
    assert len(local_only_missing_quick.detectors) == 4
    with pytest.raises(ValueError):
        select_detectors(local_only_missing_quick,
                         PETS_MANAGE_NAVIGATE_SCOPE)


# ---------------------------------------------------------------------------
# Contract: expected / retryable / abort / UNKNOWN safety.
# ---------------------------------------------------------------------------


def test_open_pets_contract():
    pets = _pets(2, 2.0)
    assert _runtime_is_clean_base(pets, SCREEN_PETS_MANAGE)
    pets_daily = _pets(2, 2.0, overlays=(STATUS_PET_SUMMON_DAILY_ACTIVE,))
    assert _runtime_is_clean_base(pets_daily, SCREEN_PETS_MANAGE)

    assert _runtime_is_clean_base(_lobby(), SCREEN_LOBBY)
    assert not _has_incompatible_destination_state(
        _lobby(), SCREEN_LOBBY, SCREEN_PETS_MANAGE)
    assert not _has_incompatible_destination_state(
        pets, SCREEN_LOBBY, SCREEN_PETS_MANAGE)

    quick = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN,
                      overlays=(MENU_QUICK,))
    assert _has_quick_menu(quick)
    assert not _has_incompatible_destination_state(
        quick, SCREEN_LOBBY, SCREEN_PETS_MANAGE)

    unknown = _snapshot(2, 2.0, status=ResolutionStatus.UNKNOWN)
    assert not _runtime_is_clean_base(unknown, SCREEN_PETS_MANAGE)
    assert not _runtime_is_clean_base(unknown, SCREEN_LOBBY)
    assert not _has_incompatible_destination_state(
        unknown, SCREEN_LOBBY, SCREEN_PETS_MANAGE)

    ambiguous = _snapshot(2, 2.0, status=ResolutionStatus.AMBIGUOUS,
                          candidates=(SCREEN_LOBBY, SCREEN_PETS_MANAGE))
    assert _has_incompatible_destination_state(
        ambiguous, SCREEN_LOBBY, SCREEN_PETS_MANAGE)

    foreign = _snapshot(2, 2.0, status=ResolutionStatus.RESOLVED,
                        base=SCREEN_MAILBOX)
    assert _has_incompatible_destination_state(
        foreign, SCREEN_LOBBY, SCREEN_PETS_MANAGE)


# ---------------------------------------------------------------------------
# Wiring: the migrated wait runs scoped; everything else stays put.
# ---------------------------------------------------------------------------


def _runtime_stub(main_observer, scoped_observer):
    actions, events = Actions(), Events()
    stub = SimpleNamespace(
        observer=main_observer, actions=actions, events=events,
        cancel_requested=lambda: False,
    )
    stub.build_verified_transition = lambda: VerifiedTransition(
        main_observer, actions, events, None)
    return stub, actions, events


class ScopedMainObserver(RecordingObserver):
    def __init__(self, initial, script=(), scoped=None):
        super().__init__(initial, script)
        self._scoped = scoped
        self.perception = build_default_perception(ROOT)
        if scoped is not None:
            scoped.perception = self.perception

    def scoped(self, perception):
        self._scoped.perception = perception
        return self._scoped


def test_open_pets_runs_scoped_with_identical_policy():
    lobby = _lobby(1, 1.0)
    pets_a = _pets(2, 2.0)
    pets_b = _pets(3, 2.3)
    scoped = RecordingObserver(lobby, [pets_a, pets_b])
    main = ScopedMainObserver(lobby, [], scoped=scoped)
    stub, actions, events = _runtime_stub(main, scoped)

    assert ProductiveRuntime._navigate_to_pets_manage(stub) is True
    assert scoped.wait_calls == [(6.0, 0.25)]
    assert main.wait_calls == []
    assert len(actions.items) == 1
    assert any(event == "precondition.pets_manage_navigate_scope_active"
               for event, _ in events.items)
    count = next(fields["detector_count"] for event, fields in events.items
                 if event == "precondition.pets_manage_navigate_scope_active")
    assert count == 5


def test_open_pets_falls_back_to_global_without_scoping():
    lobby = _lobby(1, 1.0)
    pets_a = _pets(2, 2.0)
    pets_b = _pets(3, 2.3)
    main = RecordingObserver(lobby, [pets_a, pets_b])
    stub, actions, events = _runtime_stub(main, None)

    assert ProductiveRuntime._navigate_to_pets_manage(stub) is True
    assert main.wait_calls == [(6.0, 0.25)]
    assert len(actions.items) == 1


def test_open_pets_abort_fails_bounded_without_further_input():
    lobby = _lobby(1, 1.0)
    foreign = _snapshot(2, 2.0, status=ResolutionStatus.RESOLVED,
                        base=SCREEN_MAILBOX)
    scoped = RecordingObserver(lobby, [foreign])
    main = ScopedMainObserver(lobby, [], scoped=scoped)
    stub, actions, events = _runtime_stub(main, scoped)

    assert ProductiveRuntime._navigate_to_pets_manage(stub) is False
    assert scoped.wait_calls == [(6.0, 0.25)]
    assert len(actions.items) == 1


def test_wiring_uses_generic_infra_only():
    import inspect

    runtime_source = inspect.getsource(
        ProductiveRuntime._navigate_to_pets_manage)
    assert "scoped_transition_for" in runtime_source
    assert "PETS_MANAGE_NAVIGATE_SCOPE" in runtime_source


class ScriptedObserver(RecordingObserver):
    def __init__(self, initial, effects, fresh=()):
        super().__init__(initial, [])
        self.effects = list(effects)
        self.fresh = list(fresh)

    def observe(self):
        self.observe_calls += 1
        if self.fresh:
            return self.fresh.pop(0)
        return self.initial

    def wait_until(self, condition, **kwargs):
        self.wait_calls.append((kwargs["timeout"], kwargs["stable_for"]))
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


def test_open_pets_retry_stays_scoped_with_identical_policy():
    from bot.verified_transition import VerifiedTransitionPolicy

    lobby = _lobby(1, 1.0)
    pets_a = _pets(10, 10.0)
    pets_b = _pets(11, 10.8)
    scoped = ScriptedObserver(
        lobby,
        [
            RuntimeWaitTimeout(after_sequence=1, timeout=6.0,
                               last_snapshot=lobby),
            RuntimeWaitTimeout(after_sequence=1, timeout=2.0,
                               last_snapshot=lobby),
            pets_a,
            pets_b,
        ],
        fresh=[_lobby(2, 3.0)],
    )
    actions, events = Actions(), Events()
    transition = VerifiedTransition(scoped, actions, events, None)

    from bot.semantic_actions import OpenPets

    result = transition.execute(
        "precondition.open_pets",
        OpenPets(),
        lobby,
        expected=lambda snapshot: _runtime_is_clean_base(
            snapshot, SCREEN_PETS_MANAGE),
        precondition=lambda snapshot: _runtime_is_clean_base(
            snapshot, SCREEN_LOBBY),
        retryable_from=lambda snapshot: _runtime_is_clean_base(
            snapshot, SCREEN_LOBBY),
        abort_if=lambda snapshot: _has_incompatible_destination_state(
            snapshot, SCREEN_LOBBY, SCREEN_PETS_MANAGE),
        stable_for=0.25,
        policy=VerifiedTransitionPolicy(normal_timeout=6.0, grace_timeout=2.0,
                                       max_attempts=2),
    )

    assert result.succeeded
    assert result.attempt_count == 2
    assert scoped.wait_calls == [(6.0, 0.25), (2.0, 0.25), (6.0, 0.25)]
    assert len(actions.items) == 2


# ---------------------------------------------------------------------------
# Equivalence on real frames: global vs scoped, same predicates.
# ---------------------------------------------------------------------------


def _wrap(frame_path, engine, resolver, *, sequence):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None, frame_path
    frame = FrameSnapshot(image=image, timestamp=float(sequence),
                          sequence=sequence)
    batch = engine.analyze(frame)
    return (RuntimeSnapshot(frame=frame, observations=batch,
                            state=resolver.resolve(batch),
                            facts=_facts_from(batch),
                            geometry=FrameGeometry.from_frame(image)), batch)


PETS_MANAGE_FRAMES = {
    "manage/01": "screencaps/semantic/pet_summon/manage/01.png",
    "manage/02": "screencaps/semantic/pet_summon/manage/02.png",
    "manage/03": "screencaps/semantic/pet_summon/manage/03.png",
}

LOBBY_FRAMES = {
    "lobby/01": "screencaps/semantic/lobby/20260823T025455_304538Z.png",
    "lobby/02": "screencaps/semantic/lobby/20260823T025457_320447Z.png",
    "quick-menu-from-lobby/01":
        "screencaps/semantic/guild/quick-menu-from-lobby/01.png",
}


def test_scoped_matches_global_on_pets_manage_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, PETS_MANAGE_NAVIGATE_SCOPE)
    resolver = build_default_resolver()

    for name, path in PETS_MANAGE_FRAMES.items():
        global_snapshot, _ = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        assert (scoped_snapshot.state.status,
                scoped_snapshot.state.base_context) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context), name
        assert tuple(scoped_snapshot.state.overlays) == tuple(
            global_snapshot.state.overlays), name
        assert _runtime_is_clean_base(
            scoped_snapshot, SCREEN_PETS_MANAGE) == _runtime_is_clean_base(
            global_snapshot, SCREEN_PETS_MANAGE), name


def test_scoped_matches_global_on_lobby_and_quick_menu_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, PETS_MANAGE_NAVIGATE_SCOPE)
    resolver = build_default_resolver()

    for name, path in LOBBY_FRAMES.items():
        global_snapshot, _ = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot, _ = _wrap(path, scoped, resolver, sequence=1)
        assert (scoped_snapshot.state.status,
                scoped_snapshot.state.base_context) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context), name
        assert tuple(scoped_snapshot.state.overlays) == tuple(
            global_snapshot.state.overlays), name
