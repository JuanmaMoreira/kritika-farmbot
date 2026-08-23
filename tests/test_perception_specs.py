from dataclasses import FrozenInstanceError

import pytest

from bot.perception.specs import LinearGapCalibration


def test_linear_gap_calibration_is_immutable_and_normalizes_anchors():
    calibration = LinearGapCalibration(1, 3)

    assert calibration.negative_anchor == 1.0
    assert calibration.positive_anchor == 3.0
    with pytest.raises(FrozenInstanceError):
        calibration.negative_anchor = 0.0


@pytest.mark.parametrize("anchors", [(1.0, 1.0), (2.0, 1.0)])
def test_linear_gap_calibration_rejects_equal_or_inverted_anchors(anchors):
    with pytest.raises(ValueError, match="less than"):
        LinearGapCalibration(*anchors)


@pytest.mark.parametrize(
    "anchors",
    [
        (float("nan"), 1.0),
        (0.0, float("inf")),
        (float("-inf"), 1.0),
        (False, 1.0),
    ],
)
def test_linear_gap_calibration_rejects_non_finite_or_non_real_anchors(anchors):
    with pytest.raises(ValueError, match="finite real"):
        LinearGapCalibration(*anchors)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (-10.0, 0.0),
        (0.2, 0.0),
        (0.5, 0.5),
        (0.8, 1.0),
        (10.0, 1.0),
    ],
)
def test_linear_gap_calibration_clamps_and_interpolates(score, expected):
    calibration = LinearGapCalibration(0.2, 0.8)

    assert calibration.confidence(score) == pytest.approx(expected)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf"), True])
def test_linear_gap_calibration_rejects_invalid_scores(score):
    calibration = LinearGapCalibration(0.2, 0.8)

    with pytest.raises(ValueError, match="raw_match_score"):
        calibration.confidence(score)
