"""Experimental purchase-scoped perception for ``accept_purchase``.

Covers only the post-Yes verification wait: detector subset composition,
resolution equivalence against the global engine on post-Yes frames,
transition routing inside the flow and the registry wiring with its
bounded fallback to the main transition.
"""

from pathlib import Path

import inspect

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.black_market_flow import (
    BlackMarketFlow,
    _has_incompatible_post_purchase,
    _is_purchase_confirmation,
    _is_verified_purchase,
)
from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_INSUFFICIENT_GOLD,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BLACK_MARKET,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.flow_contracts import FlowStatus
from bot.flow_registry import _build_black_market, _purchase_transition_for
from bot.observations import ObservationBatch
from bot.perception import (
    BLACK_MARKET_PURCHASE_SCOPE,
    BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES,
    black_market_purchase_perception,
    build_default_perception,
    select_detectors,
)
from bot.perception.black_market import (
    BlackMarketGoldDetector,
    BlackMarketPurchasedDetector,
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
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    CloseBlackMarket,
    OpenBlackMarket,
    SelectBlackMarketSlot,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]

POST_YES_FRAMES = {
    "purchase": (
        "screencaps/semantic/workbench/20260823T064721_367331Z-addb7117/"
        "frame-00000905.png"
    ),
    "purchase_alt": "screencaps/batch/done/20260402_164932_116901.png",
    "purchased": "screencaps/batch/done/20260402_164944_649947.png",
    "purchased_alt": "screencaps/batch/done/20260402_170101_208277.png",
    "insufficient": (
        "screencaps/semantic/black_market_currency/"
        "20260825T204903_103690Z.png"
    ),
    "inventory_full": (
        "screencaps/semantic/inventory_full/20260827T075832_116844Z/"
        "frame-01-seq-00000001.png"
    ),
    "clean": "screencaps/batch/done/20260402_164928_086696.png",
}


def _purchase_engine():
    return black_market_purchase_perception(build_default_perception(ROOT))


def test_purchase_scope_selects_exactly_the_six_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = black_market_purchase_perception(source)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 6
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES)
    assert sum(
        isinstance(item, BlackMarketGoldDetector)
        for item in scoped.detectors
    ) == 1
    assert sum(
        isinstance(item, BlackMarketPurchasedDetector)
        for item in scoped.detectors
    ) == 1
    expected_order = tuple(
        detector
        for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_purchase_scope_rejects_non_engine_source():
    with pytest.raises(ValueError):
        black_market_purchase_perception(object())


def test_purchase_scope_fails_fast_when_a_detector_is_missing():
    with pytest.raises(ValueError):
        black_market_purchase_perception(PerceptionEngine(detectors=()))


def _wrap(frame_path, engine, resolver, *, sequence):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None
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


def test_scoped_resolution_matches_global_on_post_yes_frames():
    full = build_default_perception(ROOT)
    scoped = _purchase_engine()
    resolver = build_default_resolver()

    for name, path in POST_YES_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert (
            scoped_snapshot.state.status,
            scoped_snapshot.state.base_context,
            tuple(scoped_snapshot.state.overlays),
        ) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context,
            tuple(global_snapshot.state.overlays),
        ), name
        assert scoped_snapshot.facts == global_snapshot.facts, name


def test_scoped_predicates_agree_with_global_on_post_yes_frames():
    full = build_default_perception(ROOT)
    scoped = _purchase_engine()
    resolver = build_default_resolver()

    for name, path in POST_YES_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        for slot in (0, 4, 7):
            assert _is_verified_purchase(
                scoped_snapshot, slot
            ) == _is_verified_purchase(global_snapshot, slot), (name, slot)
        assert _is_purchase_confirmation(
            scoped_snapshot
        ) == _is_purchase_confirmation(global_snapshot), name
        assert _has_incompatible_post_purchase(
            scoped_snapshot
        ) == _has_incompatible_post_purchase(global_snapshot), name


def test_unknown_frame_never_fabricates_purchase_success():
    full = build_default_perception(ROOT)
    scoped = _purchase_engine()
    resolver = build_default_resolver()
    path = "screencaps/batch/20260402_171606_055486.png"

    for engine in (full, scoped):
        snapshot = _wrap(path, engine, resolver, sequence=1)
        assert snapshot.state.status is ResolutionStatus.UNKNOWN
        assert not _is_verified_purchase(snapshot, 0)
        assert not _is_purchase_confirmation(snapshot)


