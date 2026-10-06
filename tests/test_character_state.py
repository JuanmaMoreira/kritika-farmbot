import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest

from bot.character_state import (CharacterStateStore, CharacterStateEvents, character_state_scope,
    establish_character_state, SCHEMA_VERSION, DAY, WB_PERIOD)
from bot.world_boss_state import WorldBossEligibilityPolicy, WorldBossEligibilityMode
from bot.character_identity import CHARACTER_IDS

class Clock:
    value=1_000_000.
    def __call__(self): return self.value

@pytest.fixture
def state(tmp_path):
    now=Clock()
    s=CharacterStateStore(tmp_path/'state.db',now=now)
    yield s,now
    s.close()

def calibrate(s,now,remaining=3600):
    s.clock.calibrate(remaining,raw_remaining='1h',observed_at=now())
    return now()+remaining+1800

def test_create_ids_unknown_schema_and_reopen(state):
    s,now=state
    assert len(s.rows())==28
    assert {r['character_id'] for r in s.rows()}==set(CHARACTER_IDS.values())
    assert all(r['stage_ads_remaining'] is None for r in s.rows())
    assert s.db.execute('PRAGMA user_version').fetchone()[0]==SCHEMA_VERSION
    s.ads('monk','OBSERVED',observed_count=1)
    second=CharacterStateStore(s.path,now=now)
    assert second.operational('monk')['stage_ads_remaining']==1
    second.close()

def test_reset_all_rewarded_twice_video0_temporary_and_untouched(state):
    s,now=state
    reset=calibrate(s,now)
    now.value=reset
    s.clock.catch_up()
    assert all(r['stage_ads_remaining']==2 for r in s.rows())
    s.ads('monk','REWARDED')
    assert s.operational('monk')['stage_ads_remaining']==1
    s.ads('monk','REWARDED')
    s.ads('monk','REWARDED')
    assert s.operational('monk')['stage_ads_remaining']==0
    s.ads('halo_mage','TEMPORARILY_UNAVAILABLE')
    assert s.operational('halo_mage')['stage_ads_remaining']==2
    assert s.operational('halo_mage')['ads_last_attempt_status']=='TEMPORARILY_UNAVAILABLE'
    s.ads('halo_mage','DAILY_EXHAUSTED')
    assert s.operational('halo_mage')['stage_ads_remaining']==0
    assert s.operational('cat_acrobat')['stage_ads_remaining']==2

@pytest.mark.parametrize('missed',[1,2,7])
def test_closed_app_catchup_latest_epoch(state,missed):
    s,now=state
    reset=calibrate(s,now)
    s.ads('monk','DAILY_EXHAUSTED')
    now.value=reset+(missed-1)*DAY+3
    reopened=CharacterStateStore(s.path,now=now)
    assert all(r['stage_ads_remaining']==2 for r in reopened.rows())
    assert reopened.clock.state()['next_daily']==reset+missed*DAY
    assert len({r['stage_ads_epoch'] for r in reopened.rows()})==1
    reopened.close()

def test_dynamic_countdown_close_and_seasonal_anchor_recalibration(state):
    s,now=state
    reset=calibrate(s,now,remaining=2*DAY+4000)
    s.wb('monk',True,source='RAID_COMPLETE')
    now.value += 5
    revised=reset+3600
    s.clock.calibrate(revised-now()-1800,raw_remaining='seasonal')
    assert s.clock.state()['anchor']==revised
    assert s.operational('monk')['wb_participated']==1
    now.value=revised-1801
    assert s.clock.state()['wb_open']==1
    now.value=revised-1800
    assert s.clock.state()['wb_open']==0
    assert s.clock.next_transition()<=revised

def test_earlier_recalibrated_daily_boundary_already_crossed_catches_up(state):
    s,now=state
    anchor=calibrate(s,now,remaining=2*DAY+4000)
    previous_daily=s.clock.state()['next_daily']
    s.ads('monk','DAILY_EXHAUSTED')
    s.wb('monk',True,source='RAID_COMPLETE')
    now.value=previous_daily-1800
    revised=anchor-3600
    s.clock.calibrate(revised-now()-1800)
    assert all(r['stage_ads_remaining']==2 for r in s.rows())
    assert s.clock.state()['next_daily']==previous_daily-3600+DAY
    assert s.operational('monk')['wb_participated']==1

