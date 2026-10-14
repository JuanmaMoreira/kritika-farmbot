"""Incremental CV-only replay for Arena previous rewards and nearby negatives."""
from dataclasses import asdict
import json
from pathlib import Path
from bot.arena_reader import ArenaDetector
from bot.arena_semantics import ARENA_PREVIOUS_REWARDS
from tools.curate_arena_previous_rewards import digest
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs

ROOT=Path(__file__).resolve().parents[1]


def evaluate():
    expected={}
    for relative in ('tests/fixtures/arena_previous_rewards/manifest.json',
                     'datasets/arena_previous_rewards_semantic_manifest.json',
                     'tests/fixtures/arena_phase_a/manifest.json',
                     'tests/fixtures/arena_b1/manifest.json',
                     'tests/fixtures/arena_b2/manifest.json'):
        manifest=json.loads((ROOT/relative).read_text(encoding='utf8'))
        for entry in manifest['entries']:
            path=entry['path']
            if digest(ROOT/path)!=entry['sha256']:
                raise ValueError(f'Hash mismatch: {path}')
            expected[path]=entry.get('expected_previous_rewards',False)
    # Every confirmed local seasonal WB/WM example is a relevant foreign negative.
    for relative,identity in (('world_boss_semantic_manifest.json','popup.world_boss_previous_rewards'),
                             ('monster_wave_semantic_manifest.json','popup.monster_wave_weekly_results')):
        for entry in json.loads((ROOT/'datasets'/relative).read_text(encoding='utf8'))['entries']:
            if identity in entry.get('overlays',[]) and entry.get('review_status')=='confirmed':
                path=ROOT/entry['path']
                if not path.is_file():
                    raise FileNotFoundError(path)
                if 'sha256' in entry and digest(path)!=entry['sha256']:
                    raise ValueError(f'Hash mismatch: {path}')
                expected[entry['path']]=False
    output=ROOT/'artifacts/arena_previous_rewards_20261012/evaluation'
    output.mkdir(parents=True,exist_ok=True)
    frames,stats=evaluate_detector_frame_pairs(ROOT,sorted(expected),[ArenaDetector()],cache_path=output/'cache.json')
    rows=[]
    for frame in frames:
        actual=ARENA_PREVIOUS_REWARDS in {o.name for o in frame.observations}
        rows.append(dict(path=frame.path,expected=expected[frame.path],actual=actual))
    wrong=[r for r in rows if r['actual']!=r['expected']]
    report=dict(samples=len(rows),positives=sum(expected.values()),wrong=wrong,
                incremental=asdict(stats),ocr_calls=0,rows=rows)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
    return bool(wrong)


if __name__=='__main__':raise SystemExit(evaluate())
