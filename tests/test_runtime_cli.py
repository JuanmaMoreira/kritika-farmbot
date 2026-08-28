import signal
from contextlib import contextmanager

import pytest

from bot.flow_contracts import FlowResult, FlowStatus
from bot.productive_runtime import CancellationToken
from bot.session import SessionResult, SessionStatus
from tools import run_flow, run_session
from tools.runtime_cli import EXIT_CANCELLED, cancellation_signals


class FakeRuntime:
    def __init__(self, *, flow_result=None, session_result=None):
        self.flow_result = flow_result
        self.session_result = session_result
        self.flow_definition = None
        self.session_call = None

    def run_flow(self, definition):
        self.flow_definition = definition
        return self.flow_result

    def run_session(self, definitions, *, character_count):
        self.session_call = (definitions, character_count)
        return self.session_result


def factory_for(runtime, calls):
    @contextmanager
    def factory(**kwargs):
        calls.append(kwargs)
        yield runtime
    return factory


def test_run_flow_uses_productive_runtime_and_debug(monkeypatch, tmp_path):
    runtime = FakeRuntime(flow_result=FlowResult(FlowStatus.COMPLETED))
    calls = []
    monkeypatch.setattr(run_flow, "open_productive_runtime", factory_for(runtime, calls))

    code = run_flow.main(["black_market", "--debug", "--log-dir", str(tmp_path)])

    assert code == 0
    assert runtime.flow_definition.id == "black_market"
    assert calls[0]["debug"] is True


def test_run_session_preserves_order_and_character_count(monkeypatch, tmp_path):
    result = SessionResult(SessionStatus.COMPLETED, 2, 2, ())
    runtime = FakeRuntime(session_result=result)
    calls = []
    monkeypatch.setattr(run_session, "open_productive_runtime", factory_for(runtime, calls))

    code = run_session.main([
        "world_boss", "black_market", "--characters", "2", "--log-dir", str(tmp_path)
    ])

    assert code == 0
    definitions, count = runtime.session_call
    assert [item.id for item in definitions] == ["world_boss", "black_market"]
    assert count == 2


@pytest.mark.parametrize("argv", [[], ["missing"], ["black_market", "--characters", "0"]])
def test_session_invalid_arguments_exit_2(argv):
    with pytest.raises(SystemExit) as raised:
        run_session.parse_args(argv)
    assert raised.value.code == 2


def test_flow_cancelled_has_dedicated_exit_code(monkeypatch, tmp_path):
    runtime = FakeRuntime(flow_result=FlowResult(FlowStatus.CANCELLED))
    monkeypatch.setattr(run_flow, "open_productive_runtime", factory_for(runtime, []))

    assert run_flow.main(["world_boss", "--log-dir", str(tmp_path)]) == EXIT_CANCELLED


def test_sigint_requests_safe_cancellation_token():
    token = CancellationToken()
    with cancellation_signals(token):
        handler = signal.getsignal(signal.SIGINT)
        handler(signal.SIGINT, None)
    assert token.is_requested()
