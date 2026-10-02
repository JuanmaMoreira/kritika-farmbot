"""The MW Keys adapter uses the scoped production pipeline and fresh rows."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.flow_registry import _build_productive_monster_wave
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_productive import ProductiveMonsterWaveFlow
from bot.ocr import RapidOcrEngine
from bot.perception import (
    TradingRowsDetector, TradingTabsDetector, build_default_perception,
    build_trading_navigation_perception,
)
from bot.runtime_observer import (
    RuntimeFacts, RuntimeObserver, RuntimeSnapshot, RuntimeWaitTimeout,
)
from bot.trading_key_facts_reader import (
    execute_productive_key_trade, read_fresh_key_facts,
)
from bot.keys_promotion_runtime import FreshKeyFacts
from bot.keys_promotion_runtime import KeysPromotionRuntime
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.semantic_actions import (
    CancelTradingTrade, ConfirmTradingTrade, SelectTradingMaximum,
    SelectTradingRow,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_keys import KeyTradeOperation, is_keys_ready
from bot.trading_operation import (
    TradeCostFact, TradeOutcome, TradePanelFact, TradeQuantity,
    TradeQuantityMode,
)
from bot.trading_row_facts import KEYS_SECTION, TradingRowFact, TradingRowReader
from bot.verified_transition import VerifiedTransition


ROOT = Path(__file__).resolve().parents[1]
# FailureEvidence rotates its diagnostic files. Keep this regression on the
# acquired native failure frame outside that retention pool.
FAILURE = ROOT / "artifacts/mw_stabilization/keys_failure_native.png"
KEYS = ROOT / "screencaps/semantic/trading-center/keys-top/01.png"
FULL_SIZE = (ROOT / "artifacts/acquisition-inventory-relief-chain"
             / "trading-keys-char2/20260910T002334_238388Z_01.png")
FULL_SIZE_SECOND = (ROOT / "artifacts/acquisition-inventory-relief-chain"
                    / "trading-keys-char2/20260910T002334_363497Z_02.png")
FULL_SIZE_THIRD = (ROOT / "artifacts/acquisition-inventory-relief-chain"
                   / "trading-keys-char2/20260910T002334_485307Z_03.png")
RECHECK = (ROOT / "artifacts/acquisition-inventory-relief-chain"
           / "trading-keys-recheck/20260909T224443_033566Z_01.png")
SCROLLED = (ROOT / "artifacts/acquisition-inventory-relief-chain"
            / "trading-keys-scrolled/20260909T220426_787048Z_01.png")


class Source:
    def __init__(self, image):
        self.image = image
        self.sequence = 0

    def get_frame(self):
        self.sequence += 1
        return FrameSnapshot(self.image, float(self.sequence), self.sequence)


class FrameSequenceSource:
    def __init__(self, images):
        self.images = tuple(images)
        self.sequence = 0

    def get_frame(self):
        self.sequence += 1
        image = self.images[(self.sequence - 1) % len(self.images)]
        return FrameSnapshot(image, float(self.sequence), self.sequence)


def _production_observer(image):
    return RuntimeObserver(
        Source(image), build_default_perception(ROOT),
        build_default_resolver(),
    )


def _full_size(image):
    reference = cv2.imread(str(FULL_SIZE))
    assert image is not None and reference is not None
    height, width = reference.shape[:2]
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_CUBIC)


def test_live_failure_frame_resolves_keys_only_in_scoped_productive_pipeline():
    # Normalize only the known four-pixel capture-height variant for the
    # native-size matcher; this test does not acquire OCR balance facts.
    image = _full_size(cv2.imread(str(FAILURE)))
    main = _production_observer(image)
    scoped = main.scoped(build_trading_navigation_perception(ROOT))
    assert not any(isinstance(detector, (TradingTabsDetector, TradingRowsDetector))
                   for detector in main.perception.detectors)
    assert sum(isinstance(detector, TradingTabsDetector)
               for detector in scoped.perception.detectors) == 1
    assert sum(isinstance(detector, TradingRowsDetector)
               for detector in scoped.perception.detectors) == 1
    assert not is_keys_ready(main.observe())
    snapshot = scoped.observe()
    assert snapshot.state.base_context == "screen.trading"
    names = {item.name for item in snapshot.observations.observations}
    assert {"landmark.trading_center_title", "indicator.trading_keys_active",
            "indicator.trading_keys_rows"} <= names
    assert is_keys_ready(snapshot)


def test_mw_builder_wires_scoped_keys_without_running_detectors_globally():
    class NoInput:
        def tap(self, *_args):
            raise AssertionError("builder must not send input")

    class NoCapture:
        def get_frame(self):
            raise AssertionError("builder must not capture")

    observer = RuntimeObserver(
        NoCapture(), build_default_perception(ROOT), build_default_resolver(),
    )
    actions = ActionExecutor(NoInput())
    inner = MonsterWaveFlow.__new__(MonsterWaveFlow)
    inner.activity = SimpleNamespace()
    inner.zone = object()
    dependencies = SimpleNamespace(
        observer=observer, actions=actions, events=None,
        cancel_requested=lambda: False,
        equipment_combine_relief=SimpleNamespace(run=lambda *_args: None),
        socket_relief=None,
    )
    flow = _build_productive_monster_wave(
        dependencies, VerifiedTransition(observer, actions, None),
        lambda: inner,
    )
    assert isinstance(flow, ProductiveMonsterWaveFlow)
    scoped = flow.route.keys_runtime.trading_runtime.observer
    assert scoped.source is observer.source
    # The resolver-complete MW scope excludes measured unrelated readers.
    from bot.perception import MONSTER_WAVE_BOARD_ACQUISITION_SCOPE
    specs = {d.spec.name for d in scoped.perception.detectors if hasattr(d, "spec")}
    assert MONSTER_WAVE_BOARD_ACQUISITION_SCOPE.spec_names <= specs
    assert len(scoped.perception.detectors) < len(observer.perception.detectors) + 2
    assert len([detector for detector in scoped.perception.detectors
                if isinstance(detector, TradingTabsDetector)]) == 1
    assert len([detector for detector in scoped.perception.detectors
                if isinstance(detector, TradingRowsDetector)]) == 1


def test_productive_keys_reader_consensus_from_original_trading_corpus():
    image = _full_size(cv2.imread(str(KEYS)))
    main = _production_observer(image)
    scoped = main.scoped(build_trading_navigation_perception(ROOT))
    facts = read_fresh_key_facts(
        scoped, TradingRowReader(RapidOcrEngine()),
        after_sequence=0, cancel_requested=lambda: False,
    )
    assert facts is not None
    assert facts.snapshot.sequence == facts.silver_fact.sequence == facts.gold_fact.sequence
    assert (facts.silver_fact.have, facts.silver_fact.need) == (5, 10)
    assert (facts.gold_fact.have, facts.gold_fact.need) == (9, 10)
    assert facts.snapshot.sequence > 1


@pytest.mark.parametrize("paths", (
    (FULL_SIZE, FULL_SIZE_SECOND),
    (FULL_SIZE_SECOND, FULL_SIZE_THIRD),
))
def test_native_keys_236_and_412_form_fresh_facts(paths):
    images = [cv2.imread(str(path)) for path in paths]
    assert all(image is not None for image in images)
    scoped = RuntimeObserver(
        FrameSequenceSource(images), build_default_perception(ROOT),
        build_default_resolver(),
    ).scoped(build_trading_navigation_perception(ROOT))
    facts = read_fresh_key_facts(
        scoped, TradingRowReader(RapidOcrEngine()),
        after_sequence=0, cancel_requested=lambda: False,
        max_samples=2,
    )
    assert facts is not None
    assert (facts.silver_fact.have, facts.silver_fact.need) == (236, 10)
    assert (facts.gold_fact.have, facts.gold_fact.need) == (412, 10)
    assert facts.snapshot.sequence == facts.silver_fact.sequence == facts.gold_fact.sequence
    assert facts.snapshot.sequence > 1


def test_native_keys_discordant_frames_yield_no_facts():
    images = [cv2.imread(str(path)) for path in (FULL_SIZE, RECHECK)]
    assert all(image is not None for image in images)
    scoped = RuntimeObserver(
        FrameSequenceSource(images), build_default_perception(ROOT),
        build_default_resolver(),
    ).scoped(build_trading_navigation_perception(ROOT))
    assert read_fresh_key_facts(
        scoped, TradingRowReader(RapidOcrEngine()),
        after_sequence=0, cancel_requested=lambda: False,
        max_samples=4,
    ) is None


def test_native_scrolled_keys_cannot_supply_causal_facts():
    image = cv2.imread(str(SCROLLED))
    assert image is not None
    scoped = _production_observer(image).scoped(
        build_trading_navigation_perception(ROOT)
    )
    assert read_fresh_key_facts(
        scoped, TradingRowReader(RapidOcrEngine()),
        after_sequence=0, cancel_requested=lambda: False,
        max_samples=2,
    ) is None


def test_partial_key_facts_never_reach_trade_callback():
    class Trading:
        def ensure_avatar_keys(self):
            return SimpleNamespace(
                status=FlowStatus.COMPLETED,
                final_snapshot=_keys_snapshot(1),
            )

        def leave_to_lobby(self):
            raise AssertionError("must not leave after incomplete facts")

    class Treasure:
        def enter_treasure_from_lobby(self):
            raise AssertionError("must not enter Treasure")

        def execute_gold_key_open(self, *_args, **_kwargs):
            raise AssertionError("must not open Gold")

    class QuickMenu:
        def treasure_to_trading(self):
            raise AssertionError("must not navigate")

    def trade(**_kwargs):
        raise AssertionError("incomplete facts authorized a trade")

    runtime = KeysPromotionRuntime(
        Trading(), Treasure(), QuickMenu(),
        read_key_facts=lambda _barrier: None,
        execute_key_trade=trade,
        drain_gold_keys=lambda: None,
    )
    result = runtime.run()
    assert result.status is FlowStatus.FAILED
    assert result.error == "fresh_key_facts_unavailable"
    assert not result.trade_attempts


def test_incomplete_key_rows_yield_no_facts(monkeypatch):
    import bot.trading_key_facts_reader as acquisition
    monkeypatch.setattr(acquisition, "read_key_samples", lambda *args: {})
    image = cv2.imread(str(FULL_SIZE))
    scoped = _production_observer(image).scoped(build_trading_navigation_perception(ROOT))
    assert read_fresh_key_facts(scoped, TradingRowReader(RapidOcrEngine()),
                              after_sequence=0, cancel_requested=lambda: False,
                              max_samples=2) is None


def _keys_snapshot(sequence, *, status=ResolutionStatus.RESOLVED,
                   timestamp=None):
    timestamp = float(sequence) if timestamp is None else float(timestamp)
    image = np.zeros((20, 40, 3), dtype=np.uint8)
    names = ("landmark.trading_center_title", "indicator.trading_keys_active",
             "indicator.trading_keys_rows")
    observations = ObservationBatch(
        sequence, timestamp, tuple(
            Observation(name, 1.0, ObservationSource.LOCAL_CV)
            for name in names
        ),
    )
    state = ResolvedState(
        status, sequence, timestamp,
        base_context="screen.trading" if status is ResolutionStatus.RESOLVED else None,
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence), observations, state,
        RuntimeFacts(), FrameGeometry.from_frame(image),
    )


def _facts(sequence, bronze, silver):
    return FreshKeyFacts(
        _keys_snapshot(sequence),
        TradingRowFact("silver_key", KEYS_SECTION, .43, bronze, 10, sequence),
        TradingRowFact("gold_key", KEYS_SECTION, .57, silver, 10, sequence),
    )


class ScriptedObserver:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.seen = []
        self.waits = []

    def wait_until(self, predicate, *, after_sequence, timeout, **_kwargs):
        self.waits.append((after_sequence, timeout))
        while self.snapshots:
            snapshot = self.snapshots.pop(0)
            assert snapshot.sequence > after_sequence
            self.seen.append(snapshot)
            if predicate(snapshot):
                return snapshot
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence, timeout=timeout,
            last_snapshot=self.seen[-1] if self.seen else None,
        )


class ScriptedPanel:
    def __init__(self, panels):
        self.panels = panels
        self.read_sequences = []

    def read_snapshot(self, snapshot, *, after_sequence):
        assert snapshot.sequence > after_sequence
        self.read_sequences.append(snapshot.sequence)
        return self.panels.get(snapshot.sequence)


class CollectActions:
    def __init__(self):
        self.intents = []
        self.sources = []

    def execute(self, intent, _geometry, *, events=None, source_sequence=None):
        self.intents.append(intent)
        self.sources.append(source_sequence)


def test_productive_adapter_verifies_effect_with_one_consumptive_intent():
    before = _facts(10, 40, 0)
    after = _facts(14, 0, 8)
    panels = {
        11: TradePanelFact("silver_key", 40, 10, (1, 20), sequence=11),
        12: TradePanelFact("silver_key", 40, 10, (4, 20), sequence=12),
    }
    actions = CollectActions()
    result = execute_productive_key_trade(
        operation=KeyTradeOperation.BRONZE_TO_SILVER,
        snapshot=before.snapshot, row_fact=before.silver_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=ScriptedObserver([_keys_snapshot(n) for n in (11, 12, 13)]),
        actions=actions, panel_reader=ScriptedPanel(panels),
        read_facts=lambda barrier: after if barrier < 14 else None,
        cancel_requested=lambda: False, clock=lambda: 11.5,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.after_fact == after.silver_fact
    assert [type(intent) for intent in actions.intents] == [
        SelectTradingRow, SelectTradingMaximum, ConfirmTradingTrade,
    ]
    assert actions.sources == [10, 11, 12]


def test_productive_max_waits_past_pre_dispatch_and_unchanged_frames():
    before = _facts(1046, 499, 412)
    after = _facts(1220, 499, 212)
    observer = ScriptedObserver([
        _keys_snapshot(1132, timestamp=335038.921),
        _keys_snapshot(1162, timestamp=335039.937),  # live: before dispatch
        _keys_snapshot(1170, timestamp=335040.100),  # post-dispatch 1/20
        _keys_snapshot(1190, timestamp=335040.300),  # eventual 20/20
        _keys_snapshot(1200, timestamp=335040.600),
    ])
    panel_reader = ScriptedPanel({
        1132: TradePanelFact("gold_key", 412, 10, (1, 20), sequence=1132),
        1162: TradePanelFact("gold_key", 412, 10, (1, 20), sequence=1162),
        1170: TradePanelFact("gold_key", 412, 10, (1, 20), sequence=1170),
        1190: TradePanelFact("gold_key", 412, 10, (20, 20), sequence=1190),
    })
    actions = CollectActions()

    result = execute_productive_key_trade(
        operation=KeyTradeOperation.SILVER_TO_GOLD,
        snapshot=before.snapshot, row_fact=before.gold_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=observer, actions=actions, panel_reader=panel_reader,
        read_facts=lambda barrier: after if barrier < 1220 else None,
        cancel_requested=lambda: False, clock=lambda: 335039.953,
    )

    assert result.outcome is TradeOutcome.SUCCESS
    assert [type(intent) for intent in actions.intents] == [
        SelectTradingRow, SelectTradingMaximum, ConfirmTradingTrade,
    ]
    assert actions.sources == [1046, 1132, 1190]
    assert [item.sequence for item in observer.seen] == [
        1132, 1162, 1170, 1190, 1200,
    ]
    assert panel_reader.read_sequences == [1132, 1170, 1190, 1200]
    assert result.inputs.count("tap_max") == 1
    assert result.inputs.count("tap_confirm") == 1


def test_productive_max_no_effect_only_after_bounded_wait():
    before = _facts(10, 40, 0)
    observer = ScriptedObserver([_keys_snapshot(n) for n in (11, 12, 13)])
    panel_reader = ScriptedPanel({
        n: TradePanelFact("silver_key", 40, 10, (1, 20), sequence=n)
        for n in (11, 12, 13)
    })
    actions = CollectActions()

    result = execute_productive_key_trade(
        operation=KeyTradeOperation.BRONZE_TO_SILVER,
        snapshot=before.snapshot, row_fact=before.silver_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=observer, actions=actions, panel_reader=panel_reader,
        read_facts=lambda _barrier: None, cancel_requested=lambda: False,
        clock=lambda: 11.5,
    )

    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "max_no_effect"
    assert observer.waits == [(10, 6.0), (11, 6.0)]
    assert [type(intent) for intent in actions.intents] == [
        SelectTradingRow, SelectTradingMaximum, CancelTradingTrade,
    ]
    assert result.inputs.count("tap_max") == 1
    assert "tap_confirm" not in result.inputs


def test_productive_max_rejects_pre_dispatch_max_and_inconclusive_frames():
    before = _facts(10, 40, 0)
    observer = ScriptedObserver([
        _keys_snapshot(11),
        _keys_snapshot(12, timestamp=11.4),  # 4/20, captured before MAX returned
        _keys_snapshot(13),  # unreadable
        _keys_snapshot(14),  # post-dispatch but short of target
    ])
    panel_reader = ScriptedPanel({
        11: TradePanelFact("silver_key", 40, 10, (1, 20), sequence=11),
        12: TradePanelFact("silver_key", 40, 10, (4, 20), sequence=12),
        14: TradePanelFact("silver_key", 40, 10, (2, 20), sequence=14),
    })
    actions = CollectActions()

    result = execute_productive_key_trade(
        operation=KeyTradeOperation.BRONZE_TO_SILVER,
        snapshot=before.snapshot, row_fact=before.silver_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=observer, actions=actions, panel_reader=panel_reader,
        read_facts=lambda _barrier: None, cancel_requested=lambda: False,
        clock=lambda: 11.5,
    )

    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "max_no_effect"
    assert panel_reader.read_sequences == [11, 13, 14]
    assert [type(intent) for intent in actions.intents] == [
        SelectTradingRow, SelectTradingMaximum, CancelTradingTrade,
    ]
    assert "tap_confirm" not in result.inputs


def test_productive_adapter_blocks_premium_cost_before_confirm():
    before = _facts(10, 40, 0)
    panel = TradePanelFact(
        "silver_key", 40, 10, (1, 20), sequence=11,
        costs=(TradeCostFact(kind="karats", amount=5),),
    )
    actions = CollectActions()
    result = execute_productive_key_trade(
        operation=KeyTradeOperation.BRONZE_TO_SILVER,
        snapshot=before.snapshot, row_fact=before.silver_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=ScriptedObserver([_keys_snapshot(11)]), actions=actions,
        panel_reader=ScriptedPanel({11: panel}),
        read_facts=lambda _barrier: None, cancel_requested=lambda: False,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert [type(intent) for intent in actions.intents] == [
        SelectTradingRow, CancelTradingTrade,
    ]


@pytest.mark.parametrize("boundary", (True, False))
def test_confirm_waits_for_effective_close_or_boundary_not_old_item_trade(boundary):
    before = _facts(10, 476, 189)
    after = _facts(17, 476, 9)
    panels = {
        11: TradePanelFact("gold_key", 189, 10, (1, 20), sequence=11),
        12: TradePanelFact("gold_key", 189, 10, (18, 20), sequence=12),
        13: TradePanelFact("gold_key", 189, 10, (18, 20), sequence=13),
        14: TradePanelFact("gold_key", 189, 10, (18, 20), sequence=14),
    }
    if boundary:
        panels[15] = TradePanelFact(None, None, None, None, sequence=15,
                                    shows_output_full=True)
    panel_reader = ScriptedPanel(panels)
    actions = CollectActions()
    clocks = iter((11.5, 13.5))
    barriers = []
    def read_facts(barrier):
        barriers.append(barrier)
        assert not boundary, "occluded rows must not be read after known Full"
        return after
    result = execute_productive_key_trade(
        operation=KeyTradeOperation.SILVER_TO_GOLD,
        snapshot=before.snapshot, row_fact=before.gold_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=ScriptedObserver([_keys_snapshot(n) for n in (11, 12, 13, 14, 15)]),
        actions=actions, panel_reader=panel_reader, read_facts=read_facts,
        cancel_requested=lambda: False, clock=lambda: next(clocks),
    )
    assert panel_reader.read_sequences == [11, 12, 14, 15]
    assert result.outcome is (TradeOutcome.OUTPUT_FULL if boundary else TradeOutcome.SUCCESS)
    assert barriers == ([] if boundary else [15])
    assert result.inputs.count("tap_confirm") == 1
    if boundary:
        assert result.reason == "output_full_on_confirm"


def test_confirm_transient_clean_unchanged_rows_wait_for_delayed_full():
    before = _facts(10, 476, 189)
    panels = {
        11: TradePanelFact("gold_key", 189, 10, (1, 20), sequence=11),
        12: TradePanelFact("gold_key", 189, 10, (18, 20), sequence=12),
        14: TradePanelFact(None, None, None, None, sequence=14,
                          shows_output_full=True),
    }
    actions = CollectActions()
    barriers = []
    def read_facts(barrier):
        barriers.append(barrier)
        return _facts(13, 476, 189)
    result = execute_productive_key_trade(
        operation=KeyTradeOperation.SILVER_TO_GOLD,
        snapshot=before.snapshot, row_fact=before.gold_fact,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=ScriptedObserver([_keys_snapshot(n) for n in (11, 12, 13, 14)]),
        actions=actions, panel_reader=ScriptedPanel(panels), read_facts=read_facts,
        cancel_requested=lambda: False, clock=lambda: 11.5,
    )
    assert result.outcome is TradeOutcome.OUTPUT_FULL
    assert result.reason == "output_full_on_confirm"
    assert result.inputs.count("tap_confirm") == 1
    assert barriers == [13]
