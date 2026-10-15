"""Deterministic owner traces; simulate() also accepts the eaefa576 owner.

No device, wall-clock sleep, Git or baseline checkout is needed by the tests.
The baseline comparison loads its source separately and uses this same harness.
"""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from bot.action_executor import ActionExecutor
from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL
from bot.observations import Observation, ObservationSource
from bot.operation_control import OperationBudgetExpired, OperationControl, control_scope
from bot.runtime_observer import RuntimeWaitAborted, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.stages_actions import StageControl as C
from bot.stages_runtime import StagesNavigation
from bot.state import ResolutionStatus
from tests.test_mailbox_flow import snapshot


def stage(sequence, timestamp, layer, *, source='source-A', status=None, foreign=False, covered=False):
    base='screen.stages' if layer else 'screen.lobby'
    s=snapshot(sequence,timestamp,base='screen.foreign' if foreign else base,
        overlays=(('popup.stages_'+layer,) if layer and layer!='normal' else ())
            + (('popup.foreign',) if covered else ()))
    if status is not None:
        s=replace(s,state=replace(s.state,status=status,base_context=None,
            base_candidates=('screen.stages','screen.lobby') if status is ResolutionStatus.AMBIGUOUS else ()))
    facts=[Observation('stages.'+flag,1.,ObservationSource.LOCAL_CV)
        for flag in ('abyssal','claim_inactive')]
    if layer:facts.append(Observation('stages.surface',1.,ObservationSource.LOCAL_CV,value=layer))
    return replace(s,frame=replace(s.frame,source_id=source),
        observations=replace(s.observations,observations=tuple(facts)))


def simulate(navigation_type, control, scenario, *, cancel=False, deadline=None,
             dispatch_expiry=False, native=False):
    """One open or Config X and its existing continuation, with logged waits.

    Nominal miss: six seconds, positive origin acquired at t+5.9. The next
    decision arrives 100ms into reacquisition. Each successful wait costs 100ms.
    """
    opening=control is C.OPEN
    origin=None if opening else 'config'
    source=stage(1,9.95,origin)
    clock=NS(now=10.,cancelled=False)
    inputs=[];observations=[];waits=[];records=[];captures=[]
    steps=[]
    if opening:steps.append(dict(layer=None))  # existing initial Lobby wait
    if scenario=='first':steps.append(dict(layer='normal'))
    else:
        retained=dict(layer=origin,miss=True)
        if scenario in {'stale','future','pre_input','old_sequence','missing'}:
            retained.update(age={'stale':2.1,'future':-.1,'pre_input':6.2}.get(scenario,.1))
            if scenario=='old_sequence':retained['sequence']=1
            if scenario=='missing':retained['missing']=True
        elif scenario in {'unknown','ambiguous','foreign','covered','source'}:
            retained.update({
                'unknown':dict(status=ResolutionStatus.UNKNOWN),
                'ambiguous':dict(status=ResolutionStatus.AMBIGUOUS),
                'foreign':dict(foreign=True),'covered':dict(covered=True),
                'source':dict(source='source-B'),
            }[scenario])
        steps.append(retained)
        decision=dict(layer='normal' if scenario=='late' else origin,decision=True)
        if scenario.startswith('decision_'):
            decision.update({
                'decision_stale':dict(age=2.1), 'decision_future':dict(age=-.1),
                'decision_pre_input':dict(age=6.3),'decision_source':dict(source='source-B'),
                'decision_foreign':dict(foreign=True),'decision_covered':dict(covered=True),
                'decision_unknown':dict(status=ResolutionStatus.UNKNOWN),
                'decision_ambiguous':dict(status=ResolutionStatus.AMBIGUOUS),
                'decision_old_sequence':dict(sequence=2 if not opening else 3),
            }[scenario])
        steps.append(decision)
        if scenario!='late':steps.append(dict(layer=origin if scenario=='second_fail' else 'normal',
            miss=scenario=='second_fail'))
    steps.append(dict(layer='normal' if opening else None))
    next_sequence=[1]

    class Observer:
        def __init__(self,name):self.name=name
        def wait_until(self,predicate,*,after_sequence,timeout,abort_if=None,**kwargs):
            waits.append((self.name,after_sequence,timeout))
            step=steps.pop(0)
            started=clock.now
            clock.now+=timeout if step.get('miss') else min(.1,timeout)
            next_sequence[0]+=1
            s=stage(step.get('sequence',next_sequence[0]),clock.now-step.get('age',.1 if step.get('miss') else .01),
                step['layer'],**{key:step[key] for key in ('source','status','foreign','covered') if key in step})
            observations.append(s.sequence)
            # Simulate cancellation at the return boundary of reacquisition.
            if cancel and step.get('decision'):clock.cancelled=True
            if abort_if is not None and abort_if(s):raise RuntimeWaitAborted(s)
            if step.get('miss') or s.sequence<=after_sequence or not predicate(s):
                clock.now=started+timeout
                raise RuntimeWaitTimeout(after_sequence=after_sequence,timeout=timeout,
                    last_snapshot=None if step.get('missing') else s)
            return s

    broad,narrow=Observer('full'),Observer('return')
    def execute(action,*args,**kwargs):inputs.append((action.control.value,clock.now))
    actions=NS(execute=execute)
    if dispatch_expiry:
        class SlowTarget(ActionExecutor):
            def target_for(self,action):
                if len(inputs)==1:clock.now+=2.1
                return super().target_for(action)
        actions=SlowTarget(NS(tap=lambda *args:inputs.append((control.value,clock.now))))
    def record(event,**fields):records.append((event,fields))
    nav=navigation_type(broad,actions,events=NS(record=record),clock=lambda:clock.now,
        sleeper=lambda duration:setattr(clock,'now',clock.now+duration),
        cancel_requested=lambda:clock.cancelled)
    nav.results_observer=narrow
    if native:
        # Static handoff pays the original 150ms + one native acquisition.
        # This source exists only for the opening; later calls deliver stream.
        class Source:
            def get_frame(self):
                return NS(sequence=0 if not captures else nav.cursor+1,
                    timestamp=0. if not captures else clock.now-.001)
            def refresh_native(self):captures.append(clock.now)
        broad.source=Source()
    error=None;result=None
    try:
        with control_scope(OperationControl(clock=lambda:clock.now,deadline=deadline)):
            result=nav.enter_episode() if opening else nav.exit_to_lobby(source,observer=narrow)
    except (RuntimeWaitTimeout,RuntimeWaitCancelled,RuntimeWaitAborted,OperationBudgetExpired,ValueError) as exc:
        error=type(exc).__name__
    return NS(result=result,error=error,inputs=inputs,observations=observations,
        waits=waits,elapsed=clock.now-10.,records=records,captures=captures)


