"""Incremental evaluator for the curated Craft OCR slice."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2

from bot.craft_reader import CraftReader
from bot.ocr import RapidOcrEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "datasets" / "craft_semantic_manifest.json"


def evaluate(manifest_path: Path = DEFAULT_MANIFEST) -> tuple[int, int]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    reader = CraftReader(RapidOcrEngine())
    wrong = 0
    for sequence, entry in enumerate(payload["entries"], 1):
        path = PROJECT_ROOT / entry["path"]
        data = path.read_bytes()
        image = cv2.imread(str(path))
        facts = {
            "quick_menu": reader.quick_menu_sample(image, sequence=sequence, observed_at=float(sequence)),
            "context": reader.context_sample(image, sequence=sequence, observed_at=float(sequence)),
            "recipe": reader.recipe_sample(image, sequence=sequence, observed_at=float(sequence)),
            "boundary": reader.currency_boundary_sample(image, sequence=sequence, observed_at=float(sequence)),
            "result": reader.result_sample(image, sequence=sequence, observed_at=float(sequence)),
        }
        actual = _actual(entry["kind"], facts.get(entry["kind"]))
        false_positives = [name for name, fact in facts.items() if fact is not None and name != entry["kind"]]
        errors = []
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            errors.append("sha256")
        if actual != entry["expected"]:
            errors.append(f"expected={entry['expected']!r} actual={actual!r}")
        if false_positives:
            errors.append(f"cross-kind false positives={false_positives}")
        if errors:
            wrong += 1
            print(f"WRONG {entry['path']}: {'; '.join(errors)}")
        else:
            print(f"PASS  {entry['path']}")
    total = len(payload["entries"])
    print(f"craft evaluator: {total - wrong}/{total} pass; {wrong} wrong")
    return total, wrong


def _actual(kind, fact):
    if fact is None:
        return None
    if kind == "quick_menu":
        return {"lobby": fact.lobby_label, "craft": fact.craft_label, "guild": fact.guild_label}
    if kind == "context":
        return {
            "weapon_material": fact.weapon_material,
            "armor_material": fact.armor_material,
            "accessory_material": fact.accessory_material,
            "capacity": fact.weapon_capacity,
            "hero_cost": fact.weapon_hero_cost,
        }
    if kind == "recipe":
        return {
            "family": fact.family.value,
            "tier": fact.tier.value,
            "item_type": fact.item_type.value,
            "currency": fact.currency.value,
            "unit_cost": fact.unit_cost,
            "quantity": fact.quantity,
            "quantity_cap": fact.quantity_cap,
        }
    if kind == "boundary":
        return {
            "missing_material": fact.missing_material,
            "karat_cost": fact.karat_cost,
            "reject_label": fact.reject_label,
        }
    if kind == "result":
        return {"marker": fact.marker}
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    _total, wrong = evaluate(args.manifest)
    return int(wrong > 0)


if __name__ == "__main__":
    raise SystemExit(main())
