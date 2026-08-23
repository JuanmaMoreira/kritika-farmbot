"""Observe physical Android touchscreen gestures without executing input.

The observer is an infrastructure source in the HUMAN -> system direction.
Construction and import are inert; device discovery and ``getevent`` start only
when :meth:`HumanInputObserver.start` is called explicitly.
"""

from __future__ import annotations

import math
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Callable, TypeAlias

from bot.adb import AdbClient

RelativePoint: TypeAlias = tuple[float, float]
RawPoint: TypeAlias = tuple[int, int]


class HumanInputError(RuntimeError):
    """Physical input observation could not start or failed while running."""


@dataclass(frozen=True)
class AxisRange:
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum, bool)
            or not isinstance(self.minimum, Integral)
            or isinstance(self.maximum, bool)
            or not isinstance(self.maximum, Integral)
            or self.maximum <= self.minimum
        ):
            raise ValueError("axis range requires integer maximum > minimum")
        object.__setattr__(self, "minimum", int(self.minimum))
        object.__setattr__(self, "maximum", int(self.maximum))

    def normalize(self, value: int) -> float:
        relative = (int(value) - self.minimum) / (self.maximum - self.minimum)
        return min(1.0, max(0.0, relative))


@dataclass(frozen=True)
class TouchDevice:
    path: str
    name: str
    x_axis: AxisRange
    y_axis: AxisRange
    supports_tracking_id: bool = False
    supports_btn_touch: bool = False


@dataclass(frozen=True)
class HumanTap:
    timestamp: float
    started_at: float
    position: RelativePoint
    raw_position: RawPoint
    duration: float


@dataclass(frozen=True)
class HumanSwipe:
    timestamp: float
    started_at: float
    start: RelativePoint
    end: RelativePoint
    raw_start: RawPoint
    raw_end: RawPoint
    duration: float
    path: tuple[RelativePoint, ...] = ()


@dataclass(frozen=True)
class UnknownGesture:
    timestamp: float
    started_at: float
    reason: str


HumanGesture: TypeAlias = HumanTap | HumanSwipe | UnknownGesture

_DEVICE = re.compile(r"^add device \d+:\s*(/dev/input/event\d+)\s*$")
_NAME = re.compile(r'^\s*name:\s*"(.*)"\s*$')
_AXIS = re.compile(
    r"\b(ABS_MT_POSITION_X|ABS_MT_POSITION_Y|0035|0036)\b\s*:"
    r".*?\bmin\s+(-?\d+).*?\bmax\s+(-?\d+)",
    re.IGNORECASE,
)
_TIMED_EVENT = re.compile(
    r"^\[\s*(\d+(?:\.\d+)?)\]\s+"
    r"(?:/dev/input/event\d+:\s+)?(.+?)\s*$"
)
_ROTATION_PATTERNS = (
    re.compile(r"Viewport\s+INTERNAL:.*?\borientation=(\d)", re.IGNORECASE),
    re.compile(r"\bSurfaceOrientation:\s*(\d)", re.IGNORECASE),
    re.compile(r"\bmCurrentOrientation=(\d)", re.IGNORECASE),
)


def parse_getevent_devices(output: str) -> tuple[TouchDevice, ...]:
    """Parse ``getevent -pl`` and return devices with both MT position axes."""

    devices: list[TouchDevice] = []
    path: str | None = None
    name = "unknown"
    axes: dict[str, AxisRange] = {}
    tracking = False
    btn_touch = False

    def finish() -> None:
        nonlocal path, name, axes, tracking, btn_touch
        if path is not None and "x" in axes and "y" in axes:
            devices.append(
                TouchDevice(
                    path=path,
                    name=name,
                    x_axis=axes["x"],
                    y_axis=axes["y"],
                    supports_tracking_id=tracking,
                    supports_btn_touch=btn_touch,
                )
            )
        path = None
        name = "unknown"
        axes = {}
        tracking = False
        btn_touch = False

    for line in output.splitlines():
        device_match = _DEVICE.match(line.strip())
        if device_match:
            finish()
            path = device_match.group(1)
            continue
        if path is None:
            continue
        name_match = _NAME.match(line)
        if name_match:
            name = name_match.group(1) or "unknown"
        axis_match = _AXIS.search(line)
        if axis_match:
            axis_name = axis_match.group(1).upper()
            key = "x" if axis_name in {"ABS_MT_POSITION_X", "0035"} else "y"
            try:
                axes[key] = AxisRange(int(axis_match.group(2)), int(axis_match.group(3)))
            except ValueError:
                pass
        tracking = tracking or "ABS_MT_TRACKING_ID" in line or "0039" in line
        btn_touch = btn_touch or "BTN_TOUCH" in line
    finish()
    return tuple(devices)


