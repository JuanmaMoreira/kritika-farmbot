"""Prepared-zone composition with real WB and an unrelated second activity."""

from unittest.mock import Mock

import pytest

from bot.battle_mode_zone import is_battle_mode_select
from bot.catalog import SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, SCREEN_WORLD_BOSS
from bot.eligibility import EligibilityResult, EligibilityStatus
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.prepared_activity import PreparedActivity
from bot.session import SessionPlan, SessionRunner, SessionStatus
from bot.state import ResolutionStatus
from bot.runtime_observer import RuntimeWaitCancelled
from bot.world_boss_flow import WorldBossFlowResult
from bot.verified_transition import VerifiedTransitionResult, VerifiedTransitionOutcome
from test_eligibility_integration import composed_runtime, WB_GAMEPLAY, WB_STANDALONE
from test_session import Flow, Rotation


def setup(monkeypatch, **kwargs):
    runtime, trace, events, _ = composed_runtime(monkeypatch, **kwargs)
    wb = runtime.build_flow(DEFAULT_FLOW_REGISTRY.get("world_boss"))
    def second():
        assert is_battle_mode_select(runtime.observer.observe())
        trace.append("second.activity")
        return FlowResult(FlowStatus.COMPLETED)
    probe = PreparedActivity("second", wb.zone, second)
    return runtime, wb, probe, trace, events


def run(runtime, flows, trace, checks=(), count=1):
    return SessionRunner(
        SessionPlan.standard(flows=tuple(flows), rotation_strategy=Rotation(count, trace),
                             character_count=count, eligibility=checks),
        preconditions=runtime.build_preconditions(), events=runtime.events,
    ).run()


@pytest.mark.parametrize("reverse", [False, True])
def test_adjacent_activities_share_one_visit_in_exact_selected_order(monkeypatch, reverse):
    runtime, wb, second, trace, _ = setup(monkeypatch)
    activities = [second, wb.prepared(wb.zone)] if reverse else [wb.prepared(wb.zone), second]
    result = run(runtime, activities, trace, count=2)
    assert result.status is SessionStatus.COMPLETED
    expected = (["OpenBattleModeSelect", "second.activity", *WB_GAMEPLAY] if reverse else
                ["sapphires", "OpenBattleModeSelect", *WB_GAMEPLAY, "second.activity"])
    assert trace == (expected + ["OpenQuickMenu", "SelectQuickMenuLobby", "rotation.advance"]) * 2
    assert result.flow_names == tuple(item.name for item in activities)
    assert all(c.flow_results[0].succeeded and c.flow_results[1].succeeded
               for c in result.character_results)


def test_non_adjacent_selection_closes_and_reopens_without_reorder(monkeypatch):
    runtime, wb, second, trace, _ = setup(monkeypatch)
    ordinary = Flow("ordinary", [FlowResult(FlowStatus.COMPLETED)], trace)
    result = run(runtime, [wb.prepared(wb.zone), ordinary, second], trace)
    assert result.status is SessionStatus.COMPLETED
    assert trace == [*WB_STANDALONE, "ordinary.run", "OpenBattleModeSelect",
                     "second.activity", "OpenQuickMenu", "SelectQuickMenuLobby", "rotation.advance"]


@pytest.mark.parametrize("skip_position", [0, 1])
def test_skips_keep_zone_until_last_selected_position(monkeypatch, skip_position):
    runtime, wb, second, trace, events = setup(monkeypatch)
    checks = [None, None]
    checks[skip_position] = Mock(evaluate=Mock(return_value=EligibilityResult(
        EligibilityStatus.NOT_ELIGIBLE, "selected card absent")))
    result = run(runtime, [wb.prepared(wb.zone), second], trace, tuple(checks))
    assert result.status is SessionStatus.COMPLETED
    assert trace.count("OpenBattleModeSelect") == trace.count("SelectQuickMenuLobby") == 1
    assert ("StartWorldBossBattle" in trace) is (skip_position != 0)
    assert ("second.activity" in trace) is (skip_position != 1)
    assert result.character_results[0].flow_results[skip_position].status is FlowStatus.SKIPPED_NOT_ELIGIBLE
    assert sum(e.event == "flow.skipped_not_eligible" for e in events) == 1


@pytest.mark.parametrize("active", [False, True])
def test_low_sapphires_does_not_block_shared_visit_or_second_activity(monkeypatch, active):
    runtime, wb, second, trace, _ = setup(monkeypatch, sapphires=4, active=active)
    check = Mock(wraps=runtime.build_world_boss_daily_eligibility())
    result = run(runtime, [wb.prepared(wb.zone), second], trace, (check, None))
    assert result.status is SessionStatus.COMPLETED
    check.evaluate.assert_called_once_with()
    assert trace == ["sapphires", "OpenBattleModeSelect", "second.activity",
                     "OpenQuickMenu", "SelectQuickMenuLobby", "rotation.advance"]
    first, second_result = result.character_results[0].flow_results
    assert first.event_count("world_boss.insufficient_sapphires") == int(active)
    assert first.status is (FlowStatus.COMPLETED if active else FlowStatus.SKIPPED_NOT_ELIGIBLE)
    assert second_result.succeeded


