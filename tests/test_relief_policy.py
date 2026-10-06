"""Routine ownership, conservative migration and permissions reaching real owners."""
from dataclasses import replace
from itertools import product
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.craft_semantics import CraftFamily
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_semantics import EquipmentType
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.relief_policy import ReliefPolicy, ReliefCoordinator, SocketReliefPolicy, ReliefCapability
from bot.routines import RoutineEditor, RoutineSpec, RoutineStep, RoutineStore
from bot.socket_inventory_relief import SocketStrategyOutcome, SocketReliefOutcome
from test_socket_inventory_relief import build, snapshot, plan, SCREEN_SOCKET, SCREEN_WORLD_BOSS


@pytest.mark.parametrize('enhance,sell', tuple(product((False, True), repeat=2)))
def test_socket_permissions_control_actual_suboperations(monkeypatch, enhance, sell):
    current = snapshot(1, base=SCREEN_SOCKET)
    returned = snapshot(2, base=SCREEN_WORLD_BOSS)
    operation, _, _, _, _, _, _ = build(current, [returned])
    enhancement = Mock(return_value=(SocketStrategyOutcome.NO_EFFECT, current, 0))
    selling = Mock(return_value=(SocketStrategyOutcome.NO_EFFECT, current))
    monkeypatch.setattr(operation, '_enhance', enhancement)
    monkeypatch.setattr(operation, '_sell', selling)
    coordinator = ReliefCoordinator(replace(ReliefPolicy(), socket=SocketReliefPolicy(enhance, sell)))
    result = coordinator.socket_operation(operation).run(plan())
    assert result.outcome is SocketReliefOutcome.NO_RELIEF_AVAILABLE
    assert enhancement.call_count == int(enhance)
    assert selling.call_count == int(sell)
    assert result.final_snapshot is returned


def test_socket_verified_effect_keeps_existing_fallback_order(monkeypatch):
    current = snapshot(1, base=SCREEN_SOCKET)
    operation, *_ = build(current, [snapshot(2, base=SCREEN_WORLD_BOSS)])
    monkeypatch.setattr(operation, '_enhance', Mock(return_value=(SocketStrategyOutcome.EFFECT, current, 0)))
    selling = Mock()
    monkeypatch.setattr(operation, '_sell', selling)
    assert ReliefCoordinator().socket_operation(operation).run(plan()).succeeded
    selling.assert_not_called()


@pytest.mark.parametrize('enabled', tuple(product((False, True), repeat=3)))
def test_all_craft_combinations_are_routine_permissions(enabled):
    families = frozenset(f for f, on in zip(CraftFamily, enabled) if on)
    policy = replace(ReliefPolicy(), craft_categories=families)
    assert ReliefPolicy.from_dict(policy.to_dict()) == policy
    operation = Mock()
    ReliefCoordinator(policy).handle(ReliefCapability.CRAFTING_MATERIAL, operation, max_batches=32)
    operation.assert_called_once_with(max_batches=32, families=families)


def test_treasure_disabled_stops_before_navigation_and_platinum_is_not_executable():
    operation = Mock()
    ReliefCoordinator().handle(ReliefCapability.TREASURE, operation)
    operation.assert_called_once_with()
    operation.reset_mock()
    with pytest.raises(ValueError, match='disabled'):
        ReliefCoordinator(replace(ReliefPolicy(), treasure_gold_keys=False)).handle(ReliefCapability.TREASURE, operation)
    operation.assert_not_called()
    raw = ReliefPolicy().to_dict()
    raw['treasure']['open_platinum_keys'] = True
    with pytest.raises(ValueError, match='unimplemented'):
        ReliefPolicy.from_dict(raw)


@pytest.mark.parametrize('section,key,value', [
    ('socket', 'enhance_all', 'true'),
    ('socket', 'sell_incompatible', 1),
    ('equipment_sell', 'ethereal_types', ['unknown']),
    ('equipment_sell', 'ethereal_enhance', 'false'),
    ('crafting_material', 'categories', ['unknown']),
    ('treasure', 'gold_keys', 1),
])
def test_typed_corrupt_permissions_never_enable_an_operation(section, key, value):
    raw = ReliefPolicy().to_dict()
    raw[section][key] = value
    with pytest.raises((ValueError, TypeError)):
        ReliefPolicy.from_dict(raw)


