"""Generic verified trade primitive: guards, quantity, boundaries."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from bot.action_executor import ActionExecutor, FrameGeometry
from bot.semantic_actions import (
    CancelTradingTrade, ConfirmTradingTrade, SelectTradingMaximum,
    SelectTradingRow,
)

from bot.trading_operation import (
    TradeCostFact,
    TradeOutcome,
    TradePanelFact,
    TradePanelTargets,
    TradePreconditionContext,
    TradeQuantity,
    TradeQuantityMode,
    TradeRequest,
    TradeResult,
    check_precondition,
    execute_verified_trade,
)
from bot.trading_row_facts import MATERIALS_SECTION, TradingRowFact

ITEM = "hero_armor_crafting_material"
OTHER = "hero_weapon_crafting_material"


def _fact(item_id=ITEM, have=399, need=4, row_y=0.70, sequence=10):
    return TradingRowFact(
        item_id=item_id,
        section=MATERIALS_SECTION,
        row_y=row_y,
        have=have,
        need=need,
        sequence=sequence,
        evidence=(f"sample@{sequence}:{have}/{need}",),
    )


def _context(sequence=10, **overrides):
    values = {
        "is_trading_screen": True,
        "section": MATERIALS_SECTION,
        "clean": True,
        "sequence": sequence,
    }
    values.update(overrides)
    return TradePreconditionContext(**values)


def _targets():
    return TradePanelTargets(
        max_point=(0.5, 0.8),
        confirm_point=(0.49, 0.77),
        cancel_point=(0.35, 0.77),
    )


def _panel(sequence=11, have=399, need=4, quantity=(1, 20),
           costs=(), **overrides):
    values = {
        "item_id": ITEM,
        "input_have": have,
        "input_need": need,
        "quantity": quantity,
        "costs": tuple(costs),
        "sequence": sequence,
    }
    values.update(overrides)
    return TradePanelFact(**values)


def _request(fact=None, mode=TradeQuantityMode.MAX_ALLOWED, amount=None,
             kinds=frozenset({"gold"}), **overrides):
    values = {
        "row_fact": fact if fact is not None else _fact(),
        "quantity": TradeQuantity(mode=mode, amount=amount),
        "allowed_cost_kinds": kinds,
        "row_tap_x": 0.70,
    }
    values.update(overrides)
    return TradeRequest(**values)


class _Script:
    """Deterministic injected I/O: records taps, replays panel/row reads."""

    def __init__(self, panels, rows):
        self.panels = list(panels)
        self.rows = list(rows)
        self.taps = []

    def tap(self, point):
        self.taps.append(tuple(point))

    def read_panel(self):
        if not self.panels:
            return None
        return self.panels.pop(0)

    def read_row(self):
        if not self.rows:
            return None
        return self.rows.pop(0)


def _success_script(have=399, need=4, selected=20, cap=20,
                    panel_seq=11, filled_seq=12, after_seq=13,
                    after_have=None, costs=()):
    panels = [
        _panel(sequence=panel_seq, have=have, need=need,
               quantity=(1, cap), costs=costs),
        _panel(sequence=filled_seq, have=have, need=need,
               quantity=(selected, cap), costs=costs),
        None,
    ]
    rows = [_fact(have=after_have if after_have is not None else have - need * selected,
                  need=need, sequence=after_seq)]
    return _Script(panels, rows)


# Preconditions: zero input unless every gate holds.


def test_fresh_matching_fact_may_open():
    script = _success_script()
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert script.taps[0] == (0.70, 0.70)


def test_c4_semantic_input_runs_through_action_executor_and_keeps_postcondition():
    script = _success_script()
    adb = Mock()
    executor = ActionExecutor(adb)
    intents = []

    def act(intent):
        intents.append(intent)
        executor.execute(intent, FrameGeometry(2712, 1220))

    result = execute_verified_trade(
        request=_request(), context=_context(), targets=None, tap=None,
        act=act, read_panel=script.read_panel, read_row=script.read_row,
    )

    assert result.outcome is TradeOutcome.SUCCESS
    assert [type(intent) for intent in intents] == [
        SelectTradingRow, SelectTradingMaximum, ConfirmTradingTrade,
    ]
    assert adb.tap.call_count == 3
    assert script.taps == []


def test_c4_semantic_no_and_gold_full_row_boundary():
    adb = Mock()
    executor = ActionExecutor(adb)
    intents = []
    def act(intent):
        intents.append(intent)
        executor.execute(intent, FrameGeometry(2712, 1220))

    mismatch = _Script([_panel(item_id=OTHER)], [])
    rejected = execute_verified_trade(
        request=_request(), context=_context(), targets=None, tap=None,
        act=act, read_panel=mismatch.read_panel, read_row=mismatch.read_row,
    )
    assert rejected.outcome is TradeOutcome.FAILED
    assert [type(intent) for intent in intents] == [SelectTradingRow, CancelTradingTrade]

    intents.clear()
    gold_full = _Script([_panel(item_id=None, input_have=None, input_need=None,
                                quantity=None, shows_output_full=True)], [])
    blocked = execute_verified_trade(
        request=_request(), context=_context(), targets=None, tap=None,
        act=act, read_panel=gold_full.read_panel, read_row=gold_full.read_row,
    )
    assert blocked.outcome is TradeOutcome.OUTPUT_FULL
    assert blocked.reason == "output_full_on_open"
    assert [type(intent) for intent in intents] == [SelectTradingRow]


def test_row_tap_uses_stable_row_y():
    fact = _fact(row_y=0.8537)
    script = _success_script()
    result = execute_verified_trade(
        request=_request(fact=fact), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert script.taps[0] == (0.70, 0.8537)


@pytest.mark.parametrize("mutate,reason", [
    ({"sequence": 4}, "stale_fact"),
    ({"section": "keys"}, "section_mismatch"),
    ({"is_trading_screen": False}, "not_trading"),
    ({"clean": False}, "overlays_present"),
    ({"unknown": True}, "unknown_state"),
    ({"ambiguous": True}, "ambiguous_state"),
    ({"contradictory": True}, "contradictory_state"),
])
def test_precondition_failures_do_zero_input(mutate, reason):
    script = _Script([], [])
    result = execute_verified_trade(
        request=_request(), context=_context(**mutate),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == reason
    assert script.taps == []
    assert result.inputs == ()


def test_expected_item_mismatch_does_zero_input():
    fact = _fact(item_id=OTHER)
    script = _Script([], [])
    result = execute_verified_trade(
        request=_request(fact=fact, expected_item_id=ITEM),
        context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "row_mismatch"
    assert script.taps == []


def test_have_below_need_is_no_more_input_without_tap():
    fact = _fact(have=2, need=4)
    script = _Script([], [])
    result = execute_verified_trade(
        request=_request(fact=fact), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.NO_MORE_INPUT
    assert script.taps == []


def test_user_cancel_before_input_taps_nothing():
    script = _Script([], [])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
        cancel_requested=lambda: True,
    )
    assert result.outcome is TradeOutcome.CANCELLED
    assert script.taps == []


def test_check_precondition_pure():
    assert check_precondition(_request(), _context()) is None
    assert check_precondition(_request(), _context(unknown=True)) == "unknown_state"


# Panel open.


def test_wrong_panel_never_confirms():
    script = _Script([None], [_fact(sequence=12)])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "panel_not_open"
    assert "tap_confirm" not in result.inputs
    assert script.taps == [(0.70, 0.70)]


def test_stale_panel_never_confirms():
    script = _Script([_panel(sequence=10)], [_fact(sequence=12)])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "stale_panel"
    assert "tap_confirm" not in result.inputs


def test_source_lost_after_max_aborts():
    script = _Script(
        [_panel(sequence=11), None],
        [_fact(sequence=13)],
    )
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "panel_lost_after_max"
    assert "tap_confirm" not in result.inputs
    assert result.inputs.count("tap_max") == 1


# Costs as data/guards.


def test_allowed_readable_cost_proceeds():
    costs = (TradeCostFact(kind="gold", amount=100, sufficient=True,
                           evidence=("ocr:100",)),)
    script = _success_script(costs=costs)
    result = execute_verified_trade(
        request=_request(kinds=frozenset({"gold"})), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS


def test_unexpected_currency_cancels_without_confirm():
    costs = (TradeCostFact(kind="karats", amount=5, evidence=("ocr:5",)),)
    script = _Script(
        [_panel(sequence=11, costs=costs)],
        [],
    )
    result = execute_verified_trade(
        request=_request(kinds=frozenset({"gold"})), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "unexpected_currency"
    assert "tap_confirm" not in result.inputs
    assert "tap_cancel" in result.inputs


def test_unreadable_cost_cancels_without_confirm():
    costs = (TradeCostFact(kind="gold", amount=None, evidence=("blur",)),)
    script = _Script([_panel(sequence=11, costs=costs)], [])
    result = execute_verified_trade(
        request=_request(kinds=frozenset({"gold"})), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "unreadable_cost"
    assert "tap_confirm" not in result.inputs


def test_insufficient_second_cost_returns_boundary():
    costs = (TradeCostFact(kind="gold", amount=100, sufficient=False,
                           evidence=("ocr:100",)),)
    script = _Script([_panel(sequence=11, costs=costs)], [])
    result = execute_verified_trade(
        request=_request(kinds=frozenset({"gold"})), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.INSUFFICIENT_INPUT
    assert "tap_confirm" not in result.inputs


def test_second_cost_change_after_max_blocks_confirm():
    panels = [
        _panel(sequence=11,
               costs=(TradeCostFact(kind="gold", amount=100),)),
        _panel(sequence=12, quantity=(5, 20),
               costs=(TradeCostFact(kind="karats", amount=5),)),
    ]
    script = _Script(panels, [])
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.EXACT, amount=5,
                         kinds=frozenset({"gold"})),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "unexpected_currency"
    assert "tap_confirm" not in result.inputs


# Quantity modes; no hidden arithmetic.


def test_max_allowed_observes_panel_cap_not_history():
    script = _success_script(have=399, need=4, selected=7, cap=7,
                             after_have=371)
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.inputs.count("tap_max") == 1


def test_exact_amount_confirms_only_on_match():
    script = _success_script(have=399, need=4, selected=5, cap=20,
                             after_have=379)
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.EXACT, amount=5),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS


def test_up_to_accepts_smaller_proven_fill():
    script = _success_script(have=399, need=4, selected=3, cap=3,
                             after_have=387)
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.UP_TO, amount=9),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS


def test_impossible_amount_fails_closed():
    script = _Script([_panel(sequence=11, quantity=(1, 20))], [])
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.EXACT, amount=25),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "impossible_amount"
    assert "tap_confirm" not in result.inputs
    assert "tap_cancel" in result.inputs


# >> non-idempotent: exactly one causal tap, never a blind second.


def test_max_no_effect_fails_closed_without_retry_or_confirm():
    script = _Script(
        [_panel(sequence=11, quantity=(1, 20)),
         _panel(sequence=12, quantity=(1, 20))],
        [],
    )
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "max_no_effect"
    assert result.inputs.count("tap_max") == 1
    assert "tap_confirm" not in result.inputs


def test_success_never_double_taps_max_or_confirm():
    script = _success_script()
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.inputs.count("tap_max") == 1
    assert result.inputs.count("tap_confirm") == 1


# Confirmation contract + popup-vs-row.


def test_popup_row_mismatch_cancels_without_confirm():
    script = _Script([_panel(sequence=11, item_id=OTHER)], [])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "popup_row_mismatch"
    assert "tap_confirm" not in result.inputs
    assert "tap_cancel" in result.inputs


def test_input_need_mismatch_blocks_confirm():
    script = _Script([_panel(sequence=11, need=99)], [])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "second_cost_mismatch"
    assert "tap_confirm" not in result.inputs


def test_cancel_without_point_still_spends_nothing():
    bare = TradePanelTargets(max_point=(0.5, 0.8),
                             confirm_point=(0.49, 0.77),
                             cancel_point=None)
    script = _Script([_panel(sequence=11, item_id=OTHER)], [])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=bare, tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert "tap_confirm" not in result.inputs
    assert "tap_cancel" not in result.inputs


# Postcondition.


def test_unchanged_have_is_no_effect_not_success():
    script = _success_script(after_have=399)
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.NO_EFFECT
    assert result.after_fact is not None
    assert result.after_fact.have == 399


def test_stale_after_fact_is_not_success():
    script = _success_script(after_seq=12, after_have=10)
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.FAILED
    assert result.reason == "stale_after_fact"


def test_after_identity_mismatch_is_not_success():
    script = _Script(
        [_panel(sequence=11), _panel(sequence=12, quantity=(9, 20)), None],
        [_fact(item_id=OTHER, have=1, need=10, sequence=13)],
    )
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.EXACT, amount=9),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.reason == "after_identity_mismatch"


# Boundaries are returned, never resolved.


@pytest.mark.parametrize("flag,boundary,outcome", [
    ("shows_insufficient", "insufficient_input",
     TradeOutcome.INSUFFICIENT_INPUT),
    ("shows_output_full", "output_full", TradeOutcome.OUTPUT_FULL),
    ("shows_limit", "limit_reached", TradeOutcome.LIMIT_REACHED),
])
def test_boundaries_on_open_return_without_confirm(flag, boundary, outcome):
    script = _Script([_panel(sequence=11, **{flag: True})], [])
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is outcome
    assert result.boundary == boundary
    assert "tap_confirm" not in result.inputs
    assert "tap_max" not in result.inputs


def test_output_full_after_max_returns_boundary():
    script = _Script(
        [_panel(sequence=11),
         _panel(sequence=12, shows_output_full=True)],
        [],
    )
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.OUTPUT_FULL
    assert result.boundary == "output_full"
    assert "tap_confirm" not in result.inputs


def test_output_full_on_confirm_returns_boundary():
    script = _Script(
        [_panel(sequence=11),
         _panel(sequence=12, quantity=(9, 20)),
         _panel(sequence=13, shows_output_full=True)],
        [],
    )
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.EXACT, amount=9),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.OUTPUT_FULL
    assert result.boundary == "output_full"


# Separation: executor, not planner/router/sink.


def test_module_has_no_external_sink_or_planner_imports():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "trading_operation.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("treasure", "craft", "relief", "monster_wave",
                      "planner", "stage", "inventory", "should_"):
        assert forbidden not in joined, forbidden


def test_module_defines_no_routing_decisions():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "trading_operation.py").read_text(encoding="utf-8")
    code_lines = [line for line in source.splitlines()
                  if line.strip() and not line.strip().startswith('"""')
                  and not line.strip().startswith("#")]
    import_lines = [line for line in code_lines
                    if line.strip().startswith(("import ", "from "))]
    joined_imports = "\n".join(import_lines).casefold()
    for forbidden in ("treasure", "craft", "relief", "monster_wave",
                      "planner", "stage", "inventory"):
        assert forbidden not in joined_imports, forbidden
    code = "\n".join(code_lines).casefold()
    assert "def should_" not in code
    assert "route_plan" not in code


