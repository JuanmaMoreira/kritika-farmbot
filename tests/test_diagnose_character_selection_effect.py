from pathlib import Path

from tools import diagnose_character_selection_effect as diagnostic


def test_diagnostic_refuses_input_without_execute_flag(capsys):
    assert diagnostic.main([]) == 2
    assert "without --execute" in capsys.readouterr().err


def test_diagnostic_composes_runtime_boundaries_without_direct_adb_input():
    source = Path("tools/diagnose_character_selection_effect.py").read_text(
        encoding="utf-8"
    )

    assert "ActionExecutor" in source
    assert "RuntimeObserver" in source
    assert ".tap(" not in source
    assert ".swipe(" not in source
