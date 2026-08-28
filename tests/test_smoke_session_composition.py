from types import SimpleNamespace

from bot.catalog import SCREEN_WORLD_BOSS
from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowEvent, FlowStatus
from bot.preconditions import EnsureOutcome, EnsureResult
from bot.world_boss_flow import WorldBossFlowResult
from tools.smoke_session_composition import (
    CHARACTER_COUNT,
    _flow_summary,
    _summary,
    parse_args,
)


def test_harness_is_fixed_to_two_characters_and_requires_execute():
    args = parse_args(["world-boss"])

    assert CHARACTER_COUNT == 2
    assert not args.execute


def test_world_boss_summary_preserves_business_outcome_and_retries():
    result = WorldBossFlowResult(
        status=FlowStatus.COMPLETED,
        events=(FlowEvent("world_boss.inventory_full"),),
        sapphires=10,
        inventory_full=True,
        transition_attempts=(("world_boss.start", 2, 1),),
    )

    summary = _flow_summary("world_boss", result)

    assert summary["outcome"] == "inventory_full"
    assert summary["events"] == ["world_boss.inventory_full"]
    assert summary["transition_attempts"] == [["world_boss.start", 2, 1]]


def test_session_summary_reports_world_boss_rotation_without_normalization():
    requirement = ComponentRequirement.capability("quick_menu_accessible")
    ensure = EnsureResult(
        EnsureOutcome.ALREADY_SATISFIED,
        requirement,
        SCREEN_WORLD_BOSS,
        SCREEN_WORLD_BOSS,
    )
    session = SimpleNamespace(
        status=SimpleNamespace(value="completed"),
        characters_processed=0,
        advances_completed=0,
        events=(),
        character_results=(),
        failure_character_index=None,
        failure_flow=None,
        failure_cause=None,
    )

    summary = _summary("world-boss", session, (), [ensure])

    assert summary["world_boss_rotation_count"] == 1
    assert summary["normalizations"] == 0
