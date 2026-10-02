"""Static ad end cards must get real pixels and acquisition timestamps."""
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.adb import AdbClient, AdbError, AdbTimeoutError
from bot.capture import ScrcpyFrameSource, CaptureError


def png(value):
    return cv2.imencode('.png', np.full((12, 20, 3), value, np.uint8))[1].tobytes()


def test_binary_screencap_uses_configured_device_and_no_shell_interpolation():
    data = png(123)
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, data, b''))
    adb = AdbClient('adb-custom', 'configured-device', runner=runner)
    assert adb.capture_png() == data
    runner.assert_called_once_with(
        ['adb-custom', '-s', 'configured-device', 'exec-out', 'screencap', '-p'],
        capture_output=True, text=False, timeout=10., check=False, shell=False)


@pytest.mark.parametrize('data', [b'not PNG', 'text instead of binary'])
def test_non_png_never_publishes_a_fake_fresh_frame(data):
    adb = AdbClient('adb', 'device', runner=Mock(
        return_value=subprocess.CompletedProcess([], 0, data, b'')))
    with pytest.raises(AdbError, match='not PNG'):
        adb.capture_png()


def test_capture_timeout_keeps_typed_adb_failure():
    adb = AdbClient('adb', 'device', runner=Mock(
        side_effect=subprocess.TimeoutExpired('screencap', 2)))
    with pytest.raises(AdbTimeoutError):
        adb.capture_png(timeout=2)


def test_native_refresh_advances_shared_sequence_and_preserves_old_frame():
    source = ScrcpyFrameSource(SimpleNamespace(capture_png=lambda:png(222)),
                              'server', clock=lambda:42.)
    source._publish(np.zeros((12,20,3), np.uint8), timestamp=1.)
    old = source.get_frame()
    fresh = source.refresh_native()
    assert (old.sequence, old.timestamp, int(old.image.mean())) == (1, 1., 0)
    assert (fresh.sequence, fresh.timestamp, int(fresh.image.mean())) == (2, 42., 222)
    fresh.image[:] = 0
    assert int(source.get_frame().image.mean()) == 222


def test_invalid_native_decode_leaves_last_real_frame_untouched():
    source = ScrcpyFrameSource(SimpleNamespace(capture_png=lambda:b'broken'), 'server')
    source._publish(np.zeros((12,20,3), np.uint8), timestamp=1.)
    with pytest.raises(CaptureError):
        source.refresh_native()
    assert source.get_frame().sequence == 1
