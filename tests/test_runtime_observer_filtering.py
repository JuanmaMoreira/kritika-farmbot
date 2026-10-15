"""Deterministic filtering boundaries with real observation/transition wiring."""

from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.capture import ScrcpyFrameSource
from bot.observations import ObservationBatch
from bot.operation_control import OperationControl, OperationBudgetExpired, control_scope
from bot.resolver import ContextResolver
from bot.runtime_observer import (
    RuntimeObserver, RuntimeEvidenceRequirements, RuntimeWaitAborted,
    RuntimeWaitCancelled, RuntimeWaitTimeout,
)
from bot.verified_transition import VerifiedTransitionPolicy
from test_transition_foundations import Clock, snapshot, run


class Stream:
    def __init__(self, frames, work=lambda: None):
        self.frames = list(frames)
        self.calls = 0
        self.work = work

    def get_frame(self):
        self.work()
        frame = self.frames[min(self.calls, len(self.frames) - 1)]
        self.calls += 1
        # Production get_frame returns copies, not a stable Python identity.
        return replace(frame, image=frame.image.copy())


class Analysis:
    def __init__(self, coverage=lambda: {"guard"}, work=lambda: None):
        self.calls = []
        self.coverage = coverage
        self.work = work

    def analyze(self, frame):
        self.calls.append((frame.source_id, frame.sequence))
        self.work()
        return ObservationBatch(frame.sequence, frame.timestamp, coverage=self.coverage())


def make_observer(clock, frames, *, analysis=None, capture_work=lambda: None, consumer=None):
    return RuntimeObserver(
        Stream(frames, capture_work), analysis or Analysis(),
        ContextResolver(),
        clock=clock, metrics_clock=clock, sleeper=clock.sleep, poll_interval=.01,
        snapshot_consumer=consumer,
    )


def test_static_baseline_frame_never_runs_perception_or_guards():
    clock, guards, consumed = Clock(), [], []
    obs = make_observer(clock, [snapshot().frame], consumer=consumed.append)
    with pytest.raises(RuntimeWaitTimeout) as caught:
        obs.wait_until(lambda s: guards.append(s) or True, after_sequence=1, timeout=.03)
    assert obs.perception.calls == guards == consumed == []
    assert obs.source.calls == caught.value.poll_count >= 3
    assert caught.value.last_snapshot is None
    assert clock() == pytest.approx(10.03)


def test_static_eligible_frame_is_evaluated_once_then_new_frame_without_extra_sleep():
    clock, guards, consumed = Clock(), [], []
    first, second = snapshot(2, 10).frame, snapshot(3, 10.02).frame
    obs = make_observer(clock, [first, first, second], consumer=consumed.append)
    found = obs.wait_until(lambda s: guards.append(s.sequence) or s.sequence == 3,
                           after_sequence=1, timeout=1)
    assert found.sequence == 3 and guards == [2, 3]
    assert [seq for _, seq in obs.perception.calls] == [2, 3]
    assert [s.sequence for s in consumed] == [2, 3]
    assert clock.sleeps == [.01, .01]


def test_direct_observe_other_wait_and_other_scope_reanalyze_the_same_frame():
    clock = Clock()
    obs = make_observer(clock, [snapshot(2, 10).frame])
    initial = obs.observe()
    assert obs.wait_until(lambda s: s.sequence == initial.sequence, after_sequence=1, timeout=1)
    assert obs.wait_until(lambda s: True, after_sequence=1, timeout=1)
    scoped = obs.scoped(Analysis(coverage=lambda: {"blocker"}))
    found = scoped.wait_until(lambda s: True, after_sequence=1, timeout=1,
                             evidence=RuntimeEvidenceRequirements(required_coverage={"blocker"}))
    assert found.sequence == initial.sequence and found.observations.coverage == {"blocker"}
    assert len(obs.perception.calls) == 3 and len(scoped.perception.calls) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize("missing", [None, frozenset(), frozenset({"other"})])
def test_coverage_not_yet_executed_does_not_mark_frame_evaluated(missing):
    clock, guards = Clock(), []
    capabilities = iter([missing, {"guard"}])
    obs = make_observer(clock, [snapshot(2, 10).frame],
                        analysis=Analysis(coverage=lambda: next(capabilities)))
    result = obs.wait_until(lambda s: guards.append(s) or True, after_sequence=1, timeout=1,
                            evidence=RuntimeEvidenceRequirements(required_coverage={"guard"}))
    assert result.sequence == 2 and guards == [result]
    assert len(obs.perception.calls) == 2


