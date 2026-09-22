"""Read the five visible Monster Wave inventory-board lines, without input.

The popup landmark is already resolved by the normal MW perception pipeline.
This reader runs only for that resolved popup and emits one unconfirmed sample
per frame. A caller must obtain consecutive agreeing samples before using it.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Sequence

import cv2
import numpy as np

from bot.monster_wave_semantics import POPUP_MW_BOARD, SCREEN_MONSTER_WAVE
from bot.runtime_observer import RuntimeSnapshot
from bot.state import ResolutionStatus


# Fixed row order and narrow, normalized ROIs acquired on the 2026-09-22 board.
# Bronze uses a tighter ROI to exclude the preceding Hero line's trailing glyph.
BOARD_ROWS = (
    ("brawlers_badges", "Brawler's Badges", (0.39, 0.378, 0.61, 0.405)),
    ("weapon_material", "Weapon Material", (0.39, 0.403, 0.61, 0.430)),
    ("hero_weapon_material", "Hero Weapon Material", (0.39, 0.428, 0.61, 0.455)),
    ("bronze_key", "Bronze Key", (0.42, 0.453, 0.58, 0.480)),
    ("silver_key", "Silver Key", (0.39, 0.478, 0.61, 0.505)),
)
_LINE = re.compile(r"^\((\d+)/(\d+)\)\s+(.+)$")


@dataclass(frozen=True)
class MonsterWaveBoardRow:
    item_id: str
    balance: int
    displayed_limit: int

    def __post_init__(self) -> None:
        if self.item_id not in {row[0] for row in BOARD_ROWS}:
            raise ValueError("unknown board row")
        for name in ("balance", "displayed_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} must be an integer")
        if self.balance < 0 or self.displayed_limit <= 0:
            raise ValueError("board balance/limit out of range")


@dataclass(frozen=True)
class MonsterWaveBoardSample:
    rows: tuple[MonsterWaveBoardRow, ...]
    sequence: int
    observed_at: float
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if tuple(row.item_id for row in self.rows) != tuple(row[0] for row in BOARD_ROWS):
            raise ValueError("board rows must have the acquired order and identity")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, Integral) or self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if (isinstance(self.observed_at, bool) or not isinstance(self.observed_at, Real)
                or not math.isfinite(float(self.observed_at)) or self.observed_at < 0):
            raise ValueError("observed_at must be non-negative")
        if len(self.evidence) != len(BOARD_ROWS):
            raise ValueError("evidence must include every row")


@dataclass(frozen=True)
class MonsterWaveBoardFact:
    rows: tuple[MonsterWaveBoardRow, ...]
    sequence: int
    observed_at: float
    sample_sequences: tuple[int, ...]
    evidence: tuple[str, ...]
    context: str = SCREEN_MONSTER_WAVE
    popup: str = POPUP_MW_BOARD

    def __post_init__(self) -> None:
        MonsterWaveBoardSample(self.rows, self.sequence, self.observed_at, self.evidence[-5:])
        if len(self.sample_sequences) < 2 or self.sample_sequences[-1] != self.sequence:
            raise ValueError("board fact needs at least two samples ending at sequence")
        if (any(isinstance(value, bool) or not isinstance(value, Integral) or value < 0
                for value in self.sample_sequences)
                or len(self.evidence) != len(self.sample_sequences) * len(BOARD_ROWS)):
            raise ValueError("board fact sample evidence is incomplete")
        if any(a >= b for a, b in zip(self.sample_sequences, self.sample_sequences[1:])):
            raise ValueError("sample sequences must increase")


def parse_board_line(text: str, expected_id: str) -> MonsterWaveBoardRow | None:
    """Accept only the exact acquired title and an explicit displayed pair."""

    title = next((title for item_id, title, _ in BOARD_ROWS if item_id == expected_id), None)
    if title is None or not isinstance(text, str):
        return None
    match = _LINE.fullmatch(" ".join(text.split()))
    if match is None or match.group(3).casefold() != title.casefold():
        return None
    balance, limit = int(match.group(1)), int(match.group(2))
    if limit <= 0:
        return None
    return MonsterWaveBoardRow(expected_id, balance, limit)


class MonsterWaveBoardReader:
    def __init__(self, engine) -> None:
        if not callable(getattr(engine, "recognize", None)):
            raise ValueError("engine must provide recognize(image)")
        self.engine = engine

    def read_sample(self, snapshot: RuntimeSnapshot) -> MonsterWaveBoardSample | None:
        state = snapshot.state
        if (state.status is not ResolutionStatus.RESOLVED
                or state.base_context != SCREEN_MONSTER_WAVE
                or state.overlays != (POPUP_MW_BOARD,)):
            return None
        frame = snapshot.frame.image
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be BGR")
        height, width = frame.shape[:2]
        rows, evidence = [], []
        for item_id, _title, (x1, y1, x2, y2) in BOARD_ROWS:
            crop = frame[round(y1 * height):round(y2 * height),
                         round(x1 * width):round(x2 * width)]
            if crop.size == 0:
                return None
            prepared = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            result = self.engine.recognize(prepared)
            if result.confidence < 0.90:
                return None
            row = parse_board_line(result.text, item_id)
            if row is None:
                return None
            rows.append(row)
            evidence.append(f"{item_id}:{result.text}")
        return MonsterWaveBoardSample(tuple(rows), snapshot.sequence, snapshot.timestamp, tuple(evidence))


def consensus_board_samples(
    samples: Sequence[MonsterWaveBoardSample], *, after_sequence: int,
) -> MonsterWaveBoardFact | None:
    """Require two adjacent, matching popup frames after the caller's barrier."""

    if isinstance(after_sequence, bool) or not isinstance(after_sequence, Integral) or after_sequence < 0:
        raise ValueError("after_sequence must be non-negative")
    items = tuple(samples)
    if len(items) < 2 or len(items) > 4 or not all(isinstance(item, MonsterWaveBoardSample) for item in items):
        return None
    if any(item.sequence <= after_sequence for item in items):
        return None
    if any(a.sequence >= b.sequence or a.observed_at >= b.observed_at
           for a, b in zip(items, items[1:])):
        return None
    if items[-1].observed_at - items[0].observed_at > 1.0:
        return None
    if any(item.rows != items[0].rows for item in items[1:]):
        return None
    return MonsterWaveBoardFact(
        rows=items[-1].rows,
        sequence=items[-1].sequence,
        observed_at=items[-1].observed_at,
        sample_sequences=tuple(item.sequence for item in items),
        evidence=tuple(text for item in items for text in item.evidence),
        context=SCREEN_MONSTER_WAVE,
        popup=POPUP_MW_BOARD,
    )
