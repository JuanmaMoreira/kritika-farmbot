"""Dedicated GUI sweep composes existing Session/collector/Rotation owners."""
from dataclasses import replace
from types import SimpleNamespace
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from bot.catalog import SCREEN_LOBBY
from bot.character_identity import CHARACTER_IDS, PERSONAL_NAME_CLASSES, CharacterIdentity
from bot.character_data import CharacterDataCollector, ResourceSnapshotMode
from bot.character_state import CharacterStateStore, current_character_state
from bot.event_log import RuntimeEventStream
from bot.gui_model import GuiExecutionRequest, GuiRunMode
from bot.gui_controller import GuiRuntimeController, GuiMessageKind, GuiRunStatus
from bot.productive_runtime import ProductiveRuntime, CancellationToken
from bot.preconditions import MinimalPreconditionEnsurer
from bot.rotation import RotationResult, RotationOutcome
from bot.session import SessionPlan, SessionStatus


def _sweep(tmp_path, monkeypatch, *, unknown=None, unreadable=None, duplicate=None, cancel=None):
    import bot.productive_runtime as productive
    from test_session import Rotation

    events = RuntimeEventStream()
    records = []
    events.subscribe(records.append)
    store = CharacterStateStore(tmp_path/'state.db', now=lambda: 1_000_000., events=events)
    ids = list(CHARACTER_IDS.values())
    for cid in ids:
        store.ads(cid, 'OBSERVED', observed_count=0)
        store.wb(cid, True, source='RAID_COMPLETE')
        store.resources(cid, dict(lapiz=999, dark_essence=999, light_essence=999,
                                  nature_essence=999, k_coins=999))
    operational = [dict(store.operational(cid)) for cid in ids]
    token = CancellationToken()
    index = [0]
    trace = []
    runtime = ProductiveRuntime(config=object(),observer=object(),actions=object(),facts=object(),
        auto_battle=object(),socket_relief=object(),equipment_combine_relief=object(),
        pet_summon_space_relief=object(),events=events,cancel_token=token,character_store=store,
        resource_snapshot_mode='OFF',ocr_engine=object())

    names = list(CHARACTER_IDS)
    def recognize(snapshot):
        i = snapshot.sequence//10
        if i == unknown:
            return None
        if i == duplicate:
            i -= 1
        name = names[i]
        return CharacterIdentity(name,PERSONAL_NAME_CLASSES[name],.99)
    monkeypatch.setattr(productive,'LobbyNameRecognizer',lambda engine: SimpleNamespace(recognize=recognize))
    def current():
        runtime._identity_snapshot = SimpleNamespace(sequence=index[0]*10)
        return SCREEN_LOBBY
    preconditions = MinimalPreconditionEnsurer(current)
    monkeypatch.setattr(runtime,'build_preconditions',lambda: preconditions)
    monkeypatch.setattr(runtime,'build_flows',lambda definitions: () if not definitions else pytest.fail('gameplay'))

    def read(snapshot, **kwargs):
        trace.append(('snapshot',index[0],current_character_state()[1]))
        if index[0] == unreadable:
            return None
        n = index[0]+1
        return dict(lapiz=n,dark_essence=n*2,light_essence=n*3,nature_essence=n*4,k_coins=n*5)
    collector = CharacterDataCollector(SimpleNamespace(read=read),events=events)
    class SweepRotation(Rotation):
        def advance(self):
            trace.append(('QM',index[0]))
            events.record('transition.started',transition='rotation.open_quick_menu')
            events.record('transition.completed',transition='rotation.open_quick_menu',final_sequence=index[0]*10+1)
            self.quick_menu_ready(SimpleNamespace(sequence=index[0]*10+1),origin=SCREEN_LOBBY)
            if index[0] == cancel:
                token.request()
                return RotationResult(RotationOutcome.ABORTED,error='RuntimeWaitCancelled')
            trace.append(('Select',index[0]))
            events.record('transition.started',transition='rotation.open_character_select')
            index[0] += 1
            return RotationResult(RotationOutcome.SUCCESS)
    rotation = SweepRotation(28,[])
    rotation.quick_menu_ready = collector.before_rotation
    monkeypatch.setattr(runtime,'build_rotation',lambda count: rotation)
    result = runtime.run_character_data_sweep()
    assert runtime.resource_snapshot_mode == 'OFF'
    assert runtime._identity_snapshot is None and not runtime._identity_active
    assert current_character_state() is None
    assert [dict(store.operational(cid)) for cid in ids] == operational
    return result,store,trace,records,ids


