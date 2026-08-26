from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import (
    ActionExecutor,
    DEFAULT_BLACK_MARKET_ACTION_TARGETS,
    FrameGeometry,
)
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    CloseBlackMarket,
    OpenBlackMarket,
    RejectInsufficientGold,
    SelectBlackMarketSlot,
)


def test_frame_geometry_is_derived_from_actual_landscape_frame_shape():
    frame = np.zeros((720, 1600, 3), dtype=np.uint8)

    geometry = FrameGeometry.from_frame(frame)

    assert geometry.width == 1600
    assert geometry.height == 720


@pytest.mark.parametrize(
    ("action", "target"),
    (
        (OpenBlackMarket(), DEFAULT_BLACK_MARKET_ACTION_TARGETS.open_black_market),
        (CloseBlackMarket(), DEFAULT_BLACK_MARKET_ACTION_TARGETS.close_black_market),
        (
            AcceptPurchaseConfirmation(),
            DEFAULT_BLACK_MARKET_ACTION_TARGETS.accept_purchase,
        ),
        (
            RejectInsufficientGold(),
            DEFAULT_BLACK_MARKET_ACTION_TARGETS.reject_insufficient_gold,
        ),
    ),
)
def test_executor_translates_semantic_action_to_frame_pixel_tap(action, target):
    adb = Mock()
    executor = ActionExecutor(adb)
    geometry = FrameGeometry.from_frame(np.zeros((720, 1600, 3), dtype=np.uint8))

    receipt = executor.execute(action, geometry)

    expected = (int(target[0] * 1600), int(target[1] * 720))
    adb.tap.assert_called_once_with(*expected)
    assert receipt.normalized_target == target
    assert receipt.pixel_target == expected


@pytest.mark.parametrize("slot_index", range(10))
def test_executor_supports_each_row_major_black_market_slot(slot_index):
    adb = Mock()
    executor = ActionExecutor(adb)
    geometry = FrameGeometry(width=2712, height=1224)

    receipt = executor.execute(SelectBlackMarketSlot(slot_index), geometry)

    target = DEFAULT_BLACK_MARKET_ACTION_TARGETS.slots[slot_index]
    expected = (int(target[0] * 2712), int(target[1] * 1224))
    adb.tap.assert_called_once_with(*expected)
    assert receipt.pixel_target == expected


@pytest.mark.parametrize("slot_index", (-1, 10, 1.5, True))
def test_select_slot_rejects_invalid_index(slot_index):
    with pytest.raises(ValueError, match="slot_index"):
        SelectBlackMarketSlot(slot_index)


def test_executor_does_not_query_device_size_or_apply_gameplay_policy():
    adb = Mock()
    executor = ActionExecutor(adb)

    executor.execute(OpenBlackMarket(), FrameGeometry(width=1000, height=500))

    adb.tap.assert_called_once()
    adb.shell.assert_not_called()


def test_executor_rejects_unknown_untyped_action_without_input():
    adb = Mock()
    executor = ActionExecutor(adb)

    with pytest.raises(ValueError, match="unsupported"):
        executor.execute(object(), FrameGeometry(width=1000, height=500))

    adb.tap.assert_not_called()
