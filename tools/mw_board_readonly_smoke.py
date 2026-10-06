"""Acquire an already-open MW board with productive wiring, without device input."""
import json
from pathlib import Path
import cv2

from bot.productive_runtime import open_productive_runtime
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.monster_wave_productive import ProductiveMonsterWaveFlow


def main():
    root = Path('artifacts/reliefs-mw-audit')
    root.mkdir(parents=True, exist_ok=True)
    with open_productive_runtime(log_path=root / 'readonly-live.jsonl', console=None,
                                 character_state_path=root / 'readonly-state.db') as runtime:
        flow = runtime.build_flow(DEFAULT_FLOW_REGISTRY.get('monster_wave'))
        assert isinstance(flow, ProductiveMonsterWaveFlow), 'productive wiring unavailable'
        initial = flow.boards.observer.observe()
        cv2.imwrite(str(root / 'mw_current_native.png'), initial.frame.image)
        result = flow.boards.acquire(after_sequence=initial.sequence)
        payload = {'sequence': result.context.sequence,
                   'base': result.context.state.base_context,
                   'overlays': result.context.state.overlays,
                   'rows': [dict(item_id=r.item_id, balance=r.balance, limit=r.displayed_limit,
                                 hard_pressure=r.hard_pressure) for r in result.snapshot.resource_rows],
                   'frame_age': flow.boards.clock() - result.context.timestamp,
                   'inputs': 0}
        (root / 'readonly-live-result.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload))


if __name__ == '__main__':
    main()
