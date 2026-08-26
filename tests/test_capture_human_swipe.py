import pytest

from bot.human_input import HumanSwipe
from tools.capture_human_swipe import main, parse_args, swipe_reference


def test_reference_reports_normalized_upward_swipe_geometry():
    swipe = HumanSwipe(
        timestamp=10.3,
        started_at=10.0,
        start=(0.72, 0.84),
        end=(0.68, 0.18),
        raw_start=(100, 200),
        raw_end=(300, 400),
        duration=0.3,
        path=((0.72, 0.84), (0.70, 0.50), (0.68, 0.18)),
    )

    reference = swipe_reference(swipe)

    assert reference.start == (0.72, 0.84)
    assert reference.end == (0.68, 0.18)
    assert reference.duration_seconds == 0.3
    assert reference.direction == "up"
    assert reference.horizontal_displacement == pytest.approx(-0.04)
    assert reference.vertical_displacement == pytest.approx(-0.66)
    assert reference.displacement == pytest.approx(0.661211)
    assert reference.path_points == 3


def test_capture_requires_explicit_read_only_acknowledgement(capsys):
    assert main([]) == 2
    assert "Refusing to observe Android input" in capsys.readouterr().err


def test_capture_defaults_are_bounded():
    args = parse_args([])

    assert args.timeout == 60.0
    assert args.poll_interval == 0.02
