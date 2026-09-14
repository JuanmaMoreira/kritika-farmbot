"""Generic contract tests for scoped perception infrastructure.

Covers only the new additive seam (``ScopeSpec``, ``select_detectors``,
``scoped_observer_for``, ``scoped_transition_for``). No productive path
uses this infrastructure yet; the four promoted scopes stay authoritative
and are used here solely as representability fixtures.
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.flow_registry import scoped_observer_for, scoped_transition_for
from bot.perception import (
    BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES,
    BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES,
    DAILY_CLAIM_SCOPE_SPEC_NAMES,
    MAILBOX_CLAIM_SCOPE_SPEC_NAMES,
    ScopeSpec,
    black_market_purchase_perception,
    black_market_slot_perception,
    build_default_perception,
    daily_claim_perception,
    mailbox_claim_perception,
    select_detectors,
)
from bot.perception.black_market import (
    BlackMarketGoldDetector,
    BlackMarketPurchasedDetector,
)
from bot.perception.daily_quests import DailyQuestsProgressRewardDetector
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector
from bot.perception.mailbox import MailboxClaimProcessingDetector
from bot.runtime_observer import RuntimeObserver
from bot.verified_transition import VerifiedTransition

ROOT = Path(__file__).resolve().parents[1]


class FakeLocalCv:
    """Minimal LocalCv-shaped detector reusing a real spec name."""

    def __init__(self, name):
        self.spec = SimpleNamespace(name=name)

    def detect(self, frame):
        return ()


class FakeSpecialized:
    def detect(self, frame):
        return ()


class OtherSpecialized:
    def detect(self, frame):
        return ()


def _fake_engine():
    first = FakeLocalCv("landmark.first_title")
    second = FakeLocalCv("landmark.second_prompt")
    third = FakeLocalCv("landmark.third_button")
    specialized = FakeSpecialized()
    return (
        PerceptionEngine(
            detectors=(first, second, third, specialized)
        ),
        (first, second, third, specialized),
    )


def test_scope_spec_is_frozen():
    scope = ScopeSpec(
        name="probe",
        spec_names=frozenset({"landmark.first_title"}),
        specialized_types=(FakeSpecialized,),
    )
    with pytest.raises(FrozenInstanceError):
        scope.name = "other"  # type: ignore[misc]


def test_scope_spec_normalizes_collections():
    scope = ScopeSpec(
        name="probe",
        spec_names=["landmark.first_title"],
        specialized_types=[FakeSpecialized],
    )
    assert scope.spec_names == frozenset({"landmark.first_title"})
    assert scope.specialized_types == (FakeSpecialized,)


def test_scope_spec_rejects_invalid_declarations():
    with pytest.raises(ValueError):
        ScopeSpec(name="", spec_names=frozenset({"a.b"}))
    with pytest.raises(ValueError):
        ScopeSpec(name="probe", spec_names="landmark.first_title")
    with pytest.raises(ValueError):
        ScopeSpec(name="probe", spec_names=frozenset({""}))
    with pytest.raises(ValueError):
        ScopeSpec(name="probe", spec_names=["a.b", "a.b"])
    with pytest.raises(ValueError):
        ScopeSpec(
            name="probe",
            spec_names=frozenset({"a.b"}),
            specialized_types=(object(),),
        )
    with pytest.raises(ValueError):
        ScopeSpec(
            name="probe",
            spec_names=frozenset({"a.b"}),
            specialized_types=(FakeSpecialized, FakeSpecialized),
        )
    with pytest.raises(ValueError):
        ScopeSpec(name="probe", spec_names=frozenset())


def test_selector_preserves_order_and_identity():
    source, (first, second, third, specialized) = _fake_engine()
    before = source.detectors
    scope = ScopeSpec(
        name="probe",
        spec_names=frozenset(
            {"landmark.third_button", "landmark.first_title"}
        ),
        specialized_types=(FakeSpecialized,),
    )

    scoped = select_detectors(source, scope)

    assert isinstance(scoped, PerceptionEngine)
    assert tuple(scoped.detectors) == (first, third, specialized)
    assert all(
        selected is expected
        for selected, expected in zip(
            scoped.detectors, (first, third, specialized)
        )
    )
    assert second not in scoped.detectors
    # Source engine is never mutated.
    assert source.detectors == before


def test_selector_supports_local_only_and_specialized_only_scopes():
    source, (first, second, third, specialized) = _fake_engine()

    local_only = select_detectors(
        source,
        ScopeSpec(
            name="local",
            spec_names=frozenset({"landmark.second_prompt"}),
        ),
    )
    assert tuple(local_only.detectors) == (second,)

    specialized_only = select_detectors(
        source,
        ScopeSpec(
            name="specialized",
            spec_names=frozenset(),
            specialized_types=(FakeSpecialized,),
        ),
    )
    assert tuple(specialized_only.detectors) == (specialized,)


def test_selector_fails_fast_on_missing_detectors():
    source, _ = _fake_engine()
    with pytest.raises(ValueError):
        select_detectors(
            source,
            ScopeSpec(
                name="probe",
                spec_names=frozenset({"landmark.absent_title"}),
                specialized_types=(FakeSpecialized,),
            ),
        )
    with pytest.raises(ValueError):
        select_detectors(
            source,
            ScopeSpec(
                name="probe",
                spec_names=frozenset({"landmark.first_title"}),
                specialized_types=(OtherSpecialized,),
            ),
        )
    with pytest.raises(ValueError):
        select_detectors(object(), ScopeSpec(name="p", spec_names={"a.b"}))
    with pytest.raises(ValueError):
        select_detectors(source, object())


def _golden_scopes():
    return (
        (
            "slot",
            ScopeSpec(
                name="slot",
                spec_names=BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES,
                specialized_types=(
                    BlackMarketGoldDetector,
                    BlackMarketPurchasedDetector,
                ),
            ),
            black_market_slot_perception,
            6,
        ),
        (
            "purchase",
            ScopeSpec(
                name="purchase",
                spec_names=BLACK_MARKET_PURCHASE_SCOPE_SPEC_NAMES,
                specialized_types=(
                    BlackMarketGoldDetector,
                    BlackMarketPurchasedDetector,
                ),
            ),
            black_market_purchase_perception,
            6,
        ),
        (
            "daily",
            ScopeSpec(
                name="daily",
                spec_names=DAILY_CLAIM_SCOPE_SPEC_NAMES,
                specialized_types=(DailyQuestsProgressRewardDetector,),
            ),
            daily_claim_perception,
            4,
        ),
        (
            "mailbox",
            ScopeSpec(
                name="mailbox",
                spec_names=MAILBOX_CLAIM_SCOPE_SPEC_NAMES,
                specialized_types=(MailboxClaimProcessingDetector,),
            ),
            mailbox_claim_perception,
            5,
        ),
    )


@pytest.mark.parametrize(
    "label,scope,legacy_builder,expected_count",
    _golden_scopes(),
)
def test_selector_represents_each_promoted_scope(
    label, scope, legacy_builder, expected_count
):
    source = build_default_perception(ROOT)
    source_count = len(source.detectors)

    scoped = select_detectors(source, scope)
    legacy = legacy_builder(source)

    assert len(scoped.detectors) == expected_count, label
    # Same instances in source order as the promoted builder.
    assert tuple(scoped.detectors) == tuple(legacy.detectors), label
    assert len(source.detectors) == source_count


class FakeSource:
    def __init__(self, frame):
        self.frame = frame

    def get_frame(self):
        return self.frame


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


class Actions:
    def execute(self, action, geometry):
        pass


class Recovery:
    def attempt(self, snapshot, expected):
        return None


def _real_observer(events, *, detectors="default"):
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    perception = (
        build_default_perception(ROOT)
        if detectors == "default"
        else PerceptionEngine(detectors=())
    )
    return RuntimeObserver(
        FakeSource(frame),
        perception,
        build_default_resolver(),
        events=events,
    )


def _deps(observer, events, *, actions=None):
    return SimpleNamespace(
        observer=observer,
        actions=actions if actions is not None else Actions(),
        events=events,
        cancel_requested=lambda: False,
    )


def _slot_scope():
    return ScopeSpec(
        name="slot",
        spec_names=BLACK_MARKET_SLOT_SCOPE_SPEC_NAMES,
        specialized_types=(
            BlackMarketGoldDetector,
            BlackMarketPurchasedDetector,
        ),
    )


def test_scoped_observer_success_shares_runtime_and_records_active():
    events = Events()
    consumed = []
    frame = FrameSnapshot(
        image=np.zeros((8, 8, 3), dtype=np.uint8),
        timestamp=1.0,
        sequence=1,
    )
    observer = RuntimeObserver(
        FakeSource(frame),
        build_default_perception(ROOT),
        build_default_resolver(),
        events=events,
        snapshot_consumer=consumed.append,
    )
    deps = _deps(observer, events)

    scoped = scoped_observer_for(
        deps,
        observer,
        scope=_slot_scope(),
        active_event="probe.scope_active",
        unavailable_event="probe.scope_unavailable",
    )

    assert isinstance(scoped, RuntimeObserver)
    assert scoped is not observer
    assert len(scoped.perception.detectors) == 6
    assert scoped.source is observer.source
    assert scoped.resolver is observer.resolver
    assert scoped.events is observer.events
    assert scoped.poll_interval == observer.poll_interval
    assert ("probe.scope_active", {"detector_count": 6}) in [
        (name, fields) for name, fields in events.items
    ]


def test_scoped_observer_falls_back_without_scoped_seam():
    events = Events()
    main = object()
    deps = _deps(object(), events)

    assert (
        scoped_observer_for(
            deps,
            main,
            scope=_slot_scope(),
            active_event="probe.scope_active",
            unavailable_event="probe.scope_unavailable",
        )
        is main
    )
    assert events.items == []


def test_scoped_observer_falls_back_on_missing_dependency():
    events = Events()
    observer = _real_observer(events, detectors="empty")
    deps = _deps(observer, events)

    assert (
        scoped_observer_for(
            deps,
            observer,
            scope=_slot_scope(),
            active_event="probe.scope_active",
            unavailable_event="probe.scope_unavailable",
        )
        is observer
    )
    assert any(
        name == "probe.scope_unavailable" for name, _ in events.items
    )


def test_scoped_transition_reuses_main_contract_with_scoped_observer():
    events = Events()
    observer = _real_observer(events)
    actions = Actions()
    recovery = Recovery()
    main = VerifiedTransition(observer, actions, events, recovery)
    deps = _deps(observer, events, actions=actions)

    scoped = scoped_transition_for(
        deps,
        main,
        scope=_slot_scope(),
        active_event="probe.scope_active",
        unavailable_event="probe.scope_unavailable",
    )

    assert isinstance(scoped, VerifiedTransition)
    assert scoped is not main
    assert scoped.actions is actions
    assert scoped.events is events
    assert scoped.obstruction_recovery is recovery
    assert isinstance(scoped.observer, RuntimeObserver)
    assert len(scoped.observer.perception.detectors) == 6
    assert ("probe.scope_active", {"detector_count": 6}) in [
        (name, fields) for name, fields in events.items
    ]


def test_scoped_transition_falls_back_to_main_transition():
    events = Events()
    observer = _real_observer(events, detectors="empty")
    main = VerifiedTransition(observer, Actions(), events)
    deps = _deps(observer, events)

    assert (
        scoped_transition_for(
            deps,
            main,
            scope=_slot_scope(),
            active_event="probe.scope_active",
            unavailable_event="probe.scope_unavailable",
        )
        is main
    )
    assert any(
        name == "probe.scope_unavailable" for name, _ in events.items
    )


def test_scoped_transition_falls_back_without_scoped_seam():
    events = Events()
    main = VerifiedTransition(
        _real_observer(events), Actions(), events
    )
    deps = _deps(object(), events)

    assert (
        scoped_transition_for(
            deps,
            main,
            scope=_slot_scope(),
            active_event="probe.scope_active",
            unavailable_event="probe.scope_unavailable",
        )
        is main
    )
    assert events.items == []
