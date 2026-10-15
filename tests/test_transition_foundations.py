"""Offline safety boundaries: no device, wall-clock sleeps or perception assets."""

import subprocess

import numpy as np
import pytest

from bot.action_executor import ActionExecutor, DispatchState, FrameGeometry
from bot.adb import AdbClient, AdbError
from bot.capture import FrameSnapshot
from bot.event_context import event_context
from bot.observations import ObservationBatch
from bot.operation_control import OperationControl, current_control
from bot.resolver import ContextResolver
from bot.runtime_observer import (
    RuntimeEvidenceRequirements, RuntimeFacts, RuntimeObserver, RuntimeSnapshot,
    RuntimeWaitCancelled, RuntimeWaitTimeout,
)
from bot.semantic_actions import OpenQuickMenu, ToggleAutoBattle, Swipe
from bot.monster_wave_actions import SelectMonsterWaveMax
from bot.arena_actions import ArenaAction, ArenaControl
from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy


class Clock:
    def __init__(self):
        self.now = 10.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


def snapshot(sequence=1, timestamp=9.99, source="lifetime-1", coverage=frozenset({"guard"})):
    frame = FrameSnapshot(np.zeros((20, 40, 3), dtype=np.uint8), timestamp, sequence, source_id=source)
    batch = ObservationBatch(sequence, timestamp, coverage=coverage)
    return RuntimeSnapshot(frame, batch, ContextResolver().resolve(batch), RuntimeFacts(), FrameGeometry(40, 20))


class Source:
    def __init__(self, clock, frames=(), work=lambda: None):
        self.clock = clock
        self.frames = list(frames)
        self.sequence = 1
        self.work = work

    def get_frame(self):
        self.work()
        if self.frames:
            return self.frames.pop(0)
        self.sequence += 1
        self.clock.now += .001
        return snapshot(self.sequence, self.clock(), source="lifetime-1").frame


class Perception:
    def __init__(self, work=lambda: None, coverage=frozenset({"guard"})):
        self.work = work
        self.coverage = coverage

    def analyze(self, frame):
        self.work()
        return ObservationBatch(frame.sequence, frame.timestamp, coverage=self.coverage)


class Adb:
    def __init__(self, work=lambda: None):
        self.calls = []
        self.work = work

    def tap(self, *args):
        self.calls.append(args)
        self.work()

    swipe = tap


def observer(clock, *, frames=(), capture_work=lambda: None, work=lambda: None, coverage=frozenset({"guard"})):
    return RuntimeObserver(
        Source(clock, frames, capture_work), Perception(work, coverage), ContextResolver(),
        clock=clock, sleeper=clock.sleep, poll_interval=.01,
    )


def run(clock, obs, adb=None, **kwargs):
    adb = Adb() if adb is None else adb
    transition = VerifiedTransition(obs, ActionExecutor(adb), clock=clock)
    return transition.execute(
        "foundation", kwargs.pop("action", OpenQuickMenu()), kwargs.pop("before", snapshot()),
        expected=kwargs.pop("expected", lambda s: True),
        policy=kwargs.pop("policy", VerifiedTransitionPolicy(normal_timeout=.03, grace_timeout=.02, max_attempts=2)),
        **kwargs,
    ), adb


def test_cancel_before_transition_sends_nothing_and_restores_context():
    clock, adb = Clock(), Adb()
    with pytest.raises(RuntimeWaitCancelled) as caught:
        run(clock, observer(clock), adb, cancel_requested=lambda: True)
    assert adb.calls == []
    assert caught.value.dispatch_receipts == ()
    assert current_control() is None and event_context()["operation_id"] is None


@pytest.mark.parametrize("stage", ["capture", "perception", "condition"])
def test_cancel_during_wait_stops_before_following_expensive_stage(stage):
    clock, cancelled, called = Clock(), [False], []

    def cancel():
        cancelled[0] = True

    def condition(s):
        called.append(s.sequence)
        if stage == "condition":
            cancel()
        return True

    obs = observer(clock, capture_work=cancel if stage == "capture" else lambda: None,
                   work=cancel if stage == "perception" else lambda: None)
    adb = Adb()
    with pytest.raises(RuntimeWaitCancelled) as caught:
        run(clock, obs, adb, expected=condition, cancel_requested=lambda: cancelled[0], retryable_from=lambda s: True)
    assert len(adb.calls) == 1
    assert len(caught.value.dispatch_receipts) == 1
    assert called == ([2] if stage == "condition" else [])


