from pathlib import Path
from unittest.mock import Mock
from dataclasses import replace
from types import SimpleNamespace
import cv2
import pytest
from bot.trading_materials_productive import ProductiveMaterialsAdapter,TARGET
from bot.trading_row_facts import TradingRowReader
from bot.ocr import RapidOcrEngine
from bot.trading_operation import TradePanelFact,TradeQuantity,TradeQuantityMode,TradeCostFact,TradeOutcome
from bot.directed_list_scroll import DirectedScrollOutcome
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import Swipe,ConfirmTradingTrade
from test_trading_materials_runtime import _snapshot,_fresh,_step
ROOT=Path(__file__).resolve().parents[1]


def adapter(observer=None):
    return ProductiveMaterialsAdapter(observer or Mock(),Mock(),TradingRowReader(RapidOcrEngine()),Mock(),clock=lambda:0)


def test_material_evaluator_causal_title_and_pair():
    a=adapter();f=cv2.imread(str(ROOT/'screencaps/semantic/trading-center/general-mid/04.png'))
    g=a.target_geometry(f)
    assert g is not None and a.reader.read_pair(f,g[0])==(265,40)


@pytest.mark.parametrize('path',[
    'screencaps/semantic/trading-center/general-top/01.png',
    'screencaps/semantic/trading-center/general-mid/03.png',
    'screencaps/semantic/trading-center/keys-top/01.png',
    'artifacts/mw_stabilization/materials_event_top.png',
    'artifacts/mw_stabilization/bronze_pre_panel.png',
])
def test_material_evaluator_rejects_foreign_titles_partial_target_and_panel(path):
    f=cv2.imread(str(ROOT/path));assert f is not None
    assert adapter().target_geometry(f) is None


def test_location_requires_fresh_stable_complete_target_without_input():
    o=Mock();o.wait_until.side_effect=[_snapshot(11),_snapshot(12)]
    a=adapter(o);a.target_geometry=Mock(return_value=(.36,.43))
    result=a.locate(target=TARGET,after_sequence=10)
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert result.last_sequence==12
    a.actions.execute.assert_not_called()


def test_unknown_target_and_cancellation_never_scroll():
    a=adapter();assert a.locate(target='unknown',after_sequence=0).outcome is DirectedScrollOutcome.TARGET_UNKNOWN
    a.cancel_requested=lambda:True
    with pytest.raises(RuntimeWaitCancelled): a.locate(target=TARGET,after_sequence=0)
    a.actions.execute.assert_not_called();a.observer.wait_until.assert_not_called()


def test_bounded_scan_uses_safe_lane_and_stops_on_no_progress():
    o=Mock();o.wait_until.side_effect=[_snapshot(i) for i in range(1,5)]
    a=adapter(o);a.target_geometry=Mock(return_value=None)
    a.clock=lambda:o.wait_until.call_count
    result=a.locate(target=TARGET,after_sequence=0,use_targeted=False)
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert a.actions.execute.call_count==2
    actions=[c.args[0] for c in a.actions.execute.call_args_list]
    assert all(isinstance(s,Swipe) and s.start[0]==s.end[0]==.33 for s in actions)
    assert actions[0].start[1]>actions[0].end[1]
    assert actions[1].start[1]<actions[1].end[1]
    assert result.direction_reversals==1


@pytest.mark.parametrize('premium',(False,True))
def test_material_c4_single_confirm_or_block_before_premium(premium):
    before=_fresh(10,have=80);after=_fresh(14,have=0)
    panels={11:TradePanelFact(TARGET,80,40,(1,20),sequence=11,
        costs=(TradeCostFact('karats',5),) if premium else ()),
        12:TradePanelFact(TARGET,80,40,(2,20),sequence=12)}
    class Observer:
        def wait_until(self,predicate,**kw):
            for n in range(kw['after_sequence']+1,14):
                s=_snapshot(n)
                if predicate(s):return s
            raise AssertionError('no ready frame')
    a=adapter(Observer());a.panel_reader.read_snapshot.side_effect=lambda s,**kw:panels.get(s.sequence)
    a.read=Mock(return_value=after)
    result=a.trade(operation=_step().operations[0],snapshot=before.snapshot,row_fact=before.row_fact,
                   quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED))
    confirms=[c for c in a.actions.execute.call_args_list if isinstance(c.args[0],ConfirmTradingTrade)]
    assert len(confirms)==(0 if premium else 1)
    assert result.outcome is (TradeOutcome.FAILED if premium else TradeOutcome.SUCCESS)
    if premium:a.read.assert_not_called()
    else:assert result.after_fact.have==0


