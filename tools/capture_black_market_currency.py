"""Capture one passive Black Market frame for slot-currency curation.

This opt-in acquisition tool owns only capture. It sends no Android input and
does not infer slot ground truth; the saved PNG must be reviewed separately.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import cv2

from bot.config import RuntimeConfig
from bot.runtime import build_adb_client, build_frame_source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "screencaps" / "semantic" / "black_market_currency"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture one passive full-resolution Black Market frame."
    )
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    adb = build_adb_client(config)
    if adb.get_state() != "device":
        raise RuntimeError("ADB device is not authorized/ready")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    destination = args.output_dir / f"{timestamp}.png"

    source = build_frame_source(config, adb_client=adb)
    with source:
        snapshot = source.get_frame()

    if not cv2.imwrite(str(destination), snapshot.image):
        raise RuntimeError(f"Could not write frame: {destination}")

    print(
        f"saved={destination.relative_to(PROJECT_ROOT).as_posix()} "
        f"sequence={snapshot.sequence} shape={snapshot.image.shape}"
    )
    print(f"cleanup source_stopped={not source.is_running}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