def test_cancel_during_reacquisition_does_not_retry():
    clock, cancelled, adb = Clock(), [False], Adb()

    class Reacquire:
        def wait_until(self, *args, **kwargs):
            raise RuntimeWaitTimeout(after_sequence=1, timeout=.01, last_snapshot=snapshot())

        def observe(self):
            cancelled[0] = True
            return snapshot(4, clock())

    with pytest.raises(RuntimeWaitCancelled):
        run(clock, Reacquire(), adb, expected=lambda s: False,
            retryable_from=lambda s: True, cancel_requested=lambda: cancelled[0])
    assert len(adb.calls) == 1


@pytest.mark.parametrize("when", ["before", "during", "after"])
def test_recovery_shares_cancellation_with_executor_and_return_boundary(when):
    clock, cancelled, adb = Clock(), [False], Adb()
    calls = []

    class Recovery:
        def attempt(self, before, condition):
            calls.append("attempt")
            if when == "during":
                cancelled[0] = True
                ActionExecutor(adb).execute(OpenQuickMenu(), before.geometry)
            cancelled[0] = True
            return snapshot(2, clock())

    def precondition(s):
        if when == "before":
            cancelled[0] = True
        return False

    transition = VerifiedTransition(observer(clock), ActionExecutor(adb), obstruction_recovery=Recovery(), clock=clock)
    with pytest.raises(RuntimeWaitCancelled):
        transition.execute("recovery", OpenQuickMenu(), snapshot(), expected=lambda s: False,
                           precondition=precondition, policy=VerifiedTransitionPolicy(),
                           cancel_requested=lambda: cancelled[0])
    assert adb.calls == []
    assert calls == ([] if when == "before" else ["attempt"])


def test_cancel_between_physical_parts_keeps_partial_receipt_and_sends_no_second_tap():
    clock, cancelled = Clock(), [False]
    adb = Adb(lambda: cancelled.__setitem__(0, True))
    with pytest.raises(RuntimeWaitCancelled) as caught:
        run(clock, observer(clock), adb, action=SelectMonsterWaveMax(), cancel_requested=lambda: cancelled[0])
    receipt, = caught.value.dispatch_receipts
    assert len(adb.calls) == receipt.commands_returned == receipt.commands_started == 1
    assert receipt.commands_planned == 2 and receipt.state is DispatchState.UNCERTAIN
    assert receipt.operation_id and receipt.attempt_index == 1
    assert receipt.started_at <= receipt.completed_at


@pytest.mark.parametrize("failure,state", [
    (FileNotFoundError("adb unavailable"), DispatchState.NOT_SENT),
    (OSError("I/O failed after possible send"), DispatchState.UNCERTAIN),
    (subprocess.TimeoutExpired("adb", 1), DispatchState.UNCERTAIN),
    (subprocess.CompletedProcess([], 1, "", "transport closed"), DispatchState.UNCERTAIN),
])
def test_adb_boundary_distinguishes_no_send_from_possible_send_without_transport_retry(failure, state):
    clock, calls = Clock(), []

    def runner(*args, **kwargs):
        calls.append(args)
        if isinstance(failure, BaseException):
            raise failure
        return failure

    adb = AdbClient("fake-adb", "fake-device", runner=runner)
    result, _ = run(clock, observer(clock), adb, retryable_from=lambda s: True)
    assert not result.succeeded and len(calls) == 1
    receipt, = result.dispatch_receipts
    assert receipt.state is state and not result.effect_accredited


