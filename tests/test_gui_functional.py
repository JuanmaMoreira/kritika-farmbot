from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from bot.event_log import RuntimeEventStream
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.gui_controller import GuiExecutionResult, GuiRunStatus, GuiRuntimeController
from bot.gui_evidence import locate_evidence, report_evidence_refs
from bot.gui_model import FlowSelectionModel, GuiExecutionRequest, GuiRunMode
from bot.productive_runtime import CancellationToken, ProductiveRuntime
from bot.runtime_observer import RuntimeWaitCancelled
from bot.session import SessionResult, SessionStatus
from bot.session_report import build_session_report, render_session_report
from tests.test_gui_entrypoint import build_gui_shell, Var


def runtime_for_test(monkeypatch, outcomes=(), *, pre=True, post=True):
    runtime = ProductiveRuntime(
        config=object(), observer=object(), actions=object(), facts=object(),
        auto_battle=object(), socket_relief=object(), equipment_combine_relief=object(),
        pet_summon_space_relief=object(), events=RuntimeEventStream(), cancel_token=CancellationToken(),
    )
    trace = []
    outcomes = iter(outcomes)

    def build(definition):
        def run():
            trace.append(("input", definition.id))
            outcome = next(outcomes)
            if callable(outcome):
                outcome = outcome(runtime)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return SimpleNamespace(name=definition.id, contract=definition.contract, run=run)

    def ensure(requirement):
        trace.append(("pre", requirement))
        return SimpleNamespace(succeeded=pre, error=None)

    def verify(requirements):
        trace.append(("post", requirements))
        return post

    monkeypatch.setattr(runtime, "build_flow", build)
    monkeypatch.setattr(runtime, "build_preconditions", lambda: SimpleNamespace(
        ensure=ensure, current_satisfies_any=verify,
    ))
    monkeypatch.setattr(runtime, "build_rotation", Mock(side_effect=AssertionError("Rotation forbidden")))
    monkeypatch.setattr(runtime, "run_session", Mock(side_effect=AssertionError("Session forbidden")))
    return runtime, trace


OK = FlowResult(FlowStatus.COMPLETED, (FlowEvent("noop"),))


@pytest.mark.parametrize("ids", [("mailbox",), ("mailbox", "send_stamina", "black_market")])
def test_selected_flows_match_standalone_contract_and_input_trace(monkeypatch, ids):
    definitions = DEFAULT_FLOW_REGISTRY.select(ids)
    runtime, trace = runtime_for_test(monkeypatch, [OK] * len(ids))
    aggregate = runtime.run_flows_once(definitions)
    baseline, baseline_trace = runtime_for_test(monkeypatch, [OK] * len(ids))
    for definition in definitions:
        baseline.run_flow(definition)
    assert trace == baseline_trace
    assert [value for kind, value in trace if kind == "input"] == list(ids)
    assert aggregate.status is FlowStatus.COMPLETED
    assert aggregate.flow_results == (OK,) * len(ids)
    assert aggregate.flows_completed == aggregate.business_event_count == len(ids)
    runtime.build_rotation.assert_not_called()
    runtime.run_session.assert_not_called()


@pytest.mark.parametrize("terminal", [FlowResult(FlowStatus.FAILED, error="failed"), FlowResult(FlowStatus.CANCELLED), ValueError("broken")])
def test_intermediate_terminal_preserves_partial_results_and_stops(monkeypatch, terminal):
    runtime, trace = runtime_for_test(monkeypatch, [OK, terminal, OK])
    result = runtime.run_flows_once(DEFAULT_FLOW_REGISTRY.definitions[:3])
    assert result.flows_completed == 1
    assert result.business_event_count == 1
    assert len(result.flow_results) == 2
    assert len([entry for entry in trace if entry[0] == "input"]) == 2
    assert result.status is (FlowStatus.CANCELLED if isinstance(terminal, FlowResult) and terminal.status is FlowStatus.CANCELLED else FlowStatus.FAILED)
    if result.status is FlowStatus.FAILED:
        assert result.failure is result.flow_results[-1].failure


@pytest.mark.parametrize("before", [True, False])
def test_token_cancellation_at_sequence_boundaries(monkeypatch, before):
    def finish_and_stop(runtime):
        runtime.cancel_token.request()
        return OK
    runtime, trace = runtime_for_test(monkeypatch, [finish_and_stop, OK])
    if before:
        runtime.cancel_token.request()
    result = runtime.run_flows_once(DEFAULT_FLOW_REGISTRY.definitions[:2])
    assert result.status is FlowStatus.CANCELLED
    assert result.flows_completed == (0 if before else 1)
    assert result.failure is None
    assert len([entry for entry in trace if entry[0] == "input"]) == result.flows_completed


