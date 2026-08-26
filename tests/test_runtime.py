import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

from bot.adb import AdbClient
from bot.config import RuntimeConfig
from bot.runtime import build_adb_client, build_frame_source


def runtime_config():
    return RuntimeConfig(
        device_serial="runtime-serial",
        scrcpy_server_path=r"C:\scrcpy files\scrcpy-server.jar",
        adb_executable=r"C:\Android SDK\platform-tools\adb.exe",
        game_package="com.example.not-used-by-capture",
    )


def test_build_adb_client_propagates_only_adb_configuration():
    config = runtime_config()

    adb = build_adb_client(config)

    assert adb.adb_executable == r"C:\Android SDK\platform-tools\adb.exe"
    assert adb.serial == "runtime-serial"
    assert not hasattr(adb, "scrcpy_server_path")
    assert not hasattr(adb, "game_package")


def test_build_frame_source_propagates_config_without_external_operations():
    config = runtime_config()

    source = build_frame_source(config)

    assert isinstance(source.adb, AdbClient)
    assert source.adb.adb_executable == config.adb_executable
    assert source.adb.serial == config.device_serial
    assert source.scrcpy_server_path == config.scrcpy_server_path
    assert not source.is_running


def test_build_frame_source_reuses_explicit_adb_client_without_operations():
    config = runtime_config()
    runner = Mock()
    spawner = Mock()
    adb = AdbClient("test-adb", "test-serial", runner=runner, spawner=spawner)

    source = build_frame_source(config, adb_client=adb)

    assert source.adb is adb
    assert source.scrcpy_server_path == config.scrcpy_server_path
    runner.assert_not_called()
    spawner.assert_not_called()


def test_build_frame_source_accepts_explicit_stream_quality_limits():
    source = build_frame_source(
        runtime_config(), video_bit_rate=8_000_000, max_fps=30
    )

    assert source.video_bit_rate == 8_000_000
    assert source.max_fps == 30


def test_runtime_and_tools_import_without_external_side_effects(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import bot.runtime; import bot.screen; "
                "import tools.smoke_capture; import tools.screencap_batch; "
                "import tools.asset_capture; "
                "import tools.smoke_black_market_single_character"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
