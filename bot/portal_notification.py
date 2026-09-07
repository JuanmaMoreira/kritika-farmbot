"""On-demand probe for the transversal Heaven/Hell portal notification.

The probe is deliberately *not* part of the per-frame Perception pipeline:
callers invoke it only on a fresh frame whose state already failed to satisfy
an expected condition. It never emits observations, never touches the
resolver, and never authorizes input by itself -- only an explicit CONFIRMED
outcome lets the transversal recovery tap the dismiss X.

Geometry notes (ground truth and live HIL calibration):
- fixed position below Quick Menu;
- present on Battle Mode Select, World Boss, Guild, Pets (probably others);
- absent on Lobby and Character Select;
- Heaven/Hell variants change text/color and carry transparency;
- a lateral dynamic animation must be excluded from detection.

The default scorer matches the promoted X+panel asset in the fixed search
ROI; a missing asset, a scorer failure, or a score inside the operating gap
all resolve to INCONCLUSIVE (never authorizes a tap).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Callable

from pathlib import Path

from bot.geometry import RelativeRegion, normalize_relative_region

# Fixed search ROI around the dismiss X (live-measured on 2712x1224 frames:
# X red-core center ~(0.3434, 0.1397), stable across
# Battle Mode Select and Guild). The lateral animation strip and the variable
# Heaven/Hell text stay outside the match: the anchor is the X glyph plus the
# adjacent panel chrome.
PORTAL_NOTIFICATION_ROI: RelativeRegion = (0.270, 0.085, 0.360, 0.175)

# Operating point from 11 Heaven/Hell/Guild positives (0.915-1.0),
# 6 same-ROI negatives (max 0.564) and a 603-frame curated-corpus loop
# (max 0.489 across the three wide X+panel variants).
PORTAL_NOTIFICATION_CONFIRM_THRESHOLD = 0.80
PORTAL_NOTIFICATION_ABSENT_THRESHOLD = 0.65

PORTAL_DISMISS_X_ASSET = Path(
    "assets/ui/portal/portal-dismiss-x-wide-current.png"
)
PORTAL_DISMISS_X_VARIANT_ASSETS = (
    Path("assets/ui/portal/portal-dismiss-x-wide-hell.png"),
    Path("assets/ui/portal/portal-dismiss-x-wide-guild.png"),
)


class PortalProbeOutcome(str, Enum):
    CONFIRMED = "confirmed"
    ABSENT = "absent"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class PortalNotificationProbe:
    """Pure fixed-ROI scorer for one frame image, without IO or state.

    The default scorer matches the promoted X+panel asset inside the fixed
    search ROI. When the asset is missing or unreadable the probe degrades to
    INCONCLUSIVE (never authorizes a tap).
    """

    region: RelativeRegion = PORTAL_NOTIFICATION_ROI
    confirm_threshold: float = PORTAL_NOTIFICATION_CONFIRM_THRESHOLD
    absent_threshold: float = PORTAL_NOTIFICATION_ABSENT_THRESHOLD
    scorer: Callable[[object], float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "region", normalize_relative_region(self.region)
        )
        confirm = _finite(self.confirm_threshold, "confirm_threshold")
        absent = _finite(self.absent_threshold, "absent_threshold")
        if not 0.0 <= absent < confirm <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= absent < confirm <= 1")
        object.__setattr__(self, "confirm_threshold", confirm)
        object.__setattr__(self, "absent_threshold", absent)
        scorer = self.scorer
        if scorer is None:
            scorer = _default_scorer(self.region)
        if scorer is not None and not callable(scorer):
            raise ValueError("scorer must be callable or None")
        object.__setattr__(self, "scorer", scorer)

    def probe(self, frame_image: object) -> PortalProbeOutcome:
        """Score one frame image without side effects.

        No usable scorer is always INCONCLUSIVE so no tap is ever authorized.
        A scorer failure is also INCONCLUSIVE, never a tap.
        """

        if self.scorer is None:
            return PortalProbeOutcome.INCONCLUSIVE
        try:
            score = float(self.scorer(frame_image))
        except Exception:
            return PortalProbeOutcome.INCONCLUSIVE
        if score != score or score == float("inf") or score == float("-inf"):
            return PortalProbeOutcome.INCONCLUSIVE
        if score >= self.confirm_threshold:
            return PortalProbeOutcome.CONFIRMED
        if score <= self.absent_threshold:
            return PortalProbeOutcome.ABSENT
        return PortalProbeOutcome.INCONCLUSIVE


def _default_scorer(
    region: RelativeRegion,
) -> Callable[[object], float] | None:
    """Build the asset-backed scorer, or None when no asset is available.

    Confidence is the maximum raw match over the primary rendering and its
    human-confirmed variants (Heaven + Hell), mirroring the variant mechanism
    of the per-frame detectors without joining their pipeline.
    """

    try:
        import cv2

        from bot.screen import template_match_score
    except Exception:
        return None
    root = Path(__file__).resolve().parents[1]
    templates = []
    for asset in (PORTAL_DISMISS_X_ASSET, *PORTAL_DISMISS_X_VARIANT_ASSETS):
        try:
            template = cv2.imread(
                os.fspath(root / asset), cv2.IMREAD_GRAYSCALE
            )
        except Exception:
            continue
        if template is not None and template.size > 0:
            templates.append(template)
    if not templates:
        return None

    def score(frame_image: object) -> float:
        best: float | None = None
        for template in templates:
            result = template_match_score(
                frame_image, template, region=region
            )
            if result is None:
                continue
            best = float(result) if best is None else max(best, float(result))
        if best is None:
            raise ValueError("no template fits the search region")
        return best

    return score


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a finite real number")
    return result


__all__ = (
    "PORTAL_DISMISS_X_ASSET",
    "PORTAL_DISMISS_X_VARIANT_ASSETS",
    "PORTAL_NOTIFICATION_ABSENT_THRESHOLD",
    "PORTAL_NOTIFICATION_CONFIRM_THRESHOLD",
    "PORTAL_NOTIFICATION_ROI",
    "PortalNotificationProbe",
    "PortalProbeOutcome",
)
