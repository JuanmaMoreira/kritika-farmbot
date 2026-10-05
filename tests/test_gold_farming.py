"""Economic strategy, child outcomes, character knowledge and pre-entry readiness."""
from types import SimpleNamespace as S
from unittest.mock import Mock
import json
import pytest
from bot.character_resources import character_resource_scope
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.gold_farming_flow import GoldFarmingFlow
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_productive import ProductiveMonsterWaveFlow
from bot.prepared_activity import PreparedActivity
from bot.runtime_facts import FactReadStatus
from bot.routines import RoutineSpec, RoutineStep
from bot.session import SessionPlan, SessionRunner, SessionStatus
from bot.session_report import build_session_report, ReportStatus
from bot.preconditions import MinimalPreconditionEnsurer
from test_session import Flow, Rotation, Events
from test_stages_daily import flow, balance
from bot.ads_manager import AdsOutcome

def outcome(kind): return FlowResult(FlowStatus.COMPLETED,(FlowEvent(kind),))
productive=outcome('stages_daily.completed')
exhausted=outcome('stages_daily.ads_exhausted')
no_work=outcome('monster_wave.no_work')
invested=outcome('monster_wave.completed')
unavailable=FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.ads_unavailable'),))

def cycle(stages, mw, trace=None, **kw):
 trace=[] if trace is None else trace
 return GoldFarmingFlow(Flow('stages_daily',list(stages),trace),
     Flow('monster_wave',list(mw),trace),ensure_lobby=lambda:None,**kw),trace

def test_ready_two_ads_core_has_exactly_two_investments_final_label():
 c,trace=cycle([productive,productive],[invested,invested])
 r=c.run()
 assert r.succeeded and trace==['stages_daily.run','monster_wave.run']*2
 assert [(e.fields['attempt_index'],e.fields['activity_role']) for e in r.events if e.kind=='monster_wave.completed']==[(1,'investment'),(2,'final_investment')]

@pytest.mark.parametrize('final',[no_work,invested])
def test_first_video_zero_skips_second_opportunity_but_keeps_final_investment(final):
 c,trace=cycle([exhausted],[final]);r=c.run()
 assert r.succeeded and trace==['stages_daily.run','monster_wave.run']
 assert r.event_count('gold_farming.attempt.skipped')==1
 assert next(e for e in r.events if e.kind==final.events[0].kind).fields['activity_role']=='final_investment'

def test_temporary_unavailability_is_continuable_but_never_exhausted():
 c,trace=cycle([unavailable,productive],[no_work,invested]);r=c.run()
 assert r.succeeded and len(trace)==2
 assert r.event_count('stages_daily.ads_unavailable')==1
 assert next(e for e in r.events if e.kind=='gold_farming.attempt.skipped').fields['reason']=='ads_recovery_exhausted'
 assert next(e for e in r.events if e.kind=='monster_wave.no_work').fields['activity_role']=='final_investment'

