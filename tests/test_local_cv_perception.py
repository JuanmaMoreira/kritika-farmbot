import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.catalog import (
    LANDMARK_BATTLE_MODE_SELECT_HEADER,
    LANDMARK_BLACK_MARKET_TITLE,
    LANDMARK_CHARACTER_SELECT_HEADER,
    LANDMARK_INSUFFICIENT_GOLD_PROMPT,
    LANDMARK_INVENTORY_FULL_OK_BUTTON,
    LANDMARK_LOBBY_TRADING_CENTER_LABEL,
    LANDMARK_MONSTER_WAVE_ENTRY_TITLE,
    LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
    LANDMARK_QUICK_MENU_LOBBY_TILE,
    LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
    LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
    LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
    POPUP_PURCHASE_CONFIRMATION,
    SCREEN_BLACK_MARKET,
)
from bot.capture import FrameSnapshot
from bot.observations import ObservationSource
from bot.perception import build_default_perception
from bot.perception.black_market import (
    BlackMarketGoldDetector,
    BlackMarketPurchasedDetector,
)
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector
from bot.perception.specs import (
    CHARACTER_SELECT_HEADER_SPEC,
    DEFAULT_LOCAL_CV_SPECS,
    LinearGapCalibration,
    LOBBY_TRADING_CENTER_LABEL_SPEC,
    LocalCvSpec,
)
from bot.catalog import build_default_resolver
from bot.state import ResolutionStatus


def write_template(tmp_path, name="template.png", seed=41):
    rng = np.random.default_rng(seed)
    template = rng.integers(0, 256, size=(8, 10, 3), dtype=np.uint8)
    path = tmp_path / name
    assert cv2.imwrite(str(path), template)
    return path, template


def spec(path, name="landmark.synthetic", region=(0.0, 0.0, 1.0, 1.0)):
    return LocalCvSpec(
        name=name,
        asset_path=path,
        region=region,
        calibration=LinearGapCalibration(0.5, 0.99),
    )


def test_local_cv_perfect_template_emits_presence_observation(tmp_path):
    path, template = write_template(tmp_path)
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    frame[20:28, 30:40] = template
    detector = LocalCvDetector(spec(path))

    detection = detector.measure(frame)
    observations = detector.detect(frame)

    assert detection.raw_match_score == pytest.approx(1.0, abs=1e-3)
    assert detection.semantic_confidence == 1.0
    assert len(observations) == 1
    assert observations[0].name == "landmark.synthetic"
    assert observations[0].source is ObservationSource.LOCAL_CV
    assert observations[0].confidence == 1.0
    assert observations[0].value is None
    assert observations[0].region is None


def test_local_cv_absence_emits_nothing(tmp_path):
    path, _ = write_template(tmp_path)
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    detector = LocalCvDetector(spec(path))

    assert detector.detect(frame) == ()


def test_local_cv_uses_the_configured_relative_region(tmp_path):
    path, template = write_template(tmp_path)
    frame = np.zeros((60, 100, 3), dtype=np.uint8)
    frame[35:43, 70:80] = template

    included = LocalCvDetector(spec(path, region=(0.6, 0.5, 0.9, 0.9)))
    excluded = LocalCvDetector(spec(path, region=(0.0, 0.0, 0.5, 0.5)))

    assert len(included.detect(frame)) == 1
    assert excluded.detect(frame) == ()


def test_local_cv_preloads_template_only_once(tmp_path):
    path, template = write_template(tmp_path)
    loader = Mock(wraps=cv2.imread)
    detector = LocalCvDetector(spec(path), template_loader=loader)
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    frame[20:28, 30:40] = template

    detector.detect(frame)
    detector.detect(frame)

    loader.assert_called_once_with(str(path.resolve()), cv2.IMREAD_GRAYSCALE)


def test_local_cv_uses_best_preloaded_rendering_variant(tmp_path):
    primary_path, _ = write_template(tmp_path, "primary.png", seed=3)
    variant_path, variant = write_template(tmp_path, "variant.png", seed=7)
    detector_spec = LocalCvSpec(
        name="landmark.synthetic",
        asset_path=primary_path,
        variant_asset_paths=(variant_path,),
        region=(0.0, 0.0, 1.0, 1.0),
        calibration=LinearGapCalibration(0.5, 0.99),
    )
    detector = LocalCvDetector(detector_spec)
    frame = np.zeros((50, 80, 3), dtype=np.uint8)
    frame[20:28, 30:40] = variant

    detection = detector.measure(frame)

    assert detection.raw_match_score == pytest.approx(1.0, abs=1e-3)
    assert detector.template_shapes == ((8, 10), (8, 10))
    assert detector.asset_paths == (
        primary_path.resolve(),
        variant_path.resolve(),
    )


