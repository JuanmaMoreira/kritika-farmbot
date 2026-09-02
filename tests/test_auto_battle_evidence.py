import json
from pathlib import Path

from bot.auto_battle import DEFAULT_AUTO_BATTLE_CALIBRATION


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "datasets/auto_battle_temporal_calibration_manifest.json"


def test_curated_live_calibration_has_safe_unknown_gap_and_zero_errors():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    thresholds = payload["thresholds"]
    results = payload["curated_results"]

    assert payload["fact"] == "setting.auto_battle"
    assert payload["context"] == "screen.world_boss_battle"
    assert payload["human_ground_truth"] == "confirmed_in_chat"
    assert results["off_windows"] >= 8
    assert results["on_windows"] >= 9
    assert results["false_positives"] == 0
    assert results["false_negatives"] == 0
    assert results["maximum_off_activity"] < thresholds["off_maximum"]
    assert thresholds["off_maximum"] < thresholds["on_minimum"]
    assert thresholds["on_minimum"] < results["minimum_on_activity"]
    assert tuple(payload["roi"]) == DEFAULT_AUTO_BATTLE_CALIBRATION.roi
    assert payload["frame_count"] == DEFAULT_AUTO_BATTLE_CALIBRATION.frame_count
    assert (
        payload["minimum_frame_count"]
        == DEFAULT_AUTO_BATTLE_CALIBRATION.minimum_frame_count
    )
    assert (
        payload["acquisition_timeout_seconds"]
        == DEFAULT_AUTO_BATTLE_CALIBRATION.timeout
    )
    assert thresholds["off_maximum"] == DEFAULT_AUTO_BATTLE_CALIBRATION.off_threshold
    assert thresholds["on_minimum"] == DEFAULT_AUTO_BATTLE_CALIBRATION.on_threshold


def test_live_ensure_preserved_on_and_used_one_verified_tap_from_off():
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ensure = payload["ensure_validation"]

    assert ensure["initial_on_taps"] == 0
    assert ensure["off_to_on_taps"] == 1
    assert ensure["tap_retries"] == 0
    assert ensure["final_state_human_confirmed"] == "ON"
    assert ensure["off_activity"] <= payload["thresholds"]["off_maximum"]
    assert ensure["post_tap_on_activity"] >= payload["thresholds"]["on_minimum"]
