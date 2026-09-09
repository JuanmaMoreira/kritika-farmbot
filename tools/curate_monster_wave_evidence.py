"""Reproduce the reviewed MW crops/manifest, preserving both raw acquisitions.

Run as a module from the repository root. Labels are reviewed evidence, never
inferred from production predictions. Calibration is a separate offline step.
"""
import hashlib
import json
import shutil
from pathlib import Path

import cv2

from bot.monster_wave_semantics import *

ROOTS = ("acquisition-battle-mode-monster-wave", "acquisition-monster-wave-skip-boundaries",
         "acquisition-monster-wave-weekly-reset")
# Bounds are normalized from the reviewed capture, applied to frame.shape.
CROPS = {
    # Left title fragment stays outside chat and outside the acquired modal panels.
    MW_SCREEN: ("monster-wave-after-clear", (.18, .13, .258, .172)),
    MW_NEEDS_TICKETS: ("monster-wave-entry-skip-inactive", (.716, .674, .817, .744)),
    MW_READY: ("monster-wave-skip-ready", (.661, .674, .817, .744)),
    MW_TIMER: ("monster-wave-skip-active", (.557, .675, .652, .705)),
    MW_SKIP_START: ("monster-wave-skip-active", (.716, .681, .817, .733)),
    MW_MAX: ("monster-wave-sapphires-max-selected", (.768, .556, .816, .621)),
    MW_CONTROLS_CLEAR: ("monster-wave-sapphires-max-selected", (.658, .567, .756, .624)),
    MW_TOOLTIP: ("monster-wave-sapphires-max-menu", (.608, .538, .831, .660)),
    MW_PURCHASE: ("monster-wave-skip-popup", (.369, .084, .628, .126)),
    MW_PURCHASE_FULL: ("monster-wave-skip-30-30", (.558, .648, .608, .684)),
    MW_INSUFFICIENT: ("monster-wave-insufficient-sapphires", (.361, .437, .637, .509)),
    MW_BOARD: ("monster-wave-board-day2", (.359, .508, .643, .558)),
    MW_CLEAR: ("monster-wave-skip-clear", (.386, .150, .614, .246)),
    MW_DAILY: ("battle-mode-select-initial", (.161, .207, .187, .266)),
    MW_RANKING: ("monster-wave-entry-ranking-popup", (.431, .166, .568, .220)),
    # Fixed footer only: season, class, ranks and reward amounts are dynamic.
    MW_WEEKLY: ("monster-wave-weekly-reward", (.324, .704, .678, .748)),
}


