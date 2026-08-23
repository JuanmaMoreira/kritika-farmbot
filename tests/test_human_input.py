import io
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from bot.adb import AdbClient
from bot.human_input import (
    AxisRange,
    GestureReconstructor,
    HumanInputObserver,
    HumanSwipe,
    HumanTap,
    ParsedInputEvent,
    TouchDevice,
    UnknownGesture,
    map_sensor_to_display,
    parse_getevent_devices,
    parse_getevent_line,
    parse_surface_rotation,
    relative_to_frame,
    select_touch_device,
)


DISCOVERY = """add device 1: /dev/input/event1
  name: "buttons"
  events:
    KEY (0001): KEY_POWER
add device 2: /dev/input/event7
  name: "touch panel"
  events:
    KEY (0001): BTN_TOUCH
    ABS (0003): ABS_MT_SLOT : value 0, min 0, max 9
                ABS_MT_POSITION_X : value 0, min 100, max 1100, fuzz 0
                ABS_MT_POSITION_Y : value 0, min 200, max 2200, fuzz 0
                ABS_MT_TRACKING_ID : value 0, min 0, max 65535
add device 3: /dev/input/event8
  name: "secondary digitizer"
  events:
    ABS (0003): 0035 : value 0, min 0, max 500
                0036 : value 0, min 0, max 700
"""


def touch_device():
    return TouchDevice(
        path="/dev/input/event7",
        name="touch panel",
        x_axis=AxisRange(100, 1100),
        y_axis=AxisRange(200, 2200),
        supports_tracking_id=True,
        supports_btn_touch=True,
    )


def event(timestamp, code, value):
    return ParsedInputEvent(timestamp, code, value)


def test_import_has_no_external_or_file_side_effects(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )
    result = subprocess.run(
        [sys.executable, "-c", "import bot.human_input"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_discovery_parser_requires_real_multitouch_position_axes():
    devices = parse_getevent_devices(DISCOVERY)
    assert [device.path for device in devices] == [
        "/dev/input/event7",
        "/dev/input/event8",
    ]
    primary = devices[0]
    assert primary.name == "touch panel"
    assert primary.x_axis == AxisRange(100, 1100)
    assert primary.y_axis == AxisRange(200, 2200)
    assert primary.supports_tracking_id
    assert primary.supports_btn_touch
    assert select_touch_device(devices) is primary


def test_axis_normalization_uses_real_minimum_and_maximum_and_clamps():
    axis = AxisRange(100, 1100)
    assert axis.normalize(100) == 0.0
    assert axis.normalize(600) == 0.5
    assert axis.normalize(1100) == 1.0
    assert axis.normalize(-10) == 0.0
    assert axis.normalize(9999) == 1.0


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (0, (0.2, 0.7)),
        (1, (0.7, 0.8)),
        (2, (0.8, 0.3)),
        (3, (0.3, 0.2)),
    ],
)
def test_sensor_to_display_rotation_is_explicit(rotation, expected):
    assert map_sensor_to_display((0.2, 0.7), rotation) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("point", "pixel"),
    [
        ((0.0, 0.0), (0, 0)),
        ((1.0, 1.0), (2711, 1223)),
        ((0.5, 0.5), (1356, 612)),
    ],
)
def test_display_point_uses_landscape_frame_shape(point, pixel):
    assert relative_to_frame(point, (1224, 2712, 3)) == pixel


def test_rotation_parser_prefers_internal_viewport():
    output = """SurfaceOrientation: 3
Viewport INTERNAL: displayId=0, orientation=1, logicalFrame=[0, 0, 2712, 1224]
"""
    assert parse_surface_rotation(output) == 1


@pytest.mark.parametrize(
    ("line", "code", "value"),
    [
        (
            "[ 123.100000] /dev/input/event7: EV_ABS ABS_MT_POSITION_X 00000258",
            "ABS_MT_POSITION_X",
            600,
        ),
        (
            "[ 123.200000] /dev/input/event7: 0003 0039 ffffffff",
            "ABS_MT_TRACKING_ID",
            -1,
        ),
        (
            "[ 123.300000] /dev/input/event7: EV_KEY BTN_TOUCH UP",
            "BTN_TOUCH",
            "UP",
        ),
    ],
)
def test_getevent_line_parser_supports_symbolic_and_numeric_output(line, code, value):
    parsed = parse_getevent_line(line)
    assert parsed is not None
    assert parsed.code == code
    assert parsed.value == value


def test_reconstructs_tap_from_down_coordinates_reports_and_up():
    parser = GestureReconstructor(touch_device(), rotation=0, tap_tolerance=0.03)
    stream = (
        event(10.0, "ABS_MT_TRACKING_ID", 42),
        event(10.01, "ABS_MT_POSITION_X", 600),
        event(10.02, "ABS_MT_POSITION_Y", 1200),
        event(10.03, "SYN_REPORT", 0),
        event(10.10, "ABS_MT_TRACKING_ID", -1),
    )
    gestures = tuple(item for entry in stream for item in parser.feed(entry))
    assert len(gestures) == 1
    tap = gestures[0]
    assert isinstance(tap, HumanTap)
    assert tap.position == pytest.approx((0.5, 0.5))
    assert tap.raw_position == (600, 1200)
    assert tap.started_at == 10.0
    assert tap.timestamp == 10.1
    assert tap.duration == pytest.approx(0.1)


