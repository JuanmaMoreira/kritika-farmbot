"""Focal informational Quick Menu reader and explicit pre-rotation collector."""
from enum import Enum
import re
import time

from bot.catalog import MENU_QUICK, SCREEN_LOBBY
from bot.geometry import relative_region_to_pixels
from bot.state import ResolutionStatus
from bot.character_state import current_character_state, utc_now

class ResourceSnapshotMode(str, Enum):
    OFF = 'OFF'
    BEFORE_CHARACTER_ROTATION = 'BEFORE_CHARACTER_ROTATION'

# Calibrated number-only regions; second top-row currency is K Coins.
# The third top-row field (Mao Coins) is deliberately outside this snapshot.
RESOURCE_ROIS = {
    'lapiz': (.075, .884, .125, .920),
    'k_coins': (.150, .884, .211, .920),
    'dark_essence': (.075, .954, .125, .995),
    'light_essence': (.160, .954, .211, .995),
    'nature_essence': (.245, .954, .296, .995),
}

def crop(image, roi):
    h,w = image.shape[:2]
    x1,y1,x2,y2 = relative_region_to_pixels(roi,w,h)
    return image[y1:y2,x1:x2].copy()

def integer_text(result):
    if result.confidence < .95 or dict(result.metadata).get('line_count',1) != 1:
        return None
    text = result.text.strip()
    if not re.fullmatch(r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)', text):
        return None
    return int(text.replace(',',''))

class QuickMenuResourceReader:
    def __init__(self, engine, *, events=None):
        self.engine,self.events = engine,events

    def read(self, snapshot, *, origin):
        state = snapshot.state
        if (state.status not in (ResolutionStatus.UNKNOWN, ResolutionStatus.RESOLVED)
                or set(state.overlays) != {MENU_QUICK}):
            return None
        shift = 0 if origin == SCREEN_LOBBY else .130
        values = {}
        for key, roi in RESOURCE_ROIS.items():
            roi = (roi[0]+shift,roi[1],roi[2]+shift,roi[3])
            region = crop(snapshot.frame.image,roi)
            reading = self.engine.recognize(region)
            value = integer_text(reading)
            if value is None:
                # Five acquired short-number variants need more black margin.
                # One same-frame padded read must agree AND pass the original gate.
                import cv2
                padding=max(1,round(region.shape[0]*.16))
                candidate = self.engine.recognize(cv2.copyMakeBorder(region,padding,padding,padding,padding,cv2.BORDER_CONSTANT))
                if candidate.text.strip() == reading.text.strip():
                    value = integer_text(candidate)
                if value is not None and self.events is not None:
                    self.events.record('character_state.resource_reading_padded',field=key,
                        raw_text=reading.text,confidence=reading.confidence,
                        padded_confidence=candidate.confidence,source_sequence=snapshot.sequence)
            if value is None:
                if self.events is not None:
                    self.events.record('character_state.resource_reading_unreadable',field=key,
                        raw_text=reading.text,confidence=reading.confidence,roi=roi,
                        source_sequence=snapshot.sequence)
                return None
            values[key] = value
        return values

class CharacterDataCollector:
    def __init__(self, reader, *, events, mode=ResourceSnapshotMode.BEFORE_CHARACTER_ROTATION,
                 now=utc_now, failure_directory=None):
        self.reader,self.events,self.mode,self.now = reader,events,ResourceSnapshotMode(mode),now
        self.failure_directory = failure_directory

    def before_rotation(self, snapshot, *, origin):
        if self.mode is ResourceSnapshotMode.OFF:
            return
        started = time.perf_counter()
        scope = current_character_state()
        if scope is None:
            self.events.record('character_state.resources_skipped',reason='identity_unknown')
            return False
        store,cid = scope
        try:
            at = self.now()
            values = self.reader.read(snapshot,origin=origin)
            if values is None or not store.resources(cid,values,observed_at=at):
                evidence = self._unreadable_evidence(snapshot,cid)
                self.events.record('character_state.resources_failure', character_id=cid, reason='unreadable',
                    evidence=evidence,source_sequence=snapshot.sequence)
                return False
            else:
                self.events.record('character_state.resource_snapshot_timing',character_id=cid,
                                   duration=time.perf_counter()-started, source_sequence=snapshot.sequence)
                return True
        except Exception as error:
            self.events.record('character_state.resources_failure',character_id=cid,error=str(error))
            return False

    def _unreadable_evidence(self,snapshot,cid):
        if self.failure_directory is None:
            return None
        # Diagnostic only, no second capture/perception and no success-path I/O.
        try:
            import cv2
            from pathlib import Path
            from uuid import uuid4
            root=Path(self.failure_directory)
            root.mkdir(parents=True,exist_ok=True)
            path=root/f'{cid}_{snapshot.sequence}_{uuid4().hex[:8]}.png'
            return str(path) if cv2.imwrite(str(path),snapshot.frame.image) else None
        except Exception:
            return None
