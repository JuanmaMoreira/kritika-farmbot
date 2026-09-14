"""Experimental slot-scoped perception for ``black_market.select_slot``.

Covers only the select_slot wait: detector subset composition, resolution
equivalence against the global engine on curated frames, transition routing
inside the flow, the ``RuntimeObserver.scoped`` seam and the registry wiring
with its bounded fallback to the main transition.
"""

from pathlib import Path

import inspect

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.black_market_flow import (
    BlackMarketFlow,
    _has_incompatible_branch,
    _is_actionable_gold_slot,
    _is_expected_purchase_branch,
)
from bot.capture import FrameSnapshot
from bot.catalog import (
    POPUP_INSUFFICIENT_GOLD,
    POPUP_INVENTORY_FULL,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BLACK_MARKET,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.flow_contracts import FlowStatus
from bot.flow_registry import (
    _build_black_market,
    _purchase_transition_for,
    _slot_transition_for,
)
from bot.observations import ObservationBatch
from bot.perception import (
    BLACK_MARKET_SLOT_SCOPE,
    BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES,
    black_market_slot_perception,
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

SELECT_BRANCH_FRAMES = {
    "clean": "screencaps/batch/done/20260402_164928_086696.png",
    "purchase": (
        "screencaps/semantic/workbench/20260823T064721_367331Z-addb7117/"
        "frame-00000905.png"
    ),
    "purchase_alt": "screencaps/batch/done/20260402_164932_116901.png",
    "insufficient": (
        "screencaps/semantic/black_market_currency/"
        "20260825T204903_103690Z.png"
    ),
    "inventory_full": (
        "screencaps/semantic/inventory_full/20260827T075832_116844Z/"
        "frame-01-seq-00000001.png"
    ),
}


def _scoped_engine():
    return black_market_slot_perception(build_default_perception(ROOT))


def test_slot_scope_selects_exactly_the_six_needed_detectors():
    source = build_default_perception(ROOT)
    scoped = black_market_slot_perception(source)

    assert isinstance(scoped, PerceptionEngine)
    assert len(scoped.detectors) == 6
    assert len(source.detectors) > len(scoped.detectors)
    local_names = [
        detector.spec.name
        for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert set(local_names) == set(BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES)
    assert sum(
        isinstance(item, BlackMarketGoldDetector)
        for item in scoped.detectors
    ) == 1
    assert sum(
        isinstance(item, BlackMarketPurchasedDetector)
        for item in scoped.detectors
    ) == 1
    # Same instances in source order: calibration and assets are unchanged.
    expected_order = tuple(
        detector
        for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


def test_slot_scope_rejects_non_engine_source():
    with pytest.raises(ValueError):
        black_market_slot_perception(object())


def test_slot_scope_fails_fast_when_a_detector_is_missing():
    with pytest.raises(ValueError):
        black_market_slot_perception(PerceptionEngine(detectors=()))


def _resolve(frame_path, engine, resolver):
    image = cv2.imread(str(ROOT / frame_path))
    assert image is not None
    snapshot = FrameSnapshot(image=image, timestamp=1.0, sequence=1)
    batch = engine.analyze(snapshot)
    return resolver.resolve(batch), batch


def test_scoped_resolution_matches_global_on_select_branches():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in SELECT_BRANCH_FRAMES.items():
        global_state, global_batch = _resolve(path, full, resolver)
        scoped_state, scoped_batch = _resolve(path, scoped, resolver)
        assert (scoped_state.status, scoped_state.base_context) == (
            global_state.status,
            global_state.base_context,
        ), name
        assert tuple(scoped_state.overlays) == tuple(
            global_state.overlays
        ), name
        assert _snapshot_facts(scoped_batch) == _snapshot_facts(
            global_batch
        ), name


def _snapshot_facts(batch):
    return _facts_from(batch)


def test_scoped_predicates_agree_with_global_on_select_branches():
    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()

    for name, path in SELECT_BRANCH_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert _is_expected_purchase_branch(
            scoped_snapshot
        ) == _is_expected_purchase_branch(global_snapshot), name
        assert _has_incompatible_branch(
            scoped_snapshot
        ) == _has_incompatible_branch(global_snapshot), name
        assert _is_actionable_gold_slot(
            scoped_snapshot, 0
        ) == _is_actionable_gold_slot(global_snapshot, 0), name


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
        facts=_snapshot_facts(batch),
        geometry=FrameGeometry.from_frame(image),
    )


def test_foreign_screen_divergence_stays_bounded_without_input():
    """A non-BM screen resolves UNKNOWN under the scope.

    Global perception would abort fast (RESOLVED lobby); the scope keeps
    waiting instead. Both paths stay bounded, authorize no input and fail
    the flow the same way, so no fallback machinery is warranted.
    """

    full = build_default_perception(ROOT)
    scoped = _scoped_engine()
    resolver = build_default_resolver()
    path = "screencaps/batch/done/20260402_164402_024447.png"

    global_snapshot = _wrap(path, full, resolver, sequence=1)
    scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
    assert global_snapshot.state.base_context == SCREEN_LOBBY
    assert scoped_snapshot.state.status is ResolutionStatus.UNKNOWN
    assert not _is_expected_purchase_branch(scoped_snapshot)
    assert not _has_incompatible_branch(scoped_snapshot)


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
    flow = BlackMarketFlow(
        observer,
        actions,
        events,
        verified_transition=main,
        slot_transition=slot,
    )
    return flow.run(), actions.actions, main.names, slot.names


def test_select_slot_routes_through_slot_transition_only():
    result, actions, main_names, slot_names = _run_routed(
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
    assert slot_names == ["black_market.select_slot"]
    assert main_names == [
        "black_market.open",
        "black_market.accept_purchase",
        "black_market.close",
    ]


def test_insufficient_gold_branch_keeps_routing_and_outcome():
    result, actions, main_names, slot_names = _run_routed(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={1}),
            _snapshot(
                4,
                base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INSUFFICIENT_GOLD},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET, gold=set()),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.insufficient_gold_count == 1
    assert SelectBlackMarketSlot(1) in actions
    # Batch B1: the insufficient-gold popup vocabulary is exactly the slot
    # scope, so reject runs on the slot transition instead of the global one.
    assert slot_names == [
        "black_market.select_slot",
        "black_market.reject_insufficient_gold",
    ]
    assert "black_market.reject_insufficient_gold" not in main_names


def test_unknown_branch_aborts_bounded_without_further_input():
    result, actions, _, slot_names = _run_routed(
        [_snapshot(1, base=SCREEN_LOBBY), _snapshot(5)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={0}),
            RuntimeWaitTimeout(
                after_sequence=2,
                timeout=1.0,
                last_snapshot=_snapshot(
                    3, base=SCREEN_BLACK_MARKET, gold={0}
                ),
            ),
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=2.0,
                last_snapshot=_snapshot(
                    4, base=SCREEN_BLACK_MARKET, gold={0}
                ),
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert "retry_guard_rejected" in result.error
    assert actions == [OpenBlackMarket(), SelectBlackMarketSlot(0)]
    assert slot_names == ["black_market.select_slot"]


def test_slot_transition_defaults_to_main_transition():
    observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)], []
    )
    flow = BlackMarketFlow(observer, Actions(), Events())
    assert flow.slot_transition is flow.verified_transition
    assert flow.open_transition is flow.verified_transition


def test_slot_transition_rejects_non_executable():
    with pytest.raises(ValueError):
        BlackMarketFlow(
            ScriptedObserver([], []),
            Actions(),
            Events(),
            slot_transition=object(),
        )
    with pytest.raises(ValueError):
        BlackMarketFlow(
            ScriptedObserver([], []),
            Actions(),
            Events(),
            open_transition=object(),
        )


class FakeSource:
    def __init__(self, frame):
        self.frame = frame
        self.calls = 0

    def get_frame(self):
        self.calls += 1
        return self.frame


class CountingPerception:
    def __init__(self):
        self.calls = 0

    def analyze(self, snapshot):
        self.calls += 1
        return ObservationBatch(
            sequence=snapshot.sequence, timestamp=snapshot.timestamp
        )


def test_scoped_observer_shares_source_and_narrows_perception():
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=3.0,
        sequence=7,
    )
    events = Events()
    consumed = []
    main = RuntimeObserver(
        FakeSource(frame),
        CountingPerception(),
        build_default_resolver(),
        events=events,
        snapshot_consumer=consumed.append,
    )
    narrow = CountingPerception()
    scoped = main.scoped(narrow)

    assert scoped.source is main.source
    assert scoped.resolver is main.resolver
    assert scoped.events is main.events
    assert scoped.poll_interval == main.poll_interval
    snapshot = scoped.observe()

    assert snapshot.sequence == 7
    assert narrow.calls == 1
    assert consumed and consumed[-1].sequence == 7


