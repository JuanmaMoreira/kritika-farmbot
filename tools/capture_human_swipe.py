"""Capture one physical Android swipe through HumanInputObserver, read-only."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.adb import AdbError
from bot.config import RuntimeConfig
from bot.human_input import HumanInputError, HumanInputObserver, HumanSwipe
from bot.runtime import build_adb_client


@dataclass(frozen=True)
class HumanSwipeReference:
    start: tuple[float, float]
    end: tuple[float, float]
    duration_seconds: float
    direction: str
    displacement: float
    horizontal_displacement: float
    vertical_displacement: float
    path_points: int


def swipe_reference(swipe: HumanSwipe) -> HumanSwipeReference:
    dx = swipe.end[0] - swipe.start[0]
    dy = swipe.end[1] - swipe.start[1]
    if abs(dy) >= abs(dx):
        direction = "down" if dy > 0 else "up"
    else:
        direction = "right" if dx > 0 else "left"
    return HumanSwipeReference(
        start=swipe.start,
        end=swipe.end,
        duration_seconds=swipe.duration,
        direction=direction,
        displacement=math.hypot(dx, dy),
        horizontal_displacement=dx,
        vertical_displacement=dy,
        path_points=len(swipe.path),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observe",
        action="store_true",
        help="required acknowledgement that physical input will be observed read-only",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=REPOSITORY_ROOT / ".env",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--poll-interval", type=float, default=0.02)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.observe:
        print(
            "Refusing to observe Android input without --observe. "
            "Obtain the required chat authorization first.",
            file=sys.stderr,
        )
        return 2
    if args.timeout <= 0 or args.poll_interval <= 0:
        print("--timeout and --poll-interval must be positive", file=sys.stderr)
        return 2

    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
        observer = HumanInputObserver(adb)
        deadline = time.monotonic() + args.timeout
        print("human swipe observer ready", flush=True)
        with observer:
            while time.monotonic() < deadline:
                for gesture in observer.poll():
                    if isinstance(gesture, HumanSwipe):
                        print(
                            json.dumps(
                                asdict(swipe_reference(gesture)),
                                indent=2,
                                sort_keys=True,
                            )
                        )
                        return 0
                time.sleep(args.poll_interval)
    except (AdbError, HumanInputError, OSError, ValueError) as error:
        print(f"Human swipe capture failed: {error}", file=sys.stderr)
        return 2

    print("No physical swipe observed before timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
