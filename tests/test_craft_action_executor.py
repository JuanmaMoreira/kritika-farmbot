from unittest.mock import Mock

import pytest

from bot.action_executor import (
    ActionExecutor,
    DEFAULT_CRAFT_ACTION_TARGETS,
    FrameGeometry,
)
from bot.craft_semantics import CraftFamily
from bot.semantic_actions import (
    CancelCraft,
    ConfirmCraftMaterial,
    DismissCraftResult,
    OpenHeroCraft,
    RejectCraftPremium,
    SelectCraftMax,
    SelectQuickMenuCraft,
)


@pytest.mark.parametrize(
    ("action", "target"),
    (
        (SelectQuickMenuCraft(), DEFAULT_CRAFT_ACTION_TARGETS.select_quick_menu_craft_shifted),
        (OpenHeroCraft(CraftFamily.WEAPON), DEFAULT_CRAFT_ACTION_TARGETS.open_hero_weapon),
        (OpenHeroCraft(CraftFamily.ARMOR), DEFAULT_CRAFT_ACTION_TARGETS.open_hero_armor),
        (OpenHeroCraft(CraftFamily.ACCESSORY), DEFAULT_CRAFT_ACTION_TARGETS.open_hero_accessory),
        (SelectCraftMax(), DEFAULT_CRAFT_ACTION_TARGETS.select_max),
        (ConfirmCraftMaterial(), DEFAULT_CRAFT_ACTION_TARGETS.confirm_material),
        (CancelCraft(), DEFAULT_CRAFT_ACTION_TARGETS.cancel),
        (RejectCraftPremium(), DEFAULT_CRAFT_ACTION_TARGETS.reject_karats),
        (DismissCraftResult(), DEFAULT_CRAFT_ACTION_TARGETS.dismiss_result_safe_side),
    ),
)
def test_executor_translates_only_hil_acquired_craft_controls(action, target):
    adb = Mock()
    executor = ActionExecutor(adb)

    receipt = executor.execute(action, FrameGeometry(width=2712, height=1224))

    assert receipt.normalized_target == target
    adb.tap.assert_called_once_with(int(target[0] * 2712), int(target[1] * 1224))


def test_craft_action_vocabulary_has_no_scroll_or_karat_spend():
    import bot.semantic_actions as actions

    exported = set(actions.__all__)

    assert "SelectCraftMax" in exported
    assert "RejectCraftPremium" in exported
    assert "SpendCraftKarats" not in exported
    assert "ConfirmCraftKarats" not in exported


def test_result_dismiss_uses_hil_safe_side_not_interactive_center():
    target = DEFAULT_CRAFT_ACTION_TARGETS.dismiss_result_safe_side

    assert target == (0.20, 0.50)
    assert target[0] < 0.30
