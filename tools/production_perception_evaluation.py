"""Evaluate Phase 3C production perception on all confirmed human labels."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

import cv2

from bot.catalog import (
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_BLACK_MARKET,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
    build_default_resolver,
)
from bot.capture import FrameSnapshot
from bot.perception import build_default_perception
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import CONFIRMED, ManifestEntry, load_manifest


@dataclass(frozen=True)
class DetectorMetrics:
    positives_confirmed: int
    negatives_confirmed: int
    observations_emitted: int
    true_positives: int
    false_positives: int
    false_negatives: int
    raw_negative_anchor: float
    raw_positive_anchor: float
    raw_gap: float
    positive_confidence_min: float | None
    positive_confidence_max: float | None
    max_negative_confidence: float


@dataclass(frozen=True)
class ContextMetrics:
    count: int
    correct: int
    unknown: int
    ambiguous: int
    wrong: int


@dataclass(frozen=True)
class ResolverMetrics:
    entries: int
    correct_resolutions: int
    unknown: int
    ambiguous: int
    wrong: int
    overlays_correct: int
    black_market_correct: int
    purchase_overlay_correct: int
    black_market_plus_overlay_correct: int
    unknown_plus_purchase_overlay_correct: int
    by_ground_truth: dict[str, ContextMetrics]


@dataclass(frozen=True)
class FrameResult:
    path: str
    ground_truth_base: str
    ground_truth_overlays: tuple[str, ...]
    status: str
    resolved_base: str | None
    resolved_overlays: tuple[str, ...]


@dataclass(frozen=True)
class ProductionPerceptionReport:
    detectors: dict[str, DetectorMetrics]
    resolver: ResolverMetrics
    frames: tuple[FrameResult, ...]


def evaluate_production_perception(
    repository_root: str | Path,
    manifest_path: str | Path | Iterable[str | Path] = (
        "datasets/semantic_slice_manifest.json",
        "datasets/semantic_acquisition_manifest.json",
    ),
) -> ProductionPerceptionReport:
    """Run production detectors and resolver over every confirmed manifest frame."""

    repository_root = Path(repository_root).resolve()
    manifest_paths = (
        (manifest_path,)
        if isinstance(manifest_path, (str, Path))
        else tuple(manifest_path)
    )
    indexed: dict[str, ManifestEntry] = {}
    for item in manifest_paths:
        path = Path(item)
        if not path.is_absolute():
            path = repository_root / path
        for entry in load_manifest(path):
            if entry.review_status != CONFIRMED:
                continue
            existing = indexed.get(entry.path)
            if existing is not None and existing != entry:
                raise ValueError(f"conflicting human labels for {entry.path}")
            indexed[entry.path] = entry
    entries = tuple(indexed[path] for path in sorted(indexed))
    engine = build_default_perception(repository_root)
    resolver = build_default_resolver()

    detector_accumulators = {
        spec.name: {
            "positive_confidences": [],
            "negative_confidences": [],
            "positive_raw_scores": [],
            "negative_raw_scores": [],
            "emitted": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "positives": 0,
            "negatives": 0,
        }
        for spec in (detector.spec for detector in engine.detectors)
    }
    resolver_counts = {
        "correct": 0,
        "unknown": 0,
        "ambiguous": 0,
        "wrong": 0,
        "overlays_correct": 0,
        "black_market_correct": 0,
        "purchase_correct": 0,
        "base_overlay_correct": 0,
        "unknown_overlay_correct": 0,
    }
    context_accumulators = {
        name: {
            key: 0
            for key in ("count", "correct", "unknown", "ambiguous", "wrong")
        }
        for name in (
            SCREEN_LOBBY,
            SCREEN_CHARACTER_SELECT,
            SCREEN_BLACK_MARKET,
            SCREEN_BATTLE_MODE_SELECT,
            "other_or_unknown",
        )
    }
    frame_results: list[FrameResult] = []

    for sequence, entry in enumerate(entries, start=1):
        frame_path = repository_root / entry.path
        frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"Confirmed screenshot is unreadable: {frame_path}")
        batch = engine.analyze(
            FrameSnapshot(frame, timestamp=float(sequence), sequence=sequence)
        )
        state = resolver.resolve(batch)

        for detector in engine.detectors:
            name = detector.spec.name
            accumulator = detector_accumulators[name]
            evidence = batch.best(name)
            confidence = evidence.confidence if evidence is not None else 0.0
            raw_score = detector.measure(frame).raw_match_score
            positive = _is_positive(name, entry)
            confidence_key = (
                "positive_confidences" if positive else "negative_confidences"
            )
            accumulator[confidence_key].append(confidence)
            raw_key = "positive_raw_scores" if positive else "negative_raw_scores"
            accumulator[raw_key].append(raw_score)
            accumulator["positives" if positive else "negatives"] += 1
            if evidence is not None:
                accumulator["emitted"] += 1
            if positive and evidence is not None:
                accumulator["tp"] += 1
            elif positive:
                accumulator["fn"] += 1
            elif evidence is not None:
                accumulator["fp"] += 1

        expected_base = (
            entry.base_context
            if entry.base_context
            in {SCREEN_LOBBY, SCREEN_CHARACTER_SELECT, SCREEN_BLACK_MARKET}
            else None
        )
        expected_status = (
            ResolutionStatus.RESOLVED
            if expected_base is not None
            else ResolutionStatus.UNKNOWN
        )
        expected_overlays = tuple(
            overlay
            for overlay in entry.overlays
            if overlay == POPUP_PURCHASE_CONFIRMATION
        )
        resolution_correct = (
            state.status is expected_status
            and state.base_context == expected_base
            and state.overlays == expected_overlays
        )
        resolver_counts["correct"] += int(resolution_correct)
        resolver_counts["unknown"] += int(
            state.status is ResolutionStatus.UNKNOWN
        )
        resolver_counts["ambiguous"] += int(
            state.status is ResolutionStatus.AMBIGUOUS
        )
        resolver_counts["wrong"] += int(not resolution_correct)
        resolver_counts["overlays_correct"] += int(
            state.overlays == expected_overlays
        )
        if entry.base_context == SCREEN_BLACK_MARKET:
            resolver_counts["black_market_correct"] += int(
                state.base_context == SCREEN_BLACK_MARKET
            )
        if POPUP_PURCHASE_CONFIRMATION in entry.overlays:
            resolver_counts["purchase_correct"] += int(
                POPUP_PURCHASE_CONFIRMATION in state.overlays
            )
        if (
            entry.base_context == SCREEN_BLACK_MARKET
            and POPUP_PURCHASE_CONFIRMATION in entry.overlays
        ):
            resolver_counts["base_overlay_correct"] += int(
                state.base_context == SCREEN_BLACK_MARKET
                and state.overlays == (POPUP_PURCHASE_CONFIRMATION,)
            )
        if (
            entry.base_context != SCREEN_BLACK_MARKET
            and POPUP_PURCHASE_CONFIRMATION in entry.overlays
        ):
            resolver_counts["unknown_overlay_correct"] += int(
                state.status is ResolutionStatus.UNKNOWN
                and state.overlays == (POPUP_PURCHASE_CONFIRMATION,)
            )

        context_name = (
            entry.base_context
            if entry.base_context
            in {
                SCREEN_LOBBY,
                SCREEN_CHARACTER_SELECT,
                SCREEN_BLACK_MARKET,
                SCREEN_BATTLE_MODE_SELECT,
            }
            else "other_or_unknown"
        )
        context = context_accumulators[context_name]
        base_correct = (
            state.status is expected_status
            and state.base_context == expected_base
        )
        context["count"] += 1
        context["correct"] += int(base_correct)
        context["unknown"] += int(state.status is ResolutionStatus.UNKNOWN)
        context["ambiguous"] += int(state.status is ResolutionStatus.AMBIGUOUS)
        context["wrong"] += int(
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != expected_base
        )
        frame_results.append(
            FrameResult(
                path=entry.path,
                ground_truth_base=entry.base_context,
                ground_truth_overlays=entry.overlays,
                status=state.status.value,
                resolved_base=state.base_context,
                resolved_overlays=state.overlays,
            )
        )

    detector_metrics = {}
    for name, values in detector_accumulators.items():
        positive_confidences = values["positive_confidences"]
        negative_confidences = values["negative_confidences"]
        positive_raw_scores = values["positive_raw_scores"]
        negative_raw_scores = values["negative_raw_scores"]
        raw_negative_anchor = max(negative_raw_scores)
        raw_positive_anchor = min(positive_raw_scores)
        detector_metrics[name] = DetectorMetrics(
            positives_confirmed=values["positives"],
            negatives_confirmed=values["negatives"],
            observations_emitted=values["emitted"],
            true_positives=values["tp"],
            false_positives=values["fp"],
            false_negatives=values["fn"],
            raw_negative_anchor=raw_negative_anchor,
            raw_positive_anchor=raw_positive_anchor,
            raw_gap=raw_positive_anchor - raw_negative_anchor,
            positive_confidence_min=(
                min(positive_confidences) if positive_confidences else None
            ),
            positive_confidence_max=(
                max(positive_confidences) if positive_confidences else None
            ),
            max_negative_confidence=max(negative_confidences, default=0.0),
        )

    return ProductionPerceptionReport(
        detectors=detector_metrics,
        resolver=ResolverMetrics(
            entries=len(entries),
            correct_resolutions=resolver_counts["correct"],
            unknown=resolver_counts["unknown"],
            ambiguous=resolver_counts["ambiguous"],
            wrong=resolver_counts["wrong"],
            overlays_correct=resolver_counts["overlays_correct"],
            black_market_correct=resolver_counts["black_market_correct"],
            purchase_overlay_correct=resolver_counts["purchase_correct"],
            black_market_plus_overlay_correct=resolver_counts["base_overlay_correct"],
            unknown_plus_purchase_overlay_correct=resolver_counts[
                "unknown_overlay_correct"
            ],
            by_ground_truth={
                name: ContextMetrics(**values)
                for name, values in context_accumulators.items()
            },
        ),
        frames=tuple(frame_results),
    )


def _is_positive(name: str, entry: ManifestEntry) -> bool:
    if name == LANDMARK_LOBBY_TRADING_CENTER_LABEL:
        return entry.base_context == SCREEN_LOBBY
    if name == LANDMARK_CHARACTER_SELECT_HEADER:
        return entry.base_context == SCREEN_CHARACTER_SELECT
    if name == LANDMARK_BLACK_MARKET_TITLE:
        return entry.base_context == SCREEN_BLACK_MARKET
    if name == LANDMARK_PURCHASE_CONFIRMATION_PROMPT:
        return POPUP_PURCHASE_CONFIRMATION in entry.overlays
    raise ValueError(f"Unsupported production detector: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", action="append")
    parser.add_argument(
        "--output", default="artifacts/semantic_slice/phase3c-production.json"
    )
    arguments = parser.parse_args(argv)

    report = evaluate_production_perception(
        arguments.repo_root,
        arguments.manifest
        or (
            "datasets/semantic_slice_manifest.json",
            "datasets/semantic_acquisition_manifest.json",
        ),
    )
    output_path = Path(arguments.output)
    if not output_path.is_absolute():
        output_path = Path(arguments.repo_root).resolve() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
