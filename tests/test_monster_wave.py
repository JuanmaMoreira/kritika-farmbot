"""SKIP-only policy through real verified transitions and physical action boundary."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.action_executor import ActionExecutor
from bot.catalog import (SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, MENU_QUICK,
    POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL, STATUS_WORLD_BOSS_DAILY_ACTIVE,
    SCREEN_WORLD_BOSS, SCREEN_WORLD_BOSS_BATTLE, OVERLAY_WORLD_BOSS_SELECT_BOSS,
    OVERLAY_WORLD_BOSS_RAID_COMPLETE)
from bot.flow_contracts import FlowStatus
from bot.monster_wave_actions import *
from bot.monster_wave_activity import MonsterWaveActivity, skip_state, SkipState, max_ready, popup
from bot.monster_wave_config import MonsterWaveConfig
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_semantics import *
from bot.observations import Observation, ObservationSource
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.state import ResolutionStatus
from test_world_boss_flow import snapshot


NEEDS=(MW_NEEDS_TICKETS, MW_CONTROLS_CLEAR)
READY=(MW_READY, MW_CONTROLS_CLEAR)
ACTIVE=(MW_TIMER, MW_SKIP_START, MW_CONTROLS_CLEAR)
MAX=(*ACTIVE, MW_MAX)


class Device:
    """Explicit semantic scenarios; never contacts ADB or a real device."""
    def __init__(self, entry=ACTIVE, *, boundary=POPUP_MW_CLEAR,
                 board_after=POPUP_MW_CLEAR, max_after=MAX, purchase_ok=True,
                 base=SCREEN_BATTLE_MODE_SELECT, daily=True, entry_after=ACTIVE):
        self.entry, self.boundary, self.board_after = entry, boundary, board_after
        self.max_after, self.purchase_ok = max_after, purchase_ok
        self.base, self.daily = base, daily
        self.entry_after = entry_after
        self.names=(); self.overlays=(); self.sequence=0; self.cancelled=False
        self.trace=[]; self.intents=[]; self.cancel_after=None
        self.adb=Mock(tap=lambda *p:self.trace.append(('tap',p)))
        self.executor=ActionExecutor(self.adb)
        self.events=Mock()

    def observe(self):
        self.sequence+=1
        self.trace.append(('observe',self.sequence))
        overlays=self.overlays
        if self.base==SCREEN_BATTLE_MODE_SELECT:
            overlays=(STATUS_WORLD_BOSS_DAILY_ACTIVE,)+((STATUS_MONSTER_WAVE_DAILY_ACTIVE,) if self.daily else ())
        obs=tuple(Observation(n,1.0,ObservationSource.LOCAL_CV) for n in self.names)
        return snapshot(self.sequence,base=self.base,overlays=overlays,semantic_observations=obs)

    def wait_until(self, predicate, **kwargs):
        since=None
        for _ in range(5):
            if self.cancelled:raise RuntimeWaitCancelled()
            s=self.observe()
            if s.sequence<=kwargs['after_sequence']:continue
            if predicate(s):
                since=s.timestamp if since is None else since
                if s.timestamp-since>=kwargs.get('stable_for',0):return s
            else:since=None
        raise RuntimeWaitTimeout(after_sequence=kwargs['after_sequence'],timeout=kwargs['timeout'],last_snapshot=s)

    def execute(self, action, geometry):
        kind=type(action).__name__;self.intents.append(kind);self.trace.append(('intent',kind))
        self.executor.execute(action,geometry)
        if kind=='OpenBattleModeSelect' or isinstance(action,ExitMonsterWave):
            self.base=SCREEN_BATTLE_MODE_SELECT;self.overlays=();self.names=()
        elif kind=='OpenQuickMenu':self.base=None;self.overlays=(MENU_QUICK,)
        elif kind=='SelectQuickMenuLobby':self.base=SCREEN_LOBBY;self.overlays=();self.names=()
        elif isinstance(action,OpenMonsterWave):
            self.base=SCREEN_MONSTER_WAVE
            if isinstance(self.entry,str):self.overlays=(self.entry,)
            else:self.names=self.entry;self.overlays=()
        elif isinstance(action,(AcknowledgeMonsterWaveWeekly,AcknowledgeMonsterWaveRanking)):
            if isinstance(self.entry_after,str):self.overlays=(self.entry_after,)
            else:self.names=self.entry_after;self.overlays=()
        elif isinstance(action,OpenMonsterWaveTickets):self.overlays=(POPUP_MW_PURCHASE,);self.names=()
        elif isinstance(action,FillMonsterWaveTickets):
            if self.purchase_ok:self.names=(MW_PURCHASE_FULL,)
        elif isinstance(action,CloseMonsterWaveTickets):self.names=READY;self.overlays=()
        elif isinstance(action,ActivateMonsterWaveSkip):self.names=ACTIVE
        elif isinstance(action,SelectMonsterWaveMax):
            self.names=self.max_after
            if MW_TOOLTIP in self.names:self.overlays=(OVERLAY_MW_TOOLTIP,)
        elif isinstance(action,StartMonsterWaveSkip):self.overlays=(self.boundary,)
        elif isinstance(action,AcceptMonsterWaveInventory):self.overlays=(self.board_after,)
        elif isinstance(action,(DeclineMonsterWaveInventory,RejectMonsterWaveSapphires,AcknowledgeMonsterWaveClear)):
            self.overlays=();self.names=ACTIVE
        elif kind=='OpenWorldBossSelector':self.base=None;self.overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)
        elif kind in {'SelectAvailableWorldBoss','ContinueAfterWorldBossRaid'}:self.base=SCREEN_WORLD_BOSS;self.overlays=()
        elif kind=='StartWorldBossBattle':self.base=SCREEN_WORLD_BOSS_BATTLE;self.overlays=()
        elif kind=='ExitWorldBoss':self.base=SCREEN_BATTLE_MODE_SELECT;self.overlays=()
        else:raise AssertionError(f'unexpected input {kind}')
        if kind==self.cancel_after:self.cancelled=True

    def activity(self, config=MonsterWaveConfig()):
        return MonsterWaveActivity(self,self,self.events,config=config,cancel_requested=lambda:self.cancelled)


def test_tickets_missing_purchase_disabled_is_business_and_returns_hub():
    d=Device(NEEDS);result=d.activity().run()
    assert result.succeeded and result.event_count('monster_wave.tickets_missing_purchase_disabled')==1
    assert d.intents==['OpenMonsterWave','ExitMonsterWave']
    assert d.base==SCREEN_BATTLE_MODE_SELECT


def test_single_verified_fill_all_then_activate_max_skip_clear_back():
    d=Device(NEEDS);r=d.activity(MonsterWaveConfig(purchase_skip_tickets=True)).run()
    assert r.succeeded
    assert d.intents==['OpenMonsterWave','OpenMonsterWaveTickets','FillMonsterWaveTickets',
        'CloseMonsterWaveTickets','ActivateMonsterWaveSkip','SelectMonsterWaveMax',
        'StartMonsterWaveSkip','AcknowledgeMonsterWaveClear','ExitMonsterWave']
    assert r.event_count('monster_wave.tickets_purchased')==r.event_count('monster_wave.completed')==1
    assert all(attempts==1 for _,attempts,_ in r.transition_attempts)


def test_ready_activates_but_direct_active_never_purchases_or_reactivates():
    d=Device(READY);activity=d.activity();assert activity.run().succeeded
    assert d.intents.count('ActivateMonsterWaveSkip')==1
    d.entry=ACTIVE;d.intents.clear()
    assert activity.run().succeeded
    assert 'ActivateMonsterWaveSkip' not in d.intents
    assert 'FillMonsterWaveTickets' not in d.intents


def test_previous_active_does_not_authorize_fresh_needs_tickets():
    d=Device();activity=d.activity();assert activity.run().succeeded
    d.entry=NEEDS;d.intents.clear();r=activity.run()
    assert r.event_count('monster_wave.tickets_missing_purchase_disabled')==1
    assert d.intents==['OpenMonsterWave','ExitMonsterWave']


def test_max_is_two_exact_taps_then_fresh_verification_then_skip():
    d=Device();r=d.activity().run();assert r.succeeded
    i=d.trace.index(('intent','SelectMonsterWaveMax'));tail=d.trace[i+1:]
    assert tail[0][0]==tail[1][0]=='tap' and tail[0]==tail[1]
    assert tail[2][0]=='observe'
    assert tail[3][0]=='observe'
    assert tail[4]==('intent','StartMonsterWaveSkip')
    assert d.intents.count('SelectMonsterWaveMax')==1


@pytest.mark.parametrize('evidence',[ACTIVE,(MW_TIMER,MW_SKIP_START,MW_MAX),(*MAX,MW_TOOLTIP),NEEDS,READY,()])
def test_failed_max_or_tooltip_or_expiry_never_starts_or_retaps(evidence):
    d=Device(max_after=evidence);r=d.activity().run()
    assert r.status is FlowStatus.FAILED
    assert d.intents==['OpenMonsterWave','SelectMonsterWaveMax']
    assert r.failure is not None


def test_insufficient_sapphires_only_no_clean_business_return():
    d=Device(boundary=POPUP_MW_INSUFFICIENT);r=d.activity().run()
    assert r.succeeded and r.event_count('monster_wave.insufficient_sapphires')==1
    assert d.intents[-2:]==['RejectMonsterWaveSapphires','ExitMonsterWave']
    assert not any('Accept' in a for a in d.intents)


@pytest.mark.parametrize('accept',[False,True])
def test_inventory_board_user_policy(accept):
    d=Device(boundary=POPUP_MW_BOARD)
    r=d.activity(MonsterWaveConfig(continue_when_nonblocking_inventory_full=accept)).run()
    assert r.succeeded
    assert ('AcceptMonsterWaveInventory' in d.intents)==accept
    assert ('DeclineMonsterWaveInventory' in d.intents)==(not accept)
    assert r.event_count('monster_wave.completed')==int(accept)
    assert r.event_count('monster_wave.inventory_warning_declined')==int(not accept)


@pytest.mark.parametrize('accept',[False,True])
def test_opt_in_resource_board_yields_the_same_open_popup_without_answer_or_exit(accept):
    d=Device(boundary=POPUP_MW_BOARD)
    r=d.activity(MonsterWaveConfig(continue_when_nonblocking_inventory_full=accept)).run(
        yield_resource_board=True)
    assert r.status is FlowStatus.RESOURCE_BOARD_PENDING
    assert r.board_sequence == d.sequence
    assert r.event_count('monster_wave.resource_board_pending') == 1
    assert d.base == SCREEN_MONSTER_WAVE and d.overlays == (POPUP_MW_BOARD,)
    assert d.intents[-1] == 'StartMonsterWaveSkip'
    assert 'AcceptMonsterWaveInventory' not in d.intents
    assert 'DeclineMonsterWaveInventory' not in d.intents
    assert 'ExitMonsterWave' not in d.intents


def test_opt_in_resource_board_stops_standalone_flow_before_zone_leave():
    d=Device(base=SCREEN_LOBBY,boundary=POPUP_MW_BOARD)
    r=MonsterWaveFlow(d,d,d.events).run(yield_resource_board=True)
    assert r.status is FlowStatus.RESOURCE_BOARD_PENDING
    assert d.base == SCREEN_MONSTER_WAVE and d.overlays == (POPUP_MW_BOARD,)
    assert d.intents[-1] == 'StartMonsterWaveSkip'


@pytest.mark.parametrize('blocker',[POPUP_EQUIPMENT_INVENTORY_FULL,POPUP_SOCKET_INVENTORY_FULL])
def test_opt_in_board_yield_does_not_claim_hard_blockers(blocker):
    d=Device(boundary=blocker)
    r=d.activity().run(yield_resource_board=True)
    assert r.status is FlowStatus.MANUAL_RESOLUTION
    assert r.board_sequence is None
    assert d.overlays == (blocker,)


def test_opt_in_board_yield_respects_cancellation_before_recognition():
    d=Device(boundary=POPUP_MW_BOARD)
    d.cancel_after='StartMonsterWaveSkip'
    r=d.activity().run(yield_resource_board=True)
    assert r.status is FlowStatus.CANCELLED
    assert r.board_sequence is None
    assert d.intents[-1]=='StartMonsterWaveSkip'


@pytest.mark.parametrize('blocker',[POPUP_EQUIPMENT_INVENTORY_FULL,POPUP_SOCKET_INVENTORY_FULL])
def test_hard_blocker_no_unacquired_relief_or_exit(blocker):
    d=Device(boundary=POPUP_MW_BOARD,board_after=blocker)
    r=d.activity(MonsterWaveConfig(continue_when_nonblocking_inventory_full=True)).run()
    assert r.status is FlowStatus.MANUAL_RESOLUTION and r.failure is None
    assert r.events[-1].fields['blocker']==blocker
    assert d.intents[-1]=='AcceptMonsterWaveInventory'
    assert d.overlays==(blocker,)


def test_purchase_failure_never_repeats_purchase_or_activates():
    d=Device(NEEDS,purchase_ok=False)
    r=d.activity(MonsterWaveConfig(purchase_skip_tickets=True)).run()
    assert r.status is FlowStatus.FAILED
    assert d.intents==['OpenMonsterWave','OpenMonsterWaveTickets','FillMonsterWaveTickets']
    assert r.failure is not None and r.event_count('monster_wave.tickets_purchased')==0


@pytest.mark.parametrize('cancel_after',[None,'OpenMonsterWave','FillMonsterWaveTickets','SelectMonsterWaveMax','StartMonsterWaveSkip','AcknowledgeMonsterWaveClear'])
def test_cancellation_has_no_cleanup_or_following_action(cancel_after):
    d=Device(NEEDS);d.cancel_after=cancel_after;d.cancelled=cancel_after is None
    r=d.activity(MonsterWaveConfig(purchase_skip_tickets=True)).run()
    assert r.status is FlowStatus.CANCELLED
    if cancel_after:assert d.intents[-1]==cancel_after
    else:assert d.intents==[]


def test_standalone_returns_lobby_and_ignores_daily():
    d=Device(base=SCREEN_LOBBY,daily=False)
    flow=MonsterWaveFlow(d,d,d.events)
    r=flow.run();assert r.succeeded and d.base==SCREEN_LOBBY
    assert d.intents[0]=='OpenBattleModeSelect'
    assert d.intents[-3:]==['ExitMonsterWave','OpenQuickMenu','SelectQuickMenuLobby']


@pytest.mark.parametrize('state',[ResolutionStatus.UNKNOWN,ResolutionStatus.AMBIGUOUS])
def test_unknown_never_authorizes_skip_or_max(state):
    s=snapshot(1,status=state,semantic_observations=tuple(
        Observation(n,1,ObservationSource.LOCAL_CV) for n in MAX))
    assert skip_state(s) is None and not max_ready(s)


@pytest.mark.parametrize('state',[ResolutionStatus.UNKNOWN,ResolutionStatus.AMBIGUOUS])
def test_unresolved_board_cannot_be_yielded(state):
    s=snapshot(3,base=None,status=state,
               overlays=(POPUP_MW_BOARD,))
    assert not popup(POPUP_MW_BOARD)(s)


def test_foreign_board_cannot_be_yielded():
    s=snapshot(3,base=SCREEN_LOBBY,overlays=(POPUP_MW_BOARD,))
    assert not popup(POPUP_MW_BOARD)(s)


def test_contradictory_skip_signals_never_authorize_input():
    d=Device();d.base=SCREEN_MONSTER_WAVE
    for names in ((*ACTIVE,MW_NEEDS_TICKETS),(*READY,MW_TIMER),(*NEEDS,MW_READY)):
        d.names=names;assert skip_state(d.observe()) is None


@pytest.mark.parametrize('entry,ack',[(POPUP_MW_RANKING,'AcknowledgeMonsterWaveRanking'),
                                   (POPUP_MW_WEEKLY,'AcknowledgeMonsterWaveWeekly')])
def test_entry_normalization_is_verified_operational_success(entry,ack):
    d=Device(entry);r=d.activity().run()
    assert r.status is FlowStatus.COMPLETED
    assert d.intents[:3]==['OpenMonsterWave',ack,'SelectMonsterWaveMax']
    assert [e.kind for e in r.events]==['monster_wave.completed']
    i=d.trace.index(('intent',ack))
    j=d.trace.index(('intent','SelectMonsterWaveMax'))
    assert sum(t[0]=='observe' for t in d.trace[i:j])>=2


@pytest.mark.parametrize('entry',[ACTIVE,READY,NEEDS])
def test_absent_entry_popups_do_not_add_acknowledgements(entry):
    d=Device(entry);assert d.activity().run().succeeded
    assert not any(a in d.intents for a in ('AcknowledgeMonsterWaveRanking','AcknowledgeMonsterWaveWeekly'))


@pytest.mark.parametrize('entry',[POPUP_MW_WEEKLY,POPUP_MW_RANKING])
def test_persistent_or_unknown_post_ack_never_repeats_or_spends(entry):
    for after in (entry,'popup.unacquired'):
        d=Device(entry,entry_after=after);r=d.activity().run()
        assert r.status is FlowStatus.FAILED
        assert len(d.intents)==2


def test_unknown_entry_overlay_does_not_authorize_acknowledgement():
    d=Device('popup.unacquired');r=d.activity().run()
    assert r.status is FlowStatus.FAILED
    assert d.intents==['OpenMonsterWave']


def test_entry_normalization_has_two_ack_budget_without_assuming_order():
    # Defensive transition model only; this does not claim acquired coexistence.
    class CyclingDevice(Device):
        def execute(self,action,geometry):
            if isinstance(action,AcknowledgeMonsterWaveWeekly):self.entry_after=POPUP_MW_RANKING
            elif isinstance(action,AcknowledgeMonsterWaveRanking):self.entry_after=POPUP_MW_WEEKLY
            super().execute(action,geometry)
    for entry in (POPUP_MW_WEEKLY,POPUP_MW_RANKING):
        d=CyclingDevice(entry);r=d.activity().run()
        assert r.status is FlowStatus.FAILED
        assert len(d.intents)==3 and 'SelectMonsterWaveMax' not in d.intents


@pytest.mark.parametrize('status',[ResolutionStatus.UNKNOWN,ResolutionStatus.AMBIGUOUS])
def test_unresolved_entry_even_with_known_popup_has_no_ack(status):
    class UnresolvedDevice(Device):
        def observe(self):
            observed=super().observe()
            return snapshot(observed.sequence,status=status,overlays=(POPUP_MW_WEEKLY,)) if self.base==SCREEN_MONSTER_WAVE else observed
    d=UnresolvedDevice(POPUP_MW_WEEKLY);r=d.activity().run()
    assert r.status is FlowStatus.FAILED and d.intents==['OpenMonsterWave']


def test_config_has_only_two_booleans_and_no_resource_bookkeeping():
    from dataclasses import fields
    from bot.config import RuntimeConfig
    assert [f.name for f in fields(MonsterWaveConfig)]==['purchase_skip_tickets','continue_when_nonblocking_inventory_full']
    cfg=RuntimeConfig.from_env({'DISPOSITIVO_ADB':'test','SCRCPY_SERVER_PATH':'test',
        'MW_PURCHASE_SKIP_TICKETS':'true','MW_CONTINUE_WHEN_NONBLOCKING_INVENTORY_FULL':'true'})
    assert cfg.monster_wave==MonsterWaveConfig(True,True)
    with pytest.raises(ValueError):MonsterWaveConfig(purchase_skip_tickets='false')
    with pytest.raises(ValueError):MonsterWaveConfig.from_env({'MW_PURCHASE_SKIP_TICKETS':'yes'})
    d=Device();a=d.activity();assert a.run().succeeded
    assert set(vars(a))=={'observer','actions','events','config','cancel_requested','verified_transition','facts'}
    assert not any('Battle' in k or k in {'Start','SelectX1','SelectX2','SelectX3'} for k in d.intents)
