"""Reliable reads of one visible Trading row: identity, have and need.

Consumer of ``bot.directed_list_scroll`` evidence (catalog, section,
stable row position): given a target row already located, this module
proves what the row shows before anyone may act on it. It never taps,
trades, plans or decides anything economic.

Pair reading is detection-assisted, not ROI-blind: digit glyphs with
dark outlines vote a dominant baseline, the leftmost in-column group
forms the pair box (plus a vertically overlapping continuation line),
and the parse must survive a margin perturbation unchanged. Title
matching is prefix-anchored first, with a tightly bounded fuzzy fallback
whose cross-row confusion is guarded by a pairwise catalog test.

Gold Key capacity is NOT OBSERVABLE anywhere in Trading: no reader
reports it and no fact contains it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import cv2
import numpy as np

from bot.directed_list_scroll import KnownListScrollProfile
from bot.trading_materials_scroll import TRADING_MATERIALS_SCROLL_PROFILE

MATERIALS_SECTION = "materials"
KEYS_SECTION = "keys"

# Full display titles (HIL ground truth) keyed by catalog id. Titles name
# catalog ROWS: quantities fold into row identity where the UI lists one
# base item twice (lapiz_400 vs lapiz_5).
CATALOG_TITLES: dict[str, str] = {
    "super_awakening_stone": "Super Awakening Stone 5",
    "mao_coins": "Mao Coins 2",
    "light_essence": "Light Essence 10",
    "dark_essence": "Dark Essence 10",
    "nature_essence": "Nature Essence 10",
    "lapiz_400": "Lapiz 400",
    "stamina_100": "Stamina 100",
    "gold_pouch_10m": "10M Gold Pouch 1",
    "gold_10m": "Gold 10,000,000",
    "sapphire_5": "Sapphire 5",
    "brawlers_badge": "Brawler's Badge 3",
    "lapiz_5": "Lapiz 5",
    "ring_enhance": "Ring (Enhance) 1",
    "melee_badge": "Melee Badge 2",
    "accessory_crafting_material": "Accessory Crafting Material 10",
    "weapon_crafting_material": "Weapon Crafting Material 10",
    "hero_weapon_crafting_material": "Hero Weapon Crafting Material 10",
    "hero_armor_crafting_material": "Hero Armor Crafting Material 10",
    "hero_accessory_crafting_material": "Hero Accessory Crafting Material 10",
    "r_ticket": "R-Ticket 1",
    "k_coin": "K Coin 50",
    "guild_commodity": "Guild Commodity 10",
    "silver_key": "Silver Key 2",
    "gold_key": "Gold Key 2",
    "silver_gem_key": "Silver Gem Key 2",
    "gold_gem_chest_key": "Gold Gem Chest Key 2",
}

_MATERIAL_IDS = frozenset(
    {
        "super_awakening_stone", "mao_coins", "light_essence", "dark_essence",
        "nature_essence", "lapiz_400", "stamina_100", "gold_pouch_10m",
        "gold_10m", "sapphire_5", "brawlers_badge", "lapiz_5",
        "ring_enhance", "melee_badge", "accessory_crafting_material",
        "weapon_crafting_material", "hero_weapon_crafting_material",
        "hero_armor_crafting_material", "hero_accessory_crafting_material",
        "r_ticket", "k_coin", "guild_commodity",
    }
)
_KEYS_IDS = frozenset(
    {"silver_key", "gold_key", "silver_gem_key", "gold_gem_chest_key"}
)


def section_for(item_id: str) -> str:
    """Return the owning section for a catalog id, else raise."""
    if item_id in _MATERIAL_IDS:
        return MATERIALS_SECTION
    if item_id in _KEYS_IDS:
        return KEYS_SECTION
    raise ValueError(f"unknown trading row id: {item_id!r}")


def parse_pair(text: object) -> tuple[int, int] | None:
    """Parse a strict ``have/need`` pair; commas allowed, dots rejected."""
    if not isinstance(text, str):
        return None
    import re as _re

    match = _re.fullmatch(r"\s*(\d[\d,]*)\s*/\s*(\d[\d,]*)\s*", text)
    if match is None:
        return None
    return tuple(int(part.replace(",", "")) for part in match.groups())


def normalize_title(text: object) -> str:
    """Casefold and collapse whitespace for title comparison."""
    import re as _re

    if not isinstance(text, str):
        return ""
    return _re.sub(r"\s+", " ", text.casefold().strip())


def title_matches(detected: object, expected_id: str) -> bool:
    """Check detected title text against the catalog title.

    Exact nospace-substring first; bounded fuzzy fallback (edit distance
    <= 2 with anchored prefix) for single-glyph OCR noise. Cross-row
    confusion is guarded by ``test_catalog_titles_stay_distinguishable``.
    """
    expected = CATALOG_TITLES.get(expected_id)
    if expected is None or not isinstance(detected, str):
        return False
    flat_detected = normalize_title(detected).replace(" ", "")
    flat_expected = normalize_title(expected).replace(" ", "")
    if not flat_expected:
        return False
    if flat_expected in flat_detected:
        return True
    if (
        len(flat_detected) >= 4
        and flat_detected[:4] == flat_expected[:4]
        and abs(len(flat_detected) - len(flat_expected)) <= 2
        and _edit_distance(flat_detected, flat_expected) <= 2
    ):
        return True
    return False


def _edit_distance(first: str, second: str) -> int:
    previous = list(range(len(second) + 1))
    for i, left in enumerate(first, 1):
        current = [i]
        for j, right in enumerate(second, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class RowSample:
    """One frame's parsed read of an identified row."""

    item_id: str
    section: str
    row_y: float
    have: int
    need: int
    sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id:
            raise ValueError("item_id must be a non-empty string")
        if self.section not in (MATERIALS_SECTION, KEYS_SECTION):
            raise ValueError("section must be materials or keys")
        if section_for(self.item_id) != self.section:
            raise ValueError("item_id does not belong to section")
        for name in ("have", "need", "sequence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if (
            isinstance(self.row_y, bool)
            or not isinstance(self.row_y, Real)
            or not 0.0 <= float(self.row_y) <= 1.0
        ):
            raise ValueError("row_y must be a real number in [0, 1]")


