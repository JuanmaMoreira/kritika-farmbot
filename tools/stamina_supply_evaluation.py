"""Evaluate only the newly consumed payment authority and its acquired guards."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
from bot.manual_stages_reader import ManualStagesDetector
from bot.stages_balances import StagesBalanceReader
from bot.stamina_purchase import StaminaPurchase,PAYMENT_ROI,QUANTITY_ROI
from bot.ocr import RapidOcrEngine

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/stamina_supply'

def replay():
    meta=json.loads((FIXTURE/'manifest.json').read_text());im=np.zeros(meta['shape'],dtype=np.uint8)
    h,w=im.shape[:2]
    for region in meta['regions']:
        path=FIXTURE/region['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=region['sha256']:raise ValueError('provenance mismatch')
        a,b,c,d=region['roi'];im[round(b*h):round(d*h),round(a*w):round(c*w)]=cv2.imread(str(path))
    return im

def measure(image,engine):
    s=NS(frame=NS(image=image));reader=StagesBalanceReader(NS(),engine)
    op=StaminaPurchase(NS(),reader,ManualStagesDetector())
    if not op.panel(s):return {'panel':False}
    return {'panel':True,'payment':list(reader.pair(s,PAYMENT_ROI)),
        'quantity':list(reader.pair(s,QUANTITY_ROI))}

def main():
    image=replay();engine=RapidOcrEngine()
    output=ROOT/'artifacts/stamina_budget/evaluation';output.mkdir(parents=True,exist_ok=True)
    cache_path=output/'cache.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    cases=[('acquired',image,dict(panel=True,payment=[140471,200],quantity=[1,20])),
        ('dimmed',image//3,dict(panel=False)),('unknown',np.zeros_like(image),dict(panel=False))]
    fingerprint=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in (
        'bot/stamina_purchase.py','bot/stages_balances.py','bot/perception/stages.py',
        'assets/ui/landmarks/stages/stamina_panel.png','assets/ui/landmarks/stages/kcoin.png'))).hexdigest()
    results=[];reused=0
    for name,frame,expected in cases:
        key=hashlib.sha256((fingerprint+name).encode()+frame.tobytes()).hexdigest()
        if key in cache:actual=cache[key];reused+=1
        else:actual=measure(frame,engine);cache[key]=actual
        results.append(dict(case=name,passed=actual==expected,actual=actual,expected=expected))
    report=dict(samples=len(results),reused=reused,computed=len(results)-reused,
        wrong=sum(not r['passed'] for r in results),results=results)
    cache_path.write_text(json.dumps(cache,indent=2))
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report));return bool(report['wrong'])

if __name__=='__main__':raise SystemExit(main())
