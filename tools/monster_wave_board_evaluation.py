"""Incremental board reader evaluation on the acquired MW board slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.monster_wave_board_reader import MonsterWaveBoardReader
from bot.monster_wave_semantics import MW_BOARD, POPUP_MW_BOARD, SCREEN_MONSTER_WAVE
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.ocr import RapidOcrEngine
from bot.perception import build_default_perception
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolvedState, ResolutionStatus


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets/monster_wave_board_manifest.json"


def evaluate() -> tuple[int, int]:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]
    perception = build_default_perception(ROOT)
    resolver = build_default_resolver()
    reader = MonsterWaveBoardReader(RapidOcrEngine())
    wrong = 0
    for sequence, entry in enumerate(entries, 1):
        path = ROOT / entry["path"]
        data = path.read_bytes()
        image = cv2.imread(str(path))
        errors = []
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            errors.append("sha256")
        if image is None:
            errors.append("unreadable PNG")
        else:
            frame = FrameSnapshot(image, float(sequence), sequence)
            if entry.get("context_source") == "human_confirmed_board":
                observations = ObservationBatch(sequence, float(sequence), (
                    Observation(MW_BOARD, 1.0, ObservationSource.LOCAL_CV),))
                state = ResolvedState(
                    ResolutionStatus.RESOLVED, sequence, float(sequence),
                    base_context=SCREEN_MONSTER_WAVE, overlays=(POPUP_MW_BOARD,))
            else:
                observations = perception.analyze(frame)
                state = resolver.resolve(observations)
            snapshot = RuntimeSnapshot(frame, observations, state, RuntimeFacts(),
                                       FrameGeometry.from_frame(image))
            sample = reader.read_sample(snapshot)
            actual = (None if sample is None else
                      [[row.item_id, row.balance, row.displayed_limit, row.hard_pressure]
                       for row in sample.rows])
            red_rows = set(entry.get("red_rows", ()))
            expected = (None if entry["expected"] is None else
                        [[item_id, None, None, True] if item_id in red_rows else
                         [item_id, balance, limit, False]
                         for item_id, balance, limit in entry["expected"]])
            if actual != expected:
                errors.append(f"expected={expected!r} actual={actual!r}")
            board = (state.status is ResolutionStatus.RESOLVED
                     and state.base_context == SCREEN_MONSTER_WAVE
                     and state.overlays == (POPUP_MW_BOARD,))
            if board != (entry["context"] == "board_popup"):
                errors.append(f"board context={board} expected={entry['context']}")
        if errors:
            wrong += 1
            print(f"WRONG {entry['path']}: {'; '.join(errors)}")
        else:
            print(f"PASS {entry['path']}")
    print(f"monster wave board evaluator: {len(entries)-wrong}/{len(entries)} pass")
    return len(entries), wrong


if __name__ == "__main__":
    raise SystemExit(int(evaluate()[1] > 0))
