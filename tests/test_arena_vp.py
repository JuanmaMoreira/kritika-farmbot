from datetime import datetime, timezone
from types import SimpleNamespace as NS
import sqlite3
import cv2
import numpy as np
import pytest
from bot.arena_vp import ArenaVictoryPointReader, parse_victory_points
from bot.character_state import CharacterStateStore, character_state_scope, establish_character_state
from bot.capture import FrameSnapshot
from bot.ocr import OcrResult, RapidOcrEngine
from bot.arena_flow_reader import ArenaFlowVisuals

@pytest.mark.parametrize('text,expected', [('Victory Point(s): 154,260',154260),
    ('Victory Points: 0',0),('Victory Point(s): 1,234,567',1234567),
    ('Victory Point(s): 154,26',None),('Victory Point(s): 154,',None),
    ('Victory Point(s): 12 34',None),('Acquired Victory Points: 154,260',None),
    ('Victory Point(s): 154,260 Rank 2',None),('154260',None)])
def test_parser(text,expected):
    assert parse_victory_points(text,.99)==expected
    assert parse_victory_points(text,.94) is None

def ts(value):return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()

def test_week_reset_reopen_identity_and_late_write(tmp_path):
    now=[ts('2026-10-11T12:00:00')]
    s=CharacterStateStore(tmp_path/'state.db',now=lambda:now[0])
    period=s.clock.arena_period()
    assert period=='2026-10-05'
    assert s.arena_victory_points('monk',154260,observed_at=now[0],period=period)
    assert s.arena_victory_points('eilla',0,observed_at=now[0],period=period)
    assert s.operational('ice_warlock')['arena_vp'] is None
    s.close()
    now[0]=ts('2026-10-12T06:59:59')
    s=CharacterStateStore(tmp_path/'state.db',now=lambda:now[0])
    assert s.operational('monk')['arena_vp']==154260
    assert s.operational('eilla')['arena_vp']==0
    s.close()
    now[0]+=1
    s=CharacterStateStore(tmp_path/'state.db',now=lambda:now[0])
    assert all(r['arena_vp'] is None for r in s.rows())
    assert not s.arena_victory_points('monk',9,observed_at=now[0]-1,period=period)
    new=s.clock.arena_period()
    assert s.arena_victory_points('monk',10,observed_at=now[0],period=new)
    assert not s.arena_victory_points('monk',11,observed_at=now[0]-1,period=new)
    assert s.operational('monk')['arena_vp']==10
    s.close()

def test_reuse_calibrated_world_boss_boundary(tmp_path):
    at=ts('2026-10-11T07:00:00')
    s=CharacterStateStore(tmp_path/'state.db',now=lambda:at)
    # Countdown calibrated with a revised seasonal phase at08:00Z.
    s.clock.calibrate(25*3600-1800)
    assert s.clock.arena_period(ts('2026-10-12T07:59:59'))=='2026-10-05'
    assert s.clock.arena_period(ts('2026-10-12T08:00:00'))=='2026-10-12'
    s.close()

def test_small_countdown_correction_in_same_week_does_not_erase_vp(tmp_path):
    at=ts('2026-10-10T12:00:00')
    s=CharacterStateStore(tmp_path/'state.db',now=lambda:at)
    s.clock.calibrate(19*3600-1800)
    period=s.clock.arena_period()
    assert s.arena_victory_points('monk',154260,observed_at=at,period=period)
    s.clock.calibrate(19*3600-1800+30)
    assert s.clock.arena_period()==period
    assert s.operational('monk')['arena_vp']==154260
    s.close()

def test_conservative_v1_migration(tmp_path):
    path=tmp_path/'state.db'
    s=CharacterStateStore(path);s.ads('monk','OBSERVED',observed_count=1);s.close()
    db=sqlite3.connect(path)
    for column in ('arena_vp','arena_vp_observed_at','arena_vp_period'):
        db.execute(f'ALTER TABLE operational DROP COLUMN {column}')
    db.execute('PRAGMA user_version=1');db.commit();db.close()
    s=CharacterStateStore(path)
    assert s.operational('monk')['stage_ads_remaining']==1
    assert all(r['arena_vp'] is None for r in s.rows())
    s.close()

