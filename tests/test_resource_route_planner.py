"""I-impl pure Resource Route Planner contracts."""

from dataclasses import fields, replace
from pathlib import Path

import pytest

from bot.monster_wave_board_reader import MonsterWaveBoardRow
from bot.monster_wave_board_snapshot import (
    BoardEvidence,
    BoardPopup,
    MaxState,
    MonsterWaveBoardSnapshot,
    Tickets,
)
from bot.resource_route_planner import (
    CraftCapacityFact,
    CraftStep,
    IncomingRewardFact,
    KeysPromotionStep,
    MaterialConversionFact,
    NonBoardResourceFacts,
    ResourcePlanningInput,
    ResourceRouteStatus,
    TradingMaterialsStep,
    TradingSessionStep,
    UnresolvedCode,
    plan_resource_route,
)


ROOT = Path(__file__).resolve().parents[1]
ITEMS = (
    "brawlers_badges",
    "weapon_material",
    "hero_weapon_material",
    "bronze_key",
    "silver_key",
)


def _board(*, balances=None, limits=None, observed_at=10.0, sequence=10):
    balances = balances or {}
    limits = limits or {}
    rows = tuple(MonsterWaveBoardRow(
        item_id,
        balances.get(item_id, 0),
        limits.get(item_id, 100),
    ) for item_id in ITEMS)
    return MonsterWaveBoardSnapshot(
        skip_state=None,
        tickets=Tickets.UNKNOWN,
        sapphires_daily=None,
        max_state=MaxState(None, None, None, None),
        board_popup=BoardPopup.PRESENT_WITH_ROWS,
        blockers=(),
        resource_rows=rows,
        evidence=BoardEvidence(sequence, observed_at, (sequence - 1, sequence)),
    )


def _rewards(**amounts):
    return tuple(IncomingRewardFact(item_id, amounts.get(item_id, 0)) for item_id in ITEMS)


def _input(*, board=None, rewards=None, conversions=(), crafts=(), now=10.1):
    return ResourcePlanningInput(
        board=board or _board(),
        non_board=NonBoardResourceFacts(
            incoming_rewards=rewards if rewards is not None else _rewards(),
            material_conversions=conversions,
            craft_capacities=crafts,
        ),
        now=now,
        after_sequence=0,
    )


def _weapon_conversion():
    return MaterialConversionFact(
        "weapon_material",
        "hero_weapon_material",
        "hero_weapon_crafting_material",
        input_per_trade=40,
        output_per_trade=10,
    )


def _hero_craft(*, slots=1, cost=49):
    return CraftCapacityFact(
        "hero_weapon_material",
        "weapon",
        "hero",
        material_per_craft=cost,
        free_equipment_slots=slots,
    )


def test_nothing_provably_needed_returns_no_prerequisites():
    plan = plan_resource_route(_input())
    assert plan.status is ResourceRouteStatus.NO_PREREQUISITES
    assert plan.steps == () and plan.unresolved == ()


@pytest.mark.parametrize("item_id", ["bronze_key", "silver_key"])
def test_proven_key_overflow_emits_only_keys_capability(item_id):
    board = _board(balances={item_id: 100}, limits={item_id: 100})
    plan = plan_resource_route(_input(
        board=board,
        rewards=_rewards(**{item_id: 1}),
    ))
    assert plan.status is ResourceRouteStatus.READY
    assert plan.steps == (TradingSessionStep((KeysPromotionStep(),)),)
    source = repr(plan).casefold()
    assert "treasure" not in source and "relief" not in source


def test_material_need_with_destination_capacity_emits_exact_trading_operation():
    board = _board(
        balances={"weapon_material": 95, "hero_weapon_material": 10},
        limits={"weapon_material": 100, "hero_weapon_material": 100},
    )
    plan = plan_resource_route(_input(
        board=board,
        rewards=_rewards(weapon_material=10),
        conversions=(_weapon_conversion(),),
    ))
    assert plan.status is ResourceRouteStatus.READY
    (session,) = plan.steps
    assert isinstance(session, TradingSessionStep)
    (materials,) = session.operations
    assert isinstance(materials, TradingMaterialsStep)
    assert materials.operations[0].trading_item_id == "hero_weapon_crafting_material"
    assert materials.operations[0].quantity == 1


