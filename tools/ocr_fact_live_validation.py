"""Read and preserve live OCR Runtime Fact evidence without sending input."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import cv2

from bot.catalog import build_default_resolver
from bot.config import RuntimeConfig
from bot.ocr_extractors import BATTLE_TIMER_REMAINING, RESOURCE_SAPPHIRES
from bot.perception import build_default_perception
from bot.runtime import (
    build_adb_client,
    build_frame_source,
    build_runtime_fact_reader,
)
from bot.runtime_observer import RuntimeObserver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "screencaps" / "semantic" / "ocr_runtime_facts"
FACT_NAMES = {
    "sapphires": RESOURCE_SAPPHIRES,
    "timer": BATTLE_TIMER_REMAINING,
}


class RecordingSource:
    """Retain only distinct frames actually observed by the fact reader."""

    def __init__(self, source) -> None:
        self.source = source
        self.frames = {}

    def get_frame(self):
        snapshot = self.source.get_frame()
        self.frames.setdefault(snapshot.sequence, snapshot)
        return snapshot


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fact", choices=tuple(FACT_NAMES))
    parser.add_argument("--dotenv", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reads", type=_positive_int, default=3)
    parser.add_argument("--timeout", type=_positive_float, default=5.0)
    parser.add_argument("--interval", type=_non_negative_float, default=0.75)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()
    output.relative_to(PROJECT_ROOT)
    semantic_name = FACT_NAMES[args.fact]
    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    adb = build_adb_client(config)
    source = build_frame_source(config, adb_client=adb, max_fps=15)
    perception = build_default_perception(PROJECT_ROOT)
    resolver = build_default_resolver()
    records = []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_directory = output / args.fact / stamp

    if adb.get_state() != "device":
        raise RuntimeError("ADB device is not available")

    with source:
        recording = RecordingSource(source)
        observer = RuntimeObserver(recording, perception, resolver)
        reader = build_runtime_fact_reader(observer)
        baseline = observer.observe()
        after_sequence = baseline.sequence
        for index in range(args.reads):
            result = reader.read_fact(
                semantic_name,
                after_sequence=after_sequence,
                timeout=args.timeout,
            )
            evidence = []
            for sample in result.evidence:
                captured = recording.frames.get(sample.sequence)
                relative_path = None
                if captured is not None:
                    run_directory.mkdir(parents=True, exist_ok=True)
                    path = run_directory / f"sequence-{sample.sequence}.png"
                    if not path.exists() and not cv2.imwrite(
                        str(path), captured.image
                    ):
                        raise OSError(f"OpenCV could not save {path}")
                    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
                evidence.append(
                    {
                        "sequence": sample.sequence,
                        "timestamp": sample.timestamp,
                        "raw_text": sample.raw_text,
                        "ocr_confidence": sample.ocr_confidence,
                        "frame_path": relative_path,
                    }
                )
            record = {
                "fact": semantic_name,
                "status": result.status.value,
                "value": result.fact.value if result.fact is not None else None,
                "confidence": (
                    result.fact.confidence if result.fact is not None else None
                ),
                "quality": (
                    result.fact.quality.value if result.fact is not None else None
                ),
                "context": (
                    result.fact.context if result.fact is not None else None
                ),
                "evidence": evidence,
                "detail": result.detail,
                "human_confirmation": "pending",
            }
            records.append(record)
            print(json.dumps(record, sort_keys=True))
            if result.evidence:
                after_sequence = result.evidence[-1].sequence
            if index + 1 < args.reads:
                time.sleep(args.interval)

    run_directory.mkdir(parents=True, exist_ok=True)
    report_path = run_directory / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "source": "live_scrcpy",
                "sent_device_input": False,
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"report={report_path.relative_to(PROJECT_ROOT).as_posix()}")
    return 0 if all(item["status"] == "confirmed" for item in records) else 1


def _positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def _positive_float(value: str) -> float:
    result = float(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def _non_negative_float(value: str) -> float:
    result = float(value)
    if result < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[ocr-live] FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
