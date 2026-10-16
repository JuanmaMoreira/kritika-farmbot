"""Real RuntimeObserver/VerifiedTransition/ActionExecutor wiring, offline frames."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver, POPUP_SOCKET_INVENTORY_FULL
from bot.event_context import event_context
from bot.monster_wave_activity import MonsterWaveActivity
from bot.monster_wave_semantics import (MW_SCREEN, MW_BOARD, MW_CLEAR, MW_TIMER,
    MW_SKIP_START, MW_MAX, MW_CONTROLS_CLEAR, MW_POINTS_REWARD, POPUP_MW_BOARD)
from bot.monster_wave_yes import execute_monster_wave_yes, _ContextCoverage, YES_CONTEXT_COVERAGE
from bot.observations import Observation, ObservationSource
from bot.operation_control import OperationControl, control_scope
from bot.perception import build_default_perception
from bot.perception.global_loading import GlobalLoadingDetector, ACTIVITY_GLOBAL_LOADING
from bot.runtime_observer import RuntimeObserver, RuntimeWaitCancelled
from bot.verified_transition import VerifiedTransition, VerifiedTransitionOutcome, VerifiedTransitionPolicy
from bot.monster_wave_actions import AcceptMonsterWaveInventory


class Events:
    def __init__(self):self.records=[]
    def record(self,name,**fields):self.records.append((name,fields))


def scenario(monkeypatch, steps, *, enabled=True, coverage=True):
    """All ordinary detectors execute; their emitted facts follow the scenario."""
    now=[10.];cancelled=[False];events=Events();samples=[dict(kind='board',t=10.,loading=False)]+steps
    state=SimpleNamespace(index=-1,source_calls=0,base_analyses=0,detector_calls=0,rows=samples)
    engine=build_default_perception()
    def names(kind):
        common={MW_SCREEN}
        return {'board':common|{MW_BOARD},'unknown_board':{MW_BOARD},'clear':common|{MW_CLEAR},'pending':set(),
            'mw':common,'trade':{'landmark.trading_center_title'},
            'ambiguous':common|{'landmark.trading_center_title'},
            'blocker':common|{'landmark.socket_inventory_full_prompt'},
            'points':common|{MW_POINTS_REWARD},
            'ready':common|{MW_TIMER,MW_SKIP_START,MW_MAX,MW_CONTROLS_CLEAR}}[kind]
    for d in engine.detectors:
        name=getattr(getattr(d,'spec',None),'name',None)
        def detect(image,name=name):
            return ((Observation(name,1.,ObservationSource.LOCAL_CV),)
                    if name in names(samples[int(image[0,0,0])]['kind']) else ())
        monkeypatch.setattr(d,'detect',detect)
    original_analyze=type(engine).analyze
    def counted(self,frame):
        state.base_analyses+=1
        result = original_analyze(self,frame)
        row = samples[int(frame.image[0,0,0])]
        now[0] += row.get('analysis_seconds', 0.)
        if row.get('cancel_during_analysis'):
            cancelled[0] = True
        return result
    monkeypatch.setattr(type(engine),'analyze',counted)
    def loading(self,image):
        state.detector_calls+=1
        row=samples[int(image[0,0,0])]
        assert len([e for e in events.records if e[0]=='action.dispatched'])==1
        dispatch=next(f['dispatch'] for e,f in events.records if e=='action.dispatched')
        assert event_context()['parent_operation_id']==dispatch['operation_id']
        if row.get('cancel_during_cv'):cancelled[0]=True
        now[0]+=row.get('cv_seconds',0.)
        return ((Observation(ACTIVITY_GLOBAL_LOADING,.9,ObservationSource.LOCAL_CV),)
                if row.get('loading') else ())
    monkeypatch.setattr(GlobalLoadingDetector,'detect',loading)
    def get_frame():
        state.source_calls+=1
        state.index=min(state.index+1,len(samples)-1)
        row=samples[state.index]
        now[0]=max(now[0],row.get('at',row['t']))
        image=np.full((100,200,3),state.index,np.uint8)
        return FrameSnapshot(image,row['t'],state.index+1,source_id=row.get('source','same-source'))
    observer=RuntimeObserver(SimpleNamespace(get_frame=get_frame),engine,build_default_resolver(),
        clock=lambda:now[0],sleeper=lambda s:now.__setitem__(0,now[0]+s),poll_interval=.5,events=events)
    adb=SimpleNamespace(tap=Mock(side_effect=lambda *a,**k:now.__setitem__(0,now[0]+.1)))
    transition=VerifiedTransition(observer,ActionExecutor(adb),events,clock=lambda:now[0],
        cancel_requested=lambda:cancelled[0])
    before=observer.observe()
    if not coverage:
        original=_ContextCoverage.analyze
        monkeypatch.setattr(_ContextCoverage,'analyze',lambda self,f:replace(original(self,f),coverage=None))
    def run():
        if enabled:
            return execute_monster_wave_yes(transition,'monster_wave.standalone.accept_board',before)
        return transition.execute('monster_wave.standalone.accept_board',AcceptMonsterWaveInventory(),before,
            precondition=lambda s:s.state.overlays==(POPUP_MW_BOARD,),
            expected=lambda s:s.state.overlays!=(POPUP_MW_BOARD,),policy=VerifiedTransitionPolicy(max_attempts=1))
    return SimpleNamespace(run=run,transition=transition,before=before,state=state,now=now,
        cancelled=cancelled,events=events,adb=adb,observer=observer)


@pytest.mark.parametrize('loading',[False,True])
def test_unknown_handoff_parity_and_progress_is_not_effect(monkeypatch,loading):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3,loading=loading)])
    r=h.run()
    assert r.succeeded and not r.effect_accredited and r.attempt_count==1
    assert bool(r.progress_snapshot)==loading
    if loading:
        assert r.progress_snapshot.observations.best(ACTIVITY_GLOBAL_LOADING)
        assert YES_CONTEXT_COVERAGE in r.progress_snapshot.observations.coverage
        progress=next(fields for event,fields in h.events.records if event=='monster_wave.yes_loading_progress')
        assert progress['dispatch_id']==r.dispatch_receipts[0].dispatch_id
        assert progress['operation_id']==r.operation_id and progress['effect_accredited'] is False
    assert h.adb.tap.call_count==1 and h.state.source_calls==2 and h.state.base_analyses==2


def test_loading_on_still_visible_board_changes_handoff_decision(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=True)])
    r=h.run()
    assert r.succeeded and r.progress_snapshot is not None and not r.effect_accredited
    assert r.final_snapshot.state.overlays==(POPUP_MW_BOARD,)
    assert h.adb.tap.call_count==1 and h.state.source_calls==2


def test_unknown_with_compatible_board_overlay_does_not_lose_window(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='unknown_board',t=10.3,loading=True)])
    r=h.run()
    assert r.succeeded and r.progress_snapshot is not None and not r.effect_accredited
    assert r.final_snapshot.state.base_context is None and h.adb.tap.call_count==1


@pytest.mark.parametrize('kind',['clear','blocker','points'])
def test_credited_boundary_skips_auxiliary_cv_even_with_visible_spinner(monkeypatch,kind):
    h=scenario(monkeypatch,[dict(kind=kind,t=10.3,loading=True)])
    r=h.run()
    assert r.succeeded and h.state.detector_calls==0
    assert r.effect_accredited==(kind=='clear')
    assert h.adb.tap.call_count==1 and h.state.source_calls==2


@pytest.mark.parametrize('first_kind',['pending','clear'])
def test_missing_coverage_falls_back_without_blocking_clear(monkeypatch,first_kind):
    h=scenario(monkeypatch,[dict(kind=first_kind,t=10.3,loading=True),
        dict(kind='clear',t=10.8,loading=True)],coverage=False)
    r=h.run()
    assert r.succeeded and r.progress_snapshot is None and h.state.detector_calls==0
    assert h.adb.tap.call_count==1


@pytest.mark.parametrize('kind',['trade','ambiguous'])
def test_contradictory_trading_invalidates_before_false_positive(monkeypatch,kind):
    h=scenario(monkeypatch,[dict(kind=kind,t=10.3,loading=True)])
    r=h.run()
    assert r.outcome is VerifiedTransitionOutcome.UNEXPECTED_STATE
    assert h.state.detector_calls==0 and r.progress_snapshot is None
    assert h.adb.tap.call_count==1


@pytest.mark.parametrize('kind',['trade','ambiguous'])
def test_contradiction_reacquired_after_grace_cannot_be_a_successful_handoff(monkeypatch,kind):
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=False)])
    h.state.rows.append(dict(kind=kind,t=18.2,loading=True))
    def get_frame():
        h.state.source_calls+=1
        timed_out=sum(event=='runtime_wait.completed' and fields['outcome']=='timeout'
            for event,fields in h.events.records)
        if timed_out>=2:
            return FrameSnapshot(np.full((100,200,3),2,np.uint8),h.now[0],3,source_id='same-source')
        return FrameSnapshot(np.full((100,200,3),1,np.uint8),10.3,2,source_id='same-source')
    h.observer.source.get_frame=get_frame
    r=h.run()
    assert r.outcome is VerifiedTransitionOutcome.UNEXPECTED_STATE
    assert not r.effect_accredited and r.progress_snapshot is None
    assert h.adb.tap.call_count==1 and h.state.detector_calls==1


@pytest.mark.parametrize('row',[dict(kind='pending',t=8.,at=10.3,loading=True),
    dict(kind='pending',t=10.,at=10.3,loading=True),dict(kind='pending',t=15.,at=10.3,loading=True)])
def test_stale_predispatch_or_future_frame_cannot_supply_progress(monkeypatch,row):
    # A future timestamp is exercised separately below without a subsequent
    # clock that could accidentally make it current.
    h=scenario(monkeypatch,[row,dict(kind='clear',t=15.5 if row['t']==15 else 10.8)])
    r=h.run()
    assert r.succeeded and r.progress_snapshot is None and h.state.detector_calls==0
    assert h.adb.tap.call_count==1


def test_source_rotation_is_latched_even_if_original_source_returns(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3,loading=True,source='rotated'),
        dict(kind='pending',t=10.8,loading=True)])
    r=h.run()
    assert r.succeeded and r.progress_snapshot is None and h.state.detector_calls==0
    assert h.adb.tap.call_count==1


def test_cancel_after_dispatch_prevents_additional_input(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=True,cancel_during_cv=True)])
    with pytest.raises(RuntimeWaitCancelled):h.run()
    assert h.adb.tap.call_count==1


def test_parent_deadline_expires_during_cv_without_extending_wait(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=True,cv_seconds=1.)])
    with control_scope(OperationControl(deadline=10.9,clock=lambda:h.now[0])):
        r=h.run()
    assert not r.succeeded and r.progress_snapshot is None and h.adb.tap.call_count==1


def test_finish_pass_never_repeats_yes_from_progress_board_handoff(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=True),
        dict(kind='clear',t=11.4),dict(kind='ready',t=11.8),dict(kind='ready',t=12.2)])
    accepted=h.run()
    activity=MonsterWaveActivity(h.observer,h.transition.actions,h.events,
        verified_transition=h.transition,clock=lambda:h.now[0],
        sleeper=lambda s:h.now.__setitem__(0,h.now[0]+s))
    result=activity.finish_pass(accepted.final_snapshot)
    assert result.succeeded
    kinds=[f['action_kind'] for e,f in h.events.records if e=='action.dispatched']
    assert kinds==['AcceptMonsterWaveInventory','AcknowledgeMonsterWaveClear']
    assert h.state.detector_calls==1  # No detector in the passive result loop/ACK.


def test_no_global_registration_or_missing_context_detectors(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3,loading=True)])
    assert not any(isinstance(d,GlobalLoadingDetector) for d in h.observer.perception.detectors)
    engine=h.observer.perception
    object.__setattr__(engine,'detectors',tuple(d for d in engine.detectors
        if getattr(getattr(d,'spec',None),'name',None)!=MW_CLEAR))
    r=h.run()
    assert r.succeeded and r.progress_snapshot is None and h.state.detector_calls==0


def test_real_standalone_yes_entry_uses_the_contextual_handoff(monkeypatch):
    from bot.monster_wave_standalone import MonsterWaveStandaloneNavigationRuntime
    from bot.flow_contracts import FlowStatus
    h=scenario(monkeypatch,[dict(kind='board',t=10.3),dict(kind='board',t=10.6),
        dict(kind='pending',t=11.,loading=True)])
    navigation=MonsterWaveStandaloneNavigationRuntime(h.transition,None,clock=lambda:h.now[0])
    status,after=navigation.accept_board(SimpleNamespace(context=h.before))
    assert status is FlowStatus.COMPLETED and after.sequence==4
    assert h.state.detector_calls==1 and h.adb.tap.call_count==1


def test_disappeared_loading_without_result_remains_bounded_and_never_yes_again(monkeypatch):
    from bot.flow_contracts import FlowStatus
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=True),
        dict(kind='pending',t=11.4,loading=False)])
    accepted=h.run()
    activity=MonsterWaveActivity(h.observer,h.transition.actions,h.events,
        verified_transition=h.transition,clock=lambda:h.now[0],
        sleeper=lambda s:h.now.__setitem__(0,h.now[0]+s))
    result=activity.finish_pass(accepted.final_snapshot)
    assert result.status is FlowStatus.FAILED and result.error=='mw_skip_result_unobservable'
    assert h.adb.tap.call_count==1 and h.state.detector_calls==1
    assert h.now[0]<=70.4


def test_occluded_then_visible_loading_uses_fresh_frame_without_extra_stability(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='board',t=10.3,loading=False),
        dict(kind='board',t=10.8,loading=True)])
    r=h.run()
    assert r.succeeded and r.progress_snapshot.sequence==3
    assert h.state.source_calls==3 and h.state.detector_calls==2
    assert h.adb.tap.call_count==1 and h.now[0]==10.8


def test_coverage_scope_does_not_omit_any_original_detector(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3)])
    original=h.observer.perception
    wrapped=_ContextCoverage(original,SimpleNamespace(before=h.before,valid=True))
    baseline=original.analyze(h.before.frame)
    annotated=wrapped.analyze(h.before.frame)
    assert wrapped.engine is original
    assert annotated.observations==baseline.observations
    assert annotated.sequence==baseline.sequence and YES_CONTEXT_COVERAGE in annotated.coverage


@pytest.mark.parametrize('kind,loading',[('clear',True),('pending',False),('pending',True)])
def test_simulated_latency_dispatch_and_base_analysis_parity(monkeypatch,kind,loading):
    counts=[]
    for enabled in (False,True):
        with monkeypatch.context() as mp:
            h=scenario(mp,[dict(kind=kind,t=10.3,loading=loading)],enabled=enabled)
            r=h.run()
            counts.append((r.succeeded,h.now[0],h.adb.tap.call_count,
                h.state.source_calls,h.state.base_analyses,h.state.detector_calls))
    assert counts[0][:5]==counts[1][:5]==(True,10.3,1,2,2)
    assert counts[0][5]==0 and counts[1][5]==(0 if kind=='clear' else 1)


def test_cancel_before_dispatch_sends_nothing(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3,loading=True)])
    h.cancelled[0]=True
    with pytest.raises(RuntimeWaitCancelled):h.run()
    assert h.adb.tap.call_count==0 and h.state.detector_calls==0


def test_wrong_operation_receipt_cannot_activate_detector(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3,loading=True)])
    original=ActionExecutor.execute
    def mismatched(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        return replace(result,dispatch=replace(result.dispatch,operation_id='other-operation'))
    monkeypatch.setattr(ActionExecutor,'execute',mismatched)
    r=h.run()
    assert r.succeeded and r.progress_snapshot is None
    assert h.adb.tap.call_count==1 and h.state.detector_calls==0


def test_uncertain_transport_failure_never_retries_or_runs_detector(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3,loading=True)])
    h.adb.tap.side_effect=OSError('simulated transport failure')
    r=h.run()
    assert not r.succeeded and r.attempt_count==1 and r.progress_snapshot is None
    assert h.adb.tap.call_count==1 and h.state.detector_calls==0


def test_execute_only_legacy_adapter_is_not_required_to_expose_observer(monkeypatch):
    h=scenario(monkeypatch,[dict(kind='pending',t=10.3)])
    sentinel=object();legacy=SimpleNamespace(execute=Mock(return_value=sentinel))
    assert execute_monster_wave_yes(legacy,'legacy-yes',h.before) is sentinel
    assert legacy.execute.call_count==1 and h.state.detector_calls==0


def test_s1_saved_monotonic_timeline_proves_initial_age_rejection(monkeypatch):
    # S1 #361: seq1370 age after reader .891; #364: wait elapsed
    # 2.9412841; seq1387.timestamp - seq1370.timestamp = 1.688.
    # Work between reader and wait can only increase this lower bound.
    minimum_age = .891 + 2.9412841 - (118852.953 - 118851.265)
    assert minimum_age == pytest.approx(2.1442841)
    h = scenario(monkeypatch, [dict(kind='pending', t=14.)])
    h.now[0] = h.before.timestamp + minimum_age
    result = h.run()
    assert result.termination_reason == 'runtime_evidence_rejected'
    assert result.attempt_count == 0 and result.dispatch_receipts == ()
    assert h.adb.tap.call_count == 0


def _slow_yes_source(monkeypatch, after):
    # The 2.0591021s analysis duration is S1 #363's slowest analysis.
    return scenario(monkeypatch, [dict(kind='board', t=10.3),
        dict(kind='board', t=10.6, analysis_seconds=2.0591021)] + after)


def _accept_source(h):
    from bot.monster_wave_standalone import MonsterWaveStandaloneNavigationRuntime
    return MonsterWaveStandaloneNavigationRuntime(h.transition, None,
        clock=lambda: h.now[0], cancel_requested=lambda: h.cancelled[0]).accept_board(
            SimpleNamespace(context=h.before))


def test_s1_passive_reacquisition_after_slow_perception_dispatches_one_yes(monkeypatch):
    from bot.flow_contracts import FlowStatus
    h = _slow_yes_source(monkeypatch, [dict(kind='board', t=12.8),
        dict(kind='board', t=13.1), dict(kind='clear', t=13.5)])
    status, after = _accept_source(h)
    assert status is FlowStatus.COMPLETED and after.sequence == 6
    assert h.adb.tap.call_count == 1
    evidence = next(f for e, f in h.events.records if e == 'monster_wave.yes_source_evidence')
    assert evidence['age'] > evidence['max_age'] == 2.
    assert evidence['source_matches'] and evidence['captured_after'] and not evidence['accepted']
    assert sum(e == 'monster_wave.yes_source_reacquire' for e, _ in h.events.records) == 1
    assert h.now[0] == pytest.approx(13.5)


@pytest.mark.parametrize('row', [dict(kind='clear', t=12.8),
    dict(kind='trade', t=12.8), dict(kind='ambiguous', t=12.8)])
def test_s1_late_effect_or_contradiction_never_authorizes_yes(monkeypatch, row):
    from bot.runtime_observer import RuntimeWaitAborted
    h = _slow_yes_source(monkeypatch, [row])
    with pytest.raises(RuntimeWaitAborted):
        _accept_source(h)
    assert h.adb.tap.call_count == 0


@pytest.mark.parametrize('after', [[],
    [dict(kind='board', t=10.6, at=12.8)],
    [dict(kind='board', t=12.8, analysis_seconds=2.1)]])
def test_s1_passive_tail_rejects_stall_source_timestamp_and_expiry(monkeypatch, after):
    from bot.runtime_observer import RuntimeWaitTimeout
    h = _slow_yes_source(monkeypatch, after)
    with pytest.raises(RuntimeWaitTimeout):
        _accept_source(h)
    assert h.adb.tap.call_count == 0
    # Absolute 6s plus, at most, the synchronous analysis already in flight.
    assert h.now[0] <= 16.0


def test_s1_source_rotation_aborts_even_if_original_source_returns(monkeypatch):
    from bot.runtime_observer import RuntimeWaitAborted
    h = _slow_yes_source(monkeypatch, [dict(kind='board', t=12.8, source='rotated'),
        dict(kind='board', t=13.1), dict(kind='board', t=13.4), dict(kind='clear', t=13.8)])
    with pytest.raises(RuntimeWaitAborted):
        _accept_source(h)
    assert h.adb.tap.call_count == 0


def test_s1_cancellation_in_reacquisition_never_dispatches(monkeypatch):
    h = _slow_yes_source(monkeypatch, [dict(kind='board', t=12.8,
        cancel_during_analysis=True)])
    with pytest.raises(RuntimeWaitCancelled):
        _accept_source(h)
    assert h.adb.tap.call_count == 0


def test_s1_inherited_deadline_bounds_passive_tail(monkeypatch):
    from bot.operation_control import OperationBudgetExpired
    h = _slow_yes_source(monkeypatch, [dict(kind='board', t=12.8)])
    with control_scope(OperationControl(deadline=12.75, clock=lambda: h.now[0])):
        with pytest.raises(OperationBudgetExpired):
            _accept_source(h)
    assert h.adb.tap.call_count == 0


def test_s1_fast_path_has_same_inputs_observations_and_simulated_time(monkeypatch):
    from bot.flow_contracts import FlowStatus
    results = []
    for patched in (False, True):
        with monkeypatch.context() as mp:
            h = scenario(mp, [dict(kind='board', t=10.3), dict(kind='board', t=10.6),
                dict(kind='clear', t=11.)])
            if patched:
                status, _ = _accept_source(h)
                assert status is FlowStatus.COMPLETED
            else:
                before = h.observer.wait_until(lambda s: s.state.overlays == (POPUP_MW_BOARD,),
                    after_sequence=h.before.sequence, timeout=3., stable_for=.25)
                assert execute_monster_wave_yes(h.transition, 'baseline', before).succeeded
            results.append((h.adb.tap.call_count, h.state.source_calls, h.now[0]))
    assert results == [(1, 4, 11.), (1, 4, 11.)]


def test_s1_future_acquisition_is_not_an_age_recovery_permission(monkeypatch):
    from bot.flow_contracts import FlowStatus
    h = scenario(monkeypatch, [dict(kind='board', t=11., at=10.3),
        dict(kind='board', t=11.3, at=10.6)])
    status, _ = _accept_source(h)
    assert status is FlowStatus.FAILED and h.adb.tap.call_count == 0
    assert not any(e == 'monster_wave.yes_source_reacquire' for e, _ in h.events.records)


def test_s1_missing_declared_coverage_is_not_repaired_as_age_only(monkeypatch):
    from bot.flow_contracts import FlowStatus
    h = scenario(monkeypatch, [dict(kind='board', t=10.3), dict(kind='board', t=10.6)])
    h.before = replace(h.before, observations=replace(h.before.observations,
        coverage=frozenset({'declared-board-context'})))
    status, _ = _accept_source(h)
    assert status is FlowStatus.FAILED and h.adb.tap.call_count == 0
    assert not any(e == 'monster_wave.yes_source_reacquire' for e, _ in h.events.records)


def test_s1_expiry_between_source_check_and_dispatch_still_rejects(monkeypatch):
    from bot.flow_contracts import FlowStatus
    h = scenario(monkeypatch, [dict(kind='board', t=10.3), dict(kind='board', t=10.6)])
    record = h.events.record
    def advance_after_source_check(name, **fields):
        record(name, **fields)
        if name == 'monster_wave.yes_source_evidence':
            h.now[0] += 2.1
    h.events.record = advance_after_source_check
    status, _ = _accept_source(h)
    assert status is FlowStatus.FAILED and h.adb.tap.call_count == 0
    assert any(e == 'transition.completed' and f['termination_reason'] == 'runtime_evidence_rejected'
        for e, f in h.events.records)