def test_optional_reader_failure_does_not_erase_prior_value(tmp_path):
    at=ts('2026-10-10T12:00:00')
    s=CharacterStateStore(tmp_path/'state.db',now=lambda:at)
    s.arena_victory_points('monk',5,observed_at=at,period=s.clock.arena_period())
    engine=NS(recognize=lambda _:(_ for _ in ()).throw(RuntimeError('OCR unavailable')))
    reader=ArenaVictoryPointReader(engine,clock=lambda:100.)
    frame=FrameSnapshot(np.zeros((100,200,3),np.uint8),100.,1)
    visuals=NS(selection=lambda _:True,ranking=lambda _:False,quick_menu=lambda _:False)
    with character_state_scope():
        establish_character_state(s,'monk')
        reader.observe_character(frame,visuals)
    assert s.operational('monk')['arena_vp']==5
    s.close()


def test_reader_observation_cannot_cross_monday_reset_during_ocr(tmp_path):
    wall=[ts('2026-10-12T06:59:59')]
    mono=[100.]
    store=CharacterStateStore(tmp_path/'state.db',now=lambda:wall[0])
    reader=ArenaVictoryPointReader(NS(),clock=lambda:mono[0])
    def slow_read(*args,**kwargs):
        wall[0]+=2.;mono[0]+=2.
        return 154260
    reader.read=slow_read
    frame=FrameSnapshot(np.zeros((100,200,3),np.uint8),100.,1)
    with character_state_scope():
        establish_character_state(store,'monk')
        reader.observe_character(frame,NS())
    assert store.clock.arena_period()=='2026-10-12'
    assert store.operational('monk')['arena_vp'] is None
    store.close()

@pytest.mark.parametrize('fails',[False,True])
def test_auto_repeat_reads_once_in_existing_return_and_never_adds_taps(fails):
    from test_arena_b2 import ReturnWorld
    from test_arena_flow import flow,C
    w=ReturnWorld();f=flow(w,return_context='screen.lobby');seen=[]
    def observe(frame,visuals,**kwargs):
        assert w.surface=='lobby' and visuals.selection(frame.image) and f.batch_result is not None
        seen.append(frame.sequence)
        if fails:raise RuntimeError('optional OCR failed')
    f.victory_points=NS(observe_character=observe)
    r=f.run()
    assert r.succeeded and len(seen)==1 and w.inputs[-3:]==[C.BACK]*3
    assert w.start_count==1


def test_slow_optional_failure_cannot_invalidate_return_or_add_observations():
    from test_arena_b2 import ReturnWorld
    from test_arena_flow import flow,C
    w=ReturnWorld();f=flow(w,return_context='screen.lobby');seen=[]
    def observe(frame,visuals,**kwargs):
        seen.append((w.surface,w.seq,visuals.selection(frame.image)))
        w.sleep(20.)
        raise RuntimeError('slow optional OCR failure')
    f.victory_points=NS(observe_character=observe)
    result=f.run()
    assert result.succeeded and seen==[('lobby',w.seq,True)]
    assert w.start_count==1 and w.inputs[-3:]==[C.BACK]*3

def test_no_selection_navigation_means_no_vp_attempt():
    from test_arena_flow import World,flow
    w=World();f=flow(w);seen=[]
    f.victory_points=NS(observe_character=lambda *a,**kw:seen.append(1))
    assert f.run().succeeded and not seen

@pytest.mark.parametrize('path,expected', [
    ('artifacts/arena_stability_20261010/representative02/arena_0_return_selection.png',182070),
    ('artifacts/arena_b2/20261008/30-productive-smoke/return_selection.png',128795),
    ('artifacts/arena-hil/20261008/mode-arena-after/20261008T194656_589975Z_01.png',0)])
def test_curated_selection_replay(path,expected):
    from pathlib import Path
    if not Path(path).exists():pytest.skip('local curated source unavailable')
    frame=FrameSnapshot(cv2.imread(path),100.,1)
    reader=ArenaVictoryPointReader(RapidOcrEngine(),clock=lambda:100.)
    assert reader.read(frame,ArenaFlowVisuals())==expected
    # Partial physical occlusion is unreadable; no plausible prefix accepted.
    image=frame.image.copy();h,w=image.shape[:2]
    image[round(.228*h):round(.270*h),round(.594*w):round(.643*w)]=0
    assert reader.read(FrameSnapshot(image,100.,2),ArenaFlowVisuals()) is None
