"""C2c replay of curated C4/C5/C6b Trading frames, without device input."""

from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.keys_promotion import PendingCausalOperation
from bot.keys_promotion_runtime import acknowledge_gold_full_boundary
from bot.ocr import RapidOcrEngine
from bot.perception import build_trading_perception
from bot.perception.trading_center import row_bands
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_operation import (
    TradePanelTargets, TradePreconditionContext, TradeQuantity,
    TradeQuantityMode, TradeOutcome, TradeRequest, execute_verified_trade,
)
from bot.trading_panel_reader import TradingPanelReader
from bot.trading_keys import KeyTradeOperation
from bot.trading_row_facts import (
    KEYS_SECTION, MATERIALS_SECTION, TradingRowFact, TradingRowReader,
    consensus_row_samples,
)
from bot.flow_contracts import FlowStatus


ROOT = Path(__file__).resolve().parent.parent
FRAMES = {
    "weapon": "artifacts/hil_c5/success_panel_03.png",
    "weapon_pre": "artifacts/hil_c5/no_return_01.png",
    "weapon_after": "artifacts/hil_c5/success_result_04.png",
    "bronze_max": "screencaps/semantic/inventory-relief/trading-bronze-silver/01.png",
    "silver_max": "screencaps/semantic/inventory-relief/trading-gold-max-space/01.png",
    "gold_full": "screencaps/semantic/inventory-relief/trading-gold-full-popup/01.png",
    "gold_full_causal": "artifacts/hil_i2_j2_gold_full/20260923/before.png",
    "gold_full_after": "artifacts/hil_i2_j2_gold_full/20260923/after_ok.png",
    "limit": "screencaps/semantic/inventory-relief/trading-trade-limit-popup/01.png",
    "insufficient": "screencaps/semantic/inventory-relief/trading-insufficient-popup/01.png",
    "clean": "screencaps/semantic/inventory-relief/trading-center-entry/01.png",
    "lobby": "screencaps/semantic/trading-center/lobby/01.png",
}


class _Observer:
    def __init__(self, snapshots=()):
        self.snapshots = iter(snapshots)

    def observe(self):
        return next(self.snapshots)


@pytest.fixture(scope="module")
def replay():
    perception = build_trading_perception(ROOT)
    resolver = build_default_resolver()

    def make(name, sequence, *, timestamp=10.0):
        image = cv2.imread(str(ROOT / FRAMES[name]))
        assert image is not None, FRAMES[name]
        frame = FrameSnapshot(image, timestamp, sequence)
        observations = perception.analyze(frame)
        state = resolver.resolve(observations)
        return RuntimeSnapshot(
            frame, observations, state, RuntimeFacts(),
            FrameGeometry.from_frame(image),
        )

    return make


def _reader(snapshots=()):
    return TradingPanelReader(
        _Observer(snapshots), RapidOcrEngine(), clock=lambda: 10.1,
    )


@pytest.mark.parametrize("name,item_id,have,need,quantity", [
    ("weapon", "hero_weapon_crafting_material", 265, 40, (1, 20)),
    ("bronze_max", "silver_key", 229, 10, (20, 20)),
    ("silver_max", "gold_key", 188, 10, (18, 20)),
])
def test_real_item_trade_panel_fields(replay, name, item_id, have, need, quantity):
    fact = _reader().read_snapshot(replay(name, 11))
    assert fact is not None
    assert (fact.item_id, fact.input_have, fact.input_need, fact.quantity) == (
        item_id, have, need, quantity,
    )
    assert fact.panel_open and fact.costs == ()
    assert not (fact.shows_output_full or fact.shows_insufficient or fact.shows_limit)
    assert "second_cost_area:empty" in fact.evidence
    if quantity[0] > 1:
        assert f"displayed_input:{have}/{need * quantity[0]}" in fact.evidence


@pytest.mark.parametrize("name,flags", [
    ("gold_full", (True, False, False)),
    ("gold_full_causal", (True, False, False)),
    ("insufficient", (False, True, False)),
    ("limit", (False, False, True)),
])
def test_real_trade_boundaries(replay, name, flags):
    fact = _reader().read_snapshot(replay(name, 11))
    assert fact is not None and fact.panel_open
    assert (fact.shows_output_full, fact.shows_insufficient,
            fact.shows_limit) == flags
    assert (fact.item_id, fact.input_have, fact.input_need, fact.quantity) == (
        None, None, None, None,
    )


def test_clean_trading_and_foreign_context_do_not_make_panel_fact(replay):
    reader = _reader()
    assert reader.read_snapshot(replay("clean", 11)) is None
    assert reader.read_snapshot(replay("lobby", 12)) is None
    snapshot = replay("weapon", 13)
    foreign = replace(snapshot, state=ResolvedState(
        ResolutionStatus.RESOLVED, snapshot.sequence, snapshot.timestamp,
        base_context="screen.lobby",
    ))
    assert reader.read_snapshot(foreign) is None


