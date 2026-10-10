"""Incremental focal VP replay; never accesses a device."""
import hashlib
import json
from pathlib import Path
import cv2
from bot.arena_vp import ArenaVictoryPointReader
from bot.arena_flow_reader import ArenaFlowVisuals
from bot.capture import FrameSnapshot
from bot.ocr import RapidOcrEngine

ROOT=Path(__file__).resolve().parents[1]
def main():
    data=json.loads((ROOT/'datasets/arena_vp_manifest.json').read_text())
    out=ROOT/'artifacts/arena_stability_20261010/vp_evaluation';out.mkdir(parents=True,exist_ok=True)
    cache_path=out/'cache.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    code=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in (
        'bot/arena_vp.py','bot/arena_flow_reader.py','bot/arena_reader.py','bot/ocr.py',
        'assets/arena/vp_backdrop.png','assets/arena/vp_backdrop_mask.png'))).hexdigest()
    reader=ArenaVictoryPointReader(RapidOcrEngine(),clock=lambda:100.)
    visuals=ArenaFlowVisuals();results=[];reused=0
    for e in data['entries']:
        p=ROOT/e['path'];digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=e['sha256']:raise ValueError('curated source changed')
        key=code+digest
        if key in cache:value=cache[key];reused+=1
        else:
            value=reader.read(FrameSnapshot(cv2.imread(str(p)),100.,1),visuals)
            cache[key]=value
        results.append(dict(id=e['id'],observed=value,expected=e['expected'],passed=value==e['expected']))
    report=dict(samples=len(results),wrong=sum(not x['passed'] for x in results),reused=reused,results=results)
    cache_path.write_text(json.dumps(cache,indent=2))
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report));return bool(report['wrong'])
if __name__=='__main__':raise SystemExit(main())
