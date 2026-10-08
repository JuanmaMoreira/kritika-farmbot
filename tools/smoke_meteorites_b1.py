"""Authorized B1 chain: 11 Equip, 11 slot Unequip, restore Set 1.

Requires manual shared-set preparation through chat/steer. No character change.
First divergence stops all inputs; runtime owners close source resources.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from bot.productive_runtime import open_productive_runtime, CancellationToken
from bot.shared_meteorites import SharedMeteoritesPreparation
from tools.runtime_cli import cancellation_signals

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    output = args.output; output.mkdir(parents=True, exist_ok=True)
    token = CancellationToken()
    report = dict(scope='Meteorites B1: first divergence stops inputs',
                  baseline='ce44fe55ef0490e068f972b59e96c1e9a3c58350',
                  steps=[], final_verified=False, character_id=args.character_id)
    io_seconds = 0.
    def save(name, result, progress):
        nonlocal io_seconds
        started = time.monotonic()
        step = dict(name=name, frames=[])
        for role, frame in rt.evidence.items():
            if frame is None or role == 'freshness_reject': continue
            path = output/(name+'_'+role+'.png')
            if not cv2.imwrite(str(path), frame.image): raise RuntimeError('evidence_write_failed')
            step['frames'].append(dict(role=role, path=path.relative_to(ROOT).as_posix(),
                sequence=frame.sequence, timestamp_monotonic=frame.timestamp,
                shape=list(frame.image.shape), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        if result is not None: step['result'] = asdict(result)
        step['equipped'] = list(progress.equipped); step['released'] = list(progress.released)
        report['steps'].append(step)
        report['progress'] = asdict(progress)
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
        io_seconds += time.monotonic()-started
    try:
        with cancellation_signals(token), open_productive_runtime(
                log_path=output/'runtime.jsonl', evidence_root=output/'failure',
                dotenv_path=args.dotenv_path,
                cancel_token=token, console=None) as productive:
            rt = productive.build_meteorites_runtime()
            rt.reader.engine.recognize(np.zeros((32,120,3),np.uint8))
            def record(name, result, progress):
                if result is None:
                    if name.startswith('inspect_'): rt.evidence['final'] = rt._latest
                    else: rt.evidence = {name: rt._latest}
                save(name, result, progress)
            flow = SharedMeteoritesPreparation(rt, record=record)
            p = flow.setup(productive.observer, productive.build_verified_transition(),
                           via_quick_menu=args.quick_menu)
            report['setup_evidence_io_seconds'] = io_seconds
            if p.phase == 'equipped': p = flow.cleanup()
            report['progress'] = asdict(p)
            report['final_verified'] = p.phase == 'complete'
            report['evidence_io_seconds'] = io_seconds
            report['final'] = asdict(p.known_bag) if p.known_bag else None
            if not report['final_verified']:
                save('first_divergence', None, p)
    except Exception as error:
        report['error'] = str(error)
        if 'flow' in locals():
            report['progress'] = asdict(flow.progress)
            rt.evidence['divergence'] = rt._latest
            save('first_divergence', None, flow.progress)
    finally:
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    print(json.dumps(dict(final_verified=report['final_verified'],
        error=report.get('error'), progress=report.get('progress',{})), ensure_ascii=False))
    return 0 if report['final_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character-id', required=True, help='USER_GT prepared identity, never used to switch')
    parser.add_argument('--quick-menu', action='store_true')
    parser.add_argument('--dotenv-path', type=Path, default=ROOT/'.env')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/meteorites_b1'/time.strftime('%Y%m%d_%H%M%S'))
    raise SystemExit(run(parser.parse_args()))
