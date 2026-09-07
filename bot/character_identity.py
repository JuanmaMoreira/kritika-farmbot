"""Optional Lobby HUD identity, with exact Unicode lookup and no gameplay policy."""

from dataclasses import dataclass
from types import MappingProxyType

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


@dataclass(frozen=True)
class CharacterIdentity:
    personal_name: str
    class_name: str
    confidence: float


class LobbyNameRecognizer:
    """Read one clean Lobby snapshot; missing/uncertain evidence is non-fatal.

    Exact lookup first, then only explicitly validated complete OCR variants.
    No character substitutions, transliteration, partial or fuzzy matching.
    OCR confidence is a backend score, not a probability of correct identity.
    """

    def __init__(self, engine: OcrEngine):
        self.engine = engine

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
            result = self.engine.recognize(frame[y1:y2, x1:x2].copy())
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
