"""Focal Arena CV and result OCR. None is UNKNOWN; no number is accumulated."""
import hashlib
import json
import math
from pathlib import Path
import re
import time

import cv2
import numpy as np

from bot.arena_semantics import (
    ARENA_ACTIVE, ARENA_CHALLENGE, ARENA_CONFIG, ARENA_INSUFFICIENT,
    ARENA_RANKING, ARENA_RESULT, ARENA_SELECT, ArenaBatchExecution,
    ArenaBatchResult, ArenaDifficulty, ArenaPreparationFacts, ArenaResultProvenance,
    ARENA_SINGLE_RESULT, ARENA_BATTLE, ARENA_MODE_SELECT,
)
from bot.capture import FrameSnapshot
from bot.controlled_wait import ControlledWait
from bot.observations import Observation, ObservationSource

USED_ROI = (.439, .320, .490, .359)
WON_ROI = (.443, .615, .493, .672)


def crop(frame, roi):
    h, w = frame.shape[:2]
    l, t, r, b = roi
    return frame[round(t*h):round(b*h), round(l*w):round(r*w)]


def parse_integer(text, confidence, *, minimum_confidence=.95):
    """Strict single integer. No confusables, partial strings or missing-zero."""
    text = text.strip()
    if confidence < minimum_confidence or not re.fullmatch(r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)', text):
        return None
    return int(text.replace(',', ''))


class ArenaVisuals:
    """Preloaded semantic crops, scaled using each frame's own shape.

    Match corresponding regions (including positive OFF assets), not absence of
    a check. The asset manifest owns geometry, source hashes and thresholds.
    """
    def __init__(self, *, asset_root=None):
        root = Path(asset_root) if asset_root is not None else Path(__file__).resolve().parents[1]
        data = json.loads((root/'datasets/arena_visual_assets_manifest.json').read_text(encoding='utf8'))
        self._specs = {s['id']: s for s in data['assets']}
        self.asset_paths = tuple(root/s['path'] for s in data['assets'])
        self._templates = {}
        for spec, path in zip(data['assets'], self.asset_paths):
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(path)
            self._templates[spec['id']] = image
        self._calls = 0

    def score(self, frame, name):
        self._calls += 1
        template = self._templates[name]
        roi = self._specs[name]['roi']
        l, t, r, b = roi
        inner = crop(frame, roi)
        observed = crop(frame, (max(0,l-.004), max(0,t-.006), min(1,r+.004), min(1,b+.006)))
        if not observed.size:
            return -1.
        observed = cv2.resize(observed, None, fx=template.shape[1]/inner.shape[1],
                              fy=template.shape[0]/inner.shape[0], interpolation=cv2.INTER_AREA)
        if name == 'auto_band':
            # Yellow glyphs stay fixed while transparent battle backgrounds and
            # the animated border vary. No OCR or absence-based completion.
            observed = cv2.inRange(cv2.cvtColor(observed, cv2.COLOR_BGR2HSV), (22,120,150), (40,255,255))
            template = cv2.inRange(cv2.cvtColor(template, cv2.COLOR_BGR2HSV), (22,120,150), (40,255,255))
        return float(cv2.matchTemplate(observed, template, cv2.TM_CCOEFF_NORMED).max())

    def has(self, frame, name):
        return self.score(frame, name) >= self._specs[name]['threshold']

    def numbers_intact(self, frame):
        # A black/corrupt tail can leave a plausible high-confidence prefix.
        # Check the credited dark padding beside BOTH fields in absolute color;
        # NCC on constant backgrounds would incorrectly match a black rectangle.
        for name in ('used_padding', 'won_padding'):
            observed = crop(frame, self._specs[name]['roi'])
            reference = np.median(self._templates[name].reshape(-1,3), axis=0)
            error = np.abs(observed.astype(float)-reference).max(axis=2)
            if np.percentile(error,90) > self._specs[name]['max_color_error']:
                return False
        return True

    def terminal(self, frame):
        # Shared title is only one part. Never inspect Victory Points.
        return all(self.has(frame, n) for n in
                   ('result_title', 'badge_label', 'karats_label', 'result_panel', 'result_ok'))

    def config(self, frame):
        return self.has(frame, 'config_text') and self.has(frame, 'config_start')

    def selection(self, frame):
        return all(self.has(frame, 'select_'+n) for n in ('easy', 'normal', 'hard'))

    def challenge(self, frame):
        return self.has(frame, 'challenge_controls') and self.has(frame, 'challenge_vs')

    def active(self, frame):
        return self.has(frame, 'battle_vs') and self.has(frame, 'auto_band')

    def ranking(self, frame):
        return self.has(frame, 'ranking') and self.has(frame, 'ranking_arena')

    def toggle(self, frame, prefix):
        scores = {state: self.score(frame, prefix+'_'+state) for state in ('on', 'off')}
        winner = max(scores, key=scores.get)
        threshold = self._specs[prefix+'_'+winner]['threshold']
        return (winner == 'on') if scores[winner] >= threshold and abs(scores['on']-scores['off']) >= .08 else None

    def preparation(self, frame):
        if (not self.challenge(frame) or self.config(frame) or self.terminal(frame)
                or self.has(frame, 'insufficient') or self.has(frame, 'bag_full')):
            return ArenaPreparationFacts(None, (None, None, None), None)
        scores = {d: self.score(frame, 'difficulty_'+d.value.lower()) for d in ArenaDifficulty}
        order = sorted(scores, key=scores.get, reverse=True)
        difficulty = order[0] if scores[order[0]] >= .90 and scores[order[0]]-scores[order[1]] >= .08 else None
        return ArenaPreparationFacts(difficulty, tuple(self.toggle(frame, f'buff{i}') for i in (1, 2, 3)),
                                     self.toggle(frame, 'x8'))

    def upon_defeat(self, frame):
        # Only OFF was acquired. A miss cannot establish ON.
        return False if self.config(frame) and self.has(frame, 'upon_defeat_off') else None


