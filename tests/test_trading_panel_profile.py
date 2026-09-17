"""HIL-calibrated panel geometry: safe points, separation, wiring."""

from pathlib import Path

from bot.trading_operation import TradePanelTargets, execute_verified_trade
from bot.trading_panel_profile import (
    ROW_TAP_X,
    TRADING_PANEL_PROFILE,
    TradingPanelProfile,
    panel_targets,
)


def test_points_inside_own_bboxes_with_margin():
    profile = TRADING_PANEL_PROFILE
    for point_name, bbox_name in (
        ("confirm_point", "confirm_bbox"),
        ("cancel_point", "cancel_bbox"),
        ("max_point", "max_bbox"),
    ):
        x, y = getattr(profile, point_name)
        x0, y0, x1, y1 = getattr(profile, bbox_name)
        assert x0 < x < x1 and y0 < y < y1
        # interior margin: at least ~8px from each edge on 2712x1224
        assert min(x - x0, x1 - x) > 0.002
        assert min(y - y0, y1 - y) > 0.002


def test_buttons_ordered_no_trade_label_confusion():
    profile = TRADING_PANEL_PROFILE
    # No left, Trade middle, >> right; same button row y ~= 0.79
    assert profile.cancel_point[0] < profile.confirm_point[0] < profile.max_point[0]
    for _, y in (
        profile.cancel_point,
        profile.confirm_point,
        profile.max_point,
    ):
        assert 0.74 < y < 0.83
    # confirm is the calibrated Trade center, not the prior miss nor No/>>.
    assert abs(profile.confirm_point[0] - 0.43) > 0.05
    assert profile.confirm_point != profile.cancel_point
    assert profile.confirm_point != profile.max_point


def test_bboxes_inside_popup_without_overlap():
    popup = (0.275, 0.208, 0.724, 0.849)
    boxes = (
        TRADING_PANEL_PROFILE.cancel_bbox,
        TRADING_PANEL_PROFILE.confirm_bbox,
        TRADING_PANEL_PROFILE.max_bbox,
    )
    for x0, y0, x1, y1 in boxes:
        assert popup[0] <= x0 and x1 <= popup[2]
        assert popup[1] <= y0 and y1 <= popup[3]
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            assert (
                first[2] <= second[0]
                or second[2] <= first[0]
                or first[3] <= second[1]
                or second[3] <= first[1]
            )


def test_row_tap_x_separate_from_panel():
    assert ROW_TAP_X == 0.75
    panel_xs = {
        TRADING_PANEL_PROFILE.confirm_point[0],
        TRADING_PANEL_PROFILE.cancel_point[0],
        TRADING_PANEL_PROFILE.max_point[0],
    }
    assert ROW_TAP_X not in panel_xs
    assert ROW_TAP_X > TRADING_PANEL_PROFILE.max_bbox[2]


def test_panel_targets_wiring_uses_trade_not_label():
    targets = panel_targets()
    assert isinstance(targets, TradePanelTargets)
    assert targets.confirm_point == TRADING_PANEL_PROFILE.confirm_point
    assert targets.cancel_point == TRADING_PANEL_PROFILE.cancel_point
    assert targets.max_point == TRADING_PANEL_PROFILE.max_point
    # distinct controls: confirm never equals cancel/max.
    assert len({targets.confirm_point, targets.cancel_point, targets.max_point}) == 3


def test_profile_module_has_no_sink_or_adb_imports():
    source = (
        Path(__file__).resolve().parent.parent
        / "bot"
        / "trading_panel_profile.py"
    ).read_text(encoding="utf-8")
    import_lines = [
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines).casefold()
    for forbidden in (
        "treasure", "craft", "relief", "monster_wave", "planner",
        "stage", "inventory", "adb", "scrcpy", "directed_list_scroll",
    ):
        assert forbidden not in joined, forbidden
