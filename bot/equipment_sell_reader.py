"""Local OCR reader for current Equipment Inventory sell facts.

The reader performs no sampling, navigation, policy or input.  One frame yields
at most one unconfirmed sample; callers build consensus with
``consensus_facts`` before any destructive boundary.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from bot.equipment_sell_semantics import (
    EquipmentBulkGroup,
    EquipmentGrade,
    EquipmentInventoryFact,
    EquipmentItemFact,
    EquipmentSellConfirmationFact,
    EquipmentType,
)
from bot.geometry import RelativeRegion, relative_region_to_pixels


ITEM_COUNT_ROI: RelativeRegion = (0.687, 0.234, 0.817, 0.276)
PAGE_ROI: RelativeRegion = (0.724, 0.885, 0.786, 0.937)
DETAIL_TITLE_ROI: RelativeRegion = (0.540, 0.255, 0.750, 0.310)
DETAIL_GRADE_TYPE_ROI: RelativeRegion = (0.560, 0.315, 0.750, 0.365)
CONFIRM_IDENTITY_ROI: RelativeRegion = (0.350, 0.385, 0.650, 0.425)
CONFIRM_GROUP_LINE_ROIS: tuple[RelativeRegion, ...] = (
    (0.350, 0.420, 0.650, 0.460),
    (0.360, 0.460, 0.640, 0.490),
    (0.350, 0.495, 0.650, 0.545),
)


_TYPE_NAMES = {
    "weapon": EquipmentType.WEAPON,
    "helmet": EquipmentType.HELMET,
    "chest": EquipmentType.CHEST,
    "chest armor": EquipmentType.CHEST,
    "pants": EquipmentType.PANTS,
    "gloves": EquipmentType.GLOVES,
    "boots": EquipmentType.BOOTS,
    "earring": EquipmentType.EARRING,
    "earrings": EquipmentType.EARRING,
    "necklace": EquipmentType.NECKLACE,
    "pendant": EquipmentType.NECKLACE,
    "ring": EquipmentType.RING,
}
_GRADE_NAMES = {value.value: value for value in EquipmentGrade if value is not EquipmentGrade.UNKNOWN}


def parse_item_count(text: object) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    match = re.fullmatch(
        r"\s*[^A-Za-z0-9]*\s*Item\s+Count\s*[:;]\s*"
        r"(\d[\d,]*)\s*/\s*(\d[\d,]*)\s*",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    have, capacity = (int(part.replace(",", "")) for part in match.groups())
    return (have, capacity) if capacity > 0 else None


def parse_page(text: object) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if match is None:
        return None
    page, total = (int(value) for value in match.groups())
    if page <= 0 or total <= 0 or page > total:
        return None
    return page, total


def parse_item_detail(title: object, grade_type: object) -> tuple[str, EquipmentGrade, EquipmentType, bool] | None:
    if not isinstance(title, str) or not isinstance(grade_type, str):
        return None
    normalized_title = _clean_text(title).strip("*※×»« ")
    if not normalized_title:
        return None
    match = re.fullmatch(
        r"\s*\[(Poor|Normal|Rare|Epic|Legendary|Ethereal\+?)"
        r"(?:\s+Lv\.?\s*\d+)?\]\s*([A-Za-z ]+?)\s*[.,]?\s*",
        grade_type,
        re.IGNORECASE,
    )
    if match is None:
        return None
    grade = _GRADE_NAMES.get(match.group(1).casefold())
    equipment_type = _TYPE_NAMES.get(_clean_text(match.group(2)).casefold())
    if grade is None or equipment_type is None:
        return None
    lower_title = normalized_title.casefold()
    enhance = "(enhance)" in lower_title
    # A damaged Enhance token cannot be reinterpreted as a normal item.
    if ("enhanc" in lower_title) != enhance:
        return None
    return normalized_title, grade, equipment_type, enhance


def parse_confirmation(
    identity_text: object,
    group_lines: tuple[str, ...] | list[str],
) -> tuple[str, EquipmentBulkGroup, EquipmentType | None] | None:
    if not isinstance(identity_text, str) or not all(
        isinstance(value, str) for value in group_lines
    ):
        return None
    identity = _clean_text(identity_text)
    match = re.fullmatch(r"Selling\s*\[([^]]+)\]\s*[.]?", identity, re.IGNORECASE)
    if match is None:
        return None
    item_name = _clean_text(match.group(1))
    text = _clean_text(" ".join(group_lines)).casefold()
    if re.search(r"sell\s*(?:\(\s*bulk\s*\)|\[\s*bulk\s*\])", text) is None:
        return None
    if re.search(r"all of the \(enhance\) items of the same grade", text):
        return item_name, EquipmentBulkGroup.ENHANCE_GRADE, None
    if re.search(r"all of the equipment of this grade", text):
        return item_name, EquipmentBulkGroup.EQUIPMENT_GRADE, None
    typed = re.search(r"all of the \[([^]]+)\] of this grade", text)
    if typed is not None:
        equipment_type = _TYPE_NAMES.get(_clean_text(typed.group(1)).casefold())
        if equipment_type is not None:
            return item_name, EquipmentBulkGroup.TYPE_GRADE, equipment_type
    return None


class EquipmentSellReader:
    """Read one fail-closed sample from a caller-owned frame."""

    def __init__(self, engine) -> None:
        if not callable(getattr(engine, "recognize", None)):
            raise ValueError("engine must provide recognize(image)")
        self.engine = engine

    def inventory_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> EquipmentInventoryFact | None:
        _require_frame(frame)
        count = self._read(frame, ITEM_COUNT_ROI, scale=2.5)
        page = self._read(frame, PAGE_ROI, scale=2.5)
        parsed_count = parse_item_count(count.text) if count.confidence >= 0.80 else None
        parsed_page = parse_page(page.text) if page.confidence >= 0.80 else None
        if parsed_count is None or parsed_page is None:
            return None
        return EquipmentInventoryFact(
            item_count=parsed_count[0],
            capacity=parsed_count[1],
            page=parsed_page[0],
            total_pages=parsed_page[1],
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(f"count:{count.text}", f"page:{page.text}"),
        )

    def detail_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> EquipmentItemFact | None:
        _require_frame(frame)
        title = self._read(frame, DETAIL_TITLE_ROI, scale=2.0)
        grade_type = self._read(frame, DETAIL_GRADE_TYPE_ROI, scale=2.0)
        parsed = (
            parse_item_detail(title.text, grade_type.text)
            if min(title.confidence, grade_type.confidence) >= 0.72
            else None
        )
        if parsed is None:
            return None
        name, grade, equipment_type, enhance = parsed
        return EquipmentItemFact(
            name=name,
            grade=grade,
            equipment_type=equipment_type,
            enhance=enhance,
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(f"title:{title.text}", f"grade_type:{grade_type.text}"),
        )

    def confirmation_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> EquipmentSellConfirmationFact | None:
        _require_frame(frame)
        identity = self._read(frame, CONFIRM_IDENTITY_ROI, scale=2.5)
        groups = tuple(
            self._read(frame, region, scale=2.5)
            for region in CONFIRM_GROUP_LINE_ROIS
        )
        if identity.confidence < 0.80 or min(value.confidence for value in groups) < 0.75:
            return None
        parsed = parse_confirmation(identity.text, [value.text for value in groups])
        if parsed is None:
            return None
        item_name, group, group_type = parsed
        return EquipmentSellConfirmationFact(
            item_name=item_name,
            group=group,
            group_type=group_type,
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(
                f"identity:{identity.text}",
                *(f"group:{value.text}" for value in groups),
            ),
        )

    def _read(self, frame: np.ndarray, region: RelativeRegion, *, scale: float):
        crop = _crop(frame, region)
        enlarged = cv2.resize(
            crop,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )
        return self.engine.recognize(enlarged)


def _crop(frame: np.ndarray, region: RelativeRegion) -> np.ndarray:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = relative_region_to_pixels(region, width, height)
    result = frame[y1:y2, x1:x2]
    if result.size == 0:
        raise ValueError("ROI produced an empty crop")
    return result


def _clean_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def _require_frame(frame: object) -> None:
    if (
        not isinstance(frame, np.ndarray)
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.dtype != np.uint8
        or frame.size == 0
    ):
        raise ValueError("frame must be a non-empty HxWx3 uint8 image")


__all__ = (
    "CONFIRM_GROUP_LINE_ROIS",
    "CONFIRM_IDENTITY_ROI",
    "DETAIL_GRADE_TYPE_ROI",
    "DETAIL_TITLE_ROI",
    "EquipmentSellReader",
    "ITEM_COUNT_ROI",
    "PAGE_ROI",
    "parse_confirmation",
    "parse_item_count",
    "parse_item_detail",
    "parse_page",
)
