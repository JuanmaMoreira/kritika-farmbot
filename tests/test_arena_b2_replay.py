"""Curated B2 pixels establish parsing; synthetic barriers only exercise safety."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import cv2
import pytest
from bot.arena_flow_reader import ArenaFlowReader, ArenaFlowVisuals
from bot.arena_semantics import ArenaSingleExecution, ArenaDifficulty
from bot.capture import FrameSnapshot
from bot.ocr import RapidOcrEngine

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=json.loads((ROOT/'tests/fixtures/arena_b2/manifest.json').read_text())

def frame(name):
    return cv2.imread(str(ROOT/'tests/fixtures/arena_b2'/f'{name}.png'))

@pytest.mark.parametrize('entry',MANIFEST['entries'],ids=lambda e:e['id'])
def test_pixels_provenance_and_acquired_surface(entry):
    assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256']
    v=ArenaFlowVisuals(); image=frame(entry['id'])
    predicate={'challenge':v.clean_challenge,'select_mode':v.select_mode,
        'quick_menu':v.quick_menu,'single_result':v.single_result,
        'single_active':v.single_active,'selection':v.selection,'lobby':v.lobby,'ranking':v.ranking}[entry['context']]
    assert predicate(image)
    if entry['context']!='single_result': assert not v.single_result(image)
    if entry['context']=='quick_menu': assert not v.clean_challenge(image)

def test_single_terminal_has_separate_receipt_and_complete_positive_panel():
    reader=ArenaFlowReader(object(),clock=lambda:100.)
    snap=FrameSnapshot(frame('single_victory'),100.,2)
    receipt=ArenaSingleExecution('run','source',ArenaDifficulty.EASY,8,99.,1,True,106,101068)
    assert reader.single_terminal(snap,receipt,run_id='run',source_id='source')
    assert not reader.single_terminal(snap,replace(receipt,start_verified=False),run_id='run',source_id='source')
    assert not reader.single_terminal(snap,receipt,run_id='foreign',source_id='source')
    assert not reader.single_terminal(replace(snap,sequence=1),receipt,run_id='run',source_id='source')
    assert not reader.single_terminal(replace(snap,timestamp=90.),receipt,run_id='run',source_id='source')
    assert reader.read(snap,receipt,run_id='run',source_id='source') is None
    partial=snap.image.copy(); partial[int(.8*partial.shape[0]):]=0
    assert not reader.single_terminal(replace(snap,image=partial),receipt,run_id='run',source_id='source')

@pytest.mark.parametrize('name,badges,stocks',[
    ('challenge_native_off',106,(None,317,714)),('gold_deficit',106,(-2,317,714)),
    ('single_challenge_empty',98,(0,309,706))])
def test_native_economic_replay(name,badges,stocks):
    reader=ArenaFlowReader(RapidOcrEngine(),clock=lambda:100.)
    snap=FrameSnapshot(frame(name),100.,2)
    facts=reader.economy(snap)
    assert facts is not None and facts.available_badges==badges and facts.free_buffs==(None,None,stocks[2])

def test_single_closing_native_balances_replay():
    reader=ArenaFlowReader(RapidOcrEngine(),clock=lambda:100.)
    values=reader.balances(FrameSnapshot(frame('single_selection_after'),100.,2))
    assert values is not None
    assert (values.badges,values.gold,values.karats)==(98,9045377472,101076)
