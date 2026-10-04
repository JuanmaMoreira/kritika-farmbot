"""Local, read-only Item Trade and trade-boundary facts from Trading frames.

The C4 operation owns confirmation and postconditions. This reader only
describes one fresh resolved Trading frame; it never navigates or sends input.
"""

from __future__ import annotations

import re
import time

import cv2

from bot.runtime_observer import RuntimeSnapshot
from bot.trading_center import is_trading_screen
from bot.trading_operation import TradePanelFact
from bot.trading_row_facts import parse_pair


# Relative ROIs calibrated against the existing C4/C5 and C6b Trading frames.
_ROIS = {
    "panel_title": (.42, .18, .59, .23),
    "input_title": (.54, .30, .70, .35),
    "input_pair": (.54, .34, .65, .385),
    "input_pair_material": (.54, .343, .65, .38),
    "output_title": (.30, .505, .48, .55),
    "quantity": (.592, .78, .66, .84),
    "alert_first": (.35, .43, .65, .49),
    "alert_second": (.39, .47, .63, .52),
    "alert_ok": (.44, .59, .56, .66),
    "cost_area": (.50, .405, .70, .61),
}

# Input label and output label must both agree; these are the three C4/C5
# operations used by the resource route, not a general Trading catalog.
_KNOWN_TRADES = {
    ("weapon crafting material", "hero weapon crafting material"):
        "hero_weapon_crafting_material",
    ("bronze key", "silver key"): "silver_key",
    ("silver key", "gold key"): "gold_key",
}


