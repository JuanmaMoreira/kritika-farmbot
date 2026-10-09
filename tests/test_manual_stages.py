from types import SimpleNamespace as NS
import pytest
from bot.manual_stages import select_manual_stage, ManualStageTarget as T, stamina_eligible
from bot.meteorites_session import MeteoritesCharacterScope, MeteoritesState

@pytest.mark.parametrize('cid', ['burst_breaker','berserker','demon_blade','kaiserin'])
def test_strong_without_shared_set(cid):
    assert select_manual_stage(cid) is T.ABYSSAL_RION_09

def scope(cid='strike_archer', equipped=None, state=MeteoritesState.READY):
    p = NS(phase='equipped', equipped=list(range(11)) if equipped is None else equipped,
        released=[], pending=None)
    s = MeteoritesCharacterScope(NS(progress=p),setup=None,cleanup=None,events=None)
    s.character_id=cid; s.state=state
    return s

def test_complete_credited_character_set():
    assert select_manual_stage('strike_archer',scope()) is T.ABYSSAL_RION_09

@pytest.mark.parametrize('equipped', [[],list(range(10)),[0]*11])
def test_partial_or_absent_never_09(equipped):
    assert select_manual_stage('strike_archer',scope(equipped=equipped)) is T.CHAOS_06

@pytest.mark.parametrize('state', list(MeteoritesState))
def test_only_ready_authorizes_set(state):
    expected=T.ABYSSAL_RION_09 if state is MeteoritesState.READY else T.CHAOS_06
    assert select_manual_stage('strike_archer',scope(state=state)) is expected

def test_wrong_identity_pending_released_and_config_flag_not_authority():
    s=scope()
    assert select_manual_stage('noblia',s) is T.CHAOS_06
    s.procedure.progress.pending={'slot':10}
    assert select_manual_stage('strike_archer',s) is T.CHAOS_06
    s.procedure.progress.pending=None; s.procedure.progress.released=[10]
    assert select_manual_stage('strike_archer',s) is T.CHAOS_06
    assert select_manual_stage(None) is T.CHAOS_06
    assert all('08' not in target.value for target in T)

@pytest.mark.parametrize('value,expected', [(59,False),(60,True),(61,True),(None,False),(True,False)])
def test_stamina_boundary(value,expected):
    assert stamina_eligible(value) is expected

from bot.manual_stages import ManualStagesOperation, ManualStageOutcome as O
from bot.manual_stages_reader import auto_window_state
from bot.stages_actions import StageControl as C
from bot.flow_contracts import FlowStatus as S
from bot.observations import Observation,ObservationBatch,ObservationSource
from bot.state import ResolutionStatus
from bot.runtime_observer import RuntimeWaitCancelled

def snap(layer='config',flags=None,target=T.CHAOS_06):
    values={**(flags or {})}
    obs=[Observation('stages.surface',1.,ObservationSource.LOCAL_CV,value=layer),
        Observation('stages.manual_target',1.,ObservationSource.LOCAL_CV,value=target.value)]
    obs.extend(Observation('stages.'+k+'_state',1.,ObservationSource.LOCAL_CV,value=v)
        for k,v in values.items() if v is not None)
    obs.extend(Observation('stages.'+k,1.,ObservationSource.LOCAL_CV) for k in ('stage6','stage9','chaos','abyssal','support_active'))
    return NS(sequence=1,timestamp=0.,geometry=NS(),frame=NS(image=target.value),
        state=NS(status=ResolutionStatus.RESOLVED,base_context='screen.stages',
            overlays=('popup.stages_'+layer,) if layer!='normal' else ()),
        observations=ObservationBatch(1,0.,tuple(obs)))

class Nav:
    def __init__(self,snapshot):
        self.s=snapshot;self.trace=[];self.clock=lambda:0.;self.events=None;self.relief=None
        self.cancel_requested=lambda:False
        self.actions=NS(execute=lambda action,*a,**kw:self.tap(action.control,self.s))
    def tap(self,control,s):
        self.trace.append(control)
        mapping={C.X4:'x4',C.HELL:'hell',C.PENANCE:'penance',
            C.BUFF1:'buff1',C.BUFF2:'buff2',C.BUFF3:'buff3',C.BUFF4:'buff4'}
        if control in mapping:
            states={o.name.removeprefix('stages.').removesuffix('_state'):o.value
                for o in self.s.observations.observations if o.name.endswith('_state')}
            name=mapping[control]
            if control is C.X4:
                states[name]=self.trace.count(C.X4)>=2
            else:states[name]=not states[name]
            self.s=snap(layer='normal' if control is C.X4 else 'config',flags=states,
                target=T(self.s.frame.image))
    def wait(self,predicate,**kw):
        if not predicate(self.s):raise ValueError('effect unverified')
        return self.s
    def change(self,control,s,expected,**kw):
        self.trace.append(control);return snap(next(iter(expected)))

