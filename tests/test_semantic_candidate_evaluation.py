import json

import cv2
import numpy as np
import pytest

from bot.catalog import SCREEN_CHARACTER_SELECT, SCREEN_LOBBY
from tools.semantic_candidate_evaluation import (
    NEEDS_REWORK,
    PROMISING,
    UNVALIDATED,
    VALIDATED,
    CandidateSpec,
    classify_candidate,
    deterministic_reference,
    diagnostic_operating_point,
    evaluate_candidate,
    load_candidate_spec,
    load_confirmed_entries,
    save_candidate_from_roi,
)
from tools.semantic_slice_evaluation import CONFIRMED, ManifestEntry, write_manifest


def write_image(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)


def test_confirmed_manifest_merge_is_deterministic_and_rejects_conflicts(tmp_path):
    first = tmp_path / "datasets" / "first.json"
    second = tmp_path / "datasets" / "second.json"
    lobby = ManifestEntry("screencaps/lobby.png", SCREEN_LOBBY, (), CONFIRMED)
    character = ManifestEntry(
        "screencaps/character.png", SCREEN_CHARACTER_SELECT, (), CONFIRMED
    )
    write_manifest(first, (lobby,))
    write_manifest(second, (character,))

    assert load_confirmed_entries(tmp_path, (second, first)) == (character, lobby)

    write_manifest(
        second,
        (ManifestEntry("screencaps/lobby.png", SCREEN_CHARACTER_SELECT, (), CONFIRMED),),
    )
    with pytest.raises(ValueError, match="conflicting"):
        load_confirmed_entries(tmp_path, (first, second))


def test_reference_selection_is_deterministic_and_human_label_only():
    entries = (
        ManifestEntry("screencaps/z.png", SCREEN_LOBBY, (), CONFIRMED),
        ManifestEntry("screencaps/a.png", SCREEN_LOBBY, (), CONFIRMED),
        ManifestEntry("screencaps/c.png", SCREEN_CHARACTER_SELECT, (), CONFIRMED),
    )

    assert deterministic_reference(reversed(entries), SCREEN_LOBBY).path == "screencaps/a.png"


def test_diagnostic_metrics_expose_perfect_separation_and_overlap():
    threshold, false_positives, false_negatives = diagnostic_operating_point(
        (0.9, 0.95), (0.1, 0.2)
    )
    assert 0.2 < threshold <= 0.9
    assert (false_positives, false_negatives) == (0, 0)

    _, false_positives, false_negatives = diagnostic_operating_point(
        (0.4, 0.9), (0.2, 0.6)
    )
    assert false_positives + false_negatives == 1


@pytest.mark.parametrize(
    ("positive_count", "negative_count", "gap", "status"),
    [
        (0, 30, None, UNVALIDATED),
        (10, 30, -0.01, NEEDS_REWORK),
        (2, 30, 0.4, PROMISING),
        (10, 20, 0.1, VALIDATED),
    ],
)
def test_candidate_classification_is_explicit(
    positive_count, negative_count, gap, status
):
    assert classify_candidate(positive_count, negative_count, gap) == status


def test_synthetic_candidate_evaluation_uses_raw_scores_and_human_labels(tmp_path):
    rng = np.random.default_rng(5)
    template = rng.integers(0, 256, (10, 12, 3), dtype=np.uint8)
    lobby = np.zeros((50, 80, 3), dtype=np.uint8)
    lobby[10:20, 20:32] = template
    negative = rng.integers(0, 256, (50, 80, 3), dtype=np.uint8)
    write_image(tmp_path / "assets" / "candidate.png", template)
    write_image(tmp_path / "screencaps" / "lobby.png", lobby)
    write_image(tmp_path / "screencaps" / "negative.png", negative)
    entries = (
        ManifestEntry("screencaps/lobby.png", SCREEN_LOBBY, (), CONFIRMED),
        ManifestEntry(
            "screencaps/negative.png", SCREEN_CHARACTER_SELECT, (), CONFIRMED
        ),
    )
    spec = CandidateSpec(
        "landmark.synthetic_lobby_candidate",
        "assets/candidate.png",
        (0.20, 0.10, 0.50, 0.50),
        SCREEN_LOBBY,
        "synthetic stable mark",
    )

    result = evaluate_candidate(tmp_path, entries, spec)

    assert result.positives.count == 1
    assert result.positives.minimum == pytest.approx(1.0, abs=1e-3)
    assert result.negatives.count == 1
    assert result.separation_gap > 0.5
    assert result.status == PROMISING
    assert result.potential_false_positives == 0
    assert result.potential_false_negatives == 0
    assert result.lowest_positive_path == "screencaps/lobby.png"
    assert result.highest_negative_path == "screencaps/negative.png"


def test_candidate_roi_saves_lossless_crop_and_reloadable_spec(tmp_path):
    frame = np.zeros((40, 100, 3), dtype=np.uint8)
    frame[8:18, 20:40] = (12, 34, 56)
    write_image(tmp_path / "screencaps" / "lobby.png", frame)

    spec = save_candidate_from_roi(
        tmp_path,
        "screencaps/lobby.png",
        (20, 8, 20, 10),
        "landmark.lobby_candidate",
        "interpretable lobby emblem",
        "artifacts/candidates/lobby.png",
        "artifacts/candidates/lobby.json",
    )

    crop = cv2.imread(
        str(tmp_path / "artifacts" / "candidates" / "lobby.png"),
        cv2.IMREAD_COLOR,
    )
    assert crop.shape == (10, 20, 3)
    assert np.all(crop == (12, 34, 56))
    assert load_candidate_spec(
        tmp_path / "artifacts" / "candidates" / "lobby.json"
    ) == spec
    payload = json.loads(
        (tmp_path / "artifacts" / "candidates" / "lobby.json").read_text()
    )
    assert payload["reference_path"] == "screencaps/lobby.png"


def test_candidate_roi_preserves_explicit_non_lobby_target(tmp_path):
    frame = np.zeros((40, 100, 3), dtype=np.uint8)
    write_image(tmp_path / "screencaps" / "character.png", frame)

    spec = save_candidate_from_roi(
        tmp_path,
        "screencaps/character.png",
        (10, 5, 20, 10),
        "landmark.character_candidate",
        "current character header",
        "artifacts/character.png",
        "artifacts/character.json",
        positive_base_context=SCREEN_CHARACTER_SELECT,
    )

    assert spec.positive_base_context == SCREEN_CHARACTER_SELECT
    assert load_candidate_spec(
        tmp_path / "artifacts" / "character.json"
    ).positive_base_context == SCREEN_CHARACTER_SELECT
