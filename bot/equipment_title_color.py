"""Selected Equipment title ink, independent of its spelling or item artwork."""

from dataclasses import dataclass

import cv2
import numpy as np

from bot.equipment_sell_semantics import EquipmentGrade as Grade
from bot.geometry import relative_region_to_pixels


# Inside the title bar: excludes its gold frame, side ornaments and item icon.
TITLE_INK_ROI = (.522, .273, .728, .307)


@dataclass(frozen=True)
class TitleColorSample:
    grade: Grade
    mask: np.ndarray
    diagnostic: dict


def selected_title_color(frame: np.ndarray) -> TitleColorSample:
    height, width = frame.shape[:2]
    x, y, xx, yy = relative_region_to_pixels(TITLE_INK_ROI, width, height)
    crop = frame[y:yy, x:xx]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    # Remove broad highlights/background; retain locally bright glyph strokes.
    size = max(3, round(height * .008)) | 1
    background = cv2.morphologyEx(value, cv2.MORPH_OPEN, np.ones((size, size), np.uint8))
    foreground = ((value >= 100) & (cv2.subtract(value, background) >= 35)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground)
    ink = np.zeros(value.shape, np.uint8)
    glyphs = []
    for index in range(1, count):
        left, top, w, h, area = stats[index]
        if (.008 * height <= h <= .034 * height and
                .001 * width <= w <= .020 * width and
                area >= max(4, .000005 * height * width)):
            ink[labels == index] = 255
            glyphs.append((int(left), int(top), int(w), int(h)))
    # Anti-aliasing mixes edge pixels with the dark red inventory underneath.
    # Classify glyph interiors; keep the full mask for the family marker.
    interiors = cv2.distanceTransform(ink, cv2.DIST_L2, 3) >= max(1.35, .0018 * height)
    pixels = hsv[interiors & (value >= 120)]
    scores = {}
    if pixels.size:
        hue, saturation, _ = pixels.T
        chromatic = saturation >= 110
        classes = {
            Grade.POOR: saturation <= 45,
            Grade.NORMAL: chromatic & (hue >= 53) & (hue <= 68),
            Grade.RARE: chromatic & (hue >= 98) & (hue <= 113),
            Grade.EPIC: chromatic & (hue >= 137) & (hue <= 153),
            Grade.LEGENDARY: chromatic & (hue >= 6) & (hue <= 18),
            # Red is shared by Ethereal and Ethereal+. The reader must resolve
            # the acquired grade marker before authorizing the red family.
            Grade.ETHEREAL: chromatic & ((hue <= 3) | (hue >= 177)),
        }
        scores = {grade: float(np.mean(mask)) for grade, mask in classes.items()}
    ranked = sorted(scores, key=scores.get, reverse=True)
    best = scores[ranked[0]] if ranked else 0.
    runner = scores[ranked[1]] if len(ranked) > 1 else 0.
    span = max((a + c for a, b, c, d in glyphs), default=0) - min((a for a, b, c, d in glyphs), default=0)
    strong = (len(glyphs) >= 5 and len(pixels) >= max(30, .000025 * height * width)
              and span >= .045 * width and best >= .88 and best - runner >= .78)
    return TitleColorSample(
        ranked[0] if strong else Grade.UNKNOWN, ink,
        {"ink_pixels": len(pixels), "glyphs": len(glyphs), "span": span,
         "scores": {grade.value: score for grade, score in scores.items()},
         "margin": best - runner},
    )