@pytest.mark.parametrize("timestamp,requirements", [
    (9.9, RuntimeEvidenceRequirements(max_age=.05)),
    (10., RuntimeEvidenceRequirements(captured_after=10.)),
    (9.99, RuntimeEvidenceRequirements(captured_after=10.)),
])
def test_ineligible_acquisition_is_rejected_before_analysis(timestamp, requirements):
    clock, guards = Clock(), []
    obs = make_observer(clock, [snapshot(2, timestamp).frame])
    with pytest.raises(RuntimeWaitTimeout):
        obs.wait_until(lambda s: guards.append(s) or True, after_sequence=1, timeout=.03,
                       evidence=requirements)
    assert obs.perception.calls == guards == []


def test_future_timestamp_can_become_eligible_without_new_sequence():
    clock = Clock()
    obs = make_observer(clock, [snapshot(2, 10.02).frame])
    result = obs.wait_until(lambda s: True, after_sequence=1, timeout=1,
                            evidence=RuntimeEvidenceRequirements(max_age=.05))
    assert result.sequence == 2 and len(obs.perception.calls) == 1
    assert clock() == pytest.approx(10.02)


def test_late_native_capture_keeps_start_time_and_skips_perception():
    clock = Clock()
    ok, png = cv2.imencode('.png', np.zeros((20, 40, 3), np.uint8))
    assert ok

    def capture_png():
        clock.now += .2
        return png.tobytes()

    # Real native publication/copy path; no source start, sockets or hardware.
    native = ScrcpyFrameSource(SimpleNamespace(capture_png=capture_png), 'unused.jar', clock=clock)
    frame = native.refresh_native()
    assert frame.timestamp == 10. and native.get_frame().timestamp == 10.
    obs = make_observer(clock, [native.get_frame()])
    obs.source = native
    with pytest.raises(RuntimeWaitTimeout):
        obs.wait_until(lambda s: True, after_sequence=0, timeout=.03,
                       evidence=RuntimeEvidenceRequirements(max_age=.05, source_id=frame.source_id))
    assert obs.perception.calls == [] and not native.is_running


def test_source_rotation_is_still_seen_by_analysis_even_for_old_sequence():
    clock = Clock()
    obs = make_observer(clock, [snapshot(1, 9.9, source='replacement').frame,
                                snapshot(2, 10.01).frame])
    result = obs.wait_until(lambda s: True, after_sequence=1, timeout=1,
                            evidence=RuntimeEvidenceRequirements(source_id='lifetime-1', max_age=.05))
    assert obs.perception.calls == [('replacement', 1), ('lifetime-1', 2)]
    assert result.frame.source_id == 'lifetime-1'


@pytest.mark.parametrize("stage", ['before', 'capture', 'perception', 'poll', 'condition'])
def test_cancellation_retains_checks_including_when_no_analysis_occurs(stage):
    clock, cancelled, guards = Clock(), [stage == 'before'], []

    def cancel():
        cancelled[0] = True

    def condition(s):
        guards.append(s)
        cancel()
        return True

    seq = 1 if stage == 'poll' else 2
    obs = make_observer(clock, [snapshot(seq, 10).frame],
                        analysis=Analysis(work=cancel if stage == 'perception' else lambda: None),
                        capture_work=cancel if stage == 'capture' else lambda: None)
    if stage == 'poll':
        obs._sleeper = lambda duration: (clock.sleep(duration), cancel())
    with pytest.raises(RuntimeWaitCancelled):
        obs.wait_until(condition, after_sequence=1, timeout=1, cancel_requested=lambda: cancelled[0])
    assert len(obs.perception.calls) == (1 if stage in {'perception', 'condition'} else 0)
    assert len(guards) == (1 if stage == 'condition' else 0)


