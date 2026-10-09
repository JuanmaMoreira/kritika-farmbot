"""Portable Arena replay. Synthetic contracts never establish physical game GT."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.arena_reader import ArenaDetector, ArenaResultReader, ArenaVisuals, USED_ROI, WON_ROI, crop, parse_integer
from bot.arena_semantics import *
from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.controlled_wait import ControlledWait, ControlledWaitOutcome
from bot.observations import ObservationBatch
from bot.ocr import OcrResult, RapidOcrEngine
from bot.perception import build_default_perception, build_arena_perception, STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'tests/fixtures/arena_phase_a'
MANIFEST = json.loads((DIRECTORY/'manifest.json').read_text(encoding='utf8'))


def image(name):
    return cv2.imread(str(DIRECTORY/(name+'.png')))


def execution(**changes):
    return replace(ArenaBatchExecution('batch', 'source', ArenaDifficulty.EASY, 8, 10., 1, True), **changes)


class PixelOcr:
    """Recorded/synthetic OCR keyed to crops, never invocation position."""
    def __init__(self, frame, used='104', won='104', confidence=.999):
        self.reads = {}
        self.calls = 0
        for roi, text in ((USED_ROI, used), (WON_ROI, won)):
            part = crop(frame, roi)
            for prepared in (part, cv2.cvtColor(part, cv2.COLOR_BGR2GRAY)):
                prepared = cv2.resize(prepared, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                self.reads[hashlib.sha256(prepared.tobytes()).hexdigest()] = OcrResult(text, confidence)

    def recognize(self, prepared):
        self.calls += 1
        return self.reads.get(hashlib.sha256(prepared.tobytes()).hexdigest(), OcrResult('',0.))


def read(reader, frame, receipt=None, timestamp=100., sequence=2, **kw):
    return reader.read(FrameSnapshot(frame, timestamp, sequence), receipt or execution(),
                       run_id=kw.pop('run_id','batch'), source_id=kw.pop('source_id','source'), **kw)


def test_fixture_and_asset_provenance():
    for entry in MANIFEST['entries']:
        assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest() == entry['sha256']
    assets = json.loads((ROOT/'datasets/arena_visual_assets_manifest.json').read_text())
    for asset in assets['assets']:
        assert hashlib.sha256((ROOT/asset['path']).read_bytes()).hexdigest() == asset['sha256']
    assert all(e['source'].startswith('screencaps/arena_hil/') for e in MANIFEST['entries'])


@pytest.mark.parametrize('name', ['native','stream','stream_late'])
def test_terminal_native_and_stream_recorded_104(name):
    frame = image(name)
    reader = ArenaResultReader(PixelOcr(frame), clock=lambda:100.)
    result = read(reader, frame)
    assert (result.used_tickets, result.won_tickets, result.lost_tickets, result.winrate) == (104,104,0,1.)
    assert result.difficulty is ArenaDifficulty.EASY and result.multiplier == 8
    assert result.provenance.sequence == 2 and result.provenance.run_id == 'batch'
    assert reader.ocr_calls == 4


@pytest.mark.parametrize('used,won,expected', [
    ('104','72',(104,72)), ('104','0',(104,0)), ('80','16',(80,16)),
    ('104','105',None), ('0','0',None), ('','0',None), ('104','',None),
    ('10?','104',None), ('104','1O4',None), ('104','10 4',None), ('104','-1',None),
])
def test_explicitly_synthetic_ocr_contracts(used, won, expected):
    frame = image('native')
    reader = ArenaResultReader(PixelOcr(frame,used,won), clock=lambda:100.)
    result = read(reader,frame)
    assert (None if result is None else (result.used_tickets,result.won_tickets)) == expected


def test_low_confidence_and_multiline_are_unknown():
    frame = image('native')
    assert read(ArenaResultReader(PixelOcr(frame,confidence=.94),clock=lambda:100.),frame) is None
    ocr = PixelOcr(frame)
    ocr.reads = {k: replace(v,metadata=(('line_count',2),)) for k,v in ocr.reads.items()}
    assert read(ArenaResultReader(ocr,clock=lambda:100.),frame) is None


@pytest.mark.parametrize('name', ['partial1','partial2','config','insufficient','ranking','selection',
                                 'easy_off','battle','bag_full','foreign_lobby','foreign_battle_select'])
def test_not_terminal_or_h264_corruption_rejected_before_ocr(name):
    frame = image(name)
    ocr = PixelOcr(frame)
    assert read(ArenaResultReader(ocr,clock=lambda:100.),frame) is None
    assert ocr.calls == 0


def test_shared_title_other_mode_and_partially_corrupt_number():
    frame = image('native')
    visuals = ArenaVisuals()
    # SYNTHETIC other-mode dialog retains shared title but lacks Badge label.
    crop(frame, visuals._specs['badge_label']['roi'])[:] = 0
    assert visuals.has(frame,'result_title')
    assert read(ArenaResultReader(PixelOcr(frame),clock=lambda:100.),frame) is None
    # SYNTHETIC half-erased digit does not reuse the original OCR result.
    original = image('native'); ocr = PixelOcr(original)
    broken = original.copy(); part = crop(broken,WON_ROI); part[:,part.shape[1]//2:] = 0
    assert read(ArenaResultReader(ocr,clock=lambda:100.),broken) is None


@pytest.mark.parametrize('changes', [dict(difficulty=None),dict(multiplier=None),dict(multiplier=1),
                                     dict(difficulty='EASY'),dict(multiplier=True),
                                     dict(start_verified=False),dict(run_id='other'),dict(source_id='other')])
def test_unaccredited_execution_rejected(changes):
    frame = image('native'); ocr = PixelOcr(frame)
    assert read(ArenaResultReader(ocr,clock=lambda:100.),frame,execution(**changes)) is None
    assert ocr.calls == 0


@pytest.mark.parametrize('timestamp,sequence', [(97.,2),(101.,2),(10.,2),(100.,1)])
def test_stale_future_and_pre_start_frames(timestamp, sequence):
    frame = image('native')
    assert read(ArenaResultReader(PixelOcr(frame),clock=lambda:100.),frame,timestamp=timestamp,sequence=sequence) is None


def test_no_cross_frame_accumulation_or_ocr_preprocessing_disagreement():
    frame = image('native'); ocr = PixelOcr(frame,won='')
    reader = ArenaResultReader(ocr,clock=lambda:100.)
    assert read(reader,frame) is None
    ocr.reads = PixelOcr(frame,used='',won='104').reads
    assert read(reader,frame,sequence=3) is None
    ocr.reads = PixelOcr(frame).reads
    gray = cv2.resize(cv2.cvtColor(crop(frame,WON_ROI),cv2.COLOR_BGR2GRAY),None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
    ocr.reads[hashlib.sha256(gray.tobytes()).hexdigest()] = OcrResult('10',.999)
    assert read(reader,frame,sequence=4) is None


def test_cancellation_during_ocr_and_expired_lazy_load():
    frame = image('native'); ocr = PixelOcr(frame)
    reader = ArenaResultReader(ocr,clock=lambda:100.)
    assert read(reader,frame,cancel_requested=lambda:True) is None
    assert ocr.calls == 0
    assert read(reader,frame,cancel_requested=lambda:ocr.calls>=2) is None
    assert ocr.calls == 2
    now = [100.]
    class SlowOcr(PixelOcr):
        def recognize(self, prepared):
            now[0] += .6
            return super().recognize(prepared)
    assert read(ArenaResultReader(SlowOcr(frame),clock=lambda:now[0]),frame) is None


@pytest.mark.parametrize('name,difficulty,buffs', [
    ('easy_off',ArenaDifficulty.EASY,(False,False,False)),
    ('buff1_on',ArenaDifficulty.EASY,(True,False,False)),
    ('buff12_on',ArenaDifficulty.EASY,(True,True,False)),
    ('normal',ArenaDifficulty.NORMAL,(True,True,False)),
    ('hard',ArenaDifficulty.HARD,(True,True,False)),
    ('hard_buff1_off',ArenaDifficulty.HARD,(False,True,False)),
    ('hard_off',ArenaDifficulty.HARD,(False,False,False)),
])
def test_preparation_facts(name,difficulty,buffs):
    facts = ArenaVisuals().preparation(image(name))
    assert facts.difficulty == difficulty and facts.buffs == buffs and facts.x8 is True


def test_modal_layering_and_default_scope_integration():
    detector = ArenaDetector(); resolver = build_default_resolver()
    for name in ('selection','easy_off','normal','hard'):
        state = resolver.resolve(ObservationBatch(1,1.,detector.detect(image(name))))
        assert state.base_context == SCREEN_ARENA and not state.overlays
    state = resolver.resolve(ObservationBatch(2,2.,detector.detect(image('config'))))
    assert state.base_context == SCREEN_ARENA and 'popup.arena_auto_config' in state.overlays
    assert ArenaVisuals().upon_defeat(image('config')) is False
    assert ArenaVisuals().preparation(image('config')).difficulty is None
    for name, modal in [('native','popup.arena_batch_result'),('ranking','popup.arena_new_ranking'),
                        ('insufficient','popup.arena_insufficient_badge')]:
        state = resolver.resolve(ObservationBatch(3,3.,detector.detect(image(name))))
        assert modal in state.overlays
    assert ArenaDetector in STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES
    assert any(isinstance(d,ArenaDetector) for d in build_default_perception().detectors)
    assert len(build_arena_perception().detectors) == 1


def test_synthetic_reusable_selected_and_unselected_indicators():
    # No live buff3 activation or x8 OFF transition is asserted by this fixture.
    visuals = ArenaVisuals(); frame = image('easy_off')
    for name in ('buff3_on','x8_off'):
        part = crop(frame,visuals._specs[name]['roi'])
        part[:] = cv2.resize(visuals._templates[name],(part.shape[1],part.shape[0]))
    facts = visuals.preparation(frame)
    assert facts.buffs[2] is True and facts.x8 is False
    crop(frame,visuals._specs['buff3_on']['roi'])[:] = 0
    assert visuals.preparation(frame).buffs[2] is None


def test_economy_candidate_and_explicit_reservation():
    assert planned_badges_consumption(106) == 104
    assert planned_badges_consumption(2) == 0
    assert double_points_covered(104,104,reserved=0)
    assert double_points_covered(96,104,reserved=8)
    assert not double_points_covered(96,104)
    assert not double_points_covered(None,104,reserved=8)
    assert not double_points_covered(103,104,reserved=0)


def test_typed_result_integrity_is_a_contract():
    p = ArenaResultProvenance('batch','source',2,'0'*64,.99,.99)
    for used, won in ((0,0),(104,105),(104,-1),(104,True),(True,0)):
        with pytest.raises(ValueError):
            ArenaBatchResult(ArenaDifficulty.EASY,8,used,won,100.,p)
    with pytest.raises(ValueError):
        replace(p,won_confidence=.9)


def test_wait_positive_terminal_only_cancel_timeout_and_duplicate_frames():
    now = [100.]; count = [0]
    reader = ArenaResultReader(PixelOcr(image('native')),clock=lambda:now[0])
    def observe():
        count[0] += 1
        name = 'easy_off' if count[0] < 3 else 'native'
        return FrameSnapshot(image(name),now[0],count[0]+1)
    waiter = ControlledWait(check_interval=3.,clock=lambda:now[0],sleeper=lambda s:now.__setitem__(0,now[0]+s))
    outcome, terminal = reader.wait_terminal(observe,execution(),run_id='batch',source_id='source',timeout=20.,wait=waiter)
    assert outcome.succeeded and terminal.sequence == 4 and reader.ocr_calls == 0
    count[0]=0
    outcome, terminal = reader.wait_terminal(observe,execution(),run_id='batch',source_id='source',timeout=20.,wait=waiter,cancel_requested=lambda:True)
    assert outcome.outcome is ControlledWaitOutcome.CANCELLED and terminal is None and count[0] == 0
    stale = FrameSnapshot(image('native'),50.,2)
    outcome, terminal = reader.wait_terminal(lambda:stale,execution(),run_id='batch',source_id='source',timeout=5.,wait=waiter)
    assert outcome.outcome is ControlledWaitOutcome.TIMEOUT and terminal is None


def test_actual_offline_ocr_on_native_and_stream():
    engine = RapidOcrEngine()
    reader = ArenaResultReader(engine,clock=lambda:100.)
    for name in ('native','stream','stream_late'):
        result = read(reader,image(name))
        assert result and (result.used_tickets,result.won_tickets) == (104,104)


def test_actual_ocr_on_explicitly_synthetic_number_fixtures():
    reader = ArenaResultReader(RapidOcrEngine(),clock=lambda:100.)
    for name, expected in [('synthetic_partial_win',(104,72)),('synthetic_zero',(104,0)),
                            ('synthetic_invalid_won',None)]:
        result = read(reader,image(name))
        assert (None if result is None else (result.used_tickets,result.won_tickets)) == expected


def test_actual_ocr_cannot_accept_a_corrupt_plausible_prefix():
    frame = image('native'); part = crop(frame,WON_ROI)
    part[:,part.shape[1]//2:] = 0
    reader = ArenaResultReader(RapidOcrEngine(),clock=lambda:100.)
    assert read(reader,frame) is None
    assert reader.ocr_calls == 0
