from dataclasses import replace
import json
import pytest

from bot.catalog import SCREEN_LOBBY
from bot.flow_contracts import FlowResult, FlowStatus
from bot.meteorites_session import MeteoritesCharacterScope, MeteoritesState
from bot.preconditions import MinimalPreconditionEnsurer
from bot.productive_runtime import CancellationToken
from bot.session import CharacterContext, SessionPlan, SessionRunner, SessionStatus
from bot.session_report import build_session_report, render_session_report
from bot.shared_meteorites import SharedMeteoritesPreparation
from tests.test_session import Flow, Rotation, Events
from tests.test_shared_meteorites import Game


def integration(*, enabled=True, ids=('strike_archer',), rotate=True,
                terminal=FlowStatus.COMPLETED, stop=None, safe_context=True,
                failure=None, routing_no_work=False):
    trace=[];events=Events();token=CancellationToken();base=[SCREEN_LOBBY]
    physical=[];scopes=[]
    def factory():
        game=Game(failure=failure);physical.append(game)
        procedure=SharedMeteoritesPreparation(game)
        def setup():
            trace.append('setup');p=procedure.setup(None,None);base[0]='screen.meteorites';return p
        def cleanup(*,safe_stop=False):
            trace.append(('cleanup_gate',safe_stop))
            if safe_stop and not safe_context: return procedure._stop('cleanup_entry_unverified')
            trace.append('cleanup');p=procedure.cleanup();base[0]='screen.meteorites';return p
        scope=MeteoritesCharacterScope(procedure, setup=setup, cleanup=cleanup, events=events)
        scopes.append(scope);return scope
    def exit_lobby():base[0]=SCREEN_LOBBY;trace.append('meteorites.exit');return True
    flows=[Flow('first',[FlowResult(FlowStatus.COMPLETED)]*len(ids),trace),
           Flow('last',[FlowResult(terminal)]*len(ids),trace)]
    if stop:
        run=flows[0].run
        def cancel():
            result=run()
            token.request_safe_stop() if stop=='safe' else token.request()
            return result
        flows[0].run=cancel
    if routing_no_work:flows[0].routing_no_work=lambda:FlowResult(FlowStatus.COMPLETED)
    rotation=Rotation(len(ids),trace)
    runner=SessionRunner(SessionPlan(len(ids),tuple(flows),rotation,rotate=rotate,change_meteorites=enabled),
        preconditions=MinimalPreconditionEnsurer(lambda:base[0],navigate_to_lobby=exit_lobby),events=events,
        cancel_requested=token.is_requested,safe_stop_requested=token.is_safe_stop_requested,
        character_context_factory=lambda index:CharacterContext(name='free OCR',character_id=ids[index-1]),
        meteorites_scope_factory=factory)
    return runner,trace,rotation,scopes,physical,token,base


def test_disabled_preserves_productive_trace_and_no_scope_allocated():
    runner,trace,rotation,scopes,games,_,_=integration(enabled=False)
    result=runner.run()
    assert result.status is SessionStatus.COMPLETED
    assert trace==['first.run','last.run','rotation.advance']
    assert not scopes and not games
    assert 'Meteorites: DISABLED' in render_session_report(build_session_report(result))


@pytest.mark.parametrize('rotate',[True,False])
def test_setup_before_steps_cleanup_after_all_steps_and_before_rotation(rotate):
    runner,trace,rotation,scopes,games,_,_=integration(rotate=rotate)
    result=runner.run()
    assert result.status is SessionStatus.COMPLETED
    assert trace.index('setup')<trace.index('first.run')<trace.index('last.run')<trace.index('cleanup')
    assert rotation.calls==int(rotate)
    if rotate:assert trace.index('cleanup')<trace.index('rotation.advance')
    met=result.character_results[0].meteorites
    assert met['status']=='RELEASED' and met['character_id']=='strike_archer'
    assert met['equip_effects']==list(range(11)) and met['unequip_effects']==list(range(10,0,-1))+[0]
    assert met['action_inputs']==22 and games[0].set==1
    report=render_session_report(build_session_report(result))
    assert 'Meteorites: RELEASED [strike_archer]' in report
    assert '11/11 Equip, 11/11 Unequip' in report


