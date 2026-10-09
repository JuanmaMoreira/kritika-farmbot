"""B2 software contracts; synthetic worlds do not establish physical gameplay."""
from dataclasses import replace
import json
from types import SimpleNamespace as NS

import pytest

from bot.arena_config import ArenaConfig, ArenaMode as M
from bot.arena_flow import ArenaFlow
from bot.arena_semantics import ArenaDifficulty as D, ArenaBalances, ArenaSingleExecution
from bot.config import RuntimeConfig
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.gui_model import FlowSelectionModel
from bot.productive_runtime import ProductiveRuntime, CancellationToken
from bot.routines import RoutineEditor, RoutineSpec, RoutineStep, RoutineStore, config_overrides
from test_arena_flow import World, Reader, flow, C
from test_session import Flow, Rotation, _runner


class ReturnWorld(World):
    def execute(self, action, geometry, **kw):
        before=self.surface
        super().execute(action, geometry, **kw)
        if action.control is C.BACK and self.no_effect is not C.BACK:
            self.surface={'challenge':'selection','selection':'select_mode','select_mode':'lobby'}[before]


def test_arena_is_available_but_existing_defaults_are_not_activated(tmp_path):
    store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY)
    editor=RoutineEditor(store)
    assert 'arena' not in editor.active_ids
    assert 'arena' not in FlowSelectionModel().active_ids
    assert DEFAULT_FLOW_REGISTRY.get('arena').contract==ArenaFlow.routine_contract
    editor.create('Arena')
    editor.add('arena')
    assert editor.draft.steps[0].config=={'arena':{'mode':'SINGLE_BATTLE','difficulty':'EASY'}}


def test_two_occurrences_draft_apply_save_reload_and_legacy_defaults(tmp_path):
    store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY)
    editor=RoutineEditor(store)
    editor.create('Two Arena entries')
    editor.add('arena'); editor.add('arena')
    editor.save()
    first={'arena':ArenaConfig(M.AUTO_REPEAT,D.HARD).to_dict()}
    second={'arena':ArenaConfig(M.SINGLE_BATTLE,D.NORMAL).to_dict()}
    editor.configure(0,first); editor.configure(1,second)
    assert RoutineEditor(store).draft.steps[0].config!=first  # Apply remains draft
    editor.save()
    loaded=RoutineEditor(store)
    assert [s.config for s in loaded.draft.steps]==[first,second]
    loaded.move_up(1)
    assert [s.config for s in loaded.draft.steps]==[second,first]
    old=RoutineSpec('legacy','Old',(RoutineStep('mailbox'),))
    store.save((old,),'legacy')
    assert store.load()[0]==(old,)
    assert config_overrides({'arena':{}})['arena']==ArenaConfig()


@pytest.mark.parametrize('value', [None, [], {'mode':'ADAPTIVE'}, {'difficulty':'auto'},
    {'mode':True}, {'multiplier':1}, {'buy_badges':True}, {'gold_budget':5}])
def test_invalid_or_economic_arena_settings_are_preserved_disabled(tmp_path,value):
    store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY)
    original=RoutineSpec('r','r',(RoutineStep('arena',config={'arena':value}),RoutineStep('mailbox')))
    store.save((original,),'r')
    loaded,_=store.load()
    assert loaded[0].steps[0].config==original.steps[0].config
    assert not loaded[0].steps[0].enabled and loaded[0].steps[1].enabled
    with pytest.raises((TypeError,ValueError)):
        config_overrides({'arena':value})


def test_missing_occurrence_settings_never_inherit_global_arena(monkeypatch):
    w=ReturnWorld()
    runtime=ProductiveRuntime(RuntimeConfig('offline','unused',arena=ArenaConfig(M.AUTO_REPEAT,D.HARD)),
        NS(source=w,observe=w.observe),w,object(),object(),object(),object(),object(),None,CancellationToken())
    calls=[]
    def builder(self,difficulty,**kwargs):
        calls.append((self.config.arena,difficulty,kwargs))
        return ArenaFlow(self.observer,self.actions,Reader(w),difficulty,
            mode=kwargs['mode'],return_context=kwargs['return_context'])
    monkeypatch.setattr(ProductiveRuntime,'build_arena_flow',builder)
    definition=DEFAULT_FLOW_REGISTRY.get('arena')
    a=definition.build(runtime._step_runtime(RoutineStep('arena')))
    b=definition.build(runtime._step_runtime(RoutineStep('arena',config={'arena':ArenaConfig(M.AUTO_REPEAT,D.NORMAL).to_dict()})))
    assert a is not b and a.mode is M.SINGLE_BATTLE and a.difficulty is D.EASY
    assert b.mode is M.AUTO_REPEAT and b.difficulty is D.NORMAL
    assert a.return_context==b.return_context=='screen.lobby'
    assert a.source is b.source is w and runtime.config.arena==ArenaConfig(M.AUTO_REPEAT,D.HARD)