def operation(flags=None,target=T.CHAOS_06):
    flags=flags or dict(hell=True,penance=False,buff1=True,buff2=True,buff3=True,buff4=False)
    n=Nav(snap(flags=flags,target=target))
    op=ManualStagesOperation(n,NS(engine=object()),NS(config_target=lambda image:image,battle=lambda image:True),clock=lambda:0.)
    op.target=target;op._pause=lambda _:None
    return op,n

@pytest.mark.parametrize('selected', [True,False,None])
def test_x4_only_base_no_modal_recheck_and_unknown_no_input(selected):
    op,n=operation();s=snap('normal',{'x4':selected});n.s=s
    if selected is None:
        with pytest.raises(ValueError):op.configure_x4(s)
        assert not n.trace
    else:
        assert op.configure_x4(s)
        assert n.trace==([] if selected else [C.X4,C.X4])
    with pytest.raises(ValueError):op.configure_x4(snap(flags={'x4':True}))

@pytest.mark.parametrize('target,setting,control', [(T.CHAOS_06,'hell',C.HELL),
    (T.ABYSSAL_RION_09,'penance',C.PENANCE)])
@pytest.mark.parametrize('selected', [True,False,None])
def test_correct_difficulty_guard_and_effect(monkeypatch,target,setting,control,selected):
    import bot.manual_stages as module
    monkeypatch.setattr(module,'buff_stock',lambda *a:10)
    flags=dict(hell=True,penance=True,buff1=True,buff2=True,buff3=True,buff4=True);flags[setting]=selected
    op,n=operation(flags,target)
    if selected is None:
        with pytest.raises(ValueError):op.prepare_config(n.s)
        assert not n.trace
    else:
        op.prepare_config(n.s)
        assert n.trace==([] if selected else [control])

@pytest.mark.parametrize('index', [1,2,3])
def test_mandatory_buffs_verified_and_no_uncredited_purchase(monkeypatch,index):
    import bot.manual_stages as module
    flags=dict(hell=True,penance=False,buff1=True,buff2=True,buff3=True,buff4=False)
    flags[f'buff{index}']=False
    op,n=operation(flags)
    monkeypatch.setattr(module,'buff_stock',lambda e,im,i,c:0 if i==4 else 10)
    op.prepare_config(n.s)
    assert n.trace==[getattr(C,f'BUFF{index}')]
    op,n=operation(flags)
    monkeypatch.setattr(module,'buff_stock',lambda *a:0)
    op.prepare_config(n.s)
    assert n.trace==[getattr(C,f'BUFF{index}')]


def test_first_three_buffs_never_read_counts(monkeypatch):
    import bot.manual_stages as module
    seen=[]
    def stock(e,image,index,cancel):
        assert index==4;seen.append(index);return 10
    monkeypatch.setattr(module,'buff_stock',stock)
    op,n=operation(dict(hell=True,buff1=False,buff2=False,buff3=False,buff4=True))
    op.prepare_config(n.s)
    assert seen==[4] and n.trace==[C.BUFF1,C.BUFF2,C.BUFF3]


def test_manual_reuses_support_activation_and_checks_final_readiness(monkeypatch):
    import bot.manual_stages as module
    monkeypatch.setattr(module,'buff_stock',lambda *a:10)
    op,n=operation()
    ready=Observation('stages.support_ready',1.,ObservationSource.LOCAL_CV)
    obs=tuple(o for o in n.s.observations.observations if o.name!='stages.support_active')+(ready,)
    n.s.observations=ObservationBatch(1,0.,obs)
    original=n.tap
    def tap(control,s):
        original(control,s)
        if control is C.SUPPORT:n.s=snap(flags=dict(hell=True,buff1=True,buff2=True,buff3=True,buff4=True))
    n.tap=tap
    op.prepare_config(n.s)
    assert n.trace==[C.SUPPORT]


def test_unknown_support_never_starts_or_guesses_activation(monkeypatch):
    op,n=operation()
    n.s.observations=ObservationBatch(1,0.,tuple(o for o in n.s.observations.observations
        if o.name!='stages.support_active'))
    with pytest.raises(ValueError,match='mao ready unverified'):op.prepare_config(n.s)
    assert not n.trace