@pytest.mark.parametrize("stage", ['before', 'capture', 'perception', 'condition'])
def test_explicit_deadline_never_accepts_late_work(stage):
    clock, guards = Clock(), []

    def slow():
        clock.now += .1

    def condition(s):
        guards.append(s)
        slow()
        return True

    obs = make_observer(clock, [snapshot(2, 10).frame],
                        analysis=Analysis(work=slow if stage == 'perception' else lambda: None),
                        capture_work=slow if stage == 'capture' else lambda: None)
    with pytest.raises(RuntimeWaitTimeout):
        obs.wait_until(condition, after_sequence=1, timeout=1,
                       deadline=10. if stage == 'before' else 10.05)
    assert len(obs.perception.calls) == (1 if stage in {'perception', 'condition'} else 0)
    assert len(guards) == (1 if stage == 'condition' else 0)


def test_parent_budget_bounds_static_stream_without_analysis():
    clock = Clock()
    obs = make_observer(clock, [snapshot().frame])
    with control_scope(OperationControl(observation_timeout=.03125, clock=clock)):
        with pytest.raises(OperationBudgetExpired):
            obs.wait_until(lambda s: True, after_sequence=1, timeout=1)
    assert clock() == pytest.approx(10.03125) and obs.perception.calls == []


def test_blocker_precedes_matching_postcondition_in_new_scope_on_same_frame():
    clock, guards = Clock(), []
    obs = make_observer(clock, [snapshot(2, 10).frame])
    obs.observe()
    scoped = obs.scoped(Analysis(coverage=lambda: {'blocker'}))
    with pytest.raises(RuntimeWaitAborted) as caught:
        scoped.wait_until(lambda s: guards.append(s) or True, after_sequence=1, timeout=1,
                          abort_if=lambda s: True,
                          evidence=RuntimeEvidenceRequirements(required_coverage={'blocker'}))
    assert caught.value.snapshot.sequence == 2 and len(scoped.perception.calls) == 1
    assert guards == [] and clock.sleeps == []


def test_repeated_frame_cannot_establish_stability_and_expiration_resets_it():
    clock = Clock()
    first = snapshot(2, 10).frame
    obs = make_observer(clock, [first, first, first, first,
                                snapshot(3, 10.04).frame, snapshot(4, 10.06).frame])
    obs.poll_interval = .02
    result = obs.wait_until(lambda s: True, after_sequence=1, timeout=1, stable_for=.02,
                            evidence=RuntimeEvidenceRequirements(max_age=.05))
    # At .06 the duplicate has expired, so timestamp 10.04 begins a new window.
    assert result.sequence == 4
    assert [seq for _, seq in obs.perception.calls] == [2, 3, 4]


def test_age_is_rechecked_after_perception_and_postcondition_without_retry():
    clock, guards = Clock(), []
    obs = make_observer(clock, [snapshot(2, 10.001).frame, snapshot(3, 10.2).frame],
                        capture_work=lambda: setattr(clock, 'now', clock.now + .001))

    def expected(s):
        guards.append(s.sequence)
        if s.sequence == 2:
            clock.now += .1
        return True

    result, adb = run(clock, obs, expected=expected,
                      evidence=RuntimeEvidenceRequirements(max_age=.05),
                      policy=VerifiedTransitionPolicy(normal_timeout=.3, grace_timeout=.1, max_attempts=1))
    assert result.succeeded and result.final_snapshot.sequence == 3
    assert guards == [2, 3] and len(adb.calls) == 1


def test_age_expiring_during_analysis_never_reaches_guards():
    clock, guards, consumed = Clock(), [], []

    def slow():
        clock.now += .1

    obs = make_observer(clock, [snapshot(2, 10).frame], analysis=Analysis(work=slow),
                        consumer=consumed.append)
    with pytest.raises(RuntimeWaitTimeout):
        obs.wait_until(lambda s: guards.append(s) or True, after_sequence=1, timeout=.125,
                       abort_if=lambda s: guards.append(s) or True,
                       evidence=RuntimeEvidenceRequirements(max_age=.05))
    assert len(obs.perception.calls) == len(consumed) == 1 and guards == []


def test_static_stream_cannot_make_stability_true_by_polling():
    clock = Clock()
    obs = make_observer(clock, [snapshot(2, 10).frame])
    with pytest.raises(RuntimeWaitTimeout) as caught:
        obs.wait_until(lambda s: True, after_sequence=1, timeout=.125, stable_for=.02)
    assert len(obs.perception.calls) == 1 and caught.value.last_snapshot.sequence == 2
