import json
from pathlib import Path

import cv2

from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    CANDIDATE_PET_LOW_TIER,
    LANDMARK_PET_MASS_EVOLVE_CONFIRMATION,
    MODE_PET_MASS_EVOLVE_SELECTION,
    POPUP_PET_EPIC_RUNES_FULL,
    POPUP_PET_MASS_EVOLVE_CONFIRMATION,
    SCREEN_PET_COMBINE_RESULT,
    build_default_resolver,
)
from bot.perception import (
    PET_LOW_TIER_NORMAL,
    PET_LOW_TIER_RARE,
    PET_LOW_TIER_SLOT_REGIONS,
    PetLowTierCandidateDetector,
    PetMassEvolveConfirmationDetector,
    build_default_perception,
)
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/pet_summon_space_relief_semantic_manifest.json"
CORPUS = "screencaps/semantic/pet_summon_space_relief"


def _frame(relative_path: str):
    frame = cv2.imread(str(ROOT / relative_path), cv2.IMREAD_COLOR)
    assert frame is not None, relative_path
    return frame


def _analyze(relative_path: str):
    batch = build_default_perception(ROOT).analyze(
        FrameSnapshot(_frame(relative_path), 1.0, 1)
    )
    return batch, build_default_resolver().resolve(batch)


def test_curated_relief_frames_resolve_without_route_specific_duplicates():
    entries = load_manifest(MANIFEST)

    assert len(entries) == 14
    for entry in entries:
        batch, state = _analyze(entry.path)
        assert state.status is ResolutionStatus.RESOLVED, entry.path
        assert state.base_context == entry.base_context, entry.path
        assert state.overlays == entry.overlays, entry.path
        assert all(batch.best(name) is not None for name in entry.observations)


def test_low_tier_candidates_use_tier_color_and_slot_region_not_identity():
    detector = PetLowTierCandidateDetector(asset_root=ROOT)
    normal = detector.detect(_frame(f"{CORPUS}/normal-candidates/01.png"))
    mixed = detector.detect(_frame(f"{CORPUS}/rare-candidates/01.png"))

    assert len(normal) == 16
    assert {item.value for item in normal} == {PET_LOW_TIER_NORMAL}
    assert [item.region for item in normal] == list(PET_LOW_TIER_SLOT_REGIONS)
    assert len(mixed) == 16
    assert [item.value for item in mixed].count(PET_LOW_TIER_NORMAL) == 2
    assert [item.value for item in mixed].count(PET_LOW_TIER_RARE) == 14
    assert all(item.name == CANDIDATE_PET_LOW_TIER for item in mixed)


def test_ambiguous_or_epic_coloring_is_not_a_low_tier_candidate():
    detector = PetLowTierCandidateDetector(asset_root=ROOT)
    frame = _frame(f"{CORPUS}/normal-candidates/01.png")
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = PET_LOW_TIER_SLOT_REGIONS[0]
    left, top, right, bottom = (
        int(x1 * width),
        int(y1 * height),
        int(x2 * width),
        int(y2 * height),
    )
    midpoint = (left + right) // 2
    frame[top:bottom, left:midpoint] = (0, 220, 0)
    frame[top:bottom, midpoint:right] = (220, 80, 20)

    detected_regions = {item.region for item in detector.detect(frame)}

    assert PET_LOW_TIER_SLOT_REGIONS[0] not in detected_regions


def test_candidates_are_suppressed_after_a_pet_enters_mass_evolve_mode():
    batch, state = _analyze(f"{CORPUS}/mass-evolve-selected/01.png")

    assert MODE_PET_MASS_EVOLVE_SELECTION in state.overlays
    assert batch.find(CANDIDATE_PET_LOW_TIER) == ()


def test_mass_evolve_confirmation_reuses_one_popup_with_explicit_tier_value():
    detector = PetMassEvolveConfirmationDetector(asset_root=ROOT)
    normal = detector.detect(
        _frame(f"{CORPUS}/mass-evolve-normal-confirm/01.png")
    )
    rare = detector.detect(
        _frame(f"{CORPUS}/mass-evolve-rare-confirm/01.png")
    )

    assert len(normal) == len(rare) == 1
    assert normal[0].name == rare[0].name == (
        LANDMARK_PET_MASS_EVOLVE_CONFIRMATION
    )
    assert normal[0].value == PET_LOW_TIER_NORMAL
    assert rare[0].value == PET_LOW_TIER_RARE
    for directory in ("mass-evolve-normal-confirm", "mass-evolve-rare-confirm"):
        _, state = _analyze(f"{CORPUS}/{directory}/01.png")
        assert POPUP_PET_MASS_EVOLVE_CONFIRMATION in state.overlays


def test_combine_all_and_mass_evolve_share_one_resolved_tappable_result():
    for directory in ("combine-result", "mass-evolve-result"):
        batch, state = _analyze(f"{CORPUS}/{directory}/01.png")
        assert state.base_context == SCREEN_PET_COMBINE_RESULT
        assert batch.best(ACTIVITY_COMBINE_ANIMATION_TAPPABLE) is not None


def test_epic_runes_full_semantic_is_route_independent():
    _, combine_state = _analyze(f"{CORPUS}/epic-runes-full/01.png")
    _, evolve_state = _analyze(f"{CORPUS}/epic-runes-full/03.png")

    assert POPUP_PET_EPIC_RUNES_FULL in combine_state.overlays
    assert POPUP_PET_EPIC_RUNES_FULL in evolve_state.overlays
    assert MODE_PET_MASS_EVOLVE_SELECTION not in combine_state.overlays
    assert MODE_PET_MASS_EVOLVE_SELECTION in evolve_state.overlays


def test_manifest_keeps_epic_opening_independent_of_assumed_rune_cost():
    curation = json.loads(MANIFEST.read_text(encoding="utf-8"))["curation"]

    opening = curation["epic_opening"]
    assert "never an assumed fragment count" in opening["guard"]
    assert "7-rune" in opening["discount_events"]
    assert curation["non_resolvable_soft_block"]["future_outcome"].startswith(
        "NO_RELIEF_AVAILABLE"
    )
