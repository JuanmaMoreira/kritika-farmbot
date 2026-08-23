"""Lifecycle-managed scrcpy frame capture for the 0.2 infrastructure layer."""

from __future__ import annotations

import math
import os
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Callable, Iterable, Protocol

import numpy as np

from bot.adb import AdbClient
from bot.geometry import frame_dimensions


class CaptureError(RuntimeError):
    """The frame source could not start or its receiver failed."""


class CaptureTimeoutError(CaptureError):
    """The frame source exceeded a bounded startup wait."""

    def __init__(self, message: str, timeout: float) -> None:
        self.timeout = timeout
        super().__init__(message)


@dataclass(frozen=True)
class FrameSnapshot:
    """A BGR image and the monotonic identity of its decoded frame."""

    image: np.ndarray
    timestamp: float
    sequence: int

    @property
    def width(self) -> int:
        return frame_dimensions(self.image)[0]

    @property
    def height(self) -> int:
        return frame_dimensions(self.image)[1]


class _Decoder(Protocol):
    def decode(self, payload: bytes, pts: int | None) -> Iterable[np.ndarray]: ...

    def close(self) -> None: ...


class _PyAvDecoder:
    """Small lazy PyAV boundary used by the production frame source."""

    def __init__(self) -> None:
        import av

        self._av = av
        self._codec = av.CodecContext.create("h264", "r")

    def decode(self, payload: bytes, pts: int | None) -> Iterable[np.ndarray]:
        packet = self._av.Packet(payload)
        if pts is not None:
            packet.pts = pts
        for frame in self._codec.decode(packet):
            yield frame.to_ndarray(format="bgr24")

    def close(self) -> None:
        close = getattr(self._codec, "close", None)
        if close is not None:
            close()


SocketFactory = Callable[[], socket.socket]
DecoderFactory = Callable[[], _Decoder]


class _CaptureStopped(Exception):
    pass


