"""Avatar & Keys capability: readiness, no-scroll, mapping, delegation."""

import inspect
from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center_semantics import (
    INDICATOR_TRADING_GENERAL_ACTIVE,
    INDICATOR_TRADING_KEYS_ACTIVE,
    INDICATOR_TRADING_KEYS_ROWS,
    SCREEN_TRADING,
)
from bot.trading_keys import (
    KEY_ALLOWED_COST_KINDS,
    KEY_SECTION,
    KeyTradeOperation,
    build_keys_context,
    check_keys_ready,
    execute_key_trade,
    expected_item_for,
    is_keys_ready,
    operation_for_item,
)
from bot.trading_operation import (
    TradeCostFact,
    TradeOutcome,
    TradePanelFact,
    TradePanelTargets,
    TradeQuantity,
    TradeQuantityMode,
)
from bot.trading_panel_profile import ROW_TAP_X
from bot.trading_row_facts import KEYS_SECTION, MATERIALS_SECTION, TradingRowFact

BRONZE_ROW = "silver_key"  # Bronze input, Silver output ("Silver Key 2").
SILVER_ROW = "gold_key"  # Silver input, Gold output ("Gold Key 2").


def _observation(name, confidence=0.95):
    return Observation(name, confidence, ObservationSource.LOCAL_CV)


