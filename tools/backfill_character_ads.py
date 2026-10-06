"""Explicit current-epoch Ads backfill from causal logs with recognized names."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from bot.character_identity import CHARACTER_IDS,PERSONAL_NAME_CLASSES
from bot.character_state import CharacterStateStore, DAY

def backfill(store,path):
    path=Path(path)
    clock=store.clock.state()
    if clock is None:
        raise ValueError('WB countdown calibration is required before current-epoch backfill')
    source='LOG_BACKFILL:'+hashlib.sha256(path.read_bytes()).hexdigest()
    names={name:CHARACTER_IDS[canonical] for canonical,name in PERSONAL_NAME_CLASSES.items()}
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    identities={}
    ambiguous=set()
    for row in rows:
        key=(row.get('session_id'),row.get('character_index'))
        name=row.get('character_name')
        if name in names:
            cid=names[name]
            if key in identities and identities[key]!=cid:
                ambiguous.add(key)
            identities[key]=cid
    facts={}
    for row in rows:
        key=(row.get('session_id'),row.get('character_index'))
        cid=identities.get(key)
        if cid is None or key in ambiguous:
            continue
        at=datetime.fromisoformat(row['timestamp']).timestamp()
        if not clock['next_daily']-DAY <= at < clock['next_daily']:
            continue
        if row['event']=='stages.ad_selection' and type(row.get('video_count')) is int and 0<=row['video_count']<=2:
            count=row['video_count']
            facts[cid]=(count,'DAILY_EXHAUSTED' if count==0 else 'OBSERVED',at)
        elif row['event']=='stages.sapphire_effect' and row.get('after',0)>row.get('before',0) and cid in facts:
            count,_,_=facts[cid]
            facts[cid]=(max(0,count-1),'REWARDED',at)
    written=[]
    for cid,(count,status,at) in facts.items():
        if store.ads(cid,status,observed_count=count,at=at,source=source):
            written.append(dict(character_id=cid,remaining=count,status=status,observed_at=at))
    return dict(source=source,known_scopes=len(identities),ambiguous_scopes=len(ambiguous),written=written)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    args=parser.parse_args()
    store=CharacterStateStore()
    try:
        result=backfill(store,args.log)
        Path('artifacts/character_ads_backfill.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        store.close()

if __name__=='__main__': main()