class TradingPanelReader:
    """Supply C4's zero-argument read_panel callback from a local observer."""

    def __init__(self, observer, engine, *, clock=time.monotonic,
                 max_age_s: float = 2.0) -> None:
        if not callable(getattr(observer, "observe", None)):
            raise ValueError("observer must provide observe()")
        if not callable(getattr(engine, "recognize", None)) or not callable(clock):
            raise ValueError("engine and clock must be callable")
        if max_age_s <= 0:
            raise ValueError("max_age_s must be positive")
        self.observer = observer
        self.engine = engine
        self.clock = clock
        self.max_age_s = float(max_age_s)
        self._last_sequence = 0
        self.last_diagnostic = {}

    def read_panel(self) -> TradePanelFact | None:
        snapshot = self.observer.observe()
        result = self.read_snapshot(snapshot, after_sequence=self._last_sequence)
        if isinstance(snapshot, RuntimeSnapshot):
            self._last_sequence = max(self._last_sequence, snapshot.sequence)
        return result

    def read_snapshot(self, snapshot: RuntimeSnapshot, *,
                      after_sequence: int = 0) -> TradePanelFact | None:
        self.last_diagnostic = {"sequence": getattr(snapshot, "sequence", None), "reads": {}, "reason": None}
        if (not isinstance(snapshot, RuntimeSnapshot)
                or not is_trading_screen(snapshot)
                or snapshot.state.overlays
                or snapshot.sequence <= after_sequence):
            return self._unavailable("context_or_sequence")
        age = self.clock() - snapshot.timestamp
        self.last_diagnostic["age_before_reader"] = age
        if age < 0 or age > self.max_age_s:
            return self._unavailable("stale_or_future_frame")
        frame = snapshot.frame.image

        title = self._read(frame, "panel_title")
        normal_title = title.confidence >= .85 and _plain(title.text) == "item trade"
        # This physically empty region is part of every supported Item Trade
        # panel. Alert overlays or an additional cost invalidate that layout.
        blank = cv2.cvtColor(_crop(frame, _ROIS["cost_area"]), cv2.COLOR_BGR2GRAY)
        empty_cost = 14 <= blank.mean() <= 22 and blank.std() <= 2 and blank.max() <= 30
        if not normal_title or not empty_cost:
            first = self._read(frame, "alert_first")
            second = self._read(frame, "alert_second")
            ok = self._read(frame, "alert_ok")
            if ok.confidence >= .80 and _plain(ok.text) == "ok":
                boundary = _boundary(first, second)
                if boundary is not None:
                    return self._accept_fresh(snapshot, TradePanelFact(
                        item_id=None, input_have=None, input_need=None,
                        quantity=None, sequence=snapshot.sequence,
                        shows_output_full=boundary == "output_full",
                        shows_insufficient=boundary == "insufficient",
                        shows_limit=boundary == "limit",
                        evidence=(f"alert:{boundary}",),
                    ))
                return self._unavailable("unknown_boundary")
            return self._unavailable("panel_title" if not normal_title else "second_cost_area")

        incoming = self._read(frame, "input_title")
        outgoing = self._read(frame, "output_title")
        item_id = _KNOWN_TRADES.get((_plain(incoming.text), _plain(outgoing.text)))
        # Materials red glyphs need tighter vertical padding. Keep the acquired
        # Keys crop: narrowing it makes parchment texture a spurious underscore.
        pair = self._read(frame, "input_pair_material" if item_id ==
                          "hero_weapon_crafting_material" else "input_pair")
        quantity = self._read(frame, "quantity")
        if min(incoming.confidence, outgoing.confidence,
               pair.confidence, quantity.confidence) < .85:
            return self._unavailable("ocr_confidence")
        displayed = parse_pair(pair.text.strip().strip("()"))
        selected_pair = parse_pair(quantity.text)
        if item_id is None or displayed is None or selected_pair is None:
            return self._unavailable("identity_or_pair_parse")
        have, displayed_need = displayed
        selected, cap = selected_pair
        if (selected < 1 or cap < selected or displayed_need < 1
                or displayed_need % selected):
            return self._unavailable("quantity_or_cost")
        # The panel shows total input cost after >>. C4 compares the
        # per-trade cost against the causal row, so divide only when exact.
        per_trade_need = displayed_need // selected
        return self._accept_fresh(snapshot, TradePanelFact(
            item_id=item_id, input_have=have, input_need=per_trade_need,
            quantity=(selected, cap), sequence=snapshot.sequence,
            evidence=(f"displayed_input:{have}/{displayed_need}",
                      f"quantity:{selected}/{cap}", "second_cost_area:empty"),
        ))

    def _read(self, frame, name):
        image = _crop(frame, _ROIS[name])
        enlarged = cv2.resize(image, None, fx=3, fy=3,
                              interpolation=cv2.INTER_CUBIC)
        started = time.perf_counter()
        result = self.engine.recognize(enlarged)
        diagnostic_name = "input_pair" if name == "input_pair_material" else name
        self.last_diagnostic.setdefault("reads", {})[diagnostic_name] = {
            "raw": result.text, "confidence": result.confidence,
            "ocr_seconds": time.perf_counter() - started,
        }
        return result

    def _accept_fresh(self, snapshot, fact):
        age = self.clock() - snapshot.timestamp
        self.last_diagnostic["age_after_reader"] = age
        if not 0 <= age <= self.max_age_s:
            return self._unavailable("expired_during_reader")
        return fact

    def _unavailable(self, reason):
        self.last_diagnostic["reason"] = reason
        return None


def _crop(frame, region):
    height, width = frame.shape[:2]
    left, top, right, bottom = region
    return frame[int(top * height):int(bottom * height),
                 int(left * width):int(right * width)]


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().strip(" []().\"'\n\t ")).strip()


def _boundary(first, second) -> str | None:
    if first.confidence < .85 or second.confidence < .85:
        return None
    line = _plain(first.text)
    continuation = _plain(second.text)
    if ((line.startswith("you cannot purchase any more of this")
         and continuation == "item")
        or (line.startswith("you have reached the max limit of")
            and continuation)):
        return "output_full"
    if (line == "the trade was unsuccessful"
            and continuation == "insufficient items to trade"):
        return "insufficient"
    if (line.startswith("you cannot exceed the available number")
            and continuation == "of items you have for trade"):
        return "limit"
    return None


__all__ = ("TradingPanelReader",)
