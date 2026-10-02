"""Keys acquisition diagnostics and the two fresh concordant-read boundary."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.event_context import event_scope
from bot.event_log import RuntimeEventStream
from bot.ocr import RapidOcrEngine
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_key_facts_reader import read_fresh_key_facts
from bot.trading_key_row_reader import read_key_samples
from bot.trading_row_facts import RowSample, TradingRowReader


def snapshot(sequence):
    image=np.zeros((200,440,3),np.uint8)
    batch=ObservationBatch(sequence,float(sequence),tuple(
        Observation(name,1.,ObservationSource.LOCAL_CV) for name in
        ('landmark.trading_center_title','indicator.trading_keys_active','indicator.trading_keys_rows')))
    return RuntimeSnapshot(FrameSnapshot(image,float(sequence),sequence),batch,
                           ResolvedState(ResolutionStatus.RESOLVED,sequence,float(sequence),base_context='screen.trading'),
                           RuntimeFacts(),FrameGeometry.from_frame(image))


def acquire(monkeypatch, frames, *, events=True, change=None, error=None):
    import bot.trading_key_facts_reader as acquisition
    def read(reader, frame, sequence, diagnostics):
        if error: raise error
        current={}
        for index,key in enumerate(('silver_key','gold_key')):
            value=frames[sequence-1].get(key)
            candidate=dict(item_id=key,identity_method='template',identity_match=value is not None,
                           reason=None if value is not None else 'title_mismatch',ocr_calls=int(value is not None))
            diagnostics[key].append(candidate)
            if value is not None:
                sample=RowSample(key,'keys',.42+index*.14,value,10,sequence)
                if sequence==2 and key=='silver_key' and change: sample=replace(sample,**change)
                current[key]=sample
                candidate.update(sample=vars(sample),parse_result=(value,10),
                                 pair_reads=[dict(raw=f'{value}/10',confidence=.99,parse_result=(value,10))])
        return current
    monkeypatch.setattr(acquisition,'read_key_samples',read)
    sequence=0; waits=[]
    def wait(predicate,**kw):
        nonlocal sequence
        waits.append(kw['after_sequence']);sequence+=1
        result=snapshot(sequence);assert predicate(result);return result
    recorded=[]
    sink=RuntimeEventStream((recorded.append,)) if events is True else events
    result=read_fresh_key_facts(SimpleNamespace(wait_until=wait),Mock(),after_sequence=0,
                              cancel_requested=lambda:False,max_samples=len(frames),events=sink)
    return result,[e.payload() for e in recorded],waits


def event(log,suffix): return next(e for e in log if e['event']==f'trading.keys.facts.{suffix}')


def test_two_complete_reads_stop_early_and_keep_operation_context(monkeypatch):
    with event_scope(run_id='run',flow='monster_wave',operation_id='mw-op'):
        facts,log,waits=acquire(monkeypatch,[{'silver_key':411,'gold_key':1}]*3)
    assert waits==[0,1]
    assert facts.silver_fact.have==411 and facts.gold_fact.have==1
    assert facts.snapshot.sequence==facts.silver_fact.sequence==facts.gold_fact.sequence==2
    assert event(log,'ready')['samples_attempted']==2
    assert event(log,'consensus')['accepted']
    assert all(e['operation_id']=='mw-op' for e in log)
    assert len({e['acquisition_id'] for e in log})==1
    sample=event(log,'sample')
    assert sample['ocr_calls']==2 and sample['snapshot_seconds']>=0 and sample['reader_seconds']>=0
    assert sample['candidates']['silver_key'][0]['pair_reads'][0]['raw']=='411/10'
    json.dumps(log)


@pytest.mark.parametrize('missing',('silver_key','gold_key'))
def test_missing_row_never_produces_facts(monkeypatch,missing):
    values={'silver_key':411,'gold_key':1};del values[missing]
    facts,log,waits=acquire(monkeypatch,[values]*3)
    assert facts is None and len(waits)==3
    assert event(log,'sample')['reason']==f'missing_{missing}'
    assert event(log,'unavailable')['reason']=='samples_exhausted'


def test_incomplete_read_breaks_consecutive_consensus(monkeypatch):
    facts,log,_=acquire(monkeypatch,[{'silver_key':411,'gold_key':1},{'gold_key':1},{'silver_key':411,'gold_key':1}])
    assert facts is None
    assert not any(e['event'].endswith('.consensus') for e in log)


def test_transient_then_two_good_reads_can_recover(monkeypatch):
    facts,log,_=acquire(monkeypatch,[{}, {'silver_key':411,'gold_key':1},{'silver_key':411,'gold_key':1}])
    assert facts is not None and event(log,'ready')['samples_attempted']==3


@pytest.mark.parametrize('change,reason',(
    ({'row_y':.45},'position_mismatch'),({'item_id':'gold_key'},'identity_mismatch'),
    ({'sequence':1},'stale_sequence'),({'have':410},'balances_mismatch')))
def test_consensus_guards_stay_fail_closed(monkeypatch,change,reason):
    facts,log,_=acquire(monkeypatch,[{'silver_key':411,'gold_key':1}]*2,change=change)
    assert facts is None
    assert event(log,'consensus')['comparisons']['silver_key']['reasons']==[reason]


def test_event_sink_failure_changes_neither_reads_nor_result(monkeypatch):
    sink=Mock();sink.record.side_effect=RuntimeError('sink unavailable')
    values=[{'silver_key':411,'gold_key':1}]*2
    facts,_,waits=acquire(monkeypatch,values,events=sink)
    plain,_,plain_waits=acquire(monkeypatch,values,events=None)
    assert facts.silver_fact==plain.silver_fact and waits==plain_waits


def test_reader_exception_keeps_original_error(monkeypatch):
    error=RuntimeError('OCR failed');sink=Mock()
    with pytest.raises(RuntimeError) as raised:
        acquire(monkeypatch,[{}],error=error,events=sink)
    assert raised.value is error
    assert sink.record.call_args.kwargs['reason']=='read_exception'
    assert sink.record.call_args.kwargs['exception_message']=='OCR failed'


@pytest.mark.parametrize('error,reason',((RuntimeWaitCancelled('cancelled'),'cancelled'),
    (RuntimeWaitTimeout(after_sequence=0,timeout=6,last_snapshot=None),'read_exception')))
def test_wait_error_is_not_swallowed(error,reason):
    observer=Mock();observer.wait_until.side_effect=error;sink=Mock()
    with pytest.raises(type(error)):
        read_fresh_key_facts(observer,Mock(),after_sequence=0,cancel_requested=lambda:False,events=sink)
    assert sink.record.call_args.kwargs['reason']==reason


ROOT=Path(__file__).resolve().parents[1]
POSITIVE=[
    ('artifacts/acquisition-inventory-relief-chain/trading-keys-char2/20260910T002334_238388Z_01.png',236,412),
    ('artifacts/acquisition-inventory-relief-chain/trading-keys-char2/20260910T002334_363497Z_02.png',236,412),
    ('artifacts/acquisition-inventory-relief-chain/trading-keys-char2/20260910T002334_485307Z_03.png',236,412),
    ('artifacts/acquisition-inventory-relief-chain/trading-keys-recheck/20260909T224443_033566Z_01.png',229,188),
    ('screencaps/semantic/trading-center/keys-top/01.png',5,9),
    ('artifacts/mw_stabilization/keys_4_9_native.png',4,9),
    ('artifacts/mw_stabilization/keys_failure_native.png',411,1),
    ('artifacts/mw_stabilization/keys_stream_native.png',411,1),
]


@pytest.mark.parametrize('path,silver,gold',POSITIVE)
def test_incremental_keys_evaluator_native_counts(path,silver,gold):
    frame=cv2.imread(str(ROOT/path));assert frame is not None
    details={'silver_key':[],'gold_key':[]}
    facts=read_key_samples(TradingRowReader(RapidOcrEngine()),frame,1,details)
    assert {key:(s.have,s.need) for key,s in facts.items()}=={'silver_key':(silver,10),'gold_key':(gold,10)}
    assert sum(d[0]['ocr_calls'] for d in details.values())==2
    assert all(d[0]['identity_method']=='template' for d in details.values())


@pytest.mark.parametrize('folder',('trading-keys-scrolled','trading-keys-bottom','trading-keys-char2-block','trading-keys-char2-probe'))
def test_incremental_keys_evaluator_rejects_other_rows_and_panels(folder):
    path=next((ROOT/'artifacts/acquisition-inventory-relief-chain'/folder).glob('*.png'))
    frame=cv2.imread(str(path));details={'silver_key':[],'gold_key':[]}
    engine=Mock();engine.recognize.side_effect=AssertionError('OCR on foreign rows')
    assert read_key_samples(TradingRowReader(engine),frame,1,details)=={}