def test_later_recalibration_invalidates_premature_forecast_but_keeps_fresh_count(state):
    s,now=state
    anchor=calibrate(s,now,remaining=2*DAY+4000)
    previous_daily=s.clock.state()['next_daily']
    now.value=previous_daily+60
    s.clock.catch_up()
    s.ads('halo_mage','OBSERVED',observed_count=0,source='VIDEO0')
    revised=anchor+3600
    s.clock.calibrate(revised-now()-1800)
    assert s.operational('monk')['stage_ads_remaining'] is None
    assert s.operational('halo_mage')['stage_ads_remaining']==0
    now.value=previous_daily+3600
    assert all(r['stage_ads_remaining']==2 for r in s.rows())

def test_raid_complete_monotonic_then_new_cycle_reset(state):
    s,now=state
    reset=calibrate(s,now)
    cycle=s.clock.state()['wb_cycle_id']
    s.wb('monk',True,source='RAID_COMPLETE')
    s.wb('monk',False,source='WB_PANEL',previous_reward=False)
    assert s.operational('monk')['wb_participated']==1
    assert s.operational('monk')['wb_source']=='RAID_COMPLETE'
    now.value=reset
    assert all(r['wb_participated']==0 for r in s.rows())
    assert s.clock.state()['wb_cycle_id']==cycle+1
    assert not s.wb('monk',True,source='stale',cycle=cycle)
    assert s.operational('monk')['wb_participated']==0
    assert s.clock.state()['wb_open']==1

def test_resources_atomic_partial_never_overwrites_and_fk(state):
    s,now=state
    values=dict(lapiz=1,dark_essence=0,light_essence=12000,nature_essence=4,k_coins=999999)
    assert s.resources('monk',values)
    assert not s.resources('monk',{**values,'lapiz':None})
    assert not s.resources('monk',{'lapiz':0})
    assert next(r for r in s.rows() if r['character_id']=='monk')['lapiz']==1
    with pytest.raises(ValueError): s.resources(None,values)
    with pytest.raises(sqlite3.IntegrityError),s.transaction():
        s.db.execute("INSERT INTO operational(character_id) VALUES ('position_1')")

def test_atomic_concurrent_and_failed_transaction(state):
    s,now=state
    s.ads('monk','OBSERVED',observed_count=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:s.ads('monk','REWARDED'),range(2)))
    assert s.operational('monk')['stage_ads_remaining']==0
    with pytest.raises(ValueError),s.transaction():
        s.db.execute("UPDATE operational SET stage_ads_remaining=2 WHERE character_id='monk'")
        raise ValueError('rollback')
    assert s.operational('monk')['stage_ads_remaining']==0

def test_unknown_identity_scope_events_never_contaminate(state):
    s,now=state
    consumer=CharacterStateEvents()
    def event(name,**fields):
        return SimpleNamespace(event=name,fields=fields,timestamp=datetime.fromtimestamp(now(),timezone.utc))
    with character_state_scope():
        consumer(event('stages.ad_selection',video_count=0))
        assert all(r['stage_ads_remaining'] is None for r in s.rows())
        establish_character_state(s,'monk')
        consumer(event('stages.ad_selection',video_count=2))
        consumer(event('stages.sapphire_effect',before=1,after=51))
        assert s.operational('monk')['stage_ads_remaining']==1
        consumer(event('stages.temporarily_unavailable'))
        assert s.operational('monk')['stage_ads_remaining']==1
        consumer(event('world_boss.raid_complete_verified'))
        assert s.operational('monk')['wb_participated']==1
    with character_state_scope():
        consumer(event('stages.daily_exhausted'))
    assert s.operational('monk')['stage_ads_remaining']==1

def test_newer_and_malformed_database_preserved(tmp_path):
    path=tmp_path/'future.db'
    db=sqlite3.connect(path)
    db.execute('PRAGMA user_version=999')
    db.close()
    before=path.read_bytes()
    with pytest.raises(ValueError): CharacterStateStore(path)
    assert path.read_bytes()==before
    bad=tmp_path/'bad.db'
    bad.write_bytes(b'not a sqlite file')
    with pytest.raises(sqlite3.DatabaseError): CharacterStateStore(bad)
    assert bad.read_bytes()==b'not a sqlite file'

