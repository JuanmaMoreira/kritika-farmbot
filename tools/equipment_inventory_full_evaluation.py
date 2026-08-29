"""Incremental raw-score audit for promoted Equipment Full semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    INDICATOR_COMBINE_ROW_BOTTOM,
    INDICATOR_COMBINE_ROWS,
    INDICATOR_COMBINE_ROWS_UPPER,
    LANDMARK_COMBINE_ALL_TITLE,
    LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE,
    LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT,
    LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT,
    LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE,
    LANDMARK_COMBINE_FUSE_ACTIVE,
    LANDMARK_COMBINE_FUSE_TAB,
    LANDMARK_COMBINE_TRANSMUTE_ACTIVE,
    LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT,
    MODE_COMBINE_FUSE,
    MODE_COMBINE_TRANSMUTE,
    PANEL_COMBINE_AWAKENED_TRANSMUTE,
    PANEL_COMBINE_ETHEREAL_RANDOM_PART,
    POPUP_COMBINE_ALL,
    POPUP_EQUIPMENT_INVENTORY_FULL,
    POPUP_ETHEREAL_MASS_COMBINE,
    POPUP_ETHEREAL_NO_MATERIAL,
    SCREEN_COMBINE,
)
from bot.perception import (
    COMBINE_ALL_TITLE_SPEC,
    COMBINE_ANIMATION_TAPPABLE_SPEC,
    COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC,
    COMBINE_ETHEREAL_MASS_PROMPT_SPEC,
    COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC,
    COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC,
    COMBINE_FUSE_ACTIVE_SPEC,
    COMBINE_FUSE_TAB_SPEC,
    COMBINE_ROW_BOTTOM_INDICATOR_SPEC,
    COMBINE_ROWS_INDICATOR_SPEC,
    COMBINE_ROWS_UPPER_INDICATOR_SPEC,
    COMBINE_TRANSMUTE_ACTIVE_SPEC,
    EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC,
    LocalCvDetector,
)
from tools.incremental_perception_evaluation import (
    evaluate_detector_frame_pairs,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/equipment_inventory_full_semantic_manifest.json"
DEFAULT_CACHE = ROOT / "artifacts/equipment-inventory-full-evaluation/cache.json"
DEFAULT_OUTPUT = ROOT / "artifacts/equipment-inventory-full-evaluation/report.json"

SPECS = (
    EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC,
    COMBINE_FUSE_TAB_SPEC,
    COMBINE_FUSE_ACTIVE_SPEC,
    COMBINE_TRANSMUTE_ACTIVE_SPEC,
    COMBINE_ROWS_INDICATOR_SPEC,
    COMBINE_ROWS_UPPER_INDICATOR_SPEC,
    COMBINE_ROW_BOTTOM_INDICATOR_SPEC,
    COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC,
    COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC,
    COMBINE_ALL_TITLE_SPEC,
    COMBINE_ETHEREAL_MASS_PROMPT_SPEC,
    COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC,
    COMBINE_ANIMATION_TAPPABLE_SPEC,
)


def _labels(
    entry: dict[str, object],
    observation_groups: dict[str, set[str]] | None = None,
) -> set[str]:
    labels = set(entry.get("overlays", ()))
    labels.update(entry.get("observations", ()))
    base = entry.get("base_context")
    if isinstance(base, str):
        labels.add(base)
    group = Path(str(entry.get("path", ""))).parent.name
    for observation, groups in (observation_groups or {}).items():
        if group in groups:
            labels.add(observation)
    return labels


EXPECTED_LABELS = {
    LANDMARK_EQUIPMENT_INVENTORY_FULL_PROMPT: {POPUP_EQUIPMENT_INVENTORY_FULL},
    LANDMARK_COMBINE_FUSE_TAB: {SCREEN_COMBINE},
    LANDMARK_COMBINE_FUSE_ACTIVE: {MODE_COMBINE_FUSE},
    LANDMARK_COMBINE_TRANSMUTE_ACTIVE: {MODE_COMBINE_TRANSMUTE},
    INDICATOR_COMBINE_ROWS: {INDICATOR_COMBINE_ROWS},
    INDICATOR_COMBINE_ROWS_UPPER: {INDICATOR_COMBINE_ROWS_UPPER},
    INDICATOR_COMBINE_ROW_BOTTOM: {INDICATOR_COMBINE_ROW_BOTTOM},
    LANDMARK_COMBINE_AWAKENED_TRANSMUTE_TITLE: {
        PANEL_COMBINE_AWAKENED_TRANSMUTE
    },
    LANDMARK_COMBINE_ETHEREAL_RANDOM_PART_TITLE: {
        PANEL_COMBINE_ETHEREAL_RANDOM_PART
    },
    LANDMARK_COMBINE_ALL_TITLE: {POPUP_COMBINE_ALL},
    LANDMARK_COMBINE_ETHEREAL_MASS_PROMPT: {POPUP_ETHEREAL_MASS_COMBINE},
    LANDMARK_COMBINE_ETHEREAL_NO_MATERIAL_PROMPT: {
        POPUP_ETHEREAL_NO_MATERIAL
    },
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE: {
        ACTIVITY_COMBINE_ANIMATION_TAPPABLE
    },
}


def _confirmed_entries(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = payload.get("entries", ())
    if not isinstance(entries, list):
        return []
    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("review_status") == "confirmed"
        and isinstance(entry.get("path"), str)
        and (ROOT / entry["path"]).is_file()
    ]


def _observation_groups(path: Path) -> dict[str, set[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = payload.get("curation", {}).get("observation_groups", {})
    if not isinstance(raw, dict):
        return {}
    return {
        name: {str(group) for group in groups}
        for name, groups in raw.items()
        if isinstance(name, str) and isinstance(groups, list)
    }


def evaluate(*, cache: Path, full_rebuild: bool) -> dict[str, object]:
    labels_by_path: dict[str, set[str]] = {}
    for manifest in sorted((ROOT / "datasets").glob("*.json")):
        groups = _observation_groups(manifest)
        for entry in _confirmed_entries(manifest):
            labels_by_path.setdefault(entry["path"], set()).update(
                _labels(entry, groups)
            )
    corpus_paths = set(labels_by_path)

    detectors = tuple(LocalCvDetector(spec, asset_root=ROOT) for spec in SPECS)
    frames, stats = evaluate_detector_frame_pairs(
        ROOT,
        sorted(corpus_paths),
        detectors,
        cache_path=cache,
        full_rebuild=full_rebuild,
    )
    summaries = {}
    for spec in SPECS:
        expected = EXPECTED_LABELS[spec.name]
        positives = []
        negatives = []
        for frame in frames:
            score = frame.raw_scores[spec.name]
            if expected.intersection(labels_by_path.get(frame.path, set())):
                positives.append((frame.path, score))
            else:
                negatives.append((frame.path, score))
        if not positives or not negatives:
            raise RuntimeError(f"incomplete evidence for {spec.name}")
        weakest = min(positives, key=lambda item: item[1])
        strongest = max(negatives, key=lambda item: item[1])
        summaries[spec.name] = {
            "positive_count": len(positives),
            "negative_count": len(negatives),
            "positive_raw_range": [weakest[1], max(item[1] for item in positives)],
            "weakest_positive": weakest[0],
            "strongest_negative": strongest[1],
            "strongest_negative_path": strongest[0],
            "separated": strongest[1] < weakest[1],
        }
    return {"stats": stats.__dict__, "detectors": summaries}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--full-rebuild", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate(cache=args.cache, full_rebuild=args.full_rebuild)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(item["separated"] for item in report["detectors"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
