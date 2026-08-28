"""Capture labeled World Boss evidence and execute explicit probe taps.

This is opt-in acquisition tooling, not a gameplay flow.  Every tap is supplied
explicitly by the operator, is sent through ``AdbClient``, and records clean
before/after frames without assigning semantic ground truth automatically.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import cv2

from bot.config import RuntimeConfig
from bot.geometry import relative_point_to_pixel
from bot.runtime import build_adb_client, build_frame_source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "world-boss-live"


def _safe_label(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    if not value or any(character not in allowed for character in value):
        raise argparse.ArgumentTypeError(
            "label must contain only lowercase letters, digits, '-' or '_'"
        )
    return value


def _relative_coordinate(value: str) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise argparse.ArgumentTypeError("relative coordinates must be in [0, 1]")
    return result


def _positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def _non_negative_float(value: str) -> float:
    result = float(value)
    if result < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return result


def _capture_frames(source, output: Path, label: str, count: int, interval: float):
    directory = output / label
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    previous_sequence = None
    for index in range(count):
        deadline = time.monotonic() + 5.0
        while True:
            snapshot = source.get_frame()
            if previous_sequence is None or snapshot.sequence > previous_sequence:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("no fresh frame arrived within 5 seconds")
            time.sleep(0.02)
        captured_at = dt.datetime.now(dt.timezone.utc)
        stamp = captured_at.strftime("%Y%m%dT%H%M%S_%fZ")
        path = directory / f"{stamp}_{index + 1:02d}.png"
        if not cv2.imwrite(str(path), snapshot.image):
            raise OSError(f"OpenCV could not save {path}")
        height, width = snapshot.image.shape[:2]
        records.append(
            {
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "label": label,
                "captured_at_utc": captured_at.isoformat(),
                "width": width,
                "height": height,
                "source_sequence": snapshot.sequence,
            }
        )
        previous_sequence = snapshot.sequence
        if index + 1 < count:
            time.sleep(interval)
    return records, snapshot


def _append_records(output: Path, records: list[dict]) -> None:
    manifest = output / "manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--label", required=True, type=_safe_label)
    capture.add_argument("--count", type=_positive_int, default=3)
    capture.add_argument("--interval", type=_non_negative_float, default=0.35)

    for command in ("tap", "swipe"):
        probe = subparsers.add_parser(command)
        probe.add_argument("--label", required=True, type=_safe_label)
        probe.add_argument("--x", required=True, type=_relative_coordinate)
        probe.add_argument("--y", required=True, type=_relative_coordinate)
        probe.add_argument("--after-delay", type=_non_negative_float, default=2.0)
        probe.add_argument("--after-count", type=_positive_int, default=3)
        probe.add_argument("--interval", type=_non_negative_float, default=0.35)
        if command == "swipe":
            probe.add_argument("--x2", required=True, type=_relative_coordinate)
            probe.add_argument("--y2", required=True, type=_relative_coordinate)
            probe.add_argument("--duration-ms", type=_positive_int, default=300)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    output.relative_to(PROJECT_ROOT)
    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    adb = build_adb_client(config)
    source = build_frame_source(config, adb_client=adb, max_fps=15)
    records = []
    with source:
        before, snapshot = _capture_frames(
            source,
            output,
            f"{args.label}-before" if args.command in ("tap", "swipe") else args.label,
            1 if args.command in ("tap", "swipe") else args.count,
            args.interval,
        )
        records.extend(before)
        if args.command in ("tap", "swipe"):
            height, width = snapshot.image.shape[:2]
            pixel = relative_point_to_pixel((args.x, args.y), width, height)
            if args.command == "tap":
                adb.tap(*pixel)
                probe = {
                    "kind": "tap",
                    "normalized_target": [args.x, args.y],
                    "pixel_target": list(pixel),
                }
            else:
                pixel_end = relative_point_to_pixel((args.x2, args.y2), width, height)
                adb.swipe(*pixel, *pixel_end, args.duration_ms)
                probe = {
                    "kind": "swipe",
                    "normalized_start": [args.x, args.y],
                    "normalized_end": [args.x2, args.y2],
                    "pixel_start": list(pixel),
                    "pixel_end": list(pixel_end),
                    "duration_ms": args.duration_ms,
                }
            time.sleep(args.after_delay)
            after, _ = _capture_frames(
                source,
                output,
                f"{args.label}-after",
                args.after_count,
                args.interval,
            )
            for record in before + after:
                record["probe"] = probe
            records = before + after
    _append_records(output, records)
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
