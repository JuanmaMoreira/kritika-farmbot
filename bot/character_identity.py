"""Optional Lobby HUD identity, with exact Unicode lookup and no gameplay policy."""

from dataclasses import dataclass
from types import MappingProxyType
from pathlib import Path
import cv2
import numpy as np

from bot.catalog import SCREEN_LOBBY
from bot.geometry import relative_region_to_pixels
from bot.ocr import OcrEngine
from bot.runtime_observer import RuntimeSnapshot
from bot.state import ResolutionStatus


PERSONAL_NAME_CLASSES = MappingProxyType({
    "DRAKEN三BB": "Burst Breaker",
    "DRAKEN一BK": "Berserker",
    "DRAKEN二DB": "Demon Blade",
    "Drakenn25": "Kaiserin",
    "Drakenn13": "Noblia",
    "Drakenn10": "Ice Warlock",
    "Drakenn09": "Crimson Assassin",
    "DRAKEN四R": "Rang",
    "Drakenn26": "Telumpel",
    "Drakenn20": "Halo Mage",
    "Drakenn19": "Strike Archer",
    "Drakenn23": "Galaxy Lord",
    "Drakenn08": "Wandering Master",
    "Drakenn14": "Steam Walker",
    "Drakennn15": "Mystic Wolf Guardian",
    "Drakenn16": "Blood Demon",
    "Drakenn06": "Eclair",
    "Drakenn21": "Dark Valkyrie",
    "Drakennn17": "Elemental Fairy",
    "Drakenn24": "Hastati",
    "DRAKEN六FS": "Flame Striker",
    "Drakenn27": "Eilla",
    "Drakenn11": "Lina",
    "Drakenn12": "Cat Acrobat",
    "Drakenn18": "Shadow Mage",
    "DRAKEN五M": "Monk",
    "DRAKEN四BD": "Blade Dancer",
    "Drakenn22": "Dimension Manipulator",
})

# Full OCR strings verified against the nine raw Lobby frames. These are not
# real personal names and must stay separate from authoritative ground truth.
# DRAKEN-DB was observed only below threshold; it still cannot bypass the gate.
KNOWN_LOBBY_NAME_OCR_VARIANTS = MappingProxyType({
    "DRAKEN-BK": "DRAKEN一BK",
    "DRAKEN-DB": "DRAKEN二DB",
    "DRAKENDB": "DRAKEN二DB",
    "DRAKEN=BB": "DRAKEN三BB",
})

LOBBY_PERSONAL_NAME_ROI = (0.080, 0.020, 0.190, 0.062)
MIN_NAME_CONFIDENCE = 0.95

# Permanent identifiers, independent of selection order, spelling and OCR.
CHARACTER_IDS = MappingProxyType({
    'DRAKEN三BB':'burst_breaker', 'DRAKEN一BK':'berserker', 'DRAKEN二DB':'demon_blade',
    'Drakenn25':'kaiserin', 'Drakenn13':'noblia', 'Drakenn10':'ice_warlock',
    'Drakenn09':'crimson_assassin', 'DRAKEN四R':'rang', 'Drakenn26':'telumpel',
    'Drakenn20':'halo_mage', 'Drakenn19':'strike_archer', 'Drakenn23':'galaxy_lord',
    'Drakenn08':'wandering_master', 'Drakenn14':'steam_walker',
    'Drakennn15':'mystic_wolf_guardian', 'Drakenn16':'blood_demon', 'Drakenn06':'eclair',
    'Drakenn21':'dark_valkyrie', 'Drakennn17':'elemental_fairy', 'Drakenn24':'hastati',
    'DRAKEN六FS':'flame_striker', 'Drakenn27':'eilla', 'Drakenn11':'lina',
    'Drakenn12':'cat_acrobat', 'Drakenn18':'shadow_mage', 'DRAKEN五M':'monk',
    'DRAKEN四BD':'blade_dancer', 'Drakenn22':'dimension_manipulator',
})

CONFLICT_NAMES = ('DRAKEN一BK', 'DRAKEN二DB', 'DRAKEN三BB')

def name_mask(image):
    image = cv2.resize(image, (300, 52), interpolation=cv2.INTER_AREA)
    lo, hi = image.min(axis=2), image.max(axis=2)
    return (np.uint8((lo > 150) & (hi-lo < 70)) * 255)[10:49, 42:]

