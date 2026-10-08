"""Focal Meteorites perception; one image has no temporal or input authority."""
import re
from pathlib import Path

import cv2
import numpy as np

from bot.equipment_sell_reader import parse_page
from bot.meteorites_semantics import (
    BAG_POINTS, SLOT_POINTS, MeteoriteAction, MeteoriteItem, MeteoritesBag,
    SlotState, METEORITES_MAIN, METEORITES_DETAIL, METEORITES_LOADING,
)
from bot.observations import Observation, ObservationSource

DETAIL_ROI = (.508,.302,.517,.704)
ACTION_ROI = (.197,.274,.246,.390)
TITLE_ROI = (.278,.249,.505,.287)
LEVEL_ROI = (.271,.687,.317,.728)
PAGE_ROI = (.652,.883,.708,.949)
TAB_ROIS = {'Meteorites':(.171,.148,.257,.228),'Combine':(.258,.148,.338,.228),
            'Evolve':(.343,.148,.423,.228),'Reforge':(.429,.148,.509,.228),
            'Reroll':(.515,.148,.595,.228)}


def crop(frame, roi):
    h,w=frame.shape[:2]
    x1,y1,x2,y2=roi
    return frame[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]


def normalize(frame):
    if not isinstance(frame,np.ndarray) or frame.ndim != 3 or frame.dtype != np.uint8:
        raise ValueError('expected BGR uint8 frame')
    return cv2.resize(frame,(1356,612),interpolation=cv2.INTER_AREA)


def core(frame, point):
    x,y=point
    return crop(frame,(x-.014,y-.006,x+.016,y+.046)).copy()


def correlation(a,b):
    if a is None or b is None or not a.size or not b.size:
        return -1.
    a=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY) if a.ndim==3 else a
    b=cv2.cvtColor(b,cv2.COLOR_BGR2GRAY) if b.ndim==3 else b
    if a.shape != b.shape:
        a=cv2.resize(a,(b.shape[1],b.shape[0]))
    # Glare/level alternation is excluded from these sprite cores.
    a=cv2.copyMakeBorder(a,3,3,3,3,cv2.BORDER_REPLICATE)
    return float(cv2.matchTemplate(a,b,cv2.TM_CCOEFF_NORMED).max())


def sprite_score(frame,point,sprite):
    """Local alignment of the glyph core, excluding level/lock/E authority."""
    x,y=point
    search=cv2.cvtColor(crop(frame,(x-.022,y-.024,x+.024,y+.064)),cv2.COLOR_BGR2GRAY)
    template=cv2.cvtColor(sprite,cv2.COLOR_BGR2GRAY)
    scores=[]
    for scale in (.95,1.,1.05):
        t=cv2.resize(template,None,fx=scale,fy=scale)
        if t.shape[0]<=search.shape[0] and t.shape[1]<=search.shape[1]:
            scores.append(float(cv2.matchTemplate(search,t,cv2.TM_CCOEFF_NORMED).max()))
    return max(scores,default=-1.)


def parse_title(text):
    """Exact focal grammar; missing/garbled suffix does not prove level zero."""
    match=re.fullmatch(r'\s*(?:[x×※�]|[^A-Za-z0-9+])*\s*(Ethereal\+?)\s+Meteorite\s+'
                       r'(Flare\s*\(ATK\)|\([A-Za-z ]+\))\s*(?:\+(\d+)|MAX)?\s*(?:[x×※�]|[^A-Za-z0-9+])*',text,re.I)
    if not match:
        return None
    tier='Ethereal+' if '+' in match[1] else 'Ethereal'
    level=int(match[3]) if match[3] is not None else (30 if re.search(r'MAX',text,re.I) else None)
    if level is not None and not 0<=level<=30:
        return None
    return match[2].lower().startswith('flare'),tier,level


