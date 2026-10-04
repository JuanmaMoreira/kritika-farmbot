"""Demand-driven variable balances; two fresh agreeing frames."""
import re
import time
from dataclasses import dataclass
from bot.geometry import relative_region_to_pixels
from bot.stages_runtime import lobby
from bot.sapphire_pressure import sapphire_pressure_passes

@dataclass(frozen=True)
class StageBalances:
    stamina:int
    sapphires:int
    sapphire_limit:int
    snapshot:object
    @property
    def needs_monster_wave(self):
        return sapphire_pressure_passes(self.sapphires, pressure_limit=self.sapphire_limit) > 0

class StagesBalanceReader:
    def __init__(self,navigation,engine):self.nav,self.engine=navigation,engine
    def text(self,s,roi):
        f=s.frame.image;h,w=f.shape[:2];x1,y1,x2,y2=relative_region_to_pixels(roi,w,h)
        r=self.engine.recognize(f[y1:y2,x1:x2].copy())
        if r.confidence<.85:raise ValueError('stages balance OCR inconclusive')
        return r.text
    def pair(self,s,roi):
        text=self.text(s,roi)
        text=text.strip()
        if text.startswith('(') and text.endswith(')'):text=text[1:-1]
        m=re.fullmatch(r'\s*(\d[\d,]*)\s*/\s*(\d[\d,]*)\s*',text)
        if not m:raise ValueError('stages balance pair unverified')
        pair=tuple(int(x.replace(',','')) for x in m.groups())
        if pair[1]<=0:raise ValueError('stages capacity invalid')
        return pair
    def read(self):
        previous=None;last_error=None
        for _ in range(3):
            s=self.nav.wait(lobby)
            try:
                stamina=self.pair(s,(.785,.302,.847,.34))[0]
                sapphires,limit=self.pair(s,(.787,.455,.849,.494))
            except ValueError as e:last_error=e;previous=None;continue
            values=(stamina,sapphires,limit)
            if previous==values:return StageBalances(*values,s)
            previous=values
        raise ValueError('stages fresh balance consensus unavailable') from last_error
