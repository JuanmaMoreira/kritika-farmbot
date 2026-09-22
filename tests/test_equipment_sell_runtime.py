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
            float(self.sequence),
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
