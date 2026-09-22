"""Pure, descriptive Monster Wave snapshot from one fresh resolved context."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral, Real

from bot.catalog import (
    POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL,
    SEMANTIC_CONFIDENCE_THRESHOLD,
)
from bot.monster_wave_activity import SkipState, skip_state
from bot.monster_wave_board_reader import MonsterWaveBoardFact, MonsterWaveBoardRow
from bot.monster_wave_semantics import (
    MW_BOARD, MW_CONTROLS_CLEAR, MW_MAX, MW_PURCHASE_FULL, MW_SKIP_START,
    MW_TOOLTIP, POPUP_MW_BOARD, POPUP_MW_CLEAR, POPUP_MW_INSUFFICIENT,
    POPUP_MW_PURCHASE, POPUP_MW_RANKING, POPUP_MW_WEEKLY,
    OVERLAY_MW_TOOLTIP, SCREEN_MONSTER_WAVE,
)
from bot.ocr_extractors import RESOURCE_SAPPHIRES
from bot.runtime_facts import RuntimeFact
from bot.runtime_observer import RuntimeSnapshot
from bot.state import ResolutionStatus


class BoardPopup(str, Enum):
    ABSENT = "absent"
    PRESENT_CONTENT_UNKNOWN = "present_content_unknown"
    PRESENT_WITH_ROWS = "present_with_rows"


class Tickets(str, Enum):
    NEEDS = "needs"
    READY = "ready"
    PURCHASE_FULL = "purchase_full"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MaxState:
    selected: bool | None
    controls_clear: bool | None
    start_present: bool | None
    tooltip_present: bool | None


@dataclass(frozen=True)
class BoardEvidence:
    sequence: int
    observed_at: float
    row_sequences: tuple[int, ...] = ()
    sapphire_sequences: tuple[int, ...] = ()


@dataclass(frozen=True)
class MonsterWaveBoardSnapshot:
    skip_state: SkipState | None
    tickets: Tickets
    sapphires_daily: int | None
    max_state: MaxState
    board_popup: BoardPopup
    blockers: tuple[str, ...]
    resource_rows: tuple[MonsterWaveBoardRow, ...]
    evidence: BoardEvidence
    gold_key_capacity: str = "NOT_OBSERVABLE"

    def __post_init__(self) -> None:
        if self.gold_key_capacity != "NOT_OBSERVABLE":
            raise ValueError("Gold-key capacity is not observable on the MW board")


_OVERLAYS = frozenset({
    POPUP_MW_BOARD, POPUP_MW_CLEAR, POPUP_MW_INSUFFICIENT,
    POPUP_MW_PURCHASE, POPUP_MW_RANKING, POPUP_MW_WEEKLY,
    OVERLAY_MW_TOOLTIP, POPUP_EQUIPMENT_INVENTORY_FULL,
    POPUP_SOCKET_INVENTORY_FULL,
})
_BLOCKERS = frozenset({
    POPUP_MW_INSUFFICIENT, POPUP_EQUIPMENT_INVENTORY_FULL,
    POPUP_SOCKET_INVENTORY_FULL,
})


def build_monster_wave_board_snapshot(
    snapshot: RuntimeSnapshot,
    *,
    after_sequence: int,
    now: float,
    board_fact: MonsterWaveBoardFact | None = None,
    sapphires_fact: RuntimeFact[int] | None = None,
    max_age_s: float = 2.0,
) -> MonsterWaveBoardSnapshot | None:
    """Describe only facts proven in this context after the caller's barrier.

    ``after_sequence`` is the last known board transition/navigation frame.
    Facts from that frame or earlier cannot cross into this description.
    ``now`` uses the same monotonic clock as the capture timestamp.
    """

    if isinstance(after_sequence, bool) or not isinstance(after_sequence, Integral) or after_sequence < 0:
        raise ValueError("after_sequence must be non-negative")
    if not _time(now) or not _time(max_age_s) or max_age_s < 0:
        raise ValueError("now and max_age_s must be finite non-negative times")
    if not isinstance(snapshot, RuntimeSnapshot):
        raise ValueError("snapshot must be RuntimeSnapshot")
    state = snapshot.state
    if (snapshot.sequence <= after_sequence
            or snapshot.timestamp > now
            or now - snapshot.timestamp > max_age_s
            or state.status is not ResolutionStatus.RESOLVED
            or state.base_context != SCREEN_MONSTER_WAVE
            or len(state.overlays) > 1
            or any(overlay not in _OVERLAYS for overlay in state.overlays)):
        return None
    visible = {observation.name for observation in snapshot.observations.observations
               if observation.confidence >= SEMANTIC_CONFIDENCE_THRESHOLD}
    popup_present = state.overlays == (POPUP_MW_BOARD,)
    if (MW_BOARD in visible) != popup_present:
        return None
    skip = skip_state(snapshot)
    if not state.overlays and skip is None:
        return None
    if popup_present:
        if board_fact is None:
            popup = BoardPopup.PRESENT_CONTENT_UNKNOWN
            rows = ()
            row_sequences = ()
        elif (board_fact.sequence != snapshot.sequence
              or board_fact.context != SCREEN_MONSTER_WAVE
              or board_fact.popup != POPUP_MW_BOARD
              or board_fact.observed_at != snapshot.timestamp
              or board_fact.sample_sequences[0] <= after_sequence):
            return None
        else:
            popup = BoardPopup.PRESENT_WITH_ROWS
            rows = board_fact.rows
            row_sequences = board_fact.sample_sequences
    elif board_fact is not None:
        return None
    else:
        popup, rows, row_sequences = BoardPopup.ABSENT, (), ()

    if sapphires_fact is not None:
        if (state.overlays
                or sapphires_fact.name != RESOURCE_SAPPHIRES
                or sapphires_fact.context != SCREEN_MONSTER_WAVE
                or isinstance(sapphires_fact.value, bool)
                or not isinstance(sapphires_fact.value, Integral)
                or sapphires_fact.value < 0
                or sapphires_fact.sequence != snapshot.sequence
                or sapphires_fact.timestamp != snapshot.timestamp
                or sapphires_fact.evidence[0].sequence <= after_sequence):
            return None
        sapphires = int(sapphires_fact.value)
        sapphire_sequences = tuple(item.sequence for item in sapphires_fact.evidence)
    else:
        sapphires, sapphire_sequences = None, ()

    if skip is SkipState.NEEDS_TICKETS:
        tickets = Tickets.NEEDS
    elif skip is SkipState.READY:
        tickets = Tickets.READY
    elif state.overlays == (POPUP_MW_PURCHASE,) and MW_PURCHASE_FULL in visible:
        tickets = Tickets.PURCHASE_FULL
    else:
        tickets = Tickets.UNKNOWN
    return MonsterWaveBoardSnapshot(
        skip_state=skip,
        tickets=tickets,
        sapphires_daily=sapphires,
        max_state=MaxState(
            selected=True if MW_MAX in visible else None,
            controls_clear=True if MW_CONTROLS_CLEAR in visible else None,
            start_present=True if MW_SKIP_START in visible else None,
            tooltip_present=True if MW_TOOLTIP in visible else None,
        ),
        board_popup=popup,
        blockers=tuple(name for name in state.overlays if name in _BLOCKERS),
        resource_rows=rows,
        evidence=BoardEvidence(snapshot.sequence, snapshot.timestamp,
                               row_sequences, sapphire_sequences),
    )


def _time(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, Real)
            and math.isfinite(float(value)) and float(value) >= 0.0)
