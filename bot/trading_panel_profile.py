"""HIL-calibrated Item Trade panel geometry (Trading domain, no routing).

Fresh HIL C5 2026-09-17, 2712x1224 (``artifacts/hil_c5/``), consistent
with HIL C4 2712x1220 (``artifacts/hil_c4a/`` + ``hil_c4b/``):

- popup Item Trade x 0.275-0.724 / y 0.208-0.849 (prior C4, stable);
- No (teal, cancel) bbox 0.2961-0.4148 / 0.7533-0.8080, point
  (0.3555, 0.7806): 2/2 PASS, closes to stable Trading, 265/40 intact;
- Trade (red, confirm) bbox 0.4336-0.5531 / 0.7467-0.8170, point
  (0.4934, 0.7819): SUCCESS 265 -> 225 EXACT 1, single tap, zero retry;
- >> (gold chevrons, max) bbox 0.6619-0.7139 / 0.7729-0.8309, point
  (0.699, 0.802): 1/20 -> 6/20 causal, then cancelled with No, zero spend.

Prior HIL B NO_EFFECT cause: confirm tap (0.43, 0.79) fell ~10px left
of the Trade interior (background BGR 26,59,93); real center is 171px
to the right. Class A (tap not registered), not an executed trade
without effect. Prior ``btns.txt`` No (0.293, 0.778) was the left edge
and >> (0.664, 0.880) pointed below the panel.

Row tap x = 0.75 (Trade column, HIL A PASS + C5 SUCCESS reuse at
(0.75, 0.4357) -> panel open) belongs to the row consumer, never to
the panel or to ``bot.trading_operation`` (which takes all points
caller-supplied via ``TradePanelTargets``). Panel points are normalized
[0, 1] derived from ``frame.shape``; portable across 2712x1220/1224
(x identical, y within 0.003).
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real


# Row domain (Trade column), kept separate from panel hitboxes.
ROW_TAP_X = 0.75


def _require_unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return result


def _require_point(value: object, name: str) -> tuple[float, float]:
    try:
        first, second = value  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an (x, y) pair") from error
    return (_require_unit(first, name), _require_unit(second, name))


def _require_bbox(value: object, name: str) -> tuple[float, float, float, float]:
    try:
        x0, y0, x1, y1 = value  # type: ignore[misc]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be (x0, y0, x1, y1)") from error
    x0 = _require_unit(x0, name)
    y0 = _require_unit(y0, name)
    x1 = _require_unit(x1, name)
    y1 = _require_unit(y1, name)
    if not (x0 < x1 and y0 < y1):
        raise ValueError(f"{name} must satisfy x0 < x1 and y0 < y1")
    return (x0, y0, x1, y1)


@dataclass(frozen=True)
class TradingPanelProfile:
    """Safe interior points + bboxes for one Item Trade layout.

    Points must lie strictly inside their bbox with margin; bboxes must
    not overlap. No navigation, no policy, no ADB: pure geometry.
    """

    confirm_point: tuple[float, float]
    cancel_point: tuple[float, float]
    max_point: tuple[float, float]
    confirm_bbox: tuple[float, float, float, float]
    cancel_bbox: tuple[float, float, float, float]
    max_bbox: tuple[float, float, float, float]
    frame_width: int = 2712
    frame_height: int = 1224

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "confirm_point",
            _require_point(self.confirm_point, "confirm_point"),
        )
        object.__setattr__(
            self, "cancel_point",
            _require_point(self.cancel_point, "cancel_point"),
        )
        object.__setattr__(
            self, "max_point",
            _require_point(self.max_point, "max_point"),
        )
        object.__setattr__(
            self, "confirm_bbox",
            _require_bbox(self.confirm_bbox, "confirm_bbox"),
        )
        object.__setattr__(
            self, "cancel_bbox",
            _require_bbox(self.cancel_bbox, "cancel_bbox"),
        )
        object.__setattr__(
            self, "max_bbox",
            _require_bbox(self.max_bbox, "max_bbox"),
        )
        for name in ("frame_width", "frame_height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if int(value) <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, int(value))
        for point_name, bbox_name in (
            ("confirm_point", "confirm_bbox"),
            ("cancel_point", "cancel_bbox"),
            ("max_point", "max_bbox"),
        ):
            x, y = getattr(self, point_name)
            x0, y0, x1, y1 = getattr(self, bbox_name)
            if not (x0 < x < x1 and y0 < y < y1):
                raise ValueError(f"{point_name} must lie inside {bbox_name}")
        boxes = (
            self.confirm_bbox,
            self.cancel_bbox,
            self.max_bbox,
        )
        for index, first in enumerate(boxes):
            for second in boxes[index + 1:]:
                if not (
                    first[2] <= second[0]
                    or second[2] <= first[0]
                    or first[3] <= second[1]
                    or second[3] <= first[1]
                ):
                    raise ValueError("panel bboxes must not overlap")


TRADING_PANEL_PROFILE = TradingPanelProfile(
    confirm_point=(0.4934, 0.7819),
    cancel_point=(0.3555, 0.7806),
    max_point=(0.699, 0.802),
    confirm_bbox=(0.4336, 0.7467, 0.5531, 0.8170),
    cancel_bbox=(0.2961, 0.7533, 0.4148, 0.8080),
    max_bbox=(0.6619, 0.7729, 0.7139, 0.8309),
)


def panel_targets(profile: TradingPanelProfile = TRADING_PANEL_PROFILE):
    """Build caller-supplied ``TradePanelTargets`` from a profile.

    Import is local so this geometry module stays free of operation
    policy; the operation module itself never hardcodes a coordinate.
    """
    from bot.trading_operation import TradePanelTargets

    if not isinstance(profile, TradingPanelProfile):
        raise ValueError("profile must be TradingPanelProfile")
    return TradePanelTargets(
        max_point=profile.max_point,
        confirm_point=profile.confirm_point,
        cancel_point=profile.cancel_point,
    )


__all__ = (
    "ROW_TAP_X",
    "TRADING_PANEL_PROFILE",
    "TradingPanelProfile",
    "panel_targets",
)
