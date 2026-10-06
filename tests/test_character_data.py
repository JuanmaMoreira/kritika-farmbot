import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import cv2
import numpy as np
import pytest
from bot.character_data import QuickMenuResourceReader, CharacterDataCollector, ResourceSnapshotMode, integer_text
from bot.character_state import CharacterStateStore, character_state_scope,establish_character_state
from bot.geometry import relative_region_to_pixels
from bot.ocr import RapidOcrEngine,OcrResult
from bot.world_boss_state import WorldBossStateReader,WorldBossEligibilityPolicy,WorldBossEligibilityMode,WorldBossPanel
from bot.state import ResolutionStatus

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'tests/fixtures/character_state/manifest.json'

def reconstructed(entry):
    image=np.zeros(entry['frame_shape'],np.uint8)
    h,w=image.shape[:2]
    for item in entry['crops'].values():
        path=ROOT/item['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        x1,y1,x2,y2=relative_region_to_pixels(item['roi'],w,h)
        image[y1:y2,x1:x2]=cv2.imread(str(path))
    return image

def test_real_ocr_acquired_resources_and_wb_paired_numeric_and_blank():
    engine=RapidOcrEngine()
    for entry in json.loads(MANIFEST.read_text(encoding='utf-8'))['entries']:
        image=reconstructed(entry)
        if entry['label'].endswith('qm'):
            s=SimpleNamespace(frame=SimpleNamespace(image=image),state=SimpleNamespace(status=ResolutionStatus.UNKNOWN,overlays={'menu.quick'}))
            assert QuickMenuResourceReader(engine).read(s,origin=entry['origin'])==entry['expected']
        else:
            s=SimpleNamespace(frame=SimpleNamespace(image=image),state=SimpleNamespace(status=ResolutionStatus.RESOLVED,base_context='screen.world_boss',overlays=()))
            result=WorldBossStateReader(engine).read(s)
            assert result.participated is entry['expected']['participated']
            assert result.remaining_seconds==entry['expected']['remaining_seconds']

@pytest.mark.parametrize('text,expected',[('0',0),('7',7),('999',999),('12,345,678',12345678),('12.345',None),('12,34',None),('',None),('--',None),('O',None),('1/2',None),('-1',None),('12 345',None)])
def test_strict_resource_parser_never_writes_unreadable_zero(text,expected):
    assert integer_text(OcrResult(text,.99))==expected
    assert integer_text(OcrResult('0',.94)) is None

@pytest.mark.parametrize('mode',['OFF','BEFORE_CHARACTER_ROTATION'])
def test_explicit_trigger_failures_continue_and_keep_snapshot(tmp_path,mode):
    store=CharacterStateStore(tmp_path/'state.db')
    events=Mock()
    reader=Mock(read=Mock(side_effect=ValueError('OCR error')))
    collector=CharacterDataCollector(reader,events=events,mode=mode)
    values=dict(lapiz=5,dark_essence=6,light_essence=7,nature_essence=8,k_coins=9)
    store.resources('monk',values)
    with character_state_scope():
        establish_character_state(store,'monk')
        collector.before_rotation(object(),origin='screen.lobby')
    assert reader.read.call_count==(0 if mode=='OFF' else 1)
    assert next(r for r in store.rows() if r['character_id']=='monk')['lapiz']==5
    store.close()

def test_no_identity_no_resource_read_and_no_cross_character(tmp_path):
    store=CharacterStateStore(tmp_path/'state.db')
    reader=Mock()
    collector=CharacterDataCollector(reader,events=Mock())
    with character_state_scope():
        collector.before_rotation(object(),origin='screen.lobby')
    reader.read.assert_not_called()
    assert all(r['lapiz'] is None for r in store.rows())
    store.close()


@pytest.mark.parametrize('first,second,expected',[
    (OcrResult('172',.89),OcrResult('172',.999),172),
    (OcrResult('172',.89),OcrResult('173',.999),None),
    (OcrResult('172',.89),OcrResult('172',.94),None),
    (OcrResult('',0),OcrResult('0',.999),None),
])
def test_padded_same_frame_retry_retains_strict_gate_and_text_agreement(first,second,expected):
    results=[first,second]+[OcrResult('1',.999)]*4
    engine=Mock(recognize=Mock(side_effect=results))
    snapshot=SimpleNamespace(sequence=1,frame=SimpleNamespace(image=np.zeros((100,200,3),np.uint8)),
        state=SimpleNamespace(status=ResolutionStatus.UNKNOWN,overlays={'menu.quick'}))
    value=QuickMenuResourceReader(engine).read(snapshot,origin='screen.lobby')
    if expected is None:
        assert value is None and engine.recognize.call_count==2
    else:
        assert value['lapiz']==expected and engine.recognize.call_count==6
    shapes=[c.args[0].shape for c in engine.recognize.call_args_list]
    pad=max(1,round(shapes[0][0]*.16))
    assert shapes[1][:2]==(shapes[0][0]+pad*2,shapes[0][1]+pad*2)

@pytest.mark.parametrize('damage,rank,expected',[
    ('Most Damage : 10,000','Overall Rank: Rank 104 (6.24%)',True),
    ('Most Damage : -','Overall Rank: Rank -- (--%)',False),
    ('Most Damage : --','Overall Rank: Rank -- (--%)',False),
    ('Most Damage : -','Overall Rank: Rank 104 (6.24%)',None),
    ('Most Damage : 10,000','Overall Rank: Rank -- (--%)',None),
    ('','Overall Rank: Rank -- (--%)',None)])
def test_wb_paired_semantics_not_weak_absence(damage,rank,expected):
    reader=WorldBossStateReader(Mock(recognize=Mock(side_effect=[OcrResult(t,.99) for t in (damage,rank,'1d4h14m')])))
    s=SimpleNamespace(frame=SimpleNamespace(image=np.zeros((100,200,3),np.uint8)),state=SimpleNamespace(status=ResolutionStatus.RESOLVED,base_context='screen.world_boss',overlays=()))
    assert reader.read(s).participated is expected

def test_previous_reward_is_eligible_and_independent_of_daily_quest():
    engine=Mock()
    snapshot=SimpleNamespace(state=SimpleNamespace(overlays={'popup.world_boss_previous_rewards'}))
    panel=WorldBossStateReader(engine).read(snapshot)
    assert panel==WorldBossPanel(False,True)
    engine.recognize.assert_not_called()
    policy=WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED',reader=Mock(read=Mock(return_value=panel)))
    assert policy.inspect(snapshot) is True

@pytest.mark.parametrize('mode',list(WorldBossEligibilityMode))
def test_panel_tracking_does_not_change_general_or_daily_policy(tmp_path,mode):
    store=CharacterStateStore(tmp_path/'state.db')
    store.clock.calibrate(3600)
    reader=Mock(read=Mock(return_value=WorldBossPanel(True,False)))
    policy=WorldBossEligibilityPolicy(mode,reader=reader)
    with character_state_scope():
        establish_character_state(store,'monk')
        decision=policy.inspect(SimpleNamespace(timestamp=__import__('time').monotonic()))
        assert decision is (mode is not WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED)
        assert store.operational('monk')['wb_participated']==1
    store.close()

def test_current_wb_fresh_panel_without_countdown_keeps_clock_unknown(tmp_path):
    import time
    store=CharacterStateStore(tmp_path/'state.db')
    reader=Mock(read=Mock(return_value=WorldBossPanel(False,False)))
    policy=WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED',reader=reader,store=store)
    with character_state_scope():
        establish_character_state(store,'monk')
        assert policy.inspect(SimpleNamespace(timestamp=time.monotonic())) is True
        assert store.operational('monk')['wb_participated']==0
        assert store.clock.state() is None
    store.close()

def test_raid_event_persists_before_later_cleanup_failure(tmp_path):
    from test_world_boss_flow import build_flow,happy_inputs,fact_result,SCREEN_LOBBY,auto_result
    from bot.character_state import CharacterStateEvents
    from bot.event_log import RuntimeEventStream
    store=CharacterStateStore(tmp_path/'state.db')
    store.clock.calibrate(3600)
    waits,observes,transitions=happy_inputs()
    auto=Mock()
    auto.ensure_on_quick.return_value=auto_result()
    flow,*_=build_flow(sapphire_read=fact_result('resource.sapphires',10,1,SCREEN_LOBBY),
                      timer_read=fact_result('battle.timer_remaining',20,9,'screen.world_boss_battle'),
                      waits=waits,observes=observes,transitions=transitions,auto=auto)
    original=flow.activity.verified_transition.execute
    def fail_cleanup(name,*args,**kwargs):
        if name=='world_boss.continue_after_raid':
            raise ValueError('cleanup failure after verified raid')
        return original(name,*args,**kwargs)
    flow.activity.verified_transition.execute=fail_cleanup
    flow.activity.events=RuntimeEventStream((CharacterStateEvents(),))
    with character_state_scope():
        establish_character_state(store,'monk')
        result=flow.run()
    assert result.status.value=='failed'
    assert store.operational('monk')['wb_participated']==1
    assert store.operational('monk')['wb_source']=='RAID_COMPLETE'
    store.close()