def select_touch_device(devices: tuple[TouchDevice, ...]) -> TouchDevice:
    """Choose reproducibly by touch capabilities, then coordinate area/path."""

    if not devices:
        raise HumanInputError(
            "No input device exposes ABS_MT_POSITION_X and ABS_MT_POSITION_Y"
        )

    def rank(device: TouchDevice) -> tuple[int, int, str]:
        capabilities = int(device.supports_tracking_id) * 2 + int(
            device.supports_btn_touch
        )
        area = (device.x_axis.maximum - device.x_axis.minimum) * (
            device.y_axis.maximum - device.y_axis.minimum
        )
        return -capabilities, -area, device.path

    return sorted(devices, key=rank)[0]


def parse_surface_rotation(output: str) -> int:
    """Parse Android's display rotation as quarter-turns from natural space."""

    for pattern in _ROTATION_PATTERNS:
        match = pattern.search(output)
        if match:
            rotation = int(match.group(1))
            if rotation in range(4):
                return rotation
    raise HumanInputError("Could not determine display orientation from dumpsys input")


def map_sensor_to_display(point: RelativePoint, rotation: int) -> RelativePoint:
    """Rotate normalized natural sensor space into normalized display space.

    Rotation values follow Android Surface rotation quarter-turns. Frame pixel
    geometry remains derived separately from ``frame.shape``.
    """

    x, y = _relative_point(point)
    if rotation == 0:
        return x, y
    if rotation == 1:
        return y, 1.0 - x
    if rotation == 2:
        return 1.0 - x, 1.0 - y
    if rotation == 3:
        return 1.0 - y, x
    raise ValueError("rotation must be one of 0, 1, 2, 3")


def relative_to_frame(point: RelativePoint, frame_shape: tuple[int, ...]) -> tuple[int, int]:
    """Map normalized display coordinates to a pixel from ``frame.shape``."""

    x, y = _relative_point(point)
    if len(frame_shape) < 2 or frame_shape[0] <= 0 or frame_shape[1] <= 0:
        raise ValueError("frame_shape must contain positive height and width")
    height, width = int(frame_shape[0]), int(frame_shape[1])
    return round(x * (width - 1)), round(y * (height - 1))


def _relative_point(point: object) -> RelativePoint:
    try:
        x, y = point  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError("point must contain two normalized coordinates") from error
    values: list[float] = []
    for value in (x, y):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("point coordinates must be finite values in [0, 1]")
        normalized = float(value)
        if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
            raise ValueError("point coordinates must be finite values in [0, 1]")
        values.append(normalized)
    return values[0], values[1]


@dataclass(frozen=True)
class ParsedInputEvent:
    timestamp: float
    code: str
    value: int | str


def parse_getevent_line(line: str) -> ParsedInputEvent | None:
    """Parse one symbolic or numeric ``getevent -lt`` line."""

    match = _TIMED_EVENT.match(line.strip())
    if not match:
        return None
    timestamp = float(match.group(1))
    fields = match.group(2).split()
    if len(fields) < 2:
        return None

    aliases = {
        "0035": "ABS_MT_POSITION_X",
        "0036": "ABS_MT_POSITION_Y",
        "0039": "ABS_MT_TRACKING_ID",
        "014a": "BTN_TOUCH",
        "0000": "SYN_REPORT",
    }
    interesting = {
        "ABS_MT_POSITION_X",
        "ABS_MT_POSITION_Y",
        "ABS_MT_TRACKING_ID",
        "BTN_TOUCH",
        "SYN_REPORT",
    }
    code_index = next(
        (
            index
            for index, field in enumerate(fields[:-1])
            if aliases.get(field.lower(), field.upper()) in interesting
        ),
        None,
    )
    if code_index is None:
        return None
    code = aliases.get(fields[code_index].lower(), fields[code_index].upper())
    token = fields[code_index + 1]
    if token.upper() in {"DOWN", "UP"}:
        value: int | str = token.upper()
    else:
        try:
            raw = int(token, 16)
        except ValueError:
            return None
        value = raw - (1 << 32) if raw >= (1 << 31) else raw
    return ParsedInputEvent(timestamp=timestamp, code=code, value=value)


