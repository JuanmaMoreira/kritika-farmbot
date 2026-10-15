"""A1: passive post-board acquisition, using the real RuntimeObserver loop."""
from types import SimpleNamespace as S
import json
from pathlib import Path

import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.action_executor import FrameGeometry
from bot.flow_contracts import FlowStatus
from bot.monster_wave_board_snapshot import build_monster_wave_board_snapshot
from bot.monster_wave_resource_route import MonsterWaveSnapshotRuntime
from bot.monster_wave_semantics import MW_NEEDS_TICKETS, SCREEN_MONSTER_WAVE
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.operation_control import OperationControl, control_scope
from bot.runtime_observer import RuntimeEvidenceRequirements, RuntimeObserver, RuntimeSnapshot, RuntimeFacts
from bot.state import ResolutionStatus, ResolvedState


class Clock:
    now = 10.
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


def harness(steps, *, timeout=6., cancel=lambda: False):
    """Each step is capture delay, analysis cost and optional frame overrides."""
    clock = Clock()
    image = np.zeros((20, 40, 3), np.uint8)
    pending = iter(enumerate(steps, 2))
    costs, states, coverages, analyses = {}, {}, {}, []
    latest = FrameSnapshot(image, 9., 1, source_id='mw-source')
    def capture():
        nonlocal latest
        step = next(pending, None)
        if step is not None:
            sequence, (delay, cost, options) = step
            clock.sleep(delay)
            latest = FrameSnapshot(image, options.get('timestamp', clock()), sequence,
                                   source_id=options.get('source', 'mw-source'))
            costs[sequence] = cost
            states[sequence] = options.get('status', ResolutionStatus.RESOLVED)
            coverages[sequence] = options.get('coverage', frozenset({'mw'}))
        return latest
    def analyze(frame):
        analyses.append(frame.sequence)
        clock.sleep(costs.get(frame.sequence, 0.))
        return ObservationBatch(frame.sequence, frame.timestamp,
            (Observation(MW_NEEDS_TICKETS, 1., ObservationSource.LOCAL_CV),),
            coverage=coverages.get(frame.sequence))
    def resolve(batch):
        status = states.get(batch.sequence, ResolutionStatus.UNKNOWN)
        return ResolvedState(status, batch.sequence, batch.timestamp,
            base_context=SCREEN_MONSTER_WAVE if status is ResolutionStatus.RESOLVED else None,
            base_candidates=(SCREEN_MONSTER_WAVE, 'screen.lobby') if status is ResolutionStatus.AMBIGUOUS else ())
    observer = RuntimeObserver(S(get_frame=capture), S(analyze=analyze), S(resolve=resolve),
        clock=clock, metrics_clock=clock, sleeper=clock.sleep, poll_interval=.01)
    runtime = MonsterWaveSnapshotRuntime(observer, clock=clock, timeout=timeout,
                                         cancel_requested=cancel)
    return runtime, clock, analyses


def step(delay=.02, cost=.01, **options): return delay, cost, options


def legacy_acquire(runtime):
    # Baseline 8ab7cf6: same wait without an age gate, then builder validation.
    context = runtime.observer.wait_until(
        lambda s: s.state.status is ResolutionStatus.RESOLVED,
        after_sequence=1, timeout=runtime.timeout, stable_for=.25)
    return build_monster_wave_board_snapshot(context, after_sequence=1, now=runtime.clock())


def test_analysis_expiry_reacquires_passively_instead_of_failing_after_successful_wait():
    steps = [step(), step(.3, 2.232), step(), step(.3)]
    old, old_clock, _ = harness(steps)
    assert legacy_acquire(old) is None
    new, clock, analyses = harness(steps)
    result = new.acquire(after_sequence=1)
    assert result.status is FlowStatus.COMPLETED
    assert result.fresh.context.sequence == 5
    assert clock() - result.fresh.context.timestamp < 2.
    assert analyses == [2, 3, 4, 5]
    assert clock() - old_clock() == pytest.approx(.36)