def _snapshot(sequence, *, base, observations=(), overlays=(), status=None,
              candidates=()):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), tuple(observations)),
        ResolvedState(
            status,
            sequence,
            float(sequence),
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _keys_ready(sequence=10, names=(INDICATOR_TRADING_KEYS_ACTIVE,
                                   INDICATOR_TRADING_KEYS_ROWS)):
    return _snapshot(sequence, base=SCREEN_TRADING,
                     observations=[_observation(name) for name in names])


def _fact(item_id=BRONZE_ROW, have=50, need=10, row_y=0.57, sequence=10):
    return TradingRowFact(
        item_id=item_id,
        section=KEYS_SECTION,
        row_y=row_y,
        have=have,
        need=need,
        sequence=sequence,
        evidence=(f"sample@{sequence}:{have}/{need}",),
    )


def _targets():
    return TradePanelTargets(
        max_point=(0.699, 0.802),
        confirm_point=(0.4934, 0.7819),
        cancel_point=(0.3555, 0.7806),
    )


def _panel(item_id, have, need, sequence, quantity=(1, 20), costs=(),
           **overrides):
    values = {
        "item_id": item_id,
        "input_have": have,
        "input_need": need,
        "quantity": quantity,
        "costs": tuple(costs),
        "sequence": sequence,
    }
    values.update(overrides)
    return TradePanelFact(**values)


class _Script:
    def __init__(self, panels, rows):
        self.panels = list(panels)
        self.rows = list(rows)
        self.taps = []
        self.panel_calls = 0
        self.row_calls = 0

    def tap(self, point):
        self.taps.append(tuple(point))

    def read_panel(self):
        self.panel_calls += 1
        if not self.panels:
            return None
        return self.panels.pop(0)

    def read_row(self):
        self.row_calls += 1
        if not self.rows:
            return None
        return self.rows.pop(0)


def _success_script(item_id=BRONZE_ROW, have=50, need=10, selected=5, cap=20,
                    panel_seq=11, filled_seq=12, after_seq=13,
                    after_have=None):
    panels = [
        _panel(item_id, have, need, panel_seq, quantity=(1, cap)),
        _panel(item_id, have, need, filled_seq, quantity=(selected, cap)),
        None,
    ]
    rows = [_fact(item_id=item_id, have=(have - need * selected
                                        if after_have is None else after_have),
                  need=need, sequence=after_seq)]
    return _Script(panels, rows)


def _execute(operation, snapshot=None, fact=None, quantity=None, script=None,
             **overrides):
    snapshot = snapshot if snapshot is not None else _keys_ready()
    fact = fact if fact is not None else _fact()
    quantity = quantity if quantity is not None else TradeQuantity(
        mode=TradeQuantityMode.MAX_ALLOWED)
    script = script if script is not None else _success_script()
    values = {
        "operation": operation,
        "snapshot": snapshot,
        "row_fact": fact,
        "quantity": quantity,
        "targets": _targets(),
        "tap": script.tap,
        "read_panel": script.read_panel,
        "read_row": script.read_row,
    }
    values.update(overrides)
    return execute_key_trade(**values), script


# Readiness: positive Keys gates, everything else fails closed with no input.


def test_keys_ready_proceeds_to_success():
    result, script = _execute(KeyTradeOperation.BRONZE_TO_SILVER)
    assert result.outcome is TradeOutcome.SUCCESS
    assert script.taps[0] == (ROW_TAP_X, 0.57)
    assert "operation:bronze_to_silver" in result.evidence


def test_tab_visible_but_not_active_does_zero_input():
    general = _snapshot(10, base=SCREEN_TRADING,
                        observations=[_observation(
                            INDICATOR_TRADING_GENERAL_ACTIVE)])
    assert check_keys_ready(general) == "tab_not_keys"
    assert not is_keys_ready(general)
    result, script = _execute(KeyTradeOperation.BRONZE_TO_SILVER,
                              snapshot=general,
                              script=_Script([], []))
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "tab_not_keys"
    assert script.taps == []
    assert script.panel_calls == 0
    assert script.row_calls == 0


def test_keys_active_without_rows_does_zero_input():
    bare = _snapshot(10, base=SCREEN_TRADING,
                     observations=[_observation(
                         INDICATOR_TRADING_KEYS_ACTIVE)])
    assert check_keys_ready(bare) == "rows_not_ready"
    result, script = _execute(KeyTradeOperation.SILVER_TO_GOLD,
                              snapshot=bare,
                              fact=_fact(item_id=SILVER_ROW),
                              script=_Script([], []))
    assert result.outcome is TradeOutcome.FAILED
    assert script.taps == []


def test_overlays_break_keys_readiness_without_input():
    covered = _snapshot(10, base=SCREEN_TRADING,
                        observations=[_observation(
                            INDICATOR_TRADING_KEYS_ACTIVE),
                            _observation(INDICATOR_TRADING_KEYS_ROWS)],
                        overlays=("popup.unacquired",))
    assert check_keys_ready(covered) == "overlays_present"
    result, script = _execute(KeyTradeOperation.BRONZE_TO_SILVER,
                              snapshot=covered, script=_Script([], []))
    assert result.outcome is TradeOutcome.FAILED
    assert script.taps == []


def test_contradictory_tabs_authorize_nothing():
    both = _snapshot(10, base=SCREEN_TRADING,
                     observations=[_observation(
                         INDICATOR_TRADING_GENERAL_ACTIVE),
                         _observation(INDICATOR_TRADING_KEYS_ACTIVE),
                         _observation(INDICATOR_TRADING_KEYS_ROWS)])
    assert check_keys_ready(both) == "contradictory_state"
    result, script = _execute(KeyTradeOperation.BRONZE_TO_SILVER,
                              snapshot=both, script=_Script([], []))
    assert result.outcome is TradeOutcome.FAILED
    assert script.taps == []


def test_foreign_context_authorizes_nothing():
    foreign = _snapshot(10, base=SCREEN_LOBBY,
                        observations=[_observation(
                            INDICATOR_TRADING_KEYS_ACTIVE),
                            _observation(INDICATOR_TRADING_KEYS_ROWS)])
    assert check_keys_ready(foreign) == "not_trading"
    result, script = _execute(KeyTradeOperation.SILVER_TO_GOLD,
                              snapshot=foreign,
                              fact=_fact(item_id=SILVER_ROW),
                              script=_Script([], []))
    assert result.outcome is TradeOutcome.FAILED
    assert script.taps == []


@pytest.mark.parametrize("status,reason", [
    (ResolutionStatus.UNKNOWN, "unknown_state"),
    (ResolutionStatus.AMBIGUOUS, "ambiguous_state"),
])
def test_unknown_and_ambiguous_never_authorize(status, reason):
    if status is ResolutionStatus.AMBIGUOUS:
        snapshot = _snapshot(10, base=None, status=status,
                             candidates=(SCREEN_LOBBY, SCREEN_TRADING),
                             observations=[_observation(
                                 INDICATOR_TRADING_KEYS_ACTIVE),
                                 _observation(INDICATOR_TRADING_KEYS_ROWS)])
    else:
        snapshot = _snapshot(10, base=None, status=status,
                             observations=[_observation(
                                 INDICATOR_TRADING_KEYS_ACTIVE),
                                 _observation(INDICATOR_TRADING_KEYS_ROWS)])
    assert check_keys_ready(snapshot) == reason
    assert not is_keys_ready(snapshot)
    result, script = _execute(KeyTradeOperation.BRONZE_TO_SILVER,
                              snapshot=snapshot, script=_Script([], []))
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == reason
    assert script.taps == []


def test_build_keys_context_is_keys_sectioned():
    context = build_keys_context(_keys_ready(sequence=10))
    assert context.section == KEYS_SECTION == KEY_SECTION == "keys"
    assert context.is_trading_screen and context.clean
    assert not context.unknown and not context.ambiguous
    assert not context.contradictory
    assert context.sequence == 10


# No-scroll: Keys path never touches the directed-scroll primitive.


def test_module_has_no_scroll_imports_or_fallback():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "trading_keys.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("directed_list_scroll", "trading_materials_scroll",
                      "observed_scroll", "character_select_scroll", "swipe",
                      "gesture", "emit"):
        assert forbidden not in joined, forbidden


