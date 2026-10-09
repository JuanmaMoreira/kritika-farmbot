"""One explicitly authorized Arena batch. Operator prepares resources; no generators.

Run only after chat HIL approval, from clean Lobby. STOP cancels observation,
not physical Auto Repeat. Existing productive runtime owns all device cleanup.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4
import cv2
from bot.arena_semantics import ArenaDifficulty, ArenaBatchExecution
from bot.arena_actions import ArenaAction, ArenaControl as C
from bot.action_executor import FrameGeometry
from bot.productive_runtime import open_productive_runtime

ROOT=Path(__file__).resolve().parents[1]


def existing_batch_receipt(previous, difficulty, character, ceiling, source, save):
    """Explicit HIL source handoff; no historic receipt silently reused."""
    prior=json.loads(previous.read_text(encoding='utf8'))
    execution=prior.get('execution') or {}
    start=prior.get('evidence',{}).get('start_verified') or {}
    inputs=prior.get('metrics',{}).get('inputs',[])
    badges=prior.get('metrics',{}).get('prepared_resources',{}).get('badges')
    if (prior.get('physical_operation_may_be_active') is not True
            or prior.get('phase')!='active' or inputs.count('start')!=1 or inputs[-1:]!=['start']
            or execution.get('difficulty')!=difficulty.value or execution.get('multiplier')!=8
            or prior.get('character')!=character or prior.get('authorized_badges')!=ceiling
            or not start or start.get('observed_at',-1)<=execution.get('started_at',0)
            or start.get('sequence',-1)<=execution.get('after_sequence',0)
            or type(badges) is not int or badges<8):
        raise ValueError('single verified Start and uninterrupted HIL ownership required')
    # Archival receipt remains invalid. A new lifetime/sequence segment is explicit.
    frame=source.refresh_native(); save('handoff_native',frame)
    receipt=ArenaBatchExecution(execution['run_id'],uuid4().hex,difficulty,8,
                               execution['started_at'],frame.sequence,True)
    return receipt,badges,dict(previous_result=str(previous),previous_source_id=execution['source_id'],
                              new_source_id=receipt.source_id,authority='recorded Start + positive Loading; uninterrupted HIL ownership')


def recover_prestart(runtime,reader,previous,save):
    """HIL-only, operator-authorized recovery; no production route assumed.

    A recorded configuration stop BEFORE any Start is the idle authority.
    Challenge alone cannot authorize this recovery. Each input is sent once.
    """
    prior=json.loads(previous.read_text(encoding='utf8'))
    if (prior.get('phase')!='configuration' or prior.get('execution') is not None
            or prior.get('physical_operation_may_be_active') is not False
            or 'start' in prior.get('metrics',{}).get('inputs',[])):
        raise ValueError('known pre-start configuration stop required')
    source=runtime.observer.source; v=reader.visuals
    def fresh(predicate,*,sequence=-1,barrier=-1.):
        bound=time.monotonic()+8.
        while time.monotonic()<bound:
            frame=source.refresh_native()
            if (frame.sequence>sequence and frame.timestamp>barrier
                    and 0<=time.monotonic()-frame.timestamp<=reader.max_age
                    and predicate(frame.image)):
                return frame
        raise RuntimeError('HIL navigation destination unconfirmed; no next input')
    before=fresh(v.config); save('recovery_config',before)
    step_index=0
    def step(control,before,expected):
        nonlocal step_index
        step_index+=1
        save(f'recovery_{step_index:02}_{control.value}_before',before)
        if not 0<=time.monotonic()-before.timestamp<=reader.max_age:
            raise RuntimeError('HIL navigation action source expired')
        back_asset='flow_challenge_back_button' if v.clean_challenge(before.image) else 'flow_back_button'
        if control is C.BACK and not v.clear(before.image,back_asset):
            raise RuntimeError('visible Back control uncredited')
        runtime.actions.execute(ArenaAction(control),FrameGeometry.from_frame(before.image),
                                events=runtime.events,source_sequence=before.sequence)
        barrier=time.monotonic()
        after=fresh(expected,sequence=before.sequence,barrier=barrier)
        save(f'recovery_{step_index:02}_{control.value}_after',after)
        return after
    before=step(C.CONFIG_CLOSE,before,v.clean_challenge)
    before=step(C.BACK,before,lambda f:v.selection(f) or v.ranking(f))
    if v.ranking(before.image):
        before=step(C.RANKING_OK,before,v.selection)
    before=step(C.BACK,before,lambda f:v.select_mode(f) or v.lobby(f))
    if v.select_mode(before.image):
        before=step(C.BACK,before,v.lobby)
    if not v.lobby(before.image):
        raise RuntimeError('Lobby return uncredited')


def finish_recorded_result_return(runtime, flow, previous, save):
    """HIL cleanup of an already read and acknowledged result; never another OK."""
    prior=json.loads(previous.read_text(encoding='utf8'))
    if (prior.get('phase')!='closing' or prior.get('physical_operation_may_be_active') is not False
            or not prior.get('batch_result') or prior.get('metrics',{}).get('inputs')!=['result_ok']):
        raise ValueError('recorded valid result and single prior acknowledgment required')
    source=runtime.observer.source; v=flow.reader.visuals
    before=source.refresh_native(); save('return_before',before)
    if not (v.insufficient(before.image) and 0<=time.monotonic()-before.timestamp<=flow.reader.max_age):
        raise RuntimeError('fresh Insufficient Badge required; no input sent')
    runtime.actions.execute(ArenaAction(C.BADGES_NO),FrameGeometry.from_frame(before.image),
                            events=runtime.events,source_sequence=before.sequence)
    barrier=time.monotonic(); bound=barrier+12.
    while time.monotonic()<bound:
        frame=source.refresh_native()
        if frame.sequence>before.sequence and frame.timestamp>barrier and v.clean_challenge(frame.image):
            save('return_native',frame)
            final=runtime.observer.observe()
            if (flow._clean_base(final,'screen.arena') and v.clean_challenge(final.frame.image)
                    and 0<=time.monotonic()-final.frame.timestamp<=flow.reader.max_age):
                save('return_base_verified',final.frame)
                facts=flow.reader.economy(frame)
                return dict(status='completed_hil_return',previous_result=str(previous),
                            batch_result=prior['batch_result'],physical_operation_may_be_active=False,
                            inputs=['badges_no'],final_resources=asdict(facts) if facts else None)
            raise RuntimeError('BASE return uncredited; no repeated input')
    raise RuntimeError('No return unconfirmed; no repeated input')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--difficulty',choices=[d.value for d in ArenaDifficulty],required=True)
    parser.add_argument('--character',required=True,help='operator-confirmed identity (USER_GT)')
    parser.add_argument('--authorized-badges',type=int,required=True)
    parser.add_argument('--execute',action='store_true',help='only after explicit chat authorization')
    parser.add_argument('--recover-prestart-from',type=Path,help='only after operator hands over known pre-start navigation')
    parser.add_argument('--observe-started-from',type=Path,help='passive continuation of the SAME verified physical batch')
    parser.add_argument('--finish-return-from',type=Path,help='HIL cleanup after a recorded single result OK')
    args=parser.parse_args()
    if not args.execute or args.authorized_badges<8:
        parser.error('explicit --execute and authorized Badge ceiling >=8 required')
    if sum(bool(x) for x in (args.recover_prestart_from,args.observe_started_from,args.finish_return_from))>1:
        parser.error('recovery modes are mutually exclusive')
    output=args.output.resolve(); output.relative_to(ROOT/'artifacts')
    output.mkdir(parents=True,exist_ok=False)
    stop=output/'STOP'; evidence={}
    def save(name,snapshot):
        path=output/(name+'.png')
        if name=='unrecognized_wait_surface' and not (output/'first_unknown.png').exists():
            cv2.imwrite(str(output/'first_unknown.png'),snapshot.image)
        if not cv2.imwrite(str(path),snapshot.image): raise OSError('evidence write failed')
        evidence[name]=dict(path=str(path),sequence=snapshot.sequence,observed_at=snapshot.timestamp,
                            recorded_at_utc=datetime.now(timezone.utc).isoformat())
    with open_productive_runtime(log_path=output/'events.jsonl',evidence_root=output/'failure_evidence') as runtime:
        flow=runtime.build_arena_flow(ArenaDifficulty(args.difficulty),authorized_badge_ceiling=args.authorized_badges)
        # This HIL approval covers Arena badges, not Socket Gold/enhance/sales.
        # Productive caller policies remain supported; stop at a natural blocker.
        flow.socket_relief=None
        flow.cancel_requested=lambda:stop.exists() or runtime.cancel_requested()
        flow.evidence_sink=save
        if args.finish_return_from:
            previous=args.finish_return_from.resolve(); previous.relative_to(ROOT/'artifacts')
            payload=finish_recorded_result_return(runtime,flow,previous,save)
            payload['evidence']=evidence
            (output/'result.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
            print(json.dumps(payload)); return 0
        if args.recover_prestart_from:
            previous=args.recover_prestart_from.resolve(); previous.relative_to(ROOT/'artifacts')
            recover_prestart(runtime,flow.reader,previous,save)
        handoff=None
        if args.observe_started_from:
            previous=args.observe_started_from.resolve(); previous.relative_to(ROOT/'artifacts')
            receipt,badges,handoff=existing_batch_receipt(previous,ArenaDifficulty(args.difficulty),
                args.character,args.authorized_badges,runtime.observer.source,save)
            result=flow.observe_started_batch(receipt,badges)
        else:
            result=flow.run()
        payload=dict(status=result.status.value,error=result.error,phase=result.phase,
            character=args.character,character_authority='USER_GT_HIL_chat',authorized_badges=args.authorized_badges,
            physical_operation_may_be_active=result.physical_operation_may_be_active,
            batch_result=asdict(result.batch_result) if result.batch_result else None,
            execution=asdict(result.execution) if result.execution else None,
            metrics=result.metrics,evidence=evidence)
        if handoff: payload['observation_handoff']=handoff
        # A passive native final capture; no cleanup tap on error/cancellation.
        try:
            final=runtime.observer.source.refresh_native(); save('physical_final',final)
            if result.succeeded:
                before=flow.reader.ocr_calls; started=time.perf_counter()
                facts=flow.reader.economy(final)
                payload['final_resources']=asdict(facts) if facts else None
                payload['final_resource_read_seconds']=time.perf_counter()-started
                payload['final_resource_ocr_calls']=flow.reader.ocr_calls-before
        except Exception as failure:
            payload['final_capture_error']=str(failure)
        (output/'result.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
        print(json.dumps(payload))
    return 0 if result.succeeded else 1


if __name__=='__main__':
    raise SystemExit(main())
