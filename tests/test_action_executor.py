from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import (
    ActionExecutor,
    DEFAULT_BLACK_MARKET_ACTION_TARGETS,
    DEFAULT_BATTLE_ACTION_TARGETS,
    DEFAULT_ROTATION_ACTION_TARGETS,
    FrameGeometry,
)
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    AcknowledgeInventoryFull,
    AcknowledgeWorldBossPreviousRewards,
    CloseBlackMarket,
    ConfirmCharacterSelection,
    ContinueAfterWorldBossRaid,
    DismissWorldBossBagFull,
    OpenBlackMarket,
    OpenBattleModeSelect,
    OpenCharacterSelect,
    OpenQuickMenu,
    QuickMenuLayout,
    OpenWorldBossSelector,
    RejectInsufficientGold,
    RejectWorldBossInventoryFull,
    SelectLastVisibleCharacter,
    SelectAvailableWorldBoss,
    SelectBlackMarketSlot,
    Swipe,
    ToggleAutoBattle,
    StartWorldBossBattle,
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
        (
            AcknowledgeInventoryFull(),
            DEFAULT_BLACK_MARKET_ACTION_TARGETS.acknowledge_inventory_full,
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


@pytest.mark.parametrize(
    ("action", "target"),
    (
        (OpenBattleModeSelect(), DEFAULT_BATTLE_ACTION_TARGETS.open_battle_mode_select),
        (OpenWorldBossSelector(), DEFAULT_BATTLE_ACTION_TARGETS.open_world_boss_selector),
        (SelectAvailableWorldBoss(), DEFAULT_BATTLE_ACTION_TARGETS.select_available_world_boss),
        (AcknowledgeWorldBossPreviousRewards(), DEFAULT_BATTLE_ACTION_TARGETS.acknowledge_previous_rewards),
        (StartWorldBossBattle(), DEFAULT_BATTLE_ACTION_TARGETS.start_world_boss_battle),
        (ToggleAutoBattle(), DEFAULT_BATTLE_ACTION_TARGETS.toggle_auto_battle),
        (ContinueAfterWorldBossRaid(), DEFAULT_BATTLE_ACTION_TARGETS.continue_after_raid),
        (RejectWorldBossInventoryFull(), DEFAULT_BATTLE_ACTION_TARGETS.reject_world_boss_inventory_full),
        (DismissWorldBossBagFull(), DEFAULT_BATTLE_ACTION_TARGETS.dismiss_world_boss_bag_full),
    ),
)
def test_executor_translates_world_boss_route_actions(action, target):
    adb = Mock()
    executor = ActionExecutor(adb)

    receipt = executor.execute(action, FrameGeometry(width=2712, height=1224))

    adb.tap.assert_called_once_with(int(target[0] * 2712), int(target[1] * 1224))
    assert receipt.normalized_target == target


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


@pytest.mark.parametrize(
    ("action", "target"),
    (
        (OpenQuickMenu(), DEFAULT_ROTATION_ACTION_TARGETS.open_quick_menu),
        (
            OpenCharacterSelect(),
            DEFAULT_ROTATION_ACTION_TARGETS.open_character_select,
        ),
        (
            SelectLastVisibleCharacter(),
            DEFAULT_ROTATION_ACTION_TARGETS.last_visible_character,
        ),
        (
            ConfirmCharacterSelection(),
            DEFAULT_ROTATION_ACTION_TARGETS.confirm_character_selection,
        ),
    ),
)
def test_executor_translates_rotation_taps_from_frame_geometry(action, target):
    adb = Mock()
    executor = ActionExecutor(adb)
    geometry = FrameGeometry(width=2712, height=1224)

    receipt = executor.execute(action, geometry)

    expected = (int(target[0] * 2712), int(target[1] * 1224))
    adb.tap.assert_called_once_with(*expected)
    assert receipt.normalized_target == target
    assert receipt.pixel_target == expected


def test_shifted_quick_menu_uses_non_lobby_character_target():
    adb = Mock()
    executor = ActionExecutor(adb)
    action = OpenCharacterSelect(QuickMenuLayout.SHIFTED)

    receipt = executor.execute(action, FrameGeometry(width=2712, height=1224))

    target = DEFAULT_ROTATION_ACTION_TARGETS.open_character_select_shifted
    adb.tap.assert_called_once_with(int(target[0] * 2712), int(target[1] * 1224))
    assert target[0] - DEFAULT_ROTATION_ACTION_TARGETS.open_character_select[0] == pytest.approx(0.1296)


def test_quick_menu_uses_the_shared_live_confirmed_header_target():
    assert DEFAULT_ROTATION_ACTION_TARGETS.open_quick_menu == (0.1940, 0.0564)


def test_executor_translates_auto_battle_toggle_from_frame_geometry():
    adb = Mock()
    executor = ActionExecutor(adb)
    geometry = FrameGeometry(width=2712, height=1224)

    receipt = executor.execute(ToggleAutoBattle(), geometry)

    target = DEFAULT_BATTLE_ACTION_TARGETS.toggle_auto_battle
    expected = (int(target[0] * 2712), int(target[1] * 1224))
    adb.tap.assert_called_once_with(*expected)
    assert receipt.normalized_target == target


def test_auto_battle_target_is_centered_in_live_calibrated_control_roi():
    x, y = DEFAULT_BATTLE_ACTION_TARGETS.toggle_auto_battle

    assert x == pytest.approx((0.8350 + 0.8900) / 2)
    assert y == pytest.approx((0.0180 + 0.0780) / 2)


def test_executor_translates_generic_normalized_swipe_to_one_adb_swipe():
    adb = Mock()
    executor = ActionExecutor(adb)
    geometry = FrameGeometry(width=2712, height=1224)
    action = Swipe(start=(0.80, 0.80), end=(0.80, 0.025), duration_ms=190)

    receipt = executor.execute(action, geometry)

    start = (int(action.start[0] * 2712), int(action.start[1] * 1224))
    end = (int(action.end[0] * 2712), int(action.end[1] * 1224))
    adb.swipe.assert_called_once_with(*start, *end, action.duration_ms)
    adb.tap.assert_not_called()
    assert receipt.pixel_start == start
    assert receipt.pixel_end == end


@pytest.mark.parametrize(
    "kwargs",
    (
        {"start": (-0.1, 0.5), "end": (0.5, 0.5), "duration_ms": 100},
        {"start": (0.5, 0.5), "end": (1.1, 0.5), "duration_ms": 100},
        {"start": (0.5, 0.5), "end": (0.5, 0.2), "duration_ms": 0},
    ),
)
def test_generic_swipe_rejects_invalid_geometry_or_duration(kwargs):
    with pytest.raises(ValueError):
        Swipe(**kwargs)


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
