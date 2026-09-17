"""Crafting Materials scroll adapter over the directed primitive (offline)."""

from pathlib import Path

import pytest

from bot.directed_list_scroll import (
    DirectedScrollOutcome,
    KnownListScrollProfile,
    PlannedGesture,
)
from bot.trading_materials_scroll import (
    MATERIAL_CATALOG,
    TRADING_MATERIALS_SCROLL_PROFILE,
    MaterialRow,
    MaterialViewport,
    locate_material_target,
    viewport_to_reading,
)

CATALOG = ("m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8")


def _profile(**overrides):
    base = {
        "row_pitch": 0.10,
        "visible_rows": 4,
        "lane_x": 0.50,
        "top_y": 0.20,
        "bottom_y": 0.80,
    }
    base.update(overrides)
    return KnownListScrollProfile(**base)


def _row(row_id, center_y, complete=True):
    return MaterialRow(row_id=row_id, center_y=center_y, complete=complete)


def _viewport(rows, sequence, **kwargs):
    return MaterialViewport(rows=tuple(rows), sequence=sequence, **kwargs)


class ScriptedRows:
    def __init__(self, viewports):
        self._viewports = list(viewports)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._viewports.pop(0)


class GestureRecorder:
    def __init__(self):
        self.gestures = []

    def __call__(self, gesture):
        assert isinstance(gesture, PlannedGesture)
        self.gestures.append(gesture)


def _locate(viewports, target, **kwargs):
    params = {
        "catalog": CATALOG,
        "target": target,
        "profile": _profile(),
        "max_gestures": 5,
        "content_ready": True,
    }
    params.update(kwargs)
    emit = GestureRecorder()
    result = locate_material_target(
        observe_viewport=ScriptedRows(viewports), emit=emit, **params
    )
    return result, emit


def test_top_viewport_target_below_scrolls_forward_with_profile_geometry():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40), _row("m3", 0.50)], 1),
        _viewport([_row("m2", 0.30), _row("m3", 0.40), _row("m4", 0.50)], 2),
    ]
    result, emit = _locate(viewports, "m4", max_gestures=1)
    assert result.outcome is DirectedScrollOutcome.BUDGET_EXHAUSTED
    (gesture,) = emit.gestures
    assert gesture.direction.value == "forward"
    assert gesture.lane_x == pytest.approx(0.50)
    assert gesture.delta <= _profile().max_delta + 1e-9


def test_bottom_viewport_target_above_scrolls_backward():
    viewports = [
        _viewport([_row("m6", 0.30), _row("m7", 0.40), _row("m8", 0.50)], 1),
        _viewport([_row("m4", 0.30), _row("m5", 0.40), _row("m6", 0.50)], 2),
    ]
    result, emit = _locate(viewports, "m4", max_gestures=1)
    assert result.outcome is DirectedScrollOutcome.BUDGET_EXHAUSTED
    (gesture,) = emit.gestures
    assert gesture.direction.value == "backward"
    assert gesture.start_y == pytest.approx(0.20)


def test_complete_visible_target_is_ready_without_gestures():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.45), _row("m3", 0.60)], 1),
        _viewport([_row("m1", 0.30), _row("m2", 0.45), _row("m3", 0.60)], 2),
        _viewport([_row("m1", 0.30), _row("m2", 0.45), _row("m3", 0.60)], 3),
    ]
    result, emit = _locate(viewports, "m2")
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert emit.gestures == []
    assert result.stable_row_y == pytest.approx(0.45)


def test_partial_visible_target_is_not_actionable_without_input():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.45, complete=False)], 1),
    ]
    rows = ScriptedRows(viewports)
    emit = GestureRecorder()
    result = locate_material_target(
        catalog=CATALOG,
        target="m2",
        profile=_profile(),
        observe_viewport=rows,
        emit=emit,
        max_gestures=5,
        content_ready=True,
    )
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "target_row_partial"
    assert emit.gestures == []
    assert rows.calls == 1


def test_scroll_reaches_target_and_confirms_stable_row():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40), _row("m3", 0.50)], 1),
        _viewport([_row("m2", 0.30), _row("m3", 0.40), _row("m4", 0.55)], 2),
        _viewport([_row("m2", 0.30), _row("m3", 0.40), _row("m4", 0.55)], 3),
        _viewport([_row("m2", 0.30), _row("m3", 0.40), _row("m4", 0.55)], 4),
        _viewport([_row("m2", 0.30), _row("m3", 0.40), _row("m4", 0.55)], 5),
    ]
    result, emit = _locate(viewports, "m4")
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert len(emit.gestures) == 1
    assert result.stable_row_y == pytest.approx(0.55)


