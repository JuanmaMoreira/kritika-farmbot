"""Fresh native Lobby balances; existing Sapphire ROI plus acquired Badge pair."""
from dataclasses import dataclass
import hashlib
import math
import re
import time

import cv2

from bot.arena_reader import crop
from bot.arena_flow_reader import ArenaFlowVisuals
from bot.battle_mode_zone import is_lobby
from bot.runtime_observer import RuntimeWaitCancelled
from bot.state import ResolutionStatus

BADGES_ROI = (.787, .608, .849, .648)
SAPPHIRES_ROI = (.787, .455, .849, .494)


@dataclass(frozen=True)
class ArenaFarmingResources:
    badges: int
    sapphires: int
    sequence: int
    observed_at: float
    frame_sha256: str

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in (self.badges, self.sapphires, self.sequence)):
            raise ValueError('nonnegative observed resource integers required')
        if (not math.isfinite(self.observed_at) or self.observed_at < 0
                or len(self.frame_sha256) != 64
                or any(c not in '0123456789abcdef' for c in self.frame_sha256)):
            raise ValueError('resource pixel provenance required')


class ArenaFarmingResourceReader:
    max_age = 4.

    def __init__(self, observer, engine, *, cancel_requested=lambda: False,
                 clock=time.monotonic, visuals=None):
        self.observer, self.engine = observer, engine
        self.cancel_requested, self.clock = cancel_requested, clock
        self.visuals = visuals or ArenaFlowVisuals()

    def _cancel(self):
        if self.cancel_requested():
            raise RuntimeWaitCancelled('Arena resource reading cancelled')

    def _pair(self, image, roi):
        values = []
        region = crop(image, roi)
        for prepared in (region, cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)):
            self._cancel()
            read = self.engine.recognize(cv2.resize(prepared, None, fx=3, fy=3))
            number = r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)'
            match = re.fullmatch(rf'\s*({number})\s*/\s*({number})\s*', read.text)
            if read.confidence < .95 or dict(read.metadata).get('line_count', 1) != 1 or not match:
                return None
            pair = tuple(int(v.replace(',', '')) for v in match.groups())
            if pair[1] <= 0:
                return None
            values.append(pair)
        return values[0][0] if values[0] == values[1] else None

    def parse(self, frame):
        self._cancel()
        image = frame.image.copy()
        if not 0 <= self.clock() - frame.timestamp <= self.max_age:
            return None
        # Resolve the very native image being parsed, never a prior stream state.
        state = self.observer.resolver.resolve(self.observer.perception.analyze(frame))
        if (state.status is not ResolutionStatus.RESOLVED or state.base_context != 'screen.lobby'
                or state.overlays or not self.visuals.lobby(image)):
            return None
        values = [self._pair(image, roi) for roi in (BADGES_ROI, SAPPHIRES_ROI)]
        self._cancel()
        if any(v is None for v in values) or not 0 <= self.clock() - frame.timestamp <= self.max_age:
            return None
        return ArenaFarmingResources(*values, frame.sequence, frame.timestamp,
                                    hashlib.sha256(image.tobytes()).hexdigest())

    def read(self):
        self._cancel()
        initial = self.observer.observe()
        if not is_lobby(initial):
            return None  # No navigation/closing from UNKNOWN.
        # Lazy OCR initialization happens before acquiring decision authority.
        self._pair(initial.frame.image, SAPPHIRES_ROI)
        previous = None
        cursor, timestamp = initial.sequence, initial.timestamp
        for _ in range(3):
            self._cancel()
            frame = self.observer.source.refresh_native()
            if frame.sequence <= cursor or frame.timestamp <= timestamp:
                return None
            cursor, timestamp = frame.sequence, frame.timestamp
            reading = self.parse(frame)
            if reading is not None and previous is not None and (
                    reading.badges, reading.sapphires) == (previous.badges, previous.sapphires):
                return reading
            previous = reading
        return None