class ScriptedObserver:
    def __init__(self, observes, waits):
        self.observes = list(observes)
        self.waits = list(waits)

    def observe(self):
        return self.observes.pop(0)

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
    ):
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item


class Actions:
    def __init__(self):
        self.actions = []

    def execute(self, action, geometry):
        self.actions.append(action)


class Events:
    def __init__(self):
        self.events = []

    def record(self, event, **fields):
        self.events.append((event, fields))


class RecordingTransition:
    def __init__(self, inner):
        self.inner = inner
        self.names = []

    def execute(self, name, *args, **kwargs):
        self.names.append(name)
        return self.inner.execute(name, *args, **kwargs)


def _snapshot(
    sequence,
    *,
    base=None,
    overlays=(),
    gold=(),
    purchased=(),
):
    status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    batch = ObservationBatch(sequence=sequence, timestamp=float(sequence))
    state = ResolvedState(
        status=status,
        sequence=sequence,
        timestamp=float(sequence),
        base_context=base,
        overlays=tuple(overlays),
        base_candidates=(),
    )
    return RuntimeSnapshot(
        frame=FrameSnapshot(
            image=np.zeros((1224, 2712, 3), dtype=np.uint8),
            sequence=sequence,
            timestamp=float(sequence),
        ),
        observations=batch,
        state=state,
        facts=RuntimeFacts(
            gold_slots=frozenset(gold),
            purchased_slots=frozenset(purchased),
        ),
        geometry=FrameGeometry(width=2712, height=1224),
    )


def _run_routed(observes, waits):
    observer = ScriptedObserver(observes, waits)
    actions = Actions()
    events = Events()
    main = RecordingTransition(VerifiedTransition(observer, actions, events))
    slot = RecordingTransition(VerifiedTransition(observer, actions, events))
    purchase = RecordingTransition(
        VerifiedTransition(observer, actions, events)
    )
    flow = BlackMarketFlow(
        observer,
        actions,
        events,
        verified_transition=main,
        slot_transition=slot,
        purchase_transition=purchase,
    )
    return flow.run(), actions.actions, main.names, slot.names, purchase.names


def test_accept_purchase_routes_through_purchase_transition_only():
    result, actions, main_names, slot_names, purchase_names = _run_routed(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={4}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET, purchased={4}),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.verified_purchases == (4,)
    assert actions == [
        OpenBlackMarket(),
        SelectBlackMarketSlot(4),
        AcceptPurchaseConfirmation(),
        CloseBlackMarket(),
    ]
    assert purchase_names == ["black_market.accept_purchase"]
    assert slot_names == ["black_market.select_slot"]
    assert main_names == ["black_market.open", "black_market.close"]