def test_roster_releases_before_next_character_and_new_scope():
    runner,trace,_,scopes,games,_,_=integration(ids=('strike_archer','burst_breaker'))
    result=runner.run()
    assert result.status is SessionStatus.COMPLETED and len(scopes)==2 and scopes[0] is not scopes[1]
    assert trace.count('setup')==trace.count('cleanup')==2
    assert all(g.set==1 for g in games)
    assert [c.meteorites['character_id'] for c in result.character_results]==['strike_archer','burst_breaker']


@pytest.mark.parametrize('cid',['berserker','demon_blade','kaiserin'])
def test_exceptions_by_stable_id_only(cid):
    runner,trace,_,_,games,_,_=integration(ids=(cid,))
    result=runner.run()
    assert result.status is SessionStatus.COMPLETED
    assert trace==['first.run','last.run','rotation.advance']
    assert not games[0].inputs and result.character_results[0].meteorites['status']=='SKIPPED_EXCEPTION'


@pytest.mark.parametrize('cid',[None,'DRAKEN一BK','Berserker','19'])
def test_unknown_or_free_name_identity_sends_no_input(cid):
    runner,trace,rotation,_,games,_,_=integration(ids=(cid,))
    result=runner.run()
    assert result.status is SessionStatus.FAILED and not trace and not games[0].inputs
    assert rotation.calls==0 and not result.character_results[0].flow_results
    assert result.character_results[0].meteorites['reason']=='stable_character_id_unknown'


@pytest.mark.parametrize('failure',[('equip',5),('unequip',5)])
def test_partial_failure_no_productive_after_setup_or_rotation_after_cleanup(failure):
    runner,trace,rotation,_,games,_,_=integration(failure=failure)
    result=runner.run();met=result.character_results[0].meteorites
    assert result.status is SessionStatus.FAILED and rotation.calls==0
    assert met['status']=='INTERRUPTED' and met['manual_preparation_required'] and met['set_may_remain_equipped']
    if failure[0]=='equip':assert 'first.run' not in trace and 'cleanup' not in trace
    else:assert 'last.run' in trace
    assert sum(a[:2]==failure for a in games[0].inputs)==1
    assert 'desequipá manualmente' in render_session_report(build_session_report(result))


@pytest.mark.parametrize('safe_context',[True,False])
def test_stop_safely_attempts_release_only_through_fresh_safe_gate(safe_context):
    runner,trace,rotation,_,games,_,_=integration(stop='safe',safe_context=safe_context)
    result=runner.run();met=result.character_results[0].meteorites
    assert result.status is SessionStatus.CANCELLED and rotation.calls==0 and 'last.run' not in trace
    assert ('cleanup' in trace)==safe_context
    assert met['status']==('RELEASED' if safe_context else 'INTERRUPTED')
    assert met['manual_preparation_required']==(not safe_context)
    assert len([a for a in games[0].inputs if a[0]=='unequip'])==(11 if safe_context else 0)


@pytest.mark.parametrize('terminal',[FlowStatus.FAILED,FlowStatus.MANUAL_RESOLUTION])
def test_technical_or_uncontrolled_manual_terminal_never_blind_cleanup(terminal):
    runner,trace,rotation,_,games,_,_=integration(terminal=terminal)
    result=runner.run()
    assert 'cleanup' not in trace and rotation.calls==0
    assert result.character_results[0].meteorites['status']=='INTERRUPTED'
    assert not any(a[0]=='unequip' for a in games[0].inputs)


def test_hard_interrupt_does_not_cleanup_even_if_context_known():
    runner,trace,rotation,_,games,_,_=integration(stop='hard')
    result=runner.run()
    assert result.status is SessionStatus.CANCELLED and 'cleanup' not in trace and rotation.calls==0
    assert result.character_results[0].meteorites['set_may_remain_equipped']


def test_double_callback_never_doubles_input_or_uses_ready_on_new_run():
    runner,_,_,scopes,games,_,_=integration(rotate=False)
    runner.run();scope=scopes[0];before=list(games[0].inputs)
    assert scope.finish() and games[0].inputs==before
    assert not scope.begin(CharacterContext(character_id='strike_archer'))
    runner.run();assert len(scopes)==2 and scopes[1] is not scope


