"""Bounded navigation retry for no-effect page tap in session 8d724bea."""
from dataclasses import replace
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.equipment_sell_runtime import EquipmentSellRuntime
from bot.equipment_sell_semantics import EquipmentInventoryFact


@pytest.mark.parametrize('direction', [1, -1])
@pytest.mark.parametrize('effect_after', [1, 2, None])
def test_page_navigation_retries_one_no_effect_tap(direction, effect_after):
    now = [10.]; adb = Mock()
    origin = 1 if direction == 1 else 3
    target = origin + direction
    class Source:
        sequence = 0
        def get_frame(self):
            self.sequence += 1
            now[0] += .02
            return FrameSnapshot(np.zeros((120, 240, 3), np.uint8), now[0], self.sequence)
    class Reader:
        def inventory_sample(self, image, *, sequence, observed_at):
            page = target if effect_after and adb.tap.call_count >= effect_after else origin
            return EquipmentInventoryFact(132, 132, page, 22, sequence, observed_at, (sequence,))
        detail_sample = confirmation_sample = lambda *args, **kwargs:None
    runtime = EquipmentSellRuntime(Source(), Reader(), ActionExecutor(adb),
        clock=lambda:now[0], sleeper=lambda delay:now.__setitem__(0,now[0]+delay),
        sample_timeout=.2, sample_interval=.01)
    expected = EquipmentInventoryFact(132,132,origin,22,0,10.)
    if effect_after:
        assert runtime._navigate_page(target,expected).page == target
        assert adb.tap.call_count == effect_after
    else:
        with pytest.raises(RuntimeError, match='inventory_page_transition_unverified'):
            runtime._navigate_page(target,expected)
        assert adb.tap.call_count == 2


@pytest.mark.parametrize('invalid', ['unknown','unconfirmed','count','capacity','pages',
                                   'other_page','pre_input','old_sequence','stale','future',
                                   'contradictory','cancel','cancel_during_reacquisition'])
def test_retry_requires_fresh_unchanged_post_input_inventory(invalid):
    now = [10.]; adb = Mock(); reader = Mock()
    runtime = EquipmentSellRuntime(Mock(get_frame=Mock()), reader, ActionExecutor(adb),
        clock=lambda:now[0])
    origin = EquipmentInventoryFact(132,132,1,22,2,10.,(1,2))
    retry = EquipmentInventoryFact(132,132,1,22,4,10.,(3,4))
    if invalid == 'unknown': retry = None
    if invalid == 'unconfirmed': retry = replace(retry,sample_sequences=(4,))
    if invalid == 'count': retry = replace(retry,item_count=133)
    if invalid == 'capacity': retry = replace(retry,capacity=136)
    if invalid == 'pages': retry = replace(retry,total_pages=23)
    if invalid == 'other_page': retry = replace(retry,page=3)
    if invalid == 'pre_input': retry = replace(retry,observed_at=9.)
    if invalid == 'old_sequence': retry = replace(retry,sample_sequences=(2,4))
    if invalid == 'stale': retry = replace(retry,observed_at=7.)
    if invalid == 'future': retry = replace(retry,observed_at=11.)
    if invalid == 'contradictory': retry = replace(retry,contradictory=True)
    calls = [0]
    def inventory(cursor, predicate=lambda value:True):
        calls[0] += 1
        if calls[0] == 1:
            runtime._latest = FrameSnapshot(np.zeros((120,240,3),np.uint8),10.,2)
            return origin
        if calls[0] == 2:
            if invalid == 'cancel':runtime.cancel_requested = lambda:True
            return None
        if retry:
            runtime._latest = FrameSnapshot(np.zeros((120,240,3),np.uint8),retry.observed_at,retry.sequence)
        if invalid == 'cancel_during_reacquisition':runtime.cancel_requested = lambda:True
        return retry
    runtime._inventory_after = inventory
    with pytest.raises(RuntimeError,match='inventory_page_transition_unverified'):
        runtime._navigate_page(2,origin)
    assert adb.tap.call_count == 1


def test_delayed_page_effect_during_reacquisition_does_not_retry():
    now = [10.]; adb = Mock()
    runtime = EquipmentSellRuntime(Mock(get_frame=Mock()),Mock(),ActionExecutor(adb),clock=lambda:now[0])
    origin = EquipmentInventoryFact(132,132,1,22,2,10.,(1,2))
    target = EquipmentInventoryFact(132,132,2,22,4,10.,(3,4))
    values = iter([origin,None,target])
    def inventory(cursor,predicate=lambda value:True):
        value=next(values)
        if value:
            runtime._latest=FrameSnapshot(np.zeros((120,240,3),np.uint8),value.observed_at,value.sequence)
        return value
    runtime._inventory_after=inventory
    assert runtime._navigate_page(2,origin).page == 2
    assert adb.tap.call_count == 1