class ArenaDetector:
    """Default catalog detector; zero OCR and acquired B2 physical contexts.

    Select and Challenge are the same non-battle BASE. Modal signals do not
    fabricate the occluded BASE. B2 USER_GT credits a separate battle BASE and
    Single result overlay; Arena Select Mode is independent of Survival.
    """
    def __init__(self, *, asset_root=None):
        from bot.arena_flow_reader import ArenaFlowVisuals
        self._visuals = ArenaFlowVisuals(asset_root=asset_root)
        self.asset_paths = self._visuals.asset_paths + (Path(asset_root or Path(__file__).resolve().parents[1])/'datasets/arena_visual_assets_manifest.json',)

    def detect(self, frame):
        checks = ((ARENA_SELECT, self._visuals.selection), (ARENA_CHALLENGE, self._visuals.challenge),
                  (ARENA_CONFIG, self._visuals.config), (ARENA_RESULT, self._visuals.terminal),
                  (ARENA_INSUFFICIENT, lambda f: self._visuals.has(f, 'insufficient')),
                  (ARENA_RANKING, self._visuals.ranking),
                  (ARENA_ACTIVE, self._visuals.active),
                  (ARENA_SINGLE_RESULT, self._visuals.single_result),
                  (ARENA_MODE_SELECT, self._visuals.select_mode),
                  (ARENA_BATTLE, lambda f:self._visuals.active(f) or self._visuals.single_active(f) or self._visuals.single_result(f)))
        observations = [Observation(name, 1., ObservationSource.LOCAL_CV) for name, test in checks if test(frame)]
        if any(o.name in (ARENA_SELECT, ARENA_CHALLENGE) for o in observations):
            observations.append(Observation('landmark.arena_base', 1., ObservationSource.LOCAL_CV))
        if any(o.name == ARENA_CHALLENGE for o in observations):
            preparation = self._visuals.preparation(frame)
            if preparation.difficulty is not None:
                observations.append(Observation('fact.arena_difficulty', 1., ObservationSource.LOCAL_CV, preparation.difficulty.value))
            for name, value in zip(('fact.arena_buff1', 'fact.arena_buff2', 'fact.arena_buff3', 'fact.arena_x8'),
                                   (*preparation.buffs, preparation.x8)):
                if value is not None:
                    observations.append(Observation(name, 1., ObservationSource.LOCAL_CV, value))
        if any(o.name == ARENA_CONFIG for o in observations):
            value = self._visuals.upon_defeat(frame)
            if value is not None:
                observations.append(Observation('fact.arena_upon_defeat', 1., ObservationSource.LOCAL_CV, value))
        return tuple(observations)


