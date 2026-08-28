"""Hardware opt-in smoke for one WorldBossFlow and optional one rotation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.action_executor import ActionExecutor
from bot.adb import AdbError
from bot.auto_battle import AutoBattleDetector, AutoBattleEnsurer
from bot.capture import CaptureError
from bot.catalog import build_default_resolver
from bot.config import RuntimeConfig
from bot.event_log import JsonLineEventLog
from bot.flow_contracts import FlowStatus
from bot.perception import build_default_perception
from bot.rotation import RotationOutcome, StandardRotation
from bot.runtime import build_adb_client, build_frame_source, build_runtime_fact_reader
from bot.runtime_observer import RuntimeObserver
from bot.world_boss_flow import WorldBossFlow


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("flow", "flow-then-rotation"))
    parser.add_argument(
        "--execute", action="store_true",
        help="required acknowledgement that this harness sends scoped ADB input",
    )
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument(
        "--event-log", type=Path,
        default=PROJECT_ROOT / "logs" / "world-boss-events.jsonl",
    )
    parser.add_argument("--character-count", type=int, default=28)
    return parser.parse_args(argv)


def _flow_payload(result):
    return {
        "status": result.status.value,
        "events": [
            {"kind": event.kind, "detail": event.detail}
            for event in result.events
        ],
        "error": result.error,
        "sapphires": result.sapphires,
        "previous_rewards": result.previous_rewards,
        "inventory_full": result.inventory_full,
        "auto_battle_initial": (
            result.auto_battle_initial.value
            if result.auto_battle_initial is not None else None
        ),
        "auto_battle_taps": result.auto_battle_taps,
        "initial_timer": result.initial_timer,
        "wait_elapsed": result.wait_elapsed,
        "wait_checks": result.wait_checks,
        "raid_complete_detected": result.raid_complete_detected,
        "transition_outcomes": result.transition_outcomes,
        "transition_attempts": result.transition_attempts,
    }


def main(argv=None):
    args = parse_args(argv)
    if not args.execute:
        print(
            "Refusing to send Android input without --execute. "
            "Obtain explicit chat authorization first.",
            file=sys.stderr,
        )
        return 2
    try:
        config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
        adb = build_adb_client(config)
        if adb.get_state() != "device":
            raise RuntimeError("ADB device is not ready")
        source = build_frame_source(
            config, adb_client=adb, video_bit_rate=8_000_000, max_fps=30
        )
        actions = ActionExecutor(adb)
        events = JsonLineEventLog(args.event_log)
        with source:
            observer = RuntimeObserver(
                source,
                build_default_perception(PROJECT_ROOT),
                build_default_resolver(),
            )
            flow = WorldBossFlow(
                observer,
                actions,
                build_runtime_fact_reader(observer),
                AutoBattleEnsurer(AutoBattleDetector(observer), actions),
                events,
            )
            flow_result = flow.run()
            rotation_result = None
            if (
                args.command == "flow-then-rotation"
                and flow_result.status is FlowStatus.COMPLETED
                and flow_result.raid_complete_detected
            ):
                rotation_result = StandardRotation(
                    observer,
                    actions,
                    events,
                    character_count=args.character_count,
                ).advance()
    except (AdbError, CaptureError, OSError, RuntimeError, ValueError) as error:
        print(f"World Boss smoke failed: {error}", file=sys.stderr)
        return 2

    payload = {"command": args.command, "flow": _flow_payload(flow_result)}
    if rotation_result is not None:
        payload["rotation"] = {
            "outcome": rotation_result.outcome.value,
            "error": rotation_result.error,
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if flow_result.status is not FlowStatus.COMPLETED:
        return 1
    if args.command == "flow-then-rotation":
        if rotation_result is None or rotation_result.outcome is RotationOutcome.ABORTED:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