@dataclass(frozen=True)
class TradingRowFact:
    """Stable, verified description of one visible Trading row."""

    item_id: str
    section: str
    row_y: float
    have: int
    need: int
    sequence: int
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        sample = RowSample(
            item_id=self.item_id,
            section=self.section,
            row_y=self.row_y,
            have=self.have,
            need=self.need,
            sequence=self.sequence,
        )
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for item in self.evidence:
            if not isinstance(item, str):
                raise ValueError("evidence must contain strings")
        del sample


def consensus_row_samples(
    samples: Sequence[RowSample],
    *,
    required: int = 2,
    max_samples: int = 4,
    row_tolerance: float = 0.015,
) -> TradingRowFact | None:
    """Fold consecutive agreeing samples into a fact; else None.

    Agreement means same identity and section, row_y within tolerance,
    same have and need, and strictly increasing sequences. A streak break
    (shifted row, changed counts, stale sequence) restarts the streak;
    exhausting the bound without a streak reports no fact. Pure.
    """
    items = tuple(samples)
    if not all(isinstance(item, RowSample) for item in items):
        raise ValueError("samples must contain RowSample values")
    if (
        isinstance(required, bool)
        or not isinstance(required, Integral)
        or required < 1
    ):
        raise ValueError("required must be a positive integer")
    if (
        isinstance(max_samples, bool)
        or not isinstance(max_samples, Integral)
        or max_samples < required
    ):
        raise ValueError("max_samples must cover required")
    if (
        isinstance(row_tolerance, bool)
        or not isinstance(row_tolerance, Real)
        or float(row_tolerance) < 0.0
    ):
        raise ValueError("row_tolerance must be non-negative")
    streak: list[RowSample] = []
    examined = 0
    for sample in items:
        if examined >= max_samples:
            break
        examined += 1
        if (
            streak
            and (
                sample.item_id != streak[-1].item_id
                or sample.section != streak[-1].section
                or abs(sample.row_y - streak[-1].row_y) > float(row_tolerance)
                or sample.have != streak[-1].have
                or sample.need != streak[-1].need
                or sample.sequence <= streak[-1].sequence
            )
        ):
            streak = [sample]
            continue
        streak.append(sample)
        if len(streak) >= required:
            first = streak[0]
            return TradingRowFact(
                item_id=first.item_id,
                section=first.section,
                row_y=streak[-1].row_y,
                have=first.have,
                need=first.need,
                sequence=streak[-1].sequence,
                evidence=tuple(
                    f"sample@{item.sequence}:{item.have}/{item.need}"
                    for item in streak
                ),
            )
    return None


