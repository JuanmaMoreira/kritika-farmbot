import json
from pathlib import Path

import cv2
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import (
    INDICATOR_PET_EPIC_AVAILABLE,
    INDICATOR_PET_EPIC_UNAVAILABLE,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_PET_INVENTORY_FULL,
    SCREEN_PET_COMBINE,
    SCREEN_PET_SUMMON,
    SCREEN_PET_SUMMON_RESULT,
    SCREEN_PETS_MANAGE,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_PREMIUM_TICKET_AVAILABLE,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
    build_default_resolver,
)
from bot.perception import PetEpicAvailabilityDetector, build_default_perception
from bot.state import ResolutionStatus
from tools.semantic_slice_evaluation import load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/pet_summon_semantic_manifest.json"


def _frame(relative_path: str):
    frame = cv2.imread(str(ROOT / relative_path), cv2.IMREAD_COLOR)
    assert frame is not None, relative_path
    return frame


def _resolve(relative_path: str):
    batch = build_default_perception(ROOT).analyze(
        FrameSnapshot(_frame(relative_path), 1.0, 1)
    )
    return batch, build_default_resolver().resolve(batch)


def test_all_human_confirmed_pet_summon_frames_resolve_exactly():
    entries = load_manifest(MANIFEST)

    assert len(entries) == 48
    for entry in entries:
        batch, state = _resolve(entry.path)
        assert state.status is ResolutionStatus.RESOLVED, entry.path
        assert state.base_context == entry.base_context, entry.path
        assert state.overlays == entry.overlays, entry.path
        assert all(batch.best(name) is not None for name in entry.observations)


@pytest.mark.parametrize(
    ("directory", "base", "required_overlays"),
    (
        ("manage", SCREEN_PETS_MANAGE, (STATUS_PET_SUMMON_DAILY_ACTIVE,)),
        (
            "summon-daily-active",
            SCREEN_PET_SUMMON,
            (
                STATUS_PET_EPIC_AVAILABLE,
                STATUS_PET_PREMIUM_TICKET_AVAILABLE,
                STATUS_PET_SUMMON_DAILY_ACTIVE,
            ),
        ),
        (
            "summon-epic-unavailable",
            SCREEN_PET_SUMMON,
            (STATUS_PET_EPIC_UNAVAILABLE, STATUS_PET_PREMIUM_GOLD),
        ),
        ("epic-result", SCREEN_PET_SUMMON_RESULT, ()),
        ("premium-ticket-result", SCREEN_PET_SUMMON_RESULT, ()),
        ("premium-gold-result", SCREEN_PET_SUMMON_RESULT, ()),
        ("pet-combine", SCREEN_PET_COMBINE, ()),
        (
            "premium-insufficient-gold",
            SCREEN_PET_SUMMON,
            (POPUP_INSUFFICIENT_GOLD, STATUS_PET_PREMIUM_GOLD),
        ),
        (
            "pet-inventory-full",
            SCREEN_PET_SUMMON,
            (POPUP_PET_INVENTORY_FULL, STATUS_PET_PREMIUM_GOLD),
        ),
    ),
)
def test_future_flow_outcomes_have_explicit_semantics(
    directory: str,
    base: str,
    required_overlays: tuple[str, ...],
):
    _, state = _resolve(
        f"screencaps/semantic/pet_summon/{directory}/01.png"
    )

    assert state.base_context == base
    assert state.overlays == required_overlays


def test_epic_availability_uses_card_rendering_not_fragment_ocr():
    detector = PetEpicAvailabilityDetector(asset_root=ROOT)
    available = detector.measure(
        _frame(
            "screencaps/semantic/pet_summon/"
            "summon-epic-available-premium-ticket/01.png"
        )
    )
    unavailable = detector.measure(
        _frame(
            "screencaps/semantic/pet_summon/"
            "summon-epic-unavailable/01.png"
        )
    )

    assert available.value_mean > 185.0
    assert available.available_confidence >= 0.80
    assert available.unavailable_confidence == 0.0
    assert unavailable.value_mean < 87.0
    assert unavailable.unavailable_confidence >= 0.80
    assert unavailable.available_confidence == 0.0


@pytest.mark.parametrize(
    "directory",
    (
        "epic-selector",
        "premium-ticket-selector",
        "premium-gold-selector",
        "epic-insufficient-fragments",
        "pet-inventory-full",
        "premium-insufficient-gold",
    ),
)
def test_epic_availability_is_suppressed_while_modal_state_is_active(
    directory: str,
):
    batch, _ = _resolve(
        f"screencaps/semantic/pet_summon/{directory}/01.png"
    )

    assert batch.best(INDICATOR_PET_EPIC_AVAILABLE) is None
    assert batch.best(INDICATOR_PET_EPIC_UNAVAILABLE) is None


def test_manifest_records_business_boundaries_without_implementing_policy():
    curation = json.loads(MANIFEST.read_text(encoding="utf-8"))["curation"]

    assert "no flow" in curation["scope"]
    assert "PetSummonSpaceRelief" in curation["scope"]
    assert curation["premium"]["policy_boundary"].startswith(
        "the game chooses ticket or GOLD"
    )
    assert curation["insufficient_gold"]["future_outcome"].startswith(
        "INSUFFICIENT_GOLD non-fatal"
    )
    assert curation["pet_full"]["yes_destination"] == SCREEN_PET_COMBINE
