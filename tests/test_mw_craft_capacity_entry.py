"""Direct Craft entry and deterministic Inventory branch exit contract."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from bot.catalog import MENU_QUICK, SCREEN_LOBBY
from bot.craft_runtime import CraftRouteOutcome, CraftRouteResult
from bot.flow_contracts import FlowResult, FlowStatus
from bot.monster_wave_resource_route import MonsterWavePrerequisiteNavigationRuntime
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.quick_menu import QuickMenuHandoff
from bot.semantic_actions import QuickMenuLayout
from bot.verified_transition import VerifiedTransitionResult, VerifiedTransitionOutcome
from test_monster_wave_resource_route import _anchor, _context as _resolved_context, _craft_fact
from dataclasses import replace
from bot.state import ResolvedState, ResolutionStatus


def _context(sequence, base, *, overlays=(), status=None):
    template = _resolved_context(sequence, SCREEN_LOBBY)
    status = status or (ResolutionStatus.UNKNOWN if base is None else ResolutionStatus.RESOLVED)
    state = ResolvedState(status, sequence, float(sequence), base_context=base,
                          overlays=overlays, base_candidates=(SCREEN_LOBBY, SCREEN_MONSTER_WAVE)
                          if status is ResolutionStatus.AMBIGUOUS else ())
    return replace(template, state=state)


def navigation(observer, craft, continuation=None):
    return MonsterWavePrerequisiteNavigationRuntime(
        observer, SimpleNamespace(execute=Mock()), craft,
        resume_mw_from_lobby=continuation)


@pytest.mark.parametrize("outcome", [CraftRouteOutcome.ENTERED, CraftRouteOutcome.FAILED,
                                    CraftRouteOutcome.CANCELLED])
def test_craft_entry_consumes_direct_handoff_without_inventory(outcome):
    menu = _context(11, SCREEN_MONSTER_WAVE, overlays=(MENU_QUICK,))
    handoff = QuickMenuHandoff(SCREEN_MONSTER_WAVE, 10, 11, QuickMenuLayout.SHIFTED)
    craft = SimpleNamespace(
        enter_from_verified_quick_menu=Mock(return_value=CraftRouteResult(outcome,
            craft_fact=_craft_fact(12))), request_back_to_origin=Mock(),
        probe_equipment_capacity=Mock(side_effect=AssertionError("no entry preflight")))
    nav = navigation(SimpleNamespace(wait_until=Mock()), craft)
    opened = VerifiedTransitionResult("menu", VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
                                     1, 0, menu)
    nav._open_mw_menu = Mock(return_value=([opened], handoff, None))
    result = nav.enter_craft_from_mw(_anchor(10))
    assert result.status is {CraftRouteOutcome.ENTERED: FlowStatus.COMPLETED,
                             CraftRouteOutcome.FAILED: FlowStatus.FAILED,
                             CraftRouteOutcome.CANCELLED: FlowStatus.CANCELLED}[outcome]
    craft.enter_from_verified_quick_menu.assert_called_once_with(handoff, menu)
    craft.probe_equipment_capacity.assert_not_called()
    nav._open_mw_menu.assert_called_once()


def test_inventory_branch_waits_for_lobby_then_uses_normal_mw_navigation_once():
    trace = []
    def wait(predicate, **kwargs):
        assert kwargs["after_sequence"] == 21
        assert predicate(_context(22, SCREEN_LOBBY))
        assert not predicate(_anchor(22).context)
        trace.append("expected_lobby")
        return _context(22, SCREEN_LOBBY)
    def continuation():
        trace.extend(["zone_enter", "activity_reenter"])
        return FlowResult(FlowStatus.COMPLETED)
    nav = navigation(SimpleNamespace(wait_until=wait),
                     SimpleNamespace(enter_from_verified_quick_menu=Mock(),
                                     request_back_to_origin=Mock()), continuation)
    result = nav.continue_from_craft_lobby(after_sequence=21)
    assert result.status is FlowStatus.COMPLETED
    assert result.after_sequence == 22
    assert trace == ["expected_lobby", "zone_enter", "activity_reenter"]


def test_unknown_postcondition_does_not_navigate_or_repeat_economic_intent():
    continuation = Mock()
    observer = SimpleNamespace(wait_until=Mock(side_effect=TimeoutError("Lobby missing")))
    craft = SimpleNamespace(enter_from_verified_quick_menu=Mock(), request_back_to_origin=Mock())
    nav = navigation(observer, craft, continuation)
    result = nav.continue_from_craft_lobby(after_sequence=21)
    assert result.status is FlowStatus.FAILED
    continuation.assert_not_called()
    craft.enter_from_verified_quick_menu.assert_not_called()
    craft.request_back_to_origin.assert_not_called()


def test_fresh_craft_full_popup_enters_combine_without_reopening_recipe():
    from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, SCREEN_COMBINE
    from bot.semantic_actions import OpenEquipmentCombine
    from bot.state import ResolutionStatus
    popup = _context(22, None, status=ResolutionStatus.UNKNOWN,
                     overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,))
    final = _context(23, SCREEN_COMBINE)
    craft = SimpleNamespace(enter_from_verified_quick_menu=Mock(), request_back_to_origin=Mock(),
                            observe_context=Mock(), _tap=Mock())
    nav = navigation(SimpleNamespace(observe=Mock(return_value=popup), wait_until=Mock()), craft)
    nav.transition.execute.return_value = VerifiedTransitionResult(
        "craft.full", VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT, 1, 0, final)
    assert nav.enter_combine_from_craft(SimpleNamespace()) is final
    craft.observe_context.assert_not_called()
    craft._tap.assert_not_called()
    args, kwargs = nav.transition.execute.call_args
    assert isinstance(args[1], OpenEquipmentCombine)
    assert args[2] is popup
    assert kwargs["policy"].max_attempts == 1
    assert kwargs["precondition"](popup)
    assert not kwargs["precondition"](_context(24, None, status=ResolutionStatus.AMBIGUOUS,
                                              overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,)))
    assert kwargs["expected"](final)


def test_missing_craft_full_popup_never_dispatches_combine():
    from bot.semantic_actions import OpenHeroCraft
    craft = SimpleNamespace(enter_from_verified_quick_menu=Mock(), request_back_to_origin=Mock(),
        observe_context=Mock(return_value=CraftRouteResult(CraftRouteOutcome.ENTERED,
                                                           craft_fact=_craft_fact(23))), _tap=Mock())
    nav = navigation(SimpleNamespace(observe=Mock(return_value=_context(22, None)),
                     wait_until=Mock(side_effect=TimeoutError("full popup unavailable"))), craft)
    with pytest.raises(TimeoutError):
        nav.enter_combine_from_craft(CraftRouteResult(CraftRouteOutcome.CAPACITY_BLOCKED,
                                                     craft_fact=_craft_fact(21)))
    assert isinstance(craft._tap.call_args.args[0], OpenHeroCraft)
    craft._tap.assert_called_once()
    nav.transition.execute.assert_not_called()
