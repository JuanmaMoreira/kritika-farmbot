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
from bot.monster_wave_eligibility import MonsterWaveDailyEligibility
from bot.monster_wave_semantics import *
from bot.eligibility import EligibilityStatus
from bot.session import SessionStatus
from bot.session_report import ReportStatus, build_session_report
from test_monster_wave import Device, NEEDS, READY, ACTIVE
from test_productive_runtime import _runtime
from test_world_boss_flow import fact_result
from test_session import Rotation


def runtime_for(monkeypatch, device, *, config=MonsterWaveConfig(), sapphires=20, mw_sapphires=None):
    records=[];stream=RuntimeEventStream(consumers=(records.append,))
    runtime=_runtime(device,stream);runtime.actions=device
    runtime.socket_relief=Mock();runtime.equipment_combine_relief=Mock()
    runtime.config=RuntimeConfig('test','test',monster_wave=config)
    def read_sapphires(**kwargs):
        context=kwargs.get('context',SCREEN_LOBBY)
        device.trace.append(('sapphires',context))
        value=sapphires
        if context==SCREEN_MONSTER_WAVE:
            assert device.base==SCREEN_MONSTER_WAVE and not device.overlays
            assert device.sequence>=kwargs['after_sequence']
            device.observe();device.observe()
            value=sapphires if mw_sapphires is None else mw_sapphires
        return fact_result('resource.sapphires',value,device.sequence,context)
    runtime.facts=Mock(read_sapphires=Mock(side_effect=read_sapphires))
    def auto(**kwargs):
        device.overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,)
        return SimpleNamespace(status=EnsureAutoBattleStatus.INTERRUPTED, observations=(),tap_count=0)
    runtime.auto_battle=Mock(ensure_on_quick=auto)
    monkeypatch.setattr(runtime,'_shared_obstruction_recovery',lambda:None)
    rotation=Rotation(1,[])
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
    assert d.intents.count('OpenBattleModeSelect')==d.intents.count('OpenQuickMenu')==1
    assert d.intents.count('SelectQuickMenuLobby')==1
    assert d.intents.count('OpenMonsterWave')==int(daily)
    assert r.flow_names==order
    if daily:
        assert (d.intents.index('OpenMonsterWave')<d.intents.index('OpenWorldBossSelector'))==(order[0]=='monster_wave')
    mw=r.character_results[0].flow_results[order.index('monster_wave')]
    assert mw.status is (FlowStatus.COMPLETED if daily else FlowStatus.SKIPPED_NOT_ELIGIBLE)
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
    assert 'StartMonsterWaveSkip' in d.intents and d.base==SCREEN_LOBBY
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
def test_daily_eligibility_observes_hub_and_has_no_input(daily):
    d=Device(daily=daily)
    r=MonsterWaveDailyEligibility(d,cancel_requested=lambda:False).evaluate()
    assert r.status is (EligibilityStatus.ELIGIBLE if daily else EligibilityStatus.NOT_ELIGIBLE)
    assert not d.intents and d.sequence>=4


def test_daily_unknown_does_not_become_absent():
    d=Device(base=None)
    r=MonsterWaveDailyEligibility(d,cancel_requested=lambda:False).evaluate()
    assert r.status is EligibilityStatus.UNKNOWN and r.failure is not None
    assert not d.intents


@pytest.mark.parametrize('balance',range(4))
def test_absent_daily_precedes_resource_guard_without_read_or_entry(monkeypatch,balance):
    d=Device(base=SCREEN_LOBBY,daily=False)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=balance)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.character_results[0].flow_results[0].status is FlowStatus.SKIPPED_NOT_ELIGIBLE
    runtime.facts.read_sapphires.assert_not_called()
    assert 'OpenMonsterWave' not in d.intents


@pytest.mark.parametrize('balance',range(4))
@pytest.mark.parametrize('entry',[NEEDS,READY,ACTIVE])
def test_daily_low_balance_returns_business_before_any_skip_operation(monkeypatch,balance,entry):
    d=Device(entry,base=SCREEN_LOBBY)
    runtime,records,_=runtime_for(monkeypatch,d,sapphires=balance,config=MonsterWaveConfig(True,False))
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED and d.base==SCREEN_LOBBY
    assert d.intents==['OpenBattleModeSelect','OpenMonsterWave','ExitMonsterWave',
                       'OpenQuickMenu','SelectQuickMenuLobby']
    result=r.character_results[0].flow_results[0]
    event=result.events[0]
    assert event.kind=='monster_wave.daily_sapphires_below_minimum'
    assert event.fields['observed_balance']==balance
    assert event.fields['required_sapphires']==4 and event.fields['attempt_started'] is False
    assert result.event_count('monster_wave.insufficient_sapphires')==0
    report=build_session_report(r)
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE and report.failure is None
    assert report.counts.technical_failure==0
    assert any(e.event==event.kind and e.fields['event_role']=='business' for e in records)