def main():
    root = Path.cwd()
    records = [json.loads(line) for folder in ROOTS
               for line in (root / "artifacts" / folder / "manifest.jsonl").read_text().splitlines()]
    by_label = {r["label"]: r["path"] for r in reversed(records)}
    assets = root / "assets/ui/landmarks/monster-wave"
    assets.mkdir(parents=True, exist_ok=True)
    spec_records = []
    for name, (label, bounds) in CROPS.items():
        frame = cv2.imread(str(root / by_label[label])); h, w = frame.shape[:2]
        x0, y0, x1, y1 = [round(v * (w if i % 2 == 0 else h)) for i, v in enumerate(bounds)]
        path = assets / (name.split(".")[-1] + ".png")
        cv2.imwrite(str(path), frame[y0:y1, x0:x1])
        spec_records.append(dict(name=name, asset_path=path.relative_to(root).as_posix(),
                                 region=[max(0, bounds[0]-.012), max(0, bounds[1]-.015),
                                         min(1, bounds[2]+.012), min(1, bounds[3]+.015)],
                                 raw_source=by_label[label], crop=list(bounds)))
    (root / "artifacts/mw-crops.json").write_text(json.dumps(spec_records, indent=2)+"\n")
    entries=[]
    needs={"monster-wave-entry-clean", "monster-wave-entry-nobuff", "monster-wave-entry-reenable",
           "monster-wave-entry-skip-inactive", "monster-wave-after-weekly-clean",
           "monster-wave-reentry-clean"}
    ready={"monster-wave-skip-ready", "monster-wave-skip-tickets-30-30"}
    active={"monster-wave-skip-active", "monster-wave-skip-active-day2", "monster-wave-sapphires-max-menu",
            "monster-wave-sapphires-max-selected", "monster-wave-after-clear", "monster-wave-daily-done",
            "monster-wave-bag-full", "monster-wave-inventory-board", "monster-wave-board-day2",
            "monster-wave-board-no-after", "monster-wave-insufficient-sapphires", "monster-wave-insufficient-no-after"}
    max_labels=(active-{"monster-wave-skip-active", "monster-wave-skip-active-day2", "monster-wave-sapphires-max-menu", "monster-wave-board-day2", "monster-wave-board-no-after"})|{'monster-wave-skip-clear'}
    overlays={label:overlay for overlay, labels in (
        (POPUP_MW_PURCHASE, ("monster-wave-skip-popup", "monster-wave-skip-30-30")),
        (POPUP_MW_BOARD, ("monster-wave-inventory-board", "monster-wave-board-day2")),
        (POPUP_MW_CLEAR, ("monster-wave-skip-clear",)),
        (POPUP_MW_INSUFFICIENT, ("monster-wave-insufficient-sapphires",)),
        (OVERLAY_MW_TOOLTIP, ("monster-wave-sapphires-max-menu",)),
        (POPUP_MW_RANKING, ("monster-wave-entry-ranking-popup",)),
        (POPUP_MW_WEEKLY, ("monster-wave-weekly-reward",)),
        ("popup.socket_inventory_full", ("monster-wave-bag-full",)),
    ) for label in labels}
    count={}
    for r in records:
        label=r['label']; count[label]=count.get(label,0)+1
        # Three temporal samples per state; preserve all raw files.
        if count[label]>3: continue
        obs=[]; ov=[]
        if label.startswith('battle-mode-select'):
            base='screen.battle_mode_select'; ov=['status.world_boss_daily_active']
            if label in {'battle-mode-select-initial','battle-mode-select-after-mw-back','battle-mode-select-day2',
                         'battle-mode-select-before-weekly'}:
                ov.append(STATUS_MONSTER_WAVE_DAILY_ACTIVE);obs.append(MW_DAILY)
        elif label.startswith('tower-'):
            base='unknown'
        else:
            base=SCREEN_MONSTER_WAVE;obs.append(MW_SCREEN)
            if label in needs:obs.append(MW_NEEDS_TICKETS)
            if label in ready:obs.append(MW_READY)
            if label in active:
                obs.append(MW_SKIP_START)
                if label not in overlays or label=='monster-wave-sapphires-max-menu':obs.append(MW_TIMER)
            if label in max_labels:obs.append(MW_MAX)
            # These two unselected controls remain visible for every clean usage row.
            if label in needs|ready|active and label!='monster-wave-sapphires-max-menu':
                obs.append(MW_CONTROLS_CLEAR)
            if label in overlays:
                ov.append(overlays[label]); obs.extend(lm for overlay,lm in MW_OVERLAY_LANDMARKS if overlay==overlays[label])
            if label=='monster-wave-skip-30-30':obs.append(MW_PURCHASE_FULL)
        source=root/r['path'];target=root/'screencaps/semantic/monster-wave'/label/f'{count[label]:02}.png'
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        entries.append(dict(path=target.relative_to(root).as_posix(),base_context=base,overlays=ov,
            observations=obs,review_status='confirmed',raw_source=r['path'],
            sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    payload=dict(version=1,curation=dict(source=list(ROOTS),raw_retention='Preserved by explicit user instruction',
        labels='Human acquisition ground truth plus reviewed visible landmarks; no inferred resource balances',
        limitations='No GOLD-insufficient purchase evidence or acquired relief return',
        entry_returns='Human-confirmed Weekly Results OK and New Ranking OK return to clean MW; no assumed combined order'),entries=entries)
    (root/'datasets/monster_wave_semantic_manifest.json').write_text(json.dumps(payload,indent=2)+"\n",encoding='utf-8')
    # Values reviewed in the captured HUD, never derived from costs or predictions.
    sapphire_values = {
        'monster-wave-entry-clean': 183, 'monster-wave-skip-ready': 183,
        'monster-wave-skip-active': 183, 'monster-wave-sapphires-max-selected': 183,
        'monster-wave-after-clear': 83, 'monster-wave-entry-skip-inactive': 83,
        'monster-wave-insufficient-no-after': 0,
        'monster-wave-after-weekly-clean': 70, 'monster-wave-reentry-clean': 70,
    }
    ocr_entries = []
    for entry in entries:
        label = Path(entry['path']).parent.name
        rejected = entry['base_context'] != SCREEN_MONSTER_WAVE or bool(entry['overlays'])
        if label in sapphire_values or rejected:
            ocr_entries.append({key: entry[key] for key in ('path','base_context','overlays','sha256')} |
                               dict(expected_value=None if rejected else sapphire_values[label],
                                    expected_status='context_mismatch' if rejected else 'value'))
    ocr_payload = dict(version=1, curation=dict(
        fact='resource.sapphires', roi=[.617,.040,.676,.082],
        review='Visible MW HUD balances reviewed from captures; clean context required even when popup HUD is readable',
        limitation='Real balances 0, 70, 83, 183; low nonzero Daily decisions covered by deterministic tests, not claimed as live OCR evidence'),
        entries=ocr_entries)
    (root/'datasets/monster_wave_ocr_manifest.json').write_text(json.dumps(ocr_payload,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
