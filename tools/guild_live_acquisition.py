"""Record bounded, operator-driven Guild evidence without sending device input.

The operator performs navigation and gameplay actions on the device.  This
tool only records fresh full frames plus non-sensitive timing metadata.  It is
acquisition tooling, not runtime navigation or a Guild flow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import queue
import sys
import threading
import time

import cv2

from bot.config import RuntimeConfig
from bot.runtime import build_frame_source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "guild-live"


def _safe_label(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
    if not value or any(character not in allowed for character in value):
        raise argparse.ArgumentTypeError(
            "label must contain only lowercase letters, digits, '-' or '_'"
        )
    return value


def _positive_float(value: str) -> float:
    result = float(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--label", required=True, type=_safe_label)
    parser.add_argument("--interval", type=_positive_float, default=0.25)
    parser.add_argument("--max-seconds", type=_positive_float, default=90.0)
    return parser.parse_args(argv)


def _read_stop_signal(signals: queue.SimpleQueue[str]) -> None:
    try:
        signals.put(sys.stdin.readline())
    except OSError:
        signals.put("")


def _append_records(output: Path, records: list[dict[str, object]]) -> None:
    manifest = output / "manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    output.relative_to(PROJECT_ROOT)
    directory = output / args.label
    directory.mkdir(parents=True, exist_ok=True)

    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    source = build_frame_source(config, max_fps=15)
    signals: queue.SimpleQueue[str] = queue.SimpleQueue()
    records: list[dict[str, object]] = []

    with source:
        print(
            "RECORDING_READY: perform the human action; send ENTER to stop",
            flush=True,
        )
        threading.Thread(
            target=_read_stop_signal,
            args=(signals,),
            name="guild-acquisition-stop-signal",
            daemon=True,
        ).start()
        started = time.monotonic()
        next_capture = started
        previous_sequence: int | None = None
        while time.monotonic() - started < args.max_seconds:
            try:
                signals.get_nowait()
                break
            except queue.Empty:
                pass

            now = time.monotonic()
            if now < next_capture:
                time.sleep(min(0.02, next_capture - now))
                continue
            snapshot = source.get_frame()
            if snapshot.sequence == previous_sequence:
                time.sleep(0.01)
                continue
            captured_at = dt.datetime.now(dt.timezone.utc)
            index = len(records) + 1
            stamp = captured_at.strftime("%Y%m%dT%H%M%S_%fZ")
            path = directory / f"{stamp}_{index:04d}.png"
            if not cv2.imwrite(str(path), snapshot.image):
                raise OSError(f"OpenCV could not save {path}")
            height, width = snapshot.image.shape[:2]
            records.append(
                {
                    "path": path.relative_to(PROJECT_ROOT).as_posix(),
                    "label": args.label,
                    "captured_at_utc": captured_at.isoformat(),
                    "elapsed_seconds": time.monotonic() - started,
                    "width": width,
                    "height": height,
                    "source_sequence": snapshot.sequence,
                    "capture_method": "human_action_observed",
                }
            )
            previous_sequence = snapshot.sequence
            next_capture = max(next_capture + args.interval, time.monotonic())

    _append_records(output, records)
    print(
        json.dumps(
            {
                "label": args.label,
                "frame_count": len(records),
                "duration_seconds": (
                    records[-1]["elapsed_seconds"] if records else 0.0
                ),
            },
            indent=2,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
