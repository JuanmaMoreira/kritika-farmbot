import pytest

from bot.character_select_scroll import CharacterSelectScrollProfile


def test_default_profile_contains_validated_character_select_configuration():
    profile = CharacterSelectScrollProfile()

    assert profile.region == (0.49, 0.19, 0.85, 0.805)
    assert profile.movement_threshold == 0.05
    assert profile.settled_threshold == 0.05
    assert profile.progress_swipe.start == (0.8, 0.8)
    assert profile.progress_swipe.end == (0.8, 0.025)
    assert profile.progress_swipe.duration_ms == 190
    assert profile.confirmation_swipe.start == (0.68, 0.76)
    assert profile.confirmation_swipe.end == (0.68, 0.24)
    assert profile.confirmation_swipe.duration_ms == 200
    assert profile.required_confirmations == 1
    assert profile.max_attempts == 3
    assert profile.settle_for == 1.0


def test_profile_builds_generic_detector_and_scroll_config():
    profile = CharacterSelectScrollProfile(max_attempts=4)

    detector = profile.detector()
    config = profile.config()

    assert detector.region == profile.region
    assert detector.unchanged_threshold == profile.settled_threshold
    assert config.progress_swipe is profile.progress_swipe
    assert config.confirmation_swipe is profile.confirmation_swipe
    assert config.max_attempts == 4


@pytest.mark.parametrize(
    "kwargs",
    (
        {"region": (0.5, 0.2, 0.5, 0.8)},
        {"thumbnail_width": 0},
        {"settled_threshold": -0.1},
        {"movement_threshold": 1.1},
        {"required_confirmations": 0},
        {"max_attempts": 0},
    ),
)
def test_profile_rejects_invalid_scroll_configuration(kwargs):
    with pytest.raises(ValueError):
        CharacterSelectScrollProfile(**kwargs)
