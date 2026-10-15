"""Focal offline replay with the existing incremental detector/frame cache."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from bot.perception.global_loading import GlobalLoadingDetector
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/loading_central_2b_20261015')
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT)
    out.mkdir(parents=True, exist_ok=True)
    rows = json.loads((ROOT/'datasets/global_loading_manifest.json').read_text(encoding='utf8'))['entries']
    # Verify provenance and disjoint pixels before running any predictions.
    development = {r['sha256'] for r in rows if r['split']=='development_2a'}
    for r in rows:
        if hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()!=r['sha256']:
            raise ValueError(f"hash mismatch: {r['path']}")
        if r['split']=='holdout_new_origins' and r['sha256'] in development:
            raise ValueError('holdout overlaps development pixels')
    detector = GlobalLoadingDetector()
    frames, stats = evaluate_detector_frame_pairs(ROOT,[r['path'] for r in rows],(detector,),cache_path=out/'cache.json')
    counts = {}
    predictions=[]
    for r,f in zip(rows,frames):
        c=counts.setdefault(r['split'],Counter())
        hit=bool(f.observations)
        if r['label']=='UNCERTAIN': c['uncertain']+=1
        else:c[('tp' if hit else 'fn') if r['label']=='LOADING' else ('fp' if hit else 'tn')]+=1
        predictions.append(dict(path=r['path'],split=r['split'],label=r['label'],positive=hit))
    benchmark={}
    for label,path in [('loading',rows[6]['path']),('hard_negative','screencaps/semantic/equipment_inventory_full/combine/animation/fuse-tappable.png'),('quiet_negative',rows[11]['path'])]:
        image=cv2.imread(str(ROOT/path))
        for _ in range(10):detector.detect(image)
        samples=[]
        for _ in range(200):
            start=time.perf_counter();detector.detect(image);samples.append((time.perf_counter()-start)*1000)
        benchmark[label]=dict(median_ms=float(np.median(samples)),p95_ms=float(np.percentile(samples,95)))
    result=dict(counts=counts,incremental=asdict(stats),benchmark=benchmark,predictions=predictions,
                note='No independent positive holdout; all phase2A frames are development; uncertain excluded from confusion matrices')
    (out/'evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='predictions'},indent=2))
    if any(c['fp'] for c in counts.values()):
        raise SystemExit(2)  # Deliberate precision gate: never promote on known FP.


if __name__=='__main__':main()
