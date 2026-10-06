"""Paired WB facts and countdown from acquired panels, independent of Daily."""
from dataclasses import dataclass
from enum import Enum
import math
import re
import time
from bot.character_data import crop, integer_text
from bot.character_state import current_character_state
from bot.catalog import SCREEN_WORLD_BOSS, POPUP_WORLD_BOSS_PREVIOUS_REWARDS
from bot.state import ResolutionStatus

class WorldBossEligibilityMode(str, Enum):
    DAILY_QUEST = 'DAILY_QUEST'
    CURRENT_WB_NOT_PARTICIPATED = 'CURRENT_WB_NOT_PARTICIPATED'
    GENERAL = 'GENERAL'

@dataclass(frozen=True)
class WorldBossPanel:
    participated: bool | None
    previous_reward: bool | None
    remaining_seconds: int | None = None
    raw_remaining: str = ''

class WorldBossStateReader:
    def __init__(self, engine):
        self.engine = engine

    def text(self, snapshot, roi):
        result = self.engine.recognize(crop(snapshot.frame.image,roi))
        return result.text.strip() if result.confidence >= .95 and dict(result.metadata).get('line_count',1)==1 else None

    def read(self, snapshot):
        state = snapshot.state
        if POPUP_WORLD_BOSS_PREVIOUS_REWARDS in state.overlays:
            return WorldBossPanel(False,True)
        if state.status is not ResolutionStatus.RESOLVED or state.base_context != SCREEN_WORLD_BOSS or state.overlays:
            return WorldBossPanel(None,None)
        damage = self.text(snapshot,(.345,.127,.537,.167))
        rank = self.text(snapshot,(.560,.126,.800,.170))
        # Parse closed complete labels; never turn missing OCR into zero/NO.
        d = re.fullmatch(r'Most Damage\s*:\s*((?:[\d,]+)|-+)',damage or '')
        r = re.fullmatch(r'Overall Rank:\s*Rank\s+([\d]+|-+)\s*\((?:[\d.]+|-+)%\)',rank or '')
        participated = None
        if d and r:
            ds,rs = d[1],r[1]
            if ds.strip('-') == '' and rs.strip('-') == '':
                participated = False
            elif re.fullmatch(r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)',ds) and rs.isdigit() and int(rs)>0:
                participated = True
        timer = self.text(snapshot,(.672,.703,.778,.752))
        matched = re.fullmatch(r'(\d+)\s*d\s*(\d+)\s*h\s*(\d+)\s*m',timer or '')
        remaining = None
        if matched:
            days,hours,minutes = map(int,matched.groups())
            if days <= 3 and hours < 24 and minutes < 60:
                remaining = days*86400+hours*3600+minutes*60
        return WorldBossPanel(participated,False if participated is not None else None,remaining,timer or '')

class WorldBossEligibilityPolicy:
    """When to execute the single WB activity; no input or resource authorization."""
    def __init__(self, mode=WorldBossEligibilityMode.GENERAL, *, reader=None, events=None, store=None):
        self.mode,self.reader,self.events = WorldBossEligibilityMode(mode),reader,events
        self.store=store

    def known_no_work(self):
        if self.mode is not WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED:
            return None
        scope = current_character_state()
        store = self.store or (scope[0] if scope else None)
        clock = store.clock.state() if store is not None else None
        if clock and not clock['wb_open']:
            return 'wb_closed'
        if scope is None:
            return None
        store,cid = scope
        state = store.operational(cid)
        if clock and state['wb_cycle_id']==clock['wb_cycle_id'] and state['wb_participated']==1:
            return 'current_wb_participated'
        return None

    def inspect(self, snapshot):
        if self.reader is None:
            return None
        try:
            panel = self.reader.read(snapshot)
        except Exception as error:
            if self.events is not None:
                self.events.record('character_state.wb_observation_failure',error=str(error))
            return None if self.mode is WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED else True
        scope = current_character_state()
        store = self.store or (scope[0] if scope else None)
        if store is not None:
            # Countdown is minute resolution. Project to the next minute
            # boundary; never hardcode a local timezone/hour.
            observed = store.now() - max(0,time.monotonic()-snapshot.timestamp)
            if panel.remaining_seconds is not None:
                remaining = math.ceil((observed+panel.remaining_seconds)/60)*60-observed
                store.clock.calibrate(remaining,observed_at=observed,raw_remaining=panel.raw_remaining,precision_seconds=60)
            clock = store.clock.state()
            if self.mode is WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED and clock and not clock['wb_open']:
                return False
        if scope is not None:
            store,cid=scope
            if panel.participated is not None:
                store.wb(cid,panel.participated,source='WB_PANEL',previous_reward=panel.previous_reward)
                if self.mode is WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED and store.operational(cid)['wb_participated']==1:
                    return False
        if self.mode is WorldBossEligibilityMode.CURRENT_WB_NOT_PARTICIPATED:
            return None if panel.participated is None else not panel.participated
        return True
