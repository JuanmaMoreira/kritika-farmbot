"""Select and evaluate interpretable Phase 3B semantic landmark candidates.

All labels come from versioned human manifests. Scores are raw OpenCV template
scores; this module does not create production calibration or detectors.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

import cv2

from bot.catalog import (
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_MONSTER_WAVE_ENTRY_TITLE,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
)
from bot.geometry import (
    RelativeRegion,
    normalize_relative_region,
)
from bot.observations import validate_semantic_name
from bot.screen import template_match_score
from tools.semantic_slice_evaluation import (
    CONFIRMED,
    ManifestEntry,
    load_manifest,
    validate_relative_path,
)

REPORT_VERSION = 1
VALIDATED = "VALIDATED"
PROMISING = "PROMISING"
NEEDS_REWORK = "NEEDS_REWORK"
UNVALIDATED = "UNVALIDATED"

MIN_VALIDATED_POSITIVES = 10
MIN_VALIDATED_NEGATIVES = 20
STRONG_SEPARATION_GAP = 0.10


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    asset_path: str
    region: RelativeRegion
    positive_base_context: str
    visual_description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_semantic_name(self.name))
        object.__setattr__(self, "asset_path", validate_relative_path(self.asset_path))
        object.__setattr__(
            self, "region", normalize_relative_region(self.region)
        )
        if self.positive_base_context not in {
            SCREEN_LOBBY,
            SCREEN_CHARACTER_SELECT,
            SCREEN_BATTLE_MODE_SELECT,
        }:
            raise ValueError("unsupported positive_base_context")
        if not isinstance(self.visual_description, str) or not self.visual_description:
            raise ValueError("visual_description must be non-empty")


@dataclass(frozen=True)
class ScoreDistribution:
    count: int
    minimum: float | None
    median: float | None
    maximum: float | None


@dataclass(frozen=True)
class CandidateMetrics:
    candidate: str
    asset_path: str
    positive_base_context: str
    visual_description: str
    positives: ScoreDistribution
    negatives: ScoreDistribution
    separation_gap: float | None
    diagnostic_threshold: float | None
    potential_false_positives: int | None
    potential_false_negatives: int | None
    lowest_positive_path: str | None
    highest_negative_path: str | None
    potential_false_positive_paths: tuple[str, ...]
    potential_false_negative_paths: tuple[str, ...]
    compatible_measurements: int
    incompatible_measurements: int
    status: str


CHARACTER_SELECT_SPEC = CandidateSpec(
    name=LANDMARK_CHARACTER_SELECT_HEADER,
    asset_path="assets/ui/select-character-id.png",
    region=(0.3971, 0.0417, 0.6036, 0.134),
    positive_base_context=SCREEN_CHARACTER_SELECT,
    visual_description="Character Select header",
)

BATTLE_MODE_SELECT_SPEC = CandidateSpec(
    name=LANDMARK_MONSTER_WAVE_ENTRY_TITLE,
    asset_path="assets/ui/survival-id.png",
    region=(0.1707, 0.2337, 0.2994, 0.2974),
    positive_base_context=SCREEN_BATTLE_MODE_SELECT,
    visual_description="Monster Wave entry title within Battle Mode Select",
)


def load_confirmed_entries(
    repository_root: str | Path,
    manifest_paths: Iterable[str | Path],
) -> tuple[ManifestEntry, ...]:
    """Merge confirmed human labels deterministically and reject conflicts."""

    repository_root = Path(repository_root).resolve()
    indexed: dict[str, ManifestEntry] = {}
    for manifest_path in manifest_paths:
        path = Path(manifest_path)
        if not path.is_absolute():
            path = repository_root / path
        for entry in load_manifest(path):
            if entry.review_status != CONFIRMED:
                continue
            existing = indexed.get(entry.path)
            if existing is not None and existing != entry:
                raise ValueError(f"conflicting human labels for {entry.path}")
            indexed[entry.path] = entry
    return tuple(indexed[path] for path in sorted(indexed))


def deterministic_reference(
    entries: Iterable[ManifestEntry], label: str
) -> ManifestEntry:
    matches = sorted(
        (entry for entry in entries if entry.base_context == label),
        key=lambda entry: entry.path,
    )
    if not matches:
        raise ValueError(f"no confirmed human reference for {label}")
    return matches[0]


def evaluate_candidate(
    repository_root: str | Path,
    entries: Iterable[ManifestEntry],
    spec: CandidateSpec,
) -> CandidateMetrics:
    repository_root = Path(repository_root).resolve()
    asset = repository_root / spec.asset_path
    if not asset.is_file():
        raise FileNotFoundError(f"candidate asset is unavailable: {asset}")

    positives: list[tuple[str, float]] = []
    negatives: list[tuple[str, float]] = []
    incompatible = 0
    for entry in entries:
        frame_path = repository_root / entry.path
        frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"confirmed screenshot is unreadable: {frame_path}")
        score = template_match_score(frame, asset, region=spec.region)
        if score is None:
            incompatible += 1
            continue
        target = positives if entry.base_context == spec.positive_base_context else negatives
        target.append((entry.path, float(score)))

    positive_scores = [score for _, score in positives]
    negative_scores = [score for _, score in negatives]

    gap = (
        min(positive_scores) - max(negative_scores)
        if positives and negatives
        else None
    )
    threshold, false_positives, false_negatives = diagnostic_operating_point(
        positive_scores, negative_scores
    )
    lowest_positive = min(positives, key=lambda item: (item[1], item[0]), default=None)
    highest_negative = max(negatives, key=lambda item: (item[1], item[0]), default=None)
    false_positive_paths = tuple(
        sorted(
            path
            for path, score in negatives
            if threshold is not None and score >= threshold
        )
    )
    false_negative_paths = tuple(
        sorted(
            path
            for path, score in positives
            if threshold is not None and score < threshold
        )
    )
    return CandidateMetrics(
        candidate=spec.name,
        asset_path=spec.asset_path,
        positive_base_context=spec.positive_base_context,
        visual_description=spec.visual_description,
        positives=distribution(positive_scores),
        negatives=distribution(negative_scores),
        separation_gap=gap,
        diagnostic_threshold=threshold,
        potential_false_positives=false_positives,
        potential_false_negatives=false_negatives,
        lowest_positive_path=(lowest_positive[0] if lowest_positive else None),
        highest_negative_path=(highest_negative[0] if highest_negative else None),
        potential_false_positive_paths=false_positive_paths,
        potential_false_negative_paths=false_negative_paths,
        compatible_measurements=len(positives) + len(negatives),
        incompatible_measurements=incompatible,
        status=classify_candidate(len(positives), len(negatives), gap),
    )


def distribution(values: Sequence[float]) -> ScoreDistribution:
    if not values:
        return ScoreDistribution(0, None, None, None)
    return ScoreDistribution(len(values), min(values), median(values), max(values))


def diagnostic_operating_point(
    positives: Sequence[float], negatives: Sequence[float]
) -> tuple[float | None, int | None, int | None]:
    """Return a transparent minimum-error threshold without hiding overlap."""

    if not positives or not negatives:
        return None, None, None
    values = sorted(set(float(value) for value in (*positives, *negatives)))
    thresholds = [math.nextafter(values[-1], math.inf), *values]
    thresholds.extend(
        (left + right) / 2.0 for left, right in zip(values, values[1:])
    )
    ranked = []
    for threshold in thresholds:
        false_positives = sum(score >= threshold for score in negatives)
        false_negatives = sum(score < threshold for score in positives)
        ranked.append(
            (
                false_positives + false_negatives,
                max(false_positives, false_negatives),
                false_positives,
                -threshold,
                threshold,
                false_positives,
                false_negatives,
            )
        )
    _, _, _, _, threshold, false_positives, false_negatives = min(ranked)
    return threshold, false_positives, false_negatives


def classify_candidate(
    positive_count: int, negative_count: int, separation_gap: float | None
) -> str:
    if positive_count == 0 or negative_count == 0 or separation_gap is None:
        return UNVALIDATED
    if separation_gap <= 0.0:
        return NEEDS_REWORK
    if (
        positive_count >= MIN_VALIDATED_POSITIVES
        and negative_count >= MIN_VALIDATED_NEGATIVES
        and separation_gap >= STRONG_SEPARATION_GAP
    ):
        return VALIDATED
    return PROMISING


def expanded_region(
    crop_region: RelativeRegion, padding: float = 0.01
) -> RelativeRegion:
    x1, y1, x2, y2 = normalize_relative_region(crop_region)
    return normalize_relative_region(
        (
            max(0.0, x1 - padding),
            max(0.0, y1 - padding),
            min(1.0, x2 + padding),
            min(1.0, y2 + padding),
        )
    )


def save_candidate_from_roi(
    repository_root: str | Path,
    reference_path: str,
    roi: tuple[int, int, int, int],
    name: str,
    visual_description: str,
    asset_path: str | Path,
    spec_path: str | Path,
    positive_base_context: str = SCREEN_LOBBY,
) -> CandidateSpec:
    repository_root = Path(repository_root).resolve()
    reference_path = validate_relative_path(reference_path)
    frame = cv2.imread(str(repository_root / reference_path), cv2.IMREAD_COLOR)
    if frame is None:
        raise FileNotFoundError(f"reference screenshot is unreadable: {reference_path}")
    x, y, width, height = roi
    if min(x, y) < 0 or width <= 0 or height <= 0:
        raise ValueError("ROI must have positive size and non-negative coordinates")
    frame_height, frame_width = frame.shape[:2]
    if x + width > frame_width or y + height > frame_height:
        raise ValueError("ROI must remain inside the reference screenshot")

    asset_path = Path(asset_path)
    if not asset_path.is_absolute():
        asset_path = repository_root / asset_path
    spec_path = Path(spec_path)
    if not spec_path.is_absolute():
        spec_path = repository_root / spec_path
    try:
        relative_asset = validate_relative_path(
            asset_path.resolve().relative_to(repository_root).as_posix()
        )
        spec_path.resolve().relative_to(repository_root)
    except ValueError as error:
        raise ValueError("candidate artifacts must remain inside the repository") from error

    crop_region = (
        x / frame_width,
        y / frame_height,
        (x + width) / frame_width,
        (y + height) / frame_height,
    )
    spec = CandidateSpec(
        name=name,
        asset_path=relative_asset,
        region=expanded_region(crop_region),
        positive_base_context=positive_base_context,
        visual_description=visual_description,
    )
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    crop = frame[y : y + height, x : x + width]
    if not cv2.imwrite(str(asset_path), crop):
        raise OSError(f"OpenCV could not save candidate crop: {asset_path}")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        json.dumps(
            {
                "version": REPORT_VERSION,
                "reference_path": reference_path,
                "candidate": asdict(spec),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return spec


def load_candidate_spec(path: str | Path) -> CandidateSpec:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != REPORT_VERSION:
        raise ValueError("unsupported candidate spec version")
    item = payload["candidate"]
    return CandidateSpec(
        name=item["name"],
        asset_path=item["asset_path"],
        region=tuple(item["region"]),
        positive_base_context=item["positive_base_context"],
        visual_description=item["visual_description"],
    )


def _manifest_defaults() -> list[str]:
    return [
        "datasets/semantic_slice_manifest.json",
        "datasets/semantic_acquisition_manifest.json",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    select_parser = subparsers.add_parser("select-lobby")
    select_parser.add_argument("--manifest", action="append")
    select_parser.add_argument("--reference")
    select_parser.add_argument("--name", required=True)
    select_parser.add_argument("--description", required=True)
    select_parser.add_argument("--asset", required=True)
    select_parser.add_argument("--spec", required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--manifest", action="append")
    evaluate_parser.add_argument("--candidate-spec", action="append", default=[])
    evaluate_parser.add_argument(
        "--output", default="artifacts/semantic_candidates/evaluation.json"
    )
    arguments = parser.parse_args(argv)
    repository_root = Path(arguments.repo_root).resolve()
    manifests = arguments.manifest or _manifest_defaults()
    entries = load_confirmed_entries(repository_root, manifests)

    if arguments.command == "select-lobby":
        reference = (
            validate_relative_path(arguments.reference)
            if arguments.reference
            else deterministic_reference(entries, SCREEN_LOBBY).path
        )
        frame = cv2.imread(str(repository_root / reference), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"reference screenshot is unreadable: {reference}")
        roi = tuple(
            int(value)
            for value in cv2.selectROI(
                "Select interpretable Lobby landmark", frame, showCrosshair=True
            )
        )
        cv2.destroyAllWindows()
        spec = save_candidate_from_roi(
            repository_root,
            reference,
            roi,
            arguments.name,
            arguments.description,
            arguments.asset,
            arguments.spec,
        )
        print(json.dumps(asdict(spec), indent=2, ensure_ascii=False))
        return 0

    specs = [CHARACTER_SELECT_SPEC, BATTLE_MODE_SELECT_SPEC]
    specs.extend(load_candidate_spec(path) for path in arguments.candidate_spec)
    metrics = [evaluate_candidate(repository_root, entries, spec) for spec in specs]
    payload = {
        "version": REPORT_VERSION,
        "confirmed_entries": len(entries),
        "classification_policy": {
            "validated_min_positives": MIN_VALIDATED_POSITIVES,
            "validated_min_negatives": MIN_VALIDATED_NEGATIVES,
            "validated_min_gap": STRONG_SEPARATION_GAP,
            "non_positive_gap": NEEDS_REWORK,
        },
        "candidates": [asdict(item) for item in metrics],
    }
    output = Path(arguments.output)
    if not output.is_absolute():
        output = repository_root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
