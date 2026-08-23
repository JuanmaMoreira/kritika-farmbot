import os
import queue
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from bot.adb import AdbClient, AdbError
from bot.capture import CaptureError, CaptureTimeoutError, ScrcpyFrameSource


def metadata():
    return b"\x00" + (b"device" + b"\x00" * 58) + b"h264" + (b"\x00" * 8)


def packet(payload, pts=1):
    return struct.pack(">QI", pts, len(payload)) + payload


class FakeSocket:
    def __init__(self, initial=b"", connect_error=None):
        self._chunks = queue.Queue()
        self._buffer = bytearray()
        self._closed = False
        self.timeout = None
        self.connected_to = None
        self.connect_error = connect_error
        if initial:
            self.add(initial)

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, address):
        if self.connect_error is not None:
            raise self.connect_error
        self.connected_to = address

    def recv(self, size):
        while not self._buffer:
            if self._closed:
                return b""
            try:
                chunk = self._chunks.get(timeout=self.timeout)
            except queue.Empty as error:
                raise socket.timeout from error
            if chunk is None:
                self._closed = True
                return b""
            self._buffer.extend(chunk)
        result = bytes(self._buffer[:size])
        del self._buffer[:size]
        return result

    def add(self, data):
        self._chunks.put(data)

    def close(self):
        if not self._closed:
            self._closed = True
            self._chunks.put(None)

    @property
    def closed(self):
        return self._closed


class FakeDecoder:
    def __init__(self, frames=None, failure_payload=None):
        self.frames = frames or {}
        self.failure_payload = failure_payload
        self.closed = False
        self.calls = []

    def decode(self, payload, pts):
        self.calls.append((payload, pts))
        if payload == self.failure_payload:
            raise RuntimeError("decoder exploded")
        image = self.frames.get(payload)
        return [] if image is None else [image]

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self):
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


def fake_adb(process=None):
    adb = Mock(spec=AdbClient)
    adb.spawn_shell.return_value = process or FakeProcess()
    return adb


def make_source(adb, fake_socket, decoder, **overrides):
    options = {
        "startup_delay": 0,
        "connect_timeout": 0.2,
        "first_frame_timeout": 0.2,
        "receive_timeout": 0.02,
        "shutdown_timeout": 0.2,
        "socket_factory": Mock(return_value=fake_socket),
        "decoder_factory": Mock(return_value=decoder),
    }
    options.update(overrides)
    return ScrcpyFrameSource(adb, r"C:\scrcpy files\scrcpy-server.jar", **options)


def wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")


