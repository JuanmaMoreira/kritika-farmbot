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
    # Normal routing observes three native frames (two concordant readings).
    # Post-Claim recovery allows one extra passive frame (~3s, total ~12s
    # like the MW post-CLEAR 12s window). Zero inputs, same gates.
    NORMAL_MAX_FRAMES = 3
    POST_CLAIM_MAX_FRAMES = 4
    READ_TIMEOUT = 12.

    def __init__(self, observer, engine, *, cancel_requested=lambda: False,
                 clock=time.monotonic, visuals=None):
        self.observer, self.engine = observer, engine
        self.cancel_requested, self.clock = cancel_requested, clock
        self.visuals = visuals or ArenaFlowVisuals()
        self.last_diagnosis = None

    def _cancel(self):
        if self.cancel_requested():
            raise RuntimeWaitCancelled('Arena resource reading cancelled')

    def _pair_detail(self, image, roi):
        """Single balance with a bounded rejection motive, never OCR text."""
        values = []
        region = crop(image, roi)
        for prepared in (region, cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)):
            self._cancel()
            read = self.engine.recognize(cv2.resize(prepared, None, fx=3, fy=3))
            number = r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)'
            match = re.fullmatch(rf'\s*({number})\s*/\s*({number})\s*', read.text)
            if read.confidence < .95 or dict(read.metadata).get('line_count', 1) != 1 or not match:
                return None, 'unreadable'
            pair = tuple(int(v.replace(',', '')) for v in match.groups())
            if pair[1] <= 0:
                return None, 'unreadable'
            values.append(pair)
        if values[0] != values[1]:
            return None, 'mismatch'
        return values[0][0], None

    def _pair(self, image, roi):
        value, _ = self._pair_detail(image, roi)
        return value

    def _parse_detail(self, frame):
        """Parse one frame, returning (resources|None, bounded reason)."""
        self._cancel()
        image = frame.image.copy()
        try:
            age = self.clock() - frame.timestamp
        except Exception:
            return None, 'frame_not_fresh'
        if not 0 <= age <= self.max_age:
            return None, 'frame_not_fresh'
        # Resolve the very native image being parsed, never a prior stream state.
        state = self.observer.resolver.resolve(self.observer.perception.analyze(frame))
        if state.status is not ResolutionStatus.RESOLVED:
            return None, 'context_unresolved'
        if state.base_context != 'screen.lobby':
            return None, 'context_not_lobby'
        if state.overlays:
            return None, 'overlay_incompatible'
        if not self.visuals.lobby(image):
            return None, 'lobby_visuals_rejected'
        # Backward compat for doubles stubbing _pair: map its None to a
        # generic unreadable motive (never OCR text).
        if '_pair' in self.__dict__:
            badges = self._pair(image, BADGES_ROI)
            if badges is None:
                return None, 'badges_unreadable'
            sapphires = self._pair(image, SAPPHIRES_ROI)
            if sapphires is None:
                return None, 'sapphires_unreadable'
        else:
            badges, badges_reason = self._pair_detail(image, BADGES_ROI)
            if badges is None:
                return None, ('badges_unreadable' if badges_reason == 'unreadable'
                              else 'badges_mismatch')
            sapphires, sapphires_reason = self._pair_detail(image, SAPPHIRES_ROI)
            if sapphires is None:
                return None, ('sapphires_unreadable' if sapphires_reason == 'unreadable'
                              else 'sapphires_mismatch')
        self._cancel()
        try:
            age_after = self.clock() - frame.timestamp
        except Exception:
            return None, 'post_ocr_stale'
        if not 0 <= age_after <= self.max_age:
            return None, 'post_ocr_stale'
        return ArenaFarmingResources(badges, sapphires, frame.sequence, frame.timestamp,
                                     hashlib.sha256(image.tobytes()).hexdigest()), None

    def parse(self, frame):
        reading, _ = self._parse_detail(frame)
        return reading

    def _diagnosis_summary(self, attempts, counters, last_sequence, last_age, confirmed):
        parts = [f'attempts={attempts}', f'confirmed={int(bool(confirmed))}']
        for key in sorted(counters):
            parts.append(f'{key}={counters[key]}')
        parts.append(f'last_seq={last_sequence if last_sequence is not None else "n/a"}')
        parts.append(f'age={f"{last_age:.2f}s" if isinstance(last_age, float) else "n/a"}')
        text = ' '.join(parts)
        return text[:200]

    def _read_inner(self, max_frames):
        deadline = self.clock() + self.READ_TIMEOUT
        counters = {}

        def bump(reason):
            counters[reason] = counters.get(reason, 0) + 1

        attempts = 0
        last_sequence = None
        last_age = None
        previous = None
        valid_readings = 0
        try:
            self._cancel()
            initial = self.observer.observe()
            if not is_lobby(initial):
                bump('initial_not_lobby')
                summary = self._diagnosis_summary(0, counters, None, None, False)
                self.last_diagnosis = {'attempts': 0, 'counters': dict(counters),
                                       'last_sequence': None, 'last_age': None,
                                       'confirmed': False, 'summary': summary}
                return None  # No navigation/closing from UNKNOWN.
            # Lazy OCR initialization happens before acquiring decision authority.
            self._pair(initial.frame.image, SAPPHIRES_ROI)
            cursor, timestamp = initial.sequence, initial.timestamp
            for _ in range(max_frames):
                self._cancel()
                if self.clock() >= deadline:
                    bump('deadline_expired')
                    break
                frame = self.observer.source.refresh_native(timeout=deadline-self.clock())
                attempts += 1
                last_sequence = getattr(frame, 'sequence', None)
                try:
                    last_age = self.clock() - frame.timestamp
                except Exception:
                    last_age = None
                if frame.sequence <= cursor or frame.timestamp <= timestamp:
                    bump('stale_frame')
                    continue
                cursor, timestamp = frame.sequence, frame.timestamp
                # Backward compat for doubles stubbing parse: use the stub
                # with a generic motive; production uses detailed motives.
                if 'parse' in self.__dict__:
                    reading = self.parse(frame)
                    reason = None if reading is not None else 'parse_rejected'
                else:
                    reading, reason = self._parse_detail(frame)
                self._cancel()
                if self.clock() >= deadline:
                    bump('deadline_expired')
                    break
                if reading is None:
                    bump(reason)
                    previous = None
                    continue
                valid_readings += 1
                if previous is not None and (
                        reading.badges, reading.sapphires) == (previous.badges, previous.sapphires):
                    summary = self._diagnosis_summary(attempts, counters, last_sequence,
                                                      last_age if isinstance(last_age, float) else None,
                                                      True)
                    self.last_diagnosis = {'attempts': attempts, 'counters': dict(counters),
                                           'last_sequence': last_sequence, 'last_age': last_age,
                                           'confirmed': True, 'summary': summary}
                    return reading
                if previous is not None:
                    bump('observation_disagreement')
                previous = reading
            if valid_readings:
                bump('no_consensus')
            summary = self._diagnosis_summary(attempts, counters, last_sequence,
                                              last_age if isinstance(last_age, float) else None,
                                              False)
            self.last_diagnosis = {'attempts': attempts, 'counters': dict(counters),
                                   'last_sequence': last_sequence, 'last_age': last_age,
                                   'confirmed': False, 'summary': summary}
            return None
        except RuntimeWaitCancelled:
            summary = self._diagnosis_summary(attempts, counters, last_sequence,
                                              last_age if isinstance(last_age, float) else None,
                                              False)
            self.last_diagnosis = {'attempts': attempts, 'counters': dict(counters),
                                   'last_sequence': last_sequence, 'last_age': last_age,
                                   'confirmed': False, 'summary': (summary + ' cancelled')[:200]}
            raise

    def read(self):
        return self._read_inner(self.NORMAL_MAX_FRAMES)

    def read_post_claim(self):
        """One extra passive frame after Claim; same gates, zero inputs."""
        return self._read_inner(self.POST_CLAIM_MAX_FRAMES)