@pytest.mark.parametrize("base,status", [
    (SCREEN_LOBBY, ResolutionStatus.RESOLVED),
    (SCREEN_WORLD_BOSS, ResolutionStatus.RESOLVED),
    (SCREEN_BATTLE_MODE_SELECT, ResolutionStatus.UNKNOWN),
    (SCREEN_BATTLE_MODE_SELECT, ResolutionStatus.AMBIGUOUS),
])
def test_prepared_activity_requires_verified_hub_without_opening_it(monkeypatch, base, status):
    runtime, wb, _, trace, _ = setup(monkeypatch, signal_status=status)
    runtime.observer.base = base
    result = wb.activity.run()
    assert result.status is FlowStatus.FAILED
    assert trace == []


def test_zone_rejects_unknown_return_without_any_input(monkeypatch):
    runtime, wb, _, trace, _ = setup(monkeypatch, signal_status=ResolutionStatus.UNKNOWN)
    runtime.observer.base = SCREEN_BATTLE_MODE_SELECT
    assert wb.zone.leave().status is FlowStatus.FAILED
    assert trace == []


@pytest.mark.parametrize("stage", ["enter", "leave"])
def test_runner_independently_rejects_false_zone_postconditions(monkeypatch, stage):
    runtime, wb, second, trace, _ = setup(monkeypatch)
    monkeypatch.setattr(wb.zone, stage, lambda: FlowResult(FlowStatus.COMPLETED))
    result = run(runtime, [second], trace)
    assert result.status is SessionStatus.FAILED
    assert "rotation.advance" not in trace
    assert ("second.activity" in trace) is (stage == "leave")


def test_activity_bad_hub_return_stops_session_without_cleanup_or_rotation(monkeypatch):
    runtime, wb, second, trace, _ = setup(monkeypatch)
    def bad_activity():
        runtime.observer.base = SCREEN_WORLD_BOSS
        return WorldBossFlowResult(FlowStatus.COMPLETED, raid_complete_detected=True)
    second = PreparedActivity("second", wb.zone, bad_activity)
    result = run(runtime, [second], trace)
    assert result.status is SessionStatus.FAILED
    assert trace == ["OpenBattleModeSelect"]
    assert result.failure.type == "postcondition_rejected"
    assert result.character_results[0].flow_results[0].raid_complete_detected


@pytest.mark.parametrize("error", [RuntimeWaitCancelled(), OSError("lost frame")])
def test_final_wb_return_exception_preserves_gameplay_result(monkeypatch, error):
    runtime, wb, _, trace, _ = setup(monkeypatch)
    transition = wb.activity.verified_transition
    execute = transition.execute
    def fail_back(name, action, before, **kwargs):
        if type(action).__name__ == "ExitWorldBoss":
            raise error
        return execute(name, action, before, **kwargs)
    monkeypatch.setattr(transition, "execute", fail_back)
    result = wb.run()
    assert result.status is (FlowStatus.CANCELLED if isinstance(error, RuntimeWaitCancelled)
                             else FlowStatus.FAILED)
    assert result.raid_complete_detected
    assert "OpenQuickMenu" not in trace


def test_cancelled_zone_does_not_open_or_cleanup(monkeypatch):
    runtime, wb, _, trace, _ = setup(monkeypatch)
    monkeypatch.setattr(wb.zone, "cancel_requested", lambda: True)
    assert wb.zone.enter().status is FlowStatus.CANCELLED
    assert wb.zone.leave().status is FlowStatus.CANCELLED
    assert trace == []


def test_unverified_world_boss_back_preserves_failed_transition_and_no_cleanup(monkeypatch):
    runtime, wb, _, trace, _ = setup(monkeypatch)
    transition = wb.activity.verified_transition
    execute = transition.execute
    def reject_back(name, action, before, **kwargs):
        if type(action).__name__ == "ExitWorldBoss":
            return VerifiedTransitionResult(name, VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED,
                                            2, 0, before, error="Back failed")
        return execute(name, action, before, **kwargs)
    monkeypatch.setattr(transition, "execute", reject_back)
    result = wb.run()
    assert result.status is FlowStatus.FAILED
    assert result.raid_complete_detected
    assert result.transition_outcomes[-1] == ("world_boss.return_to_battle_mode", "attempts_exhausted")
    assert "OpenQuickMenu" not in trace
