"""Incremental B1 focal authority replay; shared-title negatives never become terminal."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import perf_counter
import cv2
from bot.arena_flow_reader import ArenaFlowReader, ArenaFlowVisuals
from bot.capture import FrameSnapshot
from bot.arena_semantics import ArenaBatchExecution, ArenaDifficulty
from bot.observations import Observation, ObservationSource
from tools.arena_evaluation import TimedOcr
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs

ROOT=Path(__file__).resolve().parents[1]


class ArenaB1Probe:
    """Evaluator adapter only; productive wait calls the reader directly."""
    def __init__(self):
        self._v=ArenaFlowVisuals()
        self.asset_paths=(*self._v.asset_paths,ROOT/'bot/arena_reader.py',ROOT/'bot/arena_flow_reader.py',
                          ROOT/'datasets/arena_visual_assets_manifest.json')
    def detect(self,frame):
        return tuple(Observation('landmark.arena_b1_'+name,1.,ObservationSource.LOCAL_CV)
            for name,fn in [('terminal',self._v.terminal),('lobby',self._v.lobby),
                            ('select_mode',self._v.select_mode),('loading',self._v.loading),
                            ('challenge',self._v.clean_challenge)] if fn(frame))


def evaluate(acquired=False,existing_negatives=False):
    entries=json.loads((ROOT/'tests/fixtures/arena_b1/manifest.json').read_text(encoding='utf8'))['entries']
    expected={'lobby':{'lobby'},'lobby_variant':{'lobby'},'ranking_entry':set(),
              'config_variant':set(),'config_native_full':set(),'insufficient_live':set(),
              'terminal_48':{'terminal'},'prepared_live':{'challenge'},
              'select_mode':{'select_mode'},'off':{'challenge'},'buff1':{'challenge'},
              'buff12':{'challenge'},'after':{'challenge'},'loading':{'loading'}}
    for e in entries:
        e['expected']=expected[e['id']]
    if acquired:
        for e in json.loads((ROOT/'datasets/arena_hil_20261008_manifest.json').read_text(encoding='utf8'))['entries']:
            entry=dict(e,path=e['curated_path'],expected=None)
            entry['terminal_expected']=e['numeric_read_authorized']
            entries.append(entry)
    output=ROOT/'artifacts/arena_b1'; output.mkdir(parents=True,exist_ok=True)
    by_path={e['path']:e for e in entries}; wrong=[]
    for path,e in by_path.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=e['sha256']:
            raise ValueError(f'fixture hash mismatch: {path}')
    frames,stats=evaluate_detector_frame_pairs(ROOT,sorted(by_path),[ArenaB1Probe()],cache_path=output/'cache.json')
    for f in frames:
        actual={o.name.removeprefix('landmark.arena_b1_') for o in f.observations}; e=by_path[f.path]
        if ((e['expected'] is not None and actual!=e['expected']) or
                (e['expected'] is None and ('terminal' in actual)!=e['terminal_expected'])):
            wrong.append(dict(path=f.path,actual=sorted(actual),expected=sorted(e['expected']) if e['expected'] is not None else e['terminal_expected']))
    negative_stats=None
    if existing_negatives:
        from tools.production_perception_evaluation import DEFAULT_MANIFEST_PATHS
        paths=set()
        for manifest in DEFAULT_MANIFEST_PATHS:
            data=json.loads((ROOT/manifest).read_text(encoding='utf8'))
            paths.update(e['path'] for e in data.get('entries',[]) if e.get('review_status')=='confirmed')
        negatives,negative_stats=evaluate_detector_frame_pairs(ROOT,sorted(paths),[ArenaB1Probe()],cache_path=output/'negative_cache.json')
        # Lobby matches are legitimate; these old corpora have no Arena terminal.
        for f in negatives:
            if any(o.name in ('landmark.arena_b1_terminal','landmark.arena_b1_select_mode') for o in f.observations):
                wrong.append(dict(path=f.path,error='foreign terminal/entry'))
    engine=TimedOcr(); reader=ArenaFlowReader(engine,clock=lambda:100.); economy=[]
    expected_counts={'off':(106,(923,999,999)),'buff1':(106,(915,999,999)),
                     'buff12':(106,(915,991,999)),'after':(2,(819,895,999))}
    prewarm=perf_counter(); reader.prewarm(FrameSnapshot(cv2.imread(str(ROOT/'tests/fixtures/arena_b1/off.png')),100.,1))
    prewarm_seconds=perf_counter()-prewarm
    for name,expected_count in expected_counts.items():
        image=cv2.imread(str(ROOT/f'tests/fixtures/arena_b1/{name}.png'))
        started=perf_counter(); facts=reader.economy(FrameSnapshot(image,100.,2))
        elapsed=perf_counter()-started
        actual=(facts.available_badges,facts.free_buffs) if facts else None
        if actual!=expected_count: wrong.append(dict(fixture=name,error='economic OCR',actual=actual))
        economy.append(dict(fixture=name,seconds=elapsed,actual=actual))
    result_image=cv2.imread(str(ROOT/'tests/fixtures/arena_phase_a/native.png'))
    execution=ArenaBatchExecution('b1-replay','replay-source',ArenaDifficulty.EASY,8,10.,1,True)
    reader_warm_ms=[]
    for _ in range(5):
        started=perf_counter()
        result=reader.read(FrameSnapshot(result_image,100.,2),execution,run_id=execution.run_id,source_id=execution.source_id)
        reader_warm_ms.append((perf_counter()-started)*1000)
        if result is None or (result.used_tickets,result.won_tickets)!=(104,104):
            wrong.append(dict(error='B1 terminal reader'))
    live_replay=reader.read(FrameSnapshot(cv2.imread(str(ROOT/'tests/fixtures/arena_b1/terminal_48.png')),100.,2),
                            execution,run_id=execution.run_id,source_id=execution.source_id)
    if live_replay is None or (live_replay.used_tickets,live_replay.won_tickets)!=(48,48):
        wrong.append(dict(error='B1 live 48/48 terminal replay'))
    # Warm focal costs measured separately from capture, decode and live elapsed time.
    probe=reader.visuals; cv_cost={}
    for name,fn in [('terminal',probe.terminal),('challenge',probe.clean_challenge),('active',probe.active)]:
        image=cv2.imread(str(ROOT/'tests/fixtures/arena_phase_a'/('native.png' if name=='terminal' else 'battle.png' if name=='active' else 'easy_off.png')))
        times=[]
        for _ in range(20):
            start=perf_counter(); fn(image); times.append((perf_counter()-start)*1000)
        cv_cost[name]=times
    report=dict(samples=len(frames),wrong=wrong,incremental=asdict(stats),
        negatives=asdict(negative_stats) if negative_stats else None,prewarm_seconds=prewarm_seconds,
        economy=economy,ocr_calls=reader.ocr_calls,reader_warm_ms=reader_warm_ms,cv_ms=cv_cost)
    (output/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,default=list))
    return bool(wrong)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquired',action='store_true'); parser.add_argument('--existing-negatives',action='store_true')
    args=parser.parse_args(); raise SystemExit(evaluate(args.acquired,args.existing_negatives))
