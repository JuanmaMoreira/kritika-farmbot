"""Intentional hardware smoke test for the 0.2 scrcpy capture stack."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.adb import AdbError
from bot.capture import CaptureError, FrameSnapshot, ScrcpyFrameSource
from bot.config import RuntimeConfig
from bot.runtime import build_adb_client, build_frame_source


DEFAULT_FRAME_COUNT = 5
MIN_FRAME_COUNT = 3
NEXT_FRAME_TIMEOUT = 3.0


class SmokeValidationError(RuntimeError):
    """A real frame or lifecycle invariant failed during the smoke test."""


@dataclass(frozen=True)
class SmokeReport:
    adb_state: str
    frame_count: int
    first_frame_seconds: float
    shape: tuple[int, int, int]
    dtype: str
    first_sequence: int
    last_sequence: int
    first_timestamp: float
    last_timestamp: float
    forward_removed: bool


def run_smoke(config: RuntimeConfig, *, frame_count: int = DEFAULT_FRAME_COUNT) -> SmokeReport:
    """Run the real capture diagnostic without issuing device input commands."""

    if frame_count < MIN_FRAME_COUNT:
        raise ValueError(f"frame_count must be at least {MIN_FRAME_COUNT}")

    adb = build_adb_client(config)
    state = adb.get_state()
    if state != "device":
        raise SmokeValidationError(f"ADB state is {state!r}, expected 'device'")

    source = build_frame_source(config, adb_client=adb)
    started_at = time.monotonic()
    with source:
        first = source.get_frame()
        first_frame_seconds = time.monotonic() - started_at
        expected_shape, expected_dtype = _validate_frame(first)
        previous_sequence = first.sequence
        previous_timestamp = first.timestamp
        first_sequence = first.sequence
        first_timestamp = first.timestamp

        for _ in range(1, frame_count):
            snapshot = _wait_for_new_frame(source, previous_sequence)
            shape, dtype = _validate_frame(snapshot)
            if shape != expected_shape or dtype != expected_dtype:
                raise SmokeValidationError(
                    "Frame shape or dtype changed during the smoke test"
                )
            if snapshot.sequence <= previous_sequence:
                raise SmokeValidationError("Frame sequence did not increase")
            if snapshot.timestamp < previous_timestamp:
                raise SmokeValidationError("Frame timestamp moved backwards")
            previous_sequence = snapshot.sequence
            previous_timestamp = snapshot.timestamp

    if source.is_running:
        raise SmokeValidationError("Capture source still reports running after shutdown")

    remaining_forwards = adb.list_forwards()
    forward_removed = not any(
        _is_source_forward(rule, adb.serial, source.local_endpoint)
        for rule in remaining_forwards
    )
    if not forward_removed:
        raise SmokeValidationError(
            f"Forward {source.local_endpoint} remains after capture shutdown"
        )

    return SmokeReport(
        adb_state=state,
        frame_count=frame_count,
        first_frame_seconds=first_frame_seconds,
        shape=expected_shape,
        dtype=expected_dtype,
        first_sequence=first_sequence,
        last_sequence=previous_sequence,
        first_timestamp=first_timestamp,
        last_timestamp=previous_timestamp,
        forward_removed=forward_removed,
    )


def _wait_for_new_frame(
    source: ScrcpyFrameSource, previous_sequence: int
) -> FrameSnapshot:
    deadline = time.monotonic() + NEXT_FRAME_TIMEOUT
    while time.monotonic() < deadline:
        snapshot = source.get_frame()
        if snapshot.sequence > previous_sequence:
            return snapshot
        time.sleep(0.01)
    raise SmokeValidationError(
        f"No frame newer than sequence {previous_sequence} arrived "
        f"within {NEXT_FRAME_TIMEOUT:g} seconds"
    )


def _is_source_forward(rule: str, serial: str, local_endpoint: str) -> bool:
    fields = rule.split()
    return len(fields) >= 2 and fields[0] == serial and fields[1] == local_endpoint


def _validate_frame(snapshot: FrameSnapshot) -> tuple[tuple[int, int, int], str]:
    image = snapshot.image
    if not isinstance(image, np.ndarray):
        raise SmokeValidationError("Capture did not return a NumPy ndarray")
    if image.ndim != 3 or image.shape[2] != 3:
        raise SmokeValidationError(f"Expected HxWx3 BGR frame, got {image.shape!r}")
    if image.dtype != np.uint8:
        raise SmokeValidationError(
            f"Expected uint8 BGR frame, got dtype {image.dtype}"
        )
    height, width = image.shape[:2]
    if snapshot.width != width or snapshot.height != height:
        raise SmokeValidationError("Snapshot dimensions do not match image.shape")
    if width <= height:
        raise SmokeValidationError(
            f"Expected landscape frame, got width={width}, height={height}"
        )
    return tuple(int(value) for value in image.shape), str(image.dtype)


def _positive_frame_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("frame count must be an integer") from error
    if count < MIN_FRAME_COUNT:
        raise argparse.ArgumentTypeError(
            f"frame count must be at least {MIN_FRAME_COUNT}"
        )
    return count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the 0.2 ADB/scrcpy capture stack against real hardware."
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="dotenv file to load explicitly (default: project .env)",
    )
    parser.add_argument(
        "--frames",
        type=_positive_frame_count,
        default=DEFAULT_FRAME_COUNT,
        help=f"number of distinct snapshots to validate (default: {DEFAULT_FRAME_COUNT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        report = run_smoke(config, frame_count=args.frames)
    except KeyboardInterrupt:
        print("[smoke] Interrupted; capture cleanup completed.", file=sys.stderr)
        return 130
    except (AdbError, CaptureError, SmokeValidationError, ValueError, OSError) as error:
        print(f"[smoke] FAILED: {error}", file=sys.stderr)
        return 1

    height, width, channels = report.shape
    print(f"[smoke] ADB state: {report.adb_state}")
    print(f"[smoke] scrcpy-server protocol: {ScrcpyFrameSource.SCRCPY_VERSION}")
    print(f"[smoke] first frame: {report.first_frame_seconds:.3f}s")
    print(
        f"[smoke] frames: {report.frame_count}; sequence: "
        f"{report.first_sequence} -> {report.last_sequence}"
    )
    print(
        f"[smoke] frame: width={width}, height={height}, channels={channels}, "
        f"dtype={report.dtype}"
    )
    print(
        f"[smoke] timestamps: {report.first_timestamp:.6f} -> "
        f"{report.last_timestamp:.6f}"
    )
    print("[smoke] shutdown: complete")
    print("[smoke] forward cleanup: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
