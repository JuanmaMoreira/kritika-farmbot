from pathlib import Path

import pytest

from bot.gui_controller import GuiExecutionResult, GuiRunStatus
from bot.gui_model import GuiExecutionRequest, GuiProgress, GuiRunMode, SessionElapsedTimer
from tools import gui


class Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Root:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))


class Controller:
    def __init__(self):
        self.requests = []
        self.stop_requested = False

    def start(self, request):
        self.requests.append(request)

    def stop_safely(self):
        self.stop_requested = True
        return True


def build_gui_shell(clock):
    app = gui.KritikaFarmBotGui.__new__(gui.KritikaFarmBotGui)
    app.root = Root()
    app.controller = Controller()
    app.progress = GuiProgress()
    app.session_timer = SessionElapsedTimer(clock=clock)
    app._active_mode = None
    app._debug_for_run = False
    app.status_var = Var()
    app.character_var = Var()
    app.flow_var = Var()
    app.state_var = Var()
    app.result_var = Var()
    app.log_var = Var()
    app.session_elapsed_var = Var(app.session_timer.text)
    app._set_running_controls = lambda running: None
    return app


def test_gui_entrypoint_has_no_flow_list_or_productive_business_dependencies():
    source = Path("tools/gui.py").read_text(encoding="utf-8")

    assert "BlackMarketFlow" not in source
    assert "WorldBossFlow" not in source
    assert "AdbClient" not in source
    assert "ActionExecutor" not in source
    assert "open_productive_runtime" not in source
    assert '"Black Market"' not in source
    assert '"World Boss"' not in source


def test_gui_uses_one_scrolled_text_batched_queue_drain_and_tk_after():
    source = Path("tools/gui.py").read_text(encoding="utf-8")

    assert source.count("ScrolledText(") == 1
    assert "controller.drain(limit=250)" in source
    assert '"\\n".join(lines)' in source
    assert "root.after(" in source
    assert "threading" not in source
    assert '"Status"' in source
    assert 'text="Result:"' in source


@pytest.mark.parametrize(
    "status",
    (GuiRunStatus.COMPLETED, GuiRunStatus.FAILED, GuiRunStatus.CANCELLED),
)
def test_session_timer_freezes_for_every_terminal_result(status, tmp_path):
    now = [10.0]
    app = build_gui_shell(lambda: now[0])
    request = GuiExecutionRequest.session(("world_boss",), 2, log_dir=tmp_path)
    app._start(request)
    now[0] = 17.9
    app._refresh_session_timer()

    assert app.session_elapsed_var.get() == "00:00:07"
    assert app.root.after_calls[-1][0] == gui.SESSION_TIMER_INTERVAL_MS

    app._finish(GuiExecutionResult(status, 7.4, tmp_path / "run.log"))
    now[0] = 100.0
    app._refresh_session_timer()

    assert app.session_elapsed_var.get() == "00:00:07"
    assert app._active_mode is None


def test_stop_safely_keeps_timer_running_until_cancelled_then_new_session_resets(tmp_path):
    now = [20.0]
    app = build_gui_shell(lambda: now[0])
    request = GuiExecutionRequest.session(("world_boss",), 2, log_dir=tmp_path)
    app._start(request)
    now[0] = 25.2
    app._stop_safely()
    app._refresh_session_timer()

    assert app.controller.stop_requested
    assert app.status_var.get() == GuiRunStatus.STOPPING.value
    assert app.session_elapsed_var.get() == "00:00:05"

    app._finish(GuiExecutionResult(GuiRunStatus.CANCELLED, 5.8, tmp_path / "cancelled.log"))
    now[0] = 40.0
    app._start(request)

    assert app.session_elapsed_var.get() == "00:00:00"
    assert app._active_mode is GuiRunMode.SESSION


def test_gui_launcher_accepts_local_runtime_paths(tmp_path):
    args = gui.parse_args(["--dotenv", str(tmp_path / ".env"), "--log-dir", str(tmp_path / "logs")])

    assert args.dotenv == tmp_path / ".env"
    assert args.log_dir == tmp_path / "logs"
