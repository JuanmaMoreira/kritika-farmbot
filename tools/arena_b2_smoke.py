"""Bounded Single x8 through occurrence factory and Session, then read-only Lobby probe.

Run within explicit Arena ownership from clean Lobby. STOP stops observation only.
No resource generators, extra batch, rotation, or unrelated gameplay step.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import cv2
from uuid import uuid4
from bot.arena_config import ArenaConfig, ArenaMode
from bot.arena_flow import ArenaFlow
from bot.arena_semantics import ArenaDifficulty, ArenaSingleExecution
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import FlowDefinition, FlowRegistry
from bot.productive_runtime import open_productive_runtime
from bot.routines import RoutineSpec, RoutineStep

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--finish-from',type=Path,help='explicit same-Single handoff; never another Start')
    args=parser.parse_args()
    output=args.output.resolve(); output.relative_to(ROOT/'artifacts')
    output.mkdir(parents=True,exist_ok=False)
    evidence={}; built=[]; following=[]
    def save(name,frame):
        path=output/f'{name}.png'
        if not cv2.imwrite(str(path),frame.image): raise OSError('evidence write failed')
        evidence[name]=dict(path=str(path.relative_to(ROOT)),sequence=frame.sequence,observed_at=frame.timestamp)
    with open_productive_runtime(log_path=output/'events.jsonl',evidence_root=output/'failures') as runtime:
        def factory(dependencies):
            settings=dependencies.config.arena
            flow=dependencies.build_arena_flow(settings.difficulty,mode=settings.mode,
                authorized_badge_ceiling=8,return_context='screen.lobby')
            flow.batch_timeout=1800. if args.finish_from else 180.; flow.unknown_grace=20.
            flow.cancel_requested=lambda:(output/'STOP').exists() or runtime.cancel_requested()
            flow.evidence_sink=save
            if args.finish_from:
                previous=args.finish_from.resolve(); previous.relative_to(ROOT/'artifacts')
                prior=json.loads((previous/'result.json').read_text())
                if (prior['physical_operation_may_be_active'] is not True
                        or prior['metrics']['inputs'].count('single_start')!=1
                        or prior['metrics']['inputs'][-1]!='single_start'
                        or prior['arena_error']!='transition_unconfirmed'):
                    raise ValueError('one recorded uncertain Start and uninterrupted physical ownership required')
                stopped=cv2.imread(str(ROOT/prior['evidence']['stopped']['path']))
                if not flow.reader.visuals.single_active(stopped):
                    raise ValueError('positive historical post-Start battle evidence required')
                start=prior['evidence']['single_start_native']
                from bot.capture import FrameSnapshot
                native=cv2.imread(str(ROOT/start['path']))
                # Archival parsing only; current control authority requires a fresh
                # positive terminal/activity in observe_started_single.
                from bot.arena_flow_reader import ArenaFlowReader
                archived=ArenaFlowReader(flow.reader.engine,clock=lambda:start['observed_at'])
                balances=archived.balances(FrameSnapshot(native,start['observed_at'],start['sequence']))
                if balances is None: raise ValueError('recorded starting balances unreadable')
                events=[json.loads(line) for line in (previous/'events.jsonl').read_text().splitlines()]
                action=next(e for e in events if e.get('event')=='action.started' and e.get('target')==[.769,.943])
                fresh=flow.source.refresh_native(); save('single_handoff_native',fresh)
                receipt=ArenaSingleExecution(uuid4().hex,uuid4().hex,settings.difficulty,8,
                    action['monotonic_timestamp'],fresh.sequence,True,balances.badges,balances.karats)
                flow.run=lambda:flow.observe_started_single(receipt)
            built.append(flow)
            return flow
        class LobbyProbe:
            name='lobby_probe'; scope=ArenaFlow.scope; contract=ArenaFlow.routine_contract
            def run(self):
                snap=runtime.observer.observe(); save('following_lobby',snap.frame)
                ok=bool(built[0]._clean_base(snap,'screen.lobby') and built[0].reader.visuals.lobby(snap.frame.image))
                following.append(ok)
                return FlowResult(FlowStatus.COMPLETED if ok else FlowStatus.FAILED,
                    error=None if ok else 'read-only following Lobby verification failed',final_snapshot=snap)
        original=runtime.registry.get('arena')
        arena=FlowDefinition(original.id,original.display_name,original.scope,original.contract,factory)
        probe=FlowDefinition('lobby_probe','Read-only Lobby probe',ArenaFlow.scope,ArenaFlow.routine_contract,lambda _:LobbyProbe())
        runtime.registry=FlowRegistry(tuple(arena if d.id=='arena' else d for d in runtime.registry.definitions)+(probe,))
        routine=RoutineSpec('arena_b2_smoke','Arena B2 focal smoke',(
            RoutineStep('arena',config={'arena':ArenaConfig(ArenaMode.SINGLE_BATTLE,ArenaDifficulty.EASY).to_dict()}),
            RoutineStep('lobby_probe')))
        if args.finish_from:
            # Resume the already active operation through its owner, rather than
            # ask Session to navigate to its ordinary Lobby entry over a result.
            arena_result=factory(runtime).run()
            result=runtime.run_routine(RoutineSpec('arena_b2_following','Arena B2 following',
                (RoutineStep('lobby_probe'),))) if arena_result.succeeded else arena_result
        else:
            result=runtime.run_routine(routine)
            arena_result=next((r for r in result.flow_results if hasattr(r,'single_result')),None)
        try: save('physical_final',runtime.observer.source.refresh_native())
        except Exception as error: evidence['final_capture_error']=str(error)
        payload=dict(status=result.status.value,error=result.error,following_lobby=following,evidence=evidence,
            metrics=built[0].metrics if built else {},
            arena_status=arena_result.status.value if arena_result else None,
            arena_error=arena_result.error if arena_result else None,
            physical_operation_may_be_active=arena_result.physical_operation_may_be_active if arena_result else None,
            single_result=asdict(arena_result.single_result) if arena_result and arena_result.single_result else None)
        (output/'result.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        print(json.dumps(payload),flush=True)
    return 0 if result.status is FlowStatus.COMPLETED else 1

if __name__=='__main__': raise SystemExit(main())