def test_craft_first_is_proven_from_complete_synthetic_facts():
    board = _board(
        balances={"weapon_material": 95, "hero_weapon_material": 95},
        limits={"weapon_material": 100, "hero_weapon_material": 100},
    )
    plan = plan_resource_route(_input(
        board=board,
        rewards=_rewards(weapon_material=10),
        conversions=(_weapon_conversion(),),
        crafts=(_hero_craft(),),
    ))
    assert plan.status is ResourceRouteStatus.READY
    assert isinstance(plan.steps[0], CraftStep)
    assert plan.steps[0] == CraftStep("weapon", "hero", 1)
    assert isinstance(plan.steps[1], TradingSessionStep)
    assert isinstance(plan.steps[1].operations[0], TradingMaterialsStep)


def test_keys_and_materials_share_one_deterministic_trading_visit():
    board = _board(
        balances={"weapon_material": 95, "hero_weapon_material": 10, "silver_key": 100},
        limits={"weapon_material": 100, "hero_weapon_material": 100, "silver_key": 100},
    )
    planning = _input(
        board=board,
        rewards=_rewards(weapon_material=10, silver_key=1),
        conversions=(_weapon_conversion(),),
    )
    first = plan_resource_route(planning)
    second = plan_resource_route(planning)
    assert first == second and hash(first) == hash(second)
    assert first.status is ResourceRouteStatus.READY
    assert len(first.steps) == 1
    (session,) = first.steps
    assert isinstance(session, TradingSessionStep)
    assert tuple(type(item) for item in session.operations) == (
        KeysPromotionStep,
        TradingMaterialsStep,
    )


def test_missing_or_unknown_reward_is_never_replaced_with_a_guess():
    missing = _rewards()[:-1]
    unknown = tuple(
        IncomingRewardFact(item_id, None if item_id == "silver_key" else 0)
        for item_id in ITEMS
    )
    for rewards in (missing, unknown):
        plan = plan_resource_route(_input(rewards=rewards))
        assert plan.status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY
        assert plan.steps == ()
        assert plan.unresolved[0].code is UnresolvedCode.MISSING_INCOMING_REWARD
        assert plan.unresolved[0].item_id == "silver_key"


def test_visible_material_row_without_conversion_is_not_a_trading_diagnosis():
    board = _board(balances={"weapon_material": 100}, limits={"weapon_material": 100})
    plan = plan_resource_route(_input(
        board=board,
        rewards=_rewards(weapon_material=1),
    ))
    assert plan.status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY
    assert plan.steps == ()
    assert plan.unresolved[0].code is UnresolvedCode.MISSING_MATERIAL_CONVERSION


def test_missing_craft_or_equipment_capacity_fails_closed():
    board = _board(
        balances={"weapon_material": 95, "hero_weapon_material": 95},
        limits={"weapon_material": 100, "hero_weapon_material": 100},
    )
    base = dict(
        board=board,
        rewards=_rewards(weapon_material=10),
        conversions=(_weapon_conversion(),),
    )
    missing = plan_resource_route(_input(**base))
    unknown = plan_resource_route(_input(
        **base,
        crafts=(_hero_craft(slots=None),),
    ))
    full = plan_resource_route(_input(
        **base,
        crafts=(_hero_craft(slots=0),),
    ))
    assert missing.unresolved[0].code is UnresolvedCode.MISSING_CRAFT_FACT
    assert unknown.unresolved[0].code is UnresolvedCode.MISSING_EQUIPMENT_CAPACITY
    assert full.unresolved[0].code is UnresolvedCode.CRAFT_ENTRY_CAPACITY_UNAVAILABLE
    assert missing.steps == unknown.steps == full.steps == ()


