from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import bot.screen as screen
from tools.asset_capture import capturar_desde_dispositivo


def write_template(tmp_path, template):
    path = tmp_path / "template.png"
    assert cv2.imwrite(str(path), template)
    return path


def test_find_image_uses_explicit_frame_and_relative_region(tmp_path):
    rng = np.random.default_rng(41)
    template = rng.integers(0, 256, size=(7, 9, 3), dtype=np.uint8)
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    frame[30:37, 50:59] = template
    path = write_template(tmp_path, template)

    match = screen.find_image_on_screen(
        frame,
        path,
        region=(0.4, 0.25, 0.7, 0.6),
        threshold=0.99,
    )

    assert match == (54, 33)


def test_find_all_suppresses_overlapping_responses_and_orders_matches(tmp_path):
    rng = np.random.default_rng(73)
    template = rng.integers(0, 256, size=(8, 10, 3), dtype=np.uint8)
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    frame[10:18, 12:22] = template
    frame[50:58, 82:92] = template
    path = write_template(tmp_path, template)

    matches = screen.find_all_on_screen(frame, path, threshold=0.99)

    assert matches == [(17, 14), (87, 54)]


def test_template_larger_than_search_region_is_a_clean_no_match(tmp_path):
    template = np.zeros((20, 20, 3), dtype=np.uint8)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    path = write_template(tmp_path, template)

    assert screen.find_image_on_screen(frame, path) is None
    assert screen.find_all_on_screen(frame, path) == []


def test_template_match_score_returns_raw_best_score_for_explicit_region(tmp_path):
    rng = np.random.default_rng(101)
    template = rng.integers(0, 256, size=(8, 10, 3), dtype=np.uint8)
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    frame[30:38, 50:60] = template
    path = write_template(tmp_path, template)

    score = screen.template_match_score(
        frame, path, region=(0.4, 0.25, 0.7, 0.6)
    )

    assert score == pytest.approx(1.0, abs=1e-3)


def test_template_match_score_returns_none_when_template_does_not_fit(tmp_path):
    template = np.zeros((20, 20, 3), dtype=np.uint8)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    path = write_template(tmp_path, template)

    assert screen.template_match_score(frame, path) is None


def test_screen_no_longer_exposes_capture_or_input_infrastructure():
    retired_symbols = (
        "ScrcpyStream",
        "conectar_dispositivo",
        "capturar_pantalla",
        "click_at",
        "click_if_found",
        "is_image_on_screen",
        "swipe_from_to",
    )

    assert all(not hasattr(screen, symbol) for symbol in retired_symbols)


def test_asset_capture_reads_from_injected_frame_source():
    image = np.zeros((4, 6, 3), dtype=np.uint8)
    source = SimpleNamespace(get_frame=lambda: SimpleNamespace(image=image.copy()))

    captured = capturar_desde_dispositivo(source)

    assert np.array_equal(captured, image)
