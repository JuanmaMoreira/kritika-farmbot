"""Native fixed chrome for ads-only Stages; no OCR of constant labels."""
from pathlib import Path
import json
import cv2
import numpy as np
from bot.observations import Observation, ObservationSource

class StagesDetector:
    def __init__(self, asset_root=None):
        root=Path(asset_root or Path(__file__).resolve().parents[2])/'assets/ui/landmarks/stages'
        self.profile=json.loads((root/'profile.json').read_text())
        self.asset_paths=(root/'profile.json',*(root/(k+'.png') for k in self.profile))
        self._templates={k:cv2.imread(str(root/(k+'.png'))) for k in self.profile}
        if any(t is None for t in self._templates.values()):
            raise ValueError('stages asset unavailable')

    def score(self, frame, name, *, undimmed=True):
        h,w=frame.shape[:2];p=self.profile[name];x1,y1,x2,y2=p['search']
        search=frame[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]
        c=p['crop'];tw=round(c[2]*w)-round(c[0]*w)
        # scrcpy aligns native capture height by four pixels. Text rendering
        # scale follows width; stretching fonts to that padding breaks NCC.
        th=round(self._templates[name].shape[0]*tw/self._templates[name].shape[1])
        template=cv2.resize(self._templates[name],(tw,th))
        if search.shape[0]<th or search.shape[1]<tw:return 0.
        if name in {'support_needs','support_ready'}:
            scores=cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED)
        else:
            scores=cv2.matchTemplate(cv2.cvtColor(search,cv2.COLOR_BGR2GRAY),cv2.cvtColor(template,cv2.COLOR_BGR2GRAY),cv2.TM_CCOEFF_NORMED)
        _,score,_,pos=cv2.minMaxLoc(scores)
        matched=search[pos[1]:pos[1]+th,pos[0]:pos[0]+tw]
        # NCC is brightness invariant. A lower modal's dimmed title must not
        # authorize tapping through the upper modal.
        if undimmed and matched.mean()<template.mean()*.80:return 0.
        return float(score)

    def present(self,frame,name):return name in self._templates and self.score(frame,name)>=.94

    def detect(self,frame):
        def obs(name,value=None):return Observation('stages.'+name,1.,ObservationSource.LOCAL_CV,value=value)
        if self.present(frame,'loading'):return (obs('loading'),)
        # Upper layers first. Only the exposed modal supplies actionable facts.
        for name in ('no_ads','daily_exhausted','skip_ticket','support_purchase','results','auto','start','config'):
            if self.present(frame,name):
                found=[obs('surface',name),obs(name),obs('base')]
                if name=='config':
                    for flag in ('support_active','support_ready','support_needs','penance'):
                        if self.present(frame,flag):found.append(obs(flag))
                if name=='support_purchase' and self.present(frame,'support_full'):found.append(obs('support_full'))
                if name=='auto':
                    for flag in ('max300','video2','video1','video0'):
                        if self.present(frame,flag):found.append(obs(flag))
                return tuple(found)
        # Acquired single-OK game alert. Identity of No Ads is checked only
        # after Android confirms the main game activity, outside this CV pass.
        if self.present(frame,'alert_ok'):
            return (obs('surface','alert'),obs('alert'),obs('base'))
        if self.present(frame,'world_map'):return (obs('surface','world_map'),obs('world_map'))
        for mode in ('normal','elite'):
            if self.present(frame,mode):
                found=[obs('surface',mode),obs(mode),obs('base')]
                if mode=='normal':
                    for flag in ('abyssal','stage8'):
                        if self.present(frame,flag):found.append(obs(flag))
                    h,w=frame.shape[:2]
                    hsv=cv2.cvtColor(frame[round(.918*h):round(.95*h),round(.391*w):round(.404*w)],cv2.COLOR_BGR2HSV)
                    cyan=np.mean((hsv[:,:,0]>75)&(hsv[:,:,0]<100)&(hsv[:,:,1]>100)&(hsv[:,:,2]>90))
                    gray=np.mean((hsv[:,:,1]<40)&(hsv[:,:,2]>65)&(hsv[:,:,2]<175))
                    if cyan>.80:found.append(obs('claim_active'))
                    elif gray>.80:found.append(obs('claim_inactive'))
                return tuple(found)
        return ()

def has(snapshot,name):
    return any(o.name=='stages.'+name and o.confidence>=.8 for o in snapshot.observations.observations)

def surface(snapshot):
    o=snapshot.observations.best('stages.surface')
    return o.value if o is not None and o.confidence>=.8 else None
