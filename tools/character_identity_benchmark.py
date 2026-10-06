"""Closed-set focal identity audit on labelled Lobby frames (no hardware)."""
import json
import argparse
import hashlib
from pathlib import Path
import cv2
import numpy as np
from bot.character_identity import PERSONAL_NAME_CLASSES, LOBBY_PERSONAL_NAME_ROI, name_mask
from bot.geometry import relative_region_to_pixels

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curate-templates',action='store_true')
    args=parser.parse_args()
    manifest = json.loads((ROOT/'datasets/character_identity_manifest.json').read_text(encoding='utf-8'))
    output = ROOT/'assets/character_identity'
    output.mkdir(parents=True, exist_ok=True)
    sources=[]
    for entry in manifest['entries'] if args.curate_templates else ():
        if entry['split'] != 'calibration' or entry['personal_name'] not in ('DRAKEN一BK','DRAKEN二DB','DRAKEN三BB'):
            continue
        frame=cv2.imread(str(ROOT/entry['path']))
        h,w=frame.shape[:2]
        x1,y1,x2,y2=relative_region_to_pixels(LOBBY_PERSONAL_NAME_ROI,w,h)
        slug={'DRAKEN一BK':'berserker','DRAKEN二DB':'demon_blade','DRAKEN三BB':'burst_breaker'}[entry['personal_name']]
        cv2.imwrite(str(output/f'{slug}.png'),name_mask(frame[y1:y2,x1:x2]))
        sources.append(dict(character_id=slug,canonical_name=entry['personal_name'],raw=entry['path'],
            raw_sha256=entry['sha256'],asset=f'assets/character_identity/{slug}.png',
            asset_sha256=hashlib.sha256((output/f'{slug}.png').read_bytes()).hexdigest()))
    if sources:
        (ROOT/'datasets/character_identity_templates.json').write_text(json.dumps(dict(version=1,
            source='USER_GT labels / first calibration frame per identity',roi=LOBBY_PERSONAL_NAME_ROI,
            method='White full-name ink >=.90; Unicode/suffix ink >=.90 with >=.06 margin; validation frames never used as templates',
            entries=sources),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from bot.character_identity import LobbyNameRecognizer
    from bot.ocr import RapidOcrEngine
    from bot.state import ResolutionStatus
    from types import SimpleNamespace
    recognizer=LobbyNameRecognizer(RapidOcrEngine())
    rows=[]
    for entry in manifest['entries']:
        frame=cv2.imread(str(ROOT/entry['path']))
        s=SimpleNamespace(frame=SimpleNamespace(image=frame),state=SimpleNamespace(status=ResolutionStatus.RESOLVED,base_context='screen.lobby',overlays=()))
        identity=recognizer.recognize(s)
        rows.append(dict(path=entry['path'],expected=entry['personal_name'],actual=identity.personal_name if identity else None))
    payload=dict(total=len(rows),correct=sum(r['expected']==r['actual'] for r in rows),wrong=sum(r['actual'] is not None and r['actual']!=r['expected'] for r in rows),unknown=sum(r['actual'] is None for r in rows),rows=rows)
    (ROOT/'artifacts/character_identity_closed_set.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in payload.items() if k!='rows'})
    return int(payload['correct']!=len(rows))

if __name__=='__main__':
    raise SystemExit(main())