class GestureReconstructor:
    """Reconstruct basic single-finger taps/swipes from Linux input events."""

    def __init__(
        self,
        device: TouchDevice,
        *,
        rotation: int,
        tap_tolerance: float = 0.025,
    ) -> None:
        if rotation not in range(4):
            raise ValueError("rotation must be one of 0, 1, 2, 3")
        if not 0.0 < tap_tolerance < 1.0:
            raise ValueError("tap_tolerance must be in (0, 1)")
        self.device = device
        self.rotation = rotation
        self.tap_tolerance = float(tap_tolerance)
        self._active = False
        self._tracking_id: int | None = None
        self._started_at = 0.0
        self._x: int | None = None
        self._y: int | None = None
        self._raw_path: list[RawPoint] = []
        self._multitouch = False

    def feed(self, event: ParsedInputEvent) -> tuple[HumanGesture, ...]:
        code, value = event.code, event.value
        if code == "ABS_MT_TRACKING_ID" and isinstance(value, int):
            if value >= 0:
                if self._active and self._tracking_id not in {None, value}:
                    self._multitouch = True
                else:
                    self._begin(event.timestamp, value)
            else:
                gesture = self._finish(event.timestamp)
                return () if gesture is None else (gesture,)
        elif code == "BTN_TOUCH":
            if value in {1, "DOWN"} and not self._active:
                self._begin(event.timestamp, None)
            elif value in {0, "UP"}:
                gesture = self._finish(event.timestamp)
                return () if gesture is None else (gesture,)
        elif code == "ABS_MT_POSITION_X" and isinstance(value, int):
            self._x = value
        elif code == "ABS_MT_POSITION_Y" and isinstance(value, int):
            self._y = value
        elif code == "SYN_REPORT" and self._active:
            self._append_current()
        return ()

    def flush(self, timestamp: float) -> tuple[HumanGesture, ...]:
        if not self._active:
            return ()
        started_at = self._started_at
        self._reset()
        return (
            UnknownGesture(
                timestamp=float(timestamp),
                started_at=started_at,
                reason="incomplete gesture at input stream end",
            ),
        )

    def _begin(self, timestamp: float, tracking_id: int | None) -> None:
        self._active = True
        self._tracking_id = tracking_id
        self._started_at = timestamp
        self._x = None
        self._y = None
        self._raw_path = []
        self._multitouch = False

    def _append_current(self) -> None:
        if self._x is None or self._y is None:
            return
        point = (self._x, self._y)
        if not self._raw_path or point != self._raw_path[-1]:
            self._raw_path.append(point)

    def _finish(self, timestamp: float) -> HumanGesture | None:
        if not self._active:
            return None
        self._append_current()
        started_at = self._started_at
        raw_path = tuple(self._raw_path)
        multitouch = self._multitouch
        self._reset()
        if multitouch:
            return UnknownGesture(timestamp, started_at, "multitouch is unsupported in v1")
        if not raw_path:
            return UnknownGesture(timestamp, started_at, "gesture had no complete coordinates")

        display_path = tuple(self._display_point(point) for point in raw_path)
        start, end = display_path[0], display_path[-1]
        duration = max(0.0, timestamp - started_at)
        max_distance = max(
            math.hypot(point[0] - start[0], point[1] - start[1])
            for point in display_path
        )
        if max_distance <= self.tap_tolerance:
            return HumanTap(
                timestamp=timestamp,
                started_at=started_at,
                position=end,
                raw_position=raw_path[-1],
                duration=duration,
            )
        return HumanSwipe(
            timestamp=timestamp,
            started_at=started_at,
            start=start,
            end=end,
            raw_start=raw_path[0],
            raw_end=raw_path[-1],
            duration=duration,
            path=display_path,
        )

    def _display_point(self, raw: RawPoint) -> RelativePoint:
        sensor = (
            self.device.x_axis.normalize(raw[0]),
            self.device.y_axis.normalize(raw[1]),
        )
        return map_sensor_to_display(sensor, self.rotation)

    def _reset(self) -> None:
        self._active = False
        self._tracking_id = None
        self._x = None
        self._y = None
        self._raw_path = []
        self._multitouch = False


