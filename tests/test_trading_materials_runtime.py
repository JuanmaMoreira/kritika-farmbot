from types import SimpleNamespace

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.directed_list_scroll import DirectedScrollOutcome, DirectedScrollResult
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.resource_route_planner import TradingMaterialOperation, TradingMaterialsStep
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.trading_center_semantics import (
    INDICATOR_TRADING_GENERAL_ACTIVE,
    INDICATOR_TRADING_MATERIAL_ROWS,
    LANDMARK_TRADING_CENTER_TITLE,
    SCREEN_TRADING,
)
from bot.trading_materials_runtime import FreshMaterialFact, TradingMaterialsRuntime
from bot.trading_operation import TradeOutcome, TradeResult
from bot.trading_row_facts import MATERIALS_SECTION, TradingRowFact


def _snapshot(sequence):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    names = (
        LANDMARK_TRADING_CENTER_TITLE,
        INDICATOR_TRADING_GENERAL_ACTIVE,
        INDICATOR_TRADING_MATERIAL_ROWS,
    )
    observations = tuple(
        Observation(name, 1.0, ObservationSource.LOCAL_CV) for name in names
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=SCREEN_TRADING,
            overlays=(),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _fresh(sequence, item_id="hero_weapon_crafting_material", have=100):
    return FreshMaterialFact(
        _snapshot(sequence),
        TradingRowFact(
            item_id,
            MATERIALS_SECTION,
            0.55,
            have,
            10,
            sequence,
        ),
    )


def _step():
    return TradingMaterialsStep((
        TradingMaterialOperation(
            "hero_weapon_crafting_material",
            "weapon_material",
            "hero_weapon_material",
            2,
        ),
    ))


def test_exact_planned_material_only_is_located_read_fresh_and_executed_once():
    trace = []

    class Trading:
        def ensure_general(self):
            trace.append("general")
            return SimpleNamespace(
                status=FlowStatus.COMPLETED,
                final_snapshot=_snapshot(10),
                error=None,
            )

    def locate(*, target, after_sequence):
        trace.append(("locate", target, after_sequence))
        return DirectedScrollResult(
            DirectedScrollOutcome.TARGET_READY,
            stable_row_y=0.55,
            stable_sequence=11,
            last_sequence=12,
        )

    def read(*, target, after_sequence):
        trace.append(("read", target, after_sequence))
        return _fresh(13, target)

    def execute(*, operation, snapshot, row_fact, quantity):
        trace.append(("execute", operation.trading_item_id, quantity.mode.value, quantity.amount))
        return TradeResult(
            TradeOutcome.SUCCESS,
            row_fact,
            TradingRowFact(
                row_fact.item_id,
                row_fact.section,
                row_fact.row_y,
                80,
                row_fact.need,
                14,
            ),
        )

    result = TradingMaterialsRuntime(
        Trading(),
        locate_material=locate,
        read_material_fact=read,
        execute_material_trade=execute,
    ).execute(_step())

    assert result.status is FlowStatus.COMPLETED
    assert result.executed_operations == _step().operations
    assert trace == [
        "general",
        ("locate", "hero_weapon_crafting_material", 10),
        ("read", "hero_weapon_crafting_material", 12),
        ("execute", "hero_weapon_crafting_material", "exact", 2),
    ]


def test_adapter_never_diagnoses_or_visits_an_unplanned_row():
    targets = []

    class Trading:
        def ensure_general(self):
            return SimpleNamespace(
                status=FlowStatus.COMPLETED,
                final_snapshot=_snapshot(10),
                error=None,
            )

    runtime = TradingMaterialsRuntime(
        Trading(),
        locate_material=lambda *, target, after_sequence: (
            targets.append(target)
            or DirectedScrollResult(
                DirectedScrollOutcome.TARGET_UNKNOWN,
                last_sequence=11,
                reason="missing",
            )
        ),
        read_material_fact=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("must not speculate")
        ),
        execute_material_trade=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("must not trade")
        ),
    )

    result = runtime.execute(_step())

    assert result.status is FlowStatus.FAILED
    assert targets == ["hero_weapon_crafting_material"]


def test_equipment_full_boundary_stops_with_missing_adapter_reason():
    class Trading:
        def ensure_general(self):
            return SimpleNamespace(
                status=FlowStatus.COMPLETED,
                final_snapshot=_snapshot(10),
                error=None,
            )

    before = _fresh(13)
    runtime = TradingMaterialsRuntime(
        Trading(),
        locate_material=lambda **kwargs: DirectedScrollResult(
            DirectedScrollOutcome.TARGET_READY,
            stable_row_y=0.55,
            stable_sequence=11,
            last_sequence=12,
        ),
        read_material_fact=lambda **kwargs: before,
        execute_material_trade=lambda **kwargs: TradeResult(
            TradeOutcome.FAILED,
            before.row_fact,
            boundary="equipment_full",
            reason="equipment_full",
        ),
    )

    result = runtime.execute(_step())

    assert result.status is FlowStatus.FAILED
    assert result.error.endswith(":missing_adapter")
    assert result.executed_operations == ()
