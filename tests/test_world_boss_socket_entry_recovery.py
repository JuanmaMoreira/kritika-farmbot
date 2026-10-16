"""WB Full -> Socket H&H regression: no replay of Start or entry input."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_world_boss_flow import build_flow, snapshot, FakeTime
from bot.action_executor import DispatchReceipt, DispatchState
from bot.catalog import SCREEN_WORLD_BOSS, SCREEN_SOCKET, POPUP_SOCKET_INVENTORY_FULL
from bot.obstruction_recovery import PortalObstructionRecovery
from bot.portal_notification import PortalProbeOutcome
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import AcceptSocketInventoryFull, DismissPortalNotification
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionOutcome, VerifiedTransitionResult


def setup_recovery(probe_outcome=PortalProbeOutcome.CONFIRMED):
    clock=FakeTime();clock.current=11.5
    flow, observer, _, _, _, driver=build_flow(sapphire_read=None,fake_time=clock)
    def frame(seq, **kwargs):
        s=snapshot(seq,**kwargs)
        return replace(s,frame=replace(s.frame,source_id='live-source'))
    source=frame(10,base=SCREEN_WORLD_BOSS,overlays=(POPUP_SOCKET_INVENTORY_FULL,))
    hidden=frame(11)
    fresh=frame(12,base=SCREEN_SOCKET)
    settled=frame(13,base=SCREEN_SOCKET)
    inputs=[]
    def observe():
        clock.current=12.5
        return fresh
    def wait(condition,**kwargs):
        clock.current=13.5
        assert kwargs['after_sequence']==fresh.sequence
        assert condition(settled)
        assert kwargs['evidence'].accepts(settled,clock.clock())
        return settled
    observer.wait_until=Mock(side_effect=wait)
    probe=Mock();probe.probe.side_effect=[probe_outcome,PortalProbeOutcome.ABSENT]
    recovery=PortalObstructionRecovery(SimpleNamespace(observe=observe),
        SimpleNamespace(execute=lambda action, geometry, **kwargs: (
            kwargs.get('before_dispatch',lambda:None)(),inputs.append(action))),
        probe,clock=clock.clock,sleeper=clock.sleep)
    driver.obstruction_recovery=recovery
    receipt=DispatchReceipt(DispatchState.ADB_RETURNED,operation_id='entry',
        attempt_index=1,started_at=10.1,completed_at=10.5,commands_started=1,
        commands_returned=1,commands_planned=1)
    result=VerifiedTransitionResult('world_boss.accept_inventory_full',
        VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,1,1,hidden,'retry_guard_rejected',
        elapsed=9.,operation_id='entry',action_source_snapshot=source,dispatch_receipts=(receipt,))
    return flow.activity,driver,result,inputs,probe,observer,clock


def test_wb_socket_entry_integration_recovers_without_replaying_input():
    owner,driver,result,inputs,probe,observer,_=setup_recovery()
    driver.execute=Mock(return_value=result)
    traces=[]
    final=owner._transition(traces,result.name,AcceptSocketInventoryFull(),
        result.action_source_snapshot,expected=lambda s:s.state.base_context==SCREEN_SOCKET,
        precondition=lambda s:True,retryable_from=lambda s:False)
    assert final.state.base_context==SCREEN_SOCKET
    driver.execute.assert_called_once()
    assert inputs==[DismissPortalNotification()]
    assert traces[-1].succeeded and traces[-1].ready and traces[-1].effect_accredited
    assert traces[-1].dispatch_receipts==result.dispatch_receipts
    assert traces[-1].recovery_after_action
    observer.wait_until.assert_called_once()


@pytest.mark.parametrize('case',['no_receipt','uncertain_input','foreign_source','stale',
    'before_receipt','mixed_receipt','missing_completion','foreign_base','ambiguous',
    'upper_layer','wrong_origin','already_recovered','effect_accredited','uncertain_receipt',
    'future','coverage_lost'])
def test_invalid_wb_socket_handoff_never_probes_or_dispatches(case):
    owner,_,r,inputs,probe,_,clock=setup_recovery()
    if case=='no_receipt':r=replace(r,dispatch_receipts=())
    if case=='uncertain_input':r=replace(r,action_source_snapshot=None)
    if case=='foreign_source':r=replace(r,final_snapshot=replace(r.final_snapshot,frame=replace(r.final_snapshot.frame,source_id='other')))
    if case=='stale':clock.current=14.
    if case=='before_receipt':r=replace(r,dispatch_receipts=(replace(r.dispatch_receipts[0],completed_at=11.1),))
    if case=='mixed_receipt':r=replace(r,dispatch_receipts=(replace(r.dispatch_receipts[0],operation_id='other'),))
    if case=='missing_completion':r=replace(r,dispatch_receipts=(replace(r.dispatch_receipts[0],completed_at=None),))
    if case=='foreign_base':r=replace(r,final_snapshot=snapshot(11,base='screen.lobby'))
    if case=='ambiguous':r=replace(r,final_snapshot=snapshot(11,status=ResolutionStatus.AMBIGUOUS))
    if case=='upper_layer':r=replace(r,final_snapshot=snapshot(11,overlays=('popup.equipment_inventory_full',)))
    if case=='wrong_origin':r=replace(r,action_source_snapshot=snapshot(10,base=SCREEN_WORLD_BOSS))
    if case=='already_recovered':r=replace(r,recovery_after_action=True)
    if case=='effect_accredited':r=replace(r,effect_accredited=True)
    if case=='uncertain_receipt':r=replace(r,dispatch_receipts=(replace(r.dispatch_receipts[0],state=DispatchState.UNCERTAIN),))
    if case=='future':clock.current=10.9
    if case=='coverage_lost':r=replace(r,action_source_snapshot=replace(r.action_source_snapshot,observations=replace(r.action_source_snapshot.observations,coverage=frozenset({'socket'}))))
    assert owner._recover_socket_entry(r) is r
    assert inputs==[]
    probe.probe.assert_not_called()


@pytest.mark.parametrize('outcome',[PortalProbeOutcome.ABSENT,PortalProbeOutcome.INCONCLUSIVE])
def test_missing_portal_authority_preserves_failure_without_input(outcome):
    owner,_,r,inputs,_,observer,_=setup_recovery(outcome)
    assert owner._recover_socket_entry(r) is r
    assert inputs==[]
    observer.wait_until.assert_not_called()


def test_wb_socket_recovery_cancelled_before_probe():
    owner,_,r,inputs,probe,_,_=setup_recovery()
    owner.cancel_requested=lambda:True
    with pytest.raises(RuntimeWaitCancelled):owner._recover_socket_entry(r)
    assert inputs==[]
    probe.probe.assert_not_called()


def test_wb_socket_recovery_cancelled_after_cleanup_never_starts_relief():
    owner,driver,r,inputs,_,observer,_=setup_recovery()
    cancelled=[False]
    owner.cancel_requested=lambda:cancelled[0]
    original=driver.obstruction_recovery.observer.observe
    def observe():
        fresh=original();cancelled[0]=True
        return fresh
    driver.obstruction_recovery.observer.observe=observe
    with pytest.raises(RuntimeWaitCancelled):owner._recover_socket_entry(r)
    assert inputs==[DismissPortalNotification()]
    observer.wait_until.assert_not_called()
