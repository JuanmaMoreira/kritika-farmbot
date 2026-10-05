from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_world_boss_flow import (
    build_flow, snapshot, fact_result, EquipmentCombineRelief,
    EquipmentCombineReliefResult, EquipmentCombineReliefOutcome,
    SCREEN_LOBBY, SCREEN_WORLD_BOSS, SCREEN_BATTLE_MODE_SELECT,
    SCREEN_COMBINE, MODE_COMBINE_FUSE, OVERLAY_WORLD_BOSS_SELECT_BOSS,
    POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_METEOR_INVENTORY_FULL,
    MENU_QUICK, FlowStatus, RuntimeWaitCancelled,
    Transitions,
)


@pytest.mark.parametrize('terminal', [POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_METEOR_INVENTORY_FULL])
def test_full_after_combine_attempts_sell_once_before_another_start(terminal):
    full = lambda seq: snapshot(seq, base=SCREEN_WORLD_BOSS, overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,))
    combine = EquipmentCombineRelief((EquipmentCombineReliefResult(
        EquipmentCombineReliefOutcome.RELIEVED, final_snapshot=snapshot(9, base=SCREEN_WORLD_BOSS)),))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result('resource.sapphires', 10, 1, SCREEN_LOBBY),
        waits=[snapshot(2, base=SCREEN_LOBBY), snapshot(6, base=SCREEN_WORLD_BOSS)],
        transitions=[snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
            snapshot(4, base=SCREEN_BATTLE_MODE_SELECT, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
            snapshot(5, base=SCREEN_WORLD_BOSS), full(7),
            snapshot(8, base=SCREEN_COMBINE, overlays=(MODE_COMBINE_FUSE,)),
            full(10), snapshot(11, base=SCREEN_WORLD_BOSS),
            snapshot(14, base=SCREEN_WORLD_BOSS, overlays=(terminal,)), snapshot(15, base=SCREEN_WORLD_BOSS)],
        equipment_combine_relief=combine, equipment_sell=Mock(),
    )
    flow.activity._sell_equipment = Mock(return_value=snapshot(13, base=SCREEN_WORLD_BOSS))
    result = flow.run()
    assert result.status is FlowStatus.COMPLETED
    assert result.bag_full is (terminal == POPUP_EQUIPMENT_INVENTORY_FULL)
    flow.activity._sell_equipment.assert_called_once()
    assert len(combine.calls) == 1
    assert [name for name, *_ in driver.calls].count('world_boss.start') == 3


@pytest.mark.parametrize('outcome', ['success', 'failed', 'cancelled'])
def test_inventory_owner_result_requires_verified_wb_return(outcome):
    origin = snapshot(10, base=SCREEN_WORLD_BOSS)
    menu = snapshot(11, base=SCREEN_WORLD_BOSS, overlays=(MENU_QUICK,))
    ready = snapshot(12, base=SCREEN_WORLD_BOSS, overlays=(MENU_QUICK,))
    restored = snapshot(20, base=SCREEN_WORLD_BOSS)
    owner = Mock()
    owner.clock.return_value = 1.0
    owner.execute_relief.return_value = SimpleNamespace(
        succeeded=outcome == 'success', outcome=outcome, reason='physical_outcome',
        before=SimpleNamespace(item_count=131), after=SimpleNamespace(sequence=18,item_count=126,capacity=128))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result('resource.sapphires', 10, 1, SCREEN_LOBBY),
        waits=[ready, restored], transitions=[menu], equipment_sell=owner)
    if outcome == 'success':
        assert flow.activity._sell_equipment(origin, []) is restored
        owner._tap.assert_called_once()
        assert flow.activity._inventory_restored_wb
    else:
        expected = RuntimeWaitCancelled if outcome == 'cancelled' else ValueError
        with pytest.raises(expected):
            flow.activity._sell_equipment(origin, [])
        owner._tap.assert_not_called()
    assert owner._after_sequence == ready.sequence
    guard = driver.calls[0][3]['precondition']
    assert guard(origin)
    assert not guard(snapshot(21, base=SCREEN_WORLD_BOSS, overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,)))


@pytest.mark.parametrize('inventory_restored', [True, False])
def test_lobby_after_wb_exit_is_accepted_only_after_inventory_return(inventory_restored):
    from bot.world_boss_activity import WorldBossFlowResult
    flow, _, _, _, _, _ = build_flow(
        sapphire_read=fact_result('resource.sapphires', 10, 1, SCREEN_LOBBY),
        waits=[snapshot(10, base=SCREEN_WORLD_BOSS)])
    driver = Transitions([snapshot(11, base=SCREEN_LOBBY), snapshot(12, base=SCREEN_BATTLE_MODE_SELECT)])
    flow.activity.verified_transition = driver
    def gameplay(*args):
        flow.activity._inventory_restored_wb = inventory_restored
        return WorldBossFlowResult(FlowStatus.COMPLETED)
    flow.activity._run = gameplay
    result = flow.activity.run(sapphires=10)
    assert result.status is (FlowStatus.COMPLETED if inventory_restored else FlowStatus.FAILED)
    assert [name for name, *_ in driver.calls] == ([
        'world_boss.return_to_battle_mode', 'world_boss.inventory_return.restore_hub']
        if inventory_restored else ['world_boss.return_to_battle_mode'])