class ArenaResultReader:
    def __init__(self, engine, *, visuals=None, asset_root=None, max_age=2., clock=time.monotonic):
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('positive finite max_age required')
        self.engine = engine
        self.visuals = visuals or ArenaVisuals(asset_root=asset_root)
        self.max_age = max_age
        self.clock = clock
        self.ocr_calls = 0

    def fresh(self, snapshot, execution, *, run_id, source_id):
        return (isinstance(snapshot, FrameSnapshot) and isinstance(execution, ArenaBatchExecution)
                and execution.start_verified is True
                and isinstance(execution.difficulty, ArenaDifficulty)
                and type(execution.multiplier) is int and execution.multiplier == 8
                and execution.run_id == run_id and execution.source_id == source_id
                and snapshot.sequence > execution.after_sequence
                and snapshot.timestamp > execution.started_at
                and math.isfinite(snapshot.timestamp)
                and 0 <= self.clock()-snapshot.timestamp <= self.max_age)

    def terminal(self, snapshot, execution, *, run_id, source_id):
        return (self.fresh(snapshot, execution, run_id=run_id, source_id=source_id)
                and self.visuals.terminal(snapshot.image))

    def _integer(self, frame, roi, cancel_requested):
        image = crop(frame, roi)
        values = []
        confidence = 1.
        # Independent preprocessing agreement supplements grammar/confidence.
        # It never rescues a failed structural gate or treats plausibility as GT.
        for prepared in (image, cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)):
            if cancel_requested():
                return None, 0.
            self.ocr_calls += 1
            result = self.engine.recognize(cv2.resize(prepared, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC))
            if dict(result.metadata).get('line_count', 1) != 1:
                return None, 0.
            value = parse_integer(result.text, result.confidence)
            if value is None:
                return None, result.confidence
            confidence = min(confidence, result.confidence)
            values.append(value)
        return (values[0], confidence) if values[0] == values[1] else (None, confidence)

    def read(self, snapshot, execution, *, run_id, source_id, cancel_requested=lambda: False):
        if cancel_requested() or not self.fresh(snapshot, execution, run_id=run_id, source_id=source_id):
            return None
        # All gates and both fields use an immutable local image copy. No cache,
        # consensus across frames, or field injection API can mix observations.
        frame = snapshot.image.copy()
        if not self.visuals.terminal(frame) or not self.visuals.numbers_intact(frame):
            return None
        used, used_confidence = self._integer(frame, USED_ROI, cancel_requested)
        if used is None or used <= 0:
            return None
        won, won_confidence = self._integer(frame, WON_ROI, cancel_requested)
        if won is None or not 0 <= won <= used or cancel_requested():
            return None
        # OCR lazy load/time spent never extends capture freshness.
        if not self.fresh(snapshot, execution, run_id=run_id, source_id=source_id):
            return None
        provenance = ArenaResultProvenance(run_id, source_id, snapshot.sequence,
                                           hashlib.sha256(frame.tobytes()).hexdigest(),
                                           used_confidence, won_confidence)
        return ArenaBatchResult(execution.difficulty, execution.multiplier, used, won,
                                snapshot.timestamp, provenance)

    def wait_terminal(self, observe, execution, *, run_id, source_id, timeout,
                      cancel_requested=lambda: False, wait=None):
        """Passive positive-terminal wait; bounded, cancelable, no economic input.

        observe returns FrameSnapshot from the named lifetime. It may perform the
        existing native refresh after ambiguous stream data. This method does no
        global perception/OCR and does not cancel a physically running batch.
        Caller reads the returned snapshot (or a fresh replacement) separately.
        """
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('positive finite timeout required')
        waiter = wait or ControlledWait(check_interval=3., clock=self.clock, label='arena.terminal')
        bound = self.clock()+timeout
        latest = None
        last_sequence = execution.after_sequence
        last_timestamp = execution.started_at

        def complete():
            nonlocal latest, last_sequence, last_timestamp
            if cancel_requested() or self.clock() >= bound:
                return False
            snapshot = observe()
            if cancel_requested() or self.clock() >= bound:
                return False
            if snapshot.sequence <= last_sequence or snapshot.timestamp <= last_timestamp:
                return False
            last_sequence, last_timestamp = snapshot.sequence, snapshot.timestamp
            if self.terminal(snapshot, execution, run_id=run_id, source_id=source_id):
                latest = snapshot
                return True
            return False

        result = waiter.wait(deadline=bound, completion_condition=complete, cancel_requested=cancel_requested)
        return result, latest
