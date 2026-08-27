"""Hardware opt-in smoke for BlackMarketFlow + StandardRotation composition."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bot.action_executor import ActionExecutor
from bot.adb import AdbError
from bot.black_market_flow import BlackMarketFlow
from bot.capture import CaptureError
from bot.catalog import SCREEN_LOBBY, build_default_resolver
from bot.config import RuntimeConfig
from bot.event_log import JsonLineEventLog
from bot.perception import build_default_perception
from bot.preconditions import MinimalPreconditionEnsurer
from bot.rotation import StandardRotation
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.session import SessionPlan, SessionRunner, SessionStatus
from bot.state import ResolutionStatus


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
    parser.add_argument(
        "--character-count",
        type=int,
        default=2,
        help="truncated smoke size (1-3; product default remains 28)",
    )
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument(
        "--event-log",
        type=Path,
        default=REPOSITORY_ROOT / "logs" / "black-market-session-events.jsonl",
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
    if not 1 <= args.character_count <= 3:
        print("--character-count must be between 1 and 3", file=sys.stderr)
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
            flow = BlackMarketFlow(observer, actions, events, timeout=args.timeout)
            rotation = StandardRotation(
                observer,
                actions,
                events,
                character_count=args.character_count,
                timeout=args.timeout,
            )
            plan = SessionPlan(
                character_count=args.character_count,
                flows=(flow,),
                rotation_strategy=rotation,
            )
            runner = SessionRunner(
                plan,
                preconditions=MinimalPreconditionEnsurer(
                    lambda: (
                        SCREEN_LOBBY
                        if _wait_for_clean_lobby(observer)
                        else None
                    )
                ),
                events=events,
            )
            result = runner.run()
    except (AdbError, CaptureError, OSError, ValueError) as error:
        print(f"Black Market session smoke failed: {error}", file=sys.stderr)
        return 2

    print(json.dumps(_json_ready(result), indent=2, sort_keys=True))
    return 0 if result.status is SessionStatus.COMPLETED else 1


def _is_clean_lobby(snapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_LOBBY
        and not state.overlays
    )


def _wait_for_clean_lobby(
    observer: RuntimeObserver,
    *,
    timeout: float = 2.0,
    stable_for: float = 0.25,
) -> bool:
    initial = observer.observe()
    if _has_incompatible_lobby_state(initial):
        return False
    try:
        observer.wait_until(
            _is_clean_lobby,
            after_sequence=initial.sequence,
            timeout=timeout,
            abort_if=_has_incompatible_lobby_state,
            stable_for=stable_for,
        )
    except (RuntimeWaitAborted, RuntimeWaitTimeout):
        return False
    return True


def _has_incompatible_lobby_state(snapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_LOBBY
        )
    )


def _json_ready(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