def test_brawlers_badges_does_not_invent_an_arena_ticket_route():
    board = _board(balances={"brawlers_badges": 100}, limits={"brawlers_badges": 100})
    plan = plan_resource_route(_input(
        board=board,
        rewards=_rewards(brawlers_badges=1),
    ))
    assert plan.status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY
    assert plan.unresolved[0].code is UnresolvedCode.ARENA_TICKET_ROUTE_NOT_ESTABLISHED
    assert plan.steps == ()


def test_stale_foreign_and_contradictory_boards_never_execute():
    stale = plan_resource_route(_input(board=_board(observed_at=1.0), now=10.0))
    foreign = plan_resource_route(replace(_input(), board="not-a-board"))
    board = _board()
    contradictory_board = replace(board, resource_rows=tuple(reversed(board.resource_rows)))
    contradictory = plan_resource_route(_input(board=contradictory_board))
    malformed = plan_resource_route(_input(board=replace(board, resource_rows=("bad",))))
    assert stale.status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY
    assert stale.unresolved[0].code is UnresolvedCode.STALE_BOARD_SNAPSHOT
    assert foreign.status is ResourceRouteStatus.CONTRADICTORY
    assert foreign.unresolved[0].code is UnresolvedCode.FOREIGN_BOARD_SNAPSHOT
    assert contradictory.status is ResourceRouteStatus.CONTRADICTORY
    assert malformed.status is ResourceRouteStatus.CONTRADICTORY
    assert all(plan.steps == () for plan in (stale, foreign, contradictory, malformed))


def test_duplicate_non_board_fact_is_contradictory():
    rewards = (*_rewards(), IncomingRewardFact("silver_key", 0))
    plan = plan_resource_route(_input(rewards=rewards))
    assert plan.status is ResourceRouteStatus.CONTRADICTORY
    assert plan.unresolved[0].code is UnresolvedCode.CONTRADICTORY_NON_BOARD_FACTS
    assert plan.steps == ()


def test_multiple_required_crafts_remain_an_explicit_policy_gap():
    board = _board(
        balances={"hero_weapon_material": 100},
        limits={"hero_weapon_material": 100},
    )
    plan = plan_resource_route(_input(
        board=board,
        rewards=_rewards(hero_weapon_material=60),
        crafts=(_hero_craft(cost=20),),
    ))
    assert plan.status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY
    assert plan.unresolved[0].code is UnresolvedCode.MULTI_CRAFT_POLICY_NOT_ESTABLISHED
    assert plan.steps == ()


def test_models_are_immutable_hashable_and_snapshot_schema_stays_descriptive():
    planning = _input()
    plan = plan_resource_route(planning)
    hash(planning)
    hash(plan)
    with pytest.raises(Exception):
        planning.now = 99.0
    snapshot_names = {field.name for field in fields(MonsterWaveBoardSnapshot)}
    assert not any(name.startswith("should_") for name in snapshot_names)
    assert "route" not in " ".join(snapshot_names)


def test_planner_source_has_no_runtime_or_physical_side_effects():
    source = (ROOT / "bot/resource_route_planner.py").read_text(encoding="utf-8")
    imports = "\n".join(line for line in source.splitlines() if line.startswith(("from ", "import ")))
    for forbidden in (
        "action_executor",
        "adb",
        "device",
        "trading_runtime",
        "craft_runtime",
        "treasure",
        "equipment_relief",
        "quick_menu",
        "lobby",
    ):
        assert forbidden not in imports.casefold()
    for forbidden in (
        ".tap(",
        ".swipe(",
        "sleep(",
        "time.",
        "gold_key_capacity ==",
        "equipmentreliefstep",
        "treasurestep",
    ):
        assert forbidden not in source.casefold()
