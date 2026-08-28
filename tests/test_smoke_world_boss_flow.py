from tools.smoke_world_boss_flow import parse_args


def test_harness_requires_explicit_command_and_execute_flag_is_opt_in():
    args = parse_args(["flow"])

    assert args.command == "flow"
    assert not args.execute


def test_harness_supports_exactly_one_flow_then_rotation_smoke():
    args = parse_args(["flow-then-rotation", "--execute"])

    assert args.command == "flow-then-rotation"
    assert args.execute
    assert args.character_count == 28