def test_reentry_callbacks_while_setup_cleanup_in_progress_are_not_authorizations():
    runner,_,_,scopes,_,_,_=integration()
    factory=runner.meteorites_scope_factory
    reentrant=[]
    def create():
        scope=factory();setup=scope.setup;cleanup=scope.cleanup
        def begin():reentrant.append(scope.begin(CharacterContext(character_id='strike_archer')));return setup()
        def finish(**kw):reentrant.append(scope.finish());return cleanup(**kw)
        scope.setup=begin;scope.cleanup=finish;return scope
    runner.meteorites_scope_factory=create
    assert runner.run().status is SessionStatus.COMPLETED
    assert reentrant==[False,False] and scopes[0].report()['action_inputs']==22


def test_new_execution_after_failure_requires_empty_prepared_set_no_reused_ready():
    runner,trace,_,scopes,games,_,_=integration(terminal=FlowStatus.FAILED,rotate=False)
    first=runner.run();assert first.character_results[0].meteorites['set_may_remain_equipped']
    retained=games[0]
    def fresh_scope():
        p=SharedMeteoritesPreparation(retained)
        return MeteoritesCharacterScope(p,setup=lambda:p.setup(None,None),cleanup=lambda **k:p.cleanup(),events=Events())
    runner.meteorites_scope_factory=fresh_scope
    before=len(retained.inputs)
    second=runner.run()
    assert second.status is SessionStatus.FAILED and not second.character_results[0].flow_results
    assert not any(a[0]=='equip' for a in retained.inputs[before:])


def test_pure_no_work_occurrence_does_not_end_character_scope():
    runner,trace,_,_,_,_,_=integration(routing_no_work=True,rotate=False)
    result=runner.run()
    assert result.status is SessionStatus.COMPLETED and 'first.run' not in trace
    assert trace.index('setup')<trace.index('last.run')<trace.index('cleanup')


def test_second_safe_stop_and_hard_signal_cancel_cleanup_view():
    token=CancellationToken();token.request_safe_stop()
    assert token.is_requested() and token.is_safe_stop_requested() and not token.is_hard_requested()
    token.request_safe_stop()
    assert token.is_hard_requested() and not token.is_safe_stop_requested()


@pytest.mark.parametrize('version',[1,2])
@pytest.mark.parametrize('value',[None,True,False,1,'true',{},[]])
def test_conservative_optional_schema_load_save_and_duplicate(tmp_path,version,value):
    from bot.routines import RoutineStore,RoutineEditor
    from bot.flow_registry import DEFAULT_FLOW_REGISTRY
    raw={'id':'r','name':'R','steps':[{'flow_id':'mailbox'}]}
    if value is not None:raw['change_meteorites']=value
    path=tmp_path/'routines.json';path.write_text(json.dumps({'version':version,'selected_id':'r','routines':[raw]}))
    store=RoutineStore(path,DEFAULT_FLOW_REGISTRY);editor=RoutineEditor(store)
    assert editor.draft.change_meteorites is (value is True)
    editor.set_change_meteorites(True)
    assert json.loads(path.read_text())['routines'][0].get('change_meteorites')==value
    editor.save();assert RoutineEditor(store).draft.change_meteorites
    editor.create('Copy',duplicate=True);assert editor.draft.change_meteorites
    editor.save();assert RoutineEditor(store).draft.change_meteorites


def test_routine_flag_not_flow_config_and_draft_validation():
    from bot.routines import RoutineSpec,config_overrides
    with pytest.raises(ValueError):RoutineSpec('r','R',change_meteorites=1)
    with pytest.raises(ValueError):config_overrides({'change_meteorites':True})



def test_productive_runtime_routine_wires_flag_once_and_restores_config(monkeypatch):
    from bot.routines import RoutineSpec,RoutineStep
    from bot.productive_runtime import ProductiveRuntime
    from tests.test_gui_functional import runtime_for_test
    runtime,_=runtime_for_test(monkeypatch)
    seen=[]
    monkeypatch.setattr(runtime,'run_flows_once',lambda *a,**k:seen.append(runtime.change_meteorites))
    runtime.run_routine(RoutineSpec('r','ON',(RoutineStep('mailbox'),),change_meteorites=True))
    runtime.run_routine(RoutineSpec('r','OFF',(RoutineStep('mailbox'),)))
    assert seen==[True,False] and not runtime.change_meteorites


