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
    result=a.locate(target=TARGET,after_sequence=0)
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert a.actions.execute.call_count==2
    actions=[c.args[0] for c in a.actions.execute.call_args_list]
    assert all(isinstance(s,Swipe) and s.start[0]==s.end[0]==.33 for s in actions)
    assert actions[0].start[1]>actions[0].end[1]
    assert actions[1].start[1]<actions[1].end[1]


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