@pytest.mark.parametrize('balance',[4,5,100,183])
def test_daily_sufficient_fresh_balance_allows_skip(monkeypatch,balance):
    d=Device(base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=balance)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED
    assert 'StartMonsterWaveSkip' in d.intents
    assert runtime.facts.read_sapphires.call_args.kwargs['context']==SCREEN_MONSTER_WAVE


def test_world_boss_old_eight_does_not_authorize_mw_after_fresh_three(monkeypatch):
    d=Device(base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=8,mw_sapphires=3)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['world_boss','monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED
    assert 'StartWorldBossBattle' in d.intents and 'SelectMonsterWaveMax' not in d.intents
    assert d.trace.index(('sapphires',SCREEN_LOBBY))<d.trace.index(('intent','StartWorldBossBattle'))
    assert d.trace.index(('intent','ExitWorldBoss'))<d.trace.index(('sapphires',SCREEN_MONSTER_WAVE))
    event=r.character_results[0].flow_results[1].events[0]
    assert event.fields['observed_balance']==3
    assert build_session_report(r).status is ReportStatus.BUSINESS_INCOMPLETE


@pytest.mark.parametrize('balance',[1,2,3])
@pytest.mark.parametrize('mode',['selected','flow_once'])
def test_manual_low_balance_ignores_daily_minimum(monkeypatch,balance,mode):
    d=Device(base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,sapphires=balance)
    definition=DEFAULT_FLOW_REGISTRY.get('monster_wave')
    r=runtime.run_flows_once((definition,)) if mode=='selected' else runtime.run_flow(definition)
    assert r.status is FlowStatus.COMPLETED and 'StartMonsterWaveSkip' in d.intents
    runtime.facts.read_sapphires.assert_not_called()


@pytest.mark.parametrize('entry,ack',[(POPUP_MW_WEEKLY,'AcknowledgeMonsterWaveWeekly'),
                                   (POPUP_MW_RANKING,'AcknowledgeMonsterWaveRanking')])
def test_daily_normalizes_before_fresh_ocr_and_report_is_complete(monkeypatch,entry,ack):
    d=Device(entry,base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert build_session_report(r).status is ReportStatus.COMPLETE
    assert d.trace.index(('intent',ack))<d.trace.index(('sapphires',SCREEN_MONSTER_WAVE))
    assert d.trace.index(('sapphires',SCREEN_MONSTER_WAVE))<d.trace.index(('intent','SelectMonsterWaveMax'))


@pytest.mark.parametrize('problem',['unreadable','uncertain','failure','timeout','context_mismatch',
                                   'old_fact','lobby_fact','exception','cancelled'])
def test_daily_failed_or_stale_ocr_never_authorizes_input(monkeypatch,problem):
    from bot.runtime_facts import FactReadResult, FactReadStatus
    d=Device(base=SCREEN_LOBBY);runtime,_,_=runtime_for(monkeypatch,d)
    def read(**kwargs):
        if problem=='exception':raise RuntimeError('OCR failed')
        if problem in {'old_fact','lobby_fact'}:
            seq=kwargs['after_sequence'] if problem=='old_fact' else d.observe().sequence
            return fact_result('resource.sapphires',100,seq,
                               SCREEN_LOBBY if problem=='lobby_fact' else SCREEN_MONSTER_WAVE)
        return FactReadResult(FactReadStatus(problem))
    runtime.facts.read_sapphires.side_effect=read
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is (SessionStatus.CANCELLED if problem=='cancelled' else SessionStatus.FAILED)
    assert d.intents==['OpenBattleModeSelect','OpenMonsterWave']
    if problem!='cancelled':assert build_session_report(r).status is ReportStatus.TECHNICAL_FAILURE


@pytest.mark.parametrize('status',[EligibilityStatus.UNKNOWN,EligibilityStatus.FAILED])
def test_daily_eligibility_failure_precedes_entry_and_ocr(monkeypatch,status):
    from bot.eligibility import EligibilityResult
    from bot.failure_cause import FailureCause
    monkeypatch.setattr(MonsterWaveDailyEligibility,'evaluate',lambda self:
                        EligibilityResult(status,'unconfirmed',FailureCause.from_error(RuntimeError('unconfirmed'))))
    d=Device(base=SCREEN_LOBBY);runtime,_,_=runtime_for(monkeypatch,d)
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.FAILED and 'OpenMonsterWave' not in d.intents
    runtime.facts.read_sapphires.assert_not_called()


def test_daily_reobserves_skip_after_ocr_and_uses_new_state(monkeypatch):
    d=Device(ACTIVE,base=SCREEN_LOBBY)
    runtime,_,_=runtime_for(monkeypatch,d,config=MonsterWaveConfig(False,False))
    original=runtime.facts.read_sapphires.side_effect
    def read(**kwargs):
        result=original(**kwargs)
        d.names=NEEDS
        return result
    runtime.facts.read_sapphires.side_effect=read
    r=runtime.run_session(DEFAULT_FLOW_REGISTRY.select(['monster_wave']),character_count=1)
    assert r.status is SessionStatus.COMPLETED and 'SelectMonsterWaveMax' not in d.intents
    assert r.character_results[0].flow_results[0].event_count('monster_wave.tickets_missing_purchase_disabled')==1
