"""Incremental evaluation of acquired Manual Stages chrome, stocks and Auto."""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from bot.manual_stages_reader import ManualStagesDetector, buff_stock
from bot.arena_reader import crop
from bot.ocr import RapidOcrEngine

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'screencaps/manual_stages'
CASES={
    'chaos_base/after.png':dict(surface='normal',x4=False),
    'chaos_x4/after.png':dict(surface='normal',x4=True),
    'bb_base/after.png':dict(surface='normal',x4=True,stage9=True),
    'chaos_config/after.png':dict(surface='config',target='chaos_06',support='active',penance=True,hell=False,stock=[99]*4),
    'monk_chaos_hell/after.png':dict(surface='config',target='chaos_06',support='active',hell=True,penance=False),
    'bb_config/after.png':dict(surface='config',target='abyssal_rion_09',support='active',penance=True,stock=[98,98,98,97]),
    'bb_buff_consumption/after.png':dict(surface='config',target='abyssal_rion_09',support='active',penance=True,stock=[97,97,97,96]),
    'chaos_striker/after.png':dict(surface='start'),
    'monk_hell_battle/auto_on.png':dict(surface='battle',auto='off'),
    'monk_hell_battle/after.png':dict(surface='battle',auto='off'),
    'chaos_auto_02/before.png':dict(surface='battle',auto='on'),
    'chaos_auto_02/after.png':dict(surface='battle',auto='off'),
    'bb_auto_recover/auto_on.png':dict(surface='battle',auto='on'),
    'bb_auto_recover/auto_off.png':dict(surface='battle',auto='off'),
    'bb_clear_acquire/after.png':dict(surface='clear',terminal='clear'),
    'chaos_terminal/after.png':dict(surface='death',terminal='death'),
    'chaos_abandon/after.png':dict(surface='death_guide',terminal='death_guide'),
    'bb_map/after.png':dict(surface='world_map'),
    'cycle_hell_support_final/manual_prepared.png':dict(surface='config',target='chaos_06',
        hell=True,penance=False,support='active',stock=[98]*4),
    'cycle_hell_support_final/manual_clear.png':dict(surface='clear',terminal='clear'),
}

def curate():
    FIXTURES.mkdir(parents=True,exist_ok=True)
    d=ManualStagesDetector()
    manual=json.loads((ROOT/'assets/ui/landmarks/manual_stages/profile.json').read_text())
    keys=set(manual)|{'normal','elite','abyssal','config','start','world_map','world_map_chrome','loading',
        'support_active','support_ready','support_needs','support_purchase','support_full'}
    rois=sorted({tuple(d.profile[k]['search']) for k in keys} |
        {(.84,.01,.96,.105)} |
        {(round(.547+i*.076,4),.437,round(.570+i*.076,4),.481) for i in range(4)})
    entries=[]
    for index,(source,expected) in enumerate(CASES.items()):
        raw=ROOT/'artifacts/manual_stages'/source
        im=cv2.imread(str(raw))
        if im is None:raise ValueError(str(raw))
        regions=[]
        for number,roi in enumerate(rois):
            path=FIXTURES/f'{index:02d}_{number:02d}.png'
            cv2.imwrite(str(path),crop(im,roi))
            regions.append(dict(roi=roi,file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        entries.append(dict(id=source,source=str(raw.relative_to(ROOT)),
            raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),shape=list(im.shape),
            expected=expected,regions=regions))
    manifest=ROOT/'datasets/manual_stages_20261009_manifest.json'
    manifest.write_text(json.dumps(entries,indent=2)+'\n',encoding='utf8')

def replay(entry):
    image=np.zeros(entry['shape'],dtype=np.uint8);h,w=image.shape[:2]
    for region in entry['regions']:
        path=FIXTURES/region['file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=region['sha256']:raise ValueError('crop provenance mismatch')
        x1,y1,x2,y2=region['roi']
        image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(path))
    return image

def measure(image,expected,detector,engine=None):
    obs=detector.detect(image)
    actual={'surface':next((o.value for o in obs if o.name=='stages.surface'),None)}
    for key in expected:
        if key in {'x4','hell','penance'}:actual[key]=detector.toggle(image,key)
        elif key=='stage9':actual[key]=detector.present(image,key)
        elif key=='target':actual[key]=detector.config_target(image)
        elif key=='terminal':actual[key]=detector.terminal(image)
        elif key=='stock':actual[key]=[buff_stock(engine,image,i) for i in range(1,5)]
        elif key=='support':actual[key]=next((state for state in ('active','ready','needs')
            if detector.present(image,'support_'+state)),None)
        elif key=='auto':
            value=detector.auto_glow(image)
            actual[key]='on' if value is not None and value>=.025 else 'off' if value is not None and value<=.015 else 'unknown'
    # No modal, loading, active battle or map may pretend Clear Time.
    actual['terminal']=detector.terminal(image)
    return actual

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--curate',action='store_true')
    args=p.parse_args()
    if args.curate:curate()
    output=ROOT/'artifacts/manual_stages/evaluation';output.mkdir(parents=True,exist_ok=True)
    cache_path=output/'cache.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    detector=ManualStagesDetector();engine=RapidOcrEngine()
    fingerprint=hashlib.sha256(b''.join(path.read_bytes() for path in (
        ROOT/'bot/manual_stages_reader.py',ROOT/'bot/perception/stages.py',ROOT/'bot/ocr.py',
        *detector.asset_paths))).hexdigest()
    results=[];reused=0
    for entry in json.loads((ROOT/'datasets/manual_stages_20261009_manifest.json').read_text()):
        expected=dict(terminal=None,**entry['expected']) if 'terminal' not in entry['expected'] else entry['expected']
        key=hashlib.sha256((fingerprint+json.dumps(entry,sort_keys=True)).encode()).hexdigest()
        im=replay(entry)
        if key in cache:actual=cache[key];reused+=1
        else:actual=measure(im,expected,detector,engine);cache[key]=actual
        results.append(dict(id=entry['id'],expected=expected,actual=actual,passed=actual==expected))
    report=dict(samples=len(results),reused=reused,computed=len(results)-reused,
        wrong=sum(not x['passed'] for x in results),results=results)
    cache_path.write_text(json.dumps(cache,indent=2)+'\n')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return bool(report['wrong'])

if __name__=='__main__':raise SystemExit(main())
