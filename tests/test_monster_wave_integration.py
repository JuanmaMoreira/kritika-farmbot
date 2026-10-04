"""Real WB/MW factories, session zone ownership, business reports and manual UI."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.auto_battle import EnsureAutoBattleStatus
from bot.catalog import SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT, OVERLAY_WORLD_BOSS_RAID_COMPLETE
from bot.config import RuntimeConfig
from bot.event_log import RuntimeEventStream
from bot.flow_contracts import FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.gui_controller import _flow_status, _session_status, GuiRunStatus
from bot.monster_wave_config import MonsterWaveConfig
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_semantics import *
from bot.session import SessionStatus
from bot.session_report import ReportStatus, build_session_report
from test_monster_wave import Device, NEEDS, READY, ACTIVE
from test_productive_runtime import _runtime
from test_world_boss_flow import fact_result
from test_session import Rotation


def runtime_for(monkeypatch, device, *, config=MonsterWaveConfig(), sapphires=20, mw_sapphires=None):
    # Device facts use sequence time. The new Lobby gate also requires a
    # fresh read after its observation barrier, not the previously current frame.
    from bot.monster_wave_activity import MonsterWaveActivity
    original_init=MonsterWaveActivity.__init__
    def init(activity,*args,**kwargs):
        original_init(activity,*args,**kwargs);activity.clock=lambda:float(device.sequence)
    monkeypatch.setattr(MonsterWaveActivity,'__init__',init)
    records=[];stream=RuntimeEventStream(consumers=(records.append,))
    runtime=_runtime(device,stream);runtime.actions=device
    runtime.socket_relief=Mock();runtime.equipment_combine_relief=Mock()
    runtime.config=RuntimeConfig('test','test',monster_wave=config)
    def read_sapphires(**kwargs):
        context=kwargs.get('context',SCREEN_LOBBY)
        device.trace.append(('sapphires',context))
        value=sapphires
        if context==SCREEN_LOBBY:
            assert device.base==SCREEN_LOBBY
            device.observe();device.observe()
        if context==SCREEN_BATTLE_MODE_SELECT:
            assert device.base==SCREEN_BATTLE_MODE_SELECT and not device.overlays
            assert device.sequence>=kwargs['after_sequence']
            device.observe();device.observe()
            value=sapphires if mw_sapphires is None else mw_sapphires
        if context==SCREEN_MONSTER_WAVE:
            assert device.base==SCREEN_MONSTER_WAVE and not device.overlays
            device.observe();device.observe()
            value=max(0, sapphires - 100 * device.intents.count('AcknowledgeMonsterWaveClear'))
        return fact_result('resource.sapphires',value,device.sequence,context)
    runtime.facts=Mock(read_sapphires=Mock(side_effect=read_sapphires))
    def auto(**kwargs):
        device.overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,)
        return SimpleNamespace(status=EnsureAutoBattleStatus.INTERRUPTED, observations=(),tap_count=0)
    runtime.auto_battle=Mock(ensure_on_quick=auto)
    monkeypatch.setattr(runtime,'_shared_obstruction_recovery',lambda:None)
    rotation=Rotation(1,[])
    rotation.preferred_entry=MonsterWaveFlow.contract.precondition
    monkeypatch.setattr(runtime,'build_rotation',lambda count:rotation)
    return runtime,records,rotation


@pytest.mark.parametrize('order',[('world_boss','monster_wave'),('monster_wave','world_boss')])
@pytest.mark.parametrize('daily',[True,False])
def test_real_prepared_consumers_preserve_order_and_one_visit(monkeypatch,order,daily):
    d=Device(base=SCREEN_LOBBY,daily=daily)
    runtime,records,rotation=runtime_for(monkeypatch,d)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(order),character_count=1)
    assert r.status is SessionStatus.COMPLETED, r
    assert d.base==SCREEN_LOBBY
    assert d.intents.count('OpenBattleModeSelect')==1
    # Final MW retains MW for the Lobby request; final WB already returns hub.
    assert d.intents.count('ExitBattleModeSelect')==int(order[-1]=='world_boss')
    assert d.intents.count('OpenQuickMenu')==int(order[-1]=='monster_wave')
    assert d.intents.count('SelectQuickMenuLobby')==int(order[-1]=='monster_wave')
    assert d.intents.count('OpenMonsterWave')==1
    assert r.flow_names==order
    if daily:
        assert (d.intents.index('OpenMonsterWave')<d.intents.index('OpenWorldBossSelector'))==(order[0]=='monster_wave')
    mw=r.character_results[0].flow_results[order.index('monster_wave')]
    assert mw.status is FlowStatus.COMPLETED
    assert rotation.calls==1
    report=build_session_report(r)
    assert report.status is ReportStatus.COMPLETE
    assert not any(e.event.endswith('.failed') for e in records)


@pytest.mark.parametrize('mode',['selected','flow_once'])
def test_manual_runtime_never_applies_daily(monkeypatch,mode):
    d=Device(base=SCREEN_LOBBY,daily=False);runtime,records,_=runtime_for(monkeypatch,d)
    definition=DEFAULT_FLOW_REGISTRY.get('monster_wave')
    r=runtime.run_flows_once((definition,)) if mode=='selected' else runtime.run_flow(definition)
    assert r.status is FlowStatus.COMPLETED
    assert 'StartMonsterWaveSkip' in d.intents and d.base==SCREEN_MONSTER_WAVE
    assert not any(e.event=='flow.skipped_not_eligible' for e in records)


@pytest.mark.parametrize('boundary',[POPUP_MW_INSUFFICIENT,POPUP_MW_BOARD])
def test_business_outcomes_project_to_session_report(monkeypatch,boundary):
    d=Device(base=SCREEN_LOBBY,boundary=boundary);runtime,records,_=runtime_for(monkeypatch,d)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    report=build_session_report(r)
    assert r.status is SessionStatus.COMPLETED
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE
    assert report.failure is None and report.counts.technical_failure==0
    assert any(e.fields.get('event_role')=='business' for e in records)


def test_manual_resolution_stops_before_zone_leave_next_flow_and_rotation(monkeypatch):
    from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL
    d=Device(base=SCREEN_LOBBY,boundary=POPUP_EQUIPMENT_INVENTORY_FULL)
    runtime,records,rotation=runtime_for(monkeypatch,d)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave','world_boss']),character_count=1)
    assert r.status is SessionStatus.MANUAL_RESOLUTION
    assert d.intents[-1]=='StartMonsterWaveSkip'
    assert rotation.calls==0
    report=build_session_report(r)
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE and report.failure is None
    assert report.characters[0].flows[0].status is ReportStatus.BUSINESS_INCOMPLETE
    assert _session_status(r.status) is GuiRunStatus.MANUAL_RESOLUTION
    assert _flow_status(r.character_results[0].flow_results[0].status) is GuiRunStatus.MANUAL_RESOLUTION
    assert any(e.event=='session.manual_resolution' and e.fields['event_role']=='lifecycle' for e in records)
    assert not any(e.event.endswith('.failed') for e in records)


def test_opt_in_board_handoff_stops_session_without_next_flow_or_rotation(monkeypatch):
    d=Device(base=SCREEN_LOBBY,boundary=POPUP_MW_BOARD)
    runtime,records,rotation=runtime_for(monkeypatch,d)
    original=MonsterWaveFlow.prepared
    monkeypatch.setattr(MonsterWaveFlow,'prepared',
        lambda self,zone: original(
            self,zone,yield_resource_board=True))
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave','world_boss']),
                          character_count=1)
    assert r.status is SessionStatus.FAILED
    assert r.failure_cause == 'resource_board_pending'
    assert r.character_results[0].flow_results[0].status is FlowStatus.RESOURCE_BOARD_PENDING
    assert len(r.character_results[0].flow_results)==1
    assert rotation.calls==0
    assert d.base==SCREEN_MONSTER_WAVE and d.overlays==(POPUP_MW_BOARD,)
    assert d.intents[-1]=='StartMonsterWaveSkip'
    assert sum(intent=='OpenMonsterWave' for intent in d.intents)==1
    assert any(e.event=='flow.resource_board_pending' for e in records)
    assert not any(e.event=='flow.manual_resolution' for e in records)
    assert _flow_status(r.character_results[0].flow_results[0].status) is GuiRunStatus.FAILED


def test_technical_failure_preserves_cause_and_business_evidence(monkeypatch):
    d=Device(NEEDS,base=SCREEN_LOBBY,purchase_ok=False)
    runtime,records,rotation=runtime_for(monkeypatch,d,config=MonsterWaveConfig(True,False))
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    report=build_session_report(r)
    assert r.status is SessionStatus.FAILED and report.status is ReportStatus.TECHNICAL_FAILURE
    assert r.failure is not None and report.failure==r.failure
    assert any(e.event=='flow.failed' and e.fields.get('failure') for e in records)
    assert rotation.calls==0 and 'SelectQuickMenuLobby' not in d.intents


def test_wb_precheck_business_terminal_does_not_block_mw(monkeypatch):
    d=Device(base=SCREEN_LOBBY);runtime,_,_=runtime_for(monkeypatch,d,sapphires=4)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['world_boss','monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED
    assert 'StartWorldBossBattle' not in d.intents and 'StartMonsterWaveSkip' in d.intents
    assert d.intents.count('OpenBattleModeSelect')==1


def test_intervening_flow_closes_visit_without_reorder(monkeypatch):
    from bot.flow_contracts import FlowResult
    from test_session import Flow
    d=Device(base=SCREEN_LOBBY);runtime,_,_=runtime_for(monkeypatch,d)
    original=runtime.build_flow
    def build(definition):
        if definition.id=='mailbox':return Flow('mailbox',[FlowResult(FlowStatus.COMPLETED)],d.intents)
        return original(definition)
    monkeypatch.setattr(runtime,'build_flow',build)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave','mailbox','world_boss']),character_count=1)
    assert r.status is SessionStatus.COMPLETED
    assert d.intents.count('OpenBattleModeSelect')==2
    assert d.intents.index('SelectQuickMenuLobby')<d.intents.index('mailbox.run')<d.intents.index('OpenWorldBossSelector')


@pytest.mark.parametrize('daily',[True,False])
@pytest.mark.parametrize('entry',[NEEDS,READY,ACTIVE])
def test_zero_sapphires_skips_without_entering_mw(monkeypatch,daily,entry):
    d=Device(entry,base=SCREEN_LOBBY,daily=daily)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=0)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED and d.base==SCREEN_LOBBY
    assert d.intents==[]
    result=r.character_results[0].flow_results[0]
    assert result.sapphires_initial==0
    assert result.event_count('monster_wave.no_work')==1
    runtime.facts.read_sapphires.assert_called_once()


@pytest.mark.parametrize('balance',[1,2,3,4,5,100,183])
@pytest.mark.parametrize('daily',[True,False])
def test_positive_balance_allows_skip_without_daily_gate(monkeypatch,balance,daily):
    d=Device(base=SCREEN_LOBBY,daily=daily)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=balance)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED
    assert 'StartMonsterWaveSkip' in d.intents
    assert runtime.facts.read_sapphires.call_args.kwargs['context']==SCREEN_BATTLE_MODE_SELECT


def test_world_boss_balance_is_not_reused_for_mw(monkeypatch):
    d=Device(base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=8,mw_sapphires=0)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['world_boss','monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED
    assert 'StartWorldBossBattle' in d.intents and 'OpenMonsterWave' not in d.intents
    assert d.trace.index(('intent','ExitWorldBoss'))<d.trace.index(('sapphires',SCREEN_BATTLE_MODE_SELECT))
    assert r.character_results[0].flow_results[1].event_count('monster_wave.no_work')==1


@pytest.mark.parametrize('balance',[1,2,3])
@pytest.mark.parametrize('mode',['selected','flow_once'])
def test_manual_low_balance_ignores_daily_minimum(monkeypatch,balance,mode):
    d=Device(base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=balance)
    definition=DEFAULT_FLOW_REGISTRY.get('monster_wave')
    r=runtime.run_flows_once((definition,)) if mode=='selected' else runtime.run_flow(definition)
    assert r.status is FlowStatus.COMPLETED and 'StartMonsterWaveSkip' in d.intents
    assert runtime.facts.read_sapphires.call_count==2
    assert runtime.facts.read_sapphires.call_args_list[0].kwargs['context']==SCREEN_LOBBY
    assert runtime.facts.read_sapphires.call_args.kwargs['context']==SCREEN_BATTLE_MODE_SELECT


@pytest.mark.parametrize('entry,ack',[(POPUP_MW_WEEKLY,'AcknowledgeMonsterWaveWeekly'),
                                   (POPUP_MW_RANKING,'AcknowledgeMonsterWaveRanking')])
def test_precheck_precedes_entry_normalization_and_report_is_complete(monkeypatch,entry,ack):
    d=Device(entry,base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert build_session_report(r).status is ReportStatus.COMPLETE
    assert d.trace.index(('sapphires',SCREEN_BATTLE_MODE_SELECT))<d.trace.index(('intent',ack))
    assert d.trace.index(('sapphires',SCREEN_BATTLE_MODE_SELECT))<d.trace.index(('intent','SelectMonsterWaveMax'))


@pytest.mark.parametrize('problem',['unreadable','uncertain','failure','timeout','context_mismatch',
                                   'old_fact','lobby_fact','exception','cancelled'])
def test_failed_or_stale_precheck_never_authorizes_input(monkeypatch,problem):
    from bot.runtime_facts import FactReadResult, FactReadStatus
    d=Device(base=SCREEN_LOBBY);runtime,_,_=runtime_for(monkeypatch,d)
    original=runtime.facts.read_sapphires.side_effect
    def read(**kwargs):
        if kwargs.get('context')==SCREEN_LOBBY:return original(**kwargs)
        if problem=='exception':raise RuntimeError('OCR failed')
        if problem in {'old_fact','lobby_fact'}:
            seq=kwargs['after_sequence'] if problem=='old_fact' else d.observe().sequence
            return fact_result('resource.sapphires',100,seq,
                               SCREEN_LOBBY if problem=='lobby_fact' else SCREEN_BATTLE_MODE_SELECT)
        return FactReadResult(FactReadStatus(problem))
    runtime.facts.read_sapphires.side_effect=read
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is (SessionStatus.CANCELLED if problem=='cancelled' else SessionStatus.FAILED)
    assert d.intents==['OpenBattleModeSelect']
    if problem!='cancelled':assert build_session_report(r).status is ReportStatus.TECHNICAL_FAILURE


def test_entry_observes_skip_after_precheck_and_uses_new_state(monkeypatch):
    d=Device(ACTIVE,base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,config=MonsterWaveConfig(False,False))
    original=runtime.facts.read_sapphires.side_effect
    def read(**kwargs):
        result=original(**kwargs)
        d.entry=NEEDS
        return result
    runtime.facts.read_sapphires.side_effect=read
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED and 'SelectMonsterWaveMax' in d.intents
    assert r.character_results[0].flow_results[0].event_count('monster_wave.tickets_missing_purchase_disabled')==0
    assert r.character_results[0].flow_results[0].event_count('monster_wave.tickets_purchased')==1


@pytest.mark.parametrize('balance,passes', [(0,0),(1,0),(99,0),(101,0),(102,1),(199,1),(200,1),(201,1),(299,2),(300,2)])
def test_productive_session_uses_hub_balance_once_without_badge(monkeypatch,balance,passes):
    from bot.monster_wave_productive import ProductiveMonsterWaveFlow
    d=Device(base=SCREEN_LOBBY,daily=False)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=balance)
    inner=MonsterWaveFlow(d,d,d.events,facts=runtime.facts,sleeper=lambda _:None)
    productive=ProductiveMonsterWaveFlow(inner,boards=Mock(),navigation=Mock(),route=Mock())
    monkeypatch.setattr(runtime,'build_flows',lambda _: (productive,))
    r=runtime.run_session((),character_count=1)
    assert r.status is SessionStatus.COMPLETED, r
    result=r.character_results[0].flow_results[0]
    assert result.sapphires_initial==balance
    assert result.sapphires_consumed==passes*100
    assert d.intents.count('StartMonsterWaveSkip')==passes
    assert d.intents.count('SelectMonsterWaveMax')==int(passes>0)
    assert d.intents.count('OpenMonsterWave')==int(passes>0)
    assert runtime.facts.read_sapphires.call_count==(1 if passes==0 else 2+passes)
    assert runtime.facts.read_sapphires.call_args_list[0].kwargs['context']==SCREEN_LOBBY
    assert runtime.facts.read_sapphires.call_args.kwargs['context']==(SCREEN_LOBBY if passes==0 else SCREEN_MONSTER_WAVE)
    if passes:
        assert d.trace.index(('sapphires',SCREEN_BATTLE_MODE_SELECT))<d.trace.index(('intent','OpenMonsterWave'))
