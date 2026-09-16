"""Exercise the productive routine/manual boundary with semantic device doubles."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.catalog import (
    MENU_QUICK, SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE, OVERLAY_WORLD_BOSS_SELECT_BOSS, OVERLAY_WORLD_BOSS_RAID_COMPLETE,
)
from bot.auto_battle import EnsureAutoBattleStatus
from bot.world_boss_flow import WorldBossFlow
from bot.verified_transition import VerifiedTransitionResult, VerifiedTransitionOutcome
from test_world_boss_flow import fact_result

WB_GAMEPLAY = ["OpenWorldBossSelector", "SelectAvailableWorldBoss", "StartWorldBossBattle",
               "auto_battle", "ContinueAfterWorldBossRaid", "ExitWorldBoss"]
WB_STANDALONE = ["sapphires", "OpenBattleModeSelect", *WB_GAMEPLAY,
                 "OpenQuickMenu", "SelectQuickMenuLobby"]
from bot.event_log import RuntimeEventStream
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.gui_model import GuiProgress
from bot.preconditions import MinimalPreconditionEnsurer
from bot.runtime_observer import RuntimeWaitTimeout
from bot.session import SessionStatus
from bot.eligibility import EligibilityStatus
from bot.session_report import ReportStatus, build_session_report
from bot.state import ResolutionStatus
from test_productive_runtime import _runtime
from test_session import Flow, Rotation
from test_world_boss_eligibility import card
from test_world_boss_flow import snapshot


def composed_runtime(monkeypatch, *, active=False, signal_status=ResolutionStatus.RESOLVED, sapphires=20):
    trace, events = [], []

    class Observer:
        sequence = 0
        base = SCREEN_LOBBY
        overlays = ()

        def observe(self):
            self.sequence += 1
            if self.base == SCREEN_BATTLE_MODE_SELECT:
                return card(self.sequence, active, status=signal_status)
            if self.base == MENU_QUICK:
                return snapshot(self.sequence, overlays=(MENU_QUICK,))
            return snapshot(self.sequence, base=self.base, overlays=self.overlays)

        def wait_until(self, predicate, **kwargs):
            since = None
            for _ in range(8):
                value = self.observe()
                if value.sequence <= kwargs["after_sequence"]:
                    continue
                if predicate(value):
                    since = value.timestamp if since is None else since
                    if value.timestamp - since >= kwargs.get("stable_for", 0):
                        return value
                else:
                    since = None
            raise RuntimeWaitTimeout(after_sequence=kwargs["after_sequence"],
                                     timeout=kwargs["timeout"], last_snapshot=value)

    observer = Observer()
    runtime = _runtime(observer, RuntimeEventStream(consumers=(events.append,)))

    class Transition:
        def execute(self, name, action, before, **kwargs):
            assert kwargs["precondition"](before)
            assert not kwargs["retryable_from"](snapshot(999))
            kind = type(action).__name__
            trace.append(kind)
            observer.base = {"OpenBattleModeSelect": SCREEN_BATTLE_MODE_SELECT,
                             "OpenQuickMenu": MENU_QUICK,
                             "SelectQuickMenuLobby": SCREEN_LOBBY,
                             "OpenWorldBossSelector": None,
                             "SelectAvailableWorldBoss": SCREEN_WORLD_BOSS,
                             "StartWorldBossBattle": SCREEN_WORLD_BOSS_BATTLE,
                             "ContinueAfterWorldBossRaid": SCREEN_WORLD_BOSS,
                             "ExitWorldBoss": SCREEN_BATTLE_MODE_SELECT}[kind]
            observer.overlays = ((OVERLAY_WORLD_BOSS_SELECT_BOSS,)
                                 if kind == "OpenWorldBossSelector" else ())
            final = observer.wait_until(kwargs["expected"], after_sequence=before.sequence,
                                        timeout=6, stable_for=kwargs.get("stable_for", 0))
            return VerifiedTransitionResult(
                name, VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT, 1, 0,
                final, action_source_snapshot=before,
            )

    monkeypatch.setattr(runtime, "build_verified_transition", lambda: Transition())
    def read_sapphires(**kwargs):
        assert observer.base == SCREEN_LOBBY
        trace.append("sapphires")
        return fact_result("resource.sapphires", sapphires, observer.sequence, SCREEN_LOBBY)

    def auto_battle(**kwargs):
        trace.append("auto_battle")
        observer.overlays = (OVERLAY_WORLD_BOSS_RAID_COMPLETE,)
        return SimpleNamespace(status=EnsureAutoBattleStatus.INTERRUPTED, observations=(), tap_count=0)

    def build_flow(definition):
        if definition.id != "world_boss":
            return Flow(definition.id, [FlowResult(FlowStatus.COMPLETED)] * 3, trace)
        return WorldBossFlow(
            observer, Mock(), Mock(read_sapphires=read_sapphires),
            Mock(ensure_on_quick=auto_battle), runtime.events,
            socket_relief=Mock(), equipment_combine_relief=Mock(),
            verified_transition=runtime.build_verified_transition(),
        )

    monkeypatch.setattr(runtime, "build_flow", build_flow)
    monkeypatch.setattr(runtime, "build_rotation", lambda count: Rotation(count, trace))
    monkeypatch.setattr(runtime, "build_preconditions", lambda: MinimalPreconditionEnsurer(
        lambda: observer.base if observer.base != MENU_QUICK else None))
    builder = Mock(wraps=runtime.build_world_boss_daily_eligibility)
    monkeypatch.setattr(runtime, "build_world_boss_daily_eligibility", builder)
    return runtime, trace, events, builder


@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("manual", [True, False])
def test_productive_session_applies_daily_but_selected_flows_never_do(monkeypatch, active, manual):
    runtime, trace, events, builder = composed_runtime(monkeypatch, active=active)
    # This fixture exercises WB and ordinary flows; real WB/MW composition has
    # its own integration scenarios in test_monster_wave_integration.py.
    definitions = tuple(d for d in DEFAULT_FLOW_REGISTRY.definitions if d.id != 'monster_wave')
    if manual:
        result = runtime.run_flows_once(definitions)
        assert result.status is FlowStatus.COMPLETED
        expected = ["black_market.run", *WB_STANDALONE]
        expected += [f"{d.id}.run" for d in definitions[2:]]
        assert trace == expected
        builder.assert_not_called()
        assert not any(e.event == "flow.skipped_not_eligible" for e in events)
    else:
        result = runtime.run_session(definitions, character_count=2)
        builder.assert_called_once_with()
        assert result.status is SessionStatus.COMPLETED
        expected = ["black_market.run", "sapphires", "OpenBattleModeSelect"]
        expected += WB_GAMEPLAY if active else []
        expected += ["OpenQuickMenu", "SelectQuickMenuLobby"]
        expected += [f"{d.id}.run" for d in definitions[2:]]
        expected.append("rotation.advance")
        assert trace == expected * 2
        report = build_session_report(result)
        assert report.status is ReportStatus.COMPLETE
        assert report.counts.technical_failure == report.counts.business_incomplete == 0
        assert result.advances_completed == 2
        skips = [e for e in events if e.event == "flow.skipped_not_eligible"]
        assert len(skips) == (0 if active else 2)
        assert all(e.fields["event_role"] == "lifecycle" for e in skips)
        progress = GuiProgress()
        for event in events:
            progress.apply(event)
        assert progress.flows_completed == (14 if active else 12)
        assert report.flows_completed == progress.flows_completed
        assert result.flow_names == tuple(d.id for d in definitions)


def test_flow_once_remains_manual_even_with_world_boss_daily_check_available(monkeypatch):
    runtime, trace, _, builder = composed_runtime(monkeypatch)
    result = runtime.run_flow(DEFAULT_FLOW_REGISTRY.get("world_boss"))
    assert result.status is FlowStatus.COMPLETED
    assert trace == WB_STANDALONE
    builder.assert_not_called()


@pytest.mark.parametrize("status", [ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS])
def test_unconfirmed_daily_in_productive_session_is_technical_without_return_or_flow(monkeypatch, status):
    runtime, trace, events, _ = composed_runtime(monkeypatch, signal_status=status)
    result = runtime.run_session((DEFAULT_FLOW_REGISTRY.get("world_boss"),), character_count=1)
    assert result.status is SessionStatus.FAILED
    assert trace == ["sapphires", "OpenBattleModeSelect"]
    assert result.failure is not None
    assert not any(e.event in {"flow.started", "flow.skipped_not_eligible"} for e in events)


def test_no_daily_policy_for_other_flows(monkeypatch):
    runtime, trace, _, builder = composed_runtime(monkeypatch)
    definitions = tuple(d for d in DEFAULT_FLOW_REGISTRY.definitions if d.id not in {"world_boss", "monster_wave"})
    result = runtime.run_session(definitions, character_count=1)
    assert result.status is SessionStatus.COMPLETED
    assert trace == [f"{d.id}.run" for d in definitions] + ["rotation.advance"]
    builder.assert_not_called()


@pytest.mark.parametrize("failed_action", ["OpenQuickMenu", "SelectQuickMenuLobby"])
def test_return_failure_never_commits_skip_or_starts_world_boss(monkeypatch, failed_action):
    from bot.failure_cause import FailureCause
    failure = FailureCause("transition", "return failed", evidence_ref="file:///return-evidence")
    runtime, trace, events, _ = composed_runtime(monkeypatch)
    real_builder = runtime.build_verified_transition

    class FailingTransition:
        def execute(self, name, action, before, **kwargs):
            if type(action).__name__ == failed_action:
                trace.append(failed_action)
                return VerifiedTransitionResult(name, VerifiedTransitionOutcome.FAILED, 1, 0,
                                                before, error="return failed", failure=failure)
            return real_builder().execute(name, action, before, **kwargs)

    monkeypatch.setattr(runtime, "build_verified_transition", FailingTransition)
    result = runtime.run_session((DEFAULT_FLOW_REGISTRY.get("world_boss"),), character_count=1)
    assert result.status is SessionStatus.FAILED
    assert result.failure == failure
    assert not any(name.endswith(".run") or name == "rotation.advance" for name in trace)
    assert not any(e.event in {"flow.started", "flow.skipped_not_eligible"} for e in events)


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("sapphires", [4, 20])
def test_daily_eligibility_precedes_resource_outcome_and_report(monkeypatch, active, sapphires):
    runtime, trace, events, _ = composed_runtime(monkeypatch, active=active, sapphires=sapphires)
    result = runtime.run_session((DEFAULT_FLOW_REGISTRY.get("world_boss"),), character_count=1)
    assert result.status is SessionStatus.COMPLETED
    played = active and sapphires >= 5
    expected = ["sapphires", "OpenBattleModeSelect"]
    expected += WB_GAMEPLAY if played else []
    expected += ["OpenQuickMenu", "SelectQuickMenuLobby", "rotation.advance"]
    assert trace == expected
    raw = result.character_results[0].flow_results[0]
    assert raw.status is (FlowStatus.COMPLETED if active else FlowStatus.SKIPPED_NOT_ELIGIBLE)
    blocked = active and sapphires < 5
    assert raw.event_count("world_boss.insufficient_sapphires") == int(blocked)
    assert sum(e.event == "world_boss.insufficient_sapphires" for e in events) == int(blocked)
    assert raw.raid_complete_detected if played else "StartWorldBossBattle" not in trace
    report = build_session_report(result)
    expected_flow = (ReportStatus.SKIPPED_NOT_ELIGIBLE if not active else
                     ReportStatus.BUSINESS_INCOMPLETE if blocked else ReportStatus.COMPLETE)
    assert report.characters[0].flows[0].status is expected_flow
    assert report.status is (ReportStatus.BUSINESS_INCOMPLETE if blocked else ReportStatus.COMPLETE)
    assert report.counts.business_incomplete == int(blocked)
    assert report.counts.technical_failure == 0


@pytest.mark.parametrize("signal", [ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS, "failure"])
def test_inconclusive_daily_overrides_low_sapphires_after_verified_entry(monkeypatch, signal):
    runtime, trace, events, _ = composed_runtime(monkeypatch, sapphires=4)
    check = runtime.build_world_boss_daily_eligibility()
    evaluate = check.evaluate
    decisions = []

    def unconfirmed():
        runtime.observer.sequence += 1
        if signal == "failure":
            raise OSError("eligibility capture failed")
        return snapshot(runtime.observer.sequence, status=signal)

    def evaluate_after_entry():
        assert runtime.observer.base == SCREEN_BATTLE_MODE_SELECT
        monkeypatch.setattr(runtime.observer, "observe", unconfirmed)
        decision = evaluate()
        decisions.append(decision)
        return decision

    monkeypatch.setattr(check, "evaluate", evaluate_after_entry)
    monkeypatch.setattr(runtime, "build_world_boss_daily_eligibility", lambda: check)
    result = runtime.run_session((DEFAULT_FLOW_REGISTRY.get("world_boss"),), character_count=1)
    assert decisions[0].status is (EligibilityStatus.FAILED if signal == "failure" else EligibilityStatus.UNKNOWN)
    assert result.status is SessionStatus.FAILED
    assert result.failure == decisions[0].failure
    assert trace == ["sapphires", "OpenBattleModeSelect"]
    assert not any(e.event in {"world_boss.insufficient_sapphires", "flow.started",
                              "flow.skipped_not_eligible"} for e in events)
    report = build_session_report(result)
    assert report.status is ReportStatus.TECHNICAL_FAILURE
    assert report.counts.business_incomplete == 0


def test_selected_standalone_low_sapphires_still_avoids_zone(monkeypatch):
    runtime, trace, events, builder = composed_runtime(monkeypatch, active=False, sapphires=4)
    result = runtime.run_flows_once((DEFAULT_FLOW_REGISTRY.get("world_boss"),))
    assert result.status is FlowStatus.COMPLETED
    assert trace == ["sapphires"]
    builder.assert_not_called()
    assert sum(e.event == "world_boss.insufficient_sapphires" for e in events) == 1