def test_full_roster_correct_scope_snapshot_then_rotation_and_reopen(tmp_path,monkeypatch):
    result,store,trace,records,ids = _sweep(tmp_path,monkeypatch)
    assert result.status is SessionStatus.COMPLETED
    assert (result.characters_processed,result.identities_resolved,result.snapshots_updated,
            result.advances_completed,result.acquisition_failures) == (28,28,28,28,0)
    assert all(not c.flow_results for c in result.character_results)
    assert len([t for t in trace if t[0]=='QM']) == 28
    for i,cid in enumerate(ids):
        assert trace[i*3:i*3+3] == [('QM',i),('snapshot',i,cid),('Select',i)]
    assert not any(r.event.startswith(('flow.','stages.','world_boss.')) for r in records)
    assert next(r for r in records if r.event=='character_data_sweep.completed').fields['snapshots_updated']==28
    path=store.path
    store.close()
    reopened=CharacterStateStore(path,now=lambda:1_000_001.)
    try:
        rows={r['character_id']:r for r in reopened.rows()}
        assert all(rows[cid]['lapiz']==i+1 and rows[cid]['k_coins']==(i+1)*5 for i,cid in enumerate(ids))
    finally:
        reopened.close()


@pytest.mark.parametrize('failure',['unknown','unreadable','duplicate'])
def test_acquisition_failure_preserves_previous_row_and_continues(tmp_path,monkeypatch,failure):
    result,store,trace,records,ids = _sweep(tmp_path,monkeypatch,**{failure:3})
    try:
        assert result.status is SessionStatus.MANUAL_RESOLUTION
        assert (result.snapshots_updated,result.acquisition_failures,result.advances_completed)==(27,1,28)
        assert next(r for r in store.rows() if r['character_id']==ids[3])['lapiz']==999
        assert next(r for r in store.rows() if r['character_id']==ids[2])['lapiz']==3
    finally:
        store.close()


def test_stop_during_rotation_preserves_saved_snapshot_and_clears_scope(tmp_path,monkeypatch):
    result,store,trace,records,ids = _sweep(tmp_path,monkeypatch,cancel=3)
    try:
        assert result.status is SessionStatus.CANCELLED
        assert result.snapshots_updated==4 and result.advances_completed==3
        rows={r['character_id']:r for r in store.rows()}
        assert rows[ids[3]]['lapiz']==4 and rows[ids[4]]['lapiz']==999
    finally:
        store.close()


def test_empty_session_requires_explicit_data_mode_and_rotation():
    from test_session import Rotation,Flow
    with pytest.raises(ValueError):
        SessionPlan.standard(flows=(),rotate=True,rotation_strategy=Rotation(28,[]),character_count=28)
    with pytest.raises(ValueError):
        SessionPlan.standard(flows=(Flow('forbidden',[],[]),),rotate=True,
            rotation_strategy=Rotation(28,[]),character_count=28,character_data_only=True)
    with pytest.raises(ValueError):
        SessionPlan.standard(flows=(),rotate=False,rotation_strategy=Rotation(28,[]),
            character_count=28,character_data_only=True)


