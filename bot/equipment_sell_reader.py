"""Local OCR reader for current Equipment Inventory sell facts.

The reader performs no sampling, navigation, policy or input.  One frame yields
at most one unconfirmed sample; callers build consensus with
``consensus_facts`` before any destructive boundary.
"""

from __future__ import annotations

import re
from pathlib import Path

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
from bot.ocr import OcrResult


ITEM_COUNT_ROI: RelativeRegion = (0.687, 0.234, 0.817, 0.276)
PAGE_ROI: RelativeRegion = (0.724, 0.885, 0.786, 0.937)
DETAIL_TITLE_ROI: RelativeRegion = (0.514, 0.255, 0.731, 0.310)
DETAIL_GRADE_TYPE_ROI: RelativeRegion = (0.560, 0.315, 0.750, 0.365)
CONFIRM_IDENTITY_ROI: RelativeRegion = (0.350, 0.385, 0.650, 0.425)
# A long item name can carry its closing bracket onto the second identity line.
CONFIRM_IDENTITY_CONTINUATION_ROI: RelativeRegion = (0.350, 0.418, 0.650, 0.448)
CONFIRM_GROUP_LINE_ROIS: tuple[RelativeRegion, ...] = (
    (0.350, 0.438, 0.650, 0.469),
    (0.350, 0.473, 0.650, 0.504),
    (0.350, 0.508, 0.650, 0.540),
)

# K Coin identity wraps on an extra line, moving the three Bulk lines.
CONFIRM_COIN_GROUP_LINE_ROIS = (
    (.350, .448, .650, .483),
    (.350, .483, .650, .517),
    (.350, .517, .650, .552),
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
    normalized_title = _clean_text(title).strip("*※×»« :;")
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
    # The K Coin amount can wrap onto the next line; this ROI owns identity,
    # while the independently read Bulk lines own the destructive scope.
    match = re.fullmatch(r"Selling\s*\[([^]]+)\](?:\s+for(?:\s+\d[\d,]*(?:\s+K(?:\s+Coins)?)?)?)?\s*[.,]?", identity, re.IGNORECASE)
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
        assets = Path(__file__).resolve().parents[1] / "assets" / "equipment"
        self._grade_templates = {g: cv2.imread(str(assets / ("grade_"+g.value+".png")))
                                 for g in EquipmentGrade if (assets / ("grade_"+g.value+".png")).exists()}
        self._sell_template = cv2.imread(str(assets / "sell_available.png"))
        self._sell_token_template = cv2.imread(str(assets / "sell_available_token.png"))
        self._expand_template = cv2.imread(str(assets / "expand_bag_prompt.png"))


    def inventory_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> EquipmentInventoryFact | None:
        _require_frame(frame)
        if self.expansion_visible(frame):
            return None
        count = self._read(frame, ITEM_COUNT_ROI, scale=2.5)
        page = self._read(frame, PAGE_ROI, scale=2.5)
        parsed_count = parse_item_count(count.text) if count.confidence >= 0.80 else None
        parsed_page = parse_page(page.text) if page.confidence >= 0.80 else None
        self.last_context_diagnostic = {
            "count": {"text": count.text, "confidence": count.confidence, "parsed": parsed_count},
            "page": {"text": page.text, "confidence": page.confidence, "parsed": parsed_page},
        }
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
        self.last_detail_diagnostic = {
            "title": {"text": title.text, "confidence": title.confidence},
            "grade_type": {"text": grade_type.text, "confidence": grade_type.confidence},
            "parsed": parsed,
        }
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
            sell_available=(True if max(self._template_score(frame, template,
                                               (.765, .452, .817, .503))
                                       for template in (self._sell_template,self._sell_token_template)) >= .92 else None),
            grade_visual=(grade if self._template_score(frame, self._grade_templates.get(grade),
                                                        (.565,.322,.745,.372)) >= .92 else None),
        )

    def confirmation_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> EquipmentSellConfirmationFact | None:
        _require_frame(frame)
        identity = self._read(frame, CONFIRM_IDENTITY_ROI, scale=2.5)
        continuation = None
        if (identity.confidence >= .80 and
                re.match(r"Selling\s*\[", identity.text, re.IGNORECASE) and
                "]" not in identity.text):
            continuation = self._read(frame, CONFIRM_IDENTITY_CONTINUATION_ROI, scale=2.5)
            identity = OcrResult(
                f"{identity.text} {continuation.text}",
                min(identity.confidence, continuation.confidence),
            )
        regions = (CONFIRM_COIN_GROUP_LINE_ROIS
                   if re.search(r"\]\s+for\b", identity.text)
                   else CONFIRM_GROUP_LINE_ROIS)
        groups = tuple(
            self._read(frame, region, scale=2.5)
            for region in regions
        )
        self.last_confirmation_diagnostic = {
            "identity": {"text": identity.text, "confidence": identity.confidence},
            "continuation": ({"text": continuation.text, "confidence": continuation.confidence}
                             if continuation is not None else None),
            "groups": [{"text": v.text, "confidence": v.confidence} for v in groups],
        }
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

    def expansion_visible(self, frame):
        return self._template_score(frame, self._expand_template,
                                    (.365, .468, .635, .511)) >= .92

    @staticmethod
    def _template_score(frame, template, region):
        if template is None:
            return 0.0
        crop = _crop(frame, region)
        # Templates acquired natively at 2712x1224, normalized for live geometry.
        template = cv2.resize(template, None, fx=frame.shape[1]/2712,
                              fy=frame.shape[0]/1224, interpolation=cv2.INTER_AREA)
        if crop.shape[0] < template.shape[0] or crop.shape[1] < template.shape[1]:
            return 0.0
        return float(cv2.minMaxLoc(cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED))[1])

    def expansion_sample(self, frame, *, sequence, observed_at):
        if not self.expansion_visible(frame):
            return None
        cost = self._read(frame, (.395,.430,.605,.473), scale=2.5)
        action = self._read(frame, (.365,.468,.635,.510), scale=2.5)
        match = re.fullmatch(r"\s*(\d[\d,]*) Karats will be consumed[.,]?\s*", cost.text)
        if (match is None or min(cost.confidence,action.confidence) < .90 or
            _clean_text(action.text) != "Would you like to expand your Bag?"):
            return None
        return int(match.group(1).replace(",", "")), sequence, observed_at

    def capacity_row_cost(self, frame, row):
        y = row * .139
        value = self._read(frame, (.660,.350+y,.704,.405+y), scale=2.5)
        if value.confidence < .95 or re.fullmatch(r"\d[\d,]*", value.text.strip()) is None:
            return None
        return int(value.text.strip().replace(",", ""))

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