def test_support_needs_uses_existing_fill_ready_activate_chain(monkeypatch):
    import bot.manual_stages as module
    monkeypatch.setattr(module,'buff_stock',lambda *a:10)
    op,n=operation()
    def panel(layer,marker):
        s=snap(layer,dict(hell=True,buff1=True,buff2=True,buff3=True,buff4=True))
        obs=tuple(o for o in s.observations.observations if o.name!='stages.support_active')
        s.observations=ObservationBatch(1,0.,obs+(Observation('stages.'+marker,1.,ObservationSource.LOCAL_CV),))
        return s
    n.s=panel('config','support_needs')
    def tap(control,s):
        n.trace.append(control)
        if control is C.FILL_SUPPORT:n.s=panel('support_purchase','support_full')
        elif control is C.CLOSE_SUPPORT:n.s=panel('config','support_ready')
        elif control is C.SUPPORT:
            from bot.perception.stages import has
            n.s=panel('support_purchase','support_purchase') if has(s,'support_needs') else panel('config','support_active')
        else:raise AssertionError(control)
    n.tap=tap
    def change(control,s,expected,**kw):
        tap(control,s)
        from bot.perception.stages import surface
        assert surface(n.s) in expected;return n.s
    n.change=change
    op.prepare_config(n.s)
    assert n.trace==[C.SUPPORT,C.FILL_SUPPORT,C.CLOSE_SUPPORT,C.SUPPORT]

@pytest.mark.parametrize('stock', [None,0,1,3,4,99])
@pytest.mark.parametrize('selected', [True,False])
def test_buff4_without_coverage_off_never_karats(monkeypatch,stock,selected):
    import bot.manual_stages as module
    flags=dict(hell=True,penance=False,buff1=True,buff2=True,buff3=True,buff4=selected)
    op,n=operation(flags)
    monkeypatch.setattr(module,'buff_stock',lambda e,im,i,c:stock if i==4 else 10)
    op.prepare_config(n.s)
    desired=stock is not None and (selected or stock>=1)
    assert n.trace==([C.BUFF4] if desired!=selected else [])

def test_auto_temporal_window_rejects_unknown_and_short_off():
    assert auto_window_state([(0.,.03)]) is None
    assert auto_window_state([(i*.1,.03) for i in range(21)]) is True
    assert auto_window_state([(i*.1,.011) for i in range(21)]) is False
    assert auto_window_state([(i*.1,.001) for i in range(21)]) is False
    assert auto_window_state([(0.,.001)]) is None
    assert auto_window_state([(i*.1,None) for i in range(21)]) is None
    assert auto_window_state([(i*.1,.020) for i in range(21)]) is None

@pytest.mark.parametrize('states,inputs,verified', [([True],0,True),([False,True],1,True),
    ([None],0,False),([False,None],1,False)])
def test_auto_on_conserved_off_toggled_once_unknown_no_wait(states,inputs,verified):
    op,n=operation();values=iter(states);frame=NS(sequence=3)
    op.auto_state=lambda after:(next(values),frame)
    taps=[];op._input=lambda *a:taps.append(a[0]);op._emit=lambda *a,**kw:None
    if verified:assert op.ensure_auto() is frame
    else:
        with pytest.raises(ValueError):op.ensure_auto()
    assert taps==[C.BATTLE_AUTO]*inputs

@pytest.mark.parametrize('stamina', [0,59,60])
def test_run_stamina_under60_no_navigation(stamina):
    op,n=operation();op.balances.read=lambda:NS(stamina=stamina,sapphires=0,sapphire_limit=102,snapshot=NS())
    if stamina==60:
        op.enter_target=lambda:(_ for _ in ()).throw(ValueError('entry attempted'))
    r=op.run()
    assert r.outcome is (O.AMBIGUOUS if stamina==60 else O.STAMINA_INSUFFICIENT)
    assert not n.trace

def test_cancel_and_unresolved_run_never_repeat():
    op,n=operation();op.balances.read=lambda:(_ for _ in ()).throw(RuntimeWaitCancelled('stop'))
    assert op.run().status is S.CANCELLED
    op._unsafe_to_restart=True
    assert op.run().physical_operation_may_be_active

@pytest.mark.parametrize('terminal,delta,outcome', [('clear',4,O.REWARDED),
    ('clear',0,O.NO_PROGRESS),('death',0,O.DEFEATED)])