def test_execute_takes_no_scroll_or_swipe_callbacks():
    params = set(inspect.signature(execute_key_trade).parameters)
    assert not ({"emit", "observe_viewport", "scroll_to_target",
                 "swipe", "gesture", "max_gestures"} & params)
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "trading_keys.py").read_text(encoding="utf-8")
    assert "keys_no_scroll" not in source  # no scroll gate to trip: no scroll.
    assert "scroll" not in "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from ")))


def test_keys_success_uses_zero_swipe_vocabulary():
    result, script = _execute(KeyTradeOperation.SILVER_TO_GOLD,
                              fact=_fact(item_id=SILVER_ROW),
                              script=_success_script(item_id=SILVER_ROW))
    assert result.outcome is TradeOutcome.SUCCESS
    assert set(result.inputs) <= {"tap_row", "tap_max", "tap_confirm",
                                  "tap_cancel"}
    assert script.taps[0][0] == ROW_TAP_X == 0.75


# Mapping: causal output rows (input counts ride the output row).


def test_operation_row_mapping():
    assert expected_item_for(KeyTradeOperation.BRONZE_TO_SILVER) == BRONZE_ROW
    assert expected_item_for(KeyTradeOperation.SILVER_TO_GOLD) == SILVER_ROW
    assert operation_for_item(BRONZE_ROW) is KeyTradeOperation.BRONZE_TO_SILVER
    assert operation_for_item(SILVER_ROW) is KeyTradeOperation.SILVER_TO_GOLD
    assert len(KeyTradeOperation) == 2


@pytest.mark.parametrize("item_id", [
    "silver_gem_key", "gold_gem_chest_key", "hero_weapon_crafting_material",
    "bronze_key", "", "Silver_Key",
])
def test_operation_for_unknown_row_fails(item_id):
    with pytest.raises(ValueError):
        operation_for_item(item_id)


def test_bronze_operation_rejects_silver_fact_without_input():
    script = _Script([], [])
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER,
                         fact=_fact(item_id=SILVER_ROW),
                         script=script)
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "row_operation_mismatch"
    assert script.taps == []
    assert script.panel_calls == 0


def test_silver_operation_rejects_bronze_fact_without_input():
    script = _Script([], [])
    result, _ = _execute(KeyTradeOperation.SILVER_TO_GOLD,
                         fact=_fact(item_id=BRONZE_ROW),
                         script=script)
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "row_operation_mismatch"
    assert script.taps == []


def test_materials_fact_rejected_for_keys_operation():
    material = TradingRowFact(item_id="hero_weapon_crafting_material",
                              section=MATERIALS_SECTION, row_y=0.5,
                              have=100, need=10, sequence=10)
    script = _Script([], [])
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, fact=material,
                         script=script)
    assert result.outcome is TradeOutcome.FAILED
    assert script.taps == []


@pytest.mark.parametrize("operation", ["bronze_to_silver", None, 123,
                                       "SILVER_TO_GOLD"])
def test_unknown_operation_fails_without_input(operation):
    script = _Script([], [])
    with pytest.raises(ValueError):
        execute_key_trade(operation=operation, snapshot=_keys_ready(),
                          row_fact=_fact(),
                          quantity=TradeQuantity(
                              mode=TradeQuantityMode.MAX_ALLOWED),
                          targets=_targets(), tap=script.tap,
                          read_panel=script.read_panel,
                          read_row=script.read_row)
    assert script.taps == []


# Request delegation: quantity/cost guards reach C4 unchanged.


@pytest.mark.parametrize("mode,amount", [
    (TradeQuantityMode.MAX_ALLOWED, None),
    (TradeQuantityMode.EXACT, 1),
    (TradeQuantityMode.UP_TO, 3),
])
def test_caller_quantity_modes_delegate(mode, amount):
    quantity = TradeQuantity(mode=mode, amount=amount)
    if mode is TradeQuantityMode.MAX_ALLOWED:
        script = _success_script()
    elif mode is TradeQuantityMode.EXACT:
        fact = _fact(have=15, need=10)
        script = _Script(
            [_panel(BRONZE_ROW, 15, 10, 11, quantity=(1, 20)), None],
            [_fact(have=5, need=10, sequence=12)],
        )
        result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, fact=fact,
                             quantity=quantity, script=script)
        assert result.outcome is TradeOutcome.SUCCESS
        assert result.inputs == ("tap_row", "tap_confirm")
        return
    else:
        script = _success_script(have=50, need=10, selected=3, cap=20,
                                 after_have=20)
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER,
                         quantity=quantity, script=script)
    assert result.outcome is TradeOutcome.SUCCESS
    assert f"operation:bronze_to_silver" in result.evidence


