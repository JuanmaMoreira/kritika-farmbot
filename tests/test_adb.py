import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from bot.adb import AdbClient, AdbError, AdbTimeoutError
from bot.config import RuntimeConfig


def successful_runner(stdout=""):
    return Mock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout=stdout, stderr=""
        )
    )


def assert_command(runner, command, timeout=10.0):
    runner.assert_called_once_with(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


def test_constructs_with_custom_executable_serial_and_timeout():
    runner = successful_runner()

    client = AdbClient(
        r"C:\Program Files\Android SDK\adb.exe",
        "custom-serial",
        default_timeout=4.5,
        runner=runner,
    )

    assert client.adb_executable == r"C:\Program Files\Android SDK\adb.exe"
    assert client.serial == "custom-serial"
    assert client.default_timeout == 4.5
    runner.assert_not_called()


def test_constructs_from_runtime_config_without_retaining_unneeded_values():
    config = RuntimeConfig(
        device_serial="config-serial",
        scrcpy_server_path="not-needed-by-adb.jar",
        adb_executable="config-adb",
        game_package="com.example.not-needed-by-adb",
    )

    client = AdbClient.from_config(config, runner=successful_runner())

    assert client.adb_executable == "config-adb"
    assert client.serial == "config-serial"
    assert not hasattr(client, "scrcpy_server_path")
    assert not hasattr(client, "game_package")


@pytest.mark.parametrize(
    ("adb_executable", "serial", "timeout"),
    [
        ("", "serial", 10),
        ("adb", "  ", 10),
        ("adb", "serial", 0),
        ("adb", "serial", float("inf")),
    ],
)
def test_rejects_invalid_construction(adb_executable, serial, timeout):
    with pytest.raises(ValueError):
        AdbClient(adb_executable, serial, default_timeout=timeout)


def test_import_has_no_external_side_effects(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [sys.executable, "-c", "import bot.adb"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_get_state_uses_device_scoped_base_command_and_returns_state():
    runner = successful_runner("device\n")
    client = AdbClient(
        r"C:\Program Files\Android SDK\adb.exe", "SERIAL-123", runner=runner
    )

    assert client.get_state() == "device"
    assert_command(
        runner,
        [
            r"C:\Program Files\Android SDK\adb.exe",
            "-s",
            "SERIAL-123",
            "get-state",
        ],
    )


def test_operation_timeout_overrides_client_default():
    runner = successful_runner("device\n")
    client = AdbClient("adb", "serial", default_timeout=20, runner=runner)

    client.get_state(timeout=2.5)

    assert_command(runner, ["adb", "-s", "serial", "get-state"], timeout=2.5)


@pytest.mark.parametrize("timeout", [0, -1, float("nan")])
def test_rejects_invalid_operation_timeout_without_running(timeout):
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    with pytest.raises(ValueError, match="timeout"):
        client.get_state(timeout=timeout)

    runner.assert_not_called()


def test_shell_builds_non_interactive_device_command():
    runner = successful_runner("Physical size: 1920x1080\n")
    client = AdbClient("adb", "serial", runner=runner)

    result = client.shell("wm", "size")

    assert result.stdout == "Physical size: 1920x1080\n"
    assert_command(runner, ["adb", "-s", "serial", "shell", "wm", "size"])


def test_tap_uses_absolute_pixel_coordinates():
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    client.tap(100, 200)

    assert_command(
        runner, ["adb", "-s", "serial", "shell", "input", "tap", "100", "200"]
    )


def test_swipe_includes_coordinates_and_duration():
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    client.swipe(10, 20, 300, 400, 750)

    assert_command(
        runner,
        [
            "adb",
            "-s",
            "serial",
            "shell",
            "input",
            "swipe",
            "10",
            "20",
            "300",
            "400",
            "750",
        ],
    )


def test_push_preserves_local_path_with_spaces_and_remote_path():
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    client.push(
        Path(r"C:\Program Files\scrcpy\scrcpy-server.jar"),
        "/data/local/tmp/scrcpy-server.jar",
    )

    assert_command(
        runner,
        [
            "adb",
            "-s",
            "serial",
            "push",
            r"C:\Program Files\scrcpy\scrcpy-server.jar",
            "/data/local/tmp/scrcpy-server.jar",
        ],
    )


def test_forward_uses_explicit_endpoints():
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    client.forward("tcp:27183", "localabstract:scrcpy")

    assert_command(
        runner,
        [
            "adb",
            "-s",
            "serial",
            "forward",
            "tcp:27183",
            "localabstract:scrcpy",
        ],
    )


def test_remove_forward_uses_local_endpoint():
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    client.remove_forward("tcp:27183")

    assert_command(
        runner,
        ["adb", "-s", "serial", "forward", "--remove", "tcp:27183"],
    )


def test_nonzero_return_code_becomes_adb_error_with_process_context():
    runner = Mock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=1, stdout="device output", stderr="device offline"
        )
    )
    client = AdbClient("adb", "SERIAL", runner=runner)

    with pytest.raises(AdbError) as captured:
        client.get_state()

    error = captured.value
    assert error.command == ("adb", "-s", "SERIAL", "get-state")
    assert error.returncode == 1
    assert error.stdout == "device output"
    assert error.stderr == "device offline"
    assert "device offline" in str(error)
    assert "returncode=1" in str(error)


def test_timeout_becomes_adb_timeout_error_with_command_and_output():
    runner = Mock(
        side_effect=subprocess.TimeoutExpired(
            cmd=["adb"], timeout=3, output=b"partial output", stderr=b"still waiting"
        )
    )
    client = AdbClient("adb", "SERIAL", default_timeout=3, runner=runner)

    with pytest.raises(AdbTimeoutError) as captured:
        client.shell("long-running-command")

    error = captured.value
    assert error.command == ("adb", "-s", "SERIAL", "shell", "long-running-command")
    assert error.timeout == 3
    assert error.stdout == "partial output"
    assert error.stderr == "still waiting"
    assert "timed out after 3 seconds" in str(error)


def test_process_start_failure_becomes_adb_error():
    client = AdbClient(
        "missing-adb", "SERIAL", runner=Mock(side_effect=FileNotFoundError("not found"))
    )

    with pytest.raises(AdbError, match="Could not execute ADB") as captured:
        client.get_state()

    assert captured.value.command == ("missing-adb", "-s", "SERIAL", "get-state")
    assert captured.value.__cause__.__class__ is FileNotFoundError


@pytest.mark.parametrize(
    "operation",
    [
        lambda client: client.tap(-1, 0),
        lambda client: client.tap(0, -1),
        lambda client: client.tap(1.5, 2),
        lambda client: client.swipe(-1, 0, 1, 1, 100),
        lambda client: client.swipe(0, 0, 1, 1, 0),
    ],
)
def test_rejects_invalid_pixel_input_without_running(operation):
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    with pytest.raises(ValueError):
        operation(client)

    runner.assert_not_called()


@pytest.mark.parametrize(
    "operation",
    [
        lambda client: client.shell(),
        lambda client: client.shell(""),
        lambda client: client.push("", "/data/file"),
        lambda client: client.push("local.file", ""),
        lambda client: client.forward("", "localabstract:scrcpy"),
        lambda client: client.forward("tcp:1234", ""),
        lambda client: client.remove_forward(""),
    ],
)
def test_rejects_empty_command_values_without_running(operation):
    runner = successful_runner()
    client = AdbClient("adb", "serial", runner=runner)

    with pytest.raises(ValueError):
        operation(client)

    runner.assert_not_called()