def test_legacy_conflict_intersects_sale_permissions_and_keeps_originals(tmp_path):
    path = tmp_path / 'routines.json'
    policies = [{'ethereal_types': ['boots', 'ring'], 'ethereal_enhance': True},
                {'ethereal_types': ['boots', 'weapon'], 'ethereal_enhance': False}]
    original = json.dumps({'version': 1, 'selected_id': 'r', 'routines': [
        {'id': 'r', 'name': 'Legacy', 'steps': [
            {'flow_id': 'monster_wave', 'config': {'equipment_sell': p}} for p in policies]}]})
    path.write_text(original)
    store = RoutineStore(path, DEFAULT_FLOW_REGISTRY)
    routines, selected = store.load()
    policy = ReliefPolicy.from_dict(routines[0].relief_policy)
    assert policy.equipment_sell == EquipmentSellPolicy(frozenset({EquipmentType.BOOTS}), False)
    assert routines[0].legacy_relief_configs == {'0': policies[0], '1': policies[1]}
    assert all(s.config == {} for s in routines[0].steps)
    assert any('conflicting' in w for w in store.warnings)
    assert path.read_text() == original  # load is read-only
    store.save(routines, selected)
    assert next(tmp_path.glob('*.bak')).read_text() == original
    assert store.load()[0] == routines


@pytest.mark.parametrize('bad', [None, {}, {'unknown': True}, {'treasure': {'gold_keys': 'yes'}}])
def test_corrupt_v2_policy_is_retained_and_denies_productive_permissions(tmp_path, bad):
    path = tmp_path / 'routines.json'
    path.write_text(json.dumps({'version': 2, 'routines': [
        {'id': 'r', 'name': 'Bad', 'steps': [{'flow_id': 'mailbox'}], 'relief_policy': bad}]}))
    store = RoutineStore(path, DEFAULT_FLOW_REGISTRY)
    routine = store.load()[0][0]
    assert ReliefPolicy.from_dict(routine.relief_policy) == ReliefPolicy.safe()
    assert routine.legacy_relief_configs['invalid_relief_policy'] == bad
    assert store.warnings


def test_editor_scope_duplicate_and_reopen_do_not_invert_ethereal_semantics(tmp_path):
    store = RoutineStore(tmp_path / 'routines.json', DEFAULT_FLOW_REGISTRY)
    editor = RoutineEditor(store)
    editor.create('Shared')
    for _ in range(2):
        editor.add('monster_wave')
    policy = replace(ReliefPolicy(), equipment_sell=EquipmentSellPolicy(frozenset({EquipmentType.RING}), True))
    editor.configure_reliefs(policy.to_dict())
    editor.configure(0, {'monster_wave': {'purchase_skip_tickets': True}})
    assert ReliefPolicy.from_dict(editor.draft.relief_policy) == policy
    editor.save()
    editor.create('Copy', duplicate=True)
    editor.save()
    reopened = RoutineEditor(store)
    assert reopened.draft.relief_policy == policy.to_dict()
    reopened.configure_reliefs(ReliefPolicy.safe().to_dict())
    assert editor.draft.relief_policy == policy.to_dict()
    with pytest.raises(ValueError, match='routine'):
        reopened.configure(0, {'equipment_sell': {'ethereal_enhance': True}})


def test_legacy_implicit_consumer_default_participates_in_conservative_reconciliation(tmp_path):
    path = tmp_path / 'routines.json'
    path.write_text(json.dumps({'version': 1, 'routines': [{'id': 'r', 'name': 'Implicit', 'steps': [
        {'flow_id': 'world_boss', 'config': {'equipment_sell': {'ethereal_types': ['ring'], 'ethereal_enhance': True}}},
        {'flow_id': 'monster_wave', 'config': {}}]}]}))
    store = RoutineStore(path, DEFAULT_FLOW_REGISTRY)
    routine = store.load()[0][0]
    assert ReliefPolicy.from_dict(routine.relief_policy).equipment_sell == EquipmentSellPolicy(frozenset(), False)
    assert routine.legacy_relief_configs['0']['ethereal_types'] == ['ring']
    assert any('conflicting' in warning for warning in store.warnings)


