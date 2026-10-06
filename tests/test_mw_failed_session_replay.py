"""Actual 86adecd4 board/context + logged latency; no economic input or hardware."""
from pathlib import Path
import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.monster_wave_board_perception import MonsterWaveBoardPerception
from bot.monster_wave_board_reader import MonsterWaveBoardReader, MonsterWaveBoardSample
from bot.monster_wave_standalone import MonsterWaveBoardAcquisitionRuntime
from bot.observations import Observation, ObservationSource
from bot.ocr import RapidOcrEngine
from bot.perception import build_default_perception, select_detectors, MONSTER_WAVE_BOARD_ACQUISITION_SCOPE
from bot.perception.local_cv import LocalCvDetector
from bot.resource_route_planner import plan_resource_route
from bot.runtime_observer import RuntimeObserver
from bot.flow_contracts import FlowStatus
from test_monster_wave_productive import _Harness, _pending

ROOT = Path(__file__).parent / 'fixtures' / 'mw_session_86adecd4'


def evidence():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    images = [cv2.imread(str(ROOT / f'frame_{s}.png')) for s in (6072, 6087)]
    raw = json.loads((ROOT / 'snapshot_6072.json').read_text())
    observations = {o['name']: Observation(o['name'], o['confidence'], ObservationSource.LOCAL_CV)
                    for o in raw['observations']}
    return manifest, images, observations


def timed_replay(monkeypatch, *, memoize):
    manifest, images, observations = evidence()
    clock = [manifest['last_pair'][0]['timestamp']]
    sequence = [6071]
    scoped = select_detectors(build_default_perception(), MONSTER_WAVE_BOARD_ACQUISITION_SCOPE)
    # Aggregate cost from the failed run distributed across the same detectors.
    # This models scheduling only; saved raw observations own scene semantics.
    cost = manifest['analysis_seconds'][0] / len(scoped.detectors)
    for detector in scoped.detectors:
        name = getattr(getattr(detector, 'spec', None), 'name', None)
        def detect(image, name=name):
            clock[0] += cost
            return (observations[name],) if name in observations else ()
        monkeypatch.setattr(detector, 'detect', detect)
    perception = MonsterWaveBoardPerception(scoped) if memoize else scoped
    def get_frame():
        sequence[0] += 1
        return FrameSnapshot(images[(sequence[0] - 6072) % 2], clock[0], sequence[0])
    observer = RuntimeObserver(SimpleNamespace(get_frame=get_frame), perception, build_default_resolver(),
        clock=lambda: clock[0], sleeper=lambda t: clock.__setitem__(0, clock[0] + t))
    # Read the real pixels with the production OCR reader once outside the
    # simulated age window; replay the logged first OCR cost inside it.
    reference = MonsterWaveBoardReader(RapidOcrEngine()).read_sample(observer.observe())
    assert reference is not None
    assert [(r.balance, r.displayed_limit) for r in reference.rows[1:]] == [(738, 999), (67, 999), (238, 499), (80, 499)]
    if memoize:
        perception._last.clear()
    reads = [0]
    def read_sample(context):
        if not reads[0]:
            clock[0] += manifest['first_pair']['reader_seconds']
        reads[0] += 1
        return MonsterWaveBoardSample(reference.rows, context.sequence, context.timestamp, reference.evidence)
    runtime = MonsterWaveBoardAcquisitionRuntime(observer, SimpleNamespace(read_sample=read_sample), clock=lambda: clock[0])
    return runtime, clock, manifest


@pytest.mark.parametrize('memoize', [False, True], ids=['old_FAILED', 'fixed_continues'])
def test_actual_open_board_context_continues_without_navigation_or_reactivation(monkeypatch, memoize):
    boards, clock, manifest = timed_replay(monkeypatch, memoize=memoize)
    harness = _Harness(first=_pending(manifest['pending_sequence']))
    flow = harness.flow()
    flow.boards, flow.planner, flow.clock = boards, plan_resource_route, lambda: clock[0]
    acquire = boards.acquire
    def remember(**kwargs):
        result = acquire(**kwargs)
        harness.board = result
        return result
    boards.acquire = remember
    result = flow._consume_pending(harness.first)
    if not memoize:
        assert result.status is FlowStatus.FAILED
        assert result.error == manifest['error']
        assert harness.calls == []
    else:
        assert result.status is FlowStatus.COMPLETED, result.error
        assert harness.board.context.state.base_context == 'screen.monster_wave'
        assert harness.board.context.state.overlays == ('popup.monster_wave_inventory_board',)
        assert [c[0] for c in harness.calls] == ['yes', 'finish']
        assert clock[0] - harness.board.context.timestamp <= 2


def test_memoization_uses_exact_gray_roi_and_recomputes_changed_pixels(monkeypatch):
    scoped = select_detectors(build_default_perception(), MONSTER_WAVE_BOARD_ACQUISITION_SCOPE)
    detector = next(d for d in scoped.detectors if type(d) is LocalCvDetector)
    calls = []
    def detect(image):
        calls.append(image.copy())
        return ()
    monkeypatch.setattr(detector, 'detect', detect)
    perception = MonsterWaveBoardPerception(SimpleNamespace(detectors=(detector,)))
    # Different sequence/timestamp never reuses a snapshot or resolved context.
    image = np.zeros((1224, 2712, 3), dtype=np.uint8)
    for s in (1, 2):
        batch = perception.analyze(FrameSnapshot(image, float(s), s))
        assert (batch.sequence, batch.timestamp) == (s, float(s))
    assert len(calls) == 1
    from bot.geometry import relative_region_to_pixels
    x1, y1, *_ = relative_region_to_pixels(detector.spec.region, image.shape[1], image.shape[0])
    image[y1, x1] = 255
    perception.analyze(FrameSnapshot(image, 3., 3))
    assert len(calls) == 2