def test_stop_safely_during_selected_flow_keeps_cancelled_semantics(monkeypatch, tmp_path):
    entered = threading.Event()
    stop = threading.Event()

    def wait_for_stop(runtime):
        entered.set()
        assert stop.wait(3)
        assert runtime.cancel_requested()
        raise RuntimeWaitCancelled("requested")

    runtime, trace = runtime_for_test(monkeypatch, [OK, wait_for_stop, OK])

    @contextmanager
    def factory(**kwargs):
        runtime.cancel_token = kwargs["cancel_token"]
        yield runtime

    controller = GuiRuntimeController(runtime_factory=factory)
    controller.start(GuiExecutionRequest.selected_flows(
        tuple(d.id for d in DEFAULT_FLOW_REGISTRY.definitions[:3]), log_dir=tmp_path,
    ))
    try:
        assert entered.wait(3)
        assert controller.stop_safely()
    finally:
        stop.set()
        assert controller.wait(3)
    result = controller.drain()[-1].result
    assert result.status is GuiRunStatus.CANCELLED
    assert result.flows_completed == 1
    assert result.error is None
    assert result.advances_completed == 0
    assert len([entry for entry in trace if entry[0] == "input"]) == 2


@pytest.mark.parametrize("pre,post,inputs", [(False, True, 0), (True, False, 1)])
def test_selected_flows_stop_on_contract_rejection(monkeypatch, pre, post, inputs):
    runtime, trace = runtime_for_test(monkeypatch, [OK, OK], pre=pre, post=post)
    result = runtime.run_flows_once(DEFAULT_FLOW_REGISTRY.definitions[:2])
    assert result.status is FlowStatus.FAILED
    assert result.flows_completed == 0
    assert len([entry for entry in trace if entry[0] == "input"]) == inputs


def test_empty_selected_flows_rejected_before_work(monkeypatch):
    with pytest.raises(ValueError, match="at least one"):
        GuiExecutionRequest.selected_flows(())
    runtime, trace = runtime_for_test(monkeypatch)
    with pytest.raises(ValueError, match="at least one"):
        runtime.run_flows_once(())
    assert trace == []


def test_gui_selection_through_worker_preserves_order_and_queue_only(monkeypatch, tmp_path):
    selection = FlowSelectionModel()
    selection.move_up("world_boss")
    selection.set_enabled("send_stamina", False)
    runtime, trace = runtime_for_test(monkeypatch, [OK] * len(selection.active_ids))
    threads = []
    cleaned = []

    @contextmanager
    def factory(**kwargs):
        threads.append(threading.get_ident())
        runtime.cancel_token = kwargs["cancel_token"]
        runtime.events.subscribe(kwargs["event_consumers"][0])
        try:
            yield runtime
        finally:
            cleaned.append(True)

    controller = GuiRuntimeController(runtime_factory=factory)
    controller.start(GuiExecutionRequest.selected_flows(selection.active_ids, log_dir=tmp_path))
    assert controller.wait(3)
    messages = controller.drain(limit=200)
    result = messages[-1].result
    assert threads == [controller._thread.ident]
    assert threads[0] != threading.get_ident()
    assert cleaned == [True]
    assert result.status is GuiRunStatus.COMPLETED
    assert result.advances_completed == 0
    assert result.flows_completed == len(selection.active_ids)
    assert result.report is None
    assert [value for kind, value in trace if kind == "input"] == list(selection.active_ids)
    assert sum(message.event is not None for message in messages) > 0


def failed_report(reference):
    return build_session_report(SessionResult(
        SessionStatus.FAILED, 0, 0, (), failure=FailureCause("technical", "failed", evidence_ref=reference),
    ))


def test_finish_displays_existing_renderer_and_preserves_legacy_fields(tmp_path):
    app = build_gui_shell(lambda: 0)
    report = failed_report((tmp_path / "failure.json").as_uri())
    app._active_mode = GuiRunMode.SESSION
    result = GuiExecutionResult(GuiRunStatus.FAILED, 12.5, tmp_path / "run.jsonl", report=report)
    app._finish(result)
    assert app.report_text.text == render_session_report(report)
    assert app.report_text.options["state"] == "disabled"
    assert app.output_tabs.selected is app.report_frame
    assert app.status_var.get() == "Failed"
    assert app.progress.state == "Failed"
    assert app.session_elapsed_var.get() == "00:00:12"
    assert str(result.log_path) in app.log_var.get()
    assert app.evidence_select.options["values"] == (report.failure.evidence_ref,)
    app._finish(replace(result, report=None))
    assert app.report_text.text == "No session report available."
    assert "FAILED" in app.result_var.get()
    assert app.evidence_button.options["state"] == "disabled"