class ScrcpyFrameSource:
    """Receive the newest BGR frame from one lifecycle-managed scrcpy stream."""

    REMOTE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"
    SCRCPY_SOCKET = "localabstract:scrcpy"
    SCRCPY_VERSION = "3.3.4"
    CONFIG_PACKET_FLAG = 1 << 63
    KEY_FRAME_PACKET_FLAG = 1 << 62
    PACKET_PTS_MASK = KEY_FRAME_PACKET_FLAG - 1
    METADATA_SIZE = 1 + 64 + 4 + 4 + 4

    def __init__(
        self,
        adb: AdbClient,
        scrcpy_server_path: str | os.PathLike[str],
        *,
        local_port: int = 27183,
        connect_timeout: float = 10.0,
        first_frame_timeout: float = 10.0,
        receive_timeout: float = 0.25,
        startup_delay: float = 2.0,
        shutdown_timeout: float = 2.0,
        socket_factory: SocketFactory | None = None,
        decoder_factory: DecoderFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if adb is None:
            raise ValueError("adb must be provided explicitly")
        self.adb = adb
        self.scrcpy_server_path = _non_empty_path(scrcpy_server_path)
        self.local_port = _port(local_port)
        self.connect_timeout = _positive_duration(connect_timeout, "connect_timeout")
        self.first_frame_timeout = _positive_duration(
            first_frame_timeout, "first_frame_timeout"
        )
        self.receive_timeout = _positive_duration(receive_timeout, "receive_timeout")
        self.startup_delay = _non_negative_duration(startup_delay, "startup_delay")
        self.shutdown_timeout = _positive_duration(
            shutdown_timeout, "shutdown_timeout"
        )
        self._socket_factory = socket_factory or self._new_socket
        self._decoder_factory = decoder_factory or _PyAvDecoder
        self._clock = clock

        self._lifecycle_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._frame_event = threading.Event()
        self._running = False
        self._starting = False
        self._failure: CaptureError | None = None
        self._snapshot: FrameSnapshot | None = None
        self._sequence = 0
        self._pending_config_packet: bytes | None = None
        self._forward_active = False
        self._process: subprocess.Popen[bytes] | None = None
        self._socket: socket.socket | None = None
        self._decoder: _Decoder | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lifecycle_lock:
            return self._running and self._failure is None

    @property
    def failure(self) -> CaptureError | None:
        with self._lifecycle_lock:
            return self._failure

    def start(self) -> "ScrcpyFrameSource":
        """Acquire capture resources and wait for the first decoded frame."""

        with self._lifecycle_lock:
            if self._starting or self._running or self._has_resources():
                raise CaptureError("ScrcpyFrameSource is already started")
            self._starting = True
            self._failure = None
            self._snapshot = None
            self._pending_config_packet = None
            self._stop_event.clear()
            self._frame_event.clear()

        try:
            self.adb.push(self.scrcpy_server_path, self.REMOTE_SERVER_PATH)
            self.adb.forward(self.local_endpoint, self.SCRCPY_SOCKET)
            self._forward_active = True
            self._process = self.adb.spawn_shell(*self._server_arguments())

            if self.startup_delay:
                time.sleep(self.startup_delay)

            self._socket = self._socket_factory()
            self._socket.settimeout(self.connect_timeout)
            self._socket.connect(("127.0.0.1", self.local_port))
            self._read_metadata()

            self._decoder = self._decoder_factory()
            self._socket.settimeout(self.receive_timeout)
            with self._lifecycle_lock:
                self._running = True
            self._thread = threading.Thread(
                target=self._receive_loop,
                name=f"scrcpy-frame-source-{self.local_port}",
                daemon=True,
            )
            self._thread.start()

            if not self._frame_event.wait(self.first_frame_timeout):
                raise CaptureTimeoutError(
                    "Timed out waiting for the first scrcpy frame",
                    self.first_frame_timeout,
                )
            failure = self.failure
            if failure is not None:
                raise failure
            if self._snapshot is None:
                raise CaptureError("Capture receiver stopped before producing a frame")
            return self
        except BaseException as error:
            self._cleanup(suppress_errors=True)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(error, CaptureError):
                raise
            raise CaptureError(f"Could not start scrcpy capture: {error}") from error
        finally:
            with self._lifecycle_lock:
                self._starting = False

    def stop(self) -> None:
        """Stop capture and release every acquired resource; safe to call twice."""

        self._cleanup(suppress_errors=False)

    def get_frame(self) -> FrameSnapshot:
        """Return a copy of the latest frame so callers cannot mutate the buffer."""

        failure = self.failure
        if failure is not None:
            raise failure
        with self._frame_lock:
            if self._snapshot is None:
                raise CaptureError("No decoded frame is available")
            snapshot = self._snapshot
            return FrameSnapshot(
                image=snapshot.image.copy(),
                timestamp=snapshot.timestamp,
                sequence=snapshot.sequence,
            )

    @property
    def local_endpoint(self) -> str:
        return f"tcp:{self.local_port}"

    def __enter__(self) -> "ScrcpyFrameSource":
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            self.stop()
        except CaptureError:
            if exc_type is None:
                raise
        return False

    def _server_arguments(self) -> tuple[str, ...]:
        return (
            f"CLASSPATH={self.REMOTE_SERVER_PATH}",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            self.SCRCPY_VERSION,
            "tunnel_forward=true",
            "video_bit_rate=2000000",
            "max_size=0",
            "audio=false",
            "control=false",
        )

    def _new_socket(self) -> socket.socket:
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def _read_metadata(self) -> None:
        try:
            self._recv_exact(self.METADATA_SIZE, during_start=True)
        except socket.timeout as error:
            raise CaptureTimeoutError(
                "Timed out reading scrcpy stream metadata", self.connect_timeout
            ) from error

    def _receive_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                header = self._recv_exact(12)
                pts_flags = struct.unpack(">Q", header[:8])[0]
                payload_size = struct.unpack(">I", header[8:])[0]
                payload = self._recv_exact(payload_size)
                if pts_flags & self.CONFIG_PACKET_FLAG:
                    self._pending_config_packet = payload
                    continue
                if self._pending_config_packet is not None:
                    payload = self._pending_config_packet + payload
                    self._pending_config_packet = None
                decoded_pts = pts_flags & self.PACKET_PTS_MASK
                if self._decoder is None:
                    raise CaptureError("Capture decoder is not initialized")
                for image in self._decoder.decode(payload, decoded_pts):
                    self._publish(image)
        except _CaptureStopped:
            pass
        except Exception as error:
            if not self._stop_event.is_set():
                failure = (
                    error
                    if isinstance(error, CaptureError)
                    else CaptureError(f"Scrcpy receiver failed: {error}")
                )
                with self._lifecycle_lock:
                    self._failure = failure
                self._frame_event.set()
        finally:
            with self._lifecycle_lock:
                self._running = False

    def _recv_exact(self, size: int, *, during_start: bool = False) -> bytes:
        if self._socket is None:
            raise CaptureError("Capture socket is not initialized")
        data = bytearray()
        while len(data) < size:
            try:
                chunk = self._socket.recv(size - len(data))
            except socket.timeout:
                if during_start:
                    raise
                if self._stop_event.is_set():
                    raise _CaptureStopped
                continue
            except OSError as error:
                if self._stop_event.is_set():
                    raise _CaptureStopped from error
                raise
            if not chunk:
                if self._stop_event.is_set():
                    raise _CaptureStopped
                raise CaptureError("Scrcpy socket closed unexpectedly")
            data.extend(chunk)
        return bytes(data)

    def _publish(self, image: np.ndarray) -> None:
        if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
            raise CaptureError("Decoder must produce a BGR ndarray with three channels")
        height, width = image.shape[:2]
        if height <= 0 or width <= 0:
            raise CaptureError("Decoder produced an empty frame")
        with self._frame_lock:
            self._sequence += 1
            self._snapshot = FrameSnapshot(
                image=image.copy(), timestamp=self._clock(), sequence=self._sequence
            )
        self._frame_event.set()

    def _cleanup(self, *, suppress_errors: bool) -> None:
        with self._lifecycle_lock:
            has_resources = self._has_resources()
            self._running = False
        if not has_resources:
            return

        errors: list[Exception] = []
        self._stop_event.set()

        if self._socket is not None:
            try:
                self._socket.close()
            except Exception as error:
                errors.append(error)

        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.shutdown_timeout)
            if self._thread.is_alive():
                errors.append(CaptureError("Capture thread did not stop in time"))

        if self._process is not None:
            try:
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=self.shutdown_timeout)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=self.shutdown_timeout)
            except Exception as error:
                errors.append(error)

        if self._decoder is not None:
            try:
                self._decoder.close()
            except Exception as error:
                errors.append(error)

        if self._forward_active:
            try:
                self.adb.remove_forward(self.local_endpoint)
            except Exception as error:
                errors.append(error)

        with self._lifecycle_lock:
            self._socket = None
            self._thread = None
            self._process = None
            self._decoder = None
            self._forward_active = False
            self._pending_config_packet = None

        if errors and not suppress_errors:
            raise CaptureError(f"Capture cleanup failed: {errors[0]}") from errors[0]

    def _has_resources(self) -> bool:
        return any(
            (
                self._forward_active,
                self._process is not None,
                self._socket is not None,
                self._decoder is not None,
                self._thread is not None,
            )
        )


def _non_empty_path(value: str | os.PathLike[str]) -> str:
    try:
        path = os.fspath(value)
    except TypeError as error:
        raise ValueError("scrcpy_server_path must be a non-empty path") from error
    if not isinstance(path, str) or not path.strip():
        raise ValueError("scrcpy_server_path must be a non-empty path")
    return path.strip()


def _port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("local_port must be an integer from 1 to 65535")
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("local_port must be an integer from 1 to 65535")
    return port


def _positive_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return duration


def _non_negative_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    duration = float(value)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return duration