def test_local_cv_spec_rejects_duplicate_rendering_variants(tmp_path):
    path, _ = write_template(tmp_path)

    with pytest.raises(ValueError, match="unique"):
        LocalCvSpec(
            name="landmark.synthetic",
            asset_path=path,
            variant_asset_paths=(path,),
            region=(0.0, 0.0, 1.0, 1.0),
            calibration=LinearGapCalibration(0.5, 0.99),
        )


def test_local_cv_keeps_raw_score_separate_from_calibrated_confidence(
    tmp_path, monkeypatch
):
    path, _ = write_template(tmp_path)
    detector = LocalCvDetector(spec(path))
    monkeypatch.setattr(
        "bot.perception.local_cv.template_match_score", lambda *args, **kwargs: 0.745
    )

    detection = detector.measure(np.zeros((50, 80, 3), dtype=np.uint8))
    observation = detector.detect(np.zeros((50, 80, 3), dtype=np.uint8))[0]

    assert detection.raw_match_score == 0.745
    assert detection.semantic_confidence == pytest.approx(0.5)
    assert observation.confidence == pytest.approx(0.5)
    assert observation.value is None


def test_local_cv_does_not_emit_at_zero_calibrated_confidence(
    tmp_path, monkeypatch
):
    path, _ = write_template(tmp_path)
    detector = LocalCvDetector(spec(path))
    monkeypatch.setattr(
        "bot.perception.local_cv.template_match_score", lambda *args, **kwargs: 0.5
    )

    assert detector.detect(np.zeros((50, 80, 3), dtype=np.uint8)) == ()


def test_local_cv_fails_clearly_when_template_does_not_fit_frame_region(tmp_path):
    path, _ = write_template(tmp_path)
    detector = LocalCvDetector(spec(path, region=(0.0, 0.0, 0.05, 0.05)))

    with pytest.raises(ValueError, match="does not fit search region"):
        detector.detect(np.zeros((50, 80, 3), dtype=np.uint8))


def test_local_cv_validates_missing_and_corrupt_assets(tmp_path):
    missing = tmp_path / "missing.png"
    with pytest.raises(FileNotFoundError, match="unavailable"):
        LocalCvDetector(spec(missing))

    corrupt = tmp_path / "corrupt.png"
    corrupt.write_text("not an image", encoding="utf-8")
    with pytest.raises(ValueError, match="could not be decoded"):
        LocalCvDetector(spec(corrupt))


def test_perception_module_import_does_not_load_assets(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(repository_root), *(str(path) for path in sys.path if path)]
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import cv2; "
                "cv2.imread = lambda *args, **kwargs: "
                "(_ for _ in ()).throw(AssertionError('asset IO during import')); "
                "import bot.perception"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_default_perception_contains_exactly_the_approved_specs(monkeypatch):
    created = []

    class StubDetector:
        def __init__(self, detector_spec):
            self.spec = detector_spec

        def detect(self, frame):
            return ()

    def build_stub(detector_spec, *, asset_root):
        created.append((detector_spec, asset_root))
        return StubDetector(detector_spec)

    monkeypatch.setattr("bot.perception.LocalCvDetector", build_stub)

    engine = build_default_perception()
    second = build_default_perception()

    assert engine is not second
    assert tuple(
        detector.spec for detector in engine.detectors[:-2]
    ) == DEFAULT_LOCAL_CV_SPECS
    assert isinstance(engine.detectors[-2], BlackMarketGoldDetector)
    assert isinstance(engine.detectors[-1], BlackMarketPurchasedDetector)
    assert len(created) == 2 * len(DEFAULT_LOCAL_CV_SPECS)
    assert tuple(spec.name for spec in DEFAULT_LOCAL_CV_SPECS) == (
        LANDMARK_LOBBY_TRADING_CENTER_LABEL,
        LANDMARK_CHARACTER_SELECT_HEADER,
        LANDMARK_BATTLE_MODE_SELECT_HEADER,
        LANDMARK_BLACK_MARKET_TITLE,
        LANDMARK_INSUFFICIENT_GOLD_PROMPT,
        LANDMARK_INVENTORY_FULL_OK_BUTTON,
        LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
        LANDMARK_QUICK_MENU_LOBBY_TILE,
        LANDMARK_WORLD_BOSS_SELECT_BOSS_HEADER,
        LANDMARK_WORLD_BOSS_PREVIOUS_REWARDS_NOTICE,
        LANDMARK_WORLD_BOSS_SAPPHIRES_USED,
        LANDMARK_WORLD_BOSS_BATTLE_CURRENT_DAMAGE,
        LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    )
    assert LANDMARK_MONSTER_WAVE_ENTRY_TITLE not in {
        spec.name for spec in DEFAULT_LOCAL_CV_SPECS
    }


