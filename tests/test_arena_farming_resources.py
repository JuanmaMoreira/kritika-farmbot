"""Native curated number replays plus synthetic freshness/consensus guards."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest

from bot.arena_farming_resources import ArenaFarmingResourceReader, ArenaFarmingResources
from bot.arena_flow_reader import ArenaFlowReader
from bot.capture import FrameSnapshot
from bot.ocr import RapidOcrEngine
from bot.runtime_observer import RuntimeWaitCancelled
from bot.state import ResolutionStatus as R

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = json.loads((ROOT/'tests/fixtures/arena_farming/manifest.json').read_text())['entries']


@pytest.fixture(scope='module')
def engine(): return RapidOcrEngine()


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda e: e['id'])
def test_native_resource_pair_replay(entry, engine):
    path = ROOT/entry['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
    reader = ArenaFarmingResourceReader(None, engine)
    assert reader._pair(cv2.imread(str(path)), (0, 0, 1, 1)) == entry['expected']


def test_native_stock_border_recovers_with_same_strict_gates(engine):
    manifest = json.loads((ROOT/'tests/fixtures/arena_farming/buff_stock_manifest.json').read_text())
    path = ROOT/manifest['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['sha256']
    image = cv2.imread(str(path)); reader = ArenaFlowReader(engine)
    assert reader._integer(image, (0, 0, 1, 1), lambda: False)[0] is None
    assert reader._stock_integer(image, (0, 0, 1, 1), lambda: False) == 999
    # A negative reservation is still owned by _reserved_deficit, not stock.
    assert reader._stock_integer(image, (0, 0, 1, 1), lambda: True) is None


@pytest.mark.parametrize('reads', [[('40/106', .99), ('41/106', .99)],
    [('40/106', .94)], [('?', 1.)], [('0/0', 1.), ('0/0', 1.)],
    [('1,,2/106', 1.)], [('40', 1.)]])
def test_disagreement_low_confidence_missing_or_invalid_pair_is_unknown(reads):
    readings = iter(reads)
    def recognize(_):
        text, confidence = next(readings)
        return NS(text=text, confidence=confidence, metadata={'line_count': 1})
    reader = ArenaFarmingResourceReader(None, NS(recognize=recognize))
    assert reader._pair(np.zeros((30, 100, 3), dtype=np.uint8), (0, 0, 1, 1)) is None


def reader_world(state=R.RESOLVED, overlays=(), context='screen.lobby'):
    frame = FrameSnapshot(np.zeros((90, 160, 3), dtype=np.uint8), 100., 1)
    resolved = NS(status=state, overlays=overlays, base_context=context)
    observer = NS(perception=NS(analyze=lambda f: f), resolver=NS(resolve=lambda _: resolved),
        observe=lambda: NS(frame=frame, state=resolved, sequence=1, timestamp=100.))
    reader = ArenaFarmingResourceReader(observer, None, clock=lambda: 100.,
        visuals=NS(lobby=lambda _: True))
    reader._pair = lambda *args: 40
    return reader, frame


@pytest.mark.parametrize('state,overlays,context', [(R.UNKNOWN, (), 'screen.lobby'),
    (R.AMBIGUOUS, (), 'screen.lobby'), (R.RESOLVED, ('unknown.modal',), 'screen.lobby'),
    (R.RESOLVED, (), 'screen.arena')])
def test_native_state_gate_never_parses_unknown_occlusion_or_other_base(state, overlays, context):
    reader, frame = reader_world(state, overlays, context)
    assert reader.parse(frame) is None


def test_freshness_is_rechecked_after_ocr_and_cancel_is_safe():
    reader, frame = reader_world()
    def slow(*_): reader.clock = lambda: 105.; return 40
    reader._pair = slow
    assert reader.parse(frame) is None
    reader.cancel_requested = lambda: True
    with pytest.raises(RuntimeWaitCancelled): reader.parse(frame)


def test_two_distinct_native_frames_must_agree_and_no_stale_reuse():
    reader, _ = reader_world()
    sequence = iter([2, 3, 4]); values = iter([40, 41, 41])
    reader.observer.source = NS(refresh_native=lambda: NS(sequence=next(sequence), timestamp=101.))
    reader.parse = lambda f: ArenaFarmingResources(next(values), 100, f.sequence, f.timestamp, 'a'*64)
    # Equal timestamps are a source discontinuity, not confirmation.
    assert reader.read() is None
    sequence = iter([2, 3, 4]); values = iter([40, 41, 41])
    def refresh():
        seq = next(sequence); return NS(sequence=seq, timestamp=100. + seq)
    reader.observer.source.refresh_native = refresh
    assert reader.read().badges == 41
