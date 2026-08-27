"""Hardware opt-in harness for BlackMarketFlow on the active character."""

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
from bot.black_market_flow import BlackMarketFlow
from bot.capture import CaptureError
from bot.catalog import SCREEN_BLACK_MARKET, SCREEN_LOBBY, build_default_resolver
from bot.config import RuntimeConfig
from bot.event_log import JsonLineEventLog
from bot.flow_contracts import FlowStatus
from bot.inventory_full_transition import acknowledge_inventory_full
from bot.perception import build_default_perception
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import RuntimeObserver, RuntimeWaitAborted, RuntimeWaitTimeout
from bot.semantic_actions import CloseBlackMarket
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement that this harness sends the scoped ADB taps",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=REPOSITORY_ROOT / ".env",
        help="explicit runtime dotenv path",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--max-slots",
        type=int,
        default=0,
        help=(
            "maximum initial GOLD slots to attempt "
            "(default: 0, entry/facts probe without offer selection)"
        ),
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="attempt every slot from the one initial GOLD reading",
    )
    mode.add_argument(
        "--close-current",
        action="store_true",
        help="close an already-open clean Black Market and verify Lobby",
    )
    mode.add_argument(
        "--ack-inventory-full-current",
        action="store_true",
        help=(
            "acknowledge an already-open popup.inventory_full and verify "
            "screen.black_market"
        ),
    )
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument(
        "--event-log",
        type=Path,
        default=REPOSITORY_ROOT / "logs" / "black-market-events.jsonl",
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
    if args.max_slots is not None and args.max_slots < 0:
        print("--max-slots must be non-negative", file=sys.stderr)
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
            if args.ack_inventory_full_current:
                initial = observer.observe()
                transition = acknowledge_inventory_full(
                    VerifiedTransition(observer, actions),
                    initial,
                    policy=VerifiedTransitionPolicy(
                        normal_timeout=args.timeout,
                        grace_timeout=2.0,
                        max_attempts=2,
                    ),
                )
                if not transition.succeeded:
                    raise ValueError(
                        "inventory-full acknowledgement failed: "
                        f"{transition.outcome.value}: {transition.error}"
                    )
                final = transition.final_snapshot
                payload = {
                    "action": "acknowledge_inventory_full",
                    "attempt_count": transition.attempt_count,
                    "final_base_context": final.state.base_context,
                    "final_sequence": final.sequence,
                    "grace_wait_count": transition.grace_wait_count,
                    "initial_overlays": list(initial.state.overlays),
                    "initial_sequence": initial.sequence,
                    "outcome": transition.outcome.value,
                }
                result = None
            elif args.close_current:
                initial = observer.observe()
                if not _is_clean_base(initial, SCREEN_BLACK_MARKET):
                    raise ValueError(
                        "--close-current requires a clean screen.black_market"
                    )
                actions.execute(CloseBlackMarket(), initial.geometry)
                final = observer.wait_until(
                    lambda snapshot: _is_clean_base(snapshot, SCREEN_LOBBY),
                    after_sequence=initial.sequence,
                    timeout=args.timeout,
                    abort_if=lambda snapshot: (
                        snapshot.state.status is ResolutionStatus.AMBIGUOUS
                        or bool(snapshot.state.overlays)
                    ),
                )
                payload = {
                    "action": "close_black_market",
                    "final_base_context": final.state.base_context,
                    "final_sequence": final.sequence,
                    "initial_sequence": initial.sequence,
                    "outcome": "success",
                }
                result = None
            else:
                flow = BlackMarketFlow(
                    observer,
                    actions,
                    events,
                    timeout=args.timeout,
                )
                result = flow.run(
                    max_slot_attempts=None if args.full else args.max_slots
                )
                payload = asdict(result)
                payload["status"] = result.status.value
    except (
        AdbError,
        CaptureError,
        OSError,
        RuntimeWaitAborted,
        RuntimeWaitTimeout,
        ValueError,
    ) as error:
        print(f"Black Market smoke failed: {error}", file=sys.stderr)
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if result is not None and result.status is FlowStatus.FAILED else 0


def _is_clean_base(snapshot, expected_base: str) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == expected_base
        and not state.overlays
    )


if __name__ == "__main__":
    raise SystemExit(main())
