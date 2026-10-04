"""Focal CV anchors in General's stable suffix; never identify its event prefix.

The supplied catalog defines relative order, not an absolute screen-top count.
Templates identify titles only. Counters/costs and trade policy remain separate.
"""
from pathlib import Path
import cv2
import math
from bot.perception.trading_center import row_bands
from bot.trading_materials_scroll import MATERIAL_CATALOG

ANCHOR_IDS = ('lapiz_400', 'gold_pouch_10m', 'sapphire_5', 'lapiz_5', 'ring_enhance',
              'accessory_crafting_material', 'hero_weapon_crafting_material',
              'hero_accessory_crafting_material', 'guild_commodity')
# Only the suffix has been acquired in both current and prior General.
ORDERED_MATERIAL_SUFFIX = MATERIAL_CATALOG[5:]


class TradingListAnchors:
    def __init__(self):
        root = Path(__file__).resolve().parents[1]/'assets/ui/landmarks/trading-center/ordered'
        self.templates = {name: cv2.imread(str(root/(name+'.png')), cv2.IMREAD_GRAYSCALE)
                          for name in ANCHOR_IDS}
        if any(t is None for t in self.templates.values()):
            raise ValueError('Trading anchor asset missing')

    def read(self, frame):
        h,w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        x,y = int(.303*w), int(.35*h)
        roi = gray[y:int(.95*h),x:int(.465*w)]
        bands = [b for b in row_bands(frame) if b[3]]
        anchors = []
        for name,original in self.templates.items():
            template = cv2.resize(original, (roi.shape[1], max(1,round(.076*h))))
            if roi.shape[0] < template.shape[0]:
                continue
            _,score,_,pos = cv2.minMaxLoc(cv2.matchTemplate(roi,template,cv2.TM_CCOEFF_NORMED))
            if not math.isfinite(score) or score < .94:
                continue
            title_top = (y+pos[1])/h
            # Title crops start .014 below the acquired row top. Separator
            # fitting can pick a bevel's phase; it must not move the CV anchor.
            top = title_top-.014
            center = top+.1418/2
            if top >= .35 and top+.1418 <= .95 and any(b[0]<=center<=b[1] for b in bands):
                anchors.append((name,center))
        anchors.sort(key=lambda a:a[1])
        # Contradictory identity/order is unreadable, never an invented index.
        indices = [ORDERED_MATERIAL_SUFFIX.index(name) for name,_ in anchors]
        if indices != sorted(set(indices)):
            return ()
        return tuple(anchors)