class MeteoritesReader:
    def __init__(self, engine=None, *, asset_root=None):
        root=Path(asset_root) if asset_root is not None else Path(__file__).resolve().parents[1]
        self.templates={p.stem:cv2.imread(str(p)) for p in (root/'assets/meteorites').glob('*.png')}
        required={'main_bag_header','detail_border','equip','unequip','check','check1',
                  'flare','flare_glare','ethereal','ethereal_detail','ethereal_level',
                  'ethereal_equipped','ethereal_plus','ethereal_plus_equipped','badge_e'}
        required|={f'empty_{i}' for i in range(11)}
        required|={'tab_'+name.lower() for name in TAB_ROIS}
        if any(self.templates.get(k) is None for k in required):
            raise FileNotFoundError('Meteorites runtime assets missing')
        self.engine=engine
        self.calls=dict(detector=0,ocr=0,cv_match=0)

    def score(self,f,name,roi):
        self.calls['cv_match']+=1
        x1,y1,x2,y2=roi
        search=cv2.cvtColor(crop(f,(max(0,x1-.004),max(0,y1-.010),min(1,x2+.004),min(1,y2+.010))),cv2.COLOR_BGR2GRAY)
        template=cv2.cvtColor(self.templates[name],cv2.COLOR_BGR2GRAY)
        if search.shape[0]<template.shape[0] or search.shape[1]<template.shape[1]:
            return -1.
        return float(cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED).max())

    def main(self,f):
        self.calls['detector']+=1
        return self.score(f,'main_bag_header',(.558,.231,.671,.279))>=.94

    def detail(self,f):
        self.calls['detector']+=1
        return self.score(f,'detail_border',DETAIL_ROI)>=.94

    def loading(self,f):
        self.calls['detector']+=1
        hsv=cv2.cvtColor(crop(f,(.490,.478,.509,.524)),cv2.COLOR_BGR2HSV)
        # Curated spinner always has cyan interior in this otherwise dark gap.
        return float(np.mean((hsv[:,:,0]>=80)&(hsv[:,:,0]<=110)&(hsv[:,:,1]>110)&(hsv[:,:,2]>65)))>.10

    def active_set(self,f):
        self.calls['detector']+=1
        scores=[]
        for dx in (-.050,0,.052):
            roi=(.239+dx,.241,.255+dx,.264)
            scores.append(max(self.score(f,n,roi) for n in ('check','check1')))
        ranked=sorted(enumerate(scores,1),key=lambda v:v[1],reverse=True)
        return ranked[0][0] if ranked[0][1]>=.87 and ranked[0][1]-ranked[1][1]>=.12 else None

    def tab_sample(self,frame):
        self.calls['detector']+=1
        f=normalize(frame)
        scores={tab:self.score(f,'tab_'+tab.lower(),roi) for tab,roi in TAB_ROIS.items()}
        ranked=sorted(scores,key=scores.get,reverse=True)
        return ranked[0] if scores[ranked[0]]>=.96 and scores[ranked[0]]-scores[ranked[1]]>=.03 else None

    def slots(self,f):
        self.calls['detector']+=1
        result=[]
        for i,(x,y) in enumerate(SLOT_POINTS):
            roi=(x-.017,y-.028,x+.017,y+.028)
            img=crop(f,roi)
            hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
            red=np.mean(((hsv[:,:,0]<12)|(hsv[:,:,0]>168))&(hsv[:,:,1]>110)&(hsv[:,:,2]>110))
            light=np.mean(hsv[:,:,2]>140)
            if red>.16 or light>.35:
                result.append(SlotState.OCCUPIED)
            elif self.score(f,'empty_'+str(i),roi)>=.92:
                result.append(SlotState.EMPTY)
            else:
                result.append(SlotState.UNKNOWN)
        return tuple(result)

    def _read(self,f,roi):
        if self.engine is None:
            return '',0.
        self.calls['ocr']+=1
        img=crop(f,roi)
        r=self.engine.recognize(cv2.resize(img,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC))
        return r.text,r.confidence

    def bag_sample(self,frame,*,sequence,observed_at,read_page=True):
        f=normalize(frame)
        if not self.main(f):
            return None
        overlay=self.detail(f)
        loading=self.loading(f)
        page=None
        if read_page and not loading:
            text,confidence=self._read(f,PAGE_ROI)
            page=parse_page(text) if confidence>=.80 else None
        return MeteoritesBag(sequence,observed_at,self.active_set(f),
                             page[0] if page else None,page[1] if page else None,
                             self.slots(f) if not overlay else (SlotState.UNKNOWN,)*11,loading,overlay)

    def action(self,f):
        self.calls['detector']+=1
        scores={a:self.score(f,a.value,ACTION_ROI) for a in MeteoriteAction}
        ranked=sorted(scores,key=scores.get,reverse=True)
        return ranked[0] if scores[ranked[0]]>=.91 and scores[ranked[0]]-scores[ranked[1]]>=.12 else None

    def flare(self,img):
        self.calls['detector']+=1
        score=max(correlation(img,self.templates[n]) for n in ('flare','flare_glare'))
        return True if score>=.78 else (False if score<=.68 else None)

    def tier(self,f,point):
        self.calls['detector']+=1
        x,y=point
        roi=(x-.025,y-.066,x+.014,y-.045)
        plus=max(self.score(f,n,roi) for n in ('ethereal_plus','ethereal_plus_equipped'))
        base=max(self.score(f,n,roi) for n in ('ethereal','ethereal_detail','ethereal_level','ethereal_equipped'))
        if plus>=.84 and plus-base>=.12:
            return 'Ethereal+'
        if base>=.87 and base-plus>=.12:
            return 'Ethereal'
        return None

    def candidate(self,frame,cell):
        if type(cell) is not int or not 0<=cell<16:
            raise ValueError('cell must be 0..15')
        f=normalize(frame)
        if not self.main(f) or self.detail(f) or self.loading(f):
            return None
        point=BAG_POINTS[cell]
        sprite=core(f,point)
        flare=self.flare(sprite)
        tier=self.tier(f,point)
        return (sprite,flare,tier) if flare is not None and tier is not None else None

    def equipped_badge(self,frame,cell):
        self.calls['detector']+=1
        f=normalize(frame);x,y=BAG_POINTS[cell]
        return self.score(f,'badge_e',(x-.026,y-.067,x-.008,y-.029))>=.90

    def detail_sample(self,frame,*,sequence,observed_at):
        f=normalize(frame)
        if not self.main(f) or not self.detail(f) or self.loading(f):
            return None
        action=self.action(f)
        parsed_text,confidence=self._read(f,TITLE_ROI)
        parsed=parse_title(parsed_text) if confidence>=.80 else None
        self.diagnostic=dict(title=parsed_text,confidence=confidence,action=action)
        if parsed is None or action is None:
            return None
        flare,tier,level=parsed
        visual_flare=self.flare(core(f,(.306,.372)))
        visual_tier=self.tier(f,(.306,.372))
        if flare is not visual_flare or tier != visual_tier:
            return None
        if level is None:
            text,conf=self._read(f,LEVEL_ROI)
            self.diagnostic.update(level_text=text,level_confidence=conf,visual_tier=visual_tier)
            if conf>=.80 and re.fullmatch(r'\s*\+0\s*',text):
                level=0
            elif conf>=.80 and text.strip().lower()=='max':
                level=30
            else:
                return None
        return MeteoriteItem(flare,tier,level,action,sequence,observed_at)


class MeteoritesDetector:
    """Main structural landmark is negative on all four sibling tab views."""
    def __init__(self,*,asset_root=None):
        root=Path(asset_root) if asset_root is not None else Path(__file__).resolve().parents[1]
        self.asset_paths=tuple(sorted((root/'assets/meteorites').glob('*.png')))
        # Keep the mutable diagnostic reader out of incremental cache config.
        self._reader=MeteoritesReader(asset_root=root)

    def detect(self,frame):
        f=normalize(frame)
        if not self._reader.main(f):
            return ()
        names=[METEORITES_MAIN]
        if self._reader.detail(f):
            names.append(METEORITES_DETAIL)
        if self._reader.loading(f):
            names.append(METEORITES_LOADING)
        return tuple(Observation(n,.99,ObservationSource.LOCAL_CV) for n in names)
