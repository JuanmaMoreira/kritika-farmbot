"""Offline reproduction of reviewed Arena previous-season evidence and crops.

No device calls or physical labels inferred from detectors. Raw native captures
remain intact; fixtures are reduced replay copies, not additional live samples.
"""
import hashlib
import json
import shutil
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/'artifacts/arena_previous_rewards_20261012'
POPUP = 'popup.arena_previous_rewards'
LANDMARK = 'landmark.arena_previous_rewards'
ROIS = {
    'arena_notice': (.434, .336, .660, .380),
    'past_results': (.460, .468, .640, .513),
    'mailbox': (.349, .723, .652, .763),
    'ok': (.436, .777, .564, .866),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2)+'\n', encoding='utf8')


def main():
    curated = ROOT/'screencaps/semantic/arena-previous-rewards/20261012'
    fixtures = ROOT/'tests/fixtures/arena_previous_rewards'
    assets = ROOT/'assets/arena/previous_rewards'
    for folder in (curated, fixtures, assets):
        folder.mkdir(parents=True, exist_ok=True)
    entries = []
    portable = []
    routes = [
        ('lobby_route_live', 'lobby_before', False),
        ('arena_entry', 'select_mode_before', False),
        ('arena_entry', 'previous_rewards', True),
    ]
    if (RAW/'ok_close/frames.jsonl').is_file():
        routes += [('ok_close','ok_before',True),('ok_close','ok_after',False)]
    for route, label, positive in routes:
        sources = ([RAW/route/'001_before.png'] if not positive else
                   sorted((RAW/route).glob('*_after.png')))
        if route=='ok_close':
            sources=([RAW/route/'001_before.png'] if positive else
                     [RAW/route/'002_after.png',RAW/route/'003_settled.png'])
        records = {r['path']: r for r in map(json.loads,
            (RAW/route/'frames.jsonl').read_text().splitlines())}
        for index, source in enumerate(sources, 1):
            # Reviewed first post-tap native frame is still Select Mode + Loading.
            observed_positive=positive and not (route=='arena_entry' and source.name=='002_after.png')
            path = curated/f'{label}_{index:02}.png'
            shutil.copyfile(source, path)
            raw_path = source.relative_to(ROOT).as_posix()
            entry = dict(path=path.relative_to(ROOT).as_posix(), sha256=digest(path),
                raw_source=raw_path, capture_metadata=records[raw_path],
                annotation_authority='LIVE_EVIDENCE reviewed against USER_GT',
                base_context='screen.arena' if observed_positive or route=='ok_close' else
                    ('screen.lobby' if route=='lobby_route_live' else 'screen.arena_select_mode'),
                overlays=[POPUP] if observed_positive else [], observations=[LANDMARK] if observed_positive else [],
                physical_state='arena_previous_rewards' if observed_positive else 'arena_selection' if route=='ok_close' else
                    ('select_mode_loading' if positive else label),
                review_status='confirmed', expected_previous_rewards=observed_positive)
            entries.append(entry)
            image = cv2.imread(str(path)); h,w = image.shape[:2]
            target = fixtures/path.name
            cv2.imwrite(str(target), cv2.resize(image,(round(w/2),round(h/2)),interpolation=cv2.INTER_AREA))
            portable.append(dict(path=target.relative_to(ROOT).as_posix(),sha256=digest(target),
                source=entry['path'],source_sha256=entry['sha256'],expected_previous_rewards=observed_positive,
                physical_state=entry['physical_state'],
                authority=entry['annotation_authority']))
    # Nearby existing physical negatives, with reviewed labels from their manifests.
    for manifest_name, predicate in (
        ('world_boss_semantic_manifest.json', lambda e:'popup.world_boss_previous_rewards' in e.get('overlays',[])),
        ('monster_wave_semantic_manifest.json', lambda e:'popup.monster_wave_weekly_results' in e.get('overlays',[])),
    ):
        data=json.loads((ROOT/'datasets'/manifest_name).read_text(encoding='utf8'))
        candidates=[e for e in data['entries'] if predicate(e)]
        if not candidates:
            raise ValueError(f'No reviewed nearby negative in {manifest_name}')
        entry=candidates[0]; source=ROOT/entry['path']
        source_hash=digest(source)
        if entry.get('sha256',source_hash)!=source_hash:
            raise ValueError(f'Negative hash mismatch: {source}')
        image=cv2.imread(str(source));h,w=image.shape[:2]
        target=fixtures/(manifest_name.split('_semantic')[0]+'_season_negative.png')
        cv2.imwrite(str(target),cv2.resize(image,(round(w/2),round(h/2)),interpolation=cv2.INTER_AREA))
        portable.append(dict(path=target.relative_to(ROOT).as_posix(),sha256=digest(target),
            source=entry['path'],source_sha256=source_hash,expected_previous_rewards=False,
            authority='Existing confirmed semantic manifest', source_manifest='datasets/'+manifest_name))
    positive=next(e for e in portable if e['expected_previous_rewards'])
    frame=cv2.imread(str(ROOT/positive['path']));h,w=frame.shape[:2]
    specs=[]
    for name, roi in ROIS.items():
        l,t,r,b=roi;target=assets/(name+'.png')
        cv2.imwrite(str(target),frame[round(t*h):round(b*h),round(l*w):round(r*w)])
        specs.append(dict(id='previous_'+name,path=target.relative_to(ROOT).as_posix(),
            roi=roi,threshold=.92,reference_shape=[h,w],sha256=digest(target),
            source=positive['source'],source_sha256=positive['source_sha256'],
            fixture_source=positive['path'],fixture_sha256=positive['sha256']))
    # Native inspection crops preserve readable amounts and controls independently.
    frame=cv2.imread(str(ROOT/positive['source']));h,w=frame.shape[:2]
    crops=[]
    for name,roi in dict(modal=(.200,.154,.800,.888),results=(.213,.441,.789,.718),
                         controls=(.349,.723,.652,.866)).items():
        l,t,r,b=roi;target=RAW/(name+'_native_crop.png')
        cv2.imwrite(str(target),frame[round(t*h):round(b*h),round(l*w):round(r*w)])
        crops.append(dict(path=target.relative_to(ROOT).as_posix(),roi=roi,sha256=digest(target),
            source=positive['source'],source_sha256=positive['source_sha256']))
    write_json(RAW/'crops.json',dict(crops=crops))
    write_json(ROOT/'datasets/arena_previous_rewards_semantic_manifest.json',dict(version=1,
        curation=dict(character='Drakenn26', source='native_adb',
            route='Lobby -> Battle -> Select Mode Arena -> Arena + MODAL',
            raw_retention='Preserved; initial acquisition no OK; follow-up explicit single OK acknowledgment, no Mailbox claim',
            limitations='One character, one onset; first after frame is Loading, next two are passive modal frames, not independent eligibility samples',
            base_annotation='Physical Arena parent from route/visible title; detector does not fabricate occluded BASE'),
        entries=entries))
    write_json(fixtures/'manifest.json',dict(schema_version=1,entries=portable))
    write_json(ROOT/'datasets/arena_previous_rewards_assets_manifest.json',dict(schema_version=1,assets=specs))


if __name__=='__main__':main()