def test_productive_builds_share_coordinator_instead_of_step_sell_config(monkeypatch):
    from test_monster_wave_board_acquisition_scope import _timed_board_runtime
    from bot.flow_registry import _build_productive_monster_wave
    from bot.verified_transition import VerifiedTransition
    _, harness, observer, _, deps = _timed_board_runtime(monkeypatch)
    coordinator = ReliefCoordinator(ReliefPolicy.safe())
    deps.reliefs = coordinator
    deps.config = SimpleNamespace(equipment_sell=EquipmentSellPolicy())
    flow = _build_productive_monster_wave(deps, VerifiedTransition(observer, deps.actions, deps.events), lambda: harness.flow().inner)
    assert flow.route.reliefs is flow.route.keys_runtime.reliefs is flow.equipment_relief.reliefs is coordinator
    assert flow.equipment_sell_plan.request is coordinator.policy.equipment_sell
    assert flow.route.equipment_sell_plan.request is coordinator.policy.equipment_sell
    assert flow.socket_relief.coordinator is coordinator


def test_repeated_session_occurrences_share_policy_and_restore_runtime(monkeypatch):
    from test_routines import make_runtime
    from bot.productive_runtime import ProductiveRuntime
    runtime, _, _ = make_runtime(monkeypatch)
    before = runtime.reliefs
    bindings = []
    build_flow = ProductiveRuntime.build_flow
    def remember(self, definition):
        bindings.append(self.reliefs)
        return build_flow(self, definition)
    monkeypatch.setattr(ProductiveRuntime, 'build_flow', remember)
    routine = RoutineSpec('r', 'Shared', (RoutineStep('monster_wave'), RoutineStep('monster_wave',
        config={'monster_wave': {'purchase_skip_tickets': True}})), relief_policy=ReliefPolicy.safe().to_dict())
    runtime.run_routine(routine, character_count=1)
    assert len(bindings) == 2 and bindings[0] is bindings[1]
    assert bindings[0].policy == ReliefPolicy.safe()
    assert runtime.reliefs is before


@pytest.mark.parametrize('enabled', tuple(product((False, True), repeat=3)))
def test_craft_owner_skips_disabled_families(enabled):
    from bot.craft_runtime import CraftRuntime, CraftRouteOutcome, CraftOutcome, HeroMaterialDrainResult
    owner = CraftRuntime.__new__(CraftRuntime)
    fact = SimpleNamespace(material_for=lambda f: 100, hero_cost_for=lambda f: 49)
    owner.observe_context = Mock(return_value=SimpleNamespace(outcome=CraftRouteOutcome.ENTERED, craft_fact=fact))
    owner.drain_hero_material = Mock(return_value=HeroMaterialDrainResult(CraftOutcome.SUCCESS, (), fact))
    families = frozenset(f for f, on in zip(CraftFamily, enabled) if on)
    coordinator = ReliefCoordinator(replace(ReliefPolicy(), craft_categories=families))
    result = coordinator.handle(ReliefCapability.CRAFTING_MATERIAL, owner.drain_hero_materials, max_batches=32)
    assert result.outcome is CraftOutcome.SUCCESS
    assert [c.kwargs['family'] for c in owner.drain_hero_material.call_args_list] == [f for f in CraftFamily if f in families]


def test_equipment_coordinator_overrides_caller_permission_without_changing_navigation():
    from bot.equipment_relief import EquipmentReliefRequest, EquipmentReliefSellPlan
    from bot.equipment_combine_relief import EquipmentCombineReturnPlan
    from bot.semantic_actions import ExitCombine
    hooks = [Mock() for _ in range(7)]
    sell = EquipmentReliefSellPlan(EquipmentSellPolicy(), hooks[5], hooks[6])
    request = EquipmentReliefRequest('intent', *hooks[:4], EquipmentCombineReturnPlan(ExitCombine(), 'screen.monster_wave'), sell)
    execute = Mock()
    coordinator = ReliefCoordinator(ReliefPolicy.safe())
    coordinator.handle(ReliefCapability.EQUIPMENT, execute, request)
    actual = execute.call_args.args[0]
    assert actual.sell_plan.request == coordinator.policy.equipment_sell
    assert actual.sell_plan.enter_inventory is hooks[5]
    assert actual.operation_request == request.operation_request