def test_accept_completes_during_grace_without_second_yes():
    persisting = _snapshot(
        5,
        base=SCREEN_BLACK_MARKET,
        overlays={POPUP_PURCHASE_CONFIRMATION},
    )
    result, actions, _, _, purchase_names = _run_routed(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={4}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            RuntimeWaitTimeout(
                after_sequence=4, timeout=5.0, last_snapshot=persisting
            ),
            _snapshot(6, base=SCREEN_BLACK_MARKET, purchased={4}),
            _snapshot(7, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.verified_purchases == (4,)
    assert actions.count(AcceptPurchaseConfirmation()) == 1
    assert purchase_names == ["black_market.accept_purchase"]


def test_unverified_purchase_aborts_without_extra_yes():
    result, actions, _, _, purchase_names = _run_routed(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(7, base=SCREEN_BLACK_MARKET)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={4}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=5.0,
                last_snapshot=_snapshot(5, base=SCREEN_BLACK_MARKET),
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=2.0,
                last_snapshot=_snapshot(6, base=SCREEN_BLACK_MARKET),
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert result.error == "purchase_unverified"
    assert actions == [
        OpenBlackMarket(),
        SelectBlackMarketSlot(4),
        AcceptPurchaseConfirmation(),
    ]
    assert purchase_names == ["black_market.accept_purchase"]


def test_unknown_post_yes_never_fabricates_success_or_retry():
    result, actions, _, _, purchase_names = _run_routed(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(9)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={4}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_PURCHASE_CONFIRMATION},
            ),
            RuntimeWaitTimeout(
                after_sequence=4,
                timeout=5.0,
                last_snapshot=_snapshot(5, base=SCREEN_BLACK_MARKET),
            ),
            RuntimeWaitTimeout(
                after_sequence=5,
                timeout=2.0,
                last_snapshot=_snapshot(6, base=SCREEN_BLACK_MARKET),
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert actions.count(AcceptPurchaseConfirmation()) == 1
    assert purchase_names == ["black_market.accept_purchase"]


def test_purchase_transition_defaults_to_main_transition():
    observer = ScriptedObserver([_snapshot(1, base=SCREEN_LOBBY)], [])
    flow = BlackMarketFlow(observer, Actions(), Events())
    assert flow.purchase_transition is flow.verified_transition
    assert flow.slot_transition is flow.verified_transition


def test_purchase_transition_rejects_non_executable():
    with pytest.raises(ValueError):
        BlackMarketFlow(
            ScriptedObserver([], []),
            Actions(),
            Events(),
            purchase_transition=object(),
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


def test_registry_wires_purchase_transition_for_real_observer():
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
    main = VerifiedTransition(observer, Actions(), events)
    deps = FakeDependencies(observer, Actions(), events)

    purchase = _purchase_transition_for(deps, main)

    assert isinstance(purchase, VerifiedTransition)
    assert purchase is not main
    assert len(purchase.observer.perception.detectors) == 6
    assert purchase.observer.source is observer.source
    assert purchase.observer.resolver is observer.resolver
    assert purchase.obstruction_recovery is main.obstruction_recovery
    assert (
        "black_market.purchase_scope_active",
        {"detector_count": 6},
    ) in [(name, fields) for name, fields in events.events]


def test_registry_falls_back_to_main_without_scoped_observer():
    main = object()
    deps = FakeDependencies(object(), Actions(), Events())
    assert _purchase_transition_for(deps, main) is main


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
    main = VerifiedTransition(observer, Actions(), events)
    deps = FakeDependencies(observer, Actions(), events)

    assert _purchase_transition_for(deps, main) is main
    assert any(
        name == "black_market.purchase_scope_unavailable"
        for name, _ in events.events
    )


def test_registry_builds_black_market_with_all_three_transitions():
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

    flow = _build_black_market(deps)

    assert isinstance(flow, BlackMarketFlow)
    assert flow.slot_transition is not flow.verified_transition
    assert flow.purchase_transition is not flow.verified_transition
    assert flow.purchase_transition is not flow.slot_transition
    assert len(flow.purchase_transition.observer.perception.detectors) == 6
    assert len(flow.slot_transition.observer.perception.detectors) == 6


def test_purchase_rehost_matches_legacy_builder_exactly():
    source = build_default_perception(ROOT)

    generic = select_detectors(source, BLACK_MARKET_PURCHASE_SCOPE)
    legacy = black_market_purchase_perception(source)

    assert len(generic.detectors) == 6
    assert tuple(generic.detectors) == tuple(legacy.detectors)


def test_generic_scope_matches_legacy_on_post_yes_frames():
    source = build_default_perception(ROOT)
    generic = select_detectors(source, BLACK_MARKET_PURCHASE_SCOPE)
    legacy = black_market_purchase_perception(source)
    resolver = build_default_resolver()

    for name, path in POST_YES_FRAMES.items():
        generic_snapshot = _wrap(path, generic, resolver, sequence=1)
        legacy_snapshot = _wrap(path, legacy, resolver, sequence=1)
        assert (
            generic_snapshot.observations
            == legacy_snapshot.observations
        ), name
        assert generic_snapshot.state == legacy_snapshot.state, name
        assert generic_snapshot.facts == legacy_snapshot.facts, name
        for slot in (0, 4, 7):
            assert _is_verified_purchase(
                generic_snapshot, slot
            ) == _is_verified_purchase(legacy_snapshot, slot), (name, slot)
        assert _is_purchase_confirmation(
            generic_snapshot
        ) == _is_purchase_confirmation(legacy_snapshot), name
        assert _has_incompatible_post_purchase(
            generic_snapshot
        ) == _has_incompatible_post_purchase(legacy_snapshot), name


def test_purchase_uses_generic_infra():
    source_text = inspect.getsource(_purchase_transition_for)
    assert "scoped_transition_for(" in source_text
    assert "_scoped_transition_for(" not in source_text
    assert "black_market_purchase_perception" not in source_text
