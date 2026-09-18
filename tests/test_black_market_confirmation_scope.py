"""Scoped-first Black Market confirmation + inventory-ack (Batch C1).

Two duplicate/reuse migrations, no new ScopeSpec:

1. empty-gold confirmation wait -> BLACK_MARKET_OPEN_SCOPE via a new
   ``confirmation_observer`` (same 7 detectors as ``open``: base
   landmark, Lobby landmark, three purchase-branch popups, GOLD/Purchased
   facts). The wait consumes exactly that vocabulary; Quick Menu is not
   accessible from Black Market and portal recovery stays global.
2. inventory-full acknowledgement -> ``slot_transition`` (SLOT_SCOPE, 6
   detectors) instead of the global transition. Same shape as the
   already-scoped insufficient-gold reject: popup -> clean Black Market.

Lobby precondition, close and purchase semantics are untouched.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.black_market_flow import (
    BlackMarketFlow,
    _has_incompatible_state,
    _is_clean_base,
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
    _black_market_confirmation_observer_for,
    _build_black_market,
)
from bot.inventory_full_transition import (
    is_clean_black_market,
    is_inventory_full_popup,
)
from bot.observations import ObservationBatch
from bot.perception import (
    BLACK_MARKET_OPEN_SCOPE,
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
from bot.semantic_actions import (
    AcknowledgeInventoryFull,
    CloseBlackMarket,
    OpenBlackMarket,
    SelectBlackMarketSlot,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(sequence, *, base=None, overlays=(), gold=(), purchased=()):
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


class ScriptedObserver:
    """Main-observer double: scripted observes and waits with call log."""

    def __init__(self, observes, waits):
        self.observes = list(observes)
        self.waits = list(waits)
        self.wait_calls = []

    def observe(self):
        return self.observes.pop(0)

    def wait_until(self, condition, *, after_sequence, timeout,
                   abort_if=None, stable_for=0.0, **kwargs):
        self.wait_calls.append((timeout, stable_for))
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item


class ConfirmationObserver(ScriptedObserver):
    """Scoped confirmation double: the empty-gold wait must land here."""


class Actions:
    def __init__(self):
        self.actions = []

    def execute(self, action, geometry):
        self.actions.append(action)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


class RecordingTransition:
    def __init__(self, inner):
        self.inner = inner
        self.names = []

    def execute(self, name, *args, **kwargs):
        self.names.append(name)
        return self.inner.execute(name, *args, **kwargs)


# ---------------------------------------------------------------------------
# Composition: the confirmation wait reuses the open scope exactly.
# ---------------------------------------------------------------------------


def test_confirmation_reuses_open_scope_detectors():
    source = build_default_perception(ROOT)
    scoped = select_detectors(source, BLACK_MARKET_OPEN_SCOPE)

    assert len(scoped.detectors) == 7
    assert len(source.detectors) == 97
    local_names = [
        detector.spec.name for detector in scoped.detectors
        if isinstance(detector, LocalCvDetector)
    ]
    assert "landmark.black_market_title" in local_names
    assert "landmark.lobby_trading_center_label" in local_names
    assert "landmark.purchase_confirmation_prompt" in local_names
    assert "landmark.insufficient_gold_prompt" in local_names
    assert "landmark.inventory_full_ok_button" in local_names
    expected_order = tuple(
        detector for detector in source.detectors
        if any(detector is selected for selected in scoped.detectors)
    )
    assert tuple(scoped.detectors) == expected_order


# ---------------------------------------------------------------------------
# Contract: expected / abort / UNKNOWN / AMBIGUOUS for the confirmation read.
# ---------------------------------------------------------------------------


def _confirm_expected(snapshot):
    return _is_clean_base(snapshot, SCREEN_BLACK_MARKET) and bool(
        snapshot.facts.gold_slots
    )


def test_confirmation_contract():
    empty = _snapshot(2, base=SCREEN_BLACK_MARKET)
    assert _is_clean_base(empty, SCREEN_BLACK_MARKET)
    assert not _confirm_expected(empty)
    assert not _has_incompatible_state(empty)

    gold = _snapshot(3, base=SCREEN_BLACK_MARKET, gold={2, 3})
    assert _confirm_expected(gold)
    assert not _has_incompatible_state(gold)

    popup = _snapshot(
        3, base=SCREEN_BLACK_MARKET,
        overlays={POPUP_PURCHASE_CONFIRMATION},
    )
    assert not _confirm_expected(popup)
    assert _has_incompatible_state(popup)

    foreign = _snapshot(3, base=SCREEN_LOBBY)
    assert not _confirm_expected(foreign)
    # The confirmation abort only watches AMBIGUOUS/overlays (same as
    # global): a clean foreign base stays pending, bounded by timeout.
    assert not _has_incompatible_state(foreign)

    unknown = _snapshot(3)
    assert not _confirm_expected(unknown)
    assert not _has_incompatible_state(unknown)

    ambiguous = RuntimeSnapshot(
        unknown.frame, unknown.observations,
        ResolvedState(
            ResolutionStatus.AMBIGUOUS, 3, 3.0, base_context=None,
            overlays=(),
            base_candidates=(SCREEN_LOBBY, SCREEN_BLACK_MARKET),
        ),
        unknown.facts, unknown.geometry,
    )
    assert not _confirm_expected(ambiguous)
    assert _has_incompatible_state(ambiguous)


# ---------------------------------------------------------------------------
# Equivalence on real frames: scoped open view == global for this read.
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


CONFIRM_FRAMES = {
    "clean": "screencaps/semantic/black_market_currency/20260825T204554_063659Z.png",
    "insufficient": "screencaps/semantic/black_market_currency/20260825T204903_103690Z.png",
    "lobby": "screencaps/semantic/lobby/20260823T025455_304538Z.png",
}


def test_scoped_matches_global_on_confirmation_frames():
    full = build_default_perception(ROOT)
    scoped = select_detectors(full, BLACK_MARKET_OPEN_SCOPE)
    resolver = build_default_resolver()

    for name, path in CONFIRM_FRAMES.items():
        global_snapshot = _wrap(path, full, resolver, sequence=1)
        scoped_snapshot = _wrap(path, scoped, resolver, sequence=1)
        assert (scoped_snapshot.state.status,
                scoped_snapshot.state.base_context) == (
            global_snapshot.state.status,
            global_snapshot.state.base_context), name
        assert tuple(scoped_snapshot.state.overlays) == tuple(
            global_snapshot.state.overlays), name
        assert _is_clean_base(
            scoped_snapshot, SCREEN_BLACK_MARKET) == _is_clean_base(
            global_snapshot, SCREEN_BLACK_MARKET), name
        assert _has_incompatible_state(
            scoped_snapshot) == _has_incompatible_state(
            global_snapshot), name
        assert scoped_snapshot.facts.gold_slots == (
            global_snapshot.facts.gold_slots), name


# ---------------------------------------------------------------------------
# Routing: the confirmation wait runs scoped; open/close stay on main.
# ---------------------------------------------------------------------------


def _run_confirmation_routed():
    main = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
    )
    confirmation = ConfirmationObserver(
        [],
        [_snapshot(3, base=SCREEN_BLACK_MARKET, gold={2, 3, 5, 8})],
    )
    actions, events = Actions(), Events()
    flow = BlackMarketFlow(
        main, actions, events, confirmation_observer=confirmation
    )
    result = flow.run(max_slot_attempts=0)
    return result, actions, events, main, confirmation


def test_empty_gold_confirmation_routes_through_confirmation_observer():
    result, actions, events, main, confirmation = _run_confirmation_routed()

    assert result.status is FlowStatus.COMPLETED
    assert result.initial_gold_slots == (2, 3, 5, 8)
    assert actions.actions == [OpenBlackMarket(), CloseBlackMarket()]
    # Same contract as the global wait: 2 s confirmation, no stability.
    assert confirmation.wait_calls == [(2.0, 0.0)]
    # Main keeps the open wait (5 s, 0.75 settle) and the close wait.
    assert main.wait_calls == [(5.0, 0.75), (5.0, 0.25)]


def test_empty_gold_timeout_still_declares_no_gold():
    main = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET),
            _snapshot(4, base=SCREEN_LOBBY),
        ],
    )
    confirmation = ConfirmationObserver(
        [],
        [RuntimeWaitTimeout(
            after_sequence=2, timeout=2.0,
            last_snapshot=_snapshot(3, base=SCREEN_BLACK_MARKET),
        )],
    )
    actions, events = Actions(), Events()
    flow = BlackMarketFlow(
        main, actions, events, confirmation_observer=confirmation
    )
    result = flow.run(max_slot_attempts=0)

    assert result.status is FlowStatus.COMPLETED
    assert result.initial_gold_slots == ()
    assert ("black_market.no_gold", {}) in events.items
    assert confirmation.wait_calls == [(2.0, 0.0)]


def test_confirmation_abort_fails_bounded_without_further_input():
    main = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [_snapshot(2, base=SCREEN_BLACK_MARKET)],
    )
    confirmation = ConfirmationObserver(
        [],
        [_snapshot(
            3, base=SCREEN_BLACK_MARKET,
            overlays={POPUP_INSUFFICIENT_GOLD},
        )],
    )
    actions = Actions()
    flow = BlackMarketFlow(
        main, actions, Events(), confirmation_observer=confirmation
    )
    result = flow.run(max_slot_attempts=0)

    assert result.status is FlowStatus.FAILED
    assert "initial_gold_read_failed" in result.error
    assert actions.actions == [OpenBlackMarket()]
    assert confirmation.wait_calls == [(2.0, 0.0)]


def test_confirmation_observer_defaults_to_main_observer():
    observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)], []
    )
    flow = BlackMarketFlow(observer, Actions(), Events())
    assert flow.confirmation_observer is observer


def test_confirmation_observer_rejects_non_observer():
    observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)], []
    )
    with pytest.raises(ValueError):
        BlackMarketFlow(
            observer, Actions(), Events(), confirmation_observer=object()
        )


# ---------------------------------------------------------------------------
# Routing: inventory-full acknowledgement runs on the slot transition.
# ---------------------------------------------------------------------------


def _run_ack_routed():
    observer = ScriptedObserver(
        [_snapshot(1, base=SCREEN_LOBBY)],
        [
            _snapshot(2, base=SCREEN_BLACK_MARKET, gold={1}),
            _snapshot(
                4, base=SCREEN_BLACK_MARKET,
                overlays={POPUP_INVENTORY_FULL},
            ),
            _snapshot(5, base=SCREEN_BLACK_MARKET),
            _snapshot(6, base=SCREEN_LOBBY),
        ],
    )
    actions, events = Actions(), Events()
    main = RecordingTransition(VerifiedTransition(observer, actions, events))
    slot = RecordingTransition(VerifiedTransition(observer, actions, events))
    flow = BlackMarketFlow(
        observer, actions, events,
        verified_transition=main, slot_transition=slot,
    )
    return flow.run(), actions.actions, main.names, slot.names


def test_inventory_ack_routes_through_slot_transition_only():
    result, actions, main_names, slot_names = _run_ack_routed()

    assert result.status is FlowStatus.COMPLETED
    assert result.inventory_full_count == 1
    assert AcknowledgeInventoryFull() in actions
    assert "black_market.acknowledge_inventory_full" in slot_names
    assert "black_market.acknowledge_inventory_full" not in main_names


def test_inventory_ack_predicates_hold_under_slot_scope():
    assert is_inventory_full_popup(_snapshot(
        4, base=SCREEN_BLACK_MARKET, overlays={POPUP_INVENTORY_FULL}))
    assert is_clean_black_market(
        _snapshot(5, base=SCREEN_BLACK_MARKET))
    assert not is_clean_black_market(_snapshot(
        4, base=SCREEN_BLACK_MARKET, overlays={POPUP_INVENTORY_FULL}))


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


def test_registry_wires_confirmation_observer_for_real_observer():
    observer, events = _real_observer()
    deps = FakeDependencies(observer, Actions(), events)

    scoped = _black_market_confirmation_observer_for(deps, observer)

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 7
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert ("black_market.gold_confirmation_scope_active",
            {"detector_count": 7}) in [
        (name, fields) for name, fields in events.items
    ]


def test_registry_falls_back_to_main_without_scoped_observer():
    main = object()
    deps = FakeDependencies(object(), Actions(), Events())
    assert _black_market_confirmation_observer_for(deps, main) is main


def test_registry_falls_back_when_scope_detectors_are_missing():
    observer, events = _real_observer()
    observer.perception = PerceptionEngine(detectors=())
    deps = FakeDependencies(observer, Actions(), events)

    assert _black_market_confirmation_observer_for(deps, observer) is observer
    assert any(name == "black_market.gold_confirmation_scope_unavailable"
               for name, _ in events.items)


def test_registry_builds_black_market_with_confirmation_observer():
    observer, events = _real_observer()
    deps = FakeDependencies(observer, Actions(), events)

    flow = _build_black_market(deps)

    assert isinstance(flow, BlackMarketFlow)
    assert flow.confirmation_observer is not observer
    assert len(flow.confirmation_observer.perception.detectors) == 7


def test_wiring_uses_generic_infra():
    import inspect

    import bot.flow_registry as registry

    source = inspect.getsource(
        registry._black_market_confirmation_observer_for)
    assert "scoped_observer_for(" in source
    assert "BLACK_MARKET_OPEN_SCOPE" in source
