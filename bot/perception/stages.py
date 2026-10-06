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

    def sdk_close_scores(self,frame):
        """Fixed SDK primitives, masked independently of creative background.

        The X mask keeps its circle interior; the speaker mask keeps its glyph
        and edge. Opposite X polarity requires explicit reward authority.
        """
        values=[]
        for name in ('ad_close_round','ad_sdk_sound'):
            h,w=frame.shape[:2];p=self.profile[name];x1,y1,x2,y2=p['search']
            search=cv2.cvtColor(frame[round(y1*h):round(y2*h),round(x1*w):round(x2*w)],cv2.COLOR_BGR2GRAY)
            c=p['crop'];tw=round(c[2]*w)-round(c[0]*w)
            source=self._templates[name];th=round(source.shape[0]*tw/source.shape[1])
            template=cv2.cvtColor(cv2.resize(source,(tw,th)),cv2.COLOR_BGR2GRAY)
            if search.shape[0]<th or search.shape[1]<tw:
                values.append((0.,0.));continue
            if name=='ad_close_round':
                mask=np.zeros(template.shape,dtype=np.uint8)
                cv2.circle(mask,(tw//2,th//2),round(min(tw,th)*.36),255,-1)
            else:
                mask=cv2.dilate((template>240).astype(np.uint8)*255,np.ones((3,3),np.uint8))
            scores=cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED,mask=mask)
            finite=scores[np.isfinite(scores)]
            if name=='ad_close_round' and finite.size and np.max(np.abs(finite))>=.94:
                # A plain X on a flat background is not the acquired circle.
                safe=np.where(np.isfinite(scores),scores,0.)
                yy,xx=np.unravel_index(np.argmax(np.abs(safe)),scores.shape)
                angles=np.arange(32)*2*np.pi/32
                rings=[]
                for radius in (.34,.43):
                    xs=np.rint(xx+tw//2+min(tw,th)*radius*np.cos(angles)).astype(int)
                    ys=np.rint(yy+th//2+min(tw,th)*radius*np.sin(angles)).astype(int)
                    rings.append(float(np.median(search[ys,xs])))
                if abs(rings[0]-rings[1])<3.:
                    values.append((0.,0.));continue
            values.append((float(finite.max()),float(-finite.min())) if finite.size else (0.,0.))
        return values[0][0],values[0][1],values[1][0]

    def detect(self,frame,*,claim_only=False):
        def obs(name,value=None):return Observation('stages.'+name,1.,ObservationSource.LOCAL_CV,value=value)
        if self.present(frame,'loading'):return (obs('loading'),)
        # Upper layers first. Only the exposed modal supplies actionable facts.
        for name in ('no_ads','daily_exhausted','skip_ticket','support_purchase','results'):
            if self.present(frame,name):
                found=[obs('surface',name),obs(name),obs('base')]
                if name=='support_purchase' and self.present(frame,'support_full'):found.append(obs('support_full'))
                return tuple(found)
        # A shared OK button needs underlying Stages chrome; another owner
        # (e.g. Socket No Material) must retain its own modal. No Ads is checked only
        # after Android confirms the main game activity, outside this CV pass.
        if self.present(frame,'alert_ok') and any(
            self.score(frame,name,undimmed=False)>=.94
            for name in ('auto','start','config','normal','elite')
        ):
            return (obs('surface','alert'),obs('alert'),obs('base'))
        # Single-OK upper alerts capture input even when the Auto title remains
        # exposed outside their rectangle. Never classify that lower panel first.
        for name in ('auto','start','config'):
            if self.present(frame,name):
                found=[obs('surface',name),obs(name),obs('base')]
                if name=='config':
                    for flag in ('support_active','support_ready','support_needs','penance'):
                        if self.present(frame,flag):found.append(obs(flag))
                if name=='auto':
                    for flag in ('max300','video2','video1','video0'):
                        if self.present(frame,flag):found.append(obs(flag))
                return tuple(found)
        if self.present(frame,'world_map'):return (obs('surface','world_map'),obs('world_map'))
        for mode in ('normal','elite'):
            if self.present(frame,mode):
                found=[obs('surface',mode),obs(mode),obs('base')]
                if mode=='normal':
                    if not claim_only:
                        score=self.score(frame,'abyssal')
                        found.append(obs('abyssal_score',score))
                        if score>=.94:found.append(obs('abyssal'))
                        if self.present(frame,'stage8'):found.append(obs('stage8'))
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

class StagesClaimDetector:
    """Same upper-layer/Normal guards and Claim signal; omit episode/Stage8 work."""
    def __init__(self,detector):self.detector=detector
    def detect(self,frame):return self.detector.detect(frame,claim_only=True)
