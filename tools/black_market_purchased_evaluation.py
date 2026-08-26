"""Evaluate Black Market Purchased facts over reviewed slot evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Iterable

import cv2

from bot.catalog import SCREEN_BLACK_MARKET
from bot.perception import (
    BLACK_MARKET_PURCHASED_CONFIDENCE_THRESHOLD,
    BLACK_MARKET_SLOT_COUNT,
    BlackMarketPurchasedDetector,
)
from tools.black_market_gold_evaluation import (
    DEFAULT_CURRENCY_MANIFEST,
    load_currency_manifest,
)
from tools.production_perception_evaluation import DEFAULT_MANIFEST_PATHS
from tools.semantic_slice_evaluation import CONFIRMED, load_manifest


@dataclass(frozen=True)
class PurchasedSlotMetrics:
    positives: int
    negatives: int
    true_positives: int
    false_positives: int
    false_negatives: int
    positive_min: float | None
    negative_max: float


@dataclass(frozen=True)
class PurchasedEvaluationReport:
    frames: int
    positives: int
    negatives: int
    unrelated_screen_negatives: int
    gold_negatives: int
    karats_negatives: int
    video_negatives: int
    true_positives: int
    false_positives: int
    false_negatives: int
    false_positives_on_gold: int
    false_positives_on_karats: int
    false_positives_on_video: int
    raw_positive_min: float
    raw_positive_median: float
    raw_positive_max: float
    raw_negative_max: float
    raw_gap: float
    confidence_threshold: float
    by_slot: dict[int, PurchasedSlotMetrics]


def evaluate_black_market_purchased(
    repository_root: str | Path,
    *,
    currency_manifest: str | Path = DEFAULT_CURRENCY_MANIFEST,
    context_manifests: Iterable[str | Path] = DEFAULT_MANIFEST_PATHS,
) -> PurchasedEvaluationReport:
    root = Path(repository_root).resolve()
    manifest_path = Path(currency_manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    entries = load_currency_manifest(manifest_path)
    detector = BlackMarketPurchasedDetector(asset_root=root)

    positives: list[float] = []
    negatives: list[float] = []
    tp = fp = fn = 0
    false_positive_labels = {"GOLD": 0, "KARATS": 0, "VIDEO": 0}
    negative_labels = {"GOLD": 0, "KARATS": 0, "VIDEO": 0}
    by_slot_values = {
        index: {"pos": [], "neg": [], "tp": 0, "fp": 0, "fn": 0}
        for index in range(BLACK_MARKET_SLOT_COUNT)
    }

    for entry in entries:
        frame = cv2.imread(str(root / entry.path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"Purchased evidence is unreadable: {entry.path}")
        readings = detector.measure(frame)
        emitted = {int(item.value) for item in detector.detect(frame)}
        for index, (label, reading) in enumerate(zip(entry.slots, readings)):
            positive = label == "PURCHASED"
            predicted = index in emitted
            target = positives if positive else negatives
            target.append(reading.raw_match_score)
            values = by_slot_values[index]
            values["pos" if positive else "neg"].append(reading.raw_match_score)
            if not positive:
                negative_labels[label] += 1
            if positive and predicted:
                tp += 1
                values["tp"] += 1
            elif positive:
                fn += 1
                values["fn"] += 1
            elif predicted:
                fp += 1
                values["fp"] += 1
                false_positive_labels[label] += 1

    unrelated = 0
    for manifest in context_manifests:
        path = Path(manifest)
        if not path.is_absolute():
            path = root / path
        for entry in load_manifest(path):
            if entry.review_status != CONFIRMED or entry.base_context == SCREEN_BLACK_MARKET:
                continue
            frame = cv2.imread(str(root / entry.path), cv2.IMREAD_COLOR)
            if frame is None:
                raise FileNotFoundError(f"Context evidence is unreadable: {entry.path}")
            readings = detector.measure(frame)
            emitted = detector.detect(frame)
            unrelated += len(readings)
            negatives.extend(item.raw_match_score for item in readings)
            for index, reading in enumerate(readings):
                by_slot_values[index]["neg"].append(reading.raw_match_score)
            fp += len(emitted)
            for observation in emitted:
                by_slot_values[int(observation.value)]["fp"] += 1

    by_slot = {
        index: PurchasedSlotMetrics(
            positives=len(values["pos"]),
            negatives=len(values["neg"]),
            true_positives=values["tp"],
            false_positives=values["fp"],
            false_negatives=values["fn"],
            positive_min=min(values["pos"]) if values["pos"] else None,
            negative_max=max(values["neg"], default=0.0),
        )
        for index, values in by_slot_values.items()
    }
    return PurchasedEvaluationReport(
        frames=len(entries),
        positives=len(positives),
        negatives=len(negatives),
        unrelated_screen_negatives=unrelated,
        gold_negatives=negative_labels["GOLD"],
        karats_negatives=negative_labels["KARATS"],
        video_negatives=negative_labels["VIDEO"],
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        false_positives_on_gold=false_positive_labels["GOLD"],
        false_positives_on_karats=false_positive_labels["KARATS"],
        false_positives_on_video=false_positive_labels["VIDEO"],
        raw_positive_min=min(positives),
        raw_positive_median=median(positives),
        raw_positive_max=max(positives),
        raw_negative_max=max(negatives),
        raw_gap=min(positives) - max(negatives),
        confidence_threshold=BLACK_MARKET_PURCHASED_CONFIDENCE_THRESHOLD,
        by_slot=by_slot,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--output", default="artifacts/black-market-purchased-evaluation.json"
    )
    args = parser.parse_args(argv)
    report = evaluate_black_market_purchased(args.repo_root)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    destination.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
