"""Reproducible offline evaluation for the Phase 2D semantic slice."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Iterable

import cv2

from bot.catalog import (
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_MONSTER_WAVE_ENTRY_TITLE,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_BLACK_MARKET,
    SCREEN_CHARACTER_SELECT,
    SCREEN_LOBBY,
)
from bot.geometry import RelativeRegion, frame_dimensions
from bot.screen import template_match_score

LANDMARK_GOLD_CURRENCY_ICON = "landmark.gold_currency_icon"

MANIFEST_VERSION = 1
EVALUATION_VERSION = 1

CONFIRMED = "confirmed"
UNSURE = "unsure"
SKIPPED = "skipped"
REVIEW_STATUSES = frozenset((CONFIRMED, UNSURE, SKIPPED))
UNKNOWN_BASE_CONTEXT = "unknown"
BASE_CONTEXT_LABELS = frozenset(
    (
        SCREEN_LOBBY,
        SCREEN_CHARACTER_SELECT,
        SCREEN_BATTLE_MODE_SELECT,
        SCREEN_BLACK_MARKET,
        UNKNOWN_BASE_CONTEXT,
    )
)
OVERLAY_LABELS = frozenset((POPUP_PURCHASE_CONFIRMATION,))


@dataclass(frozen=True)
class LandmarkSpec:
    name: str
    asset_path: str
    region: RelativeRegion
    historical_threshold: float
    positive_base_context: str | None = None
    positive_overlay: str | None = None


LANDMARK_SPECS = (
    LandmarkSpec(
        name=LANDMARK_GOLD_CURRENCY_ICON,
        asset_path="assets/ui/lobby-id.png",
        region=(0.2039, 0.0302, 0.2434, 0.0899),
        historical_threshold=0.85,
        positive_base_context=SCREEN_LOBBY,
    ),
    LandmarkSpec(
        name=LANDMARK_CHARACTER_SELECT_HEADER,
        asset_path="assets/ui/select-character-id.png",
        region=(0.3971, 0.0417, 0.6036, 0.134),
        historical_threshold=0.85,
        positive_base_context=SCREEN_CHARACTER_SELECT,
    ),
    LandmarkSpec(
        name=LANDMARK_MONSTER_WAVE_ENTRY_TITLE,
        asset_path="assets/ui/survival-id.png",
        region=(0.1707, 0.2337, 0.2994, 0.2974),
        historical_threshold=0.85,
        positive_base_context=SCREEN_BATTLE_MODE_SELECT,
    ),
    LandmarkSpec(
        name=LANDMARK_BLACK_MARKET_TITLE,
        asset_path="assets/ui/black-market-id.png",
        region=(0.4395, 0.0997, 0.5579, 0.1495),
        historical_threshold=0.85,
        positive_base_context=SCREEN_BLACK_MARKET,
    ),
    LandmarkSpec(
        name=LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
        asset_path="assets/ui/black-market-purchase-confirmation-id.png",
        region=(0.4624, 0.4828, 0.5376, 0.5294),
        historical_threshold=0.85,
        positive_overlay=POPUP_PURCHASE_CONFIRMATION,
    ),
)


@dataclass(frozen=True)
class ScreenshotInfo:
    path: str
    width: int
    height: int


@dataclass(frozen=True)
class DatasetInventory:
    screenshots: tuple[ScreenshotInfo, ...]
    invalid_paths: tuple[str, ...]


@dataclass(frozen=True)
class ScoreMeasurement:
    path: str
    width: int
    height: int
    landmark: str
    asset_path: str
    region: RelativeRegion
    historical_threshold: float
    raw_match_score: float | None
    used_region: bool
    compatible: bool
    error: str | None = None


@dataclass(frozen=True)
class ReviewCandidate:
    path: str
    reasons: tuple[str, ...]
    scores: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    base_context: str | None
    overlays: tuple[str, ...]
    review_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", validate_relative_path(self.path))
        if self.review_status not in REVIEW_STATUSES:
            raise ValueError(f"invalid review_status: {self.review_status!r}")
        overlays = tuple(self.overlays)
        if len(set(overlays)) != len(overlays):
            raise ValueError("overlays must not contain duplicates")
        if any(overlay not in OVERLAY_LABELS for overlay in overlays):
            raise ValueError("manifest contains an unsupported overlay label")
        object.__setattr__(self, "overlays", tuple(sorted(overlays)))

        if self.review_status == CONFIRMED:
            if self.base_context not in BASE_CONTEXT_LABELS:
                raise ValueError("confirmed entries require a valid base_context")
        elif self.base_context is not None or overlays:
            raise ValueError(
                "unsure/skipped entries cannot contain inferred labels"
            )


def validate_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("path must be a non-empty POSIX repository-relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.parts[0].endswith(":")
        or ".." in path.parts
        or "." in path.parts
    ):
        raise ValueError("path must remain within the repository")
    return path.as_posix()


def discover_screenshots(
    repository_root: str | Path,
    screenshots_path: str | Path = "screencaps",
) -> DatasetInventory:
    repository_root = Path(repository_root).resolve()
    screenshots_root = repository_root / screenshots_path
    if not screenshots_root.is_dir():
        raise FileNotFoundError(
            f"Screenshot dataset is unavailable: {screenshots_root}"
        )

    screenshots: list[ScreenshotInfo] = []
    invalid_paths: list[str] = []
    image_paths = sorted(
        (
            path
            for path in screenshots_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ),
        key=lambda path: path.as_posix(),
    )
    for path in image_paths:
        relative_path = _repository_relative(path, repository_root)
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            invalid_paths.append(relative_path)
            continue
        width, height = frame_dimensions(frame)
        screenshots.append(ScreenshotInfo(relative_path, width, height))
    return DatasetInventory(tuple(screenshots), tuple(invalid_paths))


def evaluate_inventory(
    repository_root: str | Path,
    inventory: DatasetInventory,
    specs: Iterable[LandmarkSpec] = LANDMARK_SPECS,
) -> tuple[ScoreMeasurement, ...]:
    repository_root = Path(repository_root).resolve()
    specs = tuple(specs)
    for spec in specs:
        asset = repository_root / spec.asset_path
        if not asset.is_file():
            raise FileNotFoundError(f"Landmark asset is unavailable: {asset}")

    measurements: list[ScoreMeasurement] = []
    for screenshot in inventory.screenshots:
        frame = cv2.imread(
            str(repository_root / screenshot.path), cv2.IMREAD_COLOR
        )
        if frame is None:
            for spec in specs:
                measurements.append(
                    _failed_measurement(screenshot, spec, "screenshot became unreadable")
                )
            continue
        for spec in specs:
            try:
                score = template_match_score(
                    frame,
                    repository_root / spec.asset_path,
                    region=spec.region,
                )
                measurements.append(
                    ScoreMeasurement(
                        path=screenshot.path,
                        width=screenshot.width,
                        height=screenshot.height,
                        landmark=spec.name,
                        asset_path=spec.asset_path,
                        region=spec.region,
                        historical_threshold=spec.historical_threshold,
                        raw_match_score=score,
                        used_region=True,
                        compatible=score is not None,
                        error=None if score is not None else "template does not fit region",
                    )
                )
            except (FileNotFoundError, ValueError, cv2.error) as error:
                measurements.append(_failed_measurement(screenshot, spec, str(error)))
    return tuple(measurements)


def select_review_candidates(
    measurements: Iterable[ScoreMeasurement],
    *,
    top_per_landmark: int = 4,
    near_threshold_per_landmark: int = 2,
    cross_candidates: int = 5,
    apparent_negatives: int = 5,
    max_candidates: int = 40,
) -> tuple[ReviewCandidate, ...]:
    rows = tuple(
        row
        for row in measurements
        if row.compatible and row.raw_match_score is not None
    )
    by_landmark: dict[str, list[ScoreMeasurement]] = defaultdict(list)
    by_path: dict[str, list[ScoreMeasurement]] = defaultdict(list)
    for row in rows:
        by_landmark[row.landmark].append(row)
        by_path[row.path].append(row)

    selected: dict[str, list[str]] = {}

    def add(path: str, reason: str) -> None:
        if path not in selected and len(selected) >= max_candidates:
            return
        reasons = selected.setdefault(path, [])
        if reason not in reasons:
            reasons.append(reason)

    for landmark in sorted(by_landmark):
        landmark_rows = by_landmark[landmark]
        top_rows = sorted(
            landmark_rows,
            key=lambda row: (-float(row.raw_match_score), row.path),
        )[:top_per_landmark]
        for row in top_rows:
            add(row.path, f"top:{landmark}")

        threshold = landmark_rows[0].historical_threshold
        near_rows = sorted(
            landmark_rows,
            key=lambda row: (
                abs(float(row.raw_match_score) - threshold),
                row.path,
            ),
        )[:near_threshold_per_landmark]
        for row in near_rows:
            add(row.path, f"near_historical_threshold:{landmark}")

    cross_ranked = sorted(
        (
            (
                sorted(
                    (float(row.raw_match_score) for row in path_rows),
                    reverse=True,
                )[1],
                path,
            )
            for path, path_rows in by_path.items()
            if len(path_rows) >= 2
        ),
        key=lambda item: (-item[0], item[1]),
    )
    for _, path in cross_ranked[:cross_candidates]:
        add(path, "cross_landmark_high_score")

    negative_ranked = sorted(
        (
            (
                max(float(row.raw_match_score) for row in path_rows),
                path,
            )
            for path, path_rows in by_path.items()
        ),
        key=lambda item: (item[0], item[1]),
    )
    for _, path in negative_ranked[:apparent_negatives]:
        add(path, "apparent_negative")

    candidates: list[ReviewCandidate] = []
    for path, reasons in selected.items():
        scores = tuple(
            sorted(
                (
                    (row.landmark, float(row.raw_match_score))
                    for row in by_path[path]
                ),
                key=lambda item: item[0],
            )
        )
        candidates.append(ReviewCandidate(path, tuple(reasons), scores))
    return tuple(candidates)


def load_manifest(path: str | Path) -> tuple[ManifestEntry, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError("unsupported semantic slice manifest version")
    entries = tuple(
        ManifestEntry(
            path=item["path"],
            base_context=item.get("base_context"),
            overlays=tuple(item.get("overlays", ())),
            review_status=item["review_status"],
        )
        for item in payload.get("entries", ())
    )
    paths = tuple(entry.path for entry in entries)
    if len(paths) != len(set(paths)):
        raise ValueError("manifest paths must be unique")
    return entries


def write_manifest(path: str | Path, entries: Iterable[ManifestEntry]) -> None:
    entries = tuple(sorted(entries, key=lambda entry: entry.path))
    paths = tuple(entry.path for entry in entries)
    if len(paths) != len(set(paths)):
        raise ValueError("manifest paths must be unique")
    payload = {
        "version": MANIFEST_VERSION,
        "entries": [asdict(entry) for entry in entries],
    }
    _write_json(Path(path), payload)


def summarize_ground_truth(
    measurements: Iterable[ScoreMeasurement],
    manifest: Iterable[ManifestEntry],
    specs: Iterable[LandmarkSpec] = LANDMARK_SPECS,
) -> dict[str, object]:
    score_index = {
        (row.path, row.landmark): row.raw_match_score
        for row in measurements
        if row.compatible and row.raw_match_score is not None
    }
    confirmed = tuple(
        entry for entry in manifest if entry.review_status == CONFIRMED
    )
    landmark_results: dict[str, object] = {}
    cross_confusion: list[dict[str, object]] = []

    for spec in specs:
        positives: list[float] = []
        negatives: list[float] = []
        for entry in confirmed:
            score = score_index.get((entry.path, spec.name))
            if score is None:
                continue
            is_positive = (
                spec.positive_base_context is not None
                and entry.base_context == spec.positive_base_context
            ) or (
                spec.positive_overlay is not None
                and spec.positive_overlay in entry.overlays
            )
            target = positives if is_positive else negatives
            target.append(float(score))
            if not is_positive:
                cross_confusion.append(
                    {
                        "path": entry.path,
                        "base_context": entry.base_context,
                        "landmark": spec.name,
                        "raw_match_score": float(score),
                    }
                )
        landmark_results[spec.name] = {
            "positives": _distribution(positives),
            "negatives": _distribution(negatives),
            "lowest_positive": min(positives) if positives else None,
            "highest_negative": max(negatives) if negatives else None,
        }

    review_counts = {
        status: sum(1 for entry in manifest if entry.review_status == status)
        for status in sorted(REVIEW_STATUSES)
    }
    base_counts = {
        label: sum(
            1
            for entry in confirmed
            if entry.base_context == label
        )
        for label in sorted(BASE_CONTEXT_LABELS)
    }
    overlay_counts = {
        label: sum(1 for entry in confirmed if label in entry.overlays)
        for label in sorted(OVERLAY_LABELS)
    }
    cross_confusion.sort(
        key=lambda item: (-float(item["raw_match_score"]), str(item["path"]))
    )
    return {
        "confirmed_entries": len(confirmed),
        "review_counts": review_counts,
        "base_context_counts": base_counts,
        "overlay_counts": overlay_counts,
        "landmarks": landmark_results,
        "highest_cross_confusion": cross_confusion[:20],
    }


def run_evaluation(
    repository_root: str | Path,
    screenshots_path: str | Path,
    output_directory: str | Path,
) -> tuple[DatasetInventory, tuple[ScoreMeasurement, ...], tuple[ReviewCandidate, ...]]:
    repository_root = Path(repository_root).resolve()
    output_directory = Path(output_directory)
    if not output_directory.is_absolute():
        output_directory = repository_root / output_directory

    inventory = discover_screenshots(repository_root, screenshots_path)
    measurements = evaluate_inventory(repository_root, inventory)
    candidates = select_review_candidates(measurements)
    _write_json(
        output_directory / "inventory.json",
        {"version": EVALUATION_VERSION, **asdict(inventory)},
    )
    _write_json(
        output_directory / "scores.json",
        {
            "version": EVALUATION_VERSION,
            "measurements": [asdict(row) for row in measurements],
        },
    )
    _write_json(
        output_directory / "review_selection.json",
        {
            "version": EVALUATION_VERSION,
            "candidates": [asdict(candidate) for candidate in candidates],
        },
    )
    return inventory, measurements, candidates


def load_measurements(path: str | Path) -> tuple[ScoreMeasurement, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("version") != EVALUATION_VERSION:
        raise ValueError("unsupported semantic slice evaluation version")
    return tuple(
        ScoreMeasurement(
            path=item["path"],
            width=item["width"],
            height=item["height"],
            landmark=item["landmark"],
            asset_path=item["asset_path"],
            region=tuple(item["region"]),
            historical_threshold=item["historical_threshold"],
            raw_match_score=item.get("raw_match_score"),
            used_region=item["used_region"],
            compatible=item["compatible"],
            error=item.get("error"),
        )
        for item in payload.get("measurements", ())
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--repo-root", default=".")
    evaluate_parser.add_argument("--screenshots", default="screencaps")
    evaluate_parser.add_argument(
        "--output", default="artifacts/semantic_slice"
    )

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument(
        "--scores", default="artifacts/semantic_slice/scores.json"
    )
    summary_parser.add_argument(
        "--manifest", default="datasets/semantic_slice_manifest.json"
    )
    summary_parser.add_argument(
        "--output", default="artifacts/semantic_slice/summary.json"
    )

    arguments = parser.parse_args(argv)
    if arguments.command == "evaluate":
        inventory, measurements, candidates = run_evaluation(
            arguments.repo_root, arguments.screenshots, arguments.output
        )
        compatible = sum(1 for row in measurements if row.compatible)
        print(f"screenshots={len(inventory.screenshots)}")
        print(f"invalid={len(inventory.invalid_paths)}")
        print(f"compatible_measurements={compatible}/{len(measurements)}")
        print(f"review_candidates={len(candidates)}")
        return 0

    measurements = load_measurements(arguments.scores)
    manifest = load_manifest(arguments.manifest)
    summary = summarize_ground_truth(measurements, manifest)
    _write_json(Path(arguments.output), summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _repository_relative(path: Path, repository_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(repository_root)
    except ValueError as error:
        raise ValueError(f"path is outside repository: {path}") from error
    return validate_relative_path(relative.as_posix())


def _failed_measurement(
    screenshot: ScreenshotInfo, spec: LandmarkSpec, error: str
) -> ScoreMeasurement:
    return ScoreMeasurement(
        path=screenshot.path,
        width=screenshot.width,
        height=screenshot.height,
        landmark=spec.name,
        asset_path=spec.asset_path,
        region=spec.region,
        historical_threshold=spec.historical_threshold,
        raw_match_score=None,
        used_region=True,
        compatible=False,
        error=error,
    )


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "median": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "median": median(values),
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
