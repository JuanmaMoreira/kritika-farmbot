"""Native refresh overtaken by queued PTS frames: Blade Dancer/run05."""
from unittest.mock import Mock

import cv2
import numpy as np

from bot.adb import AdbClient
from bot.capture import ScrcpyFrameSource


def source(clock):
    return ScrcpyFrameSource(Mock(spec=AdbClient), 'unused-server', clock=clock)


def test_queued_stream_cannot_replace_newer_native_pixels_or_sequence():
    capture = source(lambda: 110.)
    native = np.full((8, 16, 3), 200, dtype=np.uint8)
    queued = np.zeros_like(native)
    capture._publish(native, timestamp=100.)
    first = capture.get_frame()
    capture._publish(queued, timestamp=99.)
    kept = capture.get_frame()
    assert kept.sequence == first.sequence
    assert kept.timestamp == 100.
    assert np.array_equal(kept.image, native)
    capture._publish(queued, timestamp=101.)
    assert capture.get_frame().sequence == first.sequence + 1
    assert capture.get_frame().timestamp == 101.


def test_native_return_keeps_acquisition_when_receiver_runs_before_get_frame():
    capture = source(lambda: 200.)
    native = np.full((8, 16, 3), 200, dtype=np.uint8)
    capture.adb.capture_png.return_value = cv2.imencode('.png', native)[1].tobytes()
    original_publish = capture._publish

    def publish_then_queued(image, *, timestamp=None):
        original_publish(image, timestamp=timestamp)
        original_publish(np.zeros_like(image), timestamp=180.)

    capture._publish = publish_then_queued
    snapshot = capture.refresh_native()
    assert snapshot.timestamp == 200.
    assert np.array_equal(snapshot.image, native)


def test_slow_native_capture_retains_old_acquisition_time_and_stays_stale():
    now = [100.]
    capture = source(lambda: now[0])
    image = np.zeros((8, 16, 3), dtype=np.uint8)

    def slow_capture():
        now[0] += 7.3555226
        return cv2.imencode('.png', image)[1].tobytes()

    capture.adb.capture_png.side_effect = slow_capture
    snapshot = capture.refresh_native()
    assert snapshot.timestamp == 100.
    assert now[0] - snapshot.timestamp > 2.

def test_newer_receiver_during_native_capture_cannot_substitute_stream_pixels():
    now=[100.]
    capture=source(lambda:now[0])
    native=np.full((8,16,3),200,dtype=np.uint8)
    stream=np.zeros_like(native)
    def take(**kwargs):
        now[0]=101.
        capture._publish(stream,timestamp=101.)
        return cv2.imencode('.png',native)[1].tobytes()
    capture.adb.capture_png.side_effect=take
    frame=capture.refresh_native(timeout=3.)
    assert frame.timestamp==100. and np.array_equal(frame.image,native)
    assert capture.get_frame().timestamp==101.
    assert frame.sequence>capture.get_frame().sequence
    capture.adb.capture_png.assert_called_once_with(timeout=3.)
