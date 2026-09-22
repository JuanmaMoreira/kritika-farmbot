"""Local OCR reader for current Craft navigation and operation facts.

One frame yields at most one unconfirmed sample.  Sampling, freshness,
navigation, and economic policy remain caller responsibilities.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from bot.craft_semantics import (
    CraftContextFact,
    CraftCurrency,
    CraftCurrencyBoundaryFact,
    CraftFamily,
    CraftItemType,
    CraftRecipeFact,
    CraftResultFact,
    CraftTier,
    QuickMenuCraftFact,
)
from bot.geometry import RelativeRegion, relative_region_to_pixels


QUICK_MENU_LOBBY_ROI: RelativeRegion = (0.170, 0.200, 0.240, 0.280)
QUICK_MENU_CRAFT_ROI: RelativeRegion = (0.360, 0.490, 0.430, 0.560)
QUICK_MENU_GUILD_ROI: RelativeRegion = (0.360, 0.590, 0.430, 0.680)

CRAFT_TITLE_ROI: RelativeRegion = (0.400, 0.070, 0.600, 0.160)
CRAFT_RATE_ROI: RelativeRegion = (0.180, 0.120, 0.300, 0.200)
CRAFT_EXPERT_MARKER_ROI: RelativeRegion = (0.440, 0.275, 0.560, 0.340)
CRAFT_HERO_COUNT_ROIS: dict[CraftFamily, RelativeRegion] = {
    CraftFamily.WEAPON: (0.740, 0.170, 0.840, 0.240),
    CraftFamily.ARMOR: (0.740, 0.460, 0.840, 0.530),
    CraftFamily.ACCESSORY: (0.740, 0.730, 0.840, 0.810),
}
CRAFT_HERO_COST_ROIS: dict[CraftFamily, RelativeRegion] = {
    CraftFamily.WEAPON: (0.735, 0.390, 0.780, 0.435),
    CraftFamily.ARMOR: (0.735, 0.640, 0.780, 0.690),
    CraftFamily.ACCESSORY: (0.735, 0.890, 0.780, 0.945),
}

_SELECTED_RECIPE_ROIS: dict[
    CraftFamily, tuple[RelativeRegion, RelativeRegion]
] = {
    CraftFamily.WEAPON: (
        (0.455, 0.245, 0.515, 0.315),
        (0.455, 0.420, 0.545, 0.490),
    ),
    CraftFamily.ARMOR: (
        (0.280, 0.245, 0.360, 0.315),
        (0.280, 0.420, 0.370, 0.490),
    ),
    CraftFamily.ACCESSORY: (
        (0.370, 0.245, 0.430, 0.315),
        (0.370, 0.420, 0.460, 0.490),
    ),
}
CRAFT_COST_LABEL_ROI: RelativeRegion = (0.315, 0.570, 0.510, 0.680)
CRAFT_COST_ROI: RelativeRegion = (0.480, 0.570, 0.550, 0.680)
CRAFT_QUANTITY_ROI: RelativeRegion = (0.430, 0.680, 0.500, 0.790)

KARAT_MISSING_ROI: RelativeRegion = (0.420, 0.370, 0.580, 0.440)
KARAT_LINE_ROI: RelativeRegion = (0.350, 0.420, 0.650, 0.500)
KARAT_SPEND_ROI: RelativeRegion = (0.370, 0.550, 0.500, 0.660)
KARAT_NO_ROI: RelativeRegion = (0.510, 0.550, 0.640, 0.660)
CRAFT_RESULT_NAME_ROI: RelativeRegion = (0.360, 0.580, 0.640, 0.670)
CRAFT_RESULT_LEFT_DARK_ROI: RelativeRegion = (0.080, 0.200, 0.300, 0.800)
CRAFT_RESULT_RIGHT_DARK_ROI: RelativeRegion = (0.700, 0.200, 0.920, 0.800)
CRAFT_RESULT_CENTER_ROI: RelativeRegion = (0.380, 0.150, 0.620, 0.750)


_TIERS = {value.value: value for value in CraftTier if value is not CraftTier.UNKNOWN}
_ITEM_TYPES = {
    "weapon": CraftItemType.WEAPON,
    "helmet": CraftItemType.HELMET,
    "chest armor": CraftItemType.CHEST_ARMOR,
    "pants": CraftItemType.PANTS,
    "gloves": CraftItemType.GLOVES,
    "boots": CraftItemType.BOOTS,
    "earring": CraftItemType.EARRINGS,
    "earrings": CraftItemType.EARRINGS,
    "necklace": CraftItemType.NECKLACE,
    "ring": CraftItemType.RING,
}


def parse_pair(text: object) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    if match is None:
        return None
    first, second = (int(value) for value in match.groups())
    if first < 0 or second <= 0 or first > second:
        return None
    return first, second


def parse_positive_int(text: object) -> int | None:
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"\s*(\d[\d,]*)\s*", text)
    if match is None:
        return None
    value = int(match.group(1).replace(",", ""))
    return value if value > 0 else None


def parse_tier(text: object) -> CraftTier:
    if not isinstance(text, str):
        return CraftTier.UNKNOWN
    return _TIERS.get(_clean(text).casefold(), CraftTier.UNKNOWN)


def parse_item_type(text: object) -> CraftItemType:
    if not isinstance(text, str):
        return CraftItemType.UNKNOWN
    return _ITEM_TYPES.get(_clean(text).casefold(), CraftItemType.UNKNOWN)


def family_for_item(item_type: CraftItemType) -> CraftFamily | None:
    if item_type is CraftItemType.WEAPON:
        return CraftFamily.WEAPON
    if item_type in {
        CraftItemType.HELMET, CraftItemType.CHEST_ARMOR, CraftItemType.PANTS,
        CraftItemType.GLOVES, CraftItemType.BOOTS,
    }:
        return CraftFamily.ARMOR
    if item_type in {
        CraftItemType.EARRINGS, CraftItemType.NECKLACE, CraftItemType.RING,
    }:
        return CraftFamily.ACCESSORY
    return None


class CraftReader:
    """Read one fail-closed sample from a caller-owned BGR frame."""

    def __init__(self, engine) -> None:
        if not callable(getattr(engine, "recognize", None)):
            raise ValueError("engine must provide recognize(image)")
        self.engine = engine

    def quick_menu_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> QuickMenuCraftFact | None:
        _require_frame(frame)
        lobby = self._read(frame, QUICK_MENU_LOBBY_ROI, scale=4.0)
        craft = self._read(frame, QUICK_MENU_CRAFT_ROI, scale=4.0)
        guild = self._read(frame, QUICK_MENU_GUILD_ROI, scale=4.0)
        if min(lobby.confidence, craft.confidence, guild.confidence) < 0.80:
            return None
        fact = QuickMenuCraftFact(
            lobby_label=lobby.text,
            craft_label=craft.text,
            guild_label=guild.text,
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(f"lobby:{lobby.text}", f"craft:{craft.text}", f"guild:{guild.text}"),
        )
        return fact if fact.complete else None

    def context_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> CraftContextFact | None:
        _require_frame(frame)
        title = self._read(frame, CRAFT_TITLE_ROI, scale=3.0)
        rate = self._read(frame, CRAFT_RATE_ROI, scale=3.0)
        expert = self._read(frame, CRAFT_EXPERT_MARKER_ROI, scale=3.0)
        counts = {
            family: self._read(frame, region, scale=3.0)
            for family, region in CRAFT_HERO_COUNT_ROIS.items()
        }
        costs = {
            family: self._read(frame, region, scale=4.0)
            for family, region in CRAFT_HERO_COST_ROIS.items()
        }
        if title.confidence < 0.75 or min(rate.confidence, expert.confidence) < 0.85:
            return None
        parsed_title = (
            "Craft"
            if re.fullmatch(r"[^A-Za-z]*Craft[^A-Za-z]*", _clean(title.text), re.IGNORECASE)
            else title.text
        )
        parsed_counts = {
            family: parse_pair(result.text) if result.confidence >= 0.85 else None
            for family, result in counts.items()
        }
        parsed_costs = {
            family: parse_positive_int(result.text) if result.confidence >= 0.85 else None
            for family, result in costs.items()
        }
        if any(value is None for value in (*parsed_counts.values(), *parsed_costs.values())):
            return None
        weapon_count = parsed_counts[CraftFamily.WEAPON]
        armor_count = parsed_counts[CraftFamily.ARMOR]
        accessory_count = parsed_counts[CraftFamily.ACCESSORY]
        assert weapon_count is not None and armor_count is not None and accessory_count is not None
        fact = CraftContextFact(
            title=parsed_title,
            rate_label=rate.text,
            expert_label=expert.text,
            weapon_material=weapon_count[0],
            armor_material=armor_count[0],
            accessory_material=accessory_count[0],
            weapon_capacity=weapon_count[1],
            armor_capacity=armor_count[1],
            accessory_capacity=accessory_count[1],
            weapon_hero_cost=int(parsed_costs[CraftFamily.WEAPON]),
            armor_hero_cost=int(parsed_costs[CraftFamily.ARMOR]),
            accessory_hero_cost=int(parsed_costs[CraftFamily.ACCESSORY]),
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(
                f"title:{title.text}", f"rate:{rate.text}",
                f"expert:{expert.text}",
                *(f"{family.value}_count:{counts[family].text}" for family in CraftFamily),
                *(f"{family.value}_cost:{costs[family].text}" for family in CraftFamily),
            ),
        )
        return fact if fact.complete else None

    def recipe_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> CraftRecipeFact | None:
        _require_frame(frame)
        candidates = []
        for expected_family, (tier_roi, item_roi) in _SELECTED_RECIPE_ROIS.items():
            tier_read = self._read(frame, tier_roi, scale=4.0)
            item_read = self._read(frame, item_roi, scale=4.0)
            if min(tier_read.confidence, item_read.confidence) < 0.85:
                continue
            tier = parse_tier(tier_read.text)
            item_type = parse_item_type(item_read.text)
            family = family_for_item(item_type)
            if tier is not CraftTier.UNKNOWN and family is expected_family:
                candidates.append((family, tier, item_type, tier_read.text, item_read.text))
        if len(candidates) != 1:
            return None
        cost_label = self._read(frame, CRAFT_COST_LABEL_ROI, scale=3.0)
        cost = self._read(frame, CRAFT_COST_ROI, scale=4.0)
        quantity = self._read(frame, CRAFT_QUANTITY_ROI, scale=4.0)
        parsed_cost = parse_positive_int(cost.text) if cost.confidence >= 0.80 else None
        parsed_quantity = parse_pair(quantity.text) if quantity.confidence >= 0.85 else None
        label = _clean(cost_label.text).casefold()
        currency = (
            CraftCurrency.MATERIAL
            if cost_label.confidence >= 0.72 and "material" in label and "used" in label
            else CraftCurrency.UNKNOWN
        )
        if parsed_cost is None or parsed_quantity is None or currency is CraftCurrency.UNKNOWN:
            return None
        family, tier, item_type, tier_text, item_text = candidates[0]
        return CraftRecipeFact(
            family=family,
            tier=tier,
            item_type=item_type,
            currency=currency,
            unit_cost=parsed_cost,
            quantity=parsed_quantity[0],
            quantity_cap=parsed_quantity[1],
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(
                f"tier:{tier_text}", f"item:{item_text}",
                f"currency:{cost_label.text}", f"cost:{cost.text}",
                f"quantity:{quantity.text}",
            ),
        )

    def currency_boundary_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> CraftCurrencyBoundaryFact | None:
        _require_frame(frame)
        missing = self._read(frame, KARAT_MISSING_ROI, scale=3.0)
        line = self._read(frame, KARAT_LINE_ROI, scale=3.0)
        spend = self._read(frame, KARAT_SPEND_ROI, scale=4.0)
        reject = self._read(frame, KARAT_NO_ROI, scale=4.0)
        missing_match = re.search(r"Need\s+(\d+)\s+material", _clean(missing.text), re.IGNORECASE)
        line_match = re.search(r"(\d+)\s+Karats", _clean(line.text), re.IGNORECASE)
        spend_value = parse_positive_int(spend.text)
        if (
            min(missing.confidence, line.confidence, spend.confidence, reject.confidence) < 0.80
            or missing_match is None
            or line_match is None
            or spend_value is None
            or int(line_match.group(1)) != spend_value
        ):
            return None
        fact = CraftCurrencyBoundaryFact(
            missing_material=int(missing_match.group(1)),
            karat_cost=spend_value,
            reject_label=reject.text,
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(
                f"missing:{missing.text}", f"line:{line.text}",
                f"spend:{spend.text}", f"reject:{reject.text}",
            ),
        )
        return fact if fact.reject_label.casefold() == "no" else None

    def result_sample(
        self, frame: np.ndarray, *, sequence: int, observed_at: float
    ) -> CraftResultFact | None:
        """Recognize the stable full-screen Craft result, not its animation."""

        _require_frame(frame)
        left = cv2.cvtColor(_crop(frame, CRAFT_RESULT_LEFT_DARK_ROI), cv2.COLOR_BGR2GRAY)
        right = cv2.cvtColor(_crop(frame, CRAFT_RESULT_RIGHT_DARK_ROI), cv2.COLOR_BGR2GRAY)
        center = cv2.cvtColor(_crop(frame, CRAFT_RESULT_CENTER_ROI), cv2.COLOR_BGR2GRAY)
        left_bright = float(np.mean(left > 40))
        right_bright = float(np.mean(right > 40))
        center_bright = float(np.mean(center > 40))
        if left_bright > 0.05 or right_bright > 0.05 or center_bright < 0.30:
            return None
        name = self._read(frame, CRAFT_RESULT_NAME_ROI, scale=3.0)
        marker = _clean(name.text)
        if name.confidence < 0.80 or len(marker) < 3:
            return None
        return CraftResultFact(
            marker="craft_result",
            sequence=sequence,
            observed_at=observed_at,
            sample_sequences=(sequence,),
            evidence=(
                f"name:{marker}", f"left_bright:{left_bright:.4f}",
                f"right_bright:{right_bright:.4f}",
                f"center_bright:{center_bright:.4f}",
            ),
        )

    def _read(self, frame: np.ndarray, region: RelativeRegion, *, scale: float):
        crop = _crop(frame, region)
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return self.engine.recognize(enlarged)


def _crop(frame: np.ndarray, region: RelativeRegion) -> np.ndarray:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = relative_region_to_pixels(region, width, height)
    result = frame[y1:y2, x1:x2]
    if result.size == 0:
        raise ValueError("ROI produced an empty crop")
    return result


def _clean(text: str) -> str:
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
    "CRAFT_COST_LABEL_ROI", "CRAFT_COST_ROI", "CRAFT_EXPERT_MARKER_ROI",
    "CRAFT_HERO_COST_ROIS",
    "CRAFT_HERO_COUNT_ROIS", "CRAFT_QUANTITY_ROI", "CRAFT_RATE_ROI",
    "CRAFT_TITLE_ROI",
    "CRAFT_RESULT_CENTER_ROI", "CRAFT_RESULT_LEFT_DARK_ROI",
    "CRAFT_RESULT_NAME_ROI", "CRAFT_RESULT_RIGHT_DARK_ROI", "CraftReader",
    "KARAT_LINE_ROI", "KARAT_MISSING_ROI", "KARAT_NO_ROI",
    "KARAT_SPEND_ROI", "QUICK_MENU_CRAFT_ROI", "QUICK_MENU_GUILD_ROI",
    "QUICK_MENU_LOBBY_ROI", "family_for_item", "parse_item_type",
    "parse_pair", "parse_positive_int", "parse_tier",
)