def test_selected_button_uses_enabled_order_and_ignores_characters(tmp_path):
    app = build_gui_shell(lambda: 0)
    app.selection = FlowSelectionModel()
    app.selection.move_up("world_boss")
    app.selection.set_enabled("mailbox", False)
    app.debug_var = Var(False)
    app.characters_var = Var("invalid for a session")
    app.dotenv_path = tmp_path / ".env"
    app.log_dir = tmp_path
    app._run_selected_flows()
    request = app.controller.requests[0]
    assert request.mode is GuiRunMode.SELECTED_FLOWS
    assert request.flow_ids == app.selection.active_ids
    assert request.character_count == 1
    assert not app.session_timer.running


def test_existing_evidence_is_located_only_on_explicit_action(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle with spaces # á"
    bundle.mkdir()
    path = bundle / "failure.json"
    path.write_text("{}")
    opened = []
    ref = path.as_uri()
    app = build_gui_shell(lambda: 0)
    monkeypatch.setattr("tools.gui.locate_evidence", lambda value: locate_evidence(value, opener=opened.append))
    app._show_report(failed_report(ref))
    assert opened == []
    app._locate_evidence()
    assert opened == [bundle.resolve()]
    path.unlink()
    app._locate_evidence()
    assert opened == [bundle.resolve()]
    assert "unavailable" in app.evidence_status_var.get()


@pytest.mark.parametrize("ref", ["file:///missing/failure.json", "https://example.org/failure.json", "file://server/share/failure.json", "file:relative/failure.json", "file:////server/share/failure.json", "file:///bad%00/failure.json"])
def test_unavailable_or_nonlocal_evidence_does_not_open_or_raise(ref):
    opener = Mock()
    assert "unavailable" in locate_evidence(ref, opener=opener)
    opener.assert_not_called()


def test_evidence_opener_failure_is_nonfatal(tmp_path):
    path = tmp_path / "failure.json"
    path.write_text("{}")
    assert "unavailable" in locate_evidence(path.as_uri(), opener=Mock(side_effect=OSError("gone")))


def test_evidence_refs_are_deduplicated_and_only_technical():
    report = failed_report("file:///expired/failure.json")
    assert report_evidence_refs(report) == (report.failure.evidence_ref,)
    from bot.session_report import ReportStatus
    assert report_evidence_refs(replace(report, status=ReportStatus.CANCELLED)) == ()
    assert report_evidence_refs(None) == ()


def test_queue_drain_renders_report_on_ui_thread_and_keeps_progress(tmp_path):
    from bot.gui_controller import GuiMessageKind, GuiWorkerMessage
    app = build_gui_shell(lambda: 0)
    app.selection = FlowSelectionModel()
    app._close_when_idle = False
    app._active_mode = GuiRunMode.SESSION
    app._append_console = Mock()
    events = []
    stream = RuntimeEventStream(consumers=(events.append,))
    stream.record("session.character.started", character_index=1, character_count=2)
    stream.record("flow.started", flow="world_boss")
    stream.record("flow.completed", flow="world_boss")
    report = failed_report((tmp_path / "failure.json").as_uri())
    result = GuiExecutionResult(GuiRunStatus.FAILED, 3.0, tmp_path / "run.jsonl", report=report)
    messages = tuple(GuiWorkerMessage(GuiMessageKind.EVENT, event=e) for e in events) + (
        GuiWorkerMessage(GuiMessageKind.RESULT, result=result),
    )
    app.controller.drain = Mock(return_value=messages)
    app._drain_worker()
    assert app.report_text.text == render_session_report(report)
    assert app.character_var.get() == "1 / 2"
    assert app.flow_var.get() == "World Boss"
    assert app.progress.flows_completed == 1
    assert app.state_var.get() == "Failed"
    assert app.session_elapsed_var.get() == "00:00:03"
    app.controller.drain.assert_called_once_with(limit=250)


def test_report_uses_supplied_character_label_without_identity_policy():
    from bot.session_report import CharacterReport, ReportStatus
    report = failed_report("file:///expired/failure.json")
    report = replace(report, characters=(CharacterReport(
        1, "Kaiserin", ReportStatus.TECHNICAL_FAILURE, (), False,
    ),))
    app = build_gui_shell(lambda: 0)
    app._show_report(report)
    assert "Kaiserin" in app.report_text.text