def test_auto_repeat_external_return_requires_three_guarded_back_transitions():
    w=ReturnWorld()
    r=flow(w,return_context='screen.lobby').run()
    assert r.succeeded and r.batch_result.used_tickets==104
    assert w.inputs[-3:]==[C.BACK]*3 and w.start_count==1
    assert r.final_snapshot.state.base_context=='screen.lobby'
    assert {'return_selection','return_select_mode','return_lobby'}<=set(r.evidence)


def test_unknown_external_return_stops_without_next_back_or_start():
    w=ReturnWorld(); original=w.execute
    def execute(action,geometry,**kw):
        original(action,geometry,**kw)
        if action.control is C.BACK: w.surface='unknown'
    w.execute=execute
    r=flow(w,return_context='screen.lobby').run()
    assert not r.succeeded and r.phase=='external_return' and r.batch_result is not None
    assert w.inputs.count(C.BACK)==1 and w.start_count==1 and r.final_snapshot is None


def test_completed_arena_continues_session_only_from_verified_external_context():
    w=ReturnWorld(); arena=flow(w,return_context='screen.lobby'); trace=[]
    following=Flow('following',[FlowResult(FlowStatus.COMPLETED)],trace)
    runner,_=_runner(1,[arena,following],Rotation(1,trace),default_context='screen.lobby')
    result=runner.run()
    assert result.status.value=='completed' and 'following.run' in trace
    assert w.surface=='lobby'


def test_failed_external_return_does_not_advance_session():
    w=ReturnWorld(); w.no_effect=C.BACK; trace=[]
    arena=flow(w,return_context='screen.lobby')
    following=Flow('following',[FlowResult(FlowStatus.COMPLETED)],trace)
    runner,_=_runner(1,[arena,following],Rotation(1,trace))
    result=runner.run()
    assert result.status.value!='completed' and not trace


class SingleWorld(ReturnWorld):
    states=World.states+('single_result','defeat_unknown','single_partial')
    def __init__(self):
        super().__init__()
        self.gold=1000000; self.karats=1000; self.price_known=True
        self.single_wait_states=['loading','battle','single_partial','single_result']
        self.single_close_unknown=False
    def execute(self,action,geometry,**kw):
        old_stock=self.stock[0]
        super().execute(action,geometry,**kw)
        if action.control is C.BUFF1 and old_stock<8 and self.buffs[0]:
            self.gold-=(8-old_stock)*3000
        if action.control is C.SINGLE_START:
            self.start_count+=1
            if self.start_error: raise RuntimeError('ADB reply lost')
            if self.no_effect is not C.SINGLE_START:
                self.queue=list(self.single_wait_states)
        elif action.control is C.SINGLE_RESULT_CLOSE:
            self.surface='unknown' if self.single_close_unknown else 'selection'
            self.badges-=getattr(self,'actual_used',8)
            self.karats+=getattr(self,'actual_karats',8)
            self.buffs=[False,False,False]


class SingleReader(Reader):
    def __init__(self,w):
        super().__init__(w)
        self.visuals.single_active=lambda f:self.visuals.state(f)=='battle'
        self.visuals.single_result=lambda f:self.visuals.state(f)=='single_result'
        self.visuals.clear=lambda f,n: w.price_known and n=='gold_buff1_price'
    def balances(self,s,**kw):
        import hashlib
        self.ocr_calls+=6
        if self.visuals.state(s.image) not in ('challenge','selection'): return None
        return ArenaBalances(self.w.badges,self.w.gold,self.w.karats,s.sequence,s.timestamp,
                             hashlib.sha256(s.image.tobytes()).hexdigest())
    def single_terminal(self,s,execution,**kw):
        return (isinstance(execution,ArenaSingleExecution) and execution.start_verified
                and s.sequence>execution.after_sequence and self.visuals.single_result(s.image))


def single_flow(w,**kw):
    f=flow(w,mode=M.SINGLE_BATTLE,return_context='screen.lobby',**kw)
    f.reader=SingleReader(w); f.v=f.reader.visuals
    return f


def test_single_dispatch_exactly_one_start_specific_result_and_two_back():
    w=SingleWorld(); r=single_flow(w).run()
    assert r.succeeded and r.mode is M.SINGLE_BATTLE and r.batch_result is None
    assert r.single_result.used_tickets==r.single_result.karats_delta==8
    assert not hasattr(r.single_result,'won_tickets')
    assert w.inputs.count(C.SINGLE_START)==1 and C.START not in w.inputs and C.CONFIG not in w.inputs
    assert w.inputs.count(C.SINGLE_RESULT_CLOSE)==1 and C.RESULT_OK not in w.inputs
    assert w.inputs[-2:]==[C.BACK]*2 and r.final_snapshot.state.base_context=='screen.lobby'
    assert r.metrics['planned_consumption']==8 and r.metrics['wait_ocr_calls']==0