def test_normal_acquisition_has_identical_simulated_latency_and_analysis_count():
    old, old_clock, old_analyses = harness([step(), step(.3)])
    assert legacy_acquire(old) is not None
    new, clock, analyses = harness([step(), step(.3)])
    assert new.acquire(after_sequence=1).status is FlowStatus.COMPLETED
    assert clock() == old_clock()
    assert analyses == old_analyses == [2, 3]


@pytest.mark.parametrize('options', [
    {'timestamp': 9.}, {'source': 'another-lifetime'}, {'coverage': None},
    {'status': ResolutionStatus.UNKNOWN}, {'status': ResolutionStatus.AMBIGUOUS},
])
def test_invalid_evidence_never_becomes_an_anchor(options):
    runtime, clock, _ = harness([step(**options), step(.3, **options)], timeout=.6)
    result = runtime.acquire(after_sequence=1, evidence=RuntimeEvidenceRequirements(
        source_id='mw-source', captured_after=10., required_coverage={'mw'}))
    assert result.status is FlowStatus.FAILED and result.fresh is None
    assert result.error.startswith('mw_snapshot_acquisition_timeout:')
    assert clock() <= 10.61


def test_static_stream_is_bounded_and_not_reanalyzed_after_expiry():
    runtime, clock, analyses = harness([step(cost=2.232)], timeout=3.)
    result = runtime.acquire(after_sequence=1)
    assert result.status is FlowStatus.FAILED and result.fresh is None
    assert result.error.startswith('mw_snapshot_acquisition_timeout:')
    assert analyses == [2]
    assert clock() == pytest.approx(13.)


def test_cancel_during_slow_analysis_returns_cancelled_without_more_work():
    holder = {}
    runtime, clock, analyses = harness([step(cost=2.232), step()],
                                     cancel=lambda: holder['clock']() > 12.)
    holder['clock'] = clock
    assert runtime.acquire(after_sequence=1).status is FlowStatus.CANCELLED
    assert analyses == [2]


@pytest.mark.parametrize('parent', [False, True])
def test_deadline_cannot_be_renewed_by_a_late_matching_analysis(parent):
    runtime, clock, analyses = harness([step(), step(.3, .5)], timeout=.6)
    control = OperationControl(deadline=10.4 if parent else None, clock=clock)
    with control_scope(control):
        result = runtime.acquire(after_sequence=1)
    assert result.status is FlowStatus.FAILED and result.fresh is None
    assert analyses == [2, 3]  # Cooperative boundary, no third acquisition/input.


def test_caller_cannot_relax_the_two_second_age_limit():
    runtime, _, _ = harness([step(), step(.3, 2.232)], timeout=3.)
    result = runtime.acquire(after_sequence=1,
                             evidence=RuntimeEvidenceRequirements(max_age=20.))
    assert result.status is FlowStatus.FAILED


def test_retained_semantic_frame_is_actionable_but_expires_during_analysis():
    data = json.loads((Path(__file__).parent/'fixtures/mw_post_board/snapshot_25142.json').read_text())
    sequence, timestamp = data['sequence'], data['timestamp']
    # Replay recorded semantics, not synthetic pixels passed through perception.
    frame = FrameSnapshot(np.zeros((20, 40, 3), np.uint8), timestamp, sequence)
    batch = ObservationBatch(sequence, timestamp, tuple(Observation(
        item['name'], item['confidence'], ObservationSource.LOCAL_CV) for item in data['observations']))
    context = RuntimeSnapshot(frame, batch,
        ResolvedState(ResolutionStatus.RESOLVED, sequence, timestamp,
                      base_context=data['state']['base_context']), RuntimeFacts(), FrameGeometry(40, 20))
    assert build_monster_wave_board_snapshot(context, after_sequence=25120, now=timestamp+1.)
    assert build_monster_wave_board_snapshot(context, after_sequence=25120, now=timestamp+2.232) is None