@pytest.mark.parametrize("status", [ResolutionStatus.UNKNOWN,
                                    ResolutionStatus.AMBIGUOUS])
def test_unresolved_context_fails_closed(replay, status):
    snapshot = replay("weapon", 11)
    state = ResolvedState(
        status, snapshot.sequence, snapshot.timestamp,
        base_candidates=("screen.trading", "screen.lobby")
        if status is ResolutionStatus.AMBIGUOUS else (),
    )
    assert _reader().read_snapshot(replace(snapshot, state=state)) is None


def test_stale_sequence_and_age_fail_closed(replay):
    snapshot = replay("weapon", 11)
    reader = _reader([snapshot, snapshot])
    assert reader.read_snapshot(snapshot, after_sequence=11) is None
    assert reader.read_snapshot(replay("weapon", 12, timestamp=7.0)) is None
    assert reader.read_panel() is not None
    assert reader.read_panel() is None


def test_unreadable_quantity_or_unknown_second_cost_fails_closed(replay):
    snapshot = replay("weapon", 11)
    for region in ((.592, .78, .66, .84), (.50, .405, .70, .61)):
        image = snapshot.frame.image.copy()
        height, width = image.shape[:2]
        left, top, right, bottom = region
        image[int(top * height):int(bottom * height),
              int(left * width):int(right * width)] = 255
        altered = replace(snapshot, frame=FrameSnapshot(
            image, snapshot.timestamp, snapshot.sequence,
        ))
        assert _reader().read_snapshot(altered) is None


def _real_row(replay, name, first_sequence):
    snapshot = replay(name, first_sequence)
    image = snapshot.frame.image
    row_reader = TradingRowReader(RapidOcrEngine())
    samples = []
    for sequence in (first_sequence, first_sequence + 1):
        for top, _, center, complete in row_bands(image):
            if complete:
                sample = row_reader.read_sample(
                    image, sequence, item_id="hero_weapon_crafting_material",
                    section=MATERIALS_SECTION, row_top=top, row_y=center,
                )
                if sample is not None:
                    samples.append(sample)
                    break
    return snapshot, consensus_row_samples(samples)


def test_c4_consumes_real_panel_and_row_replay(replay):
    before_snapshot, before = _real_row(replay, "weapon_pre", 1)
    _, after = _real_row(replay, "weapon_after", 6)
    assert before is not None and after is not None
    assert (before.have, before.need, after.have) == (265, 40, 225)
    panel = replay("weapon", 3)
    closed = replay("weapon_after", 4)
    reader = _reader((panel, closed))
    taps = []
    result = execute_verified_trade(
        request=TradeRequest(
            row_fact=before,
            quantity=TradeQuantity(TradeQuantityMode.EXACT, 1),
            allowed_cost_kinds=frozenset({"gold"}), row_tap_x=.75,
        ),
        context=TradePreconditionContext(
            is_trading_screen=before_snapshot.state.base_context == "screen.trading",
            section=MATERIALS_SECTION, clean=True, sequence=before.sequence,
        ),
        targets=TradePanelTargets((.699, .802), (.4934, .7819), (.3555, .7806)),
        tap=lambda point: taps.append(point),
        read_panel=reader.read_panel,
        read_row=lambda: after,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.inputs == ("tap_row", "tap_confirm")
    assert len(taps) == 2


def test_c6b_ack_consumes_real_gold_full_alert(replay):
    panel = replay("gold_full_causal", 21)
    assert panel.state.base_context == "screen.trading"
    pending = PendingCausalOperation(
        operation=KeyTradeOperation.SILVER_TO_GOLD,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        before_fact=TradingRowFact(
            "gold_key", KEYS_SECTION, .56, 21, 10, 20,
        ),
        boundary="output_full",
    )
    taps = []
    result = acknowledge_gold_full_boundary(
        pending,
        read_panel=_reader((panel,)).read_panel,
        tap_ok=lambda: taps.append("ok"),
        read_keys_context=lambda *, after_sequence: replay(
            "gold_full_after", after_sequence + 1,
        ),
    )
    assert result.status is FlowStatus.COMPLETED
    assert taps == ["ok"]


def test_reader_has_no_input_or_navigation_imports():
    source = (ROOT / "bot/trading_panel_reader.py").read_text(encoding="utf-8")
    for forbidden in ("ActionExecutor", "AdbClient", "adb.tap", ".execute(",
                      "VerifiedTransition"):
        assert forbidden not in source
