"""The two unscrolled Keys rows, anchored by their stable title templates.

Only variable have/need values use OCR. Every frame revalidates both titles;
no row geometry or balances survive navigation or a trade.
"""
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from bot.trading_row_facts import RowSample, KEYS_SECTION, parse_pair

KEY_ROWS = ("silver_key", "gold_key")


@lru_cache(maxsize=4)
def _templates(width, height):
    root = Path(__file__).resolve().parents[1] / "assets/ui/landmarks/trading-center"
    result = []
    for key, relative_width in zip(KEY_ROWS, (230 / 2712, 215 / 2712)):
        template = cv2.imread(str(root / f"{key}_title.png"), cv2.IMREAD_GRAYSCALE)
        if template is None:
            raise ValueError(f"Keys title asset unavailable: {key}")
        result.append(cv2.resize(template, (round(relative_width * width),
                                             round(44 / 1224 * height))))
    return tuple(result)


def read_key_samples(reader, frame, sequence, diagnostics):
    """Return complete samples only at the two established Keys positions."""
    height, width = frame.shape[:2]
    current = {}
    for index, (key, template) in enumerate(zip(KEY_ROWS, _templates(width, height))):
        candidate = dict(item_id=key, identity_method="template", pair_method="key_cell",
                         phase_seconds={}, ocr_calls=0)
        diagnostics[key].append(candidate)
        started = perf_counter()
        left, top = int(.30 * width), int((.35 + index * .1418) * height)
        roi = frame[top:int((.50 + index * .1418) * height), left:int(.46 * width)]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
            candidate.update(identity_match=False, reason="empty_title_roi", sample=None)
            continue
        scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, position = cv2.minMaxLoc(scores)
        candidate["phase_seconds"]["row_localization"] = perf_counter() - started
        candidate.update(identity_confidence=confidence, identity_match=confidence >= .90)
        if confidence < .90:
            candidate.update(reason="title_mismatch", sample=None)
            continue
        title_top = (top + position[1]) / height
        row_y = title_top + template.shape[0] / (2 * height)
        # This is the first input icon's numeric footer, derived from the
        # matching title, independent of Hough divider phase and icon art.
        box = (.495, title_top + .037, .547, title_top + .075)
        candidate.update(row_top=title_top - .05, row_y=row_y, localized_roi=box)
        started = perf_counter()
        crop = frame[int(box[1] * height):int(box[3] * height),
                     int(box[0] * width):int(box[2] * width)]
        candidate["phase_seconds"]["crop"] = perf_counter() - started
        started = perf_counter()
        prepared = _prepare_pair(crop, height, width)
        candidate["phase_seconds"]["preprocessing"] = perf_counter() - started
        if prepared is None:
            candidate.update(reason="pair_not_localized", sample=None)
            continue
        started = perf_counter()
        candidate["ocr_calls"] = 1
        result = reader.engine.recognize(prepared)
        candidate["phase_seconds"]["ocr"] = perf_counter() - started
        started = perf_counter()
        pair = parse_pair(result.text)
        reason = ("ocr_low_confidence" if result.confidence < .90 else
                  "parse_failed" if pair is None else None)
        candidate["phase_seconds"]["parsing"] = perf_counter() - started
        candidate.update(reason=reason, parse_result=pair,
                         pair_reads=[dict(method="key_cell", roi=box, raw=result.text,
                                          confidence=result.confidence, parse_result=pair,
                                          reason=reason)])
        sample = (RowSample(key, KEYS_SECTION, row_y, *pair, sequence)
                  if reason is None else None)
        candidate["sample"] = vars(sample).copy() if sample is not None else None
        if sample is not None:
            current[key] = sample
    return current


def _prepare_pair(crop, height, width):
    if not crop.size:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    red = (cv2.inRange(hsv, np.array([0, 120, 145]), np.array([8, 255, 255]))
           | cv2.inRange(hsv, np.array([170, 120, 145]), np.array([180, 255, 255])))
    if np.count_nonzero(red) > .00003 * height * width:
        # Insufficient-input numerals are red; their isolated color mask
        # removes icon/border interference without altering the digits.
        ys, xs = np.nonzero(red)
        glyph = 255 - red[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        margin = max(2, round(height * .0025))
        glyph = cv2.copyMakeBorder(glyph, margin, margin, margin * 2, margin * 2,
                                   cv2.BORDER_CONSTANT, value=255)
    else:
        white = cv2.inRange(hsv, np.array([0, 0, 220]), np.array([180, 85, 255]))
        dark = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 110]))
        size = max(3, round(height * .0057))
        mask = white & cv2.dilate(dark, np.ones((size, size), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        glyphs = [(x, y, bw, bh) for x, y, bw, bh, _ in stats[1:]
                  if .006 * height <= bh <= .027 * height
                  and .001 * width <= bw <= .014 * width]
        if not glyphs:
            return None
        # Union every glyph in the bounded causal cell, not a leftmost
        # connected chain which can silently discard a leading digit.
        x1 = min(x for x, y, bw, bh in glyphs)
        y1 = min(y for x, y, bw, bh in glyphs)
        x2 = max(x + bw for x, y, bw, bh in glyphs)
        y2 = max(y + bh for x, y, bw, bh in glyphs)
        margin = max(1, round(height * .0025))
        glyph = crop[max(0, y1 - margin):min(crop.shape[0], y2 + margin),
                     max(0, x1 - margin):min(crop.shape[1], x2 + margin)]
    return cv2.resize(glyph, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