class TradingRowReader:
    """Read one located row: title identity plus have/need pair.

    The caller owns navigation (adapter consensus), framing and sampling
    bounds; the reader only parses what one frame shows at the given row
    geometry. ``engine`` is any ``recognize(image)`` OCR engine.
    """

    def __init__(
        self,
        engine,
        *,
        profile: KnownListScrollProfile = TRADING_MATERIALS_SCROLL_PROFILE,
    ) -> None:
        if not callable(getattr(engine, "recognize", None)):
            raise ValueError("engine must provide recognize(image)")
        if not isinstance(profile, KnownListScrollProfile):
            raise ValueError("profile must be KnownListScrollProfile")
        self.engine = engine
        self.profile = profile

    def read_sample(
        self,
        frame,
        sequence: int,
        *,
        item_id: str,
        section: str,
        row_top: float,
        row_y: float,
    ) -> RowSample | None:
        """Parse one frame at known row geometry; fail-closed None."""
        if section_for(item_id) != section:
            return None
        _require_frame(frame)
        sequence = _require_sequence(sequence)
        row_top = _require_unit(row_top, "row_top")
        row_y = _require_unit(row_y, "row_y")
        if not self.match_title(frame, row_top, item_id):
            return None
        pair = self.read_pair(frame, row_top)
        if pair is None:
            return None
        have, need = pair
        return RowSample(
            item_id=item_id,
            section=section,
            row_y=row_y,
            have=have,
            need=need,
            sequence=sequence,
        )

    def match_title(self, frame, row_top: float, item_id: str) -> bool:
        """Check the row's name cell against the catalog title.

        Names may wrap two lines, so two single-line strips are read and
        joined; the anchored title rule tolerates trailing lines.
        """
        if item_id not in CATALOG_TITLES:
            return False
        _require_frame(frame)
        row_top = _require_unit(row_top, "row_top")
        height, width = frame.shape[:2]
        parts = []
        for dy1, dy2 in ((0.0, 0.05), (0.045, 0.09)):
            roi = frame[int((row_top + dy1) * height):int((row_top + dy2) * height),
                        int(0.25 * width):int(0.56 * width)]
            if roi.size == 0:
                return False
            parts.append(self._recognize(roi, scale=2.0).text)
        return title_matches(" ".join(parts), item_id)

    def read_pair(self, frame, row_top: float) -> tuple[int, int] | None:
        """Read the have/need pair under the row's first cost icon.

        The pair box is segmented (dark-outlined glyphs vote a baseline)
        and the parse must survive a margin perturbation unchanged;
        anything else is UNREADABLE, never a guessed pair.
        """
        _require_frame(frame)
        row_top = _require_unit(row_top, "row_top")
        box = _localize_pair(frame, row_top)
        if box is None:
            return None
        height, width = frame.shape[:2]
        first = self._parse_box(frame, box)
        if first is None:
            return None
        x1, y1, x2, y2 = box
        wide = (
            max(0.0, x1 - 0.007),
            max(0.0, y1 - 0.006),
            min(1.0, x2 + 0.007),
            min(1.0, y2 + 0.006),
        )
        second = self._parse_box(frame, wide)
        if second != first:
            return None
        return first

    def _parse_box(self, frame, box) -> tuple[int, int] | None:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = box
        crop = frame[int(y1 * height):int(y2 * height),
                     int(x1 * width):int(x2 * width)]
        if crop.size == 0:
            return None
        result = self._recognize(crop, scale=3.0)
        if result.confidence < 0.5:
            return None
        import re as _re

        text = _re.sub(r"\s+", "", result.text)
        return parse_pair(text)

    def _recognize(self, image, scale: float):
        resized = cv2.resize(
            image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
        return self.engine.recognize(resized)


def _localize_pair(frame, row_top: float) -> tuple[float, float, float, float] | None:
    height, width = frame.shape[:2]
    y0 = int((row_top + 0.055) * height)
    y1 = int((row_top + 0.135) * height)
    strip = frame[y0:y1, int(0.48 * width):int(0.62 * width)]
    if strip.size == 0:
        return None
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, np.array([0, 0, 235]), np.array([180, 70, 255]))
    red_low = cv2.inRange(hsv, np.array([0, 120, 150]), np.array([8, 255, 255]))
    red_high = cv2.inRange(
        hsv, np.array([170, 120, 150]), np.array([180, 255, 255])
    )
    dark = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 110]))
    near_dark = cv2.dilate(dark, np.ones((5, 5), np.uint8))
    candidate = cv2.bitwise_and(
        cv2.bitwise_or(white, cv2.bitwise_or(red_low, red_high)), near_dark
    )
    contours, _ = cv2.findContours(
        candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    glyphs: list[tuple[float, float, float, float]] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        hn, wn = bh / height, bw / width
        if 0.006 <= hn <= 0.040 and 0.0015 <= wn <= 0.030:
            glyphs.append(
                (
                    0.48 + x / width,
                    row_top + 0.055 + y / height,
                    bw / width,
                    bh / height,
                )
            )
    if not glyphs:
        return None
    centers = sorted(glyph[1] + glyph[3] / 2 for glyph in glyphs)
    baseline = max(
        (sum(1 for c in centers if abs(c - c0) <= 0.008), c0) for c0 in centers
    )[1]
    line = sorted(
        (glyph for glyph in glyphs if abs(glyph[1] + glyph[3] / 2 - baseline) <= 0.008),
        key=lambda glyph: glyph[0],
    )
    chain: list[tuple[float, float, float, float]] = []
    for glyph in line:
        if not chain:
            chain.append(glyph)
        elif glyph[0] - (chain[-1][0] + chain[-1][2]) < 0.016:
            chain.append(glyph)
        else:
            break
    if len(chain) < 3:
        return None
    box = _union(chain)
    for glyph in sorted(glyphs, key=lambda glyph: glyph[0]):
        if glyph in chain:
            continue
        if (
            glyph[1] >= box[3] - 0.005
            and glyph[1] - box[3] < 0.035
            and not (glyph[0] > box[2] or box[0] > glyph[0] + glyph[2])
            and glyph[3] < 0.035
        ):
            chain.append(glyph)
    chain = sorted(chain, key=lambda glyph: (glyph[1], glyph[0]))
    if len(chain) < 3:
        return None
    box = _union(chain)
    return (
        max(0.48, box[0] - 0.004),
        max(row_top, box[1] - 0.004),
        min(0.62, box[2] + 0.004),
        min(row_top + 0.1418, box[3] + 0.004),
    )


def _union(
    glyphs: Sequence[tuple[float, float, float, float]]
) -> tuple[float, float, float, float]:
    return (
        min(glyph[0] for glyph in glyphs),
        min(glyph[1] for glyph in glyphs),
        max(glyph[0] + glyph[2] for glyph in glyphs),
        max(glyph[1] + glyph[3] for glyph in glyphs),
    )


def read_row_fact(
    frames: Sequence[tuple],
    *,
    item_id: str,
    section: str,
    row_top: float,
    row_y: float,
    reader: TradingRowReader,
    required: int = 2,
    max_samples: int = 4,
) -> TradingRowFact | None:
    """Sample bounded frames and fold them into a fact, else None.

    ``frames`` holds ``(frame, sequence)`` pairs in capture order; at most
    ``max_samples`` are consumed and no input is ever produced here. Pure
    orchestration over the injected reader.
    """
    if section_for(item_id) != section:
        return None
    if not isinstance(reader, TradingRowReader):
        raise ValueError("reader must be TradingRowReader")
    samples: list[RowSample] = []
    for frame, sequence in list(frames)[:max_samples]:
        sample = reader.read_sample(
            frame,
            sequence,
            item_id=item_id,
            section=section,
            row_top=row_top,
            row_y=row_y,
        )
        if sample is not None:
            samples.append(sample)
    return consensus_row_samples(
        samples,
        required=required,
        max_samples=max_samples,
        row_tolerance=reader.profile.row_tolerance,
    )


def _require_frame(frame) -> None:
    if (
        not isinstance(frame, np.ndarray)
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.size == 0
        or frame.dtype != np.uint8
    ):
        raise ValueError("frame must be a non-empty HxWx3 uint8 BGR image")


def _require_sequence(sequence: object) -> int:
    if isinstance(sequence, bool) or not isinstance(sequence, Integral):
        raise ValueError("sequence must be an integer")
    return int(sequence)


def _require_unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number in [0, 1]")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be a real number in [0, 1]")
    return result


__all__ = (
    "CATALOG_TITLES",
    "KEYS_SECTION",
    "MATERIALS_SECTION",
    "RowSample",
    "TradingRowFact",
    "TradingRowReader",
    "consensus_row_samples",
    "normalize_title",
    "parse_pair",
    "read_row_fact",
    "section_for",
    "title_matches",
)
