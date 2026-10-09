"""Incremental evaluation of new B2 contexts, using curated acquisition pixels."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from bot.arena_reader import ArenaDetector
from bot.arena_semantics import ARENA_MODE_SELECT, ARENA_CHALLENGE, ARENA_SINGLE_RESULT, ARENA_BATTLE, ARENA_SELECT, ARENA_RANKING
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs

ROOT=Path(__file__).resolve().parents[1]

def main():
    entries=json.loads((ROOT/'tests/fixtures/arena_b2/manifest.json').read_text())['entries']
    for e in entries:
        if hashlib.sha256((ROOT/e['path']).read_bytes()).hexdigest()!=e['sha256']:
            raise ValueError('B2 fixture provenance mismatch')
    output=ROOT/'artifacts/arena_b2/evaluation'; output.mkdir(parents=True,exist_ok=True)
    frames,stats=evaluate_detector_frame_pairs(ROOT,[e['path'] for e in entries],
        [ArenaDetector()],cache_path=output/'cache.json')
    by_path={e['path']:e for e in entries}; wrong=[]
    for f in frames:
        names={o.name for o in f.observations}; context=by_path[f.path]['context']
        required={'select_mode':ARENA_MODE_SELECT,'challenge':ARENA_CHALLENGE,
            'single_result':ARENA_SINGLE_RESULT,'single_active':ARENA_BATTLE,'selection':ARENA_SELECT,'ranking':ARENA_RANKING}.get(context)
        if (required and required not in names) or ((ARENA_SINGLE_RESULT in names)!=(context=='single_result')):
            wrong.append(dict(path=f.path,context=context,observations=sorted(names)))
    report=dict(samples=len(frames),wrong=wrong,incremental=asdict(stats))
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))
    return bool(wrong)

if __name__=='__main__': raise SystemExit(main())
