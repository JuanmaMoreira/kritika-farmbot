"""Scoped-first Summon Pet Daily normal-path waits (Batch C2).

Seven known-transition waits share one pets-family scope (PET_SUMMON_SCOPE,
17 detectors: no new semantics, no auto-derivation):

- Manage -> Summon navigation (SelectPetSummon, incl. both re-entries);
- summon outcome (result / insufficient-gold / pet-full, selectors stay
  passive as retryable);
- result / insufficient / pet-full dismissal back to Summon;
- pet-full -> Combine (AcceptPetInventoryFull).

The initial Manage observe stays global (discovery); the space relief
keeps its own observer. Epic insufficient-fragments and runes-full popups
stay out: the flow only taps single-summon buttons, so they cannot appear
on this path; if one ever did, the scoped view degrades to a bounded
timeout with no input, same fail-closed terminal as today.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    OVERLAY_PET_EPIC_SELECTOR,
    OVERLAY_PET_PREMIUM_GOLD_SELECTOR,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_PET_INVENTORY_FULL,
    SCREEN_LOBBY,
    SCREEN_MAILBOX,
    SCREEN_PET_COMBINE,
    SCREEN_PET_SUMMON,
    SCREEN_PET_SUMMON_RESULT,
    SCREEN_PETS_MANAGE,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.flow_contracts import FlowStatus
from bot.flow_registry import (
    _build_summon_pet_daily,
    _summon_pet_observer_for,
)
from bot.observations import ObservationBatch
from bot.perception import (
    PET_SUMMON_SCOPE,
    PET_SUMMON_SCOPE_SPEC_NAMES,
    build_default_perception,
    select_detectors,
)
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector
from bot.perception.pet_summon import PetEpicAvailabilityDetector
from bot.pet_summon_space_relief import (
    PetSummonSpaceReliefOutcome,
    PetSummonSpaceReliefResult,
)
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
    _facts_from,
)
from bot.semantic_actions import (
    AcceptPetInventoryFull,
    ClosePetSummonResult,
    OpenEpicPetSummon,
    OpenPremiumPetSummon,
    OpenSingleEpicPet,
    OpenSinglePremiumPet,
    RejectInsufficientGold,
    SelectPetSummon,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.summon_pet_daily_flow import SummonPetDailyFlow

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(sequence, base, overlays=(), status=None):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    if status is None:
        status = (
            ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
        )
    if status is not ResolutionStatus.RESOLVED:
        base = None
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence)),
        ResolvedState(
            status, sequence, float(sequence), base_context=base,
            overlays=tuple(overlays),
            base_candidates=(
                (SCREEN_LOBBY, SCREEN_PETS_MANAGE)
                if status is ResolutionStatus.AMBIGUOUS else ()
            ),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _manage(sequence, daily=True):
    return _snapshot(
        sequence, SCREEN_PETS_MANAGE,
        (STATUS_PET_SUMMON_DAILY_ACTIVE,) if daily else (),
    )


def _summon(sequence, epic, resource=STATUS_PET_PREMIUM_GOLD,
            daily=True, popup=None, selector=None):
    overlays = [epic, resource]
    if daily:
        overlays.append(STATUS_PET_SUMMON_DAILY_ACTIVE)
    if popup:
        overlays.append(popup)
    if selector:
        overlays.append(selector)
    return _snapshot(sequence, SCREEN_PET_SUMMON, overlays)


def _result(sequence):
    return _snapshot(sequence, SCREEN_PET_SUMMON_RESULT)


def _combine(sequence):
    return _snapshot(sequence, SCREEN_PET_COMBINE)


class Observer:
    """Main/summon double: scripted waits with timeout/stable log."""

    def __init__(self, initial, scripted):
        self.initial = initial
        self.scripted = list(scripted)
        self.calls = []
        self.observe_calls = 0

    def observe(self):
        self.observe_calls += 1
        return self.initial

    def wait_until(self, condition, **kwargs):
        self.calls.append((kwargs["timeout"], kwargs["stable_for"]))
        if not self.scripted:
            raise RuntimeWaitTimeout(
                after_sequence=kwargs["after_sequence"],
                timeout=kwargs["timeout"], last_snapshot=None,
            )
        current = self.scripted.pop(0)
        assert current.sequence > kwargs["after_sequence"]
        abort_if = kwargs.get("abort_if")
        if abort_if is not None and abort_if(current):
            raise RuntimeWaitAborted(current)
        assert condition(current), (
            f"scripted snapshot {current.sequence} missed expected"
        )
        return current


class MainObserver(Observer):
    """Initial observe only: any wait here is a routing regression."""

    def wait_until(self, condition, **kwargs):
        raise AssertionError("main observer must not wait on this path")


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append(action)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


class Relief:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, cancel_requested):
        self.calls.append(cancel_requested)
        return self.results.pop(0)


def _flow(main, summon, relief_results=()):
    actions, events, relief = Actions(), Events(), Relief(relief_results)
    flow = SummonPetDailyFlow(
        main, actions, events, relief, summon_observer=summon,
        navigation_timeout=6.0, outcome_timeout=12.0,
        navigation_stable_for=0.25, outcome_stable_for=0.5,
    )
    return flow, actions, events, relief


def _predicates():
    actions, events = Actions(), Events()
    main = Observer(_manage(1), [])
    flow = SummonPetDailyFlow(
        main, actions, events, Relief(), summon_observer=main
    )
    return flow


# ---------------------------------------------------------------------------
# Composition: the shared scope selects exactly its declared vocabulary.
# ---------------------------------------------------------------------------


def test_pet_summon_scope_selects_exactly_seventeen_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, PET_SUMMON_SCOPE)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 17
    assert len(source.detectors) == 96
    local_names = [
        detector.spec.name for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(PET_SUMMON_SCOPE_SPEC_NAMES)
    assert "landmark.pets_shell_summon_package" in local_names
    assert "landmark.pets_manage_active" in local_names
    assert "landmark.pet_summon_active" in local_names
    assert "landmark.pet_combine_active" in local_names
    assert "landmark.pet_combine_evolve_prompt" in local_names
    assert "landmark.pet_summon_result_banner" in local_names
    assert "landmark.pet_summon_result_parchment" in local_names
    assert "landmark.insufficient_gold_prompt" in local_names
    assert "landmark.pet_inventory_full_prompt" in local_names
    assert "landmark.pet_epic_selector" in local_names
    assert "landmark.pet_premium_gold_selector" in local_names
    assert "landmark.pet_premium_ticket_selector" in local_names
    assert "landmark.quick_menu_lobby_tile" in local_names
    assert (
        sum(isinstance(item, PetEpicAvailabilityDetector)
            for item in scoped.detectors) == 1
    )
    expected_order = tuple(
        detector for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_pet_summon_scope_fails_fast():
    source = build_default_perception(ROOT)
    with pytest.raises(ValueError):
        select_detectors(PerceptionEngine(detectors=()), PET_SUMMON_SCOPE)
    with pytest.raises(ValueError):
        select_detectors(object(), PET_SUMMON_SCOPE)
    without_quick = PerceptionEngine(
        detectors=tuple(
            detector for detector in source.detectors
            if getattr(getattr(detector, "spec", None), "name", None)
            != "landmark.quick_menu_lobby_tile"
            or isinstance(detector, PetEpicAvailabilityDetector)
        )
    )
    assert len(without_quick.detectors) == len(source.detectors) - 1
    with pytest.raises(ValueError):
        select_detectors(without_quick, PET_SUMMON_SCOPE)


# ---------------------------------------------------------------------------
# Contract per wait group (synthetic): expected / retry / abort / safety.
# ---------------------------------------------------------------------------


def test_navigation_contract():
    flow = _predicates()
    manage = _manage(2)
    ready = _summon(3, STATUS_PET_EPIC_AVAILABLE)

    assert flow._is_clean_manage(manage)
    assert flow._is_summon_ready(ready)
    # Retryable source never aborts; foreign RESOLVED aborts.
    assert not flow._known_incompatible(ready, flow._is_summon_ready,
                                       flow._is_clean_manage)
    foreign = _snapshot(3, SCREEN_MAILBOX)
    assert flow._known_incompatible(foreign, flow._is_summon_ready,
                                   flow._is_clean_manage)
    # Selector/shell frames never authorize input on this wait: a selector
    # frame aborts fail-closed (selectors only appear after card taps,
    # which this wait never performs), a shell frame waits passively.
    selector = _summon(3, STATUS_PET_EPIC_AVAILABLE,
                       selector=OVERLAY_PET_EPIC_SELECTOR)
    assert flow._is_selector(selector, True)
    assert not flow._is_summon_ready(selector)
    assert flow._known_incompatible(selector, flow._is_summon_ready,
                                   flow._is_clean_manage)
    assert not flow._is_summon_shell(selector)
    # Quick-covered Summon aborts instead of authorizing card taps.
    from bot.catalog import MENU_QUICK
    quick = _snapshot(3, SCREEN_PET_SUMMON,
                      (STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD,
                       MENU_QUICK))
    assert not flow._is_summon_ready(quick)
    assert flow._known_incompatible(quick, flow._is_summon_ready,
                                   flow._is_clean_manage)
    assert not flow._is_summon_shell(quick)
    # UNKNOWN authorizes neither input nor retry.
    unknown = _snapshot(3, None)
    assert not flow._is_summon_ready(unknown)
    assert not flow._is_clean_manage(unknown)
    assert not flow._known_incompatible(unknown, flow._is_summon_ready,
                                       flow._is_clean_manage)
    ambiguous = _snapshot(3, None, status=ResolutionStatus.AMBIGUOUS)
    assert flow._known_incompatible(ambiguous, flow._is_summon_ready,
                                   flow._is_clean_manage)


def test_outcome_contract():
    flow = _predicates()
    ready = _summon(3, STATUS_PET_EPIC_AVAILABLE)
    expected = lambda s: (flow._is_summon_result(s)
                          or flow._is_insufficient_gold(s)
                          or flow._is_pet_full(s))
    retryable = lambda s: (flow._is_summon_ready(s)
                           or flow._is_selector(s, True))

    assert expected(_result(4))
    assert expected(_summon(4, STATUS_PET_EPIC_AVAILABLE,
                            popup=POPUP_INSUFFICIENT_GOLD))
    assert expected(_summon(4, STATUS_PET_EPIC_AVAILABLE,
                            popup=POPUP_PET_INVENTORY_FULL))
    assert not expected(ready)
    assert retryable(ready)
    selector = _summon(4, STATUS_PET_EPIC_AVAILABLE,
                       selector=OVERLAY_PET_EPIC_SELECTOR)
    assert retryable(selector)
    assert not expected(selector)
    # Shell (transient, epic unresolved) waits passively: incompatible but
    # explicitly excused, so the conjunction authorizes no abort/input.
    shell = _snapshot(4, SCREEN_PET_SUMMON, (STATUS_PET_PREMIUM_GOLD,))
    assert flow._is_summon_shell(shell)
    assert flow._known_incompatible(
        shell, expected,
        lambda s: retryable(s) or flow._is_selector(s, True))
    assert not (flow._known_incompatible(
        shell, expected,
        lambda s: retryable(s) or flow._is_selector(s, True))
        and not flow._is_summon_shell(shell))
    # Popup + Quick cover aborts instead of dispatching taps.
    from bot.catalog import MENU_QUICK
    covered = _snapshot(4, SCREEN_PET_SUMMON,
                        (STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD,
                         POPUP_PET_INVENTORY_FULL, MENU_QUICK))
    assert not expected(covered)
    assert flow._known_incompatible(covered, expected, retryable)
    assert not flow._is_summon_shell(covered)
    unknown = _snapshot(4, None)
    assert not expected(unknown)
    assert not flow._known_incompatible(unknown, expected, retryable)


def test_dismissal_and_combine_contracts():
    flow = _predicates()
    ready = _summon(5, STATUS_PET_EPIC_AVAILABLE)
    assert flow._is_summon_result(_result(4))
    assert flow._is_insufficient_gold(_summon(
        4, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_INSUFFICIENT_GOLD))
    assert flow._is_pet_full(_summon(
        4, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL))
    assert flow._is_clean_combine(_combine(6))
    assert not flow._is_clean_combine(_summon(
        6, STATUS_PET_EPIC_AVAILABLE))
    unknown = _snapshot(6, None)
    assert not flow._is_summon_result(unknown)
    assert not flow._is_insufficient_gold(unknown)
    assert not flow._is_pet_full(unknown)
    assert not flow._is_clean_combine(unknown)


# ---------------------------------------------------------------------------
# Routing: every normal-path wait runs scoped with identical contracts.
# ---------------------------------------------------------------------------


def test_happy_path_routes_all_waits_through_summon_observer():
    main = MainObserver(_manage(1), [])
    summon = Observer(_manage(1), [
        _summon(2, STATUS_PET_EPIC_AVAILABLE),
        _result(4),
        _summon(6, STATUS_PET_EPIC_AVAILABLE),
    ])
    flow, actions, _, _ = _flow(main, summon)

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.daily_completed and result.summons_completed == 1
    assert actions.calls == [
        SelectPetSummon(), OpenEpicPetSummon(), OpenSingleEpicPet(),
        ClosePetSummonResult(),
    ]
    # Same contracts as the global waits: 6 s nav, 12 s outcome,
    # 6 s dismissal with outcome stability.
    assert summon.calls == [(6.0, 0.25), (12.0, 0.5), (6.0, 0.5)]
    assert main.observe_calls == 1


def test_insufficient_gold_dismisses_through_summon_observer():
    main = MainObserver(_manage(1), [])
    summon = Observer(_manage(1), [
        _summon(2, STATUS_PET_EPIC_UNAVAILABLE),
        _summon(4, STATUS_PET_EPIC_UNAVAILABLE,
                popup=POPUP_INSUFFICIENT_GOLD),
        _summon(6, STATUS_PET_EPIC_UNAVAILABLE),
    ])
    flow, actions, _, _ = _flow(main, summon)

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.daily_pending and not result.daily_completed
    assert actions.calls == [
        SelectPetSummon(), OpenPremiumPetSummon(), OpenSinglePremiumPet(),
        RejectInsufficientGold(),
    ]
    assert summon.calls == [(6.0, 0.25), (12.0, 0.5), (6.0, 0.25)]


def test_pet_full_relief_retry_routes_through_summon_observer():
    main = MainObserver(_manage(1), [])
    summon = Observer(_manage(1), [
        _summon(2, STATUS_PET_EPIC_AVAILABLE),
        _summon(4, STATUS_PET_EPIC_AVAILABLE,
                popup=POPUP_PET_INVENTORY_FULL),
        _combine(6),
        _summon(8, STATUS_PET_EPIC_AVAILABLE),
        _result(10),
        _summon(12, STATUS_PET_EPIC_AVAILABLE),
    ])
    relief_final = _combine(7)
    flow, actions, _, relief = _flow(
        main, summon,
        relief_results=[PetSummonSpaceReliefResult(
            PetSummonSpaceReliefOutcome.RELIEVED, relief_final)],
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.relief_attempted and result.retry_attempted
    assert result.summons_completed == 1
    assert actions.calls == [
        SelectPetSummon(), OpenEpicPetSummon(), OpenSingleEpicPet(),
        AcceptPetInventoryFull(), SelectPetSummon(),
        OpenEpicPetSummon(), OpenSingleEpicPet(), ClosePetSummonResult(),
    ]
    assert summon.calls == [
        (6.0, 0.25), (12.0, 0.5), (6.0, 0.25),
        (6.0, 0.25), (12.0, 0.5), (6.0, 0.5),
    ]
    assert len(relief.calls) == 1


def test_outcome_abort_fails_bounded_without_further_input():
    main = MainObserver(_manage(1), [])
    summon = Observer(_manage(1), [
        _summon(2, STATUS_PET_EPIC_AVAILABLE),
        _snapshot(4, SCREEN_MAILBOX),
    ])
    flow, actions, _, _ = _flow(main, summon)

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert "state_wait_failed" in result.error
    assert actions.calls == [
        SelectPetSummon(), OpenEpicPetSummon(), OpenSingleEpicPet(),
    ]
    assert summon.calls == [(6.0, 0.25), (12.0, 0.5)]


def test_navigation_abort_fails_before_any_summon_tap():
    main = MainObserver(_manage(1), [])
    summon = Observer(_manage(1), [_snapshot(2, SCREEN_MAILBOX)])
    flow, actions, _, _ = _flow(main, summon)

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert actions.calls == [SelectPetSummon()]
    assert summon.calls == [(6.0, 0.25)]


def test_summon_observer_defaults_to_main_observer():
    main = Observer(_manage(1), [])
    flow = SummonPetDailyFlow(main, Actions(), Events(), Relief())
    assert flow.summon_observer is main


def test_summon_observer_rejects_non_observer():
    main = Observer(_manage(1), [])
    with pytest.raises(ValueError):
        SummonPetDailyFlow(
            main, Actions(), Events(), Relief(), summon_observer=object()
        )


# ---------------------------------------------------------------------------
# Equivalence on real frames: scoped == global for every flow predicate.
# ---------------------------------------------------------------------------


def _wrap(frame_path, engine, resolver, *, sequence):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None, frame_path
    frame = FrameSnapshot(image=image, timestamp=float(sequence),
                          sequence=sequence)
    batch = engine.analyze(frame)
    return RuntimeSnapshot(
        frame=frame, observations=batch, state=resolver.resolve(batch),
        facts=_facts_from(batch),
        geometry=FrameGeometry.from_frame(image),
    )


def _predicates_of(flow, snapshot, epic=True):
    return (
        flow._is_clean_manage(snapshot),
        flow._is_summon_ready(snapshot),
        flow._is_summon_result(snapshot),
        flow._is_insufficient_gold(snapshot),
        flow._is_pet_full(snapshot),
        flow._is_selector(snapshot, epic),
        flow._is_summon_shell(snapshot),
        flow._is_clean_combine(snapshot),
    )


PETS_FRAMES = {
    "manage/01": "screencaps/semantic/pet_summon/manage/01.png",
    "manage/02": "screencaps/semantic/pet_summon/manage/02.png",
    "manage/03": "screencaps/semantic/pet_summon/manage/03.png",
    "summon-daily-active/01":
        "screencaps/semantic/pet_summon/summon-daily-active/01.png",
    "summon-daily-active/02":
        "screencaps/semantic/pet_summon/summon-daily-active/02.png",
    "summon-epic-available/01":
        "screencaps/semantic/pet_summon/summon-epic-available-premium-ticket/01.png",
    "epic-selector/01":
        "screencaps/semantic/pet_summon/epic-selector/01.png",
    "premium-gold-selector/01":
        "screencaps/semantic/pet_summon/premium-gold-selector/01.png",
    "premium-ticket-selector/01":
        "screencaps/semantic/pet_summon/premium-ticket-selector/01.png",
    "premium-insufficient-gold/01":
        "screencaps/semantic/pet_summon/premium-insufficient-gold/01.png",
    "pet-inventory-full/01":
        "screencaps/semantic/pet_summon/pet-inventory-full/01.png",
    "epic-result/01":
        "screencaps/semantic/pet_summon/epic-result/01.png",
    "premium-gold-result/01":
        "screencaps/semantic/pet_summon/premium-gold-result/01.png",
    "pet-combine/01":
        "screencaps/semantic/pet_summon/pet-combine/01.png",
    "pet-combine/02":
        "screencaps/semantic/pet_summon/pet-combine/02.png",
}

FOREIGN_FRAMES = {
    "lobby": "screencaps/semantic/lobby/20260823T025455_304538Z.png",
    "quick-menu-from-lobby":
        "screencaps/semantic/guild/quick-menu-from-lobby/01.png",
}


def test_scoped_matches_global_on_pets_frames():
    flow = _predicates()
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, PET_SUMMON_SCOPE)
    resolver = build_default_resolver()

    for name, path in PETS_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert (scoped_snapshot.state.status,
                scoped_snapshot.state.base_context) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context), name
        assert tuple(scoped_snapshot.state.overlays) == tuple(
            global_snapshot.state.overlays), name
        assert _predicates_of(flow, scoped_snapshot) == _predicates_of(
            flow, global_snapshot), name


def test_foreign_frames_never_fabricate_success_or_abort():
    flow = _predicates()
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, PET_SUMMON_SCOPE)
    resolver = build_default_resolver()

    for name, path in FOREIGN_FRAMES.items():
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert not flow._is_clean_manage(scoped_snapshot), name
        assert not flow._is_summon_ready(scoped_snapshot), name
        assert not flow._is_summon_result(scoped_snapshot), name
        assert not flow._is_insufficient_gold(scoped_snapshot), name
        assert not flow._is_pet_full(scoped_snapshot), name
        assert not flow._is_clean_combine(scoped_snapshot), name
        expected = lambda s: (flow._is_summon_result(s)
                              or flow._is_insufficient_gold(s)
                              or flow._is_pet_full(s))
        assert not flow._known_incompatible(
            scoped_snapshot, expected, flow._is_summon_ready), name


# ---------------------------------------------------------------------------
# Registry wiring with bounded fallback.
# ---------------------------------------------------------------------------


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
        self.pet_summon_space_relief = Relief()


def _real_observer():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0, sequence=1,
    )
    events = Events()
    return RuntimeObserver(
        FakeSource(frame), build_default_perception(ROOT),
        build_default_resolver(), events=events,
    ), events


def test_registry_wires_summon_observer_for_real_observer():
    observer, events = _real_observer()
    deps = FakeDependencies(observer, Actions(), events)

    scoped = _summon_pet_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 17
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert ("summon_pet_daily.summon_scope_active",
            {"detector_count": 17}) in [
        (name, fields) for name, fields in events.items
    ]


def test_registry_falls_back_to_main_without_scoped_observer():
    main = object()
    deps = FakeDependencies(object(), Actions(), Events())
    assert _summon_pet_observer_for(deps, main) is main


def test_registry_falls_back_when_scope_detectors_are_missing():
    observer, events = _real_observer()
    observer.perception = PerceptionEngine(detectors=())
    deps = FakeDependencies(observer, Actions(), events)

    assert _summon_pet_observer_for(deps, observer) is observer
    assert any(name == "summon_pet_daily.summon_scope_unavailable"
               for name, _ in events.items)


def test_registry_builds_summon_pet_with_summon_observer():
    observer, events = _real_observer()
    deps = FakeDependencies(observer, Actions(), events)

    flow = _build_summon_pet_daily(deps)

    assert isinstance(flow, SummonPetDailyFlow)
    assert flow.summon_observer is not observer
    assert len(flow.summon_observer.perception.detectors) == 17


def test_wiring_uses_generic_infra():
    import inspect

    import bot.flow_registry as registry
    import bot.summon_pet_daily_flow as flow_module

    source = inspect.getsource(registry._summon_pet_observer_for)
    assert "scoped_observer_for(" in source
    assert "PET_SUMMON_SCOPE" in source
    flow_source = inspect.getsource(flow_module.SummonPetDailyFlow)
    assert "summon_observer" in flow_source
