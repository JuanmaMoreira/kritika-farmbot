import numpy as np
import pytest

from bot.character_select_scroll import CharacterSelectScrollDetector


def test_identical_character_grid_means_end_of_scroll():
    detector = CharacterSelectScrollDetector()
    frame = np.zeros((200, 400, 3), dtype=np.uint8)
    frame[50:150, 210:330] = (30, 140, 220)

    assert detector.difference(frame, frame.copy()) == 0.0
    assert detector.reached_end(frame, frame.copy())


def test_changes_inside_character_grid_mean_scroll_progress():
    detector = CharacterSelectScrollDetector(unchanged_threshold=0.03)
    first = np.zeros((200, 400, 3), dtype=np.uint8)
    second = first.copy()
    second[45:155, 205:335] = 255

    assert detector.difference(first, second) > 0.03
    assert not detector.reached_end(first, second)


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
