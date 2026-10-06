"""Opt-in short Character State smoke on productive routine/rotation owners."""
import argparse
import json
from pathlib import Path
import cv2
from bot.character_state import CharacterStateStore, current_character_state
from bot.productive_runtime import open_productive_runtime, default_log_path
from bot.routines import RoutineSpec, RoutineStep
from bot.world_boss_state import WorldBossEligibilityPolicy,WorldBossStateReader

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--characters',type=int,default=3,choices=range(1,5))
    parser.add_argument('--stages',action='store_true',help='one natural Stages opportunity per character')
    args=parser.parse_args()
    if not args.execute:
        parser.error('--execute required; this sends authorized game input')
    log=default_log_path('character-state')
    output=ROOT/'artifacts/character-state-live'/log.stem
    output.mkdir(parents=True,exist_ok=True)
    observations=[]
    with open_productive_runtime(log_path=log,console=None) as runtime:
        initial=runtime.observer.observe()
        if initial.state.base_context=='screen.world_boss' and not initial.state.overlays:
            WorldBossEligibilityPolicy(reader=WorldBossStateReader(runtime.ocr_engine),store=runtime.character_store,events=runtime.events).inspect(initial)
        if not runtime._navigate_to_lobby():
            raise RuntimeError('Cannot establish Lobby; no blind recovery')
        original=runtime.build_rotation
        def build_rotation(count):
            rotation=original(count)
            hook=rotation.quick_menu_ready
            def ready(snapshot,*,origin):
                scope=current_character_state()
                cid=scope[1] if scope else 'unknown'
                path=output/f'{len(observations)+1}_{cid}_qm.png'
                cv2.imwrite(str(path),snapshot.frame.image)
                hook(snapshot,origin=origin)
                observations.append(dict(character_id=cid,origin=origin,path=path.relative_to(ROOT).as_posix()))
            rotation.quick_menu_ready=ready
            return rotation
        runtime.build_rotation=build_rotation
        steps=(RoutineStep('mailbox'),RoutineStep('world_boss',config={'world_boss':{'eligibility':'CURRENT_WB_NOT_PARTICIPATED'}}))
        if args.stages:
            steps+=(RoutineStep('stages_daily'),)
        routine=RoutineSpec('state-smoke','Character state smoke',steps)
        result=runtime.run_routine(routine,character_count=args.characters)
        rows=runtime.character_store.rows()
        summary=dict(status=result.status.value,characters=result.characters_processed,rotations=result.advances_completed,
            cause=result.failure_cause,log=str(log),observations=observations,rows=[r for r in rows if r['character_id'] in {o['character_id'] for o in observations}])
    reopened=CharacterStateStore()
    summary['restart_rows']=[r for r in reopened.rows() if r['character_id'] in {o['character_id'] for o in observations}]
    reopened.close()
    summary['restart_equal']=summary['rows']==summary['restart_rows']
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True,indent=2))
    return int(result.status.value!='completed' or not summary['restart_equal'])

if __name__=='__main__':
    raise SystemExit(main())