def test_ready_claim_with_shifted_confirm_row_is_rejected():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.45), _row("m3", 0.60)], 1),
        _viewport([_row("m1", 0.30), _row("m2", 0.45), _row("m3", 0.60)], 2),
        _viewport([_row("m1", 0.30), _row("m2", 0.90), _row("m3", 0.60)], 3),
    ]
    result, emit = _locate(viewports, "m2")
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "target_row_partial"
    assert emit.gestures == []


def test_same_viewport_after_gesture_reports_no_progress():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 1),
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 2),
    ]
    result, emit = _locate(viewports, "m8")
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert len(emit.gestures) == 1


def test_wrong_direction_evidence_stops():
    viewports = [
        _viewport([_row("m4", 0.30), _row("m5", 0.40)], 1),
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 2),
    ]
    result, emit = _locate(viewports, "m8")
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert len(emit.gestures) == 1


def test_lost_tab_during_scroll_reports_guard_lost():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 1),
        _viewport([_row("m2", 0.30), _row("m3", 0.40)], 2, guard_ok=False),
    ]
    result, emit = _locate(viewports, "m8")
    assert result.outcome is DirectedScrollOutcome.GUARD_LOST
    assert len(emit.gestures) == 1


def test_illegible_viewport_during_scroll_reports_unreadable():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 1),
        _viewport([_row("m2", 0.30), _row("m3", 0.40)], 2, readable=False),
    ]
    result, emit = _locate(viewports, "m8")
    assert result.outcome is DirectedScrollOutcome.UNREADABLE
    assert len(emit.gestures) == 1


def test_stale_viewport_proves_neither_progress_nor_ready():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 1),
        _viewport([_row("m3", 0.30), _row("m4", 0.40)], 1),
    ]
    result, emit = _locate(viewports, "m8")
    assert result.outcome is DirectedScrollOutcome.NO_PROGRESS
    assert result.reason == "stale_observation"
    assert len(emit.gestures) == 1


def test_unknown_target_fails_without_input():
    rows = ScriptedRows([_viewport([_row("m1", 0.30)], 1)])
    emit = GestureRecorder()
    result = locate_material_target(
        catalog=CATALOG,
        target="zzz",
        profile=_profile(),
        observe_viewport=rows,
        emit=emit,
        max_gestures=5,
        content_ready=True,
    )
    assert result.outcome is DirectedScrollOutcome.TARGET_UNKNOWN
    assert emit.gestures == []


def test_keys_section_never_calls_scroll_helper():
    rows = ScriptedRows([_viewport([_row("m1", 0.30)], 1)])
    emit = GestureRecorder()
    with pytest.raises(ValueError, match="keys_no_scroll"):
        locate_material_target(
            catalog=CATALOG,
            target="m1",
            profile=_profile(),
            observe_viewport=rows,
            emit=emit,
            max_gestures=5,
            section="keys",
            content_ready=True,
        )
    assert emit.gestures == []
    assert rows.calls == 0


def test_materials_path_requires_positive_readiness():
    rows = ScriptedRows([_viewport([_row("m1", 0.30)], 1)])
    emit = GestureRecorder()
    with pytest.raises(ValueError, match="materials_not_ready"):
        locate_material_target(
            catalog=CATALOG,
            target="m1",
            profile=_profile(),
            observe_viewport=rows,
            emit=emit,
            max_gestures=5,
            content_ready=False,
        )
    assert emit.gestures == []
    assert rows.calls == 0


def test_adapter_only_emits_scroll_gestures_without_taps():
    viewports = [
        _viewport([_row("m1", 0.30), _row("m2", 0.40)], 1),
        _viewport([_row("m3", 0.30), _row("m4", 0.40)], 2),
        _viewport([_row("m3", 0.30), _row("m4", 0.40)], 3),
    ]
    result, emit = _locate(viewports, "m8", max_gestures=1)
    assert result.outcome is DirectedScrollOutcome.BUDGET_EXHAUSTED
    assert len(emit.gestures) == 1
    assert isinstance(emit.gestures[0], PlannedGesture)