def test_import_has_no_process_socket_or_file_side_effects(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [sys.executable, "-c", "import bot.capture"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_construction_is_explicit_and_has_no_side_effects():
    adb = fake_adb()
    socket_factory = Mock()
    decoder_factory = Mock()

    source = ScrcpyFrameSource(
        adb,
        r"C:\scrcpy files\scrcpy-server.jar",
        socket_factory=socket_factory,
        decoder_factory=decoder_factory,
    )

    assert source.adb is adb
    assert source.scrcpy_server_path == r"C:\scrcpy files\scrcpy-server.jar"
    assert not source.is_running
    adb.push.assert_not_called()
    socket_factory.assert_not_called()
    decoder_factory.assert_not_called()


def test_start_prepares_scrcpy_and_produces_first_frame():
    frame = np.full((4, 8, 3), 7, dtype=np.uint8)
    fake_socket = FakeSocket(metadata() + packet(b"frame-1"))
    decoder = FakeDecoder({b"frame-1": frame})
    process = FakeProcess()
    adb = fake_adb(process)
    source = make_source(adb, fake_socket, decoder)

    assert source.start() is source

    adb.push.assert_called_once_with(
        r"C:\scrcpy files\scrcpy-server.jar", source.REMOTE_SERVER_PATH
    )
    adb.forward.assert_called_once_with("tcp:27183", "localabstract:scrcpy")
    adb.spawn_shell.assert_called_once_with(
        "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
        "app_process",
        "/",
        "com.genymobile.scrcpy.Server",
        "3.3.4",
        "tunnel_forward=true",
        "video_bit_rate=2000000",
        "max_size=0",
        "audio=false",
        "control=false",
    )
    assert fake_socket.connected_to == ("127.0.0.1", 27183)
    assert source.is_running
    np.testing.assert_array_equal(source.get_frame().image, frame)

    source.stop()


def test_capture_can_bound_stream_rate_and_raise_bitrate_for_live_tooling():
    source = ScrcpyFrameSource(
        fake_adb(),
        "server.jar",
        video_bit_rate=8_000_000,
        max_fps=30,
    )

    assert "video_bit_rate=8000000" in source._server_arguments()
    assert "max_fps=30" in source._server_arguments()


def test_scrcpy_334_config_packet_is_prepended_to_next_media_packet():
    frame = np.full((4, 8, 3), 7, dtype=np.uint8)
    config_flag = ScrcpyFrameSource.CONFIG_PACKET_FLAG
    key_frame_flag = ScrcpyFrameSource.KEY_FRAME_PACKET_FLAG
    fake_socket = FakeSocket(
        metadata()
        + packet(b"sps-pps", pts=config_flag)
        + packet(b"key-frame", pts=key_frame_flag | 123)
    )
    decoder = FakeDecoder({b"sps-ppskey-frame": frame})
    source = make_source(fake_adb(), fake_socket, decoder)

    source.start()

    assert decoder.calls == [(b"sps-ppskey-frame", 123)]
    np.testing.assert_array_equal(source.get_frame().image, frame)
    source.stop()


def test_get_frame_before_first_frame_is_explicit_error():
    source = make_source(fake_adb(), FakeSocket(), FakeDecoder())

    with pytest.raises(CaptureError, match="No decoded frame"):
        source.get_frame()


def test_snapshots_have_sequence_timestamp_dimensions_and_copy_ownership():
    first = np.full((1224, 2712, 3), 10, dtype=np.uint8)
    second = np.full((1224, 2712, 3), 20, dtype=np.uint8)
    fake_socket = FakeSocket(metadata() + packet(b"first"))
    decoder = FakeDecoder({b"first": first, b"second": second})
    clock = Mock(side_effect=[100.5, 101.5])
    source = make_source(fake_adb(), fake_socket, decoder, clock=clock)

    source.start()
    first_snapshot = source.get_frame()
    assert first_snapshot.sequence == 1
    assert first_snapshot.timestamp == 100.5
    assert first_snapshot.width == 2712
    assert first_snapshot.height == 1224

    first_snapshot.image[:] = 99
    assert np.all(source.get_frame().image == 10)

    fake_socket.add(packet(b"second", pts=2))
    wait_until(lambda: source.get_frame().sequence == 2)
    second_snapshot = source.get_frame()
    assert second_snapshot.sequence == 2
    assert second_snapshot.timestamp == 101.5
    assert np.all(second_snapshot.image == 20)

    source.stop()


def test_start_twice_is_rejected():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    source = make_source(
        fake_adb(),
        FakeSocket(metadata() + packet(b"frame")),
        FakeDecoder({b"frame": frame}),
    )

    source.start()
    with pytest.raises(CaptureError, match="already started"):
        source.start()
    source.stop()


def test_stop_releases_every_resource_and_is_idempotent():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    fake_socket = FakeSocket(metadata() + packet(b"frame"))
    decoder = FakeDecoder({b"frame": frame})
    process = FakeProcess()
    adb = fake_adb(process)
    source = make_source(adb, fake_socket, decoder)

    source.stop()
    source.start()
    source.stop()
    source.stop()

    assert fake_socket.closed
    assert process.terminated
    assert process.waited
    assert decoder.closed
    adb.remove_forward.assert_called_once_with("tcp:27183")
    assert not source.is_running


def test_push_failure_does_not_clean_unacquired_resources():
    adb = fake_adb()
    adb.push.side_effect = AdbError(("adb", "push"))
    socket_factory = Mock()
    source = ScrcpyFrameSource(
        adb,
        "server.jar",
        startup_delay=0,
        socket_factory=socket_factory,
        decoder_factory=Mock(),
    )

    with pytest.raises(CaptureError, match="Could not start"):
        source.start()

    adb.forward.assert_not_called()
    adb.spawn_shell.assert_not_called()
    adb.remove_forward.assert_not_called()
    socket_factory.assert_not_called()


def test_forward_failure_does_not_remove_uncreated_forward():
    adb = fake_adb()
    adb.forward.side_effect = AdbError(("adb", "forward"))
    source = make_source(adb, FakeSocket(), FakeDecoder())

    with pytest.raises(CaptureError, match="Could not start"):
        source.start()

    adb.spawn_shell.assert_not_called()
    adb.remove_forward.assert_not_called()


def test_spawn_failure_removes_created_forward():
    adb = fake_adb()
    adb.spawn_shell.side_effect = AdbError(("adb", "shell"))
    source = make_source(adb, FakeSocket(), FakeDecoder())

    with pytest.raises(CaptureError, match="Could not start"):
        source.start()

    adb.remove_forward.assert_called_once_with("tcp:27183")


def test_cleanup_failure_does_not_hide_original_start_failure():
    start_error = AdbError(("adb", "shell"), reason="spawn failed")
    adb = fake_adb()
    adb.spawn_shell.side_effect = start_error
    adb.remove_forward.side_effect = AdbError(
        ("adb", "forward", "--remove"), reason="cleanup failed"
    )
    source = make_source(adb, FakeSocket(), FakeDecoder())

    with pytest.raises(CaptureError, match="spawn failed") as captured:
        source.start()

    assert captured.value.__cause__ is start_error
    adb.remove_forward.assert_called_once_with("tcp:27183")


def test_keyboard_interrupt_during_start_cleans_up_and_propagates():
    process = FakeProcess()
    adb = fake_adb(process)
    socket_factory = Mock(side_effect=KeyboardInterrupt)
    source = ScrcpyFrameSource(
        adb,
        "server.jar",
        startup_delay=0,
        socket_factory=socket_factory,
        decoder_factory=Mock(),
    )

    with pytest.raises(KeyboardInterrupt):
        source.start()

    assert process.terminated
    assert process.waited
    adb.remove_forward.assert_called_once_with("tcp:27183")


def test_socket_failure_terminates_process_and_removes_forward():
    process = FakeProcess()
    adb = fake_adb(process)
    source = ScrcpyFrameSource(
        adb,
        "server.jar",
        startup_delay=0,
        socket_factory=Mock(side_effect=OSError("socket unavailable")),
        decoder_factory=Mock(),
    )

    with pytest.raises(CaptureError, match="socket unavailable"):
        source.start()

    assert process.terminated
    assert process.waited
    adb.remove_forward.assert_called_once_with("tcp:27183")


def test_first_frame_timeout_cleans_all_acquired_resources():
    fake_socket = FakeSocket(metadata())
    decoder = FakeDecoder()
    process = FakeProcess()
    adb = fake_adb(process)
    source = make_source(
        adb, fake_socket, decoder, first_frame_timeout=0.03, receive_timeout=0.01
    )

    with pytest.raises(CaptureTimeoutError, match="first scrcpy frame"):
        source.start()

    assert fake_socket.closed
    assert decoder.closed
    assert process.terminated
    adb.remove_forward.assert_called_once_with("tcp:27183")
    assert not source.is_running


def test_receiver_failure_is_observable_after_successful_start():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    fake_socket = FakeSocket(metadata() + packet(b"frame"))
    source = make_source(
        fake_adb(), fake_socket, FakeDecoder({b"frame": frame})
    )

    source.start()
    fake_socket.close()
    wait_until(lambda: source.failure is not None)

    assert not source.is_running
    with pytest.raises(CaptureError, match="closed unexpectedly"):
        source.get_frame()
    source.stop()


def test_context_manager_starts_and_stops_source():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    fake_socket = FakeSocket(metadata() + packet(b"frame"))
    process = FakeProcess()
    source = make_source(
        fake_adb(process), fake_socket, FakeDecoder({b"frame": frame})
    )

    with source as active:
        assert active is source
        assert source.is_running

    assert fake_socket.closed
    assert process.terminated
    assert not source.is_running


def test_context_manager_cleans_up_when_body_raises():
    frame = np.zeros((2, 3, 3), dtype=np.uint8)
    fake_socket = FakeSocket(metadata() + packet(b"frame"))
    process = FakeProcess()
    source = make_source(
        fake_adb(process), fake_socket, FakeDecoder({b"frame": frame})
    )

    with pytest.raises(RuntimeError, match="body failed"):
        with source:
            raise RuntimeError("body failed")

    assert fake_socket.closed
    assert process.terminated
    assert not source.is_running