def test_real_cleanup_adapter_checks_known_context_before_navigation(monkeypatch):
    from types import SimpleNamespace as S
    from bot.productive_runtime import ProductiveRuntime
    from bot.state import ResolutionStatus
    from tests.test_gui_functional import runtime_for_test
    runtime,_=runtime_for_test(monkeypatch)
    runtime.observer=S(observe=lambda:S(state=S(status=ResolutionStatus.UNKNOWN,base_context=None,overlays=())))
    rt=S(cancel_requested=runtime.cancel_requested)
    monkeypatch.setattr(runtime,'build_meteorites_runtime',lambda:rt)
    monkeypatch.setattr(runtime,'_navigate_to_lobby',lambda:pytest.fail('UNKNOWN cannot navigate'))
    scope=runtime.build_meteorites_character_scope()
    scope.state=MeteoritesState.READY;scope.character_id='strike_archer'
    scope.procedure.progress.equipped=list(range(11));scope.procedure.progress.phase='equipped'
    runtime.cancel_token.request_safe_stop()
    assert not scope.finish(safe_stop=True)
    assert scope.state is MeteoritesState.INTERRUPTED
    assert scope.report()['set_may_remain_equipped']


def test_real_cleanup_adapter_ignores_soft_request_but_obeys_hard_abort(monkeypatch):
    from types import SimpleNamespace as S
    from bot.state import ResolutionStatus
    from tests.test_gui_functional import runtime_for_test
    runtime,_=runtime_for_test(monkeypatch)
    runtime.observer=S(observe=lambda:S(state=S(status=ResolutionStatus.RESOLVED,base_context='screen.meteorites',overlays=())))
    seen=[]
    rt=S(cancel_requested=runtime.cancel_requested,enter=lambda *a:S(ready=True))
    monkeypatch.setattr(runtime,'build_meteorites_runtime',lambda:rt)
    monkeypatch.setattr(type(runtime),'build_verified_transition',lambda self:object())
    scope=runtime.build_meteorites_character_scope()
    scope.state=MeteoritesState.READY;scope.character_id='strike_archer'
    scope.procedure.progress.phase='equipped';scope.procedure.progress.equipped=list(range(11))
    def cleanup():
        seen.append(rt.cancel_requested())
        runtime.cancel_token.request()
        seen.append(rt.cancel_requested())
        return scope.procedure._stop('hard_abort')
    scope.procedure.cleanup=cleanup
    runtime.cancel_token.request_safe_stop()
    assert not scope.finish(safe_stop=True)
    assert seen==[False,True] and rt.cancel_requested()  # original token restored


def test_cancellation_during_setup_is_cancelled_without_productive_or_cleanup():
    runner,trace,rotation,scopes,games,token,_=integration()
    factory=runner.meteorites_scope_factory
    def cancelled_scope():
        scope=factory()
        def setup():
            token.request_safe_stop()
            return scope.procedure._stop('cancelled_in_setup')
        scope.setup=setup
        return scope
    runner.meteorites_scope_factory=cancelled_scope
    result=runner.run()
    assert result.status is SessionStatus.CANCELLED
    assert not trace and not rotation.calls and not games[0].inputs
    assert result.character_results[0].meteorites['status']=='INTERRUPTED'


