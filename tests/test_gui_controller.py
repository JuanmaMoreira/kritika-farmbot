import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.event_log import EventLevel, RuntimeEvent
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.gui_controller import GuiMessageKind, GuiRunStatus, GuiRuntimeController
from bot.gui_model import GuiExecutionRequest
from bot.session import SessionResult, SessionStatus


class FakeRuntime:
    def __init__(self, *, flow_result=None, session_result=None):
        self.flow_result = flow_result
        self.session_result = session_result
        self.flow_call = None
        self.session_call = None

    def run_flow(self, definition):
        self.flow_call = definition
        return self.flow_result

    def run_session(self, definitions, *, character_count):
        self.session_call = (definitions, character_count)
        return self.session_result


def runtime_factory(runtime, calls, *, event=None):
    @contextmanager
    def factory(**kwargs):
        calls.append(kwargs)
        if event is not None:
            for consumer in kwargs["event_consumers"]:
                consumer(event)
        yield runtime
    return factory


def fixed_log_path(kind, *, directory):
    return Path(directory) / f"{kind}.log"


def wait_and_drain(controller):
    assert controller.wait(2)
    return controller.drain(limit=100)


def test_flow_once_uses_productive_runtime_and_queues_event_then_completed_result(tmp_path):
    calls = []
    event = RuntimeEvent(
        datetime.now(timezone.utc), EventLevel.INFO, "black_market", "flow.started", {"flow": "black_market"}
    )
    runtime = FakeRuntime(
        flow_result=FlowResult(FlowStatus.COMPLETED, events=(FlowEvent("low_gold"),))
    )
    controller = GuiRuntimeController(
        runtime_factory=runtime_factory(runtime, calls, event=event),
        log_path_factory=fixed_log_path,
    )

    controller.start(GuiExecutionRequest.flow_once(
        ("black_market",), debug=True, log_dir=tmp_path
    ))
    messages = wait_and_drain(controller)

    assert runtime.flow_call.id == "black_market"
    assert [item.kind for item in messages] == [GuiMessageKind.EVENT, GuiMessageKind.RESULT]
    result = messages[-1].result
    assert result.status is GuiRunStatus.COMPLETED
    assert result.flows_completed == 1
    assert result.business_event_count == 1
    assert result.log_path == tmp_path / "flow_black_market.log"
    assert calls[0]["console"] is None
    assert calls[0]["debug"] is True


def test_session_preserves_flow_order_and_character_count(tmp_path):
    runtime = FakeRuntime(
        session_result=SessionResult(SessionStatus.COMPLETED, 2, 2, ())
    )
    controller = GuiRuntimeController(
        runtime_factory=runtime_factory(runtime, []),
        log_path_factory=fixed_log_path,
    )

    controller.start(GuiExecutionRequest.session(
        ("world_boss", "black_market"), 2, log_dir=tmp_path
    ))
    messages = wait_and_drain(controller)

    definitions, count = runtime.session_call
    assert [item.id for item in definitions] == ["world_boss", "black_market"]
    assert count == 2
    assert messages[-1].result.advances_completed == 2


def test_concurrent_execution_is_rejected_and_stop_requests_shared_token(tmp_path):
    entered = threading.Event()

    class BlockingRuntime:
        def run_flow(self, definition):
            entered.set()
            while not self.cancel_token.is_requested():
                time.sleep(0.001)
            return FlowResult(FlowStatus.CANCELLED)

    @contextmanager
    def factory(**kwargs):
        runtime = BlockingRuntime()
        runtime.cancel_token = kwargs["cancel_token"]
        yield runtime

    controller = GuiRuntimeController(runtime_factory=factory, log_path_factory=fixed_log_path)
    request = GuiExecutionRequest.flow_once(("black_market",), log_dir=tmp_path)
    controller.start(request)
    assert entered.wait(1)

    with pytest.raises(RuntimeError, match="already active"):
        controller.start(request)
    assert controller.stop_safely()
    assert controller.status is GuiRunStatus.STOPPING
    messages = wait_and_drain(controller)
    assert messages[-1].result.status is GuiRunStatus.CANCELLED
    assert not controller.stop_safely()


@pytest.mark.parametrize(
    ("flow_status", "expected"),
    (
        (FlowStatus.FAILED, GuiRunStatus.FAILED),
        (FlowStatus.CANCELLED, GuiRunStatus.CANCELLED),
    ),
)
def test_failed_and_cancelled_results_are_visible(flow_status, expected, tmp_path):
    runtime = FakeRuntime(flow_result=FlowResult(flow_status, error="cause" if flow_status is FlowStatus.FAILED else None))
    controller = GuiRuntimeController(
        runtime_factory=runtime_factory(runtime, []),
        log_path_factory=fixed_log_path,
    )

    controller.start(GuiExecutionRequest.flow_once(("black_market",), log_dir=tmp_path))
    result = wait_and_drain(controller)[-1].result

    assert result.status is expected
    assert result.log_path == tmp_path / "flow_black_market.log"


def test_runtime_error_becomes_failed_result_without_raw_worker_exception(tmp_path):
    @contextmanager
    def factory(**kwargs):
        raise ValueError("bad config")
        yield

    controller = GuiRuntimeController(runtime_factory=factory, log_path_factory=fixed_log_path)
    controller.start(GuiExecutionRequest.flow_once(("black_market",), log_dir=tmp_path))

    result = wait_and_drain(controller)[-1].result

    assert result.status is GuiRunStatus.FAILED
    assert result.error == "ValueError: bad config"


def test_controller_has_no_tk_dependency_and_worker_only_enqueues():
    source = Path("bot/gui_controller.py").read_text(encoding="utf-8")
    assert "tkinter" not in source
    assert ".configure(" not in source
    assert ".insert(" not in source