@pytest.mark.parametrize('control',[C.OPEN,C.CLOSE_CONFIG])
@pytest.mark.parametrize('scenario,transition,inputs,elapsed,reads',[
    ('first','success_first_attempt',1,.3,3),
    ('late','success_after_grace',1,6.3,4),
    ('retry','success_after_retry',2,6.4,5),
    ('second_fail','attempts_exhausted',2,12.2,4),
])
def test_transition_traces(control,scenario,transition,inputs,elapsed,reads):
    trace=simulate(StagesNavigation,control,scenario)
    opening=control is C.OPEN
    completed=[fields for event,fields in trace.records if event=='transition.completed']
    assert completed[0]['outcome']==transition
    assert sum(action==control.value for action,_ in trace.inputs)==inputs
    assert trace.error==('RuntimeWaitTimeout' if scenario=='second_fail' else None)
    assert trace.elapsed==pytest.approx(elapsed-(0. if opening else .1))
    assert len(trace.observations)==reads-(0 if opening else 1)
    assert all(scope=='full' for scope,_,_ in trace.waits) if opening else (
        all(scope=='return' for scope,_,_ in trace.waits[:-1])
        and trace.waits[-1][0]==('return' if scenario=='second_fail' else 'full'))
    # The second miss has no grace/capture/observe tail.
    assert completed[0]['grace_count']==(0 if scenario=='first' else 1)


