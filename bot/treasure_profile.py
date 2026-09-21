"""HIL-measured Treasure geometry (Treasure domain, no routing).

Fresh HIL E 2026-09-17, 2712x1220 (``artifacts/hil_treasure_a/``):

- entry: Lobby Treasure tile gold centroid (0.721, 0.892),
  ``artifacts/action-targets/lobby.png`` 2712x1224 (gold mask bbox
  x 0.685-0.755 / y 0.84-0.965, n=5350). Consistent with legacy
  ``treasure`` (0.722, 0.9167) and Astra ``OPEN_TREASURE``
  (0.720, 0.915), but remeasured here, never copied.
- gold chest: 3rd tile interior (0.636, 0.380), tile bbox
  x 0.574-0.698 / y 0.27-0.54 from T0 divider scan; Astra
  ``GOLD_CHEST`` (0.658, 0.379) lies in the same tile.
- single: (0.618, 0.548), HIL B2 PASS (1 tap authorized,
  1677x669, dorado 354 -> 353, cero premium, sin retry).
- repeat: ``10(Open)`` label centroid (0.693, 0.540) from the B1
  popup (n=1607 yellow-mask px). Geometrically calibrated from the
  same popup as the validated single control; the tap itself is
  HIL_NOT_EXERCISED (gastar 10 keys requiere aprobacion no pedida).
- dismiss: (0.08, 0.65), safe lateral point in the left dark
  corridor, recalibrated 2026-09-18 from the live Karat reward
  overlay ``artifacts/hil_e2_fastdrain/20260918T204217/dry_000.png``
  (2712x1224): bottom bar bbox x 0.148-0.568 / y 0.700-0.933,
  reward grid x >= ~0.20, center chest x ~0.55-0.75. The point
  sits left of the bar, above it and left of the grid, over
  background pixels in both overlay (BGR 14,11,2) and clean grid
  (BGR 56,41,13) states. Safe region x 0.03-0.13 / y 0.58-0.68
  overlaps no button bbox. The earlier (0.85, 0.50) was a
  user visual approximation, never validated: it lies inside the
  reward grid and the productive path proved ``dismiss_no_effect``
  there (HIL 20260918T204152). It is not executable, nor is the
  older (0.9, 0.64) which had no effect.
- back: (0.802, 0.073) Astra ``BACK``; teal glyph bbox
  x 0.780-0.829 / y 0.040-0.104 measured on T0, plate to ~0.872.
  HIL-verify in Smoke A.

All points are normalized [0, 1] derived from ``frame.shape``;
portable across 2712x1220/1224 (y within 0.004).
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real


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
class TreasureProfile:
    """Safe interior points + bboxes for the Treasure Gold layout.

    Points must lie strictly inside their bbox with margin; bboxes
    that share a surface must not overlap. No navigation, no policy,
    no ADB: pure geometry. ``single_exercised`` records the HIL tap
    proof; ``repeat_exercised`` stays False until a live 10-open.
    """

    entry_point: tuple[float, float]
    gold_chest_point: tuple[float, float]
    single_point: tuple[float, float]
    repeat_point: tuple[float, float]
    dismiss_point: tuple[float, float]
    back_point: tuple[float, float]
    entry_bbox: tuple[float, float, float, float]
    gold_chest_bbox: tuple[float, float, float, float]
    single_bbox: tuple[float, float, float, float]
    repeat_bbox: tuple[float, float, float, float]
    back_bbox: tuple[float, float, float, float]
    frame_width: int = 2712
    frame_height: int = 1220
    single_exercised: bool = True
    repeat_exercised: bool = False

    def __post_init__(self) -> None:
        for name in (
            "entry_point",
            "gold_chest_point",
            "single_point",
            "repeat_point",
            "dismiss_point",
            "back_point",
        ):
            object.__setattr__(
                self, name, _require_point(getattr(self, name), name)
            )
        for name in (
            "entry_bbox",
            "gold_chest_bbox",
            "single_bbox",
            "repeat_bbox",
            "back_bbox",
        ):
            object.__setattr__(
                self, name, _require_bbox(getattr(self, name), name)
            )
        for name in ("frame_width", "frame_height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if int(value) <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, int(value))
        for point_name, bbox_name in (
            ("entry_point", "entry_bbox"),
            ("gold_chest_point", "gold_chest_bbox"),
            ("single_point", "single_bbox"),
            ("repeat_point", "repeat_bbox"),
            ("back_point", "back_bbox"),
        ):
            x, y = getattr(self, point_name)
            x0, y0, x1, y1 = getattr(self, bbox_name)
            if not (x0 < x < x1 and y0 < y < y1):
                raise ValueError(f"{point_name} must lie inside {bbox_name}")
        boxes = (self.single_bbox, self.repeat_bbox)
        for index, first in enumerate(boxes):
            for second in boxes[index + 1 :]:
                if not (
                    first[2] <= second[0]
                    or second[2] <= first[0]
                    or first[3] <= second[1]
                    or second[3] <= first[1]
                ):
                    raise ValueError("popup bboxes must not overlap")


TREASURE_PROFILE = TreasureProfile(
    entry_point=(0.721, 0.892),
    gold_chest_point=(0.636, 0.380),
    single_point=(0.618, 0.548),
    repeat_point=(0.693, 0.540),
    dismiss_point=(0.08, 0.65),
    back_point=(0.802, 0.073),
    entry_bbox=(0.685, 0.84, 0.755, 0.965),
    gold_chest_bbox=(0.574, 0.27, 0.698, 0.54),
    single_bbox=(0.565, 0.395, 0.645, 0.565),
    repeat_bbox=(0.650, 0.395, 0.730, 0.565),
    back_bbox=(0.790, 0.025, 0.872, 0.108),
)


def open_targets(profile: TreasureProfile = TREASURE_PROFILE):
    """Build caller-supplied ``TreasureOpenTargets`` from a profile.

    Import is local so this geometry module stays free of capability
    policy; ``bot.treasure_keys`` itself never hardcodes a coordinate.
    """

    from bot.treasure_keys import TreasureOpenTargets

    if not isinstance(profile, TreasureProfile):
        raise ValueError("profile must be TreasureProfile")
    return TreasureOpenTargets(
        open_single_point=profile.single_point,
        open_repeat_point=profile.repeat_point,
    )


__all__ = (
    "TREASURE_PROFILE",
    "TreasureProfile",
    "open_targets",
)