def test_scoped_observer_rejects_non_perception():
    main = RuntimeObserver(
        FakeSource(
            FrameSnapshot(
                image=np.zeros((8, 8, 3), dtype=np.uint8),
                timestamp=1.0,
                sequence=1,
            )
        ),
        CountingPerception(),
        build_default_resolver(),
    )
    with pytest.raises(ValueError):
        main.scoped(object())


class FakeDependencies:
    def __init__(self, observer, actions, events):
        self.observer = observer
        self.actions = actions
        self.events = events
        self.cancel_requested = lambda: False


def test_registry_falls_back_to_main_without_scoped_observer():
    main = object()
    deps = FakeDependencies(object(), Actions(), Events())
    assert _slot_transition_for(deps, main) is main


def test_registry_wires_scoped_transition_for_real_observer():
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

    slot = _slot_transition_for(deps, main)

    assert isinstance(slot, VerifiedTransition)
    assert slot is not main
    assert len(slot.observer.perception.detectors) == 6
    assert slot.observer.source is observer.source
    assert slot.observer.resolver is observer.resolver
    assert slot.obstruction_recovery is main.obstruction_recovery
    assert ("black_market.slot_scope_active", {"detector_count": 6}) in [
        (name, fields) for name, fields in events.events
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
    main = VerifiedTransition(observer, Actions(), events)
    deps = FakeDependencies(observer, Actions(), events)

    assert _slot_transition_for(deps, main) is main
    assert any(
        name == "black_market.slot_scope_unavailable"
        for name, _ in events.events
    )


def test_registry_builds_black_market_with_slot_transition():
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
    assert len(flow.slot_transition.observer.perception.detectors) == 6


def test_slot_rehost_matches_legacy_builder_exactly():
    source = build_default_perception(ROOT)

    generic = select_detectors(source, BLACK_MARKET_SLOT_SCOPE)
    legacy = black_market_slot_perception(source)

    assert len(generic.detectors) == 6
    assert tuple(generic.detectors) == tuple(legacy.detectors)


def test_generic_scope_matches_legacy_on_select_branch_frames():
    source = build_default_perception(ROOT)
    generic = select_detectors(source, BLACK_MARKET_SLOT_SCOPE)
    legacy = black_market_slot_perception(source)
    resolver = build_default_resolver()

    for name, path in SELECT_BRANCH_FRAMES.items():
        generic_state, generic_batch = _resolve(path, generic, resolver)
        legacy_state, legacy_batch = _resolve(path, legacy, resolver)
        assert generic_batch == legacy_batch, name
        assert generic_state == legacy_state, name
        generic_snapshot = _wrap(path, generic, resolver, sequence=1)
        legacy_snapshot = _wrap(path, legacy, resolver, sequence=1)
        assert _is_expected_purchase_branch(
            generic_snapshot
        ) == _is_expected_purchase_branch(legacy_snapshot), name
        assert _has_incompatible_branch(
            generic_snapshot
        ) == _has_incompatible_branch(legacy_snapshot), name
        assert _is_actionable_gold_slot(
            generic_snapshot, 0
        ) == _is_actionable_gold_slot(legacy_snapshot, 0), name


def test_both_black_market_transitions_use_generic_infra():
    for wiring in (_slot_transition_for, _purchase_transition_for):
        source_text = inspect.getsource(wiring)
        assert "scoped_transition_for(" in source_text
        assert "_scoped_transition_for(" not in source_text
    assert "black_market_slot_perception" not in inspect.getsource(
        _slot_transition_for
    )
    assert "black_market_purchase_perception" not in inspect.getsource(
        _purchase_transition_for
    )

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

    recorded = [(name, fields) for name, fields in events.events]
    assert ("black_market.slot_scope_active", {"detector_count": 6}) in recorded
    assert (
        "black_market.purchase_scope_active",
        {"detector_count": 6},
    ) in recorded
