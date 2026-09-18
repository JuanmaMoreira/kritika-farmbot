"""Opt-in HIL calibration for the E2.2 Gold Key fast drain (Treasure-only).

One condition per run, chat+steer channel: the user holds the device in
Treasure with the Gold-backed right button visible and approves every
burst explicitly (interval + max inputs announced before each run).

Modes (no navigation, no Trading/C6b, no leave: the user owns the
device before and after):

- ``dry-run`` (default): observe only, classify the live state
  (RIGHT_GOLD_OPEN_MAX / RIGHT_KARAT_OPEN / contradiction / foreign),
  save frames + report. Zero taps, always safe.
- ``burst``: E2 single-open entry (``TreasureRuntime``,
  ``OPEN_ONCE``, 1 key, fully verified) then ``drain_gold_keys_fast``
  with the requested cadence and caps. Stops on Karat boundary,
  contradiction, stall, context loss, cancel or deadline.

Evidence lands under ``artifacts/hil_e2_fastdrain/<stamp>/`` (raws, not
versioned): ``frame_*.png`` per fast-loop observation plus
``report.json`` with telemetry, per-tap observations and the human GT
line the operator confirms in chat.

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
from bot.runtime import build_adb_client, build_frame_source  # noqa: E402
from bot.runtime_observer import RuntimeObserver  # noqa: E402
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
    resolve_right_button_target,
)
from bot.treasure_keys import GoldKeyQuantity, GoldKeyQuantityMode  # noqa: E402
from bot.treasure_runtime import TreasureRuntime  # noqa: E402
from bot.verified_transition import VerifiedTransition  # noqa: E402

ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "hil_e2_fastdrain"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("dry-run", "burst"), default="dry-run",
        help="dry-run observes only; burst taps with approval",
    )
    parser.add_argument("--interval", type=float, default=0.20)
    parser.add_argument("--max-inputs", type=int, default=15)
    parser.add_argument("--watchdog-every", type=int, default=10)
    parser.add_argument("--deadline", type=float, default=60.0)
    parser.add_argument("--dry-run-seconds", type=float, default=4.0)
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
        "max_inputs": args.max_inputs,
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
            initial = observe()
            entry_reason = check_fast_drain_entry(
                initial, initial_open_verified=True
            )
            print(
                f"[burst] fast entry: {_describe(initial)} "
                f"refusal={entry_reason}"
            )
            if entry_reason is not None:
                print("[burst] fast entry refused: zero fast inputs.")
                return 2

            drain_config = GoldKeyDrainConfig(
                tap_interval_s=args.interval,
                watchdog_every=args.watchdog_every,
                safety_deadline_s=args.deadline,
                max_inputs=args.max_inputs,
            )

            def tap(point) -> None:
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
                report["taps"].append(info)
                print(
                    f"[burst] tap #{len(report['taps'])} point={point} "
                    f"seq={info['sequence']} obs={info['observations']}"
                )

            def counting_observe():
                snapshot = observe()
                index = len(report["frames"])
                report["frames"].append(_describe(snapshot))
                try:
                    import cv2

                    cv2.imwrite(
                        str(save_dir / f"drain_{index:04d}.png"),
                        snapshot.frame.image,
                    )
                except Exception:
                    pass
                return snapshot

            target_point = resolve_right_button_target(initial)
            print(
                f"[burst] interval={args.interval}s max_inputs={args.max_inputs} "
                f"watchdog_every={args.watchdog_every} "
                f"initial_target={target_point}"
            )
            result = drain_gold_keys_fast(
                initial_snapshot=initial,
                observe=counting_observe,
                tap=tap,
                config=drain_config,
                initial_open_verified=True,
                cancel_requested=cancel_requested,
                clock=time.monotonic,
                sleeper=time.sleep,
            )
            report["result"] = {
                "outcome": result.outcome.value,
                "inputs_emitted": result.inputs_emitted,
                "watchdogs_run": result.watchdogs_run,
                "gold_button_observations": result.gold_button_observations,
                "karat_boundary_seen": result.karat_boundary_seen,
                "elapsed_s": result.elapsed_s,
                "reason": result.reason,
                "evidence": list(result.evidence),
            }
            print(f"[burst] result={report['result']}")
            return 0 if result.outcome.value == "gold_keys_exhausted" else 3
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
