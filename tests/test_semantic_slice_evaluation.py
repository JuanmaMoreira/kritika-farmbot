import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.semantic_slice_evaluation import (
    CONFIRMED,
    SKIPPED,
    UNSURE,
    DatasetInventory,
    LandmarkSpec,
    ManifestEntry,
    ScoreMeasurement,
    ScreenshotInfo,
    discover_screenshots,
    load_manifest,
    select_review_candidates,
    summarize_ground_truth,
    validate_relative_path,
    write_manifest,
)


def write_image(path, width, height, value=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((height, width, 3), value, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def measurement(path, landmark, score, threshold=0.85):
    return ScoreMeasurement(
        path=path,
        width=120,
        height=80,
        landmark=landmark,
        asset_path=f"assets/ui/{landmark}.png",
        region=(0.0, 0.0, 1.0, 1.0),
        historical_threshold=threshold,
        raw_match_score=score,
        used_region=True,
        compatible=True,
    )


def test_discovery_is_recursive_relative_and_reports_unreadable_images(tmp_path):
    write_image(tmp_path / "screencaps" / "batch" / "one.png", 120, 80)
    write_image(
        tmp_path / "screencaps" / "batch" / "done" / "two.PNG",
        200,
        100,
    )
    invalid = tmp_path / "screencaps" / "batch" / "broken.png"
    invalid.write_bytes(b"not an image")

    inventory = discover_screenshots(tmp_path)

    assert inventory.screenshots == (
        ScreenshotInfo("screencaps/batch/done/two.PNG", 200, 100),
        ScreenshotInfo("screencaps/batch/one.png", 120, 80),
    )
    assert inventory.invalid_paths == ("screencaps/batch/broken.png",)


def test_discovery_fails_clearly_when_local_dataset_is_absent(tmp_path):
    with pytest.raises(FileNotFoundError, match="dataset is unavailable"):
        discover_screenshots(tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/image.png",
        "C:/absolute/image.png",
        "../outside.png",
        "screencaps\\image.png",
        "",
    ],
)
def test_manifest_paths_must_be_repository_relative_posix_paths(path):
    with pytest.raises(ValueError, match="path"):
        validate_relative_path(path)


def test_manifest_round_trip_preserves_human_review_labels(tmp_path):
    manifest_path = tmp_path / "datasets" / "manifest.json"
    entries = (
        ManifestEntry(
            "screencaps/batch/lobby.png",
            "screen.lobby",
            (),
            CONFIRMED,
        ),
        ManifestEntry(
            "screencaps/batch/popup.png",
            "screen.black_market",
            ("popup.purchase_confirmation",),
            CONFIRMED,
        ),
        ManifestEntry("screencaps/batch/unsure.png", None, (), UNSURE),
        ManifestEntry("screencaps/batch/skipped.png", None, (), SKIPPED),
    )

    write_manifest(manifest_path, reversed(entries))

    assert load_manifest(manifest_path) == tuple(
        sorted(entries, key=lambda entry: entry.path)
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert all(not Path(item["path"]).is_absolute() for item in payload["entries"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "base_context": "screen.unsupported",
            "overlays": (),
            "review_status": CONFIRMED,
        },
        {
            "base_context": "screen.lobby",
            "overlays": (),
            "review_status": UNSURE,
        },
        {
            "base_context": None,
            "overlays": ("popup.unsupported",),
            "review_status": CONFIRMED,
        },
        {
            "base_context": None,
            "overlays": (),
            "review_status": "automatic",
        },
    ],
)
def test_manifest_rejects_invalid_labels_and_status_combinations(kwargs):
    with pytest.raises(ValueError):
        ManifestEntry("screencaps/batch/image.png", **kwargs)


def test_review_selection_is_deterministic_unique_and_bounded():
    rows = (
        measurement("screencaps/a.png", "landmark.alpha", 0.95),
        measurement("screencaps/a.png", "landmark.beta", 0.90),
        measurement("screencaps/b.png", "landmark.alpha", 0.84),
        measurement("screencaps/b.png", "landmark.beta", 0.20),
        measurement("screencaps/c.png", "landmark.alpha", 0.10),
        measurement("screencaps/c.png", "landmark.beta", 0.86),
        measurement("screencaps/d.png", "landmark.alpha", 0.05),
        measurement("screencaps/d.png", "landmark.beta", 0.04),
    )

    first = select_review_candidates(
        rows,
        top_per_landmark=1,
        near_threshold_per_landmark=1,
        cross_candidates=1,
        apparent_negatives=1,
        max_candidates=3,
    )
    second = select_review_candidates(
        reversed(rows),
        top_per_landmark=1,
        near_threshold_per_landmark=1,
        cross_candidates=1,
        apparent_negatives=1,
        max_candidates=3,
    )

    assert first == second
    assert len(first) == 3
    assert len({candidate.path for candidate in first}) == len(first)
    assert first[0].path == "screencaps/a.png"


def test_ground_truth_summary_uses_only_confirmed_human_labels():
    specs = (
        LandmarkSpec(
            "landmark.alpha",
            "assets/ui/alpha.png",
            (0.0, 0.0, 1.0, 1.0),
            0.85,
            positive_base_context="screen.lobby",
        ),
        LandmarkSpec(
            "landmark.popup",
            "assets/ui/popup.png",
            (0.0, 0.0, 1.0, 1.0),
            0.85,
            positive_overlay="popup.purchase_confirmation",
        ),
    )
    rows = (
        measurement("screencaps/lobby.png", "landmark.alpha", 0.95),
        measurement("screencaps/lobby.png", "landmark.popup", 0.10),
        measurement("screencaps/popup.png", "landmark.alpha", 0.20),
        measurement("screencaps/popup.png", "landmark.popup", 0.92),
        measurement("screencaps/unsure.png", "landmark.alpha", 1.0),
        measurement("screencaps/unsure.png", "landmark.popup", 1.0),
    )
    manifest = (
        ManifestEntry("screencaps/lobby.png", "screen.lobby", (), CONFIRMED),
        ManifestEntry(
            "screencaps/popup.png",
            "screen.black_market",
            ("popup.purchase_confirmation",),
            CONFIRMED,
        ),
        ManifestEntry("screencaps/unsure.png", None, (), UNSURE),
    )

    summary = summarize_ground_truth(rows, manifest, specs)

    alpha = summary["landmarks"]["landmark.alpha"]
    popup = summary["landmarks"]["landmark.popup"]
    assert summary["confirmed_entries"] == 2
    assert alpha["positives"] == {
        "count": 1,
        "min": 0.95,
        "max": 0.95,
        "median": 0.95,
    }
    assert alpha["highest_negative"] == 0.20
    assert popup["lowest_positive"] == 0.92
    assert popup["highest_negative"] == 0.10


def test_inventory_models_do_not_require_real_screencaps():
    inventory = DatasetInventory(
        screenshots=(ScreenshotInfo("screencaps/example.png", 120, 80),),
        invalid_paths=(),
    )

    assert inventory.screenshots[0].width == 120
