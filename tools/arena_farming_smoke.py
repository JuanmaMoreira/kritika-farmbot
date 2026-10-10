"""Focal Farming Cycle through the occurrence factory, with finite consumption.

Read-only preflight executes no game inputs. A productive smoke uses the ordinary
owners, a natural Arena batch ceiling, and a finite operation budget. STOP cancels
observation; it does not claim physical cancellation of an active Auto Repeat.
"""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from types import SimpleNamespace
import cv2

from bot.arena_config import ArenaConfig, ArenaMode
from bot.arena_farming_resources import ArenaFarmingResourceReader
from bot.flow_contracts import FlowResult, FlowStatus
from bot.flow_registry import FlowDefinition, FlowRegistry
from bot.productive_runtime import open_productive_runtime
from bot.routines import RoutineSpec, RoutineStep

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--read-only', action='store_true')
    parser.add_argument('--max-operations', type=int, default=2)
    parser.add_argument('--arena-ceiling', type=int, default=128)
    parser.add_argument('--min-badges', type=int, default=40)
    parser.add_argument('--min-sapphires', type=int, default=100)
    parser.add_argument('--max-stamina',type=int)
    parser.add_argument('--relief-routine',help='Reuse only this saved routine relief policy')
    args = parser.parse_args()
    if args.max_operations < 1 or args.arena_ceiling < 8:
        parser.error('positive operation budget and Badge ceiling >=8 required')
    output = args.output.resolve(); output.relative_to(ROOT/'artifacts')
    output.mkdir(parents=True, exist_ok=False)
    evidence = {}; cycles = []; following = []
    relief_policy=None
    if args.relief_routine:
        from bot.routines import RoutineStore
        from bot.flow_registry import DEFAULT_FLOW_REGISTRY
        routines,_=RoutineStore(ROOT/'routines.json',DEFAULT_FLOW_REGISTRY).load()
        selected=next(r for r in routines if r.name==args.relief_routine)
        relief_policy=selected.relief_policy
    def save(name, frame):
        path = output/f'{name}.png'
        if not cv2.imwrite(str(path), frame.image): raise OSError('capture write failed')
        evidence[name] = dict(path=str(path.relative_to(ROOT)), sequence=frame.sequence,
                              observed_at=frame.timestamp)
    with open_productive_runtime(log_path=output/'events.jsonl', evidence_root=output/'failures') as runtime:
        original_cancel = runtime.cancel_requested
        cancelled = lambda: (output/'STOP').exists() or original_cancel()
        if args.read_only:
            reader = ArenaFarmingResourceReader(runtime.observer, runtime.ocr_engine,
                                                cancel_requested=cancelled)
            reading = reader.read()
            save('physical_final', runtime.observer.source.refresh_native())
            payload = dict(read_only=True, resources=asdict(reading) if reading else None,
                           inputs=0, evidence=evidence)
            (output/'result.json').write_text(json.dumps(payload, indent=2)+'\n', encoding='utf8')
            print(json.dumps(payload), flush=True)
            return 0 if reading else 1
        runtime = replace(runtime, cancel_token=SimpleNamespace(is_requested=cancelled))
        original = runtime.registry.get('arena')
        def factory(dependencies):
            cycle = original.build(dependencies)
            cycle.max_operations = args.max_operations
            build = cycle.arena_factory
            def arena(difficulty):
                flow = build(difficulty)
                flow.authorized_badge_ceiling = args.arena_ceiling
                flow.evidence_sink = lambda name, frame: save(f'arena_{cycle.controller.batches}_{name}', frame)
                return flow
            cycle.arena_factory = arena
            cycle.manual_stages.evidence_sink=lambda name,frame:save('manual_'+name,frame)
            cycles.append(cycle)
            return cycle
        class LobbyProbe:
            name = 'lobby_probe'; scope = original.scope; contract = original.contract
            def run(self):
                from bot.battle_mode_zone import is_lobby
                snap = runtime.observer.observe(); save('following_lobby', snap.frame)
                valid = is_lobby(snap); following.append(valid)
                return FlowResult(FlowStatus.COMPLETED if valid else FlowStatus.FAILED,
                    error=None if valid else 'following Lobby unverified', final_snapshot=snap)
        runtime.registry = FlowRegistry(tuple(FlowDefinition(d.id, d.display_name, d.scope, d.contract, factory)
            if d.id == 'arena' else d for d in runtime.registry.definitions) + (
                FlowDefinition('lobby_probe', 'Read-only Lobby probe', original.scope, original.contract, lambda _: LobbyProbe()),))
        result = runtime.run_routine(RoutineSpec('arena_farming_smoke', 'Arena Farming focal smoke', (
            RoutineStep('arena', config={'arena': ArenaConfig(ArenaMode.FARMING_CYCLE,
                min_badges_for_arena=args.min_badges,min_sapphires_for_mw=args.min_sapphires,
                maximum_stamina_consumption=args.max_stamina).to_dict()}),
            RoutineStep('lobby_probe')),relief_policy=relief_policy))
        cycle_result = next((r for r in result.flow_results if hasattr(r, 'termination')), None)
        operations = []
        if cycle_result:
            for operation in cycle_result.operations:
                batch = getattr(operation, 'batch_result', None)
                operations.append(dict(status=operation.status.value, error=operation.error,
                    batch=asdict(batch) if batch else None, metrics=getattr(operation, 'metrics', {}),
                    physical_operation_may_be_active=getattr(operation, 'physical_operation_may_be_active', False),
                    sapphires_consumed=getattr(operation, 'sapphires_consumed', None)))
                if hasattr(operation,'outcome'):
                    operations[-1].update(outcome=operation.outcome.value,
                        target=operation.target.value if operation.target else None,
                        stamina_before=operation.stamina_before,stamina_after=operation.stamina_after,
                        stamina_consumed=operation.stamina_consumed,entry_id=operation.entry_id,
                        sapphires_before=operation.sapphires_before,sapphires_after=operation.sapphires_after)
        try: save('physical_final', runtime.observer.source.refresh_native())
        except Exception as error: evidence['final_capture_error'] = str(error)
        payload = dict(status=result.status.value, error=result.error, following_lobby=following,
            termination=cycle_result.termination.value if cycle_result else None,
            stamina_consumed=cycle_result.stamina_consumed if cycle_result else None,
            remaining_stamina_budget=cycle_result.remaining_stamina_budget if cycle_result else None,
            stamina_prepared=cycle_result.stamina_prepared if cycle_result else None,
            resources=asdict(cycle_result.resources) if cycle_result and cycle_result.resources else None,
            next_activity=cycles[0].activity(cycle_result.resources) if cycle_result and cycle_result.resources else None,
            operations=operations, evidence=evidence)
        (output/'result.json').write_text(json.dumps(payload, indent=2)+'\n', encoding='utf8')
        print(json.dumps(payload), flush=True)
        return 0 if result.status is FlowStatus.COMPLETED else 1


if __name__ == '__main__': raise SystemExit(main())
