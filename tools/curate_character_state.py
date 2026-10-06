"""Promote small labelled reader crops, retaining all raw acquisition evidence."""
import json
import hashlib
from pathlib import Path
import cv2
from bot.character_data import RESOURCE_ROIS,crop

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/fixtures/character_state'
WB_ROIS=dict(damage=(.345,.127,.537,.167),rank=(.560,.126,.800,.170),timer=(.672,.703,.778,.752))

def promote(label,path,rois,expected,*,origin=None):
    path=ROOT/path
    image=cv2.imread(str(path))
    if image is None: raise ValueError(path)
    entry=dict(label=label,raw=path.relative_to(ROOT).as_posix(),raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        frame_shape=list(image.shape),source='LIVE_EVIDENCE / reviewed pixels',expected=expected,origin=origin,crops={})
    for field,roi in rois.items():
        target=OUT/f'{label}_{field}.png'
        cv2.imwrite(str(target),crop(image,roi))
        entry['crops'][field]=dict(path=target.relative_to(ROOT).as_posix(),roi=roi,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    return entry

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    entries=[]
    path=next((ROOT/'artifacts/world-boss-live/state-quick-menu-after').glob('*_03.png')).relative_to(ROOT).as_posix()
    entries.append(promote('demon_qm',path,RESOURCE_ROIS,dict(lapiz=3766,dark_essence=455,light_essence=50,nature_essence=24,k_coins=121918),origin='screen.lobby'))
    rois={k:(v[0]+.130,v[1],v[2]+.130,v[3]) for k,v in RESOURCE_ROIS.items()}
    entries.append(promote('fairy_old_qm','screencaps/semantic/world_boss/quick_menu/20260827T231126_760280Z_01.png',rois,
        dict(lapiz=93952,dark_essence=119,light_essence=6800,nature_essence=118,k_coins=147447),origin='screen.world_boss'))
    path=next((ROOT/'artifacts/world-boss-live/state-wb-main-after').glob('*_03.png')).relative_to(ROOT).as_posix()
    entries.append(promote('wb_numeric',path,WB_ROIS,dict(participated=True,remaining_seconds=101640)))
    entries.append(promote('wb_blank','screencaps/semantic/world_boss/main/20260827T231011_209632Z_01.png',WB_ROIS,
        dict(participated=False,remaining_seconds=None,physical_remaining_seconds=112740,
             timer_note='Legacy OCR confidence .87687: reject calibration, preserve current anchor')))
    (OUT/'manifest.json').write_text(json.dumps(dict(version=1,entries=entries,limitations='Minute countdown has <=60s quantization. Crops validate only focal reader fields; semantic context guards retain existing detectors.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(entries)} reviewed frames / {sum(len(e["crops"]) for e in entries)} focal crops')

if __name__=='__main__': main()
