"""Early exits preserve the original measure-based emission and error boundary."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.catalog import (
    CANDIDATE_PET_LOW_TIER, INDICATOR_PET_EPIC_AVAILABLE,
    INDICATOR_PET_EPIC_UNAVAILABLE, SEMANTIC_CONFIDENCE_THRESHOLD,
)
from bot.observations import Observation, ObservationSource
from bot.perception.pet_combine import PetLowTierCandidateDetector
from bot.perception.pet_summon import PetEpicAvailabilityDetector


ROOT = Path(__file__).resolve().parents[1]


def original_emission(detector, frame):
    """Original public detect contract expressed through diagnostic measure."""
    reading = detector.measure(frame)
    if isinstance(detector, PetLowTierCandidateDetector):
        return tuple(Observation(CANDIDATE_PET_LOW_TIER, r.confidence,
            ObservationSource.LOCAL_CV, value=r.tier, region=r.region)
            for r in reading if r.tier is not None
            and r.confidence >= SEMANTIC_CONFIDENCE_THRESHOLD)
    return tuple(Observation(name, confidence, ObservationSource.LOCAL_CV,
                            region=detector.region)
        for name, confidence in (
            (INDICATOR_PET_EPIC_AVAILABLE, reading.available_confidence),
            (INDICATOR_PET_EPIC_UNAVAILABLE, reading.unavailable_confidence))
        if confidence >= detector.confidence_threshold)


def outcome(call):
    try:
        return ("return", call())
    except (ValueError, cv2.error) as error:
        return (type(error), error.args)


def gates(monkeypatch, detector, confidence, *, prompt=1., blocker=None):
    first = detector._combine if isinstance(detector, PetLowTierCandidateDetector) else detector._summon
    items = [first]
    scores = [confidence]
    if isinstance(detector, PetLowTierCandidateDetector):
        items.append(detector._prompt); scores.append(prompt)
    items.extend(detector._blockers)
    scores.extend(.8 if i == blocker else 0. for i in range(len(detector._blockers)))
    mocks = []
    for item, score in zip(items, scores):
        spy = Mock(return_value=SimpleNamespace(semantic_confidence=score))
        monkeypatch.setattr(item, "measure", spy)
        mocks.append(spy)
    return mocks


@pytest.mark.parametrize("confidence", [0., np.nextafter(.8, 0.), .8, np.nextafter(.8, 1.), 1.])
@pytest.mark.parametrize("color,tier", [((0, 200, 0), "normal"), ((200, 0, 0), "rare")])
def test_low_tier_boundary_and_adversarial_slot_colors(monkeypatch, confidence, color, tier):
    detector = PetLowTierCandidateDetector(asset_root=ROOT)
    frame = np.full((1224, 2712, 3), color, dtype=np.uint8)
    spies = gates(monkeypatch, detector, confidence)
    expected = original_emission(detector, frame)
    for spy in spies: spy.reset_mock()
    actual = detector.detect(frame)
    assert actual == expected
    spies[0].assert_called_once()
    if confidence < .8:
        assert actual == ()
        assert all(spy.call_count == 0 for spy in spies[1:])
    else:
        assert len(actual) == 16
        assert {o.value for o in actual} == {tier}
        assert {o.confidence for o in actual} == {confidence}
        assert all(spy.call_count == 1 for spy in spies[1:])
    # Diagnostics still computes colors/tier and every later gate when inactive.
    measured = detector.measure(frame)
    assert len(measured) == 16
    assert {r.tier for r in measured} == {tier}
    assert {r.confidence for r in measured} == {confidence}


@pytest.mark.parametrize("confidence", [0., np.nextafter(.8, 0.), .8, np.nextafter(.8, 1.), 1.])
@pytest.mark.parametrize("brightness,name", [(100, INDICATOR_PET_EPIC_AVAILABLE), (44, INDICATOR_PET_EPIC_UNAVAILABLE)])
def test_epic_boundary_and_both_availability_states(monkeypatch, confidence, brightness, name):
    detector = PetEpicAvailabilityDetector(asset_root=ROOT)
    frame = np.full((1224, 2712, 3), brightness, dtype=np.uint8)
    spies = gates(monkeypatch, detector, confidence)
    expected = original_emission(detector, frame)
    for spy in spies: spy.reset_mock()
    actual = detector.detect(frame)
    assert actual == expected
    spies[0].assert_called_once()
    if confidence < .8:
        assert actual == ()
        assert all(spy.call_count == 0 for spy in spies[1:])
    else:
        assert len(actual) == 1
        assert actual[0].name == name
        assert actual[0].confidence == confidence
        assert all(spy.call_count == 1 for spy in spies[1:])
    measured = detector.measure(frame)
    assert measured.value_mean == brightness
    assert measured.summon_confidence == confidence
    assert measured.blocked_confidence == 0.


@pytest.mark.parametrize("factory", [PetLowTierCandidateDetector, PetEpicAvailabilityDetector])
@pytest.mark.parametrize("blocker", range(6))
def test_every_blocker_still_suppresses_admitted_branch(monkeypatch, factory, blocker):
    detector = factory(asset_root=ROOT)
    color = (0, 200, 0) if factory is PetLowTierCandidateDetector else (100, 100, 100)
    frame = np.full((1224, 2712, 3), color, dtype=np.uint8)
    spies = gates(monkeypatch, detector, 1., blocker=blocker)
    assert original_emission(detector, frame) == ()
    for spy in spies: spy.reset_mock()
    assert detector.detect(frame) == ()
    assert all(spy.call_count == 1 for spy in spies)


@pytest.mark.parametrize("prompt", [np.nextafter(.8, 0.), .8, np.nextafter(.8, 1.)])
def test_low_tier_prompt_remains_part_of_min_gate(monkeypatch, prompt):
    detector = PetLowTierCandidateDetector(asset_root=ROOT)
    frame = np.full((1224, 2712, 3), (0, 200, 0), dtype=np.uint8)
    gates(monkeypatch, detector, 1., prompt=prompt)
    assert detector.detect(frame) == original_emission(detector, frame)
    assert len(detector.detect(frame)) == (16 if prompt >= .8 else 0)


@pytest.mark.parametrize("factory", [PetLowTierCandidateDetector, PetEpicAvailabilityDetector])
@pytest.mark.parametrize("frame", [None, [], np.zeros((30, 40), np.uint8),
    np.zeros((0, 40, 3), np.uint8), np.zeros((30, 0, 3), np.uint8),
    np.zeros((30, 40, 4), np.uint8), np.zeros((30, 40, 3), np.float32)])
def test_malformed_frame_preserves_diagnostic_error(factory, frame):
    detector = factory(asset_root=ROOT)
    expected = outcome(lambda: original_emission(detector, frame))
    assert expected[0] is ValueError
    assert outcome(lambda: detector.detect(frame)) == expected


@pytest.mark.parametrize("factory,shape", [
    (PetLowTierCandidateDetector, (820, 1800)),  # combine fits, prompt does not
    (PetLowTierCandidateDetector, (900, 2000)),  # later selection template does not fit
    (PetEpicAvailabilityDetector, (820, 1900)),  # summon fits, first blocker does not
    (PetEpicAvailabilityDetector, (1000, 2000)), # later fragment template does not fit
])
def test_closed_gate_keeps_error_from_later_incompatible_template(factory, shape):
    detector = factory(asset_root=ROOT)
    frame = np.zeros((*shape, 3), np.uint8)
    first = detector._combine if factory is PetLowTierCandidateDetector else detector._summon
    assert first.measure(frame).semantic_confidence < .8
    expected = outcome(lambda: original_emission(detector, frame))
    assert expected[0] is ValueError
    assert "does not fit search region" in expected[1][0]
    assert outcome(lambda: detector.detect(frame)) == expected


@pytest.mark.parametrize("factory", [PetLowTierCandidateDetector, PetEpicAvailabilityDetector])
@pytest.mark.parametrize("keep_compatible_variant", [False, True])
def test_template_variants_preserve_any_fit_and_no_fit_errors(factory, keep_compatible_variant):
    detector = factory(asset_root=ROOT)
    frame = np.zeros((1224, 2712, 3), np.uint8)
    target = detector._prompt if factory is PetLowTierCandidateDetector else detector._blockers[0]
    oversized = np.zeros((1500, 2800), np.uint8)
    target._templates = (*target._templates, oversized) if keep_compatible_variant else (oversized,)
    expected = outcome(lambda: original_emission(detector, frame))
    assert outcome(lambda: detector.detect(frame)) == expected
    assert expected[0] == ("return" if keep_compatible_variant else ValueError)


@pytest.mark.parametrize("factory", [PetLowTierCandidateDetector, PetEpicAvailabilityDetector])
def test_empty_color_roi_retains_original_error(monkeypatch, factory):
    detector = factory(asset_root=ROOT)
    frame = np.zeros((1224, 2712, 3), np.uint8)
    if factory is PetLowTierCandidateDetector:
        monkeypatch.setattr("bot.perception.pet_combine.PET_LOW_TIER_SLOT_REGIONS", ((0., 0., 0., 0.),))
    else:
        detector.region = (0., 0., 0., 0.)
    expected = outcome(lambda: original_emission(detector, frame))
    assert expected[0] in (ValueError, cv2.error)
    assert outcome(lambda: detector.detect(frame)) == expected
