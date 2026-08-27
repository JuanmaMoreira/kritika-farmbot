"""Explicit runtime configuration for the 0.2 infrastructure layers.

Importing this module does not read the environment or a ``.env`` file. Use
``RuntimeConfig.from_env()`` at the composition root, or instantiate the
dataclass directly in tests and other controlled callers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


DEFAULT_ADB_EXECUTABLE = "adb"
DEFAULT_GAME_PACKAGE = "com.gamevil.kritikamobile.android.google.global.normal"
DEFAULT_CHARACTER_COUNT = 28


@dataclass(frozen=True)
class RuntimeConfig:
    """Host and device values required by future device/capture adapters."""

    device_serial: str
    scrcpy_server_path: str
    adb_executable: str = DEFAULT_ADB_EXECUTABLE
    game_package: str = DEFAULT_GAME_PACKAGE

    def __post_init__(self) -> None:
        for field_name in (
            "device_serial",
            "scrcpy_server_path",
            "adb_executable",
            "game_package",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        dotenv_path: str | os.PathLike[str] | None = None,
    ) -> "RuntimeConfig":
        """Build config from a mapping, optionally preceded by a ``.env`` file.

        Values from ``environ`` (or ``os.environ`` when omitted) override values
        loaded from ``dotenv_path``. A dotenv file is read only when its path is
        passed explicitly, keeping both import and test construction predictable.
        """

        values: dict[str, str] = {}
        if dotenv_path is not None:
            path_values = dotenv_values(Path(dotenv_path))
            values.update(
                {key: value for key, value in path_values.items() if value is not None}
            )

        source = os.environ if environ is None else environ
        values.update(source)

        return cls(
            device_serial=_required(values, "DISPOSITIVO_ADB"),
            scrcpy_server_path=_required(values, "SCRCPY_SERVER_PATH"),
            adb_executable=values.get("ADB_PATH", DEFAULT_ADB_EXECUTABLE),
            game_package=values.get("GAME_PACKAGE", DEFAULT_GAME_PACKAGE),
        )


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required runtime setting: {name}")
    return value