def test_gui_action_all_only_and_worker_never_calls_gameplay(tmp_path):
    request=GuiExecutionRequest.character_data_sweep(log_dir=tmp_path)
    assert request.mode is GuiRunMode.CHARACTER_DATA_SWEEP and request.flow_ids==() and request.character_count==28
    runtime=Mock()
    runtime.run_character_data_sweep.return_value=SimpleNamespace(status=SessionStatus.COMPLETED,
        characters_processed=28,advances_completed=28,identities_resolved=28,snapshots_updated=28,
        acquisition_failures=0,failure_cause=None)
    @contextmanager
    def factory(**kwargs):
        yield runtime
    controller=GuiRuntimeController(runtime_factory=factory)
    for bad in (replace(request,flow_ids=('world_boss',)),replace(request,character_count=1)):
        with pytest.raises(ValueError):
            controller.start(bad)
    controller.start(request)
    assert controller.wait(5)
    runtime.run_character_data_sweep.assert_called_once_with()
    runtime.run_flow.assert_not_called()
    runtime.run_session.assert_not_called()
    runtime.run_routine.assert_not_called()
    result=next(m.result for m in controller.drain() if m.kind is GuiMessageKind.RESULT)
    assert result.status is GuiRunStatus.COMPLETED and result.snapshots_updated==28


def test_gui_button_dispatch_and_completion_progress(tmp_path):
    from test_gui_entrypoint import build_gui_shell,Var
    from bot.gui_controller import GuiExecutionResult
    app=build_gui_shell(lambda:1.)
    app.debug_var=Var(False)
    app.dotenv_path=tmp_path/'.env'
    app.log_dir=tmp_path
    app._run_character_data_sweep()
    assert app.controller.requests[-1].mode is GuiRunMode.CHARACTER_DATA_SWEEP
    app._finish(GuiExecutionResult(GuiRunStatus.COMPLETED,42.,tmp_path/'sweep.log',
        characters_processed=28,advances_completed=28,identities_resolved=28,snapshots_updated=28))
    assert '28 snapshots updated' in app.result_var.get()
    assert '0 acquisition failures' in app.result_var.get()


def test_real_rotation_calls_collector_on_same_qm_before_select():
    from test_rotation import (_rotation,_snapshot,_frame,_selected_frame_at,predecessor_center,
        SENTINEL_COL2,ScriptedSentinel,_found)
    from bot.catalog import MENU_QUICK,SCREEN_CHARACTER_SELECT
    from bot.semantic_actions import OpenQuickMenu,OpenCharacterSelect
    grid=_frame(grid_fill=80)
    qm=_snapshot(2,overlays={MENU_QUICK})
    rotation,actions,_,_= _rotation([_snapshot(1,base=SCREEN_LOBBY)],
        [qm,_snapshot(3,base=SCREEN_CHARACTER_SELECT,image=grid),
         _snapshot(4,base=SCREEN_CHARACTER_SELECT,image=_selected_frame_at(grid,predecessor_center(SENTINEL_COL2))),
         _snapshot(5,base=SCREEN_LOBBY)],sentinel=ScriptedSentinel([_found()]))
    def collect(snapshot, *, origin):
        assert snapshot is qm and origin==SCREEN_LOBBY
        assert actions.actions==[OpenQuickMenu()]
    rotation.quick_menu_ready=collect
    assert rotation.advance().succeeded
    assert sum(isinstance(a,OpenQuickMenu) for a in actions.actions)==1
    assert isinstance(actions.actions[1],OpenCharacterSelect)


def test_audit_rejects_stale_source_and_cross_character_values(tmp_path,monkeypatch):
    import json
    from tools.audit_character_data_sweep import audit
    result,store,trace,records,ids=_sweep(tmp_path,monkeypatch)
    before=tmp_path/'before.json'
    before.write_text(json.dumps([dict(r) for r in store.db.execute('SELECT * FROM operational ORDER BY character_id')]))
    path=store.path
    store.close()
    log=tmp_path/'gui.jsonl'
    payloads=[r.payload() for r in records]
    log.write_text('\n'.join(json.dumps(p) for p in payloads),encoding='utf-8')
    report=audit(log,path,before)
    assert report['errors']==[] and report['latest_complete']==28
    assert report['repeated_snapshots']==[] and report['session_id']
    changed=next(p for p in payloads if p['event']=='character_state.resources_updated' and p.get('character_index')==2)
    changed['character_id']=ids[0]
    log.write_text('\n'.join(json.dumps(p) for p in payloads),encoding='utf-8')
    assert any('scope mismatch' in e for e in audit(log,path,before)['errors'])
