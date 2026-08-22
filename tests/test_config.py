import os
import subprocess
import sys
from pathlib import Path

import pytest

from bot.config import DEFAULT_GAME_PACKAGE, RuntimeConfig


def test_explicit_config_construction_does_not_need_environment():
    config = RuntimeConfig(
        device_serial="test-device",
        scrcpy_server_path="tools/scrcpy-server.jar",
        adb_executable="custom-adb",
        game_package="com.example.game",
    )

    assert config.device_serial == "test-device"
    assert config.scrcpy_server_path == "tools/scrcpy-server.jar"
    assert config.adb_executable == "custom-adb"
    assert config.game_package == "com.example.game"


def test_explicit_config_has_safe_defaults():
    config = RuntimeConfig(
        device_serial="test-device",
        scrcpy_server_path="scrcpy-server.jar",
    )

    assert config.adb_executable == "adb"
    assert config.game_package == DEFAULT_GAME_PACKAGE


def test_from_env_reads_supplied_mapping():
    config = RuntimeConfig.from_env(
        {
            "DISPOSITIVO_ADB": "env-device",
            "SCRCPY_SERVER_PATH": "env/scrcpy-server.jar",
            "ADB_PATH": "env-adb",
            "GAME_PACKAGE": "com.example.fromenv",
        }
    )

    assert config == RuntimeConfig(
        device_serial="env-device",
        scrcpy_server_path="env/scrcpy-server.jar",
        adb_executable="env-adb",
        game_package="com.example.fromenv",
    )


def test_from_env_reads_dotenv_only_when_requested(tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "DISPOSITIVO_ADB=dotenv-device\n"
        "SCRCPY_SERVER_PATH=dotenv-server.jar\n"
        "ADB_PATH=dotenv-adb\n",
        encoding="utf-8",
    )

    config = RuntimeConfig.from_env({}, dotenv_path=dotenv_path)

    assert config.device_serial == "dotenv-device"
    assert config.scrcpy_server_path == "dotenv-server.jar"
    assert config.adb_executable == "dotenv-adb"


def test_environment_mapping_overrides_dotenv(tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "DISPOSITIVO_ADB=dotenv-device\n"
        "SCRCPY_SERVER_PATH=dotenv-server.jar\n",
        encoding="utf-8",
    )

    config = RuntimeConfig.from_env(
        {
            "DISPOSITIVO_ADB": "mapping-device",
            "SCRCPY_SERVER_PATH": "mapping-server.jar",
        },
        dotenv_path=dotenv_path,
    )

    assert config.device_serial == "mapping-device"
    assert config.scrcpy_server_path == "mapping-server.jar"


@pytest.mark.parametrize("missing_name", ["DISPOSITIVO_ADB", "SCRCPY_SERVER_PATH"])
def test_from_env_rejects_missing_required_values(missing_name):
    values = {
        "DISPOSITIVO_ADB": "test-device",
        "SCRCPY_SERVER_PATH": "scrcpy-server.jar",
    }
    del values[missing_name]

    with pytest.raises(ValueError, match=missing_name):
        RuntimeConfig.from_env(values)


@pytest.mark.parametrize(
    "field_name",
    ["device_serial", "scrcpy_server_path", "adb_executable", "game_package"],
)
def test_explicit_config_rejects_blank_values(field_name):
    values = {
        "device_serial": "test-device",
        "scrcpy_server_path": "scrcpy-server.jar",
        "adb_executable": "adb",
        "game_package": "com.example.game",
    }
    values[field_name] = "  "

    with pytest.raises(ValueError, match=field_name):
        RuntimeConfig(**values)


def test_new_modules_import_without_external_side_effects(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [sys.executable, "-c", "import bot.config; import bot.geometry"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