@pytest.mark.parametrize(
    "production_spec",
    (LOBBY_TRADING_CENTER_LABEL_SPEC, CHARACTER_SELECT_HEADER_SPEC),
)
def test_promoted_detector_emits_only_for_its_curated_candidate(production_spec):
    repository_root = Path(__file__).resolve().parents[1]
    template = cv2.imread(
        str(repository_root / production_spec.asset_path),
        cv2.IMREAD_COLOR,
    )
    assert template is not None
    detector = LocalCvDetector(production_spec, asset_root=repository_root)
    frame = np.zeros((1224, 2712, 3), dtype=np.uint8)
    height, width = template.shape[:2]
    x1 = int(production_spec.region[0] * frame.shape[1])
    y1 = int(production_spec.region[1] * frame.shape[0])
    frame[y1 : y1 + height, x1 : x1 + width] = template

    observation = detector.detect(frame)[0]

    assert observation.name == production_spec.name
    assert observation.source is ObservationSource.LOCAL_CV
    assert observation.confidence == 1.0
    assert detector.detect(np.zeros_like(frame)) == ()


def build_synthetic_pipeline(tmp_path):
    black_path, black = write_template(tmp_path, "black.png", seed=73)
    purchase_path, purchase = write_template(tmp_path, "purchase.png", seed=101)
    calibration = LinearGapCalibration(0.999, 0.9999)
    detectors = (
        LocalCvDetector(
            LocalCvSpec(
                LANDMARK_BLACK_MARKET_TITLE,
                black_path,
                (0.0, 0.0, 0.5, 1.0),
                calibration,
            )
        ),
        LocalCvDetector(
            LocalCvSpec(
                LANDMARK_PURCHASE_CONFIRMATION_PROMPT,
                purchase_path,
                (0.5, 0.0, 1.0, 1.0),
                calibration,
            )
        ),
    )
    return PerceptionEngine(detectors), black, purchase


def analyze_synthetic(engine, black, purchase, *, include_black, include_purchase):
    frame = np.zeros((60, 120, 3), dtype=np.uint8)
    if include_black:
        frame[20:28, 20:30] = black
    if include_purchase:
        frame[30:38, 80:90] = purchase
    snapshot = FrameSnapshot(frame, timestamp=9.5, sequence=12)
    return engine.analyze(snapshot)


def test_in_memory_pipeline_resolves_black_market(tmp_path):
    engine, black, purchase = build_synthetic_pipeline(tmp_path)

    batch = analyze_synthetic(
        engine, black, purchase, include_black=True, include_purchase=False
    )
    state = build_default_resolver().resolve(batch)

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_BLACK_MARKET
    assert state.overlays == ()


def test_in_memory_pipeline_resolves_purchase_with_unknown_base(tmp_path):
    engine, black, purchase = build_synthetic_pipeline(tmp_path)

    batch = analyze_synthetic(
        engine, black, purchase, include_black=False, include_purchase=True
    )
    state = build_default_resolver().resolve(batch)

    assert state.status is ResolutionStatus.UNKNOWN
    assert state.base_context is None
    assert state.overlays == (POPUP_PURCHASE_CONFIRMATION,)


def test_in_memory_pipeline_resolves_black_market_plus_overlay(tmp_path):
    engine, black, purchase = build_synthetic_pipeline(tmp_path)

    batch = analyze_synthetic(
        engine, black, purchase, include_black=True, include_purchase=True
    )
    state = build_default_resolver().resolve(batch)

    assert state.status is ResolutionStatus.RESOLVED
    assert state.base_context == SCREEN_BLACK_MARKET
    assert state.overlays == (POPUP_PURCHASE_CONFIRMATION,)