def test_reconstructs_one_swipe_instead_of_multiple_taps():
    parser = GestureReconstructor(touch_device(), rotation=1, tap_tolerance=0.03)
    stream = (
        event(20.0, "BTN_TOUCH", "DOWN"),
        event(20.01, "ABS_MT_POSITION_X", 100),
        event(20.02, "ABS_MT_POSITION_Y", 200),
        event(20.03, "SYN_REPORT", 0),
        event(20.10, "ABS_MT_POSITION_X", 1100),
        event(20.11, "ABS_MT_POSITION_Y", 2200),
        event(20.12, "SYN_REPORT", 0),
        event(20.20, "BTN_TOUCH", "UP"),
    )
    gestures = tuple(item for entry in stream for item in parser.feed(entry))
    assert len(gestures) == 1
    swipe = gestures[0]
    assert isinstance(swipe, HumanSwipe)
    assert swipe.start == pytest.approx((0.0, 1.0))
    assert swipe.end == pytest.approx((1.0, 0.0))
    assert swipe.raw_start == (100, 200)
    assert swipe.raw_end == (1100, 2200)
    assert len(swipe.path) == 2


def test_incomplete_and_multitouch_sequences_are_unknown_not_invented():
    parser = GestureReconstructor(touch_device(), rotation=0)
    parser.feed(event(30.0, "ABS_MT_TRACKING_ID", 1))
    incomplete = parser.flush(30.5)
    assert isinstance(incomplete[0], UnknownGesture)
    assert "incomplete" in incomplete[0].reason

    parser.feed(event(31.0, "ABS_MT_TRACKING_ID", 1))
    parser.feed(event(31.1, "ABS_MT_POSITION_X", 600))
    parser.feed(event(31.1, "ABS_MT_POSITION_Y", 1200))
    parser.feed(event(31.1, "SYN_REPORT", 0))
    parser.feed(event(31.2, "ABS_MT_TRACKING_ID", 2))
    result = parser.feed(event(31.3, "ABS_MT_TRACKING_ID", -1))
    assert isinstance(result[0], UnknownGesture)
    assert "multitouch" in result[0].reason


class FakeProcess:
    def __init__(self, output):
        self.stdout = io.BytesIO(output)
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return 0 if self.terminated or self.killed else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 0


def test_observer_discovers_starts_reads_and_cleans_owned_process():
    lines = b"\n".join(
        [
            b"[ 40.000000] EV_ABS ABS_MT_TRACKING_ID 00000001",
            b"[ 40.010000] EV_ABS ABS_MT_POSITION_X 00000258",
            b"[ 40.020000] EV_ABS ABS_MT_POSITION_Y 000004b0",
            b"[ 40.030000] EV_SYN SYN_REPORT 00000000",
            b"[ 40.100000] EV_ABS ABS_MT_TRACKING_ID ffffffff",
        ]
    )
    process = FakeProcess(lines)
    adb = Mock(spec=AdbClient)
    adb.shell.side_effect = [
        Mock(stdout=DISCOVERY),
        Mock(stdout="Viewport INTERNAL: displayId=0, orientation=0"),
    ]
    adb.spawn_shell.return_value = process
    observer = HumanInputObserver(adb, shutdown_timeout=0.2)

    observer.start()
    deadline = time.monotonic() + 1.0
    gestures = ()
    while time.monotonic() < deadline and not gestures:
        gestures = observer.poll()
        time.sleep(0.005)
    observer.stop()

    assert isinstance(gestures[0], HumanTap)
    adb.spawn_shell.assert_called_once_with(
        "getevent", "-lt", "/dev/input/event7", capture_output=True
    )
    assert process.terminated
    assert process.waited
    assert not observer.is_running


def test_observer_restamps_device_events_into_host_monotonic_domain():
    lines = b"\n".join(
        [
            b"[ 99999.000000] EV_ABS ABS_MT_TRACKING_ID 00000001",
            b"[ 99999.010000] EV_ABS ABS_MT_POSITION_X 00000258",
            b"[ 99999.020000] EV_ABS ABS_MT_POSITION_Y 000004b0",
            b"[ 99999.030000] EV_SYN SYN_REPORT 00000000",
            b"[ 99999.100000] EV_ABS ABS_MT_TRACKING_ID ffffffff",
        ]
    )
    process = FakeProcess(lines)
    adb = Mock(spec=AdbClient)
    adb.shell.side_effect = [Mock(stdout=DISCOVERY)]
    adb.spawn_shell.return_value = process
    clock = Mock(side_effect=[100.0, 100.01, 100.02, 100.03, 100.1, 100.2])
    observer = HumanInputObserver(adb, rotation=0, clock=clock, shutdown_timeout=0.2)

    observer.start()
    deadline = time.monotonic() + 1.0
    gestures = ()
    while time.monotonic() < deadline and not gestures:
        gestures = observer.poll()
        time.sleep(0.005)
    observer.stop()

    assert gestures[0].started_at == 100.0
    assert gestures[0].timestamp == 100.1