class HumanInputObserver:
    """Lifecycle-managed source of physical touchscreen gestures."""

    def __init__(
        self,
        adb: AdbClient,
        *,
        rotation: int | None = None,
        tap_tolerance: float = 0.025,
        shutdown_timeout: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if adb is None:
            raise ValueError("adb must be provided explicitly")
        if rotation is not None and rotation not in range(4):
            raise ValueError("rotation must be one of 0, 1, 2, 3")
        if shutdown_timeout <= 0:
            raise ValueError("shutdown_timeout must be positive")
        self.adb = adb
        self.rotation_override = rotation
        self.tap_tolerance = tap_tolerance
        self.shutdown_timeout = float(shutdown_timeout)
        self._clock = clock
        self.device: TouchDevice | None = None
        self.rotation: int | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._events: deque[HumanGesture] = deque()
        self._events_lock = threading.Lock()
        self._failure: HumanInputError | None = None

    @property
    def is_running(self) -> bool:
        return (
            self._process is not None
            and self._process.poll() is None
            and self._thread is not None
            and self._thread.is_alive()
            and self._failure is None
        )

    @property
    def failure(self) -> HumanInputError | None:
        return self._failure

    def start(self) -> "HumanInputObserver":
        if self._process is not None or self._thread is not None:
            raise HumanInputError("HumanInputObserver is already started")
        discovery = self.adb.shell("getevent", "-pl").stdout
        self.device = select_touch_device(parse_getevent_devices(discovery))
        if self.rotation_override is None:
            rotation_output = self.adb.shell("dumpsys", "input").stdout
            self.rotation = parse_surface_rotation(rotation_output)
        else:
            self.rotation = self.rotation_override
        reconstructor = GestureReconstructor(
            self.device,
            rotation=self.rotation,
            tap_tolerance=self.tap_tolerance,
        )
        self._stop_event.clear()
        self._failure = None
        try:
            self._process = self.adb.spawn_shell(
                "getevent", "-lt", self.device.path, capture_output=True
            )
            if self._process.stdout is None:
                raise HumanInputError("ADB getevent process has no stdout pipe")
            self._thread = threading.Thread(
                target=self._read_loop,
                args=(reconstructor,),
                name="human-input-observer",
                daemon=True,
            )
            self._thread.start()
        except BaseException:
            self.stop()
            raise
        return self

    def poll(self) -> tuple[HumanGesture, ...]:
        if self._failure is not None:
            raise self._failure
        with self._events_lock:
            result = tuple(self._events)
            self._events.clear()
        return result

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        if process is not None:
            stdout = process.stdout
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self.shutdown_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=self.shutdown_timeout)
            if stdout is not None:
                stdout.close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.shutdown_timeout)
            if thread.is_alive():
                raise HumanInputError("getevent reader thread did not stop")
        self._process = None
        self._thread = None

    def __enter__(self) -> "HumanInputObserver":
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.stop()
        return False

    def _read_loop(self, reconstructor: GestureReconstructor) -> None:
        assert self._process is not None and self._process.stdout is not None
        process = self._process
        try:
            while not self._stop_event.is_set():
                raw_line = process.stdout.readline()
                if not raw_line:
                    break
                parsed = parse_getevent_line(raw_line.decode(errors="replace"))
                if parsed is None:
                    continue
                # getevent timestamps belong to the device's CLOCK_MONOTONIC,
                # while FrameSnapshot timestamps belong to the host. Re-stamp
                # at receipt so gesture/frame association uses one clock domain.
                host_event = ParsedInputEvent(
                    timestamp=self._clock(),
                    code=parsed.code,
                    value=parsed.value,
                )
                self._enqueue(reconstructor.feed(host_event))
            if not self._stop_event.is_set():
                self._enqueue(reconstructor.flush(self._clock()))
                returncode = process.poll()
                if returncode not in {None, 0}:
                    self._failure = HumanInputError(
                        f"adb shell getevent exited with code {returncode}"
                    )
        except (OSError, ValueError) as error:
            if not self._stop_event.is_set():
                self._failure = HumanInputError(f"getevent reader failed: {error}")

    def _enqueue(self, events: tuple[HumanGesture, ...]) -> None:
        if not events:
            return
        with self._events_lock:
            self._events.extend(events)
