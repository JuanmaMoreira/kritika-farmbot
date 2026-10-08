"""Authorized focal chain only: 3 individual Equip, 3 slot Unequip, Set 1.

Run after chat/steer preparation. Stop at first divergence, preserving bounded
evidence and asking for manual restoration. No full cleanup or anchor loop.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

import cv2
import numpy as np

from bot.productive_runtime import open_productive_runtime, CancellationToken
from bot.meteorites_semantics import SlotState
from tools.runtime_cli import cancellation_signals

ROOT=Path(__file__).resolve().parents[1]


def run(args):
    output=args.output;output.mkdir(parents=True,exist_ok=True)
    report=dict(scope='Meteorites Phase A focal smoke; first divergence stops chain',
                steps=[],final_verified=False,manual_restoration_required=False)
    token=CancellationToken()
    def save(rt,name,result=None):
        frames=[]
        for role,frame in rt.evidence.items():
            if frame is None:continue
            path=output/(name+'_'+role+'.png');cv2.imwrite(str(path),frame.image)
            frames.append(dict(role=role,path=str(path.relative_to(ROOT)),sequence=frame.sequence,
                               timestamp_monotonic=frame.timestamp,shape=list(frame.image.shape)))
        step=dict(name=name,frames=frames)
        if result is not None:step['result']=asdict(result)
        report['steps'].append(step)
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    try:
        with cancellation_signals(token),open_productive_runtime(
                log_path=output/'runtime.jsonl',cancel_token=token,console=None) as productive:
            rt=productive.build_meteorites_runtime()
            # Lazy OCR startup is excluded from timed gameplay operations.
            rt.reader.engine.recognize(np.zeros((32,120,3),np.uint8))
            entry=rt.enter(productive.observer,productive.build_verified_transition(),via_quick_menu=args.quick_menu)
            if entry is None:raise RuntimeError('entry_unverified')
            rt.evidence={'entry':rt._latest};save(rt,'entry')
            set2=rt.select_set(2)
            if set2 is None or set2.slots!=(SlotState.EMPTY,)*11:
                raise RuntimeError('prepared_Set_2_empty_unverified')
            rt.evidence={'set2':rt._latest};save(rt,'set2')
            report['manual_restoration_required']=True
            # Three deliberately individual calls. Phase B anchor algorithm is
            # absent; indices are explicit smoke parameters from acquisition.
            flare=rt.equip(args.flare_index,expected=(True,'Ethereal+',30))
            save(rt,'equip_flare',flare)
            if not flare.succeeded:raise RuntimeError('equip_flare_'+flare.reason)
            normal1=rt.equip(args.normal_index,expected=(False,'Ethereal+',20))
            save(rt,'equip_normal1',normal1)
            if not normal1.succeeded:raise RuntimeError('equip_normal1_'+normal1.reason)
            normal2=rt.equip(args.normal_index,expected=(False,'Ethereal+',21))
            save(rt,'equip_normal2',normal2)
            if not normal2.succeeded:raise RuntimeError('equip_normal2_'+normal2.reason)
            # Physical gap: selecting the equipped slot must yield its fresh
            # overlay before the first lateral Unequip is authorized.
            flare_off=rt.unequip_slot(0,expected=(True,'Ethereal+',30))
            save(rt,'unequip_flare_slot',flare_off)
            if not flare_off.succeeded:raise RuntimeError('slot_route_flare_'+flare_off.reason)
            normal2_off=rt.unequip_slot(2,expected=(False,'Ethereal+',21))
            save(rt,'unequip_normal2_slot',normal2_off)
            if not normal2_off.succeeded:raise RuntimeError('slot_route_normal2_'+normal2_off.reason)
            normal1_off=rt.unequip_slot(1,expected=(False,'Ethereal+',20))
            save(rt,'unequip_normal1_slot',normal1_off)
            if not normal1_off.succeeded:raise RuntimeError('slot_route_normal1_'+normal1_off.reason)
            empty=rt.ready()
            if empty is None or empty.slots!=(SlotState.EMPTY,)*11:raise RuntimeError('Set_2_final_empty_unverified')
            final=rt.select_set(1)
            if final is None or final.slots!=(SlotState.OCCUPIED,)*11 or final.page!=1:
                raise RuntimeError('Set_1_final_unverified')
            rt.evidence={'final':rt._latest};save(rt,'restored_set1')
            report.update(final_verified=True,manual_restoration_required=False,final=asdict(final))
    except Exception as error:
        report['error']=str(error)
        if 'rt' in locals():
            rt.evidence['divergence']=rt._latest
            save(rt,'first_divergence')
    finally:
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'steps','final'}},ensure_ascii=False))
    return 0 if report['final_verified'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flare-index',type=int,required=True)
    parser.add_argument('--normal-index',type=int,required=True)
    parser.add_argument('--quick-menu',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/meteorites_phase_a'/time.strftime('%Y%m%d_%H%M%S'))
    raise SystemExit(run(parser.parse_args()))
