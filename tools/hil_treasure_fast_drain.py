"""Opt-in HIL calibration for the E2.2 Gold Key fast drain (Treasure-only).

One condition per run, chat+steer channel: the user holds the device in
Treasure with the Gold-backed right button visible and approves every
burst explicitly (interval + total economic-input cap announced before
each run). Final tap-through inputs are counted separately.

Modes (no entry navigation and no Trading/C6b: the user places the
device in clean Treasure; a successful burst performs the normal
verified Back to Lobby):

- ``dry-run`` (default): observe only, classify the live state
  (RIGHT_GOLD_OPEN_MAX / RIGHT_KARAT_OPEN / contradiction / foreign),
  save frames + report. Zero taps, always safe.
- ``burst``: E2 single-open entry (``TreasureRuntime``,
  ``OPEN_ONCE``, 1 key, fully verified) then ``drain_gold_keys_fast``
  with the requested cadence and caps. Stops on Karat boundary,
  contradiction, stall, context loss, cancel or deadline. The fast
  drain taps ONLY the Gold-backed right button (observed or local
  reward-transient pair Gold); while Gold exists it never taps outside
  or left. The batch-10 reward grid that covers the title is a known
  transient: the loop keeps tapping the same right button through it
  (dual role: cut animation or next batch). Only after fresh Karat may
  the shared tap-through finalizer use the profile-owned safe point.

Evidence lands under ``artifacts/hil_e2_fastdrain/<stamp>/`` (raws, not
versioned): ``frame_*.png`` per fast-loop observation plus
``report.json`` with split economic/finalize telemetry, economic
per-tap observations and the human GT line the operator confirms in chat.

Importing this module is inert; processes and device IO start in main.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.action_executor import ActionExecutor  # noqa: E402
from bot.catalog import build_default_resolver  # noqa: E402
from bot.config import RuntimeConfig  # noqa: E402
from bot.perception import build_treasure_perception  # noqa: E402
from bot.perception.treasure_center import TreasureContentDetector  # noqa: E402
from bot.runtime import build_adb_client, build_frame_source  # noqa: E402
from bot.runtime_observer import RuntimeObserver  # noqa: E402
from bot.semantic_actions import DismissTreasureResult  # noqa: E402
from bot.tap_through_animation import TapThroughAnimation  # noqa: E402
from bot.treasure_center import (  # noqa: E402
    has_right_button_contradiction,
    has_right_gold_open_max,
    has_right_karat_open,
    is_treasure_screen,
)
from bot.treasure_fast_drain import (  # noqa: E402
    GoldKeyDrainConfig,
    check_fast_drain_entry,
    drain_gold_keys_fast,
    local_karat_boundary,
    local_reward_side,
    resolve_right_button_target,
)
from bot.treasure_keys import GoldKeyQuantity, GoldKeyQuantityMode  # noqa: E402
from bot.treasure_runtime import TreasureRuntime  # noqa: E402
from bot.verified_transition import VerifiedTransition  # noqa: E402

ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "hil_e2_fastdrain"


class EconomicInputCap:
    """Hard cap around right-button input; final dismiss bypasses it."""

    def __init__(self, maximum: int, emit) -> None:
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
            raise ValueError("maximum must be a non-negative integer")
        if not callable(emit):
            raise ValueError("emit must be callable")
        self.maximum = maximum
        self.emit = emit
        self.emitted = 0

    def __call__(self, point) -> None:
        if self.emitted >= self.maximum:
            raise RuntimeError("approved economic input cap exhausted")
        self.emit(point)
        self.emitted += 1


def remaining_economic_inputs(approved: int, already_emitted: int) -> int:
    """Return the right-button budget left after the verified E2 entry."""

    for name, value in (
        ("approved", approved),
        ("already_emitted", already_emitted),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if already_emitted > approved:
        raise ValueError("entry exceeded the approved economic input cap")
    return approved - already_emitted


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("dry-run", "burst"), default="dry-run",
        help="dry-run observes only; burst taps with approval",
    )
    parser.add_argument("--interval", type=float, default=0.20)
    parser.add_argument(
        "--approved-economic-inputs",
        type=int,
        default=None,
        help="required in burst mode; hard total cap including E2 entry",
    )
    parser.add_argument("--watchdog-every", type=int, default=10)
    parser.add_argument("--deadline", type=float, default=60.0)
    parser.add_argument("--dry-run-seconds", type=float, default=4.0)
    parser.add_argument(
        "--no-reward-transient", action="store_true",
        help="disable the local reward-grid contract (strict observed-only)",
    )
    parser.add_argument(
        "--allow-karat-entry", action="store_true",
        help="start directly at an observed Karat boundary with --gt "
        "lineage, running only the finalize (retry of a still-open "
        "boundary overlay)",
    )
    parser.add_argument(
        "--skip-entry", action="store_true",
        help="Skip the E2 OPEN_ONCE entry and start the fast drain from the "
        "live repeat state. Use only when the initial causal open is "
        "already demonstrated by physical GT (counter decrease + result "
        "+ reward confirmed in chat). The GT line must be pasted into the "
        "report via --gt.",
    )
    parser.add_argument(
        "--gt", type=str, default=None,
        help="Human ground-truth line justifying --skip-entry.",
    )
    parser.add_argument(
        "--dotenv", type=Path, default=PROJECT_ROOT / ".env",
    )
    parser.add_argument("--save-dir", type=Path, default=None)
    return parser.parse_args(argv)


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%dT%H%M%S")


def _describe(snapshot) -> dict:
    state = snapshot.state
    try:
        observations = sorted(
            f"{item.name}@{item.confidence:.2f}"
            for item in snapshot.observations.observations
        )
    except Exception:
        observations = []
    return {
        "sequence": snapshot.sequence,
        "observed_at": snapshot.timestamp,
        "status": getattr(state.status, "value", str(state.status)),
        "base": state.base_context,
        "overlays": list(state.overlays),
        "observations": observations,
        "is_treasure": is_treasure_screen(snapshot),
        "right_gold": has_right_gold_open_max(snapshot),
        "right_karat": has_right_karat_open(snapshot),
        "contradiction": has_right_button_contradiction(snapshot),
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.mode == "burst" and (
        args.approved_economic_inputs is None
        or args.approved_economic_inputs <= 0
    ):
        print(
            "[burst] --approved-economic-inputs N (>0) is required; "
            "zero device input emitted."
        )
        return 2
    save_dir = args.save_dir or (ARTIFACT_ROOT / _stamp())
    save_dir.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    adb = build_adb_client(config)
    source = build_frame_source(config, adb_client=adb)
    perception = build_treasure_perception()
    resolver = build_default_resolver()
    stop = threading.Event()

    def cancel_requested() -> bool:
        return stop.is_set()

    report: dict = {
        "mode": args.mode,
        "interval_s": args.interval,
        "approved_economic_inputs": args.approved_economic_inputs,
        "watchdog_every": args.watchdog_every,
        "deadline_s": args.deadline,
        "human_gt": None,
        "frames": [],
        "taps": [],
    }
    try:
        with source:
            observer = RuntimeObserver(source, perception, resolver)
            actions = ActionExecutor(adb)
            transition = VerifiedTransition(observer, actions)
            runtime = TreasureRuntime(
                observer, transition, cancel_requested=cancel_requested
            )
            content = TreasureContentDetector()
            latest = {"snapshot": None}

            def observe():
                snapshot = observer.observe()
                latest["snapshot"] = snapshot
                return snapshot

            if args.mode == "dry-run":
                deadline = time.monotonic() + args.dry_run_seconds
                index = 0
                while time.monotonic() < deadline:
                    snapshot = observe()
                    info = _describe(snapshot)
                    report["frames"].append(info)
                    try:
                        import cv2

                        cv2.imwrite(
                            str(save_dir / f"dry_{index:03d}.png"),
                            snapshot.frame.image,
                        )
                    except Exception as error:
                        report.setdefault("frame_errors", []).append(str(error))
                    print(
                        f"[dry] seq={info['sequence']} base={info['base']} "
                        f"treasure={info['is_treasure']} "
                        f"right_gold={info['right_gold']} "
                        f"right_karat={info['right_karat']} "
                        f"contradiction={info['contradiction']}"
                    )
                    index += 1
                    time.sleep(0.25)
                print(f"[dry] saved {index} frames to {save_dir}")
                return 0

            # Burst mode: E2 single-open entry (unless GT-grounded skip),
            # then the fast drain.
            if args.skip_entry:
                if not args.gt:
                    print("[burst] --skip-entry requires --gt GT line.")
                    return 2
                report["entry"] = {
                    "outcome": "skipped_by_gt",
                    "reason": args.gt,
                    "opened": None,
                    "inputs": [],
                    "evidence": ["entry:human_gt_skip"],
                }
                report["human_gt"] = args.gt
                print(f"[burst] entry skipped by GT: {args.gt}")
                entry_economic_inputs = 0
            else:
                print("[burst] entry: E2 OPEN_ONCE via TreasureRuntime ...")
                opened = runtime.execute_gold_key_open(
                    GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE),
                    max_actions=2,
                )
                report["entry"] = {
                    "outcome": opened.outcome.value,
                    "reason": opened.reason,
                    "opened": opened.opened,
                    "inputs": list(opened.inputs),
                    "evidence": list(opened.evidence),
                }
                print(
                    f"[burst] entry outcome={opened.outcome.value} "
                    f"reason={opened.reason} opened={opened.opened}"
                )
                if str(opened.outcome.value) != "success":
                    print("[burst] entry refused: zero fast inputs, stopping.")
                    return 2
                entry_economic_inputs = len(opened.inputs)
            initial = observe()
            initial_info = _describe(initial)
            try:
                initial_reading = content.measure(initial.frame.image)
                initial_info["local_gold_side"] = local_reward_side(
                    initial_reading
                )
                initial_info["local_karat"] = local_karat_boundary(
                    initial_reading
                )
            except Exception:
                initial_info["local_gold_side"] = None
                initial_info["local_karat"] = False
            report["frames"].append(initial_info)
            entry_reason = check_fast_drain_entry(
                initial, initial_open_verified=True
            )
            karat_entry = False
            # Immediate Karat after this run's verified E2 entry carries
            # natural lineage (the ~2-keys edge): latch and finalize
            # with zero right-button taps instead of refusing.
            allow_karat_entry = args.allow_karat_entry or not args.skip_entry
            if entry_reason is not None:
                try:
                    entry_reading = content.measure(initial.frame.image)
                except Exception:
                    entry_reading = None
                side = local_reward_side(entry_reading)
                if side is not None:
                    print(f"[burst] transient entry: local_gold:{side}")
                    entry_reason = None
                elif (
                    allow_karat_entry
                    and local_karat_boundary(entry_reading)
                ):
                    print("[burst] local Karat-boundary entry: finalize only")
                    entry_reason = None
                    karat_entry = True
            if entry_reason == "already_karat_boundary" and (
                args.skip_entry or allow_karat_entry
            ):
                print("[burst] karat-boundary entry: finalize only")
                entry_reason = None
                karat_entry = True
            print(
                f"[burst] fast entry: {_describe(initial)} "
                f"refusal={entry_reason}"
            )
            if entry_reason is not None:
                print("[burst] fast entry refused: zero fast inputs.")
                return 2

            right_input_budget = remaining_economic_inputs(
                args.approved_economic_inputs,
                entry_economic_inputs,
            )
            report["entry_economic_inputs"] = entry_economic_inputs
            report["right_input_budget"] = right_input_budget
            if right_input_budget == 0 and not karat_entry:
                print(
                    "[burst] approved economic cap consumed by E2 entry; "
                    "zero right-button inputs emitted."
                )
                return 3

            drain_config = GoldKeyDrainConfig(
                tap_interval_s=args.interval,
                watchdog_every=args.watchdog_every,
                safety_deadline_s=args.deadline,
                max_inputs=max(1, right_input_budget),
                reward_transient=not args.no_reward_transient,
            )

            def emit_economic_tap(point) -> None:
                snapshot = latest["snapshot"]
                geometry = snapshot.geometry
                pixel = (
                    int(point[0] * geometry.width),
                    int(point[1] * geometry.height),
                )
                adb.tap(*pixel)
                info = _describe(snapshot)
                info["tap_point"] = list(point)
                info["tap_pixel"] = list(pixel)
                info["input_kind"] = "economic_right"
                if info["right_gold"]:
                    authorization = "resolved_right_gold"
                else:
                    try:
                        side = local_reward_side(
                            content.measure(snapshot.frame.image)
                        )
                    except Exception:
                        side = None
                    authorization = (
                        f"local_right_gold:{side}"
                        if side is not None
                        else "unclassified"
                    )
                info["authorization"] = authorization
                info["physical_currency"] = "requires_before_after_gt"
                report["taps"].append(info)
                print(
                    f"[burst] tap #{len(report['taps'])} point={point} "
                    f"seq={info['sequence']} obs={info['observations']}"
                )

            economic_tap = EconomicInputCap(
                right_input_budget,
                emit_economic_tap,
            )

            def record_drain_snapshot(snapshot):
                latest["snapshot"] = snapshot
                index = len(report["frames"])
                info = _describe(snapshot)
                try:
                    reading = content.measure(snapshot.frame.image)
                    info["local_gold_side"] = local_reward_side(reading)
                    info["local_karat"] = local_karat_boundary(reading)
                except Exception:
                    info["local_gold_side"] = None
                    info["local_karat"] = False
                report["frames"].append(info)
                try:
                    import cv2

                    cv2.imwrite(
                        str(save_dir / f"drain_{index:04d}.png"),
                        snapshot.frame.image,
                    )
                except Exception:
                    pass
                return snapshot

            def counting_observe():
                return record_drain_snapshot(observe())

            class RecordingWaitObserver:
                def wait_until(self, condition, **kwargs):
                    snapshot = observer.wait_until(condition, **kwargs)
                    return record_drain_snapshot(snapshot)

            class RecordingFinalActions:
                def execute(self, action, geometry):
                    execution = actions.execute(action, geometry)
                    if isinstance(action, DismissTreasureResult):
                        info = _describe(latest["snapshot"])
                        info["tap_point"] = list(
                            execution.normalized_target
                        )
                        info["tap_pixel"] = list(execution.pixel_target)
                        info["input_kind"] = "dismiss_lateral"
                        report.setdefault("dismiss_taps", []).append(info)
                    return execution

            tap_through = TapThroughAnimation(
                RecordingWaitObserver(),
                RecordingFinalActions(),
                clock=time.monotonic,
                sleeper=time.sleep,
            )

            target_point = resolve_right_button_target(initial)
            print(
                f"[burst] interval={args.interval}s "
                f"approved_economic_inputs={args.approved_economic_inputs} "
                f"entry_economic_inputs={entry_economic_inputs} "
                f"max_right_inputs={right_input_budget} "
                f"watchdog_every={args.watchdog_every} "
                f"initial_target={target_point}"
            )
            result = drain_gold_keys_fast(
                initial_snapshot=initial,
                observe=counting_observe,
                tap=economic_tap,
                config=drain_config,
                initial_open_verified=True,
                cancel_requested=cancel_requested,
                clock=time.monotonic,
                sleeper=time.sleep,
                measure_local=content.measure,
                tap_through=tap_through,
                allow_karat_entry=karat_entry,
            )
            report["result"] = {
                "outcome": result.outcome.value,
                "right_button_inputs": result.inputs_emitted,
                "economic_inputs": entry_economic_inputs + result.inputs_emitted,
                "dismiss_inputs": result.dismiss_inputs,
                "watchdogs_run": result.watchdogs_run,
                "gold_button_observations": result.gold_button_observations,
                "karat_boundary_seen": result.karat_boundary_seen,
                "elapsed_s": result.elapsed_s,
                "reason": result.reason,
                "evidence": list(result.evidence),
            }
            boundary = next(
                (
                    frame
                    for frame in report["frames"]
                    if frame["right_karat"] or frame.get("local_karat")
                ),
                None,
            )
            report["result"]["first_karat_boundary"] = (
                {
                    "sequence": boundary["sequence"],
                    "observed_at": boundary["observed_at"],
                    "source": (
                        "resolved_right_karat"
                        if boundary["right_karat"]
                        else "local_karat"
                    ),
                }
                if boundary is not None
                else None
            )
            report["result"]["right_button_inputs_after_boundary"] = (
                sum(
                    tap["sequence"] >= boundary["sequence"]
                    for tap in report["taps"]
                )
                if boundary is not None
                else None
            )
            exit_completed = False
            if result.outcome.value == "gold_keys_exhausted":
                left = runtime.leave_treasure_to_lobby()
                report["exit"] = {
                    "status": left.status.value,
                    "error": left.error,
                    "transition_outcomes": list(left.transition_outcomes),
                    "transition_attempts": list(left.transition_attempts),
                }
                exit_completed = left.status.value == "completed"
            print(f"[burst] result={report['result']}")
            if "exit" in report:
                print(f"[burst] exit={report['exit']}")
            return (
                0
                if result.outcome.value == "gold_keys_exhausted"
                and exit_completed
                else 3
            )
    except KeyboardInterrupt:
        stop.set()
        print("[hil] cancelled by operator; device left untouched.", file=sys.stderr)
        return 130
    finally:
        report_path = save_dir / "report.json"
        try:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"[hil] report: {report_path}")
        except OSError as error:
            print(f"[hil] report write failed: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
