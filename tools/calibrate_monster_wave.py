"""Offline, directed MW calibration against the complete productive corpus."""
import json
from pathlib import Path

from bot.perception.local_cv import LocalCvDetector
from bot.perception.specs import LocalCvSpec, LinearGapCalibration
from tools.production_perception_evaluation import DEFAULT_MANIFEST_PATHS
from tools.semantic_slice_evaluation import load_manifest
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs


def main():
    root=Path.cwd()
    manifests=tuple(dict.fromkeys((*DEFAULT_MANIFEST_PATHS,'datasets/monster_wave_semantic_manifest.json')))
    entries={e.path:e for p in manifests for e in load_manifest(root/p) if e.review_status=='confirmed'}
    crops=json.loads((root/'artifacts/mw-crops.json').read_text())
    detectors=tuple(LocalCvDetector(LocalCvSpec(c['name'],Path(c['asset_path']),tuple(c['region']),
                    LinearGapCalibration(0.0,1.0))) for c in crops)
    frames,stats=evaluate_detector_frame_pairs(root,entries,detectors,cache_path='artifacts/mw-calibration-cache.json')
    result=[]
    for c in crops:
        name=c['name'];pos=[];neg=[]
        for f in frames:
            (pos if name in entries[f.path].observations else neg).append((f.raw_scores[name],f.path))
        pos.sort();neg.sort(reverse=True)
        result.append(dict(**c,positive_min=pos[:5],negative_max=neg[:8],gap=pos[0][0]-neg[0][0]))
        print(name, 'gap=',round(result[-1]['gap'],6),'pos=',pos[0],'neg=',neg[0],flush=True)
    (root/'artifacts/mw-calibration.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
