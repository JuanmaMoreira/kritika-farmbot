"""Reproduce small Arena assets/portable fixtures from the acquired curated corpus.

No acquisition, HIL or synthetic physical GT. Missing sources fail explicitly.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def build():
    manifest = json.loads((ROOT/'datasets/arena_hil_20261008_manifest.json').read_text(encoding='utf8'))
    entries = manifest['entries']
    samples = {
        'selection': 'mode-arena-after', 'easy_off': 'easy-challenge-after',
        'buff1_on': 'buff2-select-before', 'buff12_on': 'buff2-select-after',
        'config': 'auto-config-after', 'insufficient': 'final-result-close-after',
        'ranking': 'select-after-batch', 'normal': 'normal-challenge-after',
        'hard': 'hard-challenge-after', 'hard_buff1_off': 'buff1-clear-after',
        'hard_off': 'buff2-clear-after', 'native': 'final-result',
        'stream': 'final-result-close-before', 'loading': 'natural-batch-start-after',
        'foreign_lobby': 'initial', 'foreign_battle_select': 'lobby-battle-after',
        'bag_full': 'batch-modal-start-after',
    }
    chosen = {name: next(e for e in entries if e.get('label') == label) for name, label in samples.items()}
    for name, state in (('battle', 'arena_battle_auto_active'), ('partial1', 'arena_auto_final_partial')):
        chosen[name] = next(e for e in entries if e['physical_state'] == state)
    chosen['partial2'] = [e for e in entries if e['physical_state'] == 'arena_auto_final_partial'][1]
    chosen['stream_late'] = [e for e in entries if e['physical_state'] == 'arena_auto_final_clean'][1]
    frames = {}
    fixture_entries = []
    directory = ROOT/'tests/fixtures/arena_phase_a'
    directory.mkdir(parents=True, exist_ok=True)
    for name, entry in chosen.items():
        source = ROOT/entry['curated_path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'corpus hash mismatch: {source}')
        frame = cv2.imread(str(source))
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (round(w/2), round(h/2)), interpolation=cv2.INTER_AREA)
        frames[name] = frame
        target = directory/(name+'.png')
        cv2.imwrite(str(target), frame)
        fixture_entries.append(dict(id=name, path=target.relative_to(ROOT).as_posix(),
                                    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                    source=entry['curated_path'], source_sha256=entry['sha256'],
                                    authority=entry['annotation_authority'],
                                    physical_state=entry['physical_state'],
                                    numeric_read_authorized=entry['numeric_read_authorized']))
    specs = [
        ('select_easy', 'selection', (.230,.300,.330,.360), .90),
        ('select_normal', 'selection', (.456,.300,.538,.357), .84),
        ('select_hard', 'selection', (.662,.300,.764,.360), .90),
        ('difficulty_easy', 'easy_off', (.331,.307,.414,.370), .90),
        ('difficulty_normal', 'normal', (.331,.307,.414,.370), .90),
        ('difficulty_hard', 'hard', (.331,.307,.414,.370), .90),
        ('challenge_controls', 'easy_off', (.704,.815,.828,.992), .90),
        ('challenge_vs', 'easy_off', (.167,.423,.244,.646), .90),
        ('config_text', 'config', (.332,.157,.667,.488), .93),
        ('config_start', 'config', (.425,.833,.572,.925), .90),
        ('upon_defeat_off', 'config', (.647,.737,.670,.810), .94),
        ('result_title', 'native', (.313,.195,.690,.245), .90),
        ('badge_label', 'native', (.264,.321,.403,.360), .92),
        ('karats_label', 'native', (.264,.630,.403,.670), .92),
        ('result_panel', 'native', (.748,.280,.767,.803), .90),
        ('result_ok', 'native', (.434,.819,.565,.914), .90),
        ('used_padding', 'native', (.482,.321,.488,.355), .90),
        ('won_padding', 'native', (.482,.621,.487,.662), .90),
        ('insufficient', 'insufficient', (.346,.350,.650,.494), .92),
        ('bag_full', 'bag_full', (.349,.375,.650,.497), .92),
        ('ranking', 'ranking', (.393,.136,.603,.225), .90),
        ('ranking_arena', 'ranking', (.451,.270,.509,.313), .90),
        ('battle_vs', 'battle', (.484,.058,.516,.100), .88),
        ('auto_band', 'battle', (.438,.728,.565,.761), .78),
    ]
    for i, x in ((1,.507), (2,.613), (3,.720)):
        roi = (x, .236, x+.040, .304)
        specs.append((f'buff{i}_off', 'easy_off', roi, .90))
        # Same gold check shape demonstrated by buffs 1/2. Buff3 ON rendering
        # is tested synthetically; no Double Points purchase/activation acquired.
        specs.append((f'buff{i}_on', 'buff12_on', (.507,.236,.547,.304) if i==3 else roi, .90))
    specs += [('x8_on','easy_off',(.771,.692,.784,.724),.90),
              ('x8_off','easy_off',(.728,.692,.741,.724),.90)]
    assets = []
    output = ROOT/'assets/arena'
    output.mkdir(parents=True, exist_ok=True)
    for name, sample, roi, threshold in specs:
        frame = frames[sample]
        h, w = frame.shape[:2]
        l,t,r,b = roi
        target = output/(name+'.png')
        cv2.imwrite(str(target), frame[round(t*h):round(b*h), round(l*w):round(r*w)])
        runtime_roi = roi
        if name == 'buff3_on':
            runtime_roi = (.720,.236,.760,.304)
        if name == 'x8_off':
            # Reusable unchecked multiplier marker from acquired x5, not absence.
            runtime_roi = (.771,.692,.784,.724)
        assets.append(dict(id=name, path=target.relative_to(ROOT).as_posix(), roi=runtime_roi,
                           source_roi=roi, threshold=threshold,
                           sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                           source=chosen[sample]['curated_path'], source_sha256=chosen[sample]['sha256'],
                           reusable_indicator=name in ('buff3_on','x8_off')))
        if name.endswith('_padding'):
            assets[-1]['max_color_error'] = 12
    (ROOT/'datasets/arena_visual_assets_manifest.json').write_text(json.dumps(dict(schema_version=1, assets=assets),indent=2)+'\n', encoding='utf8')
    # SYNTHETIC software fixtures: replace numeric glyphs only. They establish
    # parsing/integrity contracts, never a defeat, new batch or physical GT.
    for name, used, won in [('synthetic_partial_win',104,72), ('synthetic_zero',104,0),
                             ('synthetic_invalid_won',104,105)]:
        frame = frames['native'].copy()
        h,w = frame.shape[:2]
        for roi, value, color in [((.439,.320,.490,.359),used,(0,230,230)),
                                   ((.443,.615,.493,.672),won,(250,250,250))]:
            l,t,r,b=roi
            part=frame[round(t*h):round(b*h),round(l*w):round(r*w)]
            part[:]=17
            text=str(value); size=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,.55,1)[0]
            cv2.putText(part,text,(round(.478*w)-round(l*w)-size[0],(part.shape[0]+size[1])//2),
                        cv2.FONT_HERSHEY_SIMPLEX,.55,color,1,cv2.LINE_AA)
        target=directory/(name+'.png');cv2.imwrite(str(target),frame)
        fixture_entries.append(dict(id=name,path=target.relative_to(ROOT).as_posix(),
                                    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                    source=chosen['native']['curated_path'],source_sha256=chosen['native']['sha256'],
                                    authority='SYNTHETIC software fixture; no physical gameplay authority',
                                    physical_state='synthetic_terminal_contract',numeric_read_authorized=False,
                                    expected_terminal=True,
                                    expected_reader=[used,won] if won<=used else None))
    # Preserve every reader/detector ROI and search margin on a same-shape focal
    # canvas. Pixels outside the contract are zeroed, so fixtures don't carry a
    # large screenshot dataset. Full acquired frames remain in the curator.
    regions = [a['roi'] for a in assets] + [(.439,.320,.490,.359),(.443,.615,.493,.672)]
    for entry in fixture_entries:
        target=ROOT/entry['path'];frame=cv2.imread(str(target));h,w=frame.shape[:2]
        canvas=np.zeros_like(frame)
        for l,t,r,b in regions:
            top,bottom=round(max(0,t-.007)*h),round(min(1,b+.007)*h)
            left,right=round(max(0,l-.005)*w),round(min(1,r+.005)*w)
            canvas[top:bottom,left:right]=frame[top:bottom,left:right]
        cv2.imwrite(str(target),canvas,[cv2.IMWRITE_PNG_COMPRESSION,9])
        entry['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (directory/'manifest.json').write_text(json.dumps(dict(schema_version=1,
        transform='half-size INTER_AREA; same-shape focal ROI canvas with preserved search margins; outside zeroed; synthetic numeric entries explicit',
        entries=fixture_entries),indent=2)+'\n', encoding='utf8')
    print(f'{len(assets)} assets, {len(fixture_entries)} portable fixtures')


if __name__ == '__main__':
    build()
