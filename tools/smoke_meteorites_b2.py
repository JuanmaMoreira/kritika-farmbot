"""Authorized focal B2 smoke through the real Routine/Session lifecycle, no Rotation."""
import argparse
from dataclasses import asdict, fields, is_dataclass
from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from bot.productive_runtime import open_productive_runtime, CancellationToken
from bot.routines import RoutineSpec, RoutineStep
from bot.session_report import build_session_report, render_session_report
from tools.runtime_cli import cancellation_signals

ROOT = Path(__file__).resolve().parents[1]


def json_default(value):
    # FlowEvent.fields is read-only MappingProxyType; asdict deep-copy rejects it.
    if is_dataclass(value):return {f.name:getattr(value,f.name) for f in fields(value) if f.name != "final_snapshot"}
    if isinstance(value,Mapping):return dict(value)
    if isinstance(value,datetime):return value.isoformat()
    raise TypeError('Unsupported report value: '+type(value).__name__)


def run(args):
    output=args.output; output.mkdir(parents=True,exist_ok=True)
    report=dict(scope='B2 actual Routine/Session, Send Stamina, no Rotation', steps=[], final_verified=False)
    token=CancellationToken(); scopes=[]; io_seconds=0.
    def persist():
        (output/'report.json').write_text(json.dumps(report,indent=2,default=json_default)+'\n',encoding='utf8')
    try:
        with cancellation_signals(token), open_productive_runtime(log_path=output/'runtime.jsonl',
                evidence_root=output/'failure',dotenv_path=args.dotenv_path,cancel_token=token,console=None) as runtime:
            original=runtime.build_meteorites_character_scope
            def scope_with_evidence():
                scope=original(); scopes.append(scope); rt=scope.procedure.rt
                rt.reader.engine.recognize(np.zeros((32,120,3),np.uint8))
                def record(name,result,progress):
                    nonlocal io_seconds
                    started=time.monotonic(); step=dict(name=name,frames=[])
                    if result is None:
                        if name.startswith('inspect_'):rt.evidence['final']=rt._latest
                        else:rt.evidence={name:rt._latest}
                    for role,frame in rt.evidence.items():
                        if frame is None or role=='freshness_reject':continue
                        path=output/(name+'_'+role+'.png')
                        if not cv2.imwrite(str(path),frame.image):raise RuntimeError('evidence_write_failed')
                        step['frames'].append(dict(role=role,path=path.relative_to(ROOT).as_posix(),
                            sequence=frame.sequence,timestamp_monotonic=frame.timestamp,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    if result is not None:step['result']=asdict(result)
                    step['equipped']=list(progress.equipped);step['released']=list(progress.released)
                    report['steps'].append(step);persist();io_seconds+=time.monotonic()-started
                scope.procedure.record=record
                return scope
            runtime.build_meteorites_character_scope=scope_with_evidence
            routine=RoutineSpec('meteorites-b2-smoke','Meteorites B2 smoke',
                (RoutineStep('send_stamina'),),change_meteorites=True)
            started=time.monotonic();result=runtime.run_routine(routine)
            report['routine_seconds']=time.monotonic()-started
            report['result']=result
            if result.session_result is not None:
                projection=build_session_report(result.session_result)
                (output/'session_report.txt').write_text(render_session_report(projection)+'\n',encoding='utf8')
            report['meteorites']=[scope.report() for scope in scopes]
            report['final_verified']=(result.status.value=='completed' and len(scopes)==1
                and scopes[0].state.value=='RELEASED')
            report['final_bag']=asdict(scopes[0].procedure.progress.known_bag) if scopes and scopes[0].procedure.progress.known_bag else None
    except Exception as error:
        report['error']=str(error)
        report['meteorites']=[scope.report() for scope in scopes]
    finally:
        report['evidence_io_seconds']=io_seconds;persist()
    print(json.dumps(dict(final_verified=report['final_verified'],error=report.get('error'),
        meteorites=[{k:v for k,v in s.items() if k!='progress'} for s in report.get('meteorites',[])],
        routine_seconds=report.get('routine_seconds'),evidence_io_seconds=io_seconds),default=str))
    return 0 if report['final_verified'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotenv-path',type=Path,default=ROOT/'.env')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/meteorites_b2'/time.strftime('%Y%m%d_%H%M%S'))
    raise SystemExit(run(parser.parse_args()))
