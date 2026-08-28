from pathlib import Path


def test_double_click_launcher_is_thin_hidden_wrapper_for_productive_gui():
    source = Path("Kritika FarmBot.cmd").read_text(encoding="utf-8")

    assert "tools\\agent_run.ps1" in source
    assert "tools.gui" in source
    assert "-WindowStyle Hidden" in source
    assert 'pushd "%~dp0"' in source
    assert "AdbClient" not in source
    assert "BlackMarketFlow" not in source
    assert "WorldBossFlow" not in source
