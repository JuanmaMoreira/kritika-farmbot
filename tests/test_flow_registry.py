import pytest

from bot.black_market_flow import BlackMarketFlow
from bot.daily_quests_flow import DailyQuestsFlow
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.flow_contracts import FlowScope
from bot.mailbox_flow import MailboxFlow
from bot.world_boss_flow import WorldBossFlow


def test_default_registry_is_explicit_and_preserves_selection_order():
    registry = DEFAULT_FLOW_REGISTRY

    assert [item.id for item in registry.definitions] == [
        "black_market",
        "world_boss",
        "daily_quests",
        "mailbox",
    ]
    assert [item.id for item in registry.select(["world_boss", "black_market"])] == [
        "world_boss",
        "black_market",
    ]


def test_registry_metadata_matches_productive_flow_contracts():
    black_market = DEFAULT_FLOW_REGISTRY.get("black_market")
    world_boss = DEFAULT_FLOW_REGISTRY.get("world_boss")
    daily_quests = DEFAULT_FLOW_REGISTRY.get("daily_quests")
    mailbox = DEFAULT_FLOW_REGISTRY.get("mailbox")

    assert black_market.display_name == "Black Market"
    assert black_market.scope is FlowScope.PER_CHARACTER
    assert black_market.contract == BlackMarketFlow.contract
    assert world_boss.display_name == "World Boss"
    assert world_boss.contract == WorldBossFlow.contract
    assert daily_quests.display_name == "Daily Quests"
    assert daily_quests.scope is FlowScope.PER_CHARACTER
    assert daily_quests.contract == DailyQuestsFlow.contract
    assert mailbox.display_name == "Mailbox"
    assert mailbox.scope is FlowScope.PER_CHARACTER
    assert mailbox.contract == MailboxFlow.contract


def test_registry_rejects_unknown_and_empty_selection():
    with pytest.raises(KeyError, match="unknown flow 'missing'"):
        DEFAULT_FLOW_REGISTRY.get("missing")
    with pytest.raises(ValueError, match="at least one"):
        DEFAULT_FLOW_REGISTRY.select([])
