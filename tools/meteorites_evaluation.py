"""Incremental Phase A evaluation over explicit curated corpus, never raw.

Missing corpus is a hard diagnostic, not a skipped/passing evaluation. Normal
pytest replay uses small committed fixtures and requires no ignored dataset.
"""
import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2

from bot.meteorites_reader import MeteoritesReader, MeteoritesDetector, normalize
from bot.meteorites_semantics import SlotState
from bot.ocr import RapidOcrEngine

ROOT=Path(__file__).resolve().parents[1]


def evaluate(corpus_root=ROOT):
    manifest=json.loads((ROOT/'datasets/meteorites_hil_20261008_manifest.json').read_text(encoding='utf8'))
    reader=MeteoritesReader(RapidOcrEngine())
    wrong=[]; results=[]
    for seq,s in enumerate(manifest['samples'],1):
        path=corpus_root/s['curated']
        if not path.is_file(): raise FileNotFoundError(f'curated corpus missing: {path}; use --corpus-root')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=s['sha256']: raise ValueError(f'hash mismatch: {path}')
        image=cv2.imread(str(path)); f=normalize(image); sem=s.get('semantic',{})
        bag=reader.bag_sample(image,sequence=seq,observed_at=float(seq))
        detail=reader.detail_sample(image,sequence=seq,observed_at=float(seq)) if reader.detail(f) else None
        errors=[]
        def check(ok,label):
            if not ok: errors.append(label)
        negative=sem.get('main_tab_negative') or sem.get('meteorites_base_negative') or s['id'].startswith('01_') or s['id'].startswith('34_')
        if negative: check(bag is None and detail is None,'main BASE negative')
        if sem.get('tab')=='Meteorites' or sem.get('overlay') is True: check(bag is not None,'main BASE')
        if sem.get('overlay') is True:
            check(detail is not None,'detail')
            if detail is not None:
                check(detail.flare==sem['type'].startswith('Flare'),'Flare')
                check(detail.tier==sem['tier'],'tier')
                check(detail.level==sem['level'],'level')
                check(detail.action.value==sem['lateral_action'].lower(),'lateral action/lock negative')
        if sem.get('overlay') is False: check(not reader.detail(f),'overlay absent')
        if 'active_set' in sem: check(bag is not None and bag.active_set==sem['active_set'],'set')
        if 'occupied_slots' in sem and bag is not None:
            check(bag.slots.count(SlotState.OCCUPIED)==sem['occupied_slots'],'slots occupied')
            check(SlotState.UNKNOWN not in bag.slots,'slots known')
        if 'page' in sem and not sem.get('loading') and not negative: check(bag is not None and bag.page==sem['page'],'page')
        if 'tab' in sem and not sem.get('loading'):
            check(reader.tab_sample(image)==sem['tab'],'independent tab')
        transient=('_frame_' in s['id'] and not sem.get('individual_effect') and not s['id'].endswith('frame_044'))
        if transient or sem.get('loading') or s['id']=='07_flare_reselect_before':
            check(bag is None or not bag.ready,'transient cannot authorize input')
        if sem.get('individual_effect'):
            check(bag is not None and bag.ready,'effect/readiness')
            if bag is not None:
                states=list(bag.slots)
                expected_occupied={0} if s['id'].startswith('09_') else ({0,1} if s['id'].startswith('12_') else
                    ({0,1,2} if s['id'].startswith('15_') else ({1,2} if s['id'].startswith('19_') else
                    ({1} if s['id'].startswith('21_') else set()))))
                check({i for i,v in enumerate(states) if v is SlotState.OCCUPIED}==expected_occupied,'individual slot USER_GT order')
        results.append(dict(id=s['id'],errors=errors,main=bag is not None,
                            ready=bool(bag and bag.ready),loading=reader.loading(f)))
        if errors: wrong.append(results[-1]); print('WRONG',s['id'],errors)
    out=ROOT/'artifacts/meteorites_phase_a/evaluation.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(total=len(results),wrong=wrong,samples=results),indent=2)+'\n',encoding='utf8')
    print(f'Meteorites Phase A: {len(results)-len(wrong)}/{len(results)} curated pass; {len(wrong)} wrong; calls={reader.calls}')
    return len(wrong)


def evaluate_existing_negatives():
    """Only the new BASE detector is invalidated on the existing corpus."""
    from tools.production_perception_evaluation import DEFAULT_MANIFEST_PATHS
    from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs
    paths=set()
    for name in DEFAULT_MANIFEST_PATHS:
        manifest=json.loads((ROOT/name).read_text(encoding='utf8'))
        paths.update(s['path'] for s in manifest.get('entries',[]) if s.get('review_status')=='confirmed')
    frames,stats=evaluate_detector_frame_pairs(ROOT,sorted(paths),[MeteoritesDetector()],
        cache_path=ROOT/'artifacts/meteorites_phase_a/negative_cache.json')
    wrong=[f.path for f in frames if f.observations]
    out=ROOT/'artifacts/meteorites_phase_a/negative_evaluation.json'
    out.write_text(json.dumps(dict(wrong=wrong,stats=asdict(stats)),indent=2)+'\n',encoding='utf8')
    print('Meteorites existing negatives:',len(paths)-len(wrong),'/',len(paths),'stats=',asdict(stats))
    if wrong: print('WRONG negatives:',wrong)
    return len(wrong)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus-root',type=Path,default=ROOT)
    p.add_argument('--existing-negatives',action='store_true')
    args=p.parse_args()
    raise SystemExit(bool(evaluate(args.corpus_root)+(evaluate_existing_negatives() if args.existing_negatives else 0)))
