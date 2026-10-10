"""Optional total VP from Arena selection; never a gameplay authority."""
import re
import time
import cv2
import numpy as np
from pathlib import Path
from bot.arena_reader import crop
from bot.character_state import current_character_state
from bot.event_log import record_best_effort

# Curated Arena BASE selection frames, 2026-10-08. Label included to reject
# partial/contaminated numbers and Acquired Victory Points from the final modal.
VICTORY_POINTS_ROI = (.489, .228, .633, .270)

def parse_victory_points(text, confidence):
    number = r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)'
    match = re.fullmatch(rf'\s*Victory Point(?:\(s\)|s)?\s*:\s*({number})\s*',text)
    if confidence < .95 or match is None:
        return None
    return int(match[1].replace(',',''))

class ArenaVictoryPointReader:
    def __init__(self, engine, *, clock=time.monotonic):
        self.engine,self.clock=engine,clock
        root=Path(__file__).resolve().parents[1]/'assets/arena'
        self.backdrop=cv2.imread(str(root/'vp_backdrop.png'))
        self.mask=cv2.imread(str(root/'vp_backdrop_mask.png'),cv2.IMREAD_GRAYSCALE)

    def read(self, frame, visuals, *, cancel_requested=lambda:False):
        if (cancel_requested() or not 0 <= self.clock()-frame.timestamp <= 4.
                or not visuals.selection(frame.image) or visuals.ranking(frame.image)
                or visuals.quick_menu(frame.image)):
            return None
        region=crop(frame.image,VICTORY_POINTS_ROI)
        values=[]
        # No geometric chat exclusion: attempt OCR even when ROI intersects it.
        for prepared in (region,cv2.cvtColor(region,cv2.COLOR_BGR2GRAY)):
            if cancel_requested():return None
            result=self.engine.recognize(cv2.resize(prepared,None,fx=3,fy=3))
            value=parse_victory_points(result.text,result.confidence)
            if dict(result.metadata).get('line_count',1)!=1 or value is None:return None
            values.append(value)
        # A perfectly readable prefix can survive an occluder. Credit the
        # exposed row's backdrop as well, excluding label/variable glyphs.
        # This is evaluated AFTER attempting OCR, never a chat intersection gate.
        if self.backdrop is None or self.mask is None:return None
        resized=cv2.resize(region,(self.backdrop.shape[1],self.backdrop.shape[0]))
        error=np.abs(resized.astype(float)-self.backdrop.astype(float))[self.mask>0].mean()/255.
        if error > .04:return None
        if (cancel_requested() or not 0 <= self.clock()-frame.timestamp <= 4.
                or values[0]!=values[1]):return None
        return values[0]

    def observe_character(self, frame, visuals, *, cancel_requested=lambda:False, events=None):
        scope=current_character_state()
        if scope is None:return
        store,cid=scope
        # Capture time, not completion time: a delayed OCR cannot cross reset.
        at=store.now()-(self.clock()-frame.timestamp)
        period=store.clock.arena_period(at)
        try:
            value=self.read(frame,visuals,cancel_requested=cancel_requested)
            if value is not None:
                store.arena_victory_points(cid,value,observed_at=at,period=period)
        except Exception as error:
            record_best_effort(events,'arena.vp_omitted',reason=type(error).__name__)
