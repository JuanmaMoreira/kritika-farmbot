"""Focal Manual Stages pixels; Auto's animated border needs a temporal window."""
import json
from pathlib import Path
import cv2
import numpy as np
from bot.perception.stages import StagesDetector
from bot.observations import Observation, ObservationSource
from bot.arena_reader import crop

class ManualStagesDetector(StagesDetector):
    def __init__(self):
        super().__init__()
        root=Path(__file__).resolve().parents[1]/'assets/ui/landmarks/manual_stages'
        extra=json.loads((root/'profile.json').read_text())
        self.profile.update(extra)
        self._templates.update({k:cv2.imread(str(root/(k+'.png'))) for k in extra})
        self.asset_paths=(*self.asset_paths,root/'profile.json',*(root/(k+'.png') for k in extra))

    def toggle(self,image,name):
        on,off=self.present(image,name+'_on'),self.present(image,name+'_off')
        if name=='penance':
            on = on or self.present(image,'penance_on_relief')
        return True if on and not off else False if off and not on else None

    def config_target(self,image):
        if self.present(image,'config6') and self.present(image,'number6'):return 'chaos_06'
        if self.present(image,'config9') and self.present(image,'number9'):return 'abyssal_rion_09'
        return None

    def battle(self,image):
        return self.present(image,'battle_pause') and self.present(image,'battle_auto_text')

    def terminal(self,image):
        if self.present(image,'death_title') and self.present(image,'death_abandon'):return 'death'
        if self.present(image,'guide_title') and self.present(image,'guide_close'):return 'death_guide'
        if self.present(image,'clear_time') and self.present(image,'clear_home'):return 'clear'
        return None

    def auto_glow(self,image):
        # USER_GT: same red button for ON/OFF. The border sparkles only ON.
        # Inner text establishes the control; samples of the border are calibrated
        # on Stage captures, independently of World Boss's green-pill control.
        if not self.battle(image) or self.terminal(image):return None
        # Side sparkles only. The outer metal bevel is bright even OFF (Monk
        # timeout regression); it must not count as the animated ON signal.
        values=[]
        for roi in ((.844,.032,.854,.080),(.900,.032,.911,.080)):
            hsv=cv2.cvtColor(crop(image,roi),cv2.COLOR_BGR2HSV)
            values.append(float(np.mean((hsv[:,:,2]>235)&(hsv[:,:,1]<110))))
        return float(np.mean(values))

    def detect(self,image,*,claim_only=False):
        def obs(name,value=None):return Observation('stages.'+name,1.,ObservationSource.LOCAL_CV,value=value)
        terminal=self.terminal(image)
        if terminal:
            return (obs('surface',terminal),obs(terminal),obs('battle_base'))
        inherited=super().detect(image,claim_only=claim_only)
        layer=next((o.value for o in inherited if o.name=='stages.surface'),None)
        if layer not in {None,'normal','elite','config'}:return inherited
        target=self.config_target(image)
        if target:
            flags=[obs('surface','config'),obs('config'),obs('base'),obs('manual_target',target)]
            for name in ('support_active','support_ready','support_needs'):
                if self.present(image,name):flags.append(obs(name))
            for name in ('penance','hell',*(f'buff{i}' for i in range(1,5))):
                state=self.toggle(image,name)
                if state is not None:flags.append(obs(name+'_state',state))
            return tuple(flags)
        if self.battle(image):return (obs('surface','battle'),obs('battle_base'))
        if layer=='normal':
            extra=[]
            for name in (() if claim_only else ('chaos','stage6','stage9')):
                if self.present(image,name):extra.append(obs(name))
            state=self.toggle(image,'x4')
            if state is not None:extra.append(obs('x4_state',state))
            return (*inherited,*extra)
        return inherited

def flag(snapshot,name):
    value=snapshot.observations.best('stages.'+name+'_state')
    return value.value if value is not None else None

def auto_window_state(samples):
    """Complete focal window: side sparkle ON, flat acquired border OFF."""
    if not samples or any(value is None for _,value in samples):return None
    if len(samples)<20 or samples[-1][0]-samples[0][0]<1.9:return None
    peak=max(value for _,value in samples)
    if peak>=.025:return True
    if peak<=.015:return False
    return None

def buff_stock(engine,image,index,cancel_requested=lambda:False):
    import re
    from bot.runtime_observer import RuntimeWaitCancelled
    x=.547+(index-1)*.076
    region=crop(image,(x,.437,x+.023,.481))
    values=[]
    for value in (region,cv2.cvtColor(region,cv2.COLOR_BGR2GRAY)):
        if cancel_requested():raise RuntimeWaitCancelled('manual buff reading cancelled')
        result=engine.recognize(cv2.resize(value,None,fx=3,fy=3))
        if result.confidence<.95 or not re.fullmatch(r'\d{1,3}',result.text.strip()):return None
        values.append(int(result.text.strip()))
    return values[0] if values[0]==values[1] else None
