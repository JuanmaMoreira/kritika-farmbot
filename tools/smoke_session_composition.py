"""Two-character hardware smoke for World Boss session composition."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.action_executor import ActionExecutor
from bot.adb import AdbError
from bot.auto_battle import AutoBattleDetector, AutoBattleEnsurer
from bot.black_market_flow import BlackMarketFlow, BlackMarketFlowResult
from bot.capture import CaptureError
from bot.catalog import SCREEN_LOBBY, SCREEN_WORLD_BOSS, build_default_resolver
from bot.config import RuntimeConfig
from bot.event_log import JsonLineEventLog
from bot.flow_contracts import FlowResult
from bot.perception import build_default_perception
from bot.preconditions import EnsureResult, MinimalPreconditionEnsurer
from bot.rotation import StandardRotation
from bot.runtime import build_adb_client, build_frame_source, build_runtime_fact_reader
from bot.runtime_observer import RuntimeObserver, RuntimeWaitTimeout
from bot.session import SessionPlan, SessionRunner, SessionStatus
from bot.state import ResolutionStatus
from bot.world_boss_flow import WorldBossFlow, WorldBossFlowResult


CHARACTER_COUNT = 2
_CLEAN_CONTEXTS = frozenset({SCREEN_LOBBY, SCREEN_WORLD_BOSS})


@dataclass
class RecordingPreconditions:
    delegate: MinimalPreconditionEnsurer
    records: list[EnsureResult]

    def ensure(self, requirement):
        result = self.delegate.ensure(requirement)
        self.records.append(result)
        return result

    def current_satisfies_any(self, requirements):
        return self.delegate.current_satisfies_any(requirements)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("world-boss", "multi-flow"))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required acknowledgement that this sends scoped Android input",
    )
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument(
        "--event-log",
        type=Path,
        default=PROJECT_ROOT / "logs" / "session-composition-events.jsonl",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.execute:
        print(
            "Refusing input without --execute and explicit chat authorization.",
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
        events = JsonLineEventLog(args.event_log)
        actions = ActionExecutor(adb)
        with source:
            observer = RuntimeObserver(
                source,
                build_default_perception(PROJECT_ROOT),
                build_default_resolver(),
            )
            flows = []
            if args.command == "multi-flow":
                flows.append(
                    BlackMarketFlow(
                        observer, actions, events, timeout=args.timeout
                    )
                )
            flows.append(
                WorldBossFlow(
                    observer,
                    actions,
                    build_runtime_fact_reader(observer),
                    AutoBattleEnsurer(AutoBattleDetector(observer), actions),
                    events,
                )
            )
            rotation = StandardRotation(
                observer,
                actions,
                events,
                character_count=CHARACTER_COUNT,
                timeout=args.timeout,
            )
            precondition_records: list[EnsureResult] = []
            preconditions = RecordingPreconditions(
                MinimalPreconditionEnsurer(
                    lambda: _current_clean_context(observer)
                ),
                precondition_records,
            )
            result = SessionRunner(
                SessionPlan(CHARACTER_COUNT, tuple(flows), rotation),
                preconditions=preconditions,
                events=events,
            ).run()
    except (AdbError, CaptureError, OSError, RuntimeError, ValueError) as error:
        print(f"Session composition smoke failed: {error}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            _summary(args.command, result, flows, precondition_records),
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.status is SessionStatus.COMPLETED else 1


def _current_clean_context(observer: RuntimeObserver) -> str | None:
    initial = observer.observe()
    if _is_clean_known_context(initial):
        return initial.state.base_context
    try:
        settled = observer.wait_until(
            _is_clean_known_context,
            after_sequence=initial.sequence,
            timeout=2.0,
            stable_for=0.25,
        )
    except RuntimeWaitTimeout:
        return None
    return settled.state.base_context


def _is_clean_known_context(snapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context in _CLEAN_CONTEXTS
        and not state.overlays
    )


def _summary(command, result, flows, preconditions):
    characters = []
    for character in result.character_results:
        flow_summaries = []
        for flow, flow_result in zip(flows, character.flow_results):
            flow_summaries.append(_flow_summary(flow.name, flow_result))
        advance = character.advance_result
        characters.append(
            {
                "index": character.index,
                "completed": character.completed,
                "flows": flow_summaries,
                "advance": (
                    None
                    if advance is None
                    else {
                        "outcome": advance.outcome.value,
                        "swipes": advance.swipe_count,
                        "transitions": [
                            {
                                "name": item.name,
                                "outcome": item.outcome,
                                "attempts": item.attempt_count,
                                "grace_waits": item.grace_wait_count,
                            }
                            for item in advance.transitions
                        ],
                    }
                ),
            }
        )
    ensure_records = [
        {
            "requirement": item.requirement.name,
            "outcome": item.outcome.value,
            "context_before": item.context_before,
            "context_after": item.context_after,
        }
        for item in preconditions
    ]
    return {
        "command": command,
        "character_count": CHARACTER_COUNT,
        "status": result.status.value,
        "characters_processed": result.characters_processed,
        "flows_completed": sum(
            flow.status.value == "completed"
            for character in result.character_results
            for flow in character.flow_results
        ),
        "advances_completed": result.advances_completed,
        "business_events": [event.kind for event in result.events],
        "normalizations": sum(
            item.outcome.value == "normalized" for item in preconditions
        ),
        "preconditions": ensure_records,
        "world_boss_rotation_count": sum(
            item.requirement.name == "quick_menu_accessible"
            and item.context_before == SCREEN_WORLD_BOSS
            for item in preconditions
        ),
        "failure_character_index": result.failure_character_index,
        "failure_flow": result.failure_flow,
        "failure_cause": result.failure_cause,
        "characters": characters,
    }


def _flow_summary(name: str, result: FlowResult):
    value = {
        "name": name,
        "status": result.status.value,
        "events": [event.kind for event in result.events],
        "error": result.error,
    }
    if isinstance(result, BlackMarketFlowResult):
        value.update(
            gold_slots=list(result.initial_gold_slots),
            attempted_slots=list(result.attempted_slots),
            verified_purchases=list(result.verified_purchases),
        )
    if isinstance(result, WorldBossFlowResult):
        outcome = (
            "insufficient_sapphires"
            if result.sapphires is not None and result.sapphires < 5
            else "inventory_full"
            if result.inventory_full
            else "participated"
            if result.raid_complete_detected
            else "completed_other"
        )
        value.update(
            sapphires=result.sapphires,
            outcome=outcome,
            previous_rewards=result.previous_rewards,
            auto_battle_taps=result.auto_battle_taps,
            initial_timer=result.initial_timer,
            transition_attempts=[list(item) for item in result.transition_attempts],
            transition_outcomes=[list(item) for item in result.transition_outcomes],
        )
    return value


if __name__ == "__main__":
    raise SystemExit(main())
