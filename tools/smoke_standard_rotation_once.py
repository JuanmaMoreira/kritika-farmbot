"""Hardware opt-in harness for exactly one StandardRotation.advance()."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.action_executor import ActionExecutor
from bot.adb import AdbError
from bot.capture import CaptureError
from bot.catalog import build_default_resolver
from bot.config import RuntimeConfig
from bot.event_log import JsonLineEventLog
from bot.perception import build_default_perception
from bot.rotation import RotationOutcome, StandardRotation
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import RuntimeObserver


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement that this harness sends scoped ADB input",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=REPOSITORY_ROOT / ".env",
        help="explicit runtime dotenv path",
    )
    parser.add_argument("--character-count", type=int, default=28)
    parser.add_argument("--max-swipes", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--scroll-settle-for", type=float, default=0.6)
    parser.add_argument("--selection-settle-for", type=float, default=0.25)
    parser.add_argument(
        "--event-log",
        type=Path,
        default=REPOSITORY_ROOT / "logs" / "rotation-events.jsonl",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.execute:
        print(
            "Refusing to send Android input without --execute. "
            "Obtain the required chat authorization first.",
            file=sys.stderr,
        )
        return 2

    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
        if adb.get_state() != "device":
            print("ADB device is not ready", file=sys.stderr)
            return 2
        source = build_frame_source(
            config,
            adb_client=adb,
            video_bit_rate=8_000_000,
            max_fps=30,
        )
        perception = build_default_perception(REPOSITORY_ROOT)
        resolver = build_default_resolver()
        events = JsonLineEventLog(args.event_log)
        actions = ActionExecutor(adb)

        with source:
            observer = RuntimeObserver(source, perception, resolver)
            rotation = StandardRotation(
                observer,
                actions,
                events,
                character_count=args.character_count,
                max_swipes=args.max_swipes,
                timeout=args.timeout,
                scroll_settle_for=args.scroll_settle_for,
                selection_settle_for=args.selection_settle_for,
            )
            result = rotation.advance()
    except (AdbError, CaptureError, OSError, ValueError) as error:
        print(f"Standard Rotation smoke failed: {error}", file=sys.stderr)
        return 2

    payload = asdict(result)
    payload["outcome"] = result.outcome.value
    payload["character_count"] = args.character_count
    payload["max_swipes"] = args.max_swipes
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if result.outcome is RotationOutcome.ABORTED else 0


if __name__ == "__main__":
    raise SystemExit(main())
