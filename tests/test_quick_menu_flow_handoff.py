"""Real QM flows and Rotation composed offline, with no phone or gameplay."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from bot.catalog import (
    SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT, SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE, SCREEN_PETS_MANAGE, SCREEN_CHARACTER_SELECT,
    SCREEN_QUESTS, SCREEN_MAILBOX, MENU_QUICK, MODE_DAILY_QUESTS,
    MODE_MAILBOX_CHARACTER_MAIL, STATUS_WORLD_BOSS_DAILY_ACTIVE,
    STATUS_MONSTER_WAVE_DAILY_ACTIVE,
)
from bot.component_contracts import ComponentRequirement, QUICK_MENU_ACCESS_REQUIREMENT
from bot.flow_contracts import FlowContract, FlowScope, FlowResult, FlowStatus
from bot.daily_quests_flow import DailyQuestsFlow
from bot.mailbox_flow import MailboxFlow
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE, POPUP_MW_CLEAR
from bot.quick_menu import is_clean_quick_menu_base, DEFAULT_QUICK_MENU_POLICY
from bot.rotation import StandardRotation
from bot.runtime_observer import RuntimeWaitAborted, RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.session import SessionRunner, SessionPlan, SessionStatus
from bot.state import ResolutionStatus
from bot.treasure_center_semantics import SCREEN_TREASURE
from test_navigation_handoff import HandoffDevice, mw_completed
from test_productive_runtime import _runtime, Events
from test_daily_quests_flow import rows_observation
from test_rotation import (
    ScriptedSentinel, _found, _snapshot, _frame, _selected_frame_at,
    predecessor_center, SENTINEL_COL2,
)


class MenuDevice(HandoffDevice):
    def __init__(self, base=SCREEN_MONSTER_WAVE):
        super().__init__(base=base)
        self.parent = None
        self.closed = []
        self.fail_close = None
        self.force_state = None

    def observe(self):
        s = super().observe()
        if self.base == SCREEN_QUESTS:
            s = replace(s, observations=replace(s.observations, observations=(rows_observation(),)))
        if self.base == SCREEN_CHARACTER_SELECT:
            s = _snapshot(self.sequence, base=self.base, image=_selected_frame_at(
                _frame(grid_fill=80), predecessor_center(SENTINEL_COL2)))
        if self.force_state is not None:
            s = replace(s, state=replace(s.state, status=self.force_state))
        return s

    def wait_until(self, predicate, **kwargs):
        since = None
        for _ in range(5):
            if self.cancelled:
                raise RuntimeWaitCancelled()
            s = self.observe()
            if s.sequence <= kwargs['after_sequence']:
                continue
            if kwargs.get('abort_if') and kwargs['abort_if'](s):
                raise RuntimeWaitAborted(s)
            if predicate(s):
                since = s.timestamp if since is None else since
                if s.timestamp - since >= kwargs.get('stable_for', 0):
                    return s
            else:
                since = None
        raise RuntimeWaitTimeout(after_sequence=kwargs['after_sequence'], timeout=kwargs['timeout'], last_snapshot=s)

    def execute(self, action, geometry):
        kind = type(action).__name__
        if kind == 'OpenQuickMenu':
            self.parent = self.base
        if kind in {'SelectQuickMenuQuests', 'SelectQuickMenuMailbox',
                    'CloseDailyQuests', 'CloseMailbox', 'OpenCharacterSelect',
                    'SelectCharacterCard', 'ConfirmCharacterSelection'}:
            self.intents.append(kind)
            self.executor.execute(action, geometry)
            self.overlays = self.names = ()
            if kind == 'SelectQuickMenuQuests':
                self.base, self.overlays = SCREEN_QUESTS, (MODE_DAILY_QUESTS,)
            elif kind == 'SelectQuickMenuMailbox':
                self.base, self.overlays = SCREEN_MAILBOX, (MODE_MAILBOX_CHARACTER_MAIL,)
            elif kind.startswith('Close'):
                self.closed.append((self.parent, self.sequence))
                self.base = SCREEN_WORLD_BOSS_BATTLE if kind == self.fail_close else self.parent
            elif kind == 'OpenCharacterSelect':
                self.base = SCREEN_CHARACTER_SELECT
            elif kind == 'ConfirmCharacterSelection':
                self.base = SCREEN_LOBBY
        else:
            super().execute(action, geometry)


def setup(base=SCREEN_MONSTER_WAVE):
    d = MenuDevice(base)
    r = _runtime(d, Events())
    r.actions = d
    r.cancel_token = SimpleNamespace(is_requested=lambda: d.cancelled)
    r._shared_obstruction_recovery = lambda: None
    rotation = StandardRotation(d, d, r.events, character_count=1,
        sentinel_detector=ScriptedSentinel([_found()]))
    return d, r, rotation


def compose(r, rotation, flows, *, rotate=True):
    if not flows:
        # No-input completed activity: Session still requires a literal step.
        flows = [SimpleNamespace(name='completed_activity', scope=FlowScope.PER_CHARACTER,
            contract=FlowContract(QUICK_MENU_ACCESS_REQUIREMENT,
                tuple(ComponentRequirement.exact_state(base) for base in sorted(DEFAULT_QUICK_MENU_POLICY.accessible_from))),
            run=lambda: FlowResult(FlowStatus.COMPLETED))]
    return SessionRunner(SessionPlan(1, tuple(flows), rotation, rotate=rotate),
        preconditions=r.build_preconditions(), events=r.events,
        cancel_requested=r.cancel_requested).run()


@pytest.mark.parametrize('flow_type,select,close', [
    (DailyQuestsFlow, 'SelectQuickMenuQuests', 'CloseDailyQuests'),
    (MailboxFlow, 'SelectQuickMenuMailbox', 'CloseMailbox'),
])
@pytest.mark.parametrize('origin', [SCREEN_MONSTER_WAVE, SCREEN_BATTLE_MODE_SELECT, SCREEN_TREASURE])
def test_panels_open_directly_and_freshly_restore_same_base(flow_type, select, close, origin):
    d, r, _ = setup(origin)
    result = flow_type(d, d, r.events).run()
    assert result.succeeded, result.error
    assert d.intents == ['OpenQuickMenu', select, close]
    assert result.final_snapshot.state.base_context == origin == d.base
    assert result.final_snapshot.sequence > d.closed[-1][1]
    assert result.final_snapshot.state.status is ResolutionStatus.RESOLVED
    assert is_clean_quick_menu_base(result.final_snapshot)
    assert (flow_type.name + '.base_restored', {'restored_base': origin, 'current_surface': origin}) in r.events.items


def test_mw_quests_mailbox_chain_uses_two_menus_and_zero_lobby():
    d, r, rotation = setup()
    result = compose(r, rotation, [DailyQuestsFlow(d,d,r.events), MailboxFlow(d,d,r.events)], rotate=False)
    assert result.status is SessionStatus.COMPLETED, result.error
    assert d.intents == ['OpenQuickMenu', 'SelectQuickMenuQuests', 'CloseDailyQuests',
                         'OpenQuickMenu', 'SelectQuickMenuMailbox', 'CloseMailbox']
    assert d.base == SCREEN_MONSTER_WAVE
    assert all(parent == SCREEN_MONSTER_WAVE for parent, _ in d.closed)


@pytest.mark.parametrize('origin', [SCREEN_MONSTER_WAVE, SCREEN_LOBBY, SCREEN_TREASURE,
                                    SCREEN_BATTLE_MODE_SELECT, SCREEN_PETS_MANAGE])
def test_real_rotation_starts_directly_from_credited_base(origin):
    d, r, rotation = setup(origin)
    result = compose(r, rotation, [])
    assert result.status is SessionStatus.COMPLETED, result.error
    assert d.intents == ['OpenQuickMenu', 'OpenCharacterSelect',
                         'SelectCharacterCard', 'ConfirmCharacterSelection']
    assert not hasattr(rotation, 'preferred_entry')
    assert rotation.contract.precondition == QUICK_MENU_ACCESS_REQUIREMENT
    handoffs = [fields for event, fields in r.events.items if event == 'navigation.handoff']
    assert any(e.get('destination') == 'character_select' and e.get('underlying_base') == origin for e in handoffs)


def test_full_mw_quests_mailbox_rotation_chain_has_no_lobby_normalization():
    d, r, rotation = setup()
    trace=[]
    flows=[mw_completed(d,trace), DailyQuestsFlow(d,d,r.events), MailboxFlow(d,d,r.events)]
    result = compose(r, rotation, flows)
    assert result.status is SessionStatus.COMPLETED, result.error
    assert d.intents == ['OpenQuickMenu', 'SelectQuickMenuQuests', 'CloseDailyQuests',
                         'OpenQuickMenu', 'SelectQuickMenuMailbox', 'CloseMailbox',
                         'OpenQuickMenu', 'OpenCharacterSelect', 'SelectCharacterCard',
                         'ConfirmCharacterSelection']
    finals=result.character_results[0].flow_results
    assert all(f.final_snapshot.state.base_context == SCREEN_MONSTER_WAVE for f in finals[1:])
    destinations=[e['destination'] for k,e in r.events.items
                  if k=='navigation.handoff' and e.get('route')=='quick_menu']
    assert destinations == ['daily_quests', 'mailbox', 'character_select']
    completed=[e for k,e in r.events.items if k=='flow.completed']
    assert [e['current_surface'] for e in completed] == [SCREEN_MONSTER_WAVE]*3


@pytest.mark.parametrize('failure', ['CloseDailyQuests', 'CloseMailbox'])
def test_panel_failure_stops_later_flows_and_rotation(failure):
    d,r,rotation=setup(); d.fail_close=failure
    result=compose(r,rotation,[DailyQuestsFlow(d,d,r.events),MailboxFlow(d,d,r.events)])
    assert result.status is SessionStatus.FAILED
    assert 'OpenCharacterSelect' not in d.intents
    if failure == 'CloseDailyQuests':
        assert 'SelectQuickMenuMailbox' not in d.intents


def test_wrong_restored_base_is_rejected_even_when_it_has_quick_menu():
    d,r,_=setup()
    original=d.execute
    def close_wrong(action, geometry):
        original(action,geometry)
        if type(action).__name__=='CloseMailbox':
            d.base=SCREEN_TREASURE
    d.execute=close_wrong
    result=MailboxFlow(d,d,r.events).run()
    assert not result.succeeded and result.final_snapshot is None


@pytest.mark.parametrize('origin,forced,modal', [
    (SCREEN_WORLD_BOSS_BATTLE,None,False), ('screen.black_market',None,False),
    (SCREEN_MONSTER_WAVE,ResolutionStatus.UNKNOWN,False),
    (SCREEN_MONSTER_WAVE,ResolutionStatus.AMBIGUOUS,False),
    (SCREEN_MONSTER_WAVE,None,True),
])
def test_uncredited_active_unknown_or_modal_context_never_authorizes_rotation(origin,forced,modal):
    d,r,rotation=setup(origin); d.force_state=forced
    if modal: d.overlays=(POPUP_MW_CLEAR,)
    assert compose(r,rotation,[]).status is SessionStatus.FAILED
    assert d.intents == []
    assert not rotation.advance().succeeded
    assert d.intents == []


def test_battle_mode_has_capability_but_back_wins_for_lobby():
    d,r,_=setup(SCREEN_BATTLE_MODE_SELECT)
    assert DEFAULT_QUICK_MENU_POLICY.allows(SCREEN_BATTLE_MODE_SELECT)
    assert r.build_preconditions().ensure(QUICK_MENU_ACCESS_REQUIREMENT).succeeded
    assert d.intents == []
    result=r.build_preconditions().ensure(ComponentRequirement.exact_state(SCREEN_LOBBY))
    assert result.succeeded and result.route == 'back_lobby'
    assert d.intents == ['ExitBattleModeSelect']


def test_battle_mode_to_pets_uses_quick_menu_without_lobby():
    d,r,_=setup(SCREEN_BATTLE_MODE_SELECT)
    result=r.build_preconditions().ensure(ComponentRequirement.exact_state(SCREEN_PETS_MANAGE))
    assert result.succeeded and result.route == 'quick_menu_pets'
    assert d.intents == ['OpenQuickMenu','SelectQuickMenuPets']


def test_custom_routine_preserves_repeated_panel_order():
    d,r,rotation=setup()
    result=compose(r,rotation,[MailboxFlow(d,d,r.events),DailyQuestsFlow(d,d,r.events),
                              MailboxFlow(d,d,r.events)],rotate=False)
    assert result.status is SessionStatus.COMPLETED
    assert result.flow_names == ('mailbox','daily_quests','mailbox')
    assert [i for i in d.intents if i.startswith('SelectQuickMenu')] == [
        'SelectQuickMenuMailbox','SelectQuickMenuQuests','SelectQuickMenuMailbox']


@pytest.mark.parametrize('status',[ResolutionStatus.UNKNOWN,ResolutionStatus.AMBIGUOUS])
def test_unknown_battle_mode_never_authorizes_back_or_quick_menu(status):
    d,r,_=setup(SCREEN_BATTLE_MODE_SELECT); d.force_state=status
    for requirement in (QUICK_MENU_ACCESS_REQUIREMENT,ComponentRequirement.exact_state(SCREEN_LOBBY)):
        assert not r.build_preconditions().ensure(requirement).succeeded
    assert d.intents == []


def test_registry_panel_bindings_preserve_capability_and_origin():
    from bot.flow_registry import DEFAULT_FLOW_REGISTRY
    d,r,rotation=setup(SCREEN_BATTLE_MODE_SELECT)
    flows=r.build_flows(DEFAULT_FLOW_REGISTRY.select(('daily_quests','mailbox')))
    assert all(f.contract.precondition == QUICK_MENU_ACCESS_REQUIREMENT for f in flows)
    assert compose(r,rotation,flows,rotate=False).status is SessionStatus.COMPLETED
    assert d.base == SCREEN_BATTLE_MODE_SELECT
    assert d.intents == ['OpenQuickMenu','SelectQuickMenuQuests','CloseDailyQuests',
                         'OpenQuickMenu','SelectQuickMenuMailbox','CloseMailbox']


@pytest.mark.parametrize('flow_type',[DailyQuestsFlow,MailboxFlow])
def test_cancel_during_menu_open_stops_before_destination_or_rotation(flow_type):
    d,r,_=setup();d.cancel_after='OpenQuickMenu'
    result=flow_type(d,d,r.events,cancel_requested=r.cancel_requested).run()
    assert result.status is FlowStatus.CANCELLED
    assert d.intents == ['OpenQuickMenu']