def test_second_adb_command_not_started_still_leaves_compound_dispatch_uncertain():
    calls = []

    def runner(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise FileNotFoundError("second adb unavailable")
        return subprocess.CompletedProcess([], 0, "", "")

    clock = Clock()
    result, _ = run(clock, observer(clock), AdbClient("fake", "fake", runner=runner), action=SelectMonsterWaveMax())
    receipt, = result.dispatch_receipts
    assert len(calls) == 2 and receipt.commands_returned == 1
    assert receipt.state is DispatchState.UNCERTAIN


def test_target_resolution_failure_is_definitely_not_sent():
    adb = Adb()
    with pytest.raises(ValueError) as caught:
        ActionExecutor(adb).execute(object(), FrameGeometry(40, 20))
    assert caught.value.dispatch_receipt.state is DispatchState.NOT_SENT
    assert adb.calls == []


@pytest.mark.parametrize("action,count", [(OpenQuickMenu(), 1), (SelectMonsterWaveMax(), 2),
                                        (ArenaAction(ArenaControl.X8), 2),
                                        (Swipe((.1, .1), (.8, .8), 100), 1)])
def test_successful_receipts_do_not_claim_game_effect_and_add_no_wait(action, count):
    clock, adb = Clock(), Adb()
    result, _ = run(clock, observer(clock), adb, action=action)
    receipt, = result.dispatch_receipts
    assert receipt.state is DispatchState.ADB_RETURNED
    assert receipt.commands_planned == receipt.commands_returned == count == len(adb.calls)
    assert result.effect_accredited and result.ready and result.succeeded
    assert receipt.operation_id == result.operation_id and receipt.attempt_index == 1
    assert clock.sleeps == []


def test_new_sequence_with_pre_dispatch_acquisition_cannot_satisfy_postcondition():
    clock, used = Clock(), []
    obs = observer(clock, frames=[snapshot(50, 9.9).frame, snapshot(51, 10.001).frame])
    result, adb = run(clock, obs, evidence=RuntimeEvidenceRequirements(), expected=lambda s: used.append(s.sequence) or True)
    assert result.succeeded and result.final_snapshot.sequence == 51 and used == [51]
    assert len(adb.calls) == 1


def test_evidence_expiring_inside_condition_is_rejected_then_fresh_evidence_is_used():
    clock, used = Clock(), []

    def condition(s):
        used.append(s.sequence)
        if len(used) == 1:
            clock.now += .1
        return True

    result, adb = run(clock, observer(clock), expected=condition,
                      evidence=RuntimeEvidenceRequirements(max_age=.05))
    assert result.succeeded and used == [2, 3] and len(adb.calls) == 1


@pytest.mark.parametrize("bad", [snapshot(2, 10.001, source="replacement"),
                                  snapshot(2, 10.001, coverage=None),
                                  snapshot(2, 10.001, coverage=frozenset())])
def test_source_or_coverage_loss_never_calls_guard_or_authorizes_retry(bad):
    clock, guards, adb = Clock(), [], Adb()

    class BadEvidence:
        def wait_until(self, condition, **kwargs):
            assert not condition(bad)
            raise RuntimeWaitTimeout(after_sequence=1, timeout=.01, last_snapshot=bad)

        def observe(self):
            return bad

    result, _ = run(clock, BadEvidence(), adb, evidence=RuntimeEvidenceRequirements(required_coverage={"guard"}),
                    expected=lambda s: guards.append(s) or False, retryable_from=lambda s: guards.append(s) or True)
    assert not result.succeeded and guards == [] and len(adb.calls) == 1
    assert result.termination_reason == "runtime_evidence_rejected"


def test_runtime_wait_requires_explicit_coverage_even_for_negative_guard():
    clock, guards = Clock(), []
    with pytest.raises(RuntimeWaitTimeout):
        observer(clock, coverage=None).wait_until(
            lambda s: guards.append(s) or not s.observations.observations,
            after_sequence=1, timeout=.02,
            evidence=RuntimeEvidenceRequirements(required_coverage={"guard"}),
        )
    assert guards == []


def test_total_deadline_bounds_progress_nominal_grace_and_prevents_retry():
    clock = Clock()
    result, adb = run(clock, observer(clock), expected=lambda s: False,
                      retryable_from=lambda s: True, progress_observed=lambda s: True,
                      policy=VerifiedTransitionPolicy(normal_timeout=.03, grace_timeout=.1, total_timeout=.05, max_attempts=5))
    assert not result.succeeded and not result.effect_accredited and result.progress_snapshot is not None
    assert len(adb.calls) == 1 and result.termination_reason == "operation budget exhausted"
    assert clock() <= 10.051
    assert result.action_source_snapshot is not None


def test_already_expired_shared_deadline_sends_nothing():
    clock = Clock()
    result, adb = run(clock, observer(clock), budget=OperationControl(deadline=clock(), clock=clock))
    assert len(adb.calls) == result.attempt_count == 0
    assert not result.succeeded and result.dispatch_receipts == ()


@pytest.mark.parametrize("phase", ["observation", "dispatch", "recovery"])
def test_separate_phase_allowances_stop_inputs_at_expensive_boundary(phase):
    clock, adb = Clock(), Adb()

    def slow():
        clock.now += .1

    policy = VerifiedTransitionPolicy(**{phase + "_timeout": .05})
    if phase == "recovery":
        class Recovery:
            def attempt(self, before, condition):
                slow()
                ActionExecutor(adb).execute(OpenQuickMenu(), before.geometry)

        transition = VerifiedTransition(observer(clock), ActionExecutor(adb), obstruction_recovery=Recovery(), clock=clock)
        result = transition.execute("recovery", OpenQuickMenu(), snapshot(), expected=lambda s: False,
                                    precondition=lambda s: False, policy=policy)
    elif phase == "dispatch":
        adb.work = slow
        result, _ = run(clock, observer(clock), adb, policy=policy, action=SelectMonsterWaveMax())
    else:
        result, _ = run(clock, observer(clock), adb, policy=policy, precondition=lambda s: slow() or True)
    assert not result.succeeded and len(adb.calls) == (1 if phase == "dispatch" else 0)
    assert result.termination_reason == "operation budget exhausted"


def test_accredited_effect_survives_missing_readiness_and_blocks_productive_retry():
    clock = Clock()
    result, adb = run(clock, observer(clock), expected=lambda s: False,
                      effect_observed=lambda s: s.sequence == 2,
                      progress_observed=lambda s: s.sequence == 2,
                      retryable_from=lambda s: True)
    assert result.effect_accredited and result.ready is False and not result.succeeded
    assert result.progress_snapshot.sequence == 2 and len(adb.calls) == 1
    assert result.termination_reason == "effect_accredited_not_ready"


def test_explicit_effect_predicate_is_independent_of_positive_readiness():
    clock = Clock()
    result, adb = run(clock, observer(clock), expected=lambda s: True,
                      effect_observed=lambda s: False)
    assert result.succeeded and result.ready
    assert not result.effect_accredited
    assert len(adb.calls) == 1 and clock.sleeps == []


def test_deadline_expiring_between_check_and_wait_clamp_is_a_timeout():
    class TickingClock(Clock):
        def __call__(self):
            self.now += .001
            return self.now

    # Move the deadline through different operation boundaries while time
    # advances even outside perception/sleep. No expired wait may leak an
    # invalid (zero/negative) timeout into a legacy observer's duration API.
    for milliseconds in range(1, 101):
        clock = TickingClock()
        result, adb = run(
            clock, observer(clock), expected=lambda s: False,
            policy=VerifiedTransitionPolicy(normal_timeout=.01, grace_timeout=.01,
                                             total_timeout=milliseconds / 1000),
        )
        assert not result.succeeded
        assert len(adb.calls) <= 1


def test_toggle_transport_failure_has_no_retry_even_with_positive_retry_guard():
    def fail():
        raise AdbError(("fake",), reason="transport interrupted")

    clock, adb = Clock(), Adb(fail)
    result, _ = run(clock, observer(clock), adb, action=ToggleAutoBattle(), retryable_from=lambda s: True)
    assert not result.succeeded and len(adb.calls) == 1
    assert result.dispatch_receipts[0].state is DispatchState.UNCERTAIN


def test_legacy_executor_and_observer_need_no_new_keywords_and_keep_retry_policy():
    clock, calls = Clock(), []

    class Legacy:
        waits = 0

        def observe(self):
            return snapshot(4)

        def wait_until(self, condition, *, after_sequence, timeout, abort_if=None, stable_for=0):
            self.waits += 1
            if self.waits <= 2:
                raise RuntimeWaitTimeout(after_sequence=after_sequence, timeout=timeout, last_snapshot=snapshot())
            assert condition(snapshot(5))
            return snapshot(5)

    class Actions:
        def execute(self, action, geometry):
            calls.append(action)

    result = VerifiedTransition(Legacy(), Actions(), clock=clock).execute(
        "legacy", OpenQuickMenu(), snapshot(), expected=lambda s: s.sequence == 5,
        retryable_from=lambda s: True, policy=VerifiedTransitionPolicy(max_attempts=2),
    )
    assert result.succeeded and len(calls) == 2
    assert [r.attempt_index for r in result.dispatch_receipts] == [1, 2]
    assert all(r.state is DispatchState.UNCERTAIN for r in result.dispatch_receipts)


def test_guard_expiring_during_target_resolution_prevents_dispatch():
    clock, adb = Clock(), Adb()

    class SlowTarget(ActionExecutor):
        def target_for(self, action):
            clock.now += .1
            return super().target_for(action)

    result = VerifiedTransition(observer(clock), SlowTarget(adb), clock=clock).execute(
        "target", OpenQuickMenu(), snapshot(), expected=lambda s: True,
        evidence=RuntimeEvidenceRequirements(max_age=.05), policy=VerifiedTransitionPolicy(),
    )
    assert not result.succeeded and adb.calls == []
    assert result.dispatch_receipts[0].state is DispatchState.NOT_SENT


@pytest.mark.parametrize('scenario', ['ready', 'miss', 'expired_guard', 'cancel', 'deadline'])
def test_reacquisition_with_real_waits_and_executor_keeps_retry_bounds(scenario):
    clock, adb, cancelled = Clock(), Adb(), [False]

    class Target(ActionExecutor):
        def target_for(self, action):
            if len(adb.calls) == 1:
                if scenario == 'expired_guard':
                    clock.now += .06
                if scenario == 'deadline':
                    clock.now += 1.
                if scenario == 'cancel':
                    cancelled[0] = True
            return super().target_for(action)

    transition = VerifiedTransition(observer(clock), Target(adb), clock=clock)
    args = dict(
        expected=lambda s: scenario == 'ready' and len(adb.calls) == 2,
        reacquire_from=lambda s: True,
        retryable_from=lambda s: 0 <= clock() - s.timestamp <= .05,
        policy=VerifiedTransitionPolicy(
            normal_timeout=.03, grace_timeout=.02, max_attempts=2, total_timeout=.1,
        ),
        cancel_requested=lambda: cancelled[0],
    )
    if scenario == 'cancel':
        with pytest.raises(RuntimeWaitCancelled) as caught:
            transition.execute('reacquire.real', OpenQuickMenu(), snapshot(), **args)
        receipts = caught.value.dispatch_receipts
    else:
        result = transition.execute('reacquire.real', OpenQuickMenu(), snapshot(), **args)
        assert result.succeeded is (scenario == 'ready')
        assert result.grace_wait_count == 1
        receipts = result.dispatch_receipts
        if scenario == 'miss':
            assert result.termination_reason == 'attempts_exhausted'
            assert clock() < 10.08  # No second grace/observe tail.
        if scenario == 'expired_guard':
            assert result.termination_reason == 'retry_authorization_invalidated'
        if scenario == 'deadline':
            assert result.termination_reason == 'operation budget exhausted'
    assert len(adb.calls) == (2 if scenario in {'ready', 'miss'} else 1)
    assert receipts[0].state is DispatchState.ADB_RETURNED
    if scenario in {'expired_guard', 'cancel', 'deadline'}:
        assert receipts[-1].state is DispatchState.NOT_SENT


def test_dispatch_budget_caps_adb_timeout_without_extending_its_existing_limit():
    clock, timeouts = Clock(), []

    def runner(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess([], 0, "", "")

    adb = AdbClient("fake", "fake", default_timeout=.1, runner=runner)
    result, _ = run(clock, observer(clock), adb,
                    policy=VerifiedTransitionPolicy(total_timeout=1, dispatch_timeout=.2))
    assert result.succeeded and timeouts == [.1]
    result, _ = run(clock, observer(clock), adb,
                    policy=VerifiedTransitionPolicy(total_timeout=1, dispatch_timeout=.05))
    assert result.succeeded and timeouts[-1] == pytest.approx(.05)


def test_standalone_wait_cancellation_after_capture_skips_perception():
    clock, cancelled, analyses = Clock(), [False], []
    obs = observer(clock, capture_work=lambda: cancelled.__setitem__(0, True),
                   work=lambda: analyses.append(True))
    with pytest.raises(RuntimeWaitCancelled):
        obs.wait_until(lambda s: True, after_sequence=1, timeout=1,
                       cancel_requested=lambda: cancelled[0])
    assert analyses == []


def test_legacy_stability_survives_duplicate_stream_frames():
    clock = Clock()
    obs = observer(clock, frames=[snapshot(2, 10).frame, snapshot(2, 10).frame, snapshot(3, 10.2).frame])
    result = obs.wait_until(lambda s: True, after_sequence=1, timeout=1, stable_for=.1)
    assert result.sequence == 3


def test_shared_observation_allowance_is_cumulative_across_transitions():
    clock, adb = Clock(), Adb()
    budget = OperationControl(observation_timeout=.05, clock=clock)

    def work():
        clock.now += .03

    result, _ = run(clock, observer(clock, work=work), adb, budget=budget)
    assert result.succeeded
    result, _ = run(clock, observer(clock, work=work), adb, budget=budget)
    assert not result.succeeded and result.termination_reason == "operation budget exhausted"
    assert len(adb.calls) == 2
    result, _ = run(clock, observer(clock), adb, budget=budget)
    # The exhausted observation allowance is checked before the next guard;
    # it must also prevent dispatch before any new observation phase starts.
    assert not result.succeeded and len(adb.calls) == 2


@pytest.mark.parametrize("mode", ["cancel", "expired"])
def test_real_recovery_probe_cannot_dispatch_after_cancellation_or_expiry(mode):
    from dataclasses import replace
    from bot.obstruction_recovery import PortalObstructionRecovery
    from bot.portal_notification import PortalProbeOutcome
    from bot.state import ResolvedState, ResolutionStatus

    clock, cancelled, adb = Clock(), [False], Adb()
    before = snapshot()
    before = replace(before, state=ResolvedState(
        ResolutionStatus.RESOLVED, before.sequence, before.timestamp, base_context="screen.combine",
    ))

    class Probe:
        def probe(self, image):
            if mode == "cancel":
                cancelled[0] = True
            else:
                clock.now += .1
            return PortalProbeOutcome.CONFIRMED

    obs = observer(clock)
    recovery = PortalObstructionRecovery(obs, ActionExecutor(adb), Probe(), clock=clock, sleeper=clock.sleep)
    transition = VerifiedTransition(obs, ActionExecutor(adb), obstruction_recovery=recovery, clock=clock)
    args = dict(expected=lambda s: False, precondition=lambda s: False,
                precondition_regions=((.2, .15, .3, .2),),
                policy=VerifiedTransitionPolicy(), evidence=RuntimeEvidenceRequirements(max_age=.05),
                cancel_requested=lambda: cancelled[0])
    if mode == "cancel":
        with pytest.raises(RuntimeWaitCancelled):
            transition.execute("probe", OpenQuickMenu(), before, **args)
    else:
        result = transition.execute("probe", OpenQuickMenu(), before, **args)
        assert not result.succeeded and result.termination_reason == "runtime_evidence_rejected"
    assert adb.calls == []


@pytest.mark.parametrize("factory", ["productive", "registry", "scoped"])
def test_shared_factories_preserve_existing_cancellation_callback(factory, monkeypatch):
    from types import SimpleNamespace
    from bot.productive_runtime import ProductiveRuntime
    from bot import flow_registry

    clock, adb = Clock(), Adb()
    obs = observer(clock)
    cancel = lambda: True
    dependencies = SimpleNamespace(observer=obs, actions=ActionExecutor(adb), events=None,
                                   cancel_requested=cancel, _shared_obstruction_recovery=lambda: None)
    if factory == "productive":
        transition = ProductiveRuntime.build_verified_transition(dependencies)
    elif factory == "registry":
        transition = flow_registry._verified_transition_for(dependencies)
    else:
        obs.perception.detectors = ()
        monkeypatch.setattr(flow_registry, "_scoped_subset_observer", lambda *args: obs)
        main = VerifiedTransition(obs, dependencies.actions)
        transition = flow_registry.scoped_transition_for(
            dependencies, main, scope=object(), active_event="test.active", unavailable_event="test.unavailable",
        )
        assert transition is not main
    assert transition.cancel_requested is cancel
    with pytest.raises(RuntimeWaitCancelled):
        transition.execute("factory", OpenQuickMenu(), snapshot(), expected=lambda s: True,
                           policy=VerifiedTransitionPolicy())
    assert adb.calls == []


def test_constructor_cancellation_preserves_old_wait_adapter_signature():
    clock, cancelled, adb = Clock(), [False], Adb()

    class LegacyObserver:
        def observe(self):
            raise AssertionError("cancelled operation must not reacquire")

        def wait_until(self, condition, *, after_sequence, timeout, abort_if=None, stable_for=0):
            cancelled[0] = True
            raise RuntimeWaitTimeout(after_sequence=after_sequence, timeout=timeout, last_snapshot=snapshot())

    transition = VerifiedTransition(LegacyObserver(), ActionExecutor(adb), clock=clock,
                                    cancel_requested=lambda: cancelled[0])
    with pytest.raises(RuntimeWaitCancelled):
        transition.execute("adapter", OpenQuickMenu(), snapshot(), expected=lambda s: False,
                           retryable_from=lambda s: True, policy=VerifiedTransitionPolicy(max_attempts=2))
    assert len(adb.calls) == 1
