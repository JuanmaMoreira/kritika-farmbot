"""Visual equivalence for protected-block discovery. Never sale authority."""
from pathlib import Path
import json
import cv2
import numpy as np


class EquipmentBlockMatcher:
    def __init__(self, profile=None):
        path=Path(profile or Path(__file__).resolve().parents[1]/'assets/equipment/block_scan_profile.json')
        self.profile=json.loads(path.read_text(encoding='utf-8'))
        self.asset_paths=(path,Path(__file__))
        self.threshold=float(self.profile['threshold'])
        self.uncertain_floor=float(self.profile['uncertain_floor'])
        self.roi=tuple(self.profile['roi'])
        self.margin=int(self.profile['alignment_margin'])
        if not 0<self.uncertain_floor<self.threshold<1 or len(self.roi)!=4 or self.margin<0:
            raise ValueError('invalid protected-block profile')

    def crop(self, image, center):
        h,w=image.shape[:2];cx,cy=center;x1,y1,x2,y2=self.roi
        left,top,right,bottom=round((cx+x1)*w),round((cy+y1)*h),round((cx+x2)*w),round((cy+y2)*h)
        if not 0<=left<right<=w or not 0<=top<bottom<=h:
            return None
        return image[top:bottom,left:right].copy()

    def score(self, references, candidate):
        if candidate is None or candidate.size==0 or candidate.std()<8:
            return None
        scores=[]
        for reference in references:
            if reference is None or reference.size==0 or reference.std()<8:
                continue
            src=candidate
            if src.shape!=reference.shape:
                src=cv2.resize(src,(reference.shape[1],reference.shape[0]))
            m=self.margin
            template=reference[m:-m,m:-m] if m else reference
            if not template.size:
                continue
            scores.append(float(cv2.matchTemplate(src,template,cv2.TM_CCOEFF_NORMED).max()))
        return max(scores) if scores else None

    def equivalent(self, references, candidate):
        score=self.score(references,candidate)
        return score is not None and np.isfinite(score) and score>=self.threshold
