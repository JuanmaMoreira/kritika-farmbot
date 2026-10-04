from types import SimpleNamespace as S
from unittest.mock import Mock
import pytest
from bot.flow_contracts import FlowStatus, FlowEvent
from bot.monster_wave_activity import MonsterWaveActivity, MonsterWaveResult
from bot.sapphire_pressure import sapphire_pressure_passes
from bot.stages_balances import StageBalances
from bot.catalog import SCREEN_LOBBY
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.runtime_facts import FactReadStatus, FactReadResult
from test_monster_wave_productive import _Harness
from test_monster_wave import Device
from test_world_boss_flow import fact_result
from dataclasses import replace

@pytest.mark.parametrize('balance,passes',[(0,0),(1,0),(99,0),(101,0),(102,1),
 (199,1),(200,1),(201,1),(299,2),(300,2)])
def test_shared_pressure_policy_and_stage_readiness(balance,passes):
 assert sapphire_pressure_passes(balance)==passes
 assert StageBalances(300,balance,102,None).needs_monster_wave==(passes>0)

@pytest.mark.parametrize('effects',[(199,99),(301,201,101),(1,)])
def test_productive_recalculates_from_actual_clear_effects(effects):
 clear=MonsterWaveResult(FlowStatus.COMPLETED,events=(FlowEvent('monster_wave.completed'),))
 h=_Harness(first=clear);f=h.flow()
 f.activity.prepare=lambda **kw:MonsterWaveResult(FlowStatus.COMPLETED,sapphires_initial=201)
 reads=iter(effects)
 f.activity.read_sapphires_after_clear=lambda:S(value=next(reads),sequence=100)
 r=f._run_activity_l1()
 assert r.succeeded,r.error
 assert r.event_count('monster_wave.completed')==len(effects)
 assert r.event_count('monster_wave.sapphire_effect')==len(effects)

def test_unverified_clear_effect_stops_without_next_consumption():
 clear=MonsterWaveResult(FlowStatus.COMPLETED,events=(FlowEvent('monster_wave.completed'),))
 h=_Harness(first=clear);f=h.flow()
 def fail():raise ValueError('inconclusive effect')
 f.activity.read_sapphires_after_clear=fail
 r=f._run_activity_l1()
 assert r.status is FlowStatus.FAILED and r.sapphires_consumed==0
 assert sum(c[0]=='pass' for c in h.calls)==1

@pytest.mark.parametrize('problem',['stale','wrong_context','unreadable','cancelled','old_timestamp'])
def test_clear_effect_fact_requires_fresh_mw_authority(problem):
 d=Device(base=SCREEN_MONSTER_WAVE);a=d.activity();a.clock=lambda:100.
 before=d.observe();d.observe=lambda:before
 read=fact_result('resource.sapphires',99,before.sequence+2,SCREEN_MONSTER_WAVE)
 if problem=='unreadable':read=FactReadResult(FactReadStatus.UNREADABLE)
 elif problem=='cancelled':read=FactReadResult(FactReadStatus.CANCELLED)
 else:
  evidence=tuple(replace(e,sequence=before.sequence if problem=='stale' else e.sequence,
                        timestamp=1. if problem=='old_timestamp' else 100.) for e in read.fact.evidence)
  read=replace(read,fact=replace(read.fact,context=SCREEN_LOBBY if problem=='wrong_context' else SCREEN_MONSTER_WAVE,evidence=evidence))
 a.facts=S(read_sapphires=lambda **kw:read)
 from bot.runtime_observer import RuntimeWaitCancelled
 with pytest.raises(RuntimeWaitCancelled if problem=='cancelled' else ValueError):
  a.read_sapphires_after_clear()
 assert d.intents==[]


@pytest.mark.parametrize('actual,expected',[(99,FlowStatus.COMPLETED),(199,FlowStatus.FAILED)])
def test_insufficient_popup_needs_fresh_pressure_postcondition(actual,expected):
 h=_Harness(first=MonsterWaveResult(FlowStatus.COMPLETED,
     events=(FlowEvent('monster_wave.insufficient_sapphires'),)))
 f=h.flow();f.activity.read_sapphires_after_clear=lambda:S(value=actual,sequence=100)
 result=f._run_activity_l1()
 assert result.status is expected
 assert sum(c[0]=='pass' for c in h.calls)==1
