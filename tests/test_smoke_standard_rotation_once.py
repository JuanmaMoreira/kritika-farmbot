from tools.smoke_standard_rotation_once import main, parse_args


def test_smoke_requires_explicit_execute_acknowledgement(capsys):
    assert main([]) == 2
    assert "Refusing to send Android input" in capsys.readouterr().err


def test_smoke_defaults_are_one_standard_rotation_only():
    args = parse_args([])

    assert not args.execute
    assert args.character_count == 28
    assert args.max_attempts == 3
    assert args.scroll_settle_for == 1.0
    assert args.timeout == 6.0
