import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.character_select_scroll import (
    CharacterSelectScrollDetector,
    ScrollAttemptKind,
)


def _snapshot(sequence, image):
    return FrameSnapshot(
        image=image,
        timestamp=float(sequence),
        sequence=sequence,
    )


def test_identical_character_grid_is_only_settled_similarity():
    detector = CharacterSelectScrollDetector()
    frame = np.zeros((200, 400, 3), dtype=np.uint8)
    frame[50:150, 210:330] = (30, 140, 220)

    assert detector.difference(frame, frame.copy()) == 0.0
    assert detector.settled_similar(frame, frame.copy())


def test_changes_inside_character_grid_mean_scroll_progress():
    detector = CharacterSelectScrollDetector(unchanged_threshold=0.03)
    first = np.zeros((200, 400, 3), dtype=np.uint8)
    second = first.copy()
    second[45:155, 205:335] = 255

    assert detector.difference(first, second) > 0.03
    assert not detector.settled_similar(first, second)


def test_animation_outside_grid_is_ignored():
    detector = CharacterSelectScrollDetector()
    first = np.zeros((200, 400, 3), dtype=np.uint8)
    second = first.copy()
    second[:, :150] = 255

    assert detector.difference(first, second) == 0.0


@pytest.mark.parametrize(
    "kwargs",
    (
        {"region": (0.5, 0.2, 0.5, 0.8)},
        {"thumbnail_width": 0},
        {"thumbnail_height": True},
        {"unchanged_threshold": -0.1},
        {"unchanged_threshold": 1.1},
    ),
)
def test_detector_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        CharacterSelectScrollDetector(**kwargs)


def test_detector_rejects_non_bgr_frames():
    detector = CharacterSelectScrollDetector()

    with pytest.raises(ValueError, match="BGR"):
        detector.difference(
            np.zeros((20, 40), dtype=np.uint8),
            np.zeros((20, 40), dtype=np.uint8),
        )


def test_transition_measurement_separates_transient_peak_from_settled_frame():
    detector = CharacterSelectScrollDetector(unchanged_threshold=0.03)
    before_image = np.zeros((200, 400, 3), dtype=np.uint8)
    transient_image = before_image.copy()
    transient_image[45:155, 205:335] = 255
    settled_image = before_image.copy()
    settled_image[45:155, 205:335] = 4
    before = _snapshot(10, before_image)
    transient = _snapshot(11, transient_image)
    settled = _snapshot(12, settled_image)

    measurement = detector.measure_transition(
        before, [transient, settled], settled
    )

    assert measurement.pre_sequence == 10
    assert measurement.settled_sequence == 12
    assert measurement.fresh_sample_count == 2
    assert measurement.transient_peak_sequence == 11
    assert measurement.max_transient_difference > 0.03
    assert measurement.settled_difference < 0.03
    assert detector.classify(
        measurement, movement_threshold=0.03
    ) is ScrollAttemptKind.BOUNCE_CANDIDATE


def test_transition_measurement_rejects_stale_or_reused_samples():
    detector = CharacterSelectScrollDetector()
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    before = _snapshot(10, image)
    stale = _snapshot(10, image.copy())

    with pytest.raises(ValueError, match="strictly increasing fresh"):
        detector.measure_transition(before, [stale], stale)


def test_transition_classification_requires_observed_movement():
    detector = CharacterSelectScrollDetector(unchanged_threshold=0.03)
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    before = _snapshot(1, image)
    settled = _snapshot(2, image.copy())
    measurement = detector.measure_transition(before, [settled], settled)

    assert detector.classify(
        measurement, movement_threshold=0.01
    ) is ScrollAttemptKind.INEFFECTIVE


@pytest.mark.parametrize("movement_threshold", (-0.1, 1.1, True))
def test_transition_classification_rejects_invalid_movement_threshold(
    movement_threshold,
):
    detector = CharacterSelectScrollDetector()
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    before = _snapshot(1, image)
    settled = _snapshot(2, image.copy())
    measurement = detector.measure_transition(before, [settled], settled)

    with pytest.raises(ValueError, match="movement_threshold"):
        detector.classify(
            measurement, movement_threshold=movement_threshold
        )