def test_operational_routing_zero_skip_invalidated_by_reset(state):
    from bot.stages_daily_flow import StagesDailyFlow
    from bot.character_resources import character_resource_scope
    s,now=state
    reset=calibrate(s,now)
    flow=StagesDailyFlow.__new__(StagesDailyFlow)
    with character_state_scope(),character_resource_scope():
        establish_character_state(s,'monk')
        s.ads('monk','DAILY_EXHAUSTED')
        assert flow.routing_no_work().succeeded
        now.value=reset
        assert flow.routing_no_work() is None
        assert s.operational('monk')['stage_ads_remaining']==2

def test_wb_participation_previous_reward_and_daily_quest_independent(state):
    s,now=state
    calibrate(s,now)
    s.wb('monk',False,source='PREVIOUS_REWARD',previous_reward=True)
    s.wb_daily_quest('monk',False)
    row=s.operational('monk')
    assert row['wb_previous_reward_available']==1
    assert row['wb_participated']==0
    assert row['wb_daily_quest_state']=='ABSENT'
    s.wb('monk',True,source='RAID_COMPLETE')
    assert s.operational('monk')['wb_daily_quest_state']=='ABSENT'

def test_wb_close_window_blocks_current_policy_even_with_unknown_character(state):
    s,now=state
    reset=calibrate(s,now)
    policy=WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED',store=s)
    with character_state_scope():
        assert policy.known_no_work() is None
        now.value=reset-1800
        assert policy.known_no_work()=='wb_closed'
        assert all(r['wb_participated'] is None for r in s.rows())

def test_current_wb_policy_store_yes_skips_no_attempt_unknown_inspects(state):
    s,now=state
    calibrate(s,now)
    policy=WorldBossEligibilityPolicy(WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED)
    with character_state_scope():
        establish_character_state(s,'monk')
        assert policy.known_no_work() is None
        s.wb('monk',False,source='WB_PANEL')
        assert policy.known_no_work() is None
        s.wb('monk',True,source='RAID_COMPLETE')
        assert policy.known_no_work()=='current_wb_participated'
        policy.mode=WorldBossEligibilityMode.GENERAL
        assert policy.known_no_work() is None
        policy.mode=WorldBossEligibilityMode.DAILY_QUEST
        assert policy.known_no_work() is None

def test_open_runtime_scheduler_transitions_without_character_read(state):
    import threading
    from bot.character_state import ResetScheduler
    s,now=state
    boundary=calibrate(s,now)
    transitioned=threading.Event()
    original=s.clock.catch_up
    def observed_catchup(*args,**kwargs):
        original(*args,**kwargs)
        if now()>=boundary:
            transitioned.set()
    s.clock.catch_up=observed_catchup
    now.value=boundary
    scheduler=ResetScheduler(s)
    scheduler.start()
    try:
        assert transitioned.wait(2)
        # Direct DB read: no operational()/rows() catch-up could mask the scheduler.
        with s.lock:
            assert s.db.execute('SELECT count(*) FROM operational WHERE stage_ads_remaining=2').fetchone()[0]==28
    finally:
        scheduler.close()
    assert not scheduler.thread.is_alive()

def test_backfill_requires_named_scope_current_epoch_and_preserves_newer_fact(state,tmp_path):
    import json
    from tools.backfill_character_ads import backfill
    from bot.character_state import stamp
    s,now=state
    calibrate(s,now)
    s.ads('halo_mage','OBSERVED',observed_count=1)
    def row(index,name,at):
        return dict(session_id='historical',character_index=index,character_name=name,
                    timestamp=stamp(at),event='stages.ad_selection',video_count=0)
    path=tmp_path/'causal.jsonl'
    records=[row(1,'Monk',now()-1),row(2,'Halo Mage',now()-1),
             row(3,'UNKNOWN',now()-1),row(4,'Cat Acrobat',now()-DAY-1),
             row(5,'Noblia',now()-1),row(5,'Eclair',now()-1)]
    path.write_text('\n'.join(json.dumps(r) for r in records),encoding='utf-8')
    result=backfill(s,path)
    assert [r['character_id'] for r in result['written']]==['monk']
    assert result['ambiguous_scopes']==1
    assert result['source'].startswith('LOG_BACKFILL:')
    assert s.operational('halo_mage')['stage_ads_remaining']==1
    assert s.operational('cat_acrobat')['stage_ads_remaining'] is None
    assert s.operational('noblia')['stage_ads_remaining'] is None
