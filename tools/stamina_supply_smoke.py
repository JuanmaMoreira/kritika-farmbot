"""Focal payment acquisition / parametrized purchase, always bounded and guarded."""
import argparse
import json
from pathlib import Path
import cv2
from bot.productive_runtime import open_productive_runtime
from bot.flow_registry import _build_monster_wave
from bot.stages_wiring import build_manual_stages
from bot.stamina_purchase import PAYMENT_ROI,QUANTITY_ROI
from bot.stages_actions import StageAction,StageControl as C
from bot.semantic_actions import OpenTrading,CloseTrading,CancelTradingTrade
from bot.stages_runtime import lobby

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--required',type=int)
    p.add_argument('--claim-first',action='store_true')
    a=p.parse_args()
    if a.required is not None and a.required<0:p.error('nonnegative demand required')
    out=a.output.resolve();out.relative_to(ROOT/'artifacts');out.mkdir(parents=True,exist_ok=False)
    with open_productive_runtime(log_path=out/'events.jsonl',evidence_root=out/'failures',console=None) as rt:
        op=build_manual_stages(rt,_build_monster_wave(rt));purchase=op.stamina_purchase;n=op.nav
        rt.observer._snapshot_consumer=lambda s:cv2.imwrite(str(out/'latest.png'),s.frame.image)
        cv2.imwrite(str(out/'before.png'),rt.observer.source.refresh_native().image)
        reads=[];original=op.balances.pair
        def pair(s,roi):
            cv2.imwrite(str(out/f'pair_{len(reads):02d}.png'),s.frame.image)
            value=original(s,roi)
            reads.append(dict(roi=roi,value=value,sequence=s.sequence));return value
        op.balances.pair=pair
        try:
            if a.required is not None:
                result=(op.prepare_stamina(a.required) if a.claim_first else
                    purchase.supply(op.balances.read(),a.required))
                payload=dict(required=result.required,purchased=result.purchased,
                    stamina_after=result.balances.stamina,covered=result.covered,outcome=result.outcome)
            else:
                s=n.wait(lambda s:lobby(s) or purchase.panel(s) or purchase.ready(s))
                if lobby(s):
                    n.act(OpenTrading(),s)
                    s=n.wait(lambda s:purchase.detector.present(s.frame.image,'currency') or s.state.base_context=='screen.trading')
                    n.act(StageAction(C.CURRENCY),s);s=n.wait(purchase.ready)
                if not purchase.panel(s):
                    n.act(StageAction(C.STAMINA_ROW),s);s=n.wait(purchase.panel)
                cv2.imwrite(str(out/'panel.png'),s.frame.image)
                payment=pair(s,PAYMENT_ROI);quantity=pair(s,QUANTITY_ROI)
                payload=dict(payment=payment,quantity=quantity,confirmations=0)
                s=n.wait(purchase.panel);n.act(CancelTradingTrade(),s)
                s=n.wait(lambda s:purchase.ready(s) and not purchase.panel(s))
                n.act(CloseTrading(),s);n.wait(lobby)
            payload['reads']=reads
            (out/'result.json').write_text(json.dumps(payload,indent=2),encoding='utf8')
            print(json.dumps(payload),flush=True)
        finally:
            cv2.imwrite(str(out/'final.png'),rt.observer.source.refresh_native().image)

if __name__=='__main__':main()
