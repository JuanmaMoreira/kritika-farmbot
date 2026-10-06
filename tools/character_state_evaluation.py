"""Focal reader replay and curated acquisition manifest. No device access."""
import json
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter
import cv2
from bot.character_data import QuickMenuResourceReader, crop, RESOURCE_ROIS
from bot.world_boss_state import WorldBossStateReader
from bot.ocr import RapidOcrEngine
from bot.state import ResolutionStatus

ROOT=Path(__file__).resolve().parents[1]

def main():
    engine=RapidOcrEngine()
    resource=QuickMenuResourceReader(engine)
    wb=WorldBossStateReader(engine)
    rows=[]
    paths=list((ROOT/'artifacts/world-boss-live/state-quick-menu-after').glob('*.png'))
    for path in paths:
        frame=cv2.imread(str(path))
        s=SimpleNamespace(frame=SimpleNamespace(image=frame),state=SimpleNamespace(status=ResolutionStatus.UNKNOWN,overlays={'menu.quick'}))
        before=perf_counter()
        values=resource.read(s,origin='screen.lobby')
        print(path.name,values,round(perf_counter()-before,3))
        if values is None:
            for key,roi in RESOURCE_ROIS.items():
                print(key,engine.recognize(crop(frame,roi)))
        rows.append(dict(path=path.relative_to(ROOT).as_posix(),values=values))
    for path in (ROOT/'artifacts/world-boss-live/state-wb-main-after').glob('*.png'):
        frame=cv2.imread(str(path))
        s=SimpleNamespace(frame=SimpleNamespace(image=frame),state=SimpleNamespace(status=ResolutionStatus.RESOLVED,base_context='screen.world_boss',overlays=()))
        print(path.name,wb.read(s))
        for roi in ((.345,.127,.537,.167),(.560,.126,.800,.170),(.672,.703,.778,.752)):
            print(engine.recognize(crop(frame,roi)))
    (ROOT/'artifacts/character_state_reader_evaluation.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
