"""Trading adapter from material rows to the directed-scroll primitive.

Trading-owned policy lives here, never in ``bot.directed_list_scroll``:

- Avatars & Keys never scrolls; requesting it is a caller bug and fails
  loudly without input.
- The scroll helper runs only after positively demonstrated materials
  content (see ``bot.trading_center.is_materials_content_ready``); the
  ``content_ready`` flag carries that proof into this adapter.
- Partial rows are never actionable: taps on partial rows are vetoed by
  architecture, so a partial target short-circuits before any gesture and a
  READY claim is re-verified against a fresh complete row before return.
  That re-verification is Trading-domain policy, which is why it lives in
  this adapter instead of the transversal helper.

The ordered catalog and the physical profile are caller data verified by
HIL, not constants of this module. Row identity (mapping observed rows to
opaque catalog ids, including any duplicate-title disambiguation) is owned
by the future row reader; this adapter only converts complete rows given
top to bottom into ``ViewportReading`` values.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from numbers import Real

from bot.directed_list_scroll import (
    DirectedScrollOutcome,
    DirectedScrollResult,
    KnownListScrollProfile,
    PlannedGesture,
    ViewportReading,
    scroll_to_target,
)

KEYS_SECTION = "keys"
MATERIALS_SECTION = "materials"


# General-tab catalog top to bottom, HIL ground truth (single session,
# 2712x1220, human-confirmed order). Ids name catalog ROWS (offer slots):
# quantities fold into row identity where the UI lists one base item twice
# (lapiz_400 vs lapiz_5). Counts and costs are future reader scope, not here.
MATERIAL_CATALOG: tuple[str, ...] = (
    "super_awakening_stone",
    "mao_coins",
    "light_essence",
    "dark_essence",
    "nature_essence",
    "lapiz_400",
    "stamina_100",
    "gold_pouch_10m",
    "gold_10m",
    "sapphire_5",
    "brawlers_badge",
    "lapiz_5",
    "ring_enhance",
    "melee_badge",
    "accessory_crafting_material",
    "weapon_crafting_material",
    "hero_weapon_crafting_material",
    "hero_armor_crafting_material",
    "hero_accessory_crafting_material",
    "r_ticket",
    "k_coin",
    "guild_commodity",
)


# Calibrated General-list geometry (same HIL session): pitch 0.1418 stable
# across 8 captures and both tabs; 4 complete rows; lane x=0.33 over static
# item text (no controls/slots); gesture zone inside list bounds.
# Tolerance covers divider-detection jitter at a fixed list position.
TRADING_MATERIALS_SCROLL_PROFILE = KnownListScrollProfile(
    row_pitch=0.1418,
    visible_rows=4,
    lane_x=0.33,
    top_y=0.36,
    bottom_y=0.94,
    overlap_factor=0.95,
    row_tolerance=0.015,
    consensus_required=2,
    consensus_max_samples=4,
)


@dataclass(frozen=True)
class MaterialRow:
    """One observed material row, top to bottom as displayed by the caller."""

    row_id: str
    center_y: float
    complete: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.row_id, str) or not self.row_id:
            raise ValueError("row_id must be a non-empty string")
        if isinstance(self.center_y, bool) or not isinstance(self.center_y, Real):
            raise ValueError("center_y must be a real number in [0, 1]")
        center_y = float(self.center_y)
        if not 0.0 <= center_y <= 1.0:
            raise ValueError("center_y must be a real number in [0, 1]")
        object.__setattr__(self, "center_y", center_y)
        if not isinstance(self.complete, bool):
            raise ValueError("complete must be bool")


@dataclass(frozen=True)
class MaterialViewport:
    """One fresh row observation owned and produced by the caller."""

    rows: tuple[MaterialRow, ...]
    sequence: int
    readable: bool = True
    guard_ok: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        for row in self.rows:
            if not isinstance(row, MaterialRow):
                raise ValueError("rows must contain MaterialRow values")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValueError("sequence must be an integer")
        if not isinstance(self.readable, bool):
            raise ValueError("readable must be bool")
        if not isinstance(self.guard_ok, bool):
            raise ValueError("guard_ok must be bool")


def viewport_to_reading(viewport: MaterialViewport, *, target: str) -> ViewportReading:
    """Convert complete rows to a ``ViewportReading`` for the helper.

    Partial rows are excluded: they are never actionable and must not
    prove progress or stability. Pure: performs no IO.
    """
    if not isinstance(viewport, MaterialViewport):
        raise ValueError("viewport must be MaterialViewport")
    if not isinstance(target, str) or not target:
        raise ValueError("target must be a non-empty string")
    complete = [row for row in viewport.rows if row.complete]
    target_y: float | None = None
    for row in complete:
        if row.row_id == target:
            target_y = row.center_y
            break
    return ViewportReading(
        visible_ids=tuple(row.row_id for row in complete),
        sequence=viewport.sequence,
        target_row_y=target_y,
        readable=viewport.readable,
        guard_ok=viewport.guard_ok,
    )


def locate_material_target(
    *,
    catalog: Sequence[Hashable],
    target: str,
    profile: KnownListScrollProfile,
    observe_viewport: Callable[[], MaterialViewport],
    emit: Callable[[PlannedGesture], None],
    max_gestures: int,
    section: str = MATERIALS_SECTION,
    content_ready: bool,
) -> DirectedScrollResult:
    """Drive the directed-scroll helper toward a material target.

    Fails loudly (no input) when the section forbids scroll or materials
    content was not positively demonstrated. A partial target in the first
    observation short-circuits without input. A READY claim is confirmed
    against one fresh complete row for the same target within tolerance;
    otherwise it degrades to ``NO_PROGRESS`` without further input. Never
    taps the target row.
    """
    if section == KEYS_SECTION:
        raise ValueError("keys_no_scroll")
    if section != MATERIALS_SECTION:
        raise ValueError("section must be materials")
    if content_ready is not True:
        raise ValueError("materials_not_ready")
    if not isinstance(profile, KnownListScrollProfile):
        raise ValueError("profile must be KnownListScrollProfile")
    if not callable(observe_viewport) or not callable(emit):
        raise ValueError("observe_viewport and emit must be callable")

    first = observe_viewport()
    _check_viewport(first)
    if any(row.row_id == target and not row.complete for row in first.rows):
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.NO_PROGRESS,
            last_sequence=first.sequence,
            reason="target_row_partial",
        )
    pending = [viewport_to_reading(first, target=target)]

    def _observe() -> ViewportReading:
        if pending:
            return pending.pop()
        viewport = observe_viewport()
        _check_viewport(viewport)
        return viewport_to_reading(viewport, target=target)

    result = scroll_to_target(
        catalog=catalog,
        target=target,
        profile=profile,
        observe=_observe,
        emit=emit,
        max_gestures=max_gestures,
    )
    if result.outcome is not DirectedScrollOutcome.TARGET_READY:
        return result
    return _confirm_ready(
        result=result,
        target=target,
        profile=profile,
        observe_viewport=observe_viewport,
    )


def _confirm_ready(
    *,
    result: DirectedScrollResult,
    target: str,
    profile: KnownListScrollProfile,
    observe_viewport: Callable[[], MaterialViewport],
) -> DirectedScrollResult:
    confirm = observe_viewport()
    _check_viewport(confirm)
    if not confirm.guard_ok:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.GUARD_LOST,
            gestures=result.gestures,
            last_sequence=confirm.sequence,
            reason="guard_lost",
        )
    if not confirm.readable:
        return DirectedScrollResult(
            outcome=DirectedScrollOutcome.UNREADABLE,
            gestures=result.gestures,
            last_sequence=confirm.sequence,
            reason="viewport_unreadable",
        )
    for row in confirm.rows:
        if (
            row.row_id == target
            and row.complete
            and result.stable_row_y is not None
            and abs(row.center_y - result.stable_row_y) <= profile.row_tolerance
        ):
            return result
    return DirectedScrollResult(
        outcome=DirectedScrollOutcome.NO_PROGRESS,
        gestures=result.gestures,
        last_sequence=confirm.sequence,
        reason="target_row_partial",
    )


def _check_viewport(viewport: object) -> None:
    if not isinstance(viewport, MaterialViewport):
        raise ValueError("observe_viewport must return MaterialViewport")


__all__ = (
    "KEYS_SECTION",
    "MATERIALS_SECTION",
    "MATERIAL_CATALOG",
    "TRADING_MATERIALS_SCROLL_PROFILE",
    "MaterialRow",
    "MaterialViewport",
    "locate_material_target",
    "viewport_to_reading",
)