def test_viewport_converter_excludes_partial_rows():
    reading = viewport_to_reading(
        _viewport([_row("m1", 0.30), _row("m2", 0.45, complete=False)], 7),
        target="m2",
    )
    assert reading.visible_ids == ("m1",)
    assert reading.target_row_y is None
    assert reading.sequence == 7


def test_helper_module_has_no_trading_semantics():
    source = (
        Path(__file__).resolve().parent.parent.joinpath("bot", "directed_list_scroll.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    for forbidden in ("trading", "material"):
        assert forbidden not in source, forbidden


# Real-catalog offline simulations (HIL ground truth, synthetic geometry).


def test_real_catalog_has_22_ordered_rows_with_materials_in_place():
    assert len(MATERIAL_CATALOG) == 22
    assert len(set(MATERIAL_CATALOG)) == 22
    assert MATERIAL_CATALOG.index("accessory_crafting_material") == 14
    assert MATERIAL_CATALOG.index("weapon_crafting_material") == 15
    assert MATERIAL_CATALOG.index("hero_weapon_crafting_material") == 16
    assert MATERIAL_CATALOG.index("hero_armor_crafting_material") == 17
    assert MATERIAL_CATALOG.index("hero_accessory_crafting_material") == 18
    assert MATERIAL_CATALOG[0] == "super_awakening_stone"
    assert MATERIAL_CATALOG[-1] == "guild_commodity"


def test_real_profile_pins_hil_geometry():
    profile = TRADING_MATERIALS_SCROLL_PROFILE
    assert profile.row_pitch == pytest.approx(0.1418)
    assert profile.visible_rows == 4
    assert profile.lane_x == pytest.approx(0.33)
    assert profile.top_y == pytest.approx(0.36)
    assert profile.bottom_y == pytest.approx(0.94)
    assert profile.max_delta == pytest.approx(3 * 0.1418 * 0.95)
    assert profile.row_tolerance == pytest.approx(0.015)


def _real_rows(ids, first_center=0.4283, pitch=0.1418):
    return [
        MaterialRow(row_id=row_id, center_y=first_center + index * pitch)
        for index, row_id in enumerate(ids)
    ]


def _real_locate(viewports, target, **kwargs):
    params = {
        "catalog": MATERIAL_CATALOG,
        "target": target,
        "profile": TRADING_MATERIALS_SCROLL_PROFILE,
        "max_gestures": 6,
        "content_ready": True,
    }
    params.update(kwargs)
    emit = GestureRecorder()
    result = locate_material_target(
        observe_viewport=ScriptedRows(viewports), emit=emit, **params
    )
    return result, emit


def test_real_forward_reaches_hero_armor():
    target = "hero_armor_crafting_material"
    viewports = [
        _viewport(_real_rows(MATERIAL_CATALOG[11:15]), 1),
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 2),
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 3),
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 4),
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 5),
    ]
    result, emit = _real_locate(viewports, target)
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert len(emit.gestures) == 1
    assert emit.gestures[0].direction.value == "forward"
    assert emit.gestures[0].delta <= (
        TRADING_MATERIALS_SCROLL_PROFILE.max_delta + 1e-9
    )
    assert result.stable_row_y == pytest.approx(0.4283 + 3 * 0.1418)


def test_real_backward_reaches_weapon_material():
    target = "weapon_crafting_material"
    viewports = [
        _viewport(_real_rows(MATERIAL_CATALOG[18:22]), 1),
        _viewport(_real_rows(MATERIAL_CATALOG[15:19]), 2),
        _viewport(_real_rows(MATERIAL_CATALOG[15:19]), 3),
        _viewport(_real_rows(MATERIAL_CATALOG[15:19]), 4),
        _viewport(_real_rows(MATERIAL_CATALOG[15:19]), 5),
    ]
    result, emit = _real_locate(viewports, target)
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert len(emit.gestures) == 1
    assert emit.gestures[0].direction.value == "backward"
    assert result.stable_row_y == pytest.approx(0.4283)


def test_real_already_visible_needs_no_gesture():
    target = "hero_armor_crafting_material"
    viewports = [
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 1),
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 2),
        _viewport(_real_rows(MATERIAL_CATALOG[14:18]), 3),
    ]
    result, emit = _real_locate(viewports, target)
    assert result.outcome is DirectedScrollOutcome.TARGET_READY
    assert emit.gestures == []
