"""HIL-verified Trading navigation geometry (no trade policy).

Acquired 2026-09-21 on 2712x1220 under
``artifacts/hil_trading_navigation/20260921T211707``:

- Lobby -> Trading: direct visible ``Trading Center`` control, one tap at
  (662, 1089), followed by fresh Trading/General.
- Trading -> Avatars & Keys: tab center, one tap at (1317, 293) =
  the active Keys tab and four Keys rows.
- Trading -> Lobby: the Trading-specific red X (not a generic Back), one tap
  at (2108, 170), followed by fresh clean Lobby.

Every tap was explicitly authorized, single-attempt, and human-confirmed.
The conservative bboxes are measured from the same current screenshots and
only document the visible controls containing the proven interior points.
All geometry is normalized from ``frame.shape`` by ``ActionExecutor``.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real


def _unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return result


def _point(value: object, name: str) -> tuple[float, float]:
    try:
        x, y = value  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an (x, y) pair") from error
    return (_unit(x, name), _unit(y, name))


def _bbox(value: object, name: str) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = value  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be (x0, y0, x1, y1)") from error
    result = tuple(_unit(item, name) for item in (x0, y0, x1, y1))
    if not (result[0] < result[2] and result[1] < result[3]):
        raise ValueError(f"{name} must satisfy x0 < x1 and y0 < y1")
    return result  # type: ignore[return-value]


@dataclass(frozen=True)
class TradingNavigationProfile:
    """Current exercised Trading navigation and tab controls."""

    entry_point: tuple[float, float]
    avatar_keys_point: tuple[float, float]
    general_point: tuple[float, float]
    close_point: tuple[float, float]
    entry_bbox: tuple[float, float, float, float]
    avatar_keys_bbox: tuple[float, float, float, float]
    general_bbox: tuple[float, float, float, float]
    close_bbox: tuple[float, float, float, float]
    frame_width: int = 2712
    frame_height: int = 1220

    def __post_init__(self) -> None:
        for name in (
            "entry_point", "avatar_keys_point", "general_point", "close_point"
        ):
            object.__setattr__(self, name, _point(getattr(self, name), name))
        for name in (
            "entry_bbox", "avatar_keys_bbox", "general_bbox", "close_bbox"
        ):
            object.__setattr__(self, name, _bbox(getattr(self, name), name))
        for name in ("frame_width", "frame_height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for point_name, bbox_name in (
            ("entry_point", "entry_bbox"),
            ("avatar_keys_point", "avatar_keys_bbox"),
            ("general_point", "general_bbox"),
            ("close_point", "close_bbox"),
        ):
            x, y = getattr(self, point_name)
            x0, y0, x1, y1 = getattr(self, bbox_name)
            if not (x0 < x < x1 and y0 < y < y1):
                raise ValueError(f"{point_name} must lie inside {bbox_name}")


TRADING_NAVIGATION_PROFILE = TradingNavigationProfile(
    # Pixel centers preserve the exact exercised integer targets after
    # ActionExecutor's normalized -> pixel floor conversion.
    entry_point=(0.244284661, 0.893032787),
    avatar_keys_point=(0.485803835, 0.240573770),
    # HIL J 2026-09-22: Keys -> General produced fresh General/material rows.
    # The point and bbox promote the already-captured current control.
    general_point=(0.2924, 0.2418),
    close_point=(0.777470501, 0.139754098),
    entry_bbox=(0.205, 0.820, 0.285, 0.975),
    avatar_keys_bbox=(0.435, 0.150, 0.535, 0.285),
    general_bbox=(0.2356, 0.1928, 0.3333, 0.2859),
    close_bbox=(0.750, 0.070, 0.805, 0.190),
)


__all__ = ("TRADING_NAVIGATION_PROFILE", "TradingNavigationProfile")
