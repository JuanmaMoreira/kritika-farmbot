"""Curate B1 focal navigation/economy replay, never new physical evidence."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from bot.arena_reader import crop, USED_ROI, WON_ROI
from bot.arena_flow_reader import ECONOMY_ROIS

ROOT = Path(__file__).resolve().parents[1]


def build():
    acquired = json.loads((ROOT/'datasets/arena_hil_20261008_manifest.json').read_text(encoding='utf8'))['entries']
    samples = {'lobby':'lobby-battle-before', 'select_mode':'lobby-battle-after',
               'off':'easy-challenge-after', 'buff1':'buff2-select-before',
               'buff12':'buff2-select-after', 'after':'buff2-clear-after',
               'loading':'natural-batch-start-after'}
    specs = [('flow_lobby_battle','lobby',(.778,.538,.838,.588)),
             ('flow_back_button','select_mode',(.772,.022,.834,.120)),
             ('flow_select_title','select_mode',(.434,.118,.557,.169)),
             ('flow_arena_card','select_mode',(.247,.242,.317,.290)),
             ('flow_loading','loading',(.480,.455,.520,.552))]
    frames = {}; entries = []; assets = []
    out = ROOT/'tests/fixtures/arena_b1'; out.mkdir(parents=True,exist_ok=True)
    previous=out/'manifest.json'
    variants=[e for e in json.loads(previous.read_text(encoding='utf8'))['entries']
              if e.get('source_kind')=='native_adb'] if previous.exists() else []
    for name,label in samples.items():
        entry = next(e for e in acquired if e.get('label') == label)
        path = ROOT/entry['curated_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('corpus hash mismatch')
        image = cv2.imread(str(path)); h,w = image.shape[:2]
        frames[name] = cv2.resize(image,(round(w/2),round(h/2)),interpolation=cv2.INTER_AREA)
        entries.append(dict(id=name,source=entry['curated_path'],source_sha256=entry['sha256'],
                            authority=entry['annotation_authority']))
    for entry in variants:
        path=ROOT/entry['source']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['source_sha256']:
            raise ValueError('native variant hash mismatch')
        image=cv2.imread(str(path)); h,w=image.shape[:2]
        scale=entry.get('fixture_scale',.5)
        frames[entry['id']]=cv2.resize(image,(round(w*scale),round(h*scale)),interpolation=cv2.INTER_AREA)
        entries.append(entry)
    if 'config_variant' in frames:
        specs.append(('flow_upon_defeat_off','config_variant',(.647,.737,.670,.810)))
    if 'prepared_live' in frames:
        specs.append(('flow_challenge_back_button','prepared_live',(.772,.022,.834,.120)))
    for name,sample,roi in specs:
        path = ROOT/'assets/arena'/(name+'.png')
        cv2.imwrite(str(path),crop(frames[sample],roi))
        assets.append(dict(id=name,path=path.relative_to(ROOT).as_posix(),roi=roi,
                           threshold=.90 if name=='flow_lobby_battle' else .85 if name=='flow_upon_defeat_off' else .94,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           source=next(e for e in entries if e['id']==sample)))
    # Preserve existing Phase A focal regions too, so these exercise actual CV.
    base = json.loads((ROOT/'datasets/arena_visual_assets_manifest.json').read_text(encoding='utf8'))['assets']
    rois = [s['roi'] for s in base]+list(ECONOMY_ROIS)+[USED_ROI,WON_ROI]+[s[2] for s in specs]
    for entry in entries:
        frame = frames[entry['id']]; canvas = np.zeros_like(frame); h,w=frame.shape[:2]
        for l,t,r,b in rois:
            x0,x1=round(max(0,l-.005)*w),round(min(1,r+.005)*w)
            y0,y1=round(max(0,t-.007)*h),round(min(1,b+.007)*h)
            canvas[y0:y1,x0:x1]=frame[y0:y1,x0:x1]
        path=out/(entry['id']+'.png'); cv2.imwrite(str(path),canvas)
        entry.update(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (ROOT/'datasets/arena_b1_assets_manifest.json').write_text(json.dumps(dict(schema_version=1,assets=assets),indent=2)+'\n',encoding='utf8')
    (out/'manifest.json').write_text(json.dumps(dict(schema_version=1,transform='half-size focal canvas; no synthetic physical states',entries=entries),indent=2)+'\n',encoding='utf8')


if __name__ == '__main__':
    build()