def test_row_tap_uses_profile_x_and_stable_row_y():
    fact = _fact(row_y=0.8537)
    result, script = _execute(KeyTradeOperation.BRONZE_TO_SILVER, fact=fact)
    assert result.outcome is TradeOutcome.SUCCESS
    assert script.taps[0] == (ROW_TAP_X, 0.8537)


def test_keys_allowlist_blocks_premium_cost():
    costs = (TradeCostFact(kind="karats", amount=5, evidence=("ocr:5",)),)
    script = _Script([_panel(BRONZE_ROW, 50, 10, 11, costs=costs)], [])
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, script=script)
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "unexpected_currency"
    assert "tap_confirm" not in result.inputs
    assert KEY_ALLOWED_COST_KINDS == frozenset({"gold"})


def test_unreadable_cost_blocks_confirm():
    costs = (TradeCostFact(kind="gold", amount=None, evidence=("blur",)),)
    script = _Script([_panel(BRONZE_ROW, 50, 10, 11, costs=costs)], [])
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, script=script)
    assert result.reason == "unreadable_cost"
    assert "tap_confirm" not in result.inputs


def test_have_below_need_returns_no_more_input_without_tap():
    fact = _fact(have=5, need=10)
    script = _Script([], [])
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, fact=fact,
                         script=script)
    assert result.outcome is TradeOutcome.NO_MORE_INPUT
    assert script.taps == []
    assert "operation:bronze_to_silver" in result.evidence


# Results: C4 outcomes pass through with operation metadata, no routing.


def test_success_passthrough_carries_after_fact():
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER)
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.after_fact is not None
    assert result.after_fact.have < result.before_fact.have
    assert result.boundary is None


def test_insufficient_input_passthrough():
    script = _Script([_panel(BRONZE_ROW, 50, 10, 11,
                             shows_insufficient=True)], [])
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, script=script)
    assert result.outcome is TradeOutcome.INSUFFICIENT_INPUT
    assert result.boundary == "insufficient_input"
    assert "tap_confirm" not in result.inputs


def test_output_full_passthrough_without_treasure_routing():
    script = _Script([_panel(SILVER_ROW, 25, 10, 11,
                             shows_output_full=True)], [])
    result, script_used = _execute(
        KeyTradeOperation.SILVER_TO_GOLD,
        fact=_fact(item_id=SILVER_ROW, have=25, need=10),
        script=script)
    assert result.outcome is TradeOutcome.OUTPUT_FULL
    assert result.boundary == "output_full"
    assert "tap_confirm" not in result.inputs
    assert "operation:silver_to_gold" in result.evidence
    for token in ("treasure", "craft", "relief", "monster_wave"):
        assert token not in "\n".join(result.inputs).casefold()
        assert token not in "\n".join(result.evidence).casefold()


def test_no_effect_passthrough_is_not_success():
    script = _success_script(after_have=50)
    result, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER, script=script)
    assert result.outcome is TradeOutcome.NO_EFFECT
    assert result.after_fact is not None
    assert result.after_fact.have == 50


def test_operations_are_independent_no_order_policy():
    first, _ = _execute(KeyTradeOperation.BRONZE_TO_SILVER)
    second, _ = _execute(
        KeyTradeOperation.SILVER_TO_GOLD,
        fact=_fact(item_id=SILVER_ROW),
        script=_success_script(item_id=SILVER_ROW))
    assert first.outcome is TradeOutcome.SUCCESS
    assert second.outcome is TradeOutcome.SUCCESS
    # Reverse order works identically: no sequencing is enforced.
    third, _ = _execute(
        KeyTradeOperation.SILVER_TO_GOLD,
        fact=_fact(item_id=SILVER_ROW),
        script=_success_script(item_id=SILVER_ROW))
    assert third.outcome is TradeOutcome.SUCCESS


# Separation: executor/adapter only; Gold capacity never inferred.


def test_module_has_no_external_sink_planner_or_counts_imports():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "trading_keys.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("treasure", "craft", "relief", "monster_wave",
                      "planner", "stage", "inventory", "should_"):
        assert forbidden not in joined, forbidden
    assert "def should_" not in source.casefold()
    assert "route_plan" not in source.casefold()
    assert "def _key_counts" not in source
    assert "_key_counts(" not in source
    assert "def promote" not in source.casefold()


def test_gold_capacity_stays_not_observable():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "trading_keys.py").read_text(encoding="utf-8")
    assert "NOT OBSERVABLE" in source
    assert "Gold Key capacity is NOT OBSERVABLE" in source
