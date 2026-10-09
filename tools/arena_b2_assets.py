"""Reproduce focal assets/portable fixtures from reviewed B2 acquisition manifest."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from bot.arena_reader import crop, USED_ROI, WON_ROI
from bot.arena_flow_reader import ECONOMY_ROIS

ROOT = Path(__file__).resolve().parents[1]


def build():
    data = json.loads((ROOT / 'datasets/arena_b2_acquisition_manifest.json').read_text(encoding='utf8'))
    frames = {}
    fixture_entries = []
    for entry in data['entries']:
        path = ROOT / entry['source']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['source_sha256']:
            raise ValueError('B2 acquisition source/hash missing')
        frame = cv2.imread(str(path))
        h, w = frame.shape[:2]
        frames[entry['id']] = cv2.resize(frame, (round(w / 2), round(h / 2)), interpolation=cv2.INTER_AREA)
        fixture_entries.append(dict(entry))
    assets = []
    for spec in data['assets']:
        path = ROOT / 'assets/arena' / (spec['id'] + '.png')
        cv2.imwrite(str(path), crop(frames[spec['source_id']], spec['roi']))
        assets.append(dict(spec, path=path.relative_to(ROOT).as_posix(),
            reference_shape=frames[spec['source_id']].shape[:2],
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    rois = [USED_ROI, WON_ROI, *ECONOMY_ROIS]
    for manifest in ('arena_visual_assets_manifest.json', 'arena_b1_assets_manifest.json'):
        rois.extend(s['roi'] for s in json.loads((ROOT / 'datasets' / manifest).read_text(encoding='utf8'))['assets'])
    rois.extend(s['roi'] for s in data['assets'])
    rois.extend(data.get('fixture_rois', []))
    out = ROOT / 'tests/fixtures/arena_b2'
    out.mkdir(parents=True, exist_ok=True)
    for entry in fixture_entries:
        frame = frames[entry['id']]
        canvas = np.zeros_like(frame)
        h, w = frame.shape[:2]
        for l, t, r, b in rois:
            x0, x1 = round(max(0, l-.005)*w), round(min(1, r+.005)*w)
            y0, y1 = round(max(0, t-.007)*h), round(min(1, b+.007)*h)
            canvas[y0:y1, x0:x1] = frame[y0:y1, x0:x1]
        path = out / (entry['id'] + '.png')
        cv2.imwrite(str(path), canvas)
        entry.update(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (out / 'manifest.json').write_text(json.dumps(dict(schema_version=1, entries=fixture_entries), indent=2)+'\n', encoding='utf8')
    (ROOT / 'datasets/arena_b2_assets_manifest.json').write_text(json.dumps(dict(schema_version=1, assets=assets), indent=2)+'\n', encoding='utf8')


if __name__ == '__main__':
    build()
