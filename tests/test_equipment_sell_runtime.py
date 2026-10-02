import time
from unittest.mock import Mock

import numpy as np

from bot.action_executor import ActionExecutor, DEFAULT_EQUIPMENT_ACTION_TARGETS
from bot.capture import FrameSnapshot
from bot.equipment_sell_operation import (
    EquipmentSellCandidate,
    EquipmentSellOutcome,
    EquipmentSellRequest,
)
from bot.equipment_sell_policy import EquipmentSellAuthorization
from bot.equipment_sell_runtime import EquipmentSellRuntime
from bot.equipment_sell_semantics import (
    EquipmentBulkGroup,
    EquipmentGrade,
    EquipmentInventoryFact,
    EquipmentItemFact,
    EquipmentSellConfirmationFact,
    EquipmentType,
)


class _Source:
    def __init__(self):
        self.sequence = 0

    def get_frame(self):
        self.sequence += 1
        return FrameSnapshot(
            np.zeros((1220, 2712, 3), dtype=np.uint8),
            time.monotonic(),
            self.sequence,
        )


class _Reader:
    def __init__(self, adb):
        self.adb = adb

    def inventory_sample(self, _frame, *, sequence, observed_at):
        count = 120 if self.adb.tap.call_count < 3 else 119
        return EquipmentInventoryFact(
            count, 112, 7, 22, sequence, observed_at,
            sample_sequences=(sequence,),
        )

    def detail_sample(self, _frame, *, sequence, observed_at):
        return EquipmentItemFact(
            "Gloves (Enhance)",
            EquipmentGrade.EPIC,
            EquipmentType.GLOVES,
            True,
            sequence,
            observed_at,
            sample_sequences=(sequence,),
        )

    def confirmation_sample(self, _frame, *, sequence, observed_at):
        return EquipmentSellConfirmationFact(
            "Gloves (Enhance)",
            EquipmentBulkGroup.ENHANCE_GRADE,
            None,
            sequence,
            observed_at,
            sample_sequences=(sequence,),
        )


def _request():
    return EquipmentSellRequest(
        authorization=EquipmentSellAuthorization(
            allowed_types=frozenset({EquipmentType.GLOVES}),
            allowed_grades=frozenset({EquipmentGrade.EPIC}),
            allowed_enhance_states=frozenset({True}),
            allowed_bulk_groups=frozenset({EquipmentBulkGroup.ENHANCE_GRADE}),
        ),
        candidate=EquipmentSellCandidate(page=7, slot=15),
    )


def test_runtime_executes_one_verified_bulk_sale_through_action_executor():
    adb = Mock()
    actions = ActionExecutor(adb)
    runtime = EquipmentSellRuntime(
        _Source(),
        _Reader(adb),
        actions,
        sample_interval=0,
    )

    result = runtime.execute(_request())

    assert result.outcome is EquipmentSellOutcome.SUCCESS
    assert result.confirm_count == 1
    assert adb.tap.call_count == 3
    expected = (
        DEFAULT_EQUIPMENT_ACTION_TARGETS.inventory_slots[15],
        DEFAULT_EQUIPMENT_ACTION_TARGETS.open_sell,
        DEFAULT_EQUIPMENT_ACTION_TARGETS.confirm_bulk_sale,
    )
    assert [call.args for call in adb.tap.call_args_list] == [
        (int(x * 2712), int(y * 1220)) for x, y in expected
    ]


def test_runtime_unreadable_initial_inventory_sends_no_input():
    adb = Mock()
    reader = Mock()
    reader.inventory_sample.return_value = None
    runtime = EquipmentSellRuntime(
        _Source(),
        reader,
        ActionExecutor(adb),
        sample_timeout=1,
        sample_interval=0,
    )

    result = runtime.execute(_request())

    assert result.outcome is EquipmentSellOutcome.FAILED
    assert result.reason == "initial_inventory_unreadable"
    adb.tap.assert_not_called()


def test_runtime_waits_bounded_animation_frames_without_retrying_confirm():
    adb = Mock()

    class DelayedPostReader(_Reader):
        def __init__(self, adb):
            super().__init__(adb)
            self.post_reads = 0

        def inventory_sample(self, frame, *, sequence, observed_at):
            if self.adb.tap.call_count >= 3:
                self.post_reads += 1
                if self.post_reads <= 8:
                    return None
            return super().inventory_sample(
                frame, sequence=sequence, observed_at=observed_at
            )

    runtime = EquipmentSellRuntime(
        _Source(),
        DelayedPostReader(adb),
        ActionExecutor(adb),
        sample_interval=0,
    )

    result = runtime.execute(_request())

    assert result.outcome is EquipmentSellOutcome.SUCCESS
    assert result.confirm_count == 1
    assert adb.tap.call_count == 3


def _expansion_runtime(*, popup_cost=180, effect=True):
    adb=Mock()
    class ExpansionReader(_Reader):
        def inventory_sample(self, frame, *, sequence, observed_at):
            if adb.tap.call_count == 1:
                return None
            capacity=132 if effect and adb.tap.call_count >= 2 else 128
            return EquipmentInventoryFact(130,capacity,9,22,sequence,observed_at,
                                          sample_sequences=(sequence,))
        def capacity_row_cost(self, frame, row):
            assert row == 0
            return 180
        def expansion_sample(self, frame, *, sequence, observed_at):
            return (popup_cost,sequence,observed_at)
        def expansion_visible(self, frame):
            return True
    runtime=EquipmentSellRuntime(_Source(),ExpansionReader(adb),ActionExecutor(adb),
                                 sample_interval=.001,sample_timeout=.04)
    before=EquipmentInventoryFact(130,128,9,22,2,time.monotonic(),sample_sequences=(1,2))
    return runtime,adb,before


def test_capacity_purchase_uses_next_row_once_and_verifies_exactly_four_slots():
    runtime,adb,before=_expansion_runtime()
    result=runtime._expand(before)
    assert result.succeeded
    assert result.confirm_count == 1 and result.cost == 180
    assert result.after.capacity == before.capacity + 4
    assert adb.tap.call_count == 2
    assert adb.tap.call_args_list[0].args == (int(.68*2712),int(.375*1220))
    assert adb.tap.call_args_list[1].args == (int(.43*2712),int(.625*1220))


def test_capacity_popup_cost_mismatch_cancels_without_confirm():
    runtime,adb,before=_expansion_runtime(popup_cost=181)
    result=runtime._expand(before)
    assert not result.succeeded and result.confirm_count == 0
    assert result.reason == "expansion_popup_unverified"
    assert adb.tap.call_count == 2
    assert adb.tap.call_args_list[-1].args == (int(.57*2712),int(.625*1220))


def test_capacity_inconclusive_effect_never_repeats_purchase():
    runtime,adb,before=_expansion_runtime(effect=False)
    result=runtime._expand(before)
    assert not result.succeeded and result.confirm_count == 1
    assert result.reason == "effect_inconclusive"
    assert result.after is None
    assert adb.tap.call_count == 2