def test_native_materials_after_trade_preserves_leading_one():
    frame=cv2.imread(str(ROOT/'artifacts/mw_stabilization/mw_gold_relief_final.png'))
    assert frame is not None
    a=adapter();geometry=a.target_geometry(frame)
    assert geometry is not None
    diagnostics={}
    assert a.reader.read_pair(frame,geometry[0],diagnostics=diagnostics) == (134,40)
    assert [read["raw"] for read in diagnostics["pair_reads"]] == ["134/40","134/40"]


def test_targeted_anchor_loss_falls_back_with_remaining_budget():
    o=Mock();o.wait_until.side_effect=[_snapshot(i) for i in range(1,6)]
    a=adapter(o);a.target_geometry=Mock(return_value=None)
    a.clock=lambda:o.wait_until.call_count
    a.anchors.read=Mock(side_effect=[(('lapiz_400',.5),),()])
    r=a.locate(target=TARGET,after_sequence=0,max_gestures=2)
    assert r.fallbacks==1 and r.gesture_count==2
    assert [c.args[0].duration_ms for c in a.actions.execute.call_args_list]==[250,900]
    assert r.reason=='material_scan_exhausted'


def test_unknown_prefix_coarse_then_one_calculated_gesture_and_strong_confirmation():
    o=Mock();o.wait_until.side_effect=[_snapshot(i) for i in range(1,5)]
    a=adapter(o);a.clock=lambda:o.wait_until.call_count
    a.target_geometry=Mock(side_effect=[None,None,(.58,.65),(.58,.65)])
    a.anchors.read=Mock(side_effect=[(),(('sapphire_5',.65),)])
    r=a.locate(target=TARGET,after_sequence=0)
    assert r.outcome is DirectedScrollOutcome.TARGET_READY and r.gesture_count==2
    assert r.fallbacks==0 and r.stable_sequence==4
    swipes=[c.args[0] for c in a.actions.execute.call_args_list]
    assert swipes[0].start==(.33,.94) and swipes[0].end==(.33,.02)
    assert swipes[0].duration_ms==swipes[1].duration_ms==250
    assert swipes[1].end[1]>.02


def test_missing_anchor_after_coarse_keeps_fallback_with_remaining_total_budget():
    o=Mock();o.wait_until.side_effect=[_snapshot(i) for i in range(1,5)]
    a=adapter(o);a.clock=lambda:o.wait_until.call_count
    a.target_geometry=Mock(return_value=None);a.anchors.read=Mock(return_value=())
    r=a.locate(target=TARGET,after_sequence=0,max_gestures=2)
    assert r.fallbacks==1 and r.gesture_count==2
    assert [c.args[0].duration_ms for c in a.actions.execute.call_args_list]==[250,900]


def test_targeted_navigation_retains_strong_complete_target_confirmation():
    o=Mock();o.wait_until.side_effect=[_snapshot(i) for i in range(1,4)]
    a=adapter(o)
    a.clock=lambda:1.
    a.target_geometry=Mock(side_effect=[None,(.50,.57),(.50,.57)])
    a.anchors.read=Mock(return_value=(('lapiz_400',.5),))
    r=a.locate(target=TARGET,after_sequence=0)
    assert r.outcome is DirectedScrollOutcome.TARGET_READY and r.gesture_count==1
    assert r.stable_sequence==3 and r.observations==3
    assert a.actions.execute.call_count==1
    assert isinstance(a.actions.execute.call_args.args[0],Swipe)


def test_targeted_emit_rejects_stale_context_before_dispatch():
    o=Mock();o.wait_until.return_value=_snapshot(1)
    a=adapter(o);a.clock=lambda:3.01
    a.target_geometry=Mock(return_value=None)
    a.anchors.read=Mock(return_value=(('lapiz_400',.5),))
    with pytest.raises(ValueError,match='stale or lost'):
        a.locate(target=TARGET,after_sequence=0)
    a.actions.execute.assert_not_called()


@pytest.mark.parametrize('budget',[0,-1,True,1.5])
def test_invalid_navigation_budget_never_acquires_or_dispatches(budget):
    a=adapter()
    with pytest.raises(ValueError,match='positive integer'):
        a.locate(target=TARGET,after_sequence=0,max_gestures=budget)
    a.observer.wait_until.assert_not_called();a.actions.execute.assert_not_called()


def test_failed_confirmation_never_seeds_old_target_geometry_as_fresh():
    o=Mock();o.wait_until.side_effect=[_snapshot(i) for i in range(1,5)]
    a=adapter(o);g=(.36,.43)
    a.target_geometry=Mock(side_effect=[g,None,g,g])
    a.anchors.read=Mock(return_value=((TARGET,.43),))
    result=a.locate(target=TARGET,after_sequence=0)
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert result.last_sequence==4 and result.fallbacks==1
    a.actions.execute.assert_not_called()
