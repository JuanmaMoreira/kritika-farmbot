"""Exercise the productive routine/manual boundary with semantic device doubles."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.catalog import MENU_QUICK, SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY
from bot.event_log import RuntimeEventStream
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.gui_model import GuiProgress
from bot.preconditions import MinimalPreconditionEnsurer
from bot.runtime_observer import RuntimeWaitTimeout
from bot.session import SessionStatus
from bot.session_report import ReportStatus, build_session_report
from bot.state import ResolutionStatus
from test_productive_runtime import _runtime
from test_session import Flow, Rotation
from test_world_boss_eligibility import card
from test_world_boss_flow import snapshot


def composed_runtime(monkeypatch, *, active=False, signal_status=ResolutionStatus.RESOLVED):
    trace, events = [], []

    class Observer:
        sequence = 0
        base = SCREEN_LOBBY

        def observe(self):
            self.sequence += 1
            if self.base == SCREEN_BATTLE_MODE_SELECT:
                return card(self.sequence, active, status=signal_status)
            if self.base == MENU_QUICK:
                return snapshot(self.sequence, overlays=(MENU_QUICK,))
            return snapshot(self.sequence, base=self.base)

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
                             "SelectQuickMenuLobby": SCREEN_LOBBY}[kind]
            final = observer.wait_until(kwargs["expected"], after_sequence=before.sequence,
                                        timeout=6, stable_for=kwargs.get("stable_for", 0))
            return SimpleNamespace(succeeded=True, final_snapshot=final)

    monkeypatch.setattr(runtime, "build_verified_transition", lambda: Transition())
    monkeypatch.setattr(runtime, "build_flow", lambda definition: Flow(
        definition.id, [FlowResult(FlowStatus.COMPLETED)] * 3, trace))
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
    definitions = DEFAULT_FLOW_REGISTRY.definitions
    if manual:
        result = runtime.run_flows_once(definitions)
        assert result.status is FlowStatus.COMPLETED
        assert trace == [f"{d.id}.run" for d in definitions]
        builder.assert_not_called()
        assert not any(e.event == "flow.skipped_not_eligible" for e in events)
    else:
        result = runtime.run_session(definitions, character_count=2)
        builder.assert_called_once_with()
        assert result.status is SessionStatus.COMPLETED
        expected = ["black_market.run", "OpenBattleModeSelect", "OpenQuickMenu", "SelectQuickMenuLobby"]
        expected += [f"{d.id}.run" for d in definitions[1:] if active or d.id != "world_boss"]
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
    assert trace == ["world_boss.run"]
    builder.assert_not_called()


@pytest.mark.parametrize("status", [ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS])
def test_unconfirmed_daily_in_productive_session_is_technical_without_return_or_flow(monkeypatch, status):
    runtime, trace, events, _ = composed_runtime(monkeypatch, signal_status=status)
    result = runtime.run_session((DEFAULT_FLOW_REGISTRY.get("world_boss"),), character_count=1)
    assert result.status is SessionStatus.FAILED
    assert trace == ["OpenBattleModeSelect"]
    assert result.failure is not None
    assert not any(e.event in {"flow.started", "flow.skipped_not_eligible"} for e in events)


def test_no_daily_policy_for_other_flows(monkeypatch):
    runtime, trace, _, builder = composed_runtime(monkeypatch)
    definitions = tuple(d for d in DEFAULT_FLOW_REGISTRY.definitions if d.id != "world_boss")
    result = runtime.run_session(definitions, character_count=1)
    assert result.status is SessionStatus.COMPLETED
    assert trace == [f"{d.id}.run" for d in definitions] + ["rotation.advance"]
    builder.assert_not_called()


def test_return_operation_rejects_unknown_before_any_input(monkeypatch):
    runtime, trace, _, _ = composed_runtime(monkeypatch)
    with pytest.raises(ValueError, match="confirmed Battle Mode Select"):
        runtime._return_world_boss_eligibility_to_lobby(snapshot(1))
    assert trace == []


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
                return SimpleNamespace(succeeded=False, final_snapshot=before,
                                       error="return failed", failure=failure)
            return real_builder().execute(name, action, before, **kwargs)

    monkeypatch.setattr(runtime, "build_verified_transition", FailingTransition)
    result = runtime.run_session((DEFAULT_FLOW_REGISTRY.get("world_boss"),), character_count=1)
    assert result.status is SessionStatus.FAILED
    assert result.failure == failure
    assert not any(name.endswith(".run") or name == "rotation.advance" for name in trace)
    assert not any(e.event in {"flow.started", "flow.skipped_not_eligible"} for e in events)
