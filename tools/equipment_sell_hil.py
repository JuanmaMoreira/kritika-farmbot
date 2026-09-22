"""Read-only probe or explicitly approved one-sale Equipment HIL harness."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.action_executor import ActionExecutor
from bot.config import RuntimeConfig
from bot.equipment_sell_operation import (
    EquipmentSellCandidate,
    EquipmentSellRequest,
)
from bot.equipment_sell_policy import EquipmentSellAuthorization
from bot.equipment_sell_reader import EquipmentSellReader
from bot.equipment_sell_runtime import EquipmentSellRuntime
from bot.equipment_sell_semantics import (
    DISPOSABLE_GRADES,
    LOW_BULK_GRADES,
    EquipmentBulkGroup,
    EquipmentGrade,
    EquipmentType,
    consensus_facts,
)
from bot.ocr import RapidOcrEngine
from bot.runtime import build_adb_client, build_frame_source


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dotenv", type=Path, default=PROJECT_ROOT / ".env"
    )
    parser.add_argument(
        "--probe",
        choices=("inventory", "detail", "confirmation"),
        default="inventory",
        help="read current facts without sending input",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="send exactly one approved bulk-sale sequence",
    )
    parser.add_argument("--approved-name")
    parser.add_argument(
        "--type", choices=tuple(value.value for value in EquipmentType)
    )
    parser.add_argument(
        "--grade", choices=tuple(value.value for value in EquipmentGrade)
    )
    parser.add_argument("--enhance", choices=("true", "false"))
    parser.add_argument("--page", type=int)
    parser.add_argument("--slot", type=int)
    parser.add_argument(
        "--save-frame",
        type=Path,
        help="optional read-only capture of the current frame",
    )
    return parser.parse_args(argv)


def _read_consensus(source, reader, kind):
    method = getattr(reader, f"{kind}_sample")
    samples = []
    sequences = set()
    deadline = time.monotonic() + 4.0
    while len(sequences) < 4 and time.monotonic() < deadline:
        snapshot = source.get_frame()
        if snapshot.sequence in sequences:
            time.sleep(0.05)
            continue
        sequences.add(snapshot.sequence)
        sample = method(
            snapshot.image,
            sequence=snapshot.sequence,
            observed_at=snapshot.timestamp,
        )
        if sample is not None:
            samples.append(sample)
            fact = consensus_facts(samples, required=2, max_samples=4)
            if fact is not None:
                return fact
        time.sleep(0.05)
    return None


class _ApprovedNameReader:
    def __init__(self, reader, approved_name):
        self.reader = reader
        self.approved_name = " ".join(approved_name.casefold().split())

    def inventory_sample(self, *args, **kwargs):
        return self.reader.inventory_sample(*args, **kwargs)

    def detail_sample(self, *args, **kwargs):
        fact = self.reader.detail_sample(*args, **kwargs)
        if fact is None or " ".join(fact.name.casefold().split()) != self.approved_name:
            return None
        return fact

    def confirmation_sample(self, *args, **kwargs):
        fact = self.reader.confirmation_sample(*args, **kwargs)
        if fact is None or " ".join(fact.item_name.casefold().split()) != self.approved_name:
            return None
        return fact


def _fact_payload(fact):
    if fact is None:
        return None
    payload = dict(vars(fact))
    for key, value in tuple(payload.items()):
        if hasattr(value, "value"):
            payload[key] = value.value
        elif isinstance(value, tuple):
            payload[key] = list(value)
    return payload


def _require_execution_args(args):
    required = {
        "approved_name": args.approved_name,
        "type": args.type,
        "grade": args.grade,
        "enhance": args.enhance,
        "page": args.page,
        "slot": args.slot,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(
            "--execute requires explicit " + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        )


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.execute:
        _require_execution_args(args)
    config = RuntimeConfig.from_env(dotenv_path=args.dotenv)
    adb = build_adb_client(config)
    if adb.get_state() != "device":
        print("ADB device is not ready", file=sys.stderr)
        return 2
    reader = EquipmentSellReader(RapidOcrEngine())
    source = build_frame_source(
        config, adb_client=adb, video_bit_rate=8_000_000, max_fps=30
    )
    with source:
        if not args.execute:
            if args.save_frame is not None:
                args.save_frame.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(args.save_frame), source.get_frame().image):
                    raise OSError(f"could not save {args.save_frame}")
            fact = _read_consensus(source, reader, args.probe)
            print(json.dumps(_fact_payload(fact), indent=2, sort_keys=True))
            return int(fact is None)

        grade = EquipmentGrade(args.grade)
        if grade not in DISPOSABLE_GRADES:
            raise ValueError("HIL harness refuses Ethereal+ and unknown grades")
        authorization = EquipmentSellAuthorization(
            allowed_types=frozenset({EquipmentType(args.type)}),
            allowed_grades=frozenset({grade}),
            allowed_enhance_states=frozenset({args.enhance == "true"}),
            allowed_bulk_groups=frozenset(
                {
                    (
                        EquipmentBulkGroup.ENHANCE_GRADE
                        if args.enhance == "true"
                        else EquipmentBulkGroup.EQUIPMENT_GRADE
                    )
                    if grade in LOW_BULK_GRADES
                    else EquipmentBulkGroup.TYPE_GRADE
                }
            ),
            label="explicit-chat-approved-hil",
        )
        runtime = EquipmentSellRuntime(
            source,
            _ApprovedNameReader(reader, args.approved_name),
            ActionExecutor(adb),
        )
        result = runtime.execute(
            EquipmentSellRequest(
                authorization=authorization,
                candidate=EquipmentSellCandidate(args.page, args.slot),
            )
        )
        print(
            json.dumps(
                {
                    "outcome": result.outcome.value,
                    "reason": result.reason,
                    "before": _fact_payload(result.before),
                    "item": _fact_payload(result.item),
                    "confirmation": _fact_payload(result.confirmation),
                    "after": _fact_payload(result.after),
                    "inputs": list(result.inputs),
                    "confirm_count": result.confirm_count,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return int(not result.succeeded)


if __name__ == "__main__":
    raise SystemExit(main())