def test_real_routine_selected_mode_reaches_session_and_character_hooks(monkeypatch):
    from types import SimpleNamespace as S
    import bot.productive_runtime as productive
    from bot.routines import RoutineSpec,RoutineStep
    from tests.test_gui_functional import runtime_for_test
    runtime,_=runtime_for_test(monkeypatch)
    runner,trace,rotation,scopes,_,_,_=integration(rotate=False)
    monkeypatch.delattr(runtime,'run_session')  # exercise the real Session composition
    monkeypatch.setattr(runtime,'build_rotation',lambda count:rotation)
    monkeypatch.setattr(runtime,'build_preconditions',lambda:runner.preconditions)
    flows=iter(runner.plan.flows)
    monkeypatch.setattr(runtime,'build_flow',lambda definition:next(flows))
    monkeypatch.setattr(runtime,'build_meteorites_character_scope',runner.meteorites_scope_factory)
    monkeypatch.setattr(productive,'LobbyNameRecognizer',lambda engine:S())
    monkeypatch.setattr(runtime,'_resolve_character_identity',lambda *a,**k:CharacterContext(character_id='strike_archer'))
    result=runtime.run_routine(RoutineSpec('r','R',
        (RoutineStep('send_stamina'),RoutineStep('mailbox')),change_meteorites=True))
    assert result.status is FlowStatus.COMPLETED and result.session_result is not None
    assert result.session_result.character_results[0].meteorites['status']=='RELEASED'
    assert trace.index('setup')<trace.index('first.run')<trace.index('last.run')<trace.index('cleanup')
    assert len(scopes)==1 and not rotation.calls and not runtime.change_meteorites


@pytest.mark.parametrize('target',['screen.guild','screen.battle_mode_select','quick_menu_accessible'])
def test_meteorites_entry_exit_keeps_navigation_in_caller(target):
    from bot.component_contracts import ComponentRequirement
    base=['screen.meteorites'];trace=[]
    def move(context,label):base[0]=context;trace.append(label);return True
    ensurer=MinimalPreconditionEnsurer(lambda:base[0],
        navigate_to_lobby=lambda:move(SCREEN_LOBBY,'exit'),
        navigate_lobby_to_guild=lambda:move('screen.guild','guild'),
        navigate_to_battle_mode=lambda:move('screen.battle_mode_select','battle'))
    requirement=ComponentRequirement.capability('quick_menu_accessible') if target=='quick_menu_accessible' else ComponentRequirement.exact_state(target)
    result=ensurer.ensure(requirement)
    assert result.succeeded and trace[0]=='exit'
    assert trace==(['exit','guild'] if target=='screen.guild' else ['exit','battle'] if target=='screen.battle_mode_select' else ['exit'])


@pytest.mark.parametrize('during',['setup','cleanup'])
def test_unexpected_support_exception_keeps_conservative_physical_warning(during):
    runner,trace,rotation,scopes,games,_,_=integration()
    factory=runner.meteorites_scope_factory
    def scope_with_error():
        scope=factory()
        def error(**kwargs):raise RuntimeError('transport_or_perception_uncertain')
        if during=='setup':scope.setup=error
        else:scope.cleanup=error
        return scope
    runner.meteorites_scope_factory=scope_with_error
    result=runner.run();met=result.character_results[0].meteorites
    assert result.status is SessionStatus.FAILED and not rotation.calls
    assert met['status']=='INTERRUPTED' and met[during+'_outcome']=='exception'
    assert met['manual_preparation_required'] and met['set_may_remain_equipped']
    assert 'El set puede seguir equipado.' in render_session_report(build_session_report(result))
    if during=='setup':assert not trace and not games[0].inputs


def test_stop_before_character_reports_requested_but_unstarted():
    runner,trace,_,scopes,_,token,_=integration()
    token.request_safe_stop()
    result=runner.run()
    assert result.status is SessionStatus.CANCELLED and not trace and not scopes
    text=render_session_report(build_session_report(result))
    assert 'Meteorites: NOT_REQUESTED' in text and 'Meteorites: DISABLED' not in text


def test_smoke_report_exports_real_session_flow_event_immutable_data():
    from bot.flow_contracts import FlowEvent
    from bot.productive_runtime import FlowsOnceResult
    from tools.smoke_meteorites_b2 import json_default
    runner,_,_,_,_,_,_=integration(rotate=False)
    session=runner.run()
    flow=FlowResult(FlowStatus.COMPLETED,(FlowEvent('send_stamina.completed',fields={'verified':True}),))
    value=FlowsOnceResult(FlowStatus.COMPLETED,(flow,),session_result=session)
    exported=json.loads(json.dumps(value,default=json_default))
    assert exported['flow_results'][0]['events'][0]['fields']=={'verified':True}
    assert exported['session_result']['character_results'][0]['meteorites']['status']=='RELEASED'
