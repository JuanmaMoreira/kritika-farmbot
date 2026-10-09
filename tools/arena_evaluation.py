"""Incremental Arena detector + focal OCR evaluator. Portable by default.

--acquired also validates the local acquisition corpus (never raw artifacts).
--existing-negatives evaluates only the added detector on confirmed old frames.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import perf_counter

import cv2

from bot.arena_reader import ArenaDetector, ArenaResultReader
from bot.arena_semantics import ArenaBatchExecution, ArenaDifficulty, ARENA_RESULT, ARENA_ACTIVE, ARENA_SELECT, ARENA_CHALLENGE, ARENA_CONFIG, ARENA_RANKING, ARENA_INSUFFICIENT
from bot.capture import FrameSnapshot
from bot.ocr import RapidOcrEngine
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs

ROOT = Path(__file__).resolve().parents[1]


class TimedOcr:
    def __init__(self):
        self.engine = RapidOcrEngine()
        self.milliseconds = []

    def recognize(self, image):
        started = perf_counter()
        result = self.engine.recognize(image)
        self.milliseconds.append((perf_counter()-started)*1000)
        return result


def evaluate(*, acquired=False, existing_negatives=False):
    fixtures = json.loads((ROOT/'tests/fixtures/arena_phase_a/manifest.json').read_text(encoding='utf8'))
    entries = [dict(e, expected_terminal=e.get('expected_terminal',e['numeric_read_authorized'])) for e in fixtures['entries']]
    if acquired:
        acquisition = json.loads((ROOT/'datasets/arena_hil_20261008_manifest.json').read_text(encoding='utf8'))
        entries += [dict(e, id=e.get('label') or Path(e['curated_path']).stem, path=e['curated_path'],
                         expected_terminal=e['numeric_read_authorized']) for e in acquisition['entries']]
    by_path = {e['path']:e for e in entries}
    for path, entry in by_path.items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'corpus hash mismatch: {path}')
    detector = ArenaDetector()
    output = ROOT/'artifacts/arena_phase_a'
    output.mkdir(parents=True, exist_ok=True)
    frames, stats = evaluate_detector_frame_pairs(ROOT, sorted(by_path), [detector], cache_path=output/'cache.json')
    engine = TimedOcr()
    reader = ArenaResultReader(engine, clock=lambda:100.)
    execution = ArenaBatchExecution('acquisition-replay','replay-lifetime',ArenaDifficulty.EASY,8,10.,1,True)
    wrong = []; rows = []; ocr_ms = []; terminal_ms = []; cold_ms = None
    for frame in frames:
        entry = by_path[frame.path]
        names = {o.name for o in frame.observations}
        errors = []
        expected = entry['expected_terminal']
        if (ARENA_RESULT in names) != expected:
            errors.append('terminal identity')
        state = entry['physical_state']
        required = (ARENA_SELECT if state == 'arena_select' else
                    ARENA_CHALLENGE if state.startswith('arena_challenge') else
                    ARENA_CONFIG if state.startswith('arena_auto_config') else
                    ARENA_RANKING if state == 'arena_new_ranking' else
                    ARENA_INSUFFICIENT if state == 'insufficient_badges_purchase' else
                    ARENA_ACTIVE if state == 'arena_battle_auto_active' else None)
        # Corruption is allowed to lose a landmark; never a numeric authority.
        clean = entry.get('visual_integrity','clean_for_target') == 'clean_for_target'
        if required and clean and required not in names:
            errors.append(required)
        image = cv2.imread(str(ROOT/frame.path))
        started = perf_counter(); terminal = reader.visuals.terminal(image)
        terminal_ms.append((perf_counter()-started)*1000)
        started = perf_counter(); calls_before = reader.ocr_calls
        result = reader.read(FrameSnapshot(image,100.,2), execution, run_id=execution.run_id, source_id=execution.source_id)
        elapsed = (perf_counter()-started)*1000
        if reader.ocr_calls > calls_before:
            if cold_ms is None:
                cold_ms = elapsed
            else:
                ocr_ms.append(elapsed)
        expected_reader = entry.get('expected_reader',[104,104] if expected else None)
        actual_reader = [result.used_tickets,result.won_tickets] if result else None
        if actual_reader != expected_reader:
            errors.append(f'numeric result expected {expected_reader}, got {actual_reader}')
        if not expected and result is not None:
            errors.append('negative accepted')
        rows.append(dict(path=frame.path, errors=errors, terminal=terminal, reader_ms=elapsed,
                         ocr_calls=reader.ocr_calls-calls_before))
        if errors:
            wrong.append(rows[-1]); print('WRONG',frame.path,errors)
    negative_stats = None
    if existing_negatives:
        from tools.production_perception_evaluation import DEFAULT_MANIFEST_PATHS
        paths = set()
        for path in DEFAULT_MANIFEST_PATHS:
            manifest = json.loads((ROOT/path).read_text(encoding='utf8'))
            paths.update(e['path'] for e in manifest.get('entries',[]) if e.get('review_status') == 'confirmed')
        negatives, negative_stats = evaluate_detector_frame_pairs(ROOT, sorted(paths), [ArenaDetector()], cache_path=output/'negative_cache.json')
        wrong += [dict(path=f.path,errors=['foreign observation'], observations=[o.name for o in f.observations]) for f in negatives if f.observations]
        print('Existing confirmed negatives:',len(paths),asdict(negative_stats))
    report = dict(samples=len(rows), wrong=wrong, incremental=asdict(stats), rows=rows,
                  cost=dict(cold_reader_ms=cold_ms, warm_reader_ms=ocr_ms,
                            terminal_cv_ms=terminal_ms, ocr_ms=engine.milliseconds,
                            total_ocr_calls=reader.ocr_calls),
                  negative_stats=asdict(negative_stats) if negative_stats else None)
    (output/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(f'Arena: {len(rows)} samples, {len(wrong)} wrong; incremental={asdict(stats)}; OCR calls={reader.ocr_calls}')
    print('Cold reader ms:',cold_ms,'warm reader ms:',ocr_ms)
    return len(wrong)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquired',action='store_true')
    parser.add_argument('--existing-negatives',action='store_true')
    args = parser.parse_args()
    raise SystemExit(bool(evaluate(acquired=args.acquired,existing_negatives=args.existing_negatives)))
