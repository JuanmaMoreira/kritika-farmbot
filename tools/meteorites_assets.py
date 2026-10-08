"""Reproduce small Phase A assets from hash-verified curated acquisition only."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2

from bot.meteorites_semantics import BAG_POINTS, SLOT_POINTS

ROOT = Path(__file__).resolve().parents[1]


def crop(frame, roi):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = roi
    return frame[round(y1*h):round(y2*h), round(x1*w):round(x2*w)]


def build(corpus_root):
    manifest = json.loads((ROOT/'datasets/meteorites_hil_20261008_manifest.json').read_text(encoding='utf8'))
    samples = {s['id']: s for s in manifest['samples']}
    output = ROOT/'assets/meteorites'
    output.mkdir(parents=True, exist_ok=True)
    provenance = []

    def save(name, sample_id, roi):
        s = samples[sample_id]
        path = corpus_root/s['curated']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == s['sha256'], path
        frame = cv2.imread(str(path))
        # Templates use a width-scaled coordinate space; actual sampling uses
        # frame.shape. A 4-pixel source-height discrepancy never changes bytes.
        frame = cv2.resize(frame, (1356, 612))
        img = crop(frame, roi)
        path = output/(name+'.png')
        assert cv2.imwrite(str(path), img)
        provenance.append(dict(asset=path.relative_to(ROOT).as_posix(),
                               sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               source=s['curated'], source_sha256=s['sha256'], roi=roi))

    empty='03_set2_empty_last'
    save('main_bag_header',empty,(.558,.231,.671,.279))
    for name,sample_id,roi in (
        ('Meteorites',empty,(.171,.148,.257,.228)),
        ('Combine','27_tab_combine_last',(.258,.148,.338,.228)),
        ('Evolve','28_tab_evolve_last',(.343,.148,.423,.228)),
        ('Reforge','29_tab_reforge_last',(.429,.148,.509,.228)),
        ('Reroll','30_tab_reroll_last',(.515,.148,.595,.228))):
        save('tab_'+name.lower(),sample_id,roi)
    save('detail_border','04_flare_p12_overlay_last',(.508,.302,.517,.704))
    save('equip','04_flare_p12_overlay_last',(.197,.274,.246,.390))
    save('unequip','18_flare_equipped_overlay_last',(.197,.274,.246,.390))
    save('check',empty,(.239,.241,.255,.264))
    save('check1','02_lobby_direct_entry_last',(.189,.241,.205,.264))
    save('flare','03_set2_empty_last',(.566,.366,.596,.418))
    save('flare_glare','38_restore_set1_last',(.566,.366,.596,.418))
    save('ethereal_plus','03_set2_empty_last',(.622,.306,.661,.327))
    save('ethereal_plus_equipped','15_equip_normal_shield_last',(.555,.306,.594,.327))
    save('ethereal','03_set2_empty_last',(.555,.306,.594,.327))
    save('ethereal_equipped','02_lobby_direct_entry_last',(.555,.306,.594,.327))
    save('ethereal_detail','36_ethereal_flare_zero_last',(.281,.306,.320,.327))
    save('ethereal_level','03_set2_empty_last',(.555,.588,.594,.609))
    save('badge_e','02_lobby_direct_entry_last',(.554,.305,.572,.343))
    for i,(x,y) in enumerate(SLOT_POINTS):
        save('empty_'+str(i),empty,(x-.017,y-.028,x+.017,y+.028))
    (ROOT/'datasets/meteorites_visual_assets_manifest.json').write_text(
        json.dumps(dict(schema_version=1,authority='LIVE_EVIDENCE curated + USER_GT geometry',assets=provenance),indent=2)+'\n',encoding='utf8')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus-root',type=Path,default=ROOT)
    build(p.parse_args().corpus_root)
