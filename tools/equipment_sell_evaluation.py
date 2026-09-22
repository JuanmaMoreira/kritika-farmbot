"""Incremental evaluator for Equipment Sell OCR facts and contextual negatives."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2

from bot.equipment_sell_reader import EquipmentSellReader
from bot.ocr import RapidOcrEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "datasets" / "equipment_sell_semantic_manifest.json"


def evaluate(manifest_path: Path = DEFAULT_MANIFEST) -> tuple[int, int]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    reader = EquipmentSellReader(RapidOcrEngine())
    wrong = 0
    for sequence, entry in enumerate(payload["entries"], 1):
        path = PROJECT_ROOT / entry["path"]
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        image = cv2.imread(str(path))
        if image is None:
            print(f"WRONG {entry['path']}: unreadable image")
            wrong += 1
            continue
        inventory = reader.inventory_sample(
            image, sequence=sequence, observed_at=float(sequence)
        )
        detail = reader.detail_sample(
            image, sequence=sequence, observed_at=float(sequence)
        )
        confirmation = reader.confirmation_sample(
            image, sequence=sequence, observed_at=float(sequence)
        )
        actual = _actual(entry["kind"], inventory, detail, confirmation)
        errors = []
        if digest != entry["sha256"]:
            errors.append("sha256")
        if actual != entry["expected"]:
            errors.append(f"expected={entry['expected']!r} actual={actual!r}")
        if entry["kind"] == "inventory" and (detail is not None or confirmation is not None):
            errors.append("cross-kind false positive")
        if entry["kind"] == "detail" and (inventory is not None or confirmation is not None):
            errors.append("cross-kind false positive")
        if entry["kind"] == "confirmation" and (inventory is not None or detail is not None):
            errors.append("cross-kind false positive")
        if entry["kind"] == "none" and any(
            value is not None for value in (inventory, detail, confirmation)
        ):
            errors.append("negative false positive")
        if errors:
            wrong += 1
            print(f"WRONG {entry['path']}: {'; '.join(errors)}")
        else:
            print(f"PASS  {entry['path']}")
    total = len(payload["entries"])
    print(f"equipment-sell evaluator: {total - wrong}/{total} pass; {wrong} wrong")
    return total, wrong


def _actual(kind, inventory, detail, confirmation):
    if kind == "inventory" and inventory is not None:
        return {
            "item_count": inventory.item_count,
            "capacity": inventory.capacity,
            "page": inventory.page,
            "total_pages": inventory.total_pages,
        }
    if kind == "detail" and detail is not None:
        return {
            "name": detail.name,
            "grade": detail.grade.value,
            "equipment_type": detail.equipment_type.value,
            "enhance": detail.enhance,
        }
    if kind == "confirmation" and confirmation is not None:
        return {
            "item_name": confirmation.item_name,
            "group": confirmation.group.value,
            "group_type": (
                confirmation.group_type.value
                if confirmation.group_type is not None
                else None
            ),
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    _total, wrong = evaluate(args.manifest)
    return int(wrong > 0)


if __name__ == "__main__":
    raise SystemExit(main())
