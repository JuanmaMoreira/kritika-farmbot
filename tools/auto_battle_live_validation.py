"""Supervised live validation for temporal Auto Battle detection and ensure-on."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import cv2
import numpy as np

from bot.action_executor import ActionExecutor
from bot.auto_battle import AutoBattleDetector, AutoBattleEnsurer
from bot.catalog import build_default_resolver
from bot.config import RuntimeConfig
from bot.perception import build_default_perception
from bot.runtime import build_adb_client, build_frame_source
from bot.runtime_observer import RuntimeObserver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "auto-battle-live"


class RecordingSource:
    def __init__(self, source) -> None:
        self.source = source
        self.frames = {}

    def get_frame(self):
        snapshot = self.source.get_frame()
        self.frames.setdefault(snapshot.sequence, snapshot)
        return snapshot


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("detect", "ensure"))
    parser.add_argument("--ground-truth", choices=("off", "on", "pending"), default="pending")
    parser.add_argument("--reads", type=int, default=3)
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def _record(reading, recording, run_directory, index):
    return _record_fact(
        reading.fact,
        reading.evidence,
        reading.status.value,
        reading.detail,
        recording,
        run_directory,
        index,
    )


def _record_fact(
    fact,
    samples,
    status,
    detail,
    recording,
    run_directory,
    index,
):
    evidence = []
    for sample in samples:
        captured = recording.frames.get(sample.sequence)
        frame_path = None
        if captured is not None:
            path = run_directory / f"read-{index:02d}-sequence-{sample.sequence}.png"
            if not cv2.imwrite(str(path), captured.image):
                raise OSError(f"OpenCV could not save {path}")
            frame_path = path.relative_to(PROJECT_ROOT).as_posix()
        evidence.append(
            {
                "sequence": sample.sequence,
                "timestamp": sample.timestamp,
                "activity": sample.activity,
                "frame_path": frame_path,
            }
        )
    return {
        "status": status,
        "value": fact.value.value if fact is not None else None,
        "confidence": fact.confidence if fact is not None else None,
        "activity": (
            float(np.median([item["activity"] for item in evidence[1:]]))
            if len(evidence) > 1
            else None
        ),
        "activity_mean": (
            float(np.mean([item["activity"] for item in evidence[1:]]))
            if len(evidence) > 1
            else None
        ),
        "frame_count": len(evidence),
        "duration": (
            evidence[-1]["timestamp"] - evidence[0]["timestamp"]
            if len(evidence) > 1
            else 0.0
        ),
        "evidence": evidence,
        "detail": detail,
    }


def main(argv=None):
    args = parse_args(argv)
    if args.reads <= 0:
        raise ValueError("reads must be positive")
    output = args.output.resolve()
    output.relative_to(PROJECT_ROOT)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_directory = output / f"{stamp}-{args.command}-{args.ground_truth}"
    run_directory.mkdir(parents=True, exist_ok=False)
    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    adb = build_adb_client(config)
    if adb.get_state() != "device":
        raise RuntimeError("ADB device is not available")
    source = build_frame_source(config, adb_client=adb, max_fps=15)
    records = []
    with source:
        recording = RecordingSource(source)
        observer = RuntimeObserver(
            recording,
            build_default_perception(PROJECT_ROOT),
            build_default_resolver(),
        )
        detector = AutoBattleDetector(observer)
        baseline = observer.observe()
        if args.command == "detect":
            cursor = baseline.sequence
            for index in range(1, args.reads + 1):
                reading = detector.observe(after_sequence=cursor)
                record = _record(reading, recording, run_directory, index)
                records.append(record)
                print(json.dumps(record, sort_keys=True))
                if reading.evidence:
                    cursor = reading.evidence[-1].sequence
                if index < args.reads:
                    time.sleep(0.15)
            tap_count = 0
        else:
            actions = ActionExecutor(adb)
            result = AutoBattleEnsurer(detector, actions).ensure_on(
                after_sequence=baseline.sequence
            )
            records = [
                _record_fact(
                    item,
                    item.evidence,
                    "confirmed",
                    None,
                    recording,
                    run_directory,
                    index,
                )
                for index, item in enumerate(result.observations, start=1)
            ]
            tap_count = result.tap_count
            print(
                json.dumps(
                    {
                        "ensure_status": result.status.value,
                        "tap_count": tap_count,
                        "detail": result.detail,
                    },
                    sort_keys=True,
                )
            )
    report = {
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": args.command,
        "human_ground_truth": args.ground_truth,
        "sent_device_input": args.command == "ensure" and tap_count > 0,
        "tap_count": tap_count,
        "records": records,
    }
    report_path = run_directory / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"report={report_path.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
