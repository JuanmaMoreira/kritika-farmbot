"""Causal replay: Ice Warlock 215 -> 15 Silver, then OCR 15/10J.

Native failure frames were downscaled by retention. Events preserve the exact
old OCR result; the pixel fixture is newly acquired from the preserved state,
not an invented restoration of those original native pixels.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.ocr import OcrResult, RapidOcrEngine
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitTimeout
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_key_facts_reader import execute_productive_key_trade, read_fresh_key_facts
from bot.trading_key_row_reader import read_key_samples, _prepare_pair
from bot.trading_keys import KeyTradeOperation
from bot.trading_operation import TradeOutcome, TradePanelFact, TradeQuantity, TradeQuantityMode
from bot.trading_row_facts import TradingRowFact, TradingRowReader

ROOT = Path(__file__).parent / 'fixtures/trading_session_a94ac2e7'
MANIFEST = json.loads((ROOT / 'manifest.json').read_text())
EVENTS = {e['event_sequence']: e for e in json.loads((ROOT / 'events.json').read_text())}


def frame():
    entry = MANIFEST['patches'][0]
    data = (ROOT / entry['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry['sha256']
    width, height = entry['geometry']
    image = np.zeros((height, width, 3), np.uint8)
    x, y, xx, yy = entry['box']
    image[y:yy, x:xx] = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return image


def snapshot(sequence, image):
    timestamp = float(sequence)
    observations = tuple(Observation(name, 1., ObservationSource.LOCAL_CV) for name in (
        'landmark.trading_center_title', 'indicator.trading_keys_active', 'indicator.trading_keys_rows'))
    return RuntimeSnapshot(FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, observations),
        ResolvedState(ResolutionStatus.RESOLVED, sequence, timestamp, base_context='screen.trading'),
        RuntimeFacts(), FrameGeometry.from_frame(image))


class Observer:
    def __init__(self, image):
        self.image = image
        self.sequence = 0

    def wait_until(self, predicate, *, after_sequence, timeout, **kwargs):
        for _ in range(4):
            self.sequence = max(self.sequence, after_sequence) + 1
            item = snapshot(self.sequence, self.image)
            if predicate(item):
                return item
        raise RuntimeWaitTimeout(after_sequence=after_sequence, timeout=timeout, last_snapshot=item)


def test_preserved_native_keys_pixels_accredit_two_fresh_complete_reads():
    facts = read_fresh_key_facts(Observer(frame()), TradingRowReader(RapidOcrEngine()),
        after_sequence=93109, cancel_requested=lambda: False, max_samples=2)
    assert facts is not None
    assert (facts.silver_fact.have, facts.silver_fact.need) == (6, 10)
    assert (facts.gold_fact.have, facts.gold_fact.need) == (15, 10)
    assert facts.snapshot.sequence == facts.gold_fact.sequence == facts.silver_fact.sequence == 93111


@pytest.mark.parametrize('recorded_failure', [True, False])
def test_failed_trade_effect_replay_never_retries_economically(recorded_failure):
    image = frame()
    observer = Observer(image)
    row = TradingRowFact(**EVENTS[25031]['before_fact'])
    # Replay the exact original OCR evidence, rather than claiming that a new
    # capture reproduces the old H264 compression pixels.
    recorded = EVENTS[25010]['candidates']
    reads = [recorded[key][0]['pair_reads'][0] for key in ('silver_key', 'gold_key')]
    class RecordedEngine:
        def __init__(self): self.index = 0
        def recognize(self, image):
            entry = reads[self.index % 2]; self.index += 1
            return OcrResult(entry['raw'], entry['confidence'])
    reader = TradingRowReader(RecordedEngine() if recorded_failure else RapidOcrEngine())
    def read_facts(barrier):
        return read_fresh_key_facts(observer, reader, after_sequence=barrier,
            cancel_requested=lambda: False)
    panels = {93035: TradePanelFact('gold_key', 215, 10, (1, 20), sequence=93035),
              93036: TradePanelFact('gold_key', 215, 10, (20, 20), sequence=93036)}
    actions = []
    result = execute_productive_key_trade(operation=KeyTradeOperation.SILVER_TO_GOLD,
        snapshot=snapshot(93034, image), row_fact=row,
        quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED), observer=observer,
        actions=SimpleNamespace(execute=lambda intent, *args, **kwargs: actions.append(intent)),
        panel_reader=SimpleNamespace(read_snapshot=lambda item, **kwargs: panels.get(item.sequence)),
        read_facts=read_facts, cancel_requested=lambda: False, clock=lambda: 93035.5)
    assert result.inputs == ('tap_row', 'tap_max', 'tap_confirm')
    assert len(actions) == 3
    if recorded_failure:
        assert result.outcome is TradeOutcome.FAILED
        assert result.reason == EVENTS[25031]['reason'] == 'after_fact_unreadable'
    else:
        assert result.outcome is TradeOutcome.SUCCESS
        assert result.after_fact.have == 15
        assert result.fresh_key_facts.silver_fact.have == 6


@pytest.mark.parametrize('have,selected,target,max_needed', [(15, 1, 1, False), (215, 1, 20, True)])
def test_keys_useful_maximum_and_normal_quantity_action(have, selected, target, max_needed):
    image = frame(); observer = Observer(image)
    before = TradingRowFact('gold_key', 'keys', .5661764705882354, have, 10, 10)
    panels = {11: TradePanelFact('gold_key', have, 10, (selected, 20), sequence=11)}
    if max_needed:
        panels[12] = TradePanelFact('gold_key', have, 10, (target, 20), sequence=12)
    after = TradingRowFact('gold_key', 'keys', before.row_y, have - target*10, 10, 20)
    actions=[]
    result=execute_productive_key_trade(operation=KeyTradeOperation.SILVER_TO_GOLD,
        snapshot=snapshot(10,image),row_fact=before,quantity=TradeQuantity(TradeQuantityMode.MAX_ALLOWED),
        observer=observer,actions=SimpleNamespace(execute=lambda intent,*args,**kwargs:actions.append(intent)),
        panel_reader=SimpleNamespace(read_snapshot=lambda item,**kwargs:panels.get(item.sequence)),
        read_facts=lambda barrier:SimpleNamespace(gold_fact=after,silver_fact=before),
        cancel_requested=lambda:False,clock=lambda:11.5)
    assert result.outcome is TradeOutcome.SUCCESS
    assert result.inputs.count('tap_max') == int(max_needed)
    assert result.inputs.count('tap_confirm') == 1
    if not max_needed:
        assert 'max_skipped:already_selected' in result.evidence


def test_numeric_crop_excludes_off_line_icon_corner_without_losing_digits():
    image=frame(); height,width=image.shape[:2]
    box=EVENTS[25010]['candidates']['gold_key'][0]['localized_roi']
    l,t,r,b=box
    cell=image[int(t*height):int(b*height),int(l*width):int(r*width)].copy()
    # Isolated white edge on the icon is within the old size filter but does
    # not align with digit tops. This protects the demonstrated J failure.
    cv2.rectangle(cell,(125,12),(140,44),(20,20,20),-1)
    cv2.line(cell,(133,18),(133,35),(255,255,255),2)
    cv2.line(cell,(127,35),(133,35),(255,255,255),2)
    prepared=_prepare_pair(cell,height,width)
    assert prepared is not None and prepared.shape[1] < 330
    read=RapidOcrEngine().recognize(prepared)
    assert read.text == '15/10' and read.confidence >= .90