def test_single_explicit_handoff_closes_without_navigation_preparation_or_start():
    w=SingleWorld(); w.surface='single_result'; f=single_flow(w)
    receipt=ArenaSingleExecution('prior_run','new_source',D.EASY,8,w.now-1.,0,True,w.badges,w.karats)
    result=f.observe_started_single(receipt)
    assert result.succeeded and result.single_result.run_id=='prior_run'
    assert w.inputs==[C.SINGLE_RESULT_CLOSE,C.BACK,C.BACK] and w.start_count==0
    with pytest.raises(ValueError):
        single_flow(SingleWorld()).observe_started_single(replace(receipt,start_verified=False))


@pytest.mark.parametrize('difficulty',list(D))
def test_single_explicit_difficulty(difficulty):
    w=SingleWorld(); f=single_flow(w); f.difficulty=difficulty
    r=f.run()
    assert r.succeeded and r.single_result.difficulty is difficulty
    assert C[difficulty.name] in w.inputs


@pytest.mark.parametrize('stock',[0,6,7])
def test_one_entry_buff1_selected_without_count_gate(stock):
    w=SingleWorld(); w.stock[0]=stock
    r=single_flow(w).run()
    assert r.succeeded and w.gold==1000000-(8-stock)*3000
    assert w.karats==1008 and w.start_count==1


@pytest.mark.parametrize('control',[C.BUFF1,C.BUFF2])
def test_mandatory_buff_without_selected_effect_never_starts(control):
    w=SingleWorld(); w.stock[0]=6; w.no_effect=control
    r=single_flow(w).run()
    assert not r.succeeded and C.SINGLE_START not in w.inputs
    assert w.inputs.count(control)==1


def test_single_buffs_use_only_one_entry_coverage_and_premium_is_off_when_unknown():
    w=SingleWorld(); w.stock=[8,8,None]
    original=w.execute
    # Unknown Double Points inventory never sends its input.
    r=single_flow(w).run()
    assert r.succeeded and C.BUFF3 not in w.inputs and r.metrics['planned_consumption']==8


@pytest.mark.parametrize('failure',['badges','x8','x8_unknown','buff_unknown'])
def test_single_readiness_never_sends_start(failure):
    w=SingleWorld()
    if failure=='badges': w.badges=7
    if failure=='x8': w.x8=False; w.no_effect=C.X8
    if failure=='x8_unknown': w.x8=None
    if failure=='buff_unknown': w.buffs[0]=None
    r=single_flow(w).run()
    assert not r.succeeded and w.start_count==0


@pytest.mark.parametrize('surface',['defeat_unknown','single_partial','challenge','unknown'])
def test_absence_of_win_or_partial_single_overlay_never_terminates(surface):
    w=SingleWorld(); w.single_wait_states=['loading',surface]
    r=single_flow(w).run()
    assert not r.succeeded and r.single_result is None and r.physical_operation_may_be_active
    assert w.start_count==1 and C.SINGLE_RESULT_CLOSE not in w.inputs and C.BACK not in w.inputs


def test_post_single_start_error_never_retries_and_blocks_same_instance():
    w=SingleWorld(); w.start_error=True; f=single_flow(w)
    r=f.run(); again=f.run()
    assert r.status is FlowStatus.FAILED and r.physical_operation_may_be_active
    assert again.error=='previous_physical_operation_unresolved' and w.start_count==1


def test_single_observer_cancel_does_not_claim_physical_cancel_or_close():
    w=SingleWorld(); w.cancel_on=C.SINGLE_START
    r=single_flow(w).run()
    assert r.status is FlowStatus.CANCELLED and r.physical_operation_may_be_active
    assert C.SINGLE_RESULT_CLOSE not in w.inputs and C.BACK not in w.inputs


@pytest.mark.parametrize('used,karats',[(7,8),(16,8),(8,0),(8,16)])
def test_single_requires_credited_balance_effects_before_routine_continuation(used,karats):
    w=SingleWorld(); w.actual_used=used; w.actual_karats=karats
    r=single_flow(w).run()
    assert not r.succeeded and r.single_result is None
    assert C.SINGLE_RESULT_CLOSE in w.inputs and C.BACK not in w.inputs


def test_single_completed_operation_allows_following_step():
    w=SingleWorld(); trace=[]; following=Flow('next',[FlowResult(FlowStatus.COMPLETED)],trace)
    runner,_=_runner(1,[single_flow(w),following],Rotation(1,trace))
    assert runner.run().status.value=='completed' and trace==['next.run','rotation.advance']


def test_single_unknown_close_blocks_next_step_and_rotation():
    w=SingleWorld(); w.single_close_unknown=True; trace=[]
    following=Flow('next',[FlowResult(FlowStatus.COMPLETED)],trace)
    runner,_=_runner(1,[single_flow(w),following],Rotation(1,trace))
    assert runner.run().status.value!='completed' and not trace
