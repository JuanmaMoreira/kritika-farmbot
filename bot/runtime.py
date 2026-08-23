"""Minimal composition root for the implemented 0.2 infrastructure."""

from __future__ import annotations

from bot.adb import AdbClient
from bot.capture import ScrcpyFrameSource
from bot.config import RuntimeConfig


def build_adb_client(config: RuntimeConfig) -> AdbClient:
    """Construct the ADB boundary without starting external operations."""

    return AdbClient.from_config(config)


def build_frame_source(
    config: RuntimeConfig,
    *,
    adb_client: AdbClient | None = None,
    video_bit_rate: int = 2_000_000,
    max_fps: int | None = None,
) -> ScrcpyFrameSource:
    """Construct capture with explicit config and an optional shared ADB client."""

    adb = adb_client if adb_client is not None else build_adb_client(config)
    return ScrcpyFrameSource(
        adb=adb,
        scrcpy_server_path=config.scrcpy_server_path,
        video_bit_rate=video_bit_rate,
        max_fps=max_fps,
    )
