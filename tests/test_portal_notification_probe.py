"""Hermetic tests for the on-demand portal notification probe.

All frames are synthetic and seeded; the only versioned input is the small
promoted X+panel template asset. No phone or acquisition frames required.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.geometry import relative_region_to_pixels
from bot.portal_notification import (
    PORTAL_DISMISS_X_ASSET,
    PORTAL_DISMISS_X_VARIANT_ASSETS,
    PortalNotificationProbe,
    PortalProbeOutcome,
)


def _asset() -> np.ndarray:
    path = Path(__file__).resolve().parents[1] / PORTAL_DISMISS_X_ASSET
    template = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert template is not None and template.size > 0
    return template


def _background(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(800, 1600, 3), dtype=np.uint8)


def test_default_probe_wires_asset_scorer_with_measured_operating_point():
    probe = PortalNotificationProbe()
    assert probe.scorer is not None
    assert probe.absent_threshold == 0.65
    assert probe.confirm_threshold == 0.80
    assert probe.absent_threshold < probe.confirm_threshold


def _paste(background: np.ndarray, template: np.ndarray) -> np.ndarray:
    probe = PortalNotificationProbe()
    x1, y1, _, _ = relative_region_to_pixels(probe.region, 1600, 800)
    pasted = background.copy()
    height, width = template.shape[:2]
    pasted[y1 : y1 + height, x1 : x1 + width] = template
    return pasted


def test_pasted_template_confirms_while_noise_never_confirms():
    probe = PortalNotificationProbe()
    background = _background()
    assert probe.probe(background) is not PortalProbeOutcome.CONFIRMED
    assert probe.probe(_paste(background, _asset())) is (
        PortalProbeOutcome.CONFIRMED
    )


def test_pasted_hell_variant_confirms_through_max():
    probe = PortalNotificationProbe()
    assert PORTAL_DISMISS_X_VARIANT_ASSETS
    for variant in PORTAL_DISMISS_X_VARIANT_ASSETS:
        path = Path(__file__).resolve().parents[1] / variant
        template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert template is not None and template.size > 0
        assert probe.probe(_paste(_background(), template)) is (
            PortalProbeOutcome.CONFIRMED
        )


def test_failing_scorer_and_bad_thresholds_stay_fail_safe():
    def broken(frame_image: object) -> float:
        raise RuntimeError("no signal")

    probe = PortalNotificationProbe(scorer=broken)
    assert (
        probe.probe(np.zeros((800, 1600, 3), dtype=np.uint8))
        is PortalProbeOutcome.INCONCLUSIVE
    )
    with pytest.raises(ValueError):
        PortalNotificationProbe(confirm_threshold=0.5, absent_threshold=0.5)
