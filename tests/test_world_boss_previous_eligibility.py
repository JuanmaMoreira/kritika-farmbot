"""Previous Rewards proves current-cycle NO before a later header OCR miss."""
from unittest.mock import Mock

import pytest

from bot.catalog import POPUP_WORLD_BOSS_PREVIOUS_REWARDS, SCREEN_WORLD_BOSS, SCREEN_LOBBY, SCREEN_WORLD_BOSS_BATTLE
from bot.flow_contracts import FlowStatus
from bot.runtime_observer import RuntimeWaitCancelled
from bot.verified_transition import VerifiedTransitionOutcome
from bot.world_boss_state import (
    WorldBossEligibilityPolicy, WorldBossPanel, WorldBossStateReader,
)
from tests.test_world_boss_flow import build_flow, happy_inputs, fact_result, auto_result


@pytest.mark.parametrize('previous', [False, True])
def test_unknown_header_uses_only_verified_previous_rewards(previous):
    waits, observes, transitions = happy_inputs(previous=previous)
    reader = Mock()
    def read(snapshot):
        if POPUP_WORLD_BOSS_PREVIOUS_REWARDS in snapshot.state.overlays:
            # Use the production non-OCR evidence for this acquired popup.
            return WorldBossStateReader(Mock()).read(snapshot)
        return WorldBossPanel(None, None)
    reader.read.side_effect = read
    policy = WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED', reader=reader)
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result('resource.sapphires', 247, 1, SCREEN_LOBBY),
        timer_read=fact_result('battle.timer_remaining', 20, 9, SCREEN_WORLD_BOSS_BATTLE),
        auto=Mock(ensure_on_quick=Mock(return_value=auto_result())),
        waits=waits, observes=observes, transitions=transitions)
    flow.eligibility_policy = flow.activity.eligibility_policy = policy
    result = flow.run()
    names = [call[0] for call in driver.calls]
    assert names.count('world_boss.ack_previous_rewards') == int(previous)
    if previous:
        assert result.status is FlowStatus.COMPLETED
        assert result.raid_complete_detected
        assert [call[0] for call in driver.calls].count('world_boss.start') == 1
        assert reader.read.call_args.args[0].state.base_context == SCREEN_WORLD_BOSS
    else:
        assert result.status is FlowStatus.MANUAL_RESOLUTION
        assert result.event_count('world_boss.participation_unknown') == 1
        assert 'world_boss.start' not in [call[0] for call in driver.calls]


def test_explicit_main_no_work_still_overrides_previous_rewards():
    waits, observes, transitions = happy_inputs(previous=True)
    transitions = transitions[:4]  # No Start/Raid on this branch; close to Lobby.
    policy = WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED', reader=Mock())
    policy.reader.read.side_effect = [WorldBossPanel(False, True), WorldBossPanel(True, False)]
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result('resource.sapphires', 247, 1, SCREEN_LOBBY),
        waits=waits, observes=observes, transitions=transitions)
    flow.eligibility_policy = flow.activity.eligibility_policy = policy
    result = flow.run()
    assert result.status is FlowStatus.COMPLETED
    assert result.event_count('world_boss.current_cycle_no_work') == 1
    assert 'world_boss.start' not in [call[0] for call in driver.calls]


@pytest.mark.parametrize('cancelled', [False, True])
def test_previous_decision_cannot_bypass_failed_or_cancelled_ack(cancelled):
    waits, observes, transitions = happy_inputs(previous=True)
    reader = Mock(read=Mock(return_value=WorldBossPanel(False, True)))
    policy = WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED', reader=reader)
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result('resource.sapphires', 247, 1, SCREEN_LOBBY),
        waits=waits, observes=observes, transitions=transitions)
    flow.eligibility_policy = flow.activity.eligibility_policy = policy
    execute = driver.execute

    def guarded(name, *args, **kwargs):
        if name == 'world_boss.ack_previous_rewards' and cancelled:
            driver.calls.append((name,))
            raise RuntimeWaitCancelled('cancelled during acknowledgment')
        return execute(name, *args, **kwargs)

    driver.execute = guarded
    if not cancelled:
        driver.outcomes = [VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT] * 3 + [VerifiedTransitionOutcome.TIMEOUT]
    result = flow.run()
    assert result.status is (FlowStatus.CANCELLED if cancelled else FlowStatus.FAILED)
    names = [call[0] for call in driver.calls]
    assert names.count('world_boss.ack_previous_rewards') == 1
    assert 'world_boss.start' not in names


def test_uncredited_previous_inspection_does_not_authorize_start():
    waits, observes, transitions = happy_inputs(previous=True)
    policy = WorldBossEligibilityPolicy('CURRENT_WB_NOT_PARTICIPATED', reader=None)
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result('resource.sapphires', 247, 1, SCREEN_LOBBY),
        waits=waits, observes=observes, transitions=transitions)
    flow.eligibility_policy = flow.activity.eligibility_policy = policy
    assert flow.run().status is FlowStatus.MANUAL_RESOLUTION
    assert 'world_boss.start' not in [call[0] for call in driver.calls]