def test_one_entry_two_different_starts_home_fresh_reward(terminal,delta,outcome):
    op,n=operation();trace=[]
    before=NS(stamina=60,sapphires=20,sapphire_limit=102,snapshot=NS(sequence=1,timestamp=0.))
    after=NS(stamina=0,sapphires=20+delta,snapshot=NS(sequence=10,timestamp=2.))
    reads=iter([before,after]);op.balances.read=lambda:next(reads)
    op.enter_target=lambda:n.s
    op.prepare_config=lambda s:s
    def change(control,s,expected,**kw):
        trace.append(control)
        assert expected==({'start'} if control is C.START else {'battle','death','death_guide','clear'})
        return snap('start' if control is C.START else 'battle')
    n.change=change
    op.ensure_auto=lambda seq:trace.append('auto') or NS(sequence=3)
    op.wait_terminal=lambda seq:trace.append('wait') or (terminal,NS())
    op.return_home=lambda t,f:trace.append('home') or after.snapshot
    r=op.run()
    assert r.succeeded and r.outcome is outcome and not r.physical_operation_may_be_active
    assert trace==[C.START,C.STRIKER_START,'auto','wait','home']
    assert r.sapphires_after-r.sapphires_before==delta
    assert r.stamina_consumed==60 and r.entry_id==1

def test_unknown_after_consumptive_start_latches_no_duplicate():
    op,n=operation();op.balances.read=lambda:NS(stamina=60,sapphires=0,sapphire_limit=102,snapshot=NS())
    op.enter_target=lambda:n.s;op.prepare_config=lambda s:s
    def change(control,s,expected,**kw):
        n.trace.append(control)
        if control is C.STRIKER_START:raise ValueError('effect unknown')
        return snap('start')
    n.change=change
    result=op.run()
    assert result.status is S.MANUAL_RESOLUTION and result.physical_operation_may_be_active
    assert result.stamina_consumed is None and result.entry_id==1
    assert op.run().physical_operation_may_be_active
    assert n.trace==[C.START,C.STRIKER_START]

def test_closed_entry_balance_interruption_reconciles_from_lobby_without_start():
    from bot.stages_runtime import lobby
    op,n=operation();trace=[]
    before=NS(stamina=120,sapphires=20,sapphire_limit=102,snapshot=NS(sequence=1,timestamp=0.))
    after=NS(stamina=61,sapphires=24,snapshot=NS(sequence=10,timestamp=2.))
    def read():
        trace.append('read')
        if len(trace)==1:return before
        if trace.count('read')==2:raise ValueError('fresh balance interrupted')
        return after
    op.balances.read=read;op.enter_target=lambda:n.s;op.prepare_config=lambda s:s
    n.change=lambda control,s,expected,**kw:n.trace.append(control) or snap(
        'start' if control is C.START else 'battle')
    op.ensure_auto=lambda seq:NS(sequence=3)
    op.wait_terminal=lambda seq:('clear',NS())
    op.return_home=lambda t,f:after.snapshot
    first=op.run()
    assert first.stamina_consumed==60 and first.entry_reconciliation_pending
    assert not first.physical_operation_may_be_active
    n.wait=lambda predicate,**kw:trace.append(predicate is lobby) or NS()
    resumed=op.resume()
    assert resumed.succeeded and resumed.stamina_consumed==60 and resumed.entry_id==first.entry_id
    assert resumed.outcome is O.REWARDED and True in trace
    assert n.trace==[C.START,C.STRIKER_START]

def test_relief_resumes_only_after_base_quantity_and_config_revalidation():
    op,n=operation();trace=[];n.s=snap('normal',{'x4':True})
    op.open_target=lambda s:trace.append('base_x4_target') or snap()
    restored=op.restore_config(snap('start'))
    assert n.trace==[C.CLOSE_START,C.CLOSE_CONFIG] and trace==['base_x4_target']
    op.prepare_config=lambda s:trace.append('readiness') or s
    op.resume_after_relief(C.STRIKER_START,restored,{'battle'})
    assert n.trace[-2:]==[C.START,C.STRIKER_START] and trace[-1]=='readiness'

def test_start_cancel_or_reading_ambiguity_never_authorizes_next_entry():
    op,n=operation()
    op.balances.read=lambda:(_ for _ in ()).throw(ValueError('stamina unreadable'))
    assert op.run().outcome is O.AMBIGUOUS and not n.trace