def test_result_carries_descriptive_evidence():
    script = _success_script()
    result = execute_verified_trade(
        request=_request(), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert isinstance(result, TradeResult)
    assert result.before_fact.have == 399
    assert result.after_fact is not None
    assert result.after_fact.have < 399
    assert result.evidence


def test_max_skipped_when_exact_already_selected():
    script = _Script(
        [_panel(sequence=11, have=53, need=40, quantity=(1, 20)), None],
        [_fact(have=13, need=40, sequence=12)],
    )
    fact = _fact(have=53, need=40)
    result = execute_verified_trade(
        request=_request(fact=fact, mode=TradeQuantityMode.EXACT, amount=1),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.inputs == ("tap_row", "tap_confirm")
    assert result.after_fact is not None
    assert result.after_fact.have == 13


def test_max_skipped_when_max_allowed_already_full():
    script = _Script(
        [_panel(sequence=11, quantity=(9, 9)), None],
        [_fact(have=399 - 36, need=4, sequence=12)],
    )
    fact = _fact(have=399, need=4)
    result = execute_verified_trade(
        request=_request(fact=fact), context=_context(),
        targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert "tap_max" not in result.inputs


def test_max_skipped_when_up_to_target_already_shown():
    script = _Script(
        [_panel(sequence=11, quantity=(3, 3)), None],
        [_fact(have=399 - 12, need=4, sequence=12)],
    )
    result = execute_verified_trade(
        request=_request(mode=TradeQuantityMode.UP_TO, amount=9),
        context=_context(), targets=_targets(), tap=script.tap,
        read_panel=script.read_panel, read_row=script.read_row,
    )
    assert result.outcome is TradeOutcome.SUCCESS
    assert "tap_max" not in result.inputs
