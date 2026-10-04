"""Offline inter-flow routing through the production guards and input executor."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.battle_mode_zone import BattleModeZone
from bot.catalog import SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT, SCREEN_PETS_MANAGE
from bot.component_contracts import ComponentRequirement as Requirement, ComponentContract, QUICK_MENU_ACCESS_REQUIREMENT
from bot.quick_menu import DEFAULT_QUICK_MENU_POLICY
from bot.flow_contracts import FlowContract, FlowResult, FlowStatus, FlowScope, FlowEvent
from bot.monster_wave_flow import MonsterWaveFlow
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE, POPUP_MW_CLEAR
from bot.prepared_activity import PreparedActivity
from bot.productive_runtime import ProductiveRuntime
from bot.rotation import RotationResult, RotationOutcome
from bot.session import SessionPlan, SessionRunner, SessionStatus
from bot.state import ResolutionStatus
from test_monster_wave import Device, ACTIVE
from test_productive_runtime import _runtime, Events


class HandoffDevice(Device):
    def execute(self, action, geometry):
        kind = type(action).__name__
        if kind in {'SelectQuickMenuPets', 'OpenPets'}:
            self.intents.append(kind)
            self.executor.execute(action, geometry)
            self.base = SCREEN_PETS_MANAGE
            self.names = self.overlays = ()
        else:
            super().execute(action, geometry)


def harness():
    device = HandoffDevice(base=SCREEN_MONSTER_WAVE)
    device.names = ACTIVE
    runtime = _runtime(device, Events())
    runtime.actions = device
    runtime.cancel_token = SimpleNamespace(is_requested=lambda: device.cancelled)
    runtime._shared_obstruction_recovery = lambda: None
    trace = []
    return device, runtime, trace


def activity(name, required, final, device, trace, *, no_work=None, terminal=None):
    def run():
        assert device.base == required
        trace.append(name)
        if terminal:
            return FlowResult(terminal)
        device.base = final
        device.overlays = ()
        return FlowResult(FlowStatus.COMPLETED)
    if required == SCREEN_BATTLE_MODE_SELECT:
        return PreparedActivity(name, BattleModeZone(device, Mock()), run, routing_no_work=no_work,
            exit_postconditions=(Requirement.exact_state(final),))
    return SimpleNamespace(name=name, scope=FlowScope.PER_CHARACTER, run=run,
        contract=FlowContract(Requirement.exact_state(required), (Requirement.exact_state(final),)),
        routing_no_work=no_work)


def run(runtime, flows, trace, *, rotate=False):
    class Rotation:
        character_count = 1
        contract = ComponentContract(QUICK_MENU_ACCESS_REQUIREMENT, (Requirement.exact_state(SCREEN_LOBBY),))
        def advance(self):
            assert DEFAULT_QUICK_MENU_POLICY.allows(runtime.observer.base)
            runtime.observer.base = SCREEN_LOBBY
            runtime.observer.names = runtime.observer.overlays = ()
            trace.append('rotation')
            return RotationResult(RotationOutcome.SUCCESS)
    return SessionRunner(SessionPlan(1, tuple(flows), Rotation(), rotate=rotate),
        preconditions=runtime.build_preconditions(), events=runtime.events,
        cancel_requested=runtime.cancel_requested).run()


def mw_completed(device, trace, terminal=None):
    # Prior gameplay is represented by its declared verified MW final surface.
    return activity('monster_wave', SCREEN_MONSTER_WAVE, SCREEN_MONSTER_WAVE, device, trace, terminal=terminal)


def test_mw_to_tot_only_backs_to_shared_hub():
    d, r, trace = harness()
    tot = activity('tower_of_tribulation', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace)
    result = run(r, (mw_completed(d, trace), tot), trace)
    assert result.status is SessionStatus.COMPLETED
    assert d.intents == ['ExitMonsterWave']
    assert trace == ['monster_wave', 'tower_of_tribulation']


def test_wb_to_mw_reuses_verified_hub():
    d, r, trace = harness()
    d.base = SCREEN_BATTLE_MODE_SELECT
    wb = activity('world_boss', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace)
    mw = activity('monster_wave', SCREEN_BATTLE_MODE_SELECT, SCREEN_MONSTER_WAVE, d, trace)
    assert run(r, (wb, mw), trace).status is SessionStatus.COMPLETED
    assert trace == ['world_boss', 'monster_wave']
    assert d.intents == []


def test_mw_to_pets_uses_direct_quick_menu_without_lobby():
    d, r, trace = harness()
    pets = activity('summon_pet_daily', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    assert run(r, (mw_completed(d, trace), pets), trace).status is SessionStatus.COMPLETED
    assert d.intents == ['OpenQuickMenu', 'SelectQuickMenuPets']
    assert trace == ['monster_wave', 'summon_pet_daily']
    # Real geometry mapping, measured from the existing shifted-menu evidence.
    assert d.executor.rotation_targets.select_pets_shifted == (.395, .350)


@pytest.mark.parametrize('destination', ['black_market', 'send_stamina'])
def test_mw_to_lobby_only_flow_uses_minimum_known_route(destination):
    d, r, trace = harness()
    flow = activity(destination, SCREEN_LOBBY, SCREEN_LOBBY, d, trace)
    assert run(r, (mw_completed(d, trace), flow), trace).status is SessionStatus.COMPLETED
    assert d.intents == ['OpenQuickMenu', 'SelectQuickMenuLobby']


def test_mw_end_of_routine_preserves_capable_base_for_rotation():
    d, r, trace = harness()
    assert run(r, (mw_completed(d, trace),), trace, rotate=True).status is SessionStatus.COMPLETED
    assert d.intents == []
    assert trace == ['monster_wave', 'rotation']


def test_mailbox_to_rotation_has_no_redundant_navigation():
    d, r, trace = harness()
    d.base = SCREEN_LOBBY
    mailbox = activity('mailbox', SCREEN_LOBBY, SCREEN_LOBBY, d, trace)
    assert run(r, (mailbox,), trace, rotate=True).status is SessionStatus.COMPLETED
    assert d.intents == []
    assert trace == ['mailbox', 'rotation']


@pytest.mark.parametrize('known_no_work', [True, False])
def test_pure_no_work_proof_skips_only_routing_unknown_preserves_entry(known_no_work):
    d, r, trace = harness()
    def proof():
        assert d.intents == []
        assert trace == ['monster_wave']
        return FlowResult(FlowStatus.COMPLETED, (FlowEvent('tot.no_work'),)) if known_no_work else None
    tot = activity('tower_of_tribulation', SCREEN_BATTLE_MODE_SELECT, SCREEN_MONSTER_WAVE, d, trace, no_work=proof)
    pets = activity('summon_pet_daily', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    result = run(r, (mw_completed(d, trace), tot, pets), trace)
    assert result.status is SessionStatus.COMPLETED
    assert trace == (['monster_wave', 'summon_pet_daily'] if known_no_work else
                     ['monster_wave', 'tower_of_tribulation', 'summon_pet_daily'])
    assert d.intents == ([] if known_no_work else ['ExitMonsterWave']) + ['OpenQuickMenu', 'SelectQuickMenuPets']
    assert len(result.character_results[0].flow_results) == 3
    handoffs = [fields for event, fields in r.events.items if event == 'navigation.handoff']
    if known_no_work:
        assert handoffs[-1]['next_requested_flow'] == 'tower_of_tribulation'
        assert handoffs[-1]['next_useful_flow'] == 'summon_pet_daily'


def test_literal_custom_order_and_repeated_flows_are_never_reordered():
    d, r, trace = harness()
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    daily = activity('black_market', SCREEN_LOBBY, SCREEN_LOBBY, d, trace)
    mailbox = activity('send_stamina', SCREEN_LOBBY, SCREEN_LOBBY, d, trace)
    flows = (mw_completed(d, trace), pets, daily, mailbox, daily)
    result = run(r, flows, trace)
    assert result.status is SessionStatus.COMPLETED
    assert trace == ['monster_wave', 'pets', 'black_market', 'send_stamina', 'black_market']
    assert result.flow_names == tuple(f.name for f in flows)


@pytest.mark.parametrize('terminal', [FlowStatus.FAILED, FlowStatus.CANCELLED])
def test_failure_or_cancel_cuts_before_next_handoff(terminal):
    d, r, trace = harness()
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    result = run(r, (mw_completed(d, trace, terminal), pets), trace, rotate=True)
    assert result.status.value == terminal.value
    assert d.intents == [] and trace == ['monster_wave']


@pytest.mark.parametrize('status,modal', [(ResolutionStatus.UNKNOWN, False),
    (ResolutionStatus.AMBIGUOUS, False), (ResolutionStatus.RESOLVED, True)])
def test_unknown_ambiguous_or_unresolved_modal_never_authorizes_handoff(status, modal):
    d, r, trace = harness()
    observe = d.observe
    def blocked():
        s = observe()
        return replace(s, state=replace(s.state, status=status, overlays=(POPUP_MW_CLEAR,) if modal else ()))
    d.observe = blocked
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    assert run(r, (pets,), trace).status is SessionStatus.FAILED
    assert d.intents == [] and trace == []


def test_modal_owner_finishes_before_navigation_reclassifies_and_routes():
    d, r, trace = harness()
    # CLEAR belongs to MW: resolve it during gameplay, before result finalization.
    def completion():
        from bot.monster_wave_actions import AcknowledgeMonsterWaveClear
        d.overlays = (POPUP_MW_CLEAR,)
        before = d.observe()
        d.execute(AcknowledgeMonsterWaveClear(), before.geometry)
        trace.append('monster_wave')
        return FlowResult(FlowStatus.COMPLETED)
    mw = mw_completed(d, trace)
    mw.run = completion
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    assert run(r, (mw, pets), trace).status is SessionStatus.COMPLETED
    assert d.intents == ['AcknowledgeMonsterWaveClear', 'OpenQuickMenu', 'SelectQuickMenuPets']


def test_entry_readiness_is_not_used_as_pure_lookahead_from_mw():
    d, r, trace = harness()
    tot = activity('tower_of_tribulation', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace)
    readiness = Mock(side_effect=AssertionError('contextual readiness is not a pure proof'))
    tot = replace(tot, entry_readiness=readiness)
    assert run(r, (mw_completed(d, trace), tot), trace).status is SessionStatus.COMPLETED
    readiness.assert_not_called()
    assert d.intents == ['ExitMonsterWave']


def test_real_mw_flow_result_is_finalized_before_navigation_inputs():
    d, r, trace = harness()
    d.base = SCREEN_LOBBY
    mw = MonsterWaveFlow(d, d, r.events, facts=d.facts(), sleeper=lambda _: None)
    mw.entry_readiness = lambda: None
    result = mw.run()
    assert result.succeeded and d.base == SCREEN_MONSTER_WAVE
    assert result.final_snapshot.state.base_context == SCREEN_MONSTER_WAVE
    assert 'ExitMonsterWave' not in d.intents and 'SelectQuickMenuLobby' not in d.intents
    handoff_start = len(d.intents)
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    assert run(r, (pets,), trace).status is SessionStatus.COMPLETED
    assert d.intents[handoff_start:] == ['OpenQuickMenu', 'SelectQuickMenuPets']


def test_known_mw_back_lineage_to_lobby_reenters_hub_only_when_requested():
    d, r, trace = harness()
    execute = d.execute
    def back_to_lobby(action, geometry):
        execute(action, geometry)
        if type(action).__name__ == 'ExitMonsterWave':
            d.base = SCREEN_LOBBY
    d.execute = back_to_lobby
    tot = activity('tower_of_tribulation', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace)
    assert run(r, (mw_completed(d, trace), tot), trace).status is SessionStatus.COMPLETED
    assert d.intents == ['ExitMonsterWave', 'OpenBattleModeSelect']


def test_wb_readiness_uses_fresh_hub_resources_not_a_previous_mw_result():
    from bot.world_boss_flow import WorldBossFlow
    from test_world_boss_flow import fact_result
    d, r, trace = harness()
    d.base = SCREEN_BATTLE_MODE_SELECT
    reads = []
    def read_sapphires(**kwargs):
        reads.append(kwargs['context'])
        return fact_result('resource.sapphires', 0, d.sequence, SCREEN_BATTLE_MODE_SELECT)
    wb = WorldBossFlow(d, d, Mock(read_sapphires=read_sapphires), Mock(), r.events,
                       socket_relief=Mock(), equipment_combine_relief=Mock())
    wb._sapphires_hint = 500  # Diagnostic from an earlier visit must not authorize work.
    result = run(r, (wb.prepared(wb.zone),), trace)
    assert result.status is SessionStatus.COMPLETED
    assert result.character_results[0].flow_results[0].event_count('world_boss.insufficient_sapphires') == 1
    assert reads == [SCREEN_BATTLE_MODE_SELECT] and d.intents == []


def test_pure_routing_proof_cannot_override_an_eligibility_owner():
    from bot.eligibility import EligibilityResult, EligibilityStatus
    d, r, trace = harness()
    tot = activity('tower_of_tribulation', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace,
                   no_work=Mock(side_effect=AssertionError('must not bypass Eligibility')))
    rotation = SimpleNamespace(character_count=1, advance=Mock(),
        contract=ComponentContract(Requirement.exact_state(SCREEN_LOBBY), (Requirement.exact_state(SCREEN_LOBBY),)))
    eligibility = Mock(evaluate=lambda: EligibilityResult(EligibilityStatus.NOT_ELIGIBLE, 'verified at hub'))
    plan = SessionPlan(1, (tot,), rotation, rotate=False, eligibility=(eligibility,))
    result = SessionRunner(plan, preconditions=r.build_preconditions(), events=r.events).run()
    assert result.status is SessionStatus.COMPLETED and d.intents == ['ExitMonsterWave']
    tot.routing_no_work.assert_not_called()


def test_manual_routine_retains_wb_readiness_after_mw_without_daily_policy():
    from bot.world_boss_flow import WorldBossFlow
    from bot.flow_registry import DEFAULT_FLOW_REGISTRY
    from test_world_boss_flow import fact_result
    d, r, trace = harness()
    facts = Mock(read_sapphires=lambda **kwargs:
        fact_result('resource.sapphires', 0, d.sequence, kwargs['context']))
    wb = WorldBossFlow(d, d, facts, Mock(), r.events, socket_relief=Mock(), equipment_combine_relief=Mock())
    r.build_flows = lambda definitions: (mw_completed(d, trace), wb)
    r.build_rotation = lambda count: SimpleNamespace(character_count=1, advance=Mock(),
        contract=ComponentContract(Requirement.exact_state(SCREEN_LOBBY), (Requirement.exact_state(SCREEN_LOBBY),)))
    result = r.run_flows_once(DEFAULT_FLOW_REGISTRY.select(('monster_wave', 'world_boss')))
    assert result.status is FlowStatus.COMPLETED
    assert d.intents == ['ExitMonsterWave']
    assert result.flow_results[-1].event_count('world_boss.insufficient_sapphires') == 1


def test_hub_to_pets_uses_direct_quick_menu_after_proven_no_work():
    d, r, trace = harness()
    d.base = SCREEN_BATTLE_MODE_SELECT
    wb = activity('world_boss', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace)
    mw = activity('monster_wave', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace,
        no_work=lambda: FlowResult(FlowStatus.COMPLETED, (FlowEvent('monster_wave.no_work'),)))
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    assert run(r, (wb, mw, pets), trace).status is SessionStatus.COMPLETED
    assert d.intents == ['OpenQuickMenu', 'SelectQuickMenuPets']
    assert trace == ['world_boss', 'pets']


def test_unknown_tot_is_not_skipped_and_its_hub_result_routes_safely_to_pets():
    d, r, trace = harness()
    tot = activity('tower_of_tribulation', SCREEN_BATTLE_MODE_SELECT, SCREEN_BATTLE_MODE_SELECT, d, trace,
                   no_work=lambda: None)
    pets = activity('pets', SCREEN_PETS_MANAGE, SCREEN_PETS_MANAGE, d, trace)
    assert run(r, (mw_completed(d, trace), tot, pets), trace).status is SessionStatus.COMPLETED
    assert d.intents == ['ExitMonsterWave', 'OpenQuickMenu', 'SelectQuickMenuPets']
    assert trace == ['monster_wave', 'tower_of_tribulation', 'pets']
