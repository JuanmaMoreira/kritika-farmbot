"""Read-only attribution/performance audit of an actual GUI sweep log and SQLite."""
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

from bot.character_identity import CHARACTER_IDS
from bot.character_state import CharacterStateStore, DEFAULT_DB_PATH

FIELDS=('lapiz','dark_essence','light_essence','nature_essence','k_coins')

def timestamp(value):
    return datetime.fromisoformat(value).timestamp()

def audit(log,db_path,before):
    events=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
    grouped=defaultdict(list)
    for event in events:
        if event.get('character_index') is not None:
            grouped[event['character_index']].append(event)
    store=CharacterStateStore(db_path)
    try:
        rows=[dict(row) for row in store.rows()]
        operational=[dict(row) for row in store.db.execute('SELECT * FROM operational ORDER BY character_id')]
    finally:
        store.close()
    resources={row['character_id']:row for row in rows}
    errors=[]
    checks=[]
    seen=set()
    previous_sequence=-1
    durations=[]
    readers=[]
    rotations=[]
    fingerprints=defaultdict(list)
    for i,items in sorted(grouped.items()):
        def one(name):
            selected=[e for e in items if e['event']==name]
            if len(selected)!=1:
                raise ValueError(f'{i}: expected one {name}, found {len(selected)}')
            return selected[0]
        try:
            start=one('session.character.started')
            identity=one('character.identity_resolved')
            saved=one('character_state.resources_updated')
            timing=one('character_state.resource_snapshot_timing')
            snapshot=one('character_data_sweep.snapshot')
            rotation=one('rotation.started')
            end=one('rotation.completed')
            cid=identity['character_id']
            assert cid in CHARACTER_IDS.values() and cid not in seen, 'unknown/duplicate identity'
            seen.add(cid)
            assert saved['character_id']==snapshot['character_id']==timing['character_id']==cid, 'scope mismatch'
            assert snapshot['status']=='saved', 'snapshot not saved'
            times=[timestamp(e) for e in (start['timestamp'],identity['timestamp'],
                    saved['observed_at'],saved['timestamp'],end['timestamp'])]
            # float time.time and datetime.now can round the same tick differently.
            assert all(a<=b+.001 for a,b in zip(times,times[1:])), 'timestamp outside scope'
            assert snapshot['source_sequence']==timing['source_sequence']>previous_sequence, 'stale source'
            previous_sequence=timing['source_sequence']
            transitions=[e for e in items if e['event']=='transition.started' and e.get('transition')=='rotation.open_quick_menu']
            assert len(transitions)==1, 'QM open count'
            ready=next(e for e in items if e['event']=='transition.completed' and e.get('transition')=='rotation.open_quick_menu')
            assert ready['final_sequence']==timing['source_sequence'], 'snapshot does not reuse QM-ready frame'
            select=next(e for e in items if e['event']=='transition.started' and e.get('transition')=='rotation.open_character_select')
            assert timestamp(saved['timestamp'])<=timestamp(select['timestamp']), 'snapshot after Select'
            row=resources[cid]
            assert row['canonical_name']==identity['canonical_name'] and row['display_name']==identity['display_name'], 'identity metadata mismatch'
            assert abs(row['resource_observed_at']-timestamp(saved['observed_at']))<.001, 'SQLite observation timestamp mismatch'
            assert all(type(row[key]) is int and row[key]==saved[key] for key in FIELDS), 'SQLite value mismatch'
            elapsed=timestamp(end['timestamp'])-timestamp(start['timestamp'])
            durations.append(elapsed)
            readers.append(timing['duration'])
            rotations.append(timestamp(end['timestamp'])-timestamp(rotation['timestamp'])-timing['duration'])
            fingerprints[tuple(row[key] for key in FIELDS)].append(cid)
            checks.append(dict(index=i,character_id=cid,display_name=row['display_name'],
                canonical_name=row['canonical_name'],observed_at=saved['observed_at'],
                source_sequence=timing['source_sequence'],elapsed=elapsed,reader_seconds=timing['duration'],
                **{key:row[key] for key in FIELDS}))
        except (ValueError,AssertionError,StopIteration,KeyError) as error:
            errors.append(f'{i}: {error}')
    if seen!=set(CHARACTER_IDS.values()):
        errors.append(f'missing identities: {sorted(set(CHARACTER_IDS.values())-seen)}')
    if any(e['event'].startswith(('flow.','stages.','world_boss.')) for e in events):
        errors.append('productive flow events present')
    if operational!=json.loads(before.read_text()):
        errors.append('operational state differs from before (inspect ResetClock/provenance)')
    completed=[e for e in events if e['event']=='character_data_sweep.completed']
    if len(completed)!=1 or completed[0].get('status')!='completed':
        errors.append('sweep completion missing/non-completed')
    return dict(log=str(log),run_id=events[0].get('run_id'),
        session_id=next((e.get('session_id') for e in events if e['event']=='session.started'),None),
        summary=completed[0] if completed else {},errors=errors,rows=checks,
        repeated_snapshots=[v for v in fingerprints.values() if len(v)>1],operational=operational,
        median_character_seconds=median(durations) if durations else None,
        median_reader_seconds=median(readers) if readers else None,
        total_reader_seconds=sum(readers),
        median_navigation_rotation_seconds=median(rotations) if rotations else None,
        sqlite_rows=len(rows),latest_complete=sum(all(type(row[k]) is int for k in FIELDS) for row in rows))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path)
    p.add_argument('--db',type=Path,default=DEFAULT_DB_PATH)
    p.add_argument('--before',type=Path,default=Path('artifacts/character-data-sweep/operational-before.json'))
    p.add_argument('--output',type=Path,default=Path('artifacts/character-data-sweep'))
    args=p.parse_args()
    result=audit(args.log,args.db,args.before)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    if result['rows']:
        with (args.output/'resources.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(result['rows'][0]))
            writer.writeheader()
            writer.writerows(result['rows'])
    (args.output/'resources.md').write_text(
        '| Character | Lapiz | Dark | Light | Nature | K Coins | Observed UTC |\n'
        '| --- | ---: | ---: | ---: | ---: | ---: | --- |\n'+
        '\n'.join('| '+' | '.join(str(row[k]) for k in ('display_name',*FIELDS,'observed_at'))+' |' for row in result['rows']),encoding='utf-8')
    by_id={r['character_id']:r for r in result['rows']}
    columns=('display_name','character_id','stage_ads_remaining','ads_source','ads_updated_at',
             'wb_cycle_id','wb_participated','wb_source','wb_updated_at')
    with (args.output/'operational.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        for row in result['operational']:
            writer.writerow({k:by_id[row['character_id']]['display_name'] if k=='display_name' else row[k] for k in columns})
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','operational','summary')},ensure_ascii=True))
    return bool(result['errors'])

if __name__=='__main__':
    raise SystemExit(main())
