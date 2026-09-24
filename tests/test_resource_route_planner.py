"""Operational entry thresholds and symbolic resource routing."""
from dataclasses import replace
import pytest
from bot.monster_wave_board_reader import MonsterWaveBoardRow
from bot.monster_wave_board_snapshot import (
    BoardEvidence, BoardPopup, MaxState, MonsterWaveBoardSnapshot, Tickets,
)
from bot.resource_route_planner import (
    CraftCapacityFact, CraftStep, IncomingRewardFact, KeysPromotionStep,
    NonBoardResourceFacts, PlanningEvidenceKind, ResourcePlanningInput,
    ResourceRouteStatus, TradingMaterialsStep, TradingSessionStep,
    UnresolvedCode, plan_resource_route,
)

ITEMS = ("brawlers_badges", "weapon_material", "hero_weapon_material",
         "bronze_key", "silver_key")
LIMITS = dict(brawlers_badges=499, weapon_material=999,
              hero_weapon_material=999, bronze_key=499, silver_key=499)


def board(**balances):
    return MonsterWaveBoardSnapshot(
        skip_state=None, tickets=Tickets.UNKNOWN, sapphires_daily=None,
        max_state=MaxState(None, None, None, None),
        board_popup=BoardPopup.PRESENT_WITH_ROWS, blockers=(),
        resource_rows=tuple(
            MonsterWaveBoardRow(item, balances.get(item, 0), LIMITS[item])
            for item in ITEMS
        ),
        evidence=BoardEvidence(10, 10.0, (9, 10)),
    )


def plan(*, facts=None, **balances):
    return plan_resource_route(ResourcePlanningInput(
        board(**balances),
        facts if facts is not None else NonBoardResourceFacts(),
        10.1, 0,
    ))


def craft_fact(slots=1):
    return CraftCapacityFact("hero_weapon_material", "weapon", "hero", 49, slots)


def shape(result):
    if result.status is ResourceRouteStatus.NO_PREREQUISITES:
        return "none"
    assert result.status is ResourceRouteStatus.READY
    return tuple(
        ("craft" if isinstance(step, CraftStep) else
         ("keys", "materials") if len(step.operations) == 2 else ("keys",))
        for step in result.steps
    )


@pytest.mark.parametrize("item,before,at,expected", [
    ("bronze_key", 399, 400, (("keys",),)),
    ("silver_key", 449, 450, (("keys",),)),
    ("weapon_material", 799, 800, (("keys", "materials"),)),
    ("hero_weapon_material", 799, 800, ("craft",)),
])
def test_inclusive_entry_boundaries(item, before, at, expected):
    facts = NonBoardResourceFacts(craft_capacities=(craft_fact(),))
    assert shape(plan(facts=facts, **{item: before})) == "none"
    assert shape(plan(facts=facts, **{item: at})) == expected


@pytest.mark.parametrize("item,amount", [
    ("bronze_key", 501), ("silver_key", 501),
    ("weapon_material", 1001), ("hero_weapon_material", 1001),
])
def test_above_displayed_limit_is_actionable(item, amount):
    facts = NonBoardResourceFacts(craft_capacities=(craft_fact(),))
    assert plan(facts=facts, **{item: amount}).status is ResourceRouteStatus.READY


def test_badges_are_warning_only_and_never_block_other_capabilities():
    alone = plan(brawlers_badges=499)
    assert shape(alone) == "none"
    assert any(e.kind is PlanningEvidenceKind.WARNING for e in alone.evidence)
    together = plan(brawlers_badges=500, bronze_key=400)
    assert shape(together) == (("keys",),)


def test_materials_pay_for_keys_but_keys_do_not_pay_for_general():
    materials = plan(weapon_material=800, bronze_key=399, silver_key=449)
    assert shape(materials) == (("keys", "materials"),)
    assert isinstance(materials.steps[0].operations[0], KeysPromotionStep)
    assert isinstance(materials.steps[0].operations[1], TradingMaterialsStep)
    assert materials.steps[0].operations[1].operations[0].quantity is None
    assert shape(plan(weapon_material=799, bronze_key=400)) == (("keys",),)


def test_craft_alone_and_craft_then_keys_only():
    facts = NonBoardResourceFacts(craft_capacities=(craft_fact(),))
    assert shape(plan(facts=facts, hero_weapon_material=800)) == ("craft",)
    assert shape(plan(facts=facts, hero_weapon_material=800, silver_key=450)) == (
        "craft", ("keys",),
    )


def test_deterministic_current_trade_projection_straddles_800():
    facts = NonBoardResourceFacts(craft_capacities=(craft_fact(),))
    assert shape(plan(facts=facts, weapon_material=800, hero_weapon_material=599)) == (
        ("keys", "materials"),
    )
    assert shape(plan(facts=facts, weapon_material=800, hero_weapon_material=600)) == (
        "craft", ("keys", "materials"),
    )
    assert shape(plan(facts=facts, weapon_material=839, hero_weapon_material=599)) == (
        ("keys", "materials"),
    )
    assert shape(plan(facts=facts, weapon_material=840, hero_weapon_material=590)) == (
        "craft", ("keys", "materials"),
    )


def test_incoming_rewards_are_ignored_in_production_plan():
    facts = NonBoardResourceFacts(
        incoming_rewards=(IncomingRewardFact("silver_key", None),),
    )
    assert plan(facts=facts, bronze_key=400) == plan(bronze_key=400)
    assert plan(facts=facts, silver_key=449).status is ResourceRouteStatus.NO_PREREQUISITES


def test_craft_entry_capacity_remains_explicit_and_no_relief_step_is_invented():
    assert plan(hero_weapon_material=800).unresolved[0].code is UnresolvedCode.MISSING_CRAFT_FACT
    full = NonBoardResourceFacts(craft_capacities=(craft_fact(0),))
    assert plan(facts=full, hero_weapon_material=800).unresolved[0].code is (
        UnresolvedCode.CRAFT_ENTRY_CAPACITY_UNAVAILABLE
    )


def test_stale_board_still_fails_closed():
    planning = ResourcePlanningInput(board(bronze_key=400), NonBoardResourceFacts(),
                                     20.0, 0)
    assert plan_resource_route(planning).status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY


def test_red_pressure_matches_equivalent_numeric_route_without_changing_thresholds():
    facts = NonBoardResourceFacts(craft_capacities=(craft_fact(),))
    numeric = board(brawlers_badges=260, weapon_material=999,
                    hero_weapon_material=999, bronze_key=499, silver_key=499)
    red = replace(numeric, resource_rows=tuple(
        MonsterWaveBoardRow(item, None, None, True) for item in ITEMS))
    def route(source):
        return plan_resource_route(ResourcePlanningInput(source, facts, 10.1, 0))
    assert shape(route(red)) == shape(route(numeric)) == (
        "craft", ("keys", "materials"))
    assert any(e.kind is PlanningEvidenceKind.WARNING for e in route(red).evidence)


def test_red_weapon_without_exact_projection_fails_closed():
    numeric = board(weapon_material=800, hero_weapon_material=599)
    rows = list(numeric.resource_rows)
    rows[1] = MonsterWaveBoardRow("weapon_material", None, None, True)
    red = replace(numeric, resource_rows=tuple(rows))
    result = plan_resource_route(ResourcePlanningInput(red, NonBoardResourceFacts(), 10.1, 0))
    assert result.status is ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY
    assert result.unresolved[0].required_fact == "exact_weapon_and_hero_for_projection"
