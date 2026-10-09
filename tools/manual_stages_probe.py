"""Focal authorized acquisition: one guarded action, fresh captures, runtime cleanup."""
import argparse
import json
import time
from pathlib import Path
import cv2
from bot.productive_runtime import open_productive_runtime
from bot.stages_wiring import build_stages_daily
from bot.flow_registry import _build_monster_wave
from bot.stages_actions import CloseAdAffordance, StageControl
from bot.perception.stages import surface
from bot.arena_reader import crop

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--enter-map', action='store_true')
    p.add_argument('--open-characters', action='store_true')
    p.add_argument('--return-lobby',action='store_true')
    p.add_argument('--chaos-config', action='store_true')
    p.add_argument('--rion-config', action='store_true')
    p.add_argument('--run-prepared-chaos', action='store_true')
    p.add_argument('--run-prepared-rion', action='store_true')
    p.add_argument('--ensure-auto-live', action='store_true')
    p.add_argument('--mw-pass', action='store_true')
    p.add_argument('--point', type=float, nargs=2, action='append')
    p.add_argument('--double', action='store_true')
    p.add_argument('--reference', type=Path)
    p.add_argument('--guard-roi', type=float, nargs=4)
    p.add_argument('--delay', type=float, default=1.)
    p.add_argument('--stamina-guard', action='store_true')
    a = p.parse_args()
    out = a.output.resolve(); out.relative_to(ROOT/'artifacts')
    out.mkdir(parents=True, exist_ok=False)
    if a.point and (not a.reference or not a.guard_roi): p.error('fresh visual guard required')
    with open_productive_runtime(log_path=out/'events.jsonl', console=None) as rt:
        rt.observer._snapshot_consumer=lambda s:cv2.imwrite(str(out/'latest.png'),s.frame.image)
        if a.stamina_guard:
            rt.ocr_engine.recognize(crop(rt.observer.source.get_frame().image, (.615,.036,.636,.080)))
        frame = rt.observer.source.refresh_native()
        cv2.imwrite(str(out/'before.png'), frame.image)
        if a.mw_pass:
            from bot.stages_wiring import ensure_lobby_entry
            result=_build_monster_wave(rt).run_resource_pass()
            print(json.dumps(dict(status=result.status.value,error=result.error,
                sapphires_consumed=getattr(result,'sapphires_consumed',None))),flush=True)
            if not result.succeeded:raise ValueError(result.error or 'MW pass failed')
            ensure_lobby_entry(rt)
        elif a.ensure_auto_live:
            from bot.stages_wiring import build_manual_stages_navigation
            from bot.manual_stages import ManualStagesOperation
            nav,balances,visuals=build_manual_stages_navigation(rt,_build_monster_wave(rt))
            op=ManualStagesOperation(nav,balances,visuals,
                evidence_sink=lambda name,f:cv2.imwrite(str(out/(name+'.png')),f.image))
            op.ensure_auto()
        elif a.run_prepared_chaos or a.run_prepared_rion:
            from bot.stages_wiring import build_manual_stages_navigation
            from bot.manual_stages import ManualStagesOperation,ManualStageTarget
            from bot.arena_farming_resources import ArenaFarmingResourceReader
            nav,balances,visuals=build_manual_stages_navigation(rt,_build_monster_wave(rt))
            op=ManualStagesOperation(nav,balances,visuals,
                evidence_sink=lambda name,f:cv2.imwrite(str(out/(name+'.png')),f.image))
            op.target=ManualStageTarget.CHAOS_06 if a.run_prepared_chaos else ManualStageTarget.ABYSSAL_RION_09
            s=op.prepare_config(nav.wait(lambda s:surface(s)=='config'))
            reader=ArenaFarmingResourceReader(rt.observer,rt.ocr_engine)
            readings=[]
            for _ in range(2):
                f=rt.observer.source.refresh_native()
                difficulty='hell' if a.run_prepared_chaos else 'penance'
                if visuals.config_target(f.image)!=op.target.value or visuals.toggle(f.image,difficulty) is not True:
                    raise ValueError('fresh manual config guard failed')
                readings.append(reader._pair(f.image,(.615,.036,.685,.082)))
            print(json.dumps(dict(fresh_stamina=readings)),flush=True)
            if None in readings or min(readings)<60 or readings[0]!=readings[1]:
                raise ValueError('fresh Stamina consensus >=60 required')
            s=nav.wait(lambda s:surface(s)=='config')
            s=nav.change(StageControl.START,s,{'start'})
            cv2.imwrite(str(out/'striker.png'),s.frame.image)
            s=nav.change(StageControl.STRIKER_START,s,{'battle','death'},timeout=12.)
            cv2.imwrite(str(out/'battle.png'),s.frame.image)
            original_glow=visuals.auto_glow
            samples=[]
            def acquired_glow(image):
                value=original_glow(image)
                samples.append(dict(t=time.monotonic(),value=value))
                cv2.imwrite(str(out/f'auto_sample_{len(samples):03d}.png'),crop(image,(.84,.01,.92,.105)))
                return value
            visuals.auto_glow=acquired_glow
            try:op.ensure_auto(s.sequence)
            finally:(out/'auto_samples.json').write_text(json.dumps(samples,indent=2))
            op._pause(30.)
        elif a.rion_config:
            from bot.stages_wiring import build_manual_stages_navigation
            from bot.manual_stages import ManualStagesOperation,ManualStageTarget
            from bot.stages_runtime import lobby
            nav,balances,visuals=build_manual_stages_navigation(rt,_build_monster_wave(rt))
            op=ManualStagesOperation(nav,balances,visuals)
            op.target=ManualStageTarget.ABYSSAL_RION_09
            s=nav.current()
            op.enter_target() if lobby(s) else op.open_target(s)
        elif a.chaos_config:
            from bot.stages_wiring import build_manual_stages_navigation
            from bot.stages_runtime import lobby,exposed
            from bot.perception.stages import has
            from bot.manual_stages_reader import flag
            nav,_,_=build_manual_stages_navigation(rt,_build_monster_wave(rt))
            s=nav.current()
            if lobby(s):s=nav.enter_episode('chaos')
            else:
                if surface(s)=='elite':s=nav.change(StageControl.NORMAL,s,{'normal'})
                if not has(s,'chaos'):
                    s=nav.change(StageControl.WORLD_MAP,s,{'world_map'})
                    s=nav.change(StageControl.CHAOS,s,{'world_map','normal'})
                    if surface(s)=='world_map':s=nav.change(StageControl.WORLD_MAP,s,{'normal'})
                    s=nav.wait(lambda s:exposed(s) and has(s,'chaos'))
                s=nav.claim_rewards(s)
            if flag(s,'x4') is None:raise ValueError('x4 unknown')
            if flag(s,'x4') is False:
                nav.tap(StageControl.X4,s)
                # Double tap is one known quantity gesture; no intermediate
                # unknown snapshot authorizes an additional input.
                rt.actions.execute(__import__('bot.stages_actions',fromlist=['StageAction']).StageAction(StageControl.X4),s.geometry,
                    events=rt.events,source_sequence=s.sequence)
                s=nav.wait(lambda s:exposed(s) and flag(s,'x4') is True)
            nav.change(StageControl.STAGE6,s,{'config'})
        elif a.return_lobby:
            from bot.stages_wiring import build_manual_stages_navigation
            nav,_,_=build_manual_stages_navigation(rt,_build_monster_wave(rt))
            nav.exit_to_lobby(nav.current())
        elif a.open_characters:
            from bot.stages_wiring import build_manual_stages_navigation
            from bot.stages_runtime import lobby
            from bot.catalog import MENU_QUICK, SCREEN_CHARACTER_SELECT
            from bot.semantic_actions import OpenQuickMenu, OpenCharacterSelect
            nav,_,_=build_manual_stages_navigation(rt,_build_monster_wave(rt))
            s=nav.current()
            if surface(s)=='config':s=nav.change(StageControl.CLOSE_CONFIG,s,{'normal'})
            if surface(s)=='normal':
                nav.tap(StageControl.BACK,s);s=nav.wait(lobby)
            s=nav.wait(lobby);nav.act(OpenQuickMenu(),s)
            s=nav.wait(lambda s:set(s.state.overlays)=={MENU_QUICK})
            nav.act(OpenCharacterSelect(),s)
            nav.wait(lambda s:s.state.base_context==SCREEN_CHARACTER_SELECT and not s.state.overlays)
        elif a.enter_map:
            nav = build_stages_daily(rt, _build_monster_wave(rt)).nav
            s = nav.enter_episode()
            nav.change(StageControl.WORLD_MAP, s, {'world_map'})
        elif a.point:
            for index, point in enumerate(a.point):
                frame = rt.observer.source.refresh_native()
                reference = cv2.imread(str(a.reference))
                old = crop(reference, tuple(a.guard_roi))
                current = crop(frame.image, tuple(a.guard_roi))
                old = cv2.resize(old, (current.shape[1], current.shape[0]))
                score = float(cv2.matchTemplate(current, old, cv2.TM_CCOEFF_NORMED)[0,0])
                if score < .98 or current.mean() < old.mean()*.80:
                    raise ValueError(f'acquisition source guard failed: {score}')
                if a.stamina_guard:
                    # Select Striker's X covers capacity; acquired exposed numerator
                    # is 61. This focal acquisition gate accepts that exact reading
                    # only, rather than parsing a truncated capacity as a balance.
                    region=crop(frame.image, (.615,.036,.636,.080))
                    readings=[rt.ocr_engine.recognize(cv2.resize(v,None,fx=3,fy=3))
                        for v in (region,cv2.cvtColor(region,cv2.COLOR_BGR2GRAY))]
                    available=61 if all(r.text.strip()=='61' and r.confidence>=.99 for r in readings) else None
                    print(json.dumps(dict(fresh_stamina=available, sequence=frame.sequence)), flush=True)
                    if available is None or available < 60:
                        raise ValueError('fresh Stamina >=60 not verified; no Start')
                from bot.action_executor import FrameGeometry
                geometry = FrameGeometry.from_frame(frame.image)
                for _ in range(2 if a.double else 1):
                    rt.actions.execute(CloseAdAffordance(tuple(point)), geometry,
                        events=rt.events, source_sequence=frame.sequence)
                    time.sleep(.10)
                time.sleep(.5)
                cv2.imwrite(str(out/f'effect_{index}.png'), rt.observer.source.refresh_native().image)
        time.sleep(min(35., max(0., a.delay)))
        final = rt.observer.source.refresh_native()
        cv2.imwrite(str(out/'after.png'), final.image)
        s = rt.observer.observe()
        print(json.dumps(dict(shape=final.image.shape, sequence=final.sequence,
            surface=surface(s), base=s.state.base_context, overlays=s.state.overlays)))

if __name__ == '__main__': main()
