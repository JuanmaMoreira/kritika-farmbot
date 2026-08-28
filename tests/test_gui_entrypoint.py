from pathlib import Path

from tools import gui


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


def test_gui_launcher_accepts_local_runtime_paths(tmp_path):
    args = gui.parse_args(["--dotenv", str(tmp_path / ".env"), "--log-dir", str(tmp_path / "logs")])

    assert args.dotenv == tmp_path / ".env"
    assert args.log_dir == tmp_path / "logs"