class FocalNameDiscriminator:
    """White full-name ink, calibrated on first frames; reject low score/margin."""
    def __init__(self):
        root = Path(__file__).resolve().parents[1] / 'assets/character_identity'
        self.templates = {name: cv2.imread(str(root / f'{CHARACTER_IDS[name]}.png'), 0)
                          for name in CONFLICT_NAMES}

    def resolve(self, crop):
        mask = name_mask(crop)
        if any(t is None for t in self.templates.values()) or np.count_nonzero(mask) < 100:
            return None
        padded = cv2.copyMakeBorder(mask, 3, 3, 3, 3, cv2.BORDER_CONSTANT)
        # The shared DRAKEN prefix cannot provide the discrimination margin.
        # Require full-name agreement plus a separate Unicode/suffix winner.
        suffix = cv2.copyMakeBorder(mask[:,160:],3,3,3,3,cv2.BORDER_CONSTANT)
        scores = sorted(((float(cv2.matchTemplate(suffix, template[:,160:], cv2.TM_CCOEFF_NORMED).max()), name)
                         for name, template in self.templates.items()), reverse=True)
        full = float(cv2.matchTemplate(padded,self.templates[scores[0][1]],cv2.TM_CCOEFF_NORMED).max())
        if full < .90 or scores[0][0] < .90 or scores[0][0] - scores[1][0] < .06:
            return None
        return scores[0][1], scores[0][0]


@dataclass(frozen=True)
class CharacterIdentity:
    personal_name: str
    class_name: str
    confidence: float
    method: str = 'canonical_ocr'

    @property
    def character_id(self):
        return CHARACTER_IDS[self.personal_name]


class LobbyNameRecognizer:
    """Read one clean Lobby snapshot; missing/uncertain evidence is non-fatal.

    Closed canonical OCR for ordinary names; full-name and suffix templates
    resolve the three conflictives. No positional identity or fuzzy lookup.
    OCR confidence is a backend score, not a probability of correct identity.
    """

    def __init__(self, engine: OcrEngine):
        self.engine = engine
        self.discriminator = FocalNameDiscriminator()

    def recognize(self, snapshot: RuntimeSnapshot | None) -> CharacterIdentity | None:
        try:
            if snapshot is None:
                return None
            state = snapshot.state
            if (state.status is not ResolutionStatus.RESOLVED
                    or state.base_context != SCREEN_LOBBY or state.overlays):
                return None
            frame = snapshot.frame.image
            height, width = frame.shape[:2]
            x1, y1, x2, y2 = relative_region_to_pixels(
                LOBBY_PERSONAL_NAME_ROI, width, height,
            )
            # Own the tiny crop; a backend cannot mutate the shared capture.
            crop = frame[y1:y2, x1:x2].copy()
            result = self.engine.recognize(crop)
            # Conflict aliases never resolve from OCR alone. A low-confidence
            # OCR may nominate this focal branch, but cannot lower its CV gate.
            nominated = KNOWN_LOBBY_NAME_OCR_VARIANTS.get(result.text, result.text)
            if nominated in CONFLICT_NAMES:
                visual = self.discriminator.resolve(crop)
                if visual is None or visual[0] != nominated:
                    return None
                return CharacterIdentity(visual[0], PERSONAL_NAME_CLASSES[visual[0]], visual[1], 'focal_template')
            if nominated not in PERSONAL_NAME_CLASSES:
                visual = self.discriminator.resolve(crop)
                if visual is not None:
                    return CharacterIdentity(visual[0],PERSONAL_NAME_CLASSES[visual[0]],visual[1],'focal_template')
            if result.confidence < MIN_NAME_CONFIDENCE:
                return None
            if dict(result.metadata).get("line_count", 1) != 1:
                return None
            personal_name = result.text
            class_name = PERSONAL_NAME_CLASSES.get(personal_name)
            if class_name is None:
                personal_name = KNOWN_LOBBY_NAME_OCR_VARIANTS.get(result.text)
                class_name = PERSONAL_NAME_CLASSES.get(personal_name)
            if class_name is None:
                return None
            return CharacterIdentity(personal_name, class_name, result.confidence)
        except Exception:
            # Identity never promotes an OCR/backend error to a session failure.
            return None
