"""One guarded acquisition input followed by bounded passive native captures.

Only under chat ownership. No automatic retries or resource generation; the
explicit buff1 Gold acquisition below requires fresh economic evidence.
Native-only acquisition owns no stream/process/forward and leaves the game state
for explicit inspection. Unknown surfaces never authorize an input.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.arena_actions import ArenaAction, ArenaControl as C
from bot.arena_flow_reader import ArenaFlowReader
from bot.capture import FrameSnapshot
from bot.config import RuntimeConfig
from bot.ocr import RapidOcrEngine
from bot.runtime import build_adb_client
from bot.semantic_actions import OpenQuickMenu, SelectQuickMenuLobby

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect', choices=('lobby', 'select_mode', 'selection', 'challenge', 'ranking', 'quick_menu', 'single_result'))
    parser.add_argument('--action', choices=('battle', 'arena', 'easy', 'back', 'quick_menu', 'ranking_ok', 'lobby', 'buff1', 'buff2', 'buff3', 'single_start', 'single_result_close'))
    parser.add_argument('--gold-proof', type=Path, help='reviewed receipt of the current buff1 prepaid reservation')
    parser.add_argument('--watch', type=float, default=3.)
    parser.add_argument('--navigate-challenge', action='store_true', help='reuse ArenaFlow navigation only')
    args = parser.parse_args()
    if args.navigate_challenge:
        if args.action:
            parser.error('navigation and one-input modes are exclusive')
        from bot.productive_runtime import open_productive_runtime
        from bot.arena_semantics import ArenaDifficulty
        output = args.output.resolve()
        output.relative_to(ROOT / 'artifacts')
        output.mkdir(parents=True, exist_ok=False)
        with open_productive_runtime(log_path=output/'events.jsonl') as runtime:
            flow = runtime.build_arena_flow(ArenaDifficulty.EASY)
            # Navigation primitives only. Never call run/_prepare/_start here.
            flow._cursor=-1; flow._last_timestamp=-1.; flow._barrier=-1.
            flow._last_native=-float('inf'); flow._latest=None
            flow.evidence={}; flow.metrics=dict(captures=0,native_captures=0,
                capture_seconds=0.,cv_seconds=0.,action_seconds=0.,
                sleep_wall_seconds=0.,stale_rejects=0,observation_ages=[],inputs=[])
            before = flow._navigate()
            cv2.imwrite(str(output/'challenge.png'), before.image)
            flow.reader.prewarm(before)
            native = flow.source.refresh_native()
            cv2.imwrite(str(output/'challenge_native.png'), native.image)
            resources = flow.reader.economy(native)
            print(json.dumps(dict(navigation='Challenge EASY',
                resources=asdict(resources) if resources else None,
                inputs=flow.metrics['inputs'])), flush=True)
        return
    if not 0 < args.watch <= 60 or (args.action and not args.expect):
        parser.error('bounded watch and positive expected surface required')
    allowed={'battle':{'lobby'},'arena':{'select_mode'},'easy':{'selection'},
        'back':{'challenge','selection','select_mode'},'quick_menu':{'challenge'},
        'ranking_ok':{'ranking'},'lobby':{'quick_menu'},
        'buff1':{'challenge'},'buff2':{'challenge'},'buff3':{'challenge'},
        'single_start':{'challenge'},'single_result_close':{'single_result'}}
    if args.action and args.expect not in allowed[args.action]:
        parser.error('action has no acquired authority on the requested surface')
    output = args.output.resolve()
    output.relative_to(ROOT / 'artifacts')
    output.mkdir(parents=True, exist_ok=False)
    adb = build_adb_client(RuntimeConfig.from_env(dotenv_path=ROOT / '.env'))
    reader = ArenaFlowReader(RapidOcrEngine())
    sequence = 0

    def capture(label):
        nonlocal sequence
        started = time.monotonic()
        utc = datetime.now(timezone.utc).isoformat()
        png = adb.capture_png()
        frame = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('invalid native capture')
        sequence += 1
        path = output / f'{sequence:03}_{label}.png'
        path.write_bytes(png)
        with (output / 'frames.jsonl').open('a', encoding='utf8') as stream:
            stream.write(json.dumps(dict(path=path.relative_to(ROOT).as_posix(),
                captured_at_utc=utc, source='native_adb', sequence=sequence,
                sequence_scope=str(output.relative_to(ROOT)), observed_at=started,
                shape=frame.shape, sha256=hashlib.sha256(png).hexdigest())) + '\n')
        return FrameSnapshot(frame, started, sequence)

    before = capture('before')
    if args.action:
        v = reader.visuals
        predicate = dict(lobby=v.lobby, select_mode=v.select_mode,
            selection=v.selection, challenge=v.clean_challenge, ranking=v.ranking,
            quick_menu=v.quick_menu, single_result=v.single_result)[args.expect]
        if not predicate(before.image) or time.monotonic()-before.timestamp > reader.max_age:
            raise RuntimeError('expected fresh surface uncredited; no input')
        if args.action.startswith('buff'):
            if args.expect!='challenge':
                raise RuntimeError('buff acquisition requires Challenge')
            reader.prewarm(before)
            before=capture('economy_before')
            facts=reader.economy(before)
            index=int(args.action[-1])-1
            if (facts is None or facts.available_badges<8 or facts.preparation.x8 is not True
                    or facts.preparation.buffs[index] is not False or facts.free_buffs[index] is None):
                raise RuntimeError('fresh x8/badges/OFF stock required; no input')
            if facts.free_buffs[index]<8:
                # Focal Gold acquisition authorized by explicit USER_GT in chat:
                # direct tiny Gold purchase, current visible buff1 price 3000.
                if index!=0 or facts.free_buffs[index]!=6:
                    raise RuntimeError('only current USER_GT buff1 Gold acquisition is covered')
                gold, _=reader._integer(before.image,(.355,.044,.445,.087),lambda:False)
                karats, _=reader._integer(before.image,(.502,.044,.565,.087),lambda:False)
                cost, _=reader._integer(before.image,(.544,.447,.591,.496),lambda:False)
                if gold is None or gold<24000 or karats is None or cost!=3000:
                    raise RuntimeError('visible Gold3000 and bounded balance uncredited; no input')
                (output/'economic_before.json').write_text(json.dumps(dict(resources=asdict(facts),
                    gold=gold,karats=karats,gold_unit_cost=cost,maximum_gold=24000))+'\n',encoding='utf8')
            if time.monotonic()-before.timestamp>reader.max_age:
                raise RuntimeError('economic acquisition expired; no input')
        if args.action=='single_start':
            if args.expect!='challenge' or args.gold_proof is None:
                raise RuntimeError('Single acquisition requires current Challenge and reviewed Gold proof')
            proof=args.gold_proof.resolve()
            proof.relative_to(ROOT/'artifacts')
            prior=json.loads((proof/'economic_before.json').read_text(encoding='utf8'))
            reader.prewarm(before)
            before=capture('single_prepared')
            facts=reader.economy(before)
            gold,_=reader._integer(before.image,(.355,.044,.445,.087),lambda:False)
            karats,_=reader._integer(before.image,(.502,.044,.565,.087),lambda:False)
            if (facts is None or facts.available_badges<8 or facts.preparation.x8 is not True
                    or facts.preparation.buffs!=(True,True,True) or facts.free_buffs[0]!=-2
                    or any(value is None or value<8 for value in facts.free_buffs[1:])
                    or prior['resources']['free_buffs'][0]!=6 or prior['gold_unit_cost']!=3000
                    or gold!=prior['gold']-6000 or karats!=prior['karats']):
                raise RuntimeError('fresh x8/badges/shared buffs and prepaid deficit uncredited; no Start')
            if time.monotonic()-before.timestamp>reader.max_age:
                raise RuntimeError('single economy expired; no Start')
            (output/'single_prepared.json').write_text(json.dumps(dict(resources=asdict(facts),
                gold=gold,karats=karats,prepaid_gold_proof=proof.relative_to(ROOT).as_posix()))+'\n',encoding='utf8')
        if args.action == 'back':
            if not v.back_visible(before.image):
                raise RuntimeError('Back control uncredited; no input')
        action = (OpenQuickMenu() if args.action == 'quick_menu' else
                  SelectQuickMenuLobby() if args.action == 'lobby' else ArenaAction(C(args.action)))
        (output / 'action.json').write_text(json.dumps(dict(action=args.action,
            expected=args.expect, before_sequence=before.sequence,
            requested_at_utc=datetime.now(timezone.utc).isoformat())) + '\n', encoding='utf8')
        ActionExecutor(adb).execute(action, FrameGeometry.from_frame(before.image), source_sequence=before.sequence)
    bound = time.monotonic() + args.watch
    while time.monotonic() < bound:
        last=capture('after')
        time.sleep(.25)
    if args.action and args.action.startswith('buff'):
        facts=reader.economy(last)
        gold,_=reader._integer(last.image,(.355,.044,.445,.087),lambda:False)
        karats,_=reader._integer(last.image,(.502,.044,.565,.087),lambda:False)
        print(json.dumps(dict(resources=asdict(facts) if facts else None,gold=gold,karats=karats)),flush=True)
    print(json.dumps(dict(output=output.relative_to(ROOT).as_posix(), captures=sequence,
                         input=args.action)), flush=True)


if __name__ == '__main__':
    main()
