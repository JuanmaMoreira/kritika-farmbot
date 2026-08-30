from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.perception.specs import (
    BATTLE_MODE_SELECT_HEADER_SPEC,
    BLACK_MARKET_TITLE_SPEC,
    CHARACTER_SELECT_HEADER_SPEC,
    COMBINE_ALL_TITLE_SPEC,
    COMBINE_ANIMATION_TAPPABLE_SPEC,
    COMBINE_AWAKENED_TRANSMUTE_TITLE_SPEC,
    COMBINE_ETHEREAL_MASS_PROMPT_SPEC,
    COMBINE_ETHEREAL_NO_MATERIAL_PROMPT_SPEC,
    COMBINE_ETHEREAL_RANDOM_PART_TITLE_SPEC,
    COMBINE_FUSE_ACTIVE_SPEC,
    COMBINE_FUSE_TAB_SPEC,
    COMBINE_ROW_BOTTOM_INDICATOR_SPEC,
    COMBINE_ROWS_INDICATOR_SPEC,
    COMBINE_ROWS_UPPER_INDICATOR_SPEC,
    COMBINE_TRANSMUTE_ACTIVE_SPEC,
    DAILY_QUESTS_ROW_CLAIM_SPEC,
    DAILY_QUESTS_TAB_ACTIVE_SPEC,
    DAILY_QUESTS_TITLE_SPEC,
    DEFAULT_LOCAL_CV_SPECS,
    INSUFFICIENT_GOLD_PROMPT_SPEC,
    INVENTORY_FULL_OK_BUTTON_SPEC,
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    LinearGapCalibration,
    MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC,
    MAILBOX_ROW_CLAIM_SPEC,
    MAILBOX_ROW_DELETE_SPEC,
    MAILBOX_TITLE_SPEC,
    PURCHASE_CONFIRMATION_PROMPT_SPEC,
    QUICK_MENU_LOBBY_TILE_SPEC,
    WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC,
    EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC,
    WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC,
    SOCKET_INVENTORY_FULL_PROMPT_SPEC,
    WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC,
    WORLD_BOSS_SAPPHIRES_USED_SPEC,
    WORLD_BOSS_SELECT_BOSS_HEADER_SPEC,
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
    assert LOBBY_TRADING_CENTER_LABEL_SPEC.calibration.negative_anchor == (
        pytest.approx(0.47562649846076965)
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
        "assets/ui/landmarks/black-market-title-frame-current.png"
    )
    assert BLACK_MARKET_TITLE_SPEC.variant_asset_paths == ()
    assert BLACK_MARKET_TITLE_SPEC.calibration.negative_anchor == pytest.approx(
        0.566973090171814
    )
    assert BLACK_MARKET_TITLE_SPEC.calibration.positive_anchor == pytest.approx(
        0.6773226857185364
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
    assert BATTLE_MODE_SELECT_HEADER_SPEC.asset_path.as_posix() == (
        "assets/ui/landmarks/battle-mode-world-boss-current.png"
    )
    assert BATTLE_MODE_SELECT_HEADER_SPEC.variant_asset_paths == (
        Path("assets/ui/landmarks/battle-mode-world-boss-historical.png"),
    )
    assert BATTLE_MODE_SELECT_HEADER_SPEC.region == (0.16, 0.58, 0.32, 0.68)
    assert BATTLE_MODE_SELECT_HEADER_SPEC.calibration.negative_anchor == (
        pytest.approx(0.39035069942474365)
    )
    assert BATTLE_MODE_SELECT_HEADER_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9919484853744507)
    )
    assert WORLD_BOSS_SELECT_BOSS_HEADER_SPEC.region == (0.33, 0.01, 0.67, 0.15)
    assert WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC.region == (
        0.25, 0.78, 0.75, 0.91
    )
    assert SOCKET_INVENTORY_FULL_PROMPT_SPEC.region == (
        0.31, 0.38, 0.69, 0.54
    )
    assert SOCKET_INVENTORY_FULL_PROMPT_SPEC.calibration.negative_anchor == (
        pytest.approx(0.5793697237968445)
    )
    assert SOCKET_INVENTORY_FULL_PROMPT_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9941959977149963)
    )
    assert EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC.region == (0.28, 0.32, 0.72, 0.62)
    assert EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC.calibration.negative_anchor == (
        pytest.approx(0.3778718113899231)
    )
    assert EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC.calibration.positive_anchor == (
        pytest.approx(0.9870349764823914)
    )
    assert EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC.variant_asset_paths == (
        Path("assets/ui/landmarks/equipment-inventory-full-prompt-current.png"),
    )
    assert COMBINE_FUSE_TAB_SPEC.region == (0.16, 0.13, 0.29, 0.25)
    assert COMBINE_TRANSMUTE_ACTIVE_SPEC.region == (0.23, 0.13, 0.38, 0.25)
    assert COMBINE_ROWS_INDICATOR_SPEC.region == (0.19, 0.55, 0.24, 0.96)
    assert COMBINE_ROWS_UPPER_INDICATOR_SPEC.region == (0.19, 0.55, 0.24, 0.84)
    assert COMBINE_ROW_BOTTOM_INDICATOR_SPEC.region == (0.19, 0.84, 0.24, 0.96)
    assert COMBINE_ANIMATION_TAPPABLE_SPEC.region == (0.40, 0.55, 0.60, 0.94)
    assert WORLD_BOSS_SAPPHIRES_USED_SPEC.region == (0.45, 0.74, 0.64, 0.88)
    assert WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC.region == (
        0.015, 0.22, 0.20, 0.43
    )
    assert WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC.region == (
        0.32, 0.14, 0.68, 0.36
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
        (
            BATTLE_MODE_SELECT_HEADER_SPEC,
            (320, 70),
            "d55ae274244e1b299884027a4c2958496ac58abb0c89e2ab3a784fcc094973a7",
        ),
        (
            WORLD_BOSS_SELECT_BOSS_HEADER_SPEC,
            (680, 110),
            "6bcf85d1d91b33889c0965e66b55ed4cf680e3914322e3e563c53200cce9f21d",
        ),
        (
            WORLD_BOSS_PREVIOUS_REWARDS_NOTICE_SPEC,
            (915, 75),
            "981d41283ddcf78e13646183ad3a80e2b9050cc6063e6480a94f81d7952fe3fb",
        ),
        (
            WORLD_BOSS_SAPPHIRES_USED_SPEC,
            (265, 55),
            "5c1a95f07c729fc03cf053a11ec801e5c871a72c238ca3e1356573505f76f892",
        ),
        (
            WORLD_BOSS_BATTLE_CURRENT_DAMAGE_SPEC,
            (290, 65),
            "f3e5e5e0ab898a3e19531213b85dbb893ae667a0b70101e9f05947568e924e6f",
        ),
        (
            WORLD_BOSS_RAID_COMPLETE_TITLE_SPEC,
            (700, 95),
            "b5f87a11d6b42c067820ddf3c7d101ed7d325141bad5d71398ca847419ddb132",
        ),
        (
            SOCKET_INVENTORY_FULL_PROMPT_SPEC,
            (867, 123),
            "06dfb3251fc38c459200c006ee2a02fe55ee2576547c8abee7db3731330b4cc1",
        ),
        (
            EQUIPMENT_INVENTORY_FULL_PROMPT_SPEC,
            (755, 170),
            "c14d92f88f29122a730ea32968d3aa17093fc9bcd20412deb54f4db5c839dd62",
        ),
        (
            DAILY_QUESTS_TITLE_SPEC,
            (200, 80),
            "021245cc75eac0df0edd85e1077307853bcaec5367029f216772d21dc3b77944",
        ),
        (
            DAILY_QUESTS_TAB_ACTIVE_SPEC,
            (280, 80),
            "e5a6e7b747013ffb23da3d1f94e8246cf8539a4a292e31e187252e28448711b6",
        ),
        (
            DAILY_QUESTS_ROW_CLAIM_SPEC,
            (210, 125),
            "2879136914db3c4ba336f10a8d2511be2aa8ba5c9c43bdf5cc42855399935249",
        ),
        (
            MAILBOX_TITLE_SPEC,
            (205, 75),
            "170e0379a305d6331bb323fea1f69c97a8999588c7ba194ce1513cb96e633cd8",
        ),
        (
            MAILBOX_CHARACTER_MAIL_ACTIVE_SPEC,
            (350, 110),
            "a7d0ae196a928fce558effd43dde09718c0f8d0271b5fc8cb5bde7f890254b41",
        ),
        (
            MAILBOX_ROW_CLAIM_SPEC,
            (210, 135),
            "345f4b843c8cf84a94b61083f57b59c7193258aa457e99e496f01ceb5537b22b",
        ),
        (
            MAILBOX_ROW_DELETE_SPEC,
            (210, 135),
            "45d607b16830f7bc95be86bdf46dbede69ebb4960fd54c385b14cdf5b7de47b9",
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


def test_battle_mode_historical_variant_is_the_exact_evaluated_candidate():
    repository_root = Path(__file__).resolve().parents[1]
    path = repository_root / BATTLE_MODE_SELECT_HEADER_SPEC.variant_asset_paths[0]
    payload = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(payload, dtype="uint8"), cv2.IMREAD_COLOR)

    assert image is not None
    assert (image.shape[1], image.shape[0]) == (280, 70)
    assert hashlib.sha256(payload).hexdigest() == (
        "72bf894aa0955a39ff7397897a9fb88f101b9567818a02e4d6184fe96e49b8d0"
    )


@pytest.mark.parametrize(
    ("name", "dimensions", "sha256"),
    (
        ("combine-all-higher-title-current.png", (770, 100), "716fad8eaaf27adc86ab8f6b2ec6de24d55f8ca910b3243371fd42d6e482fbd8"),
        ("combine-all-identical-title-current.png", (770, 100), "897a4624a79f8ef75b5ac4c098eef239196260d99b3aedc4e2b208f9bd43b0a3"),
        ("combine-animation-ethereal-current.png", (360, 320), "8d1d66a56782b093714ae2a4ad1b1d5041e8ef28f40345d1ffb552d212192d58"),
        ("combine-animation-fuse-current.png", (360, 320), "e3e4e0b30d21b995968413e5fa0e4e1c5b8869d2e1b3860e490c01fb8a52f9dc"),
        ("combine-animation-transmute-current.png", (360, 320), "15967cd56247f5c4f0df01b7a87c3ad9857aaf83cb91c559d8f93bf595d58800"),
        ("combine-awakened-transmute-title-current.png", (400, 85), "88434f44ff4d1844c02071da7a930834d035e202dd3af328c351fd969d5b53f7"),
        ("combine-ethereal-mass-confirm-prompt-current.png", (650, 160), "27f5753a610d10d549fc3aaf10934287d935ca856fcd7eb8867d3cf887623a10"),
        ("combine-ethereal-no-material-prompt-current.png", (840, 160), "ed20098dfb0e07602491dad2d8099eb705939b500e3ec2670e163f1c7d9f7401"),
        ("combine-ethereal-random-part-title-current.png", (400, 85), "8af627ba477eba277451ba9a734aa52d9fe13225dcc80e70064721c0f058fc31"),
        ("combine-fuse-tab-selected-current.png", (250, 100), "8813cb0cdddc2e40b3d96edf1e39aa92bbd28c5e7ba180641031b08fa9faecf4"),
        ("combine-fuse-tab-selected-dimmed-current.png", (250, 100), "680d5f76401bdc36175a153d90ffb944ab72d63e75af5e89e9f08bef0a2b2ad1"),
        ("combine-fuse-tab-unselected-current.png", (250, 100), "400e502c008f77690106301c876bebe8f2ed0667cf7d8979235bb30b83e8f556"),
        ("combine-fuse-tab-unselected-dimmed-current.png", (250, 100), "f0fdfaa582acb1e7e566e2fc9bf3e19e515b213dc74d5819d851cd5ee7c3ca1b"),
        ("combine-new-indicator-current.png", (70, 75), "2d674394d2b7057fef491e160c4cf3f900117572a139fea2c9e24ae3af0ed42a"),
        ("combine-transmute-active-current.png", (255, 100), "b2e919a8a804c0ade6e3686cdf2ae88045ebc6c9cab0314d7c7c31b3f74e022c"),
        ("combine-transmute-active-dimmed-current.png", (255, 100), "9ea7512b82649a95206ac1ebf7f2b09b34f7c22b32616c14dfa08f5f4c002b72"),
        ("equipment-inventory-full-prompt-current.png", (855, 200), "217f2d7d7122d2cdfa922cff20765d6b7a5bb7bb19b0feda44aef04f9f783f2b"),
    ),
)
def test_equipment_inventory_full_assets_are_exact_candidates(
    name, dimensions, sha256
):
    path = Path(__file__).resolve().parents[1] / "assets/ui/landmarks" / name
    payload = path.read_bytes()
    image = cv2.imdecode(np.frombuffer(payload, dtype="uint8"), cv2.IMREAD_COLOR)

    assert image is not None
    assert (image.shape[1], image.shape[0]) == dimensions
    assert hashlib.sha256(payload).hexdigest() == sha256


def test_battle_mode_landmark_avoids_the_known_dynamic_chat_region():
    chat = (0.44, 0.12, 0.85, 0.21)
    region = BATTLE_MODE_SELECT_HEADER_SPEC.region

    assert min(region[2], chat[2]) <= max(region[0], chat[0]) or min(
        region[3], chat[3]
    ) <= max(region[1], chat[1])