@pytest.mark.parametrize('control',[C.OPEN,C.CLOSE_CONFIG])
@pytest.mark.parametrize('scenario',[
    'stale','future','pre_input','old_sequence','missing',
    'unknown','ambiguous','foreign','covered','source',
    'decision_stale','decision_future','decision_pre_input','decision_old_sequence',
    'decision_unknown','decision_ambiguous','decision_foreign','decision_covered','decision_source',
])
def test_invalid_evidence_never_authorizes_a_second_input(control,scenario):
    trace=simulate(StagesNavigation,control,scenario)
    assert trace.error=='RuntimeWaitTimeout'
    assert [action for action,_ in trace.inputs]==[control.value]


@pytest.mark.parametrize('control',[C.OPEN,C.CLOSE_CONFIG])
def test_cancel_after_reacquisition_never_dispatches_or_continues(control):
    trace=simulate(StagesNavigation,control,'retry',cancel=True)
    assert trace.error=='RuntimeWaitCancelled'
    assert [action for action,_ in trace.inputs]==[control.value]


@pytest.mark.parametrize('control',[C.OPEN,C.CLOSE_CONFIG])
@pytest.mark.parametrize('deadline',[10.,16.05,16.1])
def test_inherited_deadline_cannot_refresh_retry_permission(control,deadline):
    trace=simulate(StagesNavigation,control,'retry',deadline=deadline)
    # A deadline before entry is raised by the existing wait/control boundary.
    assert len(trace.inputs)<=1
    assert trace.error is not None


@pytest.mark.parametrize('control',[C.OPEN,C.CLOSE_CONFIG])
def test_permission_expiring_during_target_resolution_stops_before_physical_input(control):
    trace=simulate(StagesNavigation,control,'retry',dispatch_expiry=True)
    assert trace.error=='RuntimeWaitTimeout'
    assert len(trace.inputs)==1


def test_native_handoff_remains_bounded_and_preserves_first_success():
    trace=simulate(StagesNavigation,C.OPEN,'first',native=True)
    assert trace.error is None
    assert [action for action,_ in trace.inputs]==[C.OPEN.value]
    assert len(trace.captures)==1
    assert trace.elapsed==pytest.approx(.47)


@pytest.mark.parametrize('blocker',[POPUP_EQUIPMENT_INVENTORY_FULL,POPUP_SOCKET_INVENTORY_FULL])
@pytest.mark.parametrize('base',['screen.lobby','screen.stages'])
def test_open_preserves_positive_blocker_handoff_and_relief_intent(blocker,base):
    clock=NS(now=10.)
    before=stage(1,9.9,None)
    blocked=snapshot(2,10.1,base=base,overlays=(blocker,))
    blocked=replace(blocked,frame=replace(blocked.frame,source_id='source-A'))
    calls=[]
    def wait(predicate,**kwargs):
        clock.now=10.2
        assert predicate(blocked)
        return blocked
    nav=StagesNavigation(NS(wait_until=wait),NS(execute=lambda *a,**kw:calls.append('open')),
        clock=lambda:clock.now)
    nav.relief=lambda control,s,expected:calls.append((control,s,expected)) or 'relieved'
    assert nav.change(C.OPEN,before,{'normal','elite'})=='relieved'
    assert calls==['open',(C.OPEN,blocked,{'normal','elite'})]


@pytest.mark.parametrize('loss',['foreign','covered','ambiguous','source'])
def test_observed_loss_cannot_be_replaced_by_later_positive_origin(loss):
    clock=NS(now=10.)
    before=stage(1,9.9,None)
    wrong=stage(2,10.1,None,**{
        'foreign':dict(foreign=True),'covered':dict(covered=True),
        'ambiguous':dict(status=ResolutionStatus.AMBIGUOUS),
        'source':dict(source='source-B'),
    }[loss])
    recovered=stage(3,10.2,None)
    evaluated=[];inputs=[]
    def wait(predicate,*,abort_if,**kwargs):
        for s in (wrong,recovered):
            clock.now=s.timestamp+.01;evaluated.append(s.sequence)
            if abort_if(s):raise RuntimeWaitAborted(s)
            if predicate(s):return s
        raise AssertionError('no new permission after loss')
    nav=StagesNavigation(NS(wait_until=wait),NS(execute=lambda *a,**kw:inputs.append('open')),
        clock=lambda:clock.now)
    with pytest.raises(RuntimeWaitTimeout):nav.change(C.OPEN,before,{'normal','elite'})
    assert inputs==['open'] and evaluated==[2]
