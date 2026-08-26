"""Evaluate the minimal fixed-grid Black Market GOLD detector offline."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Iterable

import cv2

from bot.catalog import SCREEN_BLACK_MARKET
from bot.perception import (
    BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD,
    BLACK_MARKET_SLOT_COUNT,
    BlackMarketGoldDetector,
)
from tools.production_perception_evaluation import DEFAULT_MANIFEST_PATHS
from tools.semantic_slice_evaluation import CONFIRMED, load_manifest


DEFAULT_CURRENCY_MANIFEST = "datasets/black_market_currency_manifest.json"
SUPPORTED_CURRENCIES = frozenset({"GOLD", "KARATS", "VIDEO", "PURCHASED"})
SUPPORTED_REVIEW_STATUSES = frozenset({"human_confirmed", "visual_reviewed"})


@dataclass(frozen=True)
class CurrencyEntry:
    path: str
    review_status: str
    slots: tuple[str, ...]

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path)
        if (
            not self.path
            or path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or "\\" in self.path
        ):
            raise ValueError("currency evidence path must be repository-relative POSIX")
        if self.review_status not in SUPPORTED_REVIEW_STATUSES:
            raise ValueError("unsupported currency review_status")
        slots = tuple(self.slots)
        if len(slots) != BLACK_MARKET_SLOT_COUNT:
            raise ValueError("currency evidence must label exactly ten slots")
        if any(item not in SUPPORTED_CURRENCIES for item in slots):
            raise ValueError("unsupported slot currency label")
        object.__setattr__(self, "path", path.as_posix())
        object.__setattr__(self, "slots", slots)


@dataclass(frozen=True)
class SlotMetrics:
    positives: int
    negatives: int
    true_positives: int
    false_positives: int
    false_negatives: int
    positive_min: float | None
    negative_max: float


@dataclass(frozen=True)
class GoldEvaluationReport:
    frames: int
    black_market_slot_examples: int
    evaluated_slot_examples: int
    positives: int
    negatives: int
    karats_negatives: int
    unrelated_screen_negatives: int
    true_positives: int
    false_positives: int
    false_positives_on_karats: int
    false_negatives: int
    raw_positive_min: float
    raw_positive_median: float
    raw_positive_max: float
    raw_negative_max: float
    raw_gap: float
    confidence_threshold: float
    by_slot: dict[int, SlotMetrics]


def load_currency_manifest(path: str | Path) -> tuple[CurrencyEntry, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("unsupported Black Market currency manifest version")
    entries = tuple(
        CurrencyEntry(
            path=item["path"],
            review_status=item["review_status"],
            slots=tuple(item["slots"]),
        )
        for item in payload.get("entries", ())
    )
    paths = tuple(item.path for item in entries)
    if len(paths) != len(set(paths)):
        raise ValueError("currency evidence paths must be unique")
    return entries


def evaluate_black_market_gold(
    repository_root: str | Path,
    *,
    currency_manifest: str | Path = DEFAULT_CURRENCY_MANIFEST,
    context_manifests: Iterable[str | Path] = DEFAULT_MANIFEST_PATHS,
) -> GoldEvaluationReport:
    root = Path(repository_root).resolve()
    manifest_path = Path(currency_manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    entries = load_currency_manifest(manifest_path)
    detector = BlackMarketGoldDetector(asset_root=root)

    positives: list[float] = []
    negatives: list[float] = []
    tp = fp = fn = fp_karats = karats = 0
    by_slot_values = {
        index: {"pos": [], "neg": [], "tp": 0, "fp": 0, "fn": 0}
        for index in range(BLACK_MARKET_SLOT_COUNT)
    }
    for entry in entries:
        frame = cv2.imread(str(root / entry.path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"Currency evidence is unreadable: {entry.path}")
        readings = detector.measure(frame)
        emitted = {item.value for item in detector.detect(frame)}
        for index, (label, reading) in enumerate(zip(entry.slots, readings)):
            positive = label == "GOLD"
            predicted = index in emitted
            target = positives if positive else negatives
            target.append(reading.raw_match_score)
            per_slot = by_slot_values[index]
            per_slot["pos" if positive else "neg"].append(reading.raw_match_score)
            if positive and predicted:
                tp += 1
                per_slot["tp"] += 1
            elif positive:
                fn += 1
                per_slot["fn"] += 1
            elif predicted:
                fp += 1
                per_slot["fp"] += 1
                fp_karats += int(label == "KARATS")
            karats += int(label == "KARATS")

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
        index: SlotMetrics(
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
    return GoldEvaluationReport(
        frames=len(entries),
        black_market_slot_examples=len(entries) * BLACK_MARKET_SLOT_COUNT,
        evaluated_slot_examples=len(positives) + len(negatives),
        positives=len(positives),
        negatives=len(negatives),
        karats_negatives=karats,
        unrelated_screen_negatives=unrelated,
        true_positives=tp,
        false_positives=fp,
        false_positives_on_karats=fp_karats,
        false_negatives=fn,
        raw_positive_min=min(positives),
        raw_positive_median=median(positives),
        raw_positive_max=max(positives),
        raw_negative_max=max(negatives),
        raw_gap=min(positives) - max(negatives),
        confidence_threshold=BLACK_MARKET_GOLD_CONFIDENCE_THRESHOLD,
        by_slot=by_slot,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="artifacts/black-market-gold-evaluation.json")
    args = parser.parse_args(argv)
    report = evaluate_black_market_gold(args.repo_root)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
