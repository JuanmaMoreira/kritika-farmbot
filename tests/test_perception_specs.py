from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.perception.specs import (
    BLACK_MARKET_TITLE_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    DEFAULT_LOCAL_CV_SPECS,
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    INVENTORY_FULL_OK_BUTTON_SPEC,
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    LinearGapCalibration,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
)


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


def test_promoted_specs_use_curated_assets_regions_and_valid_calibrations():
    assert LOBBY_TRADING_CENTER_LABEL_SPEC.asset_path.as_posix() == (
        "assets/ui/landmarks/lobby-trading-center-label.png"
    )
    assert LOBBY_TRADING_CENTER_LABEL_SPEC.region == (
        0.19095870206489673,
        0.905032679738562,
        0.29761061946902656,
        0.9822222222222222,
    )
    assert CHARACTER_SELECT_HEADER_SPEC.asset_path.as_posix() == (
        "assets/ui/landmarks/character-select-header.png"
    )
    assert CHARACTER_SELECT_HEADER_SPEC.region == (
        0.40297935103244836,
        0.02676470588235294,
        0.5852212389380531,
        0.11212418300653594,
    )
    assert CHARACTER_SELECT_HEADER_SPEC.calibration.negative_anchor == (
        pytest.approx(0.2776434123516083)
    )
    assert BLACK_MARKET_TITLE_SPEC.asset_path.as_posix() == (
        "assets/ui/black-market-id.png"
    )
    assert BLACK_MARKET_TITLE_SPEC.variant_asset_paths == ()
    assert BLACK_MARKET_TITLE_SPEC.calibration.negative_anchor == pytest.approx(
        0.2230203002691269
    )
    assert BLACK_MARKET_TITLE_SPEC.calibration.positive_anchor == pytest.approx(
        0.3993116021156311
    )
    assert INSUFFICIENT_GOLD_PROMPT_SPEC.asset_path.as_posix() == (
        "assets/ui/landmarks/insufficient-gold-prompt-current.png"
    )
    assert INSUFFICIENT_GOLD_PROMPT_SPEC.region == (
        1100 / 2712,
        500 / 1224,
        1620 / 2712,
        610 / 1224,
    )
    assert INSUFFICIENT_GOLD_PROMPT_SPEC.calibration.negative_anchor == (
        pytest.approx(0.443979948759079)
    )
    assert INSUFFICIENT_GOLD_PROMPT_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9999777674674988)
    )
    assert INVENTORY_FULL_OK_BUTTON_SPEC.asset_path.as_posix() == (
        "assets/ui/landmarks/inventory-full-ok-button-current.png"
    )
    assert INVENTORY_FULL_OK_BUTTON_SPEC.region == (0.41, 0.54, 0.59, 0.70)
    assert INVENTORY_FULL_OK_BUTTON_SPEC.calibration.negative_anchor == (
        pytest.approx(0.8948967456817627)
    )
    assert INVENTORY_FULL_OK_BUTTON_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9836453795433044)
    )
    assert PURCHASE_CONFIRMATION_PROMPT_SPEC.variant_asset_paths == (
        Path("assets/ui/landmarks/purchase-confirmation-prompt-current.png"),
    )
    assert PURCHASE_CONFIRMATION_PROMPT_SPEC.region == (
        1235 / 2712,
        590 / 1224,
        1460 / 2712,
        647 / 1224,
    )
    assert PURCHASE_CONFIRMATION_PROMPT_SPEC.calibration.negative_anchor == (
        pytest.approx(0.4875827729701996)
    )
    assert PURCHASE_CONFIRMATION_PROMPT_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9959162473678589)
    )
    assert QUICK_MENU_LOBBY_TILE_SPEC.asset_path.as_posix() == (
        "assets/ui/landmarks/quick-menu-lobby-tile.png"
    )
    assert QUICK_MENU_LOBBY_TILE_SPEC.region == (0.02, 0.10, 0.25, 0.32)
    assert QUICK_MENU_LOBBY_TILE_SPEC.calibration.negative_anchor == (
        pytest.approx(0.2981472909450531)
    )
    assert QUICK_MENU_LOBBY_TILE_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9826233983039856)
    )
    assert all(
        spec.calibration.negative_anchor
        < spec.calibration.positive_anchor
        for spec in DEFAULT_LOCAL_CV_SPECS
    )


@pytest.mark.parametrize(
    ("spec", "dimensions", "sha256"),
    (
        (
            LOBBY_TRADING_CENTER_LABEL_SPEC,
            (235, 70),
            "483ec9fa2d5bd07e8bb2fc8e8188e9ccc0b916c453e0a4818b9428dab801b360",
        ),
        (
            CHARACTER_SELECT_HEADER_SPEC,
            (440, 80),
            "e16be1dc88a74f9f4511d5c0058f7249e635dcd2bca864c1f206f567b2b61e93",
        ),
        (
            INSUFFICIENT_GOLD_PROMPT_SPEC,
            (375, 52),
            "5917521be0a18a42bd8fa24ffca4c796c1aac92ee6873fe6a7bf15119b61bf07",
        ),
        (
            INVENTORY_FULL_OK_BUTTON_SPEC,
            (355, 115),
            "409423118776db07478b15f43dc8c15a1a44a55cd89e1636c2cf00d95066b32e",
        ),
        (
            PURCHASE_CONFIRMATION_PROMPT_SPEC,
            (212, 35),
            "02f96359411f6f23a7cb73c9dd5a986cd3afb8f6978fe04fc17aa9ab4d788f1d",
        ),
        (
            QUICK_MENU_LOBBY_TILE_SPEC,
            (126, 140),
            "314fdc69d94e252c75c96428ef450bbf6c7044934cdda76872b6ac39378af180",
        ),
    ),
)
def test_promoted_assets_are_exact_evaluated_candidates(spec, dimensions, sha256):
    repository_root = Path(__file__).resolve().parents[1]
    asset_path = spec.asset_path
    if spec is PURCHASE_CONFIRMATION_PROMPT_SPEC:
        asset_path = spec.variant_asset_paths[0]
    asset = repository_root / asset_path
    payload = asset.read_bytes()
    image = cv2.imdecode(np.frombuffer(payload, dtype="uint8"), cv2.IMREAD_COLOR)

    assert image is not None
    assert (image.shape[1], image.shape[0]) == dimensions
    assert hashlib.sha256(payload).hexdigest() == sha256