@pytest.mark.parametrize('terminal',[FlowResult(FlowStatus.FAILED,error='real'),
 FlowResult(FlowStatus.CANCELLED),FlowResult(FlowStatus.MANUAL_RESOLUTION),
 FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.ad_aborted_recovered'),)),
 FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.ads_unavailable'),),error='real')])
def test_real_child_terminal_preserved_and_no_investment_or_rotation(terminal):
 c,trace=cycle([terminal],[]);r=c.run()
 assert (r.status,r.error,r.failure)==(terminal.status,terminal.error,terminal.failure)
 assert trace==['stages_daily.run']

def test_user_can_stop_controlled_unavailability():
 c,trace=cycle([unavailable],[],continue_on_unavailable=False)
 assert c.run().status is FlowStatus.MANUAL_RESOLUTION and len(trace)==1

def test_mw_failure_stops_second_attempt():
 terminal=FlowResult(FlowStatus.FAILED,error='board failed')
 c,trace=cycle([productive],[terminal]);r=c.run()
 assert r.status is FlowStatus.FAILED and r.error=='board failed' and len(trace)==2

def test_stages_pressure_prerequisite_zero_then_productive_then_final_investment():
 trace=[];events=Events()
 stage,nav,_=flow([balance(310),balance(),balance(),balance(360)],
     [AdsOutcome.RETURNED],mw=lambda:trace.append('prerequisite') or no_work)
 nav.events=events
 # First explicit Video 0 in the next opportunity ends that character's core.
 original=stage.run;calls=[]
 def staged_run():
  calls.append(1)
  return original() if len(calls)==1 else exhausted
 stage.run=staged_run
 c=GoldFarmingFlow(stage,Flow('monster_wave',[invested,no_work],trace),ensure_lobby=lambda:None)
 assert c.run().succeeded
 assert trace==['prerequisite','monster_wave.run','monster_wave.run']
 assert any(e=='stages.prerequisite.result' and f['result']=='completed' for e,f in events.records)

def test_explicit_exhaustion_same_character_reentry_and_second_occurrence_no_navigation():
 first,n,_=flow([balance(),balance()],[]);n.prepare_ad=lambda s:(s,0)
 second,n2,_=flow([],[])
 with character_resource_scope() as knowledge:
  assert first.run().event_count('stages_daily.ads_exhausted')==1
  # Recovery doesn't enter a new session-character scope.
  first.reenter_same_character()
  assert knowledge.stage_ads_exhausted
  assert second.run().event_count('stages_daily.ads_exhausted')==1
  assert n2.calls==[]
 with character_resource_scope() as knowledge:
  assert not knowledge.stage_ads_exhausted
  b,n3,_=flow([balance(),balance(),balance(300)],[AdsOutcome.RETURNED])
  assert b.run().succeeded and 'enter' in n3.calls

def test_unavailable_and_abort_do_not_create_exhaustion_knowledge():
 with character_resource_scope() as knowledge:
  a,_,_=flow([balance(),balance(),balance()],[AdsOutcome.UNAVAILABLE]*4)
  assert a.run().status is FlowStatus.MANUAL_RESOLUTION
  assert not knowledge.stage_ads_exhausted
  b,_,_=flow([balance(),balance(),balance(stamina=1)],[AdsOutcome.ABORTED_RECOVERED])
  assert b.run().status is FlowStatus.MANUAL_RESOLUTION
  assert not knowledge.stage_ads_exhausted

def mw_flow(value=0,status=FactReadStatus.CONFIRMED,sequence=11,context='screen.lobby',timestamp=10.9):
 a=Mock();a.clock=lambda:11.;a.cancel_requested=Mock(return_value=False);a.observer.observe.return_value=S(sequence=10)
 a.facts.read_sapphires.return_value=S(status=status,fact=S(name='resource.sapphires',context=context,
     value=value,timestamp=timestamp,sequence=sequence,evidence=(S(sequence=sequence),)))
 f=MonsterWaveFlow.__new__(MonsterWaveFlow);f.activity=a
 f.zone=S(enter=Mock(return_value=FlowResult(FlowStatus.COMPLETED)),leave=Mock(return_value=FlowResult(FlowStatus.COMPLETED)))
 return f

@pytest.mark.parametrize('productive_wrapper',[False,True])
def test_fresh_zero_standalone_no_zone_no_mw_activity(productive_wrapper):
 f=mw_flow()
 if productive_wrapper:
  p=ProductiveMonsterWaveFlow.__new__(ProductiveMonsterWaveFlow);p.inner=f;p.zone=f.zone;p._run_activity_l1=Mock();f=p
 r=f.run()
 assert r.succeeded and r.event_count('monster_wave.no_work')==1
 f.zone.enter.assert_not_called();f.zone.leave.assert_not_called()

@pytest.mark.parametrize('kw',[{'status':FactReadStatus.UNCERTAIN},{'sequence':10},{'context':'screen.monster_wave'},{'value':-1},{'timestamp':8.8},{'timestamp':12.}])
def test_unconfirmed_zero_fails_closed_without_navigation(kw):
 f=mw_flow(**kw);assert f.run().status is FlowStatus.FAILED
 f.zone.enter.assert_not_called()

def test_positive_precheck_is_not_reused_as_accounting_or_cached_zero():
 f=mw_flow(300);assert f.entry_readiness() is None
 f.activity.facts.read_sapphires.return_value.fact.value=0
 assert f.entry_readiness().event_count('monster_wave.no_work')==1
 assert f.activity.facts.read_sapphires.call_count==2

def test_explicit_mw_zero_session_prepared_entry_stays_lobby_then_rotation():
 trace=[];f=mw_flow();f.zone.entry_requirement=GoldFarmingFlow.contract.precondition
 from bot.component_contracts import ComponentRequirement
 f.zone.hub_requirement=ComponentRequirement.exact_state('screen.battle_mode_select')
 plan=SessionPlan(1,(f.prepared(f.zone),),Rotation(1,trace))
 runner=SessionRunner(plan,preconditions=MinimalPreconditionEnsurer(lambda:'screen.lobby'),events=Events())
 r=runner.run();assert r.status is SessionStatus.COMPLETED
 assert trace==['rotation.advance'];f.zone.enter.assert_not_called()

@pytest.mark.parametrize('first',[productive,exhausted])
def test_cycle_session_character_isolation_rotation_after_core_reporting(first):
 trace=[]
 c,_=cycle(([first,productive,productive] if first is exhausted else [productive]*4),
     ([no_work,invested,invested] if first is exhausted else [invested]*4),trace)
 r=SessionRunner(SessionPlan(2,(c,),Rotation(2,trace)),
     preconditions=MinimalPreconditionEnsurer(lambda:'screen.lobby'),events=Events()).run()
 assert r.status is SessionStatus.COMPLETED and r.advances_completed==2
 assert trace.index('rotation.advance')==(2 if first is exhausted else 4)
 report=build_session_report(r)
 assert report.status is (ReportStatus.BUSINESS_INCOMPLETE if first is exhausted else ReportStatus.COMPLETE)

def test_exact_legacy_preset_migrates_custom_and_overrides_preserved(tmp_path):
 from bot.routines import RoutineStore
 from bot.flow_registry import DEFAULT_FLOW_REGISTRY
 from dataclasses import replace
 literal=tuple(RoutineStep(f) for f in ('stages_daily','monster_wave','stages_daily','monster_wave'))
 legacy=RoutineSpec('basic-gold','Basic Gold Farming',literal)
 custom=RoutineSpec('custom','Custom',literal)
 store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY);store.save((legacy,custom),'basic-gold')
 loaded,selected=store.load()
 assert selected=='basic-gold' and loaded[0].steps==(RoutineStep('gold_farming'),) and loaded[1]==custom
 edited=replace(legacy,steps=(replace(literal[0],continue_on_unavailable=False),*literal[1:]))
 store.save((edited,),'basic-gold');assert store.load()[0]==(edited,)


def test_controlled_unavailable_bad_return_fails_before_any_investment():
 c,trace=cycle([unavailable],[])
 def reject():raise ValueError('Lobby not restored')
 c.ensure_lobby=reject
 r=c.run()
 assert r.status is FlowStatus.FAILED and r.error=='Lobby not restored'
 assert trace==['stages_daily.run']

def test_prepared_readiness_failure_preserves_terminal_no_zone_no_rotation():
 trace=[];f=mw_flow(status=FactReadStatus.UNCERTAIN)
 f.zone.entry_requirement=GoldFarmingFlow.contract.precondition
 f.zone.hub_requirement=GoldFarmingFlow.contract.precondition
 r=SessionRunner(SessionPlan(1,(f.prepared(f.zone),),Rotation(1,trace)),
     preconditions=MinimalPreconditionEnsurer(lambda:'screen.lobby'),events=Events()).run()
 assert r.status is SessionStatus.FAILED and trace==[]
 f.zone.enter.assert_not_called()

def test_gold_occurrence_config_and_continuation_independent_registry_binding(monkeypatch):
 import bot.flow_registry as registry
 import bot.stages_wiring as wiring
 from test_routines import make_runtime
 runtime,_,_=make_runtime(monkeypatch)
 configs=[];children=[]
 def mw_builder(dependencies):
  configs.append((dependencies.config.monster_wave,dependencies.config.equipment_sell))
  child=S(run=Mock(return_value=no_work));children.append(child);return child
 monkeypatch.setattr(registry,'_build_monster_wave',mw_builder)
 monkeypatch.setattr(wiring,'build_stages_daily',lambda dep,mw:S(monster_wave=mw,run=Mock(return_value=productive),nav=S(wait=lambda predicate:None)))
 from bot.flow_registry import DEFAULT_FLOW_REGISTRY
 definition=DEFAULT_FLOW_REGISTRY.get('gold_farming')
 first=definition.build(runtime._step_runtime(RoutineStep('gold_farming',continue_on_unavailable=False,
     config={'monster_wave':{'continue_when_nonblocking_inventory_full':True}})))
 second=definition.build(runtime._step_runtime(RoutineStep('gold_farming')))
 assert first.monster_wave is first.stages.monster_wave is children[0]
 assert second.monster_wave is second.stages.monster_wave is children[1]
 assert first.monster_wave is not second.monster_wave
 assert configs[0][0].continue_when_nonblocking_inventory_full
 assert not configs[1][0].continue_when_nonblocking_inventory_full
 assert not first.continue_on_unavailable and second.continue_on_unavailable


def test_failed_ad_recovery_still_invests_pending_sapphires_then_rotates():
 trace=[]
 c,_=cycle([unavailable],[invested],trace)
 with character_resource_scope() as knowledge:
  r=SessionRunner(SessionPlan(1,(c,),Rotation(1,trace)),
      preconditions=MinimalPreconditionEnsurer(lambda:'screen.lobby'),events=Events()).run()
  assert r.status is SessionStatus.COMPLETED and r.advances_completed==1
  assert not knowledge.stage_ads_exhausted
 assert trace==['stages_daily.run','monster_wave.run','rotation.advance']
 assert build_session_report(r).status is ReportStatus.BUSINESS_INCOMPLETE


@pytest.mark.parametrize('stages,mw,expected_lobbies', [
    ([productive, productive], [invested, invested], 3),
    ([exhausted], [invested], 1),
    ([unavailable], [invested], 1),
])
def test_final_investment_preserves_mw_surface_for_caller(stages, mw, expected_lobbies):
    seed = object()
    mw[-1] = FlowResult(FlowStatus.COMPLETED, mw[-1].events, final_snapshot=seed)
    c, _ = cycle(stages, mw)
    c.ensure_lobby = Mock()
    result = c.run()
    assert result.succeeded and result.final_snapshot is seed
    assert c.ensure_lobby.call_count == expected_lobbies
    assert 'screen.monster_wave' in {s.name for s in c.contract.successful_postconditions}