def test_opening_config_unknown_difficulty_observes_until_stable_without_input(monkeypatch):
    import bot.manual_stages as module
    op,n=operation(dict(hell=None,penance=True,buff1=True,buff2=True,buff3=True,buff4=False))
    monkeypatch.setattr(module,'buff_stock',lambda *a:99)
    wait=n.wait;observed=[]
    def settle(predicate,**kw):
        if not observed:
            assert not predicate(n.s) and not n.trace
            n.s=snap(flags=dict(hell=False,penance=True,buff1=True,buff2=True,buff3=True,buff4=False))
            observed.append('stable')
        return wait(predicate,**kw)
    n.wait=settle
    op.prepare_config(n.s)
    assert observed==['stable'] and n.trace==[C.HELL,C.BUFF4]

@pytest.mark.parametrize('sapphires',[102,129])
def test_capacity_full_is_functional_no_start(sapphires):
    op,n=operation()
    op.balances.read=lambda:NS(stamina=60,sapphires=sapphires,sapphire_limit=102,snapshot=NS())
    result=op.run()
    assert result.succeeded and result.outcome is O.SAPPHIRE_CAPACITY_FULL
    assert not n.trace

@pytest.mark.parametrize('terminal,controls',[('clear',[C.CLEAR_HOME]),
    ('death',[C.DEATH_ABANDON,C.DEATH_GUIDE_CLOSE]),('death_guide',[C.DEATH_GUIDE_CLOSE])])
def test_terminal_specific_closure_verifies_clean_lobby(terminal,controls):
    op,n=operation();trace=[];frame=NS(sequence=1,image=terminal)
    op.visuals.terminal=lambda image:image
    op._input=lambda control,*a:trace.append(control)
    op._fresh_frame=lambda *a:NS(sequence=2,image='death_guide')
    n.dispatched_at=0.
    def wait(predicate,**kw):
        from bot.catalog import SCREEN_LOBBY
        s=NS(state=NS(status=ResolutionStatus.RESOLVED,base_context=SCREEN_LOBBY,overlays=()),frame=NS())
        assert predicate(s);trace.append('verified_lobby');return s
    n.wait=wait
    op.return_home(terminal,frame)
    assert trace==controls+['verified_lobby']

def test_wait_positive_only_light_polling_and_cancel():
    op,n=operation();elapsed=[0.];op.clock=lambda:elapsed[0]
    op._pause=lambda seconds:elapsed.__setitem__(0,elapsed[0]+seconds)
    frames=iter([NS(sequence=1,image='loading'),NS(sequence=2,image='battle'),NS(sequence=3,image='clear')])
    op._fresh_frame=lambda *a:next(frames)
    op.visuals.terminal=lambda image:'clear' if image=='clear' else None
    terminal,_=op.wait_terminal(0)
    assert terminal=='clear' and elapsed[0]==33.
    n.cancel_requested=lambda:True
    with pytest.raises(RuntimeWaitCancelled):op._cancel()


@pytest.mark.parametrize('fresh,second_timeout,taps', [('clear',False,2),('clear',True,2),
    ('loading',False,1),('unknown',False,1)])
def test_home_no_effect_retry_requires_fresh_clear_and_is_bounded(fresh,second_timeout,taps):
    from bot.runtime_observer import RuntimeWaitTimeout
    op,n=operation();trace=[];n.dispatched_at=0.
    op.visuals.terminal=lambda image:'clear' if image=='clear' else None
    op._input=lambda control,*a:trace.append(control)
    op._fresh_frame=lambda *a:NS(sequence=2,image=fresh)
    calls=[]
    def wait(predicate,**kw):
        calls.append(1)
        if len(calls)==1 or second_timeout:
            raise RuntimeWaitTimeout(after_sequence=1,timeout=12.,last_snapshot=None)
        return NS(frame=NS())
    n.wait=wait
    if fresh=='clear' and not second_timeout:
        op.return_home('clear',NS(sequence=1,image='clear'))
    else:
        with pytest.raises(RuntimeWaitTimeout):op.return_home('clear',NS(sequence=1,image='clear'))
    assert trace==[C.CLEAR_HOME]*taps

def test_session_exposes_verified_set_only_during_character_steps():
    from test_meteorites_session import integration
    from bot.meteorites_session import current_meteorites_scope
    runner,trace,_,scopes,_,_,_=integration(ids=('strike_archer','burst_breaker'))
    seen=[];run=runner.plan.flows[0].run
    def read_scope():
        credited=current_meteorites_scope()
        assert credited is scopes[-1]
        seen.append(select_manual_stage(credited.character_id,credited))
        return run()
    runner.plan.flows[0].run=read_scope
    assert current_meteorites_scope() is None
    assert runner.run().status.value=='completed'
    assert seen==[T.ABYSSAL_RION_09,T.ABYSSAL_RION_09]
    assert trace.count('setup')==trace.count('cleanup')==2
    assert current_meteorites_scope() is None
