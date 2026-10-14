"""adbbe95b: a CLEAR title miss must not certify dismissal or repeat SKIP."""
from dataclasses import replace

import pytest

from bot.flow_contracts import FlowStatus
from bot.monster_wave_activity import MonsterWaveActivity
from bot.monster_wave_actions import AcknowledgeMonsterWaveClear
from bot.monster_wave_semantics import (
    MW_CLEAR, MW_CONTROLS_CLEAR, MW_MAX, MW_NEEDS_TICKETS, MW_SKIP_START,
    MW_TIMER, POPUP_MW_CLEAR, SCREEN_MONSTER_WAVE,
)
from bot.observations import Observation, ObservationSource
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.state import ResolutionStatus
from tests.test_verified_transition import Actions, Events
from test_world_boss_flow import snapshot


def frame(sequence, timestamp, *, clear=False, names=(), status=None,
          base=SCREEN_MONSTER_WAVE, overlays=None):
    observations = [Observation(n, 1., ObservationSource.LOCAL_CV) for n in names]
    if clear:
        observations.append(Observation(MW_CLEAR, .90, ObservationSource.LOCAL_CV))
    s = snapshot(sequence, base=base, status=status,
                 overlays=((POPUP_MW_CLEAR,) if clear else ()) if overlays is None else overlays,
                 semantic_observations=tuple(observations))
    return replace(s, frame=replace(s.frame, timestamp=timestamp),
                   observations=replace(s.observations, timestamp=timestamp),
                   state=replace(s.state, timestamp=timestamp))


READY = (MW_TIMER, MW_SKIP_START, MW_MAX, MW_CONTROLS_CLEAR)


class Observer:
    """Each wait polls its recorded scenario, with real temporal stability."""
    def __init__(self, waits, observes, cancelled):
        self.waits, self.observes = list(waits), list(observes)
        self.now, self.cancelled = 10.1, cancelled
        self.polls = []

    def wait_until(self, condition, *, after_sequence, timeout, stable_for=0., **kwargs):
        since = None
        frames = self.waits.pop(0)
        for s in frames:
            if self.cancelled[0]:
                raise RuntimeWaitCancelled()
            self.now = s.timestamp + .1
            self.polls.append(s.sequence)
            if s.sequence <= after_sequence:
                continue
            if condition(s):
                since = s.timestamp if since is None else since
                if s.timestamp - since >= stable_for:
                    return s
            else:
                since = None
        raise RuntimeWaitTimeout(after_sequence=after_sequence, timeout=timeout, last_snapshot=s)

    def observe(self):
        s = self.observes.pop(0)
        self.now += .2
        return s


def setup(*, bad=None, second_failure=False, late=False, needs=False):
    before = frame(58312, 10., clear=True)
    # Recorded snapshots 58324/58330: MW+MAX, no overlay, but the CLEAR
    # dialog is physically open. Its title is occluded by reward notices.
    misses = [frame(58324, 11.3, names=(MW_MAX,)),
              frame(58330, 11.9, names=(MW_MAX,)),
              frame(58335, 16., clear=True)]
    fresh = frame(58396, 18.2, clear=True)
    names = (MW_NEEDS_TICKETS, MW_CONTROLS_CLEAR) if needs else READY
    ready = [frame(58400, 18.8, names=names), frame(58406, 19.4, names=names)]
    waits = [misses, [frame(58390, 18., clear=True)], ready]
    observes = [fresh]
    if second_failure:
        waits[2:] = [[frame(58450, 24.2, clear=True)], [frame(58470, 26.2, clear=True)]]
        observes += [frame(58471, 26.3, clear=True)]
    if late:
        observes[0] = frame(58396, 18.2, names=READY)
    if bad in ('unknown', 'ambiguous'):
        status = ResolutionStatus.UNKNOWN if bad == 'unknown' else ResolutionStatus.AMBIGUOUS
        observes[0] = frame(58396, 18.2, clear=True, status=status, base=None)
    if bad == 'foreign': observes[0] = frame(58396, 18.2, clear=True, base='screen.lobby')
    if bad == 'overlay': observes[0] = frame(58396, 18.2, overlays=(POPUP_MW_CLEAR, 'popup.foreign'))
    if bad == 'miss': observes[0] = frame(58396, 18.2, names=(MW_MAX,))
    if bad in ('stale', 'future', 'pre_input'):
        observes[0] = frame(58396, {'stale':14., 'future':20., 'pre_input':10.05}[bad], clear=True)
    if bad == 'old_sequence':
        observes[0] = frame(58312, 18.2, clear=True)
        waits[2:] = [[frame(58390, 18., clear=True)]]
    cancelled = [False]
    observer = Observer(waits, observes, cancelled)
    if bad == 'cancelled':
        original = observer.observe
        def cancelling_observe():
            s = original()
            cancelled[0] = True
            return s
        observer.observe = cancelling_observe
    actions, events = Actions(), Events()
    activity = MonsterWaveActivity(observer, actions, events,
                    clock=lambda: observer.now, cancel_requested=lambda: cancelled[0])
    return activity, before, observer, actions, events


@pytest.mark.parametrize('second_failure', [False, True])
def test_title_misses_do_not_complete_and_only_clear_ok_retries_once(second_failure):
    activity, before, observer, actions, events = setup(second_failure=second_failure)
    result = activity.finish_pass(before)
    assert result.status is (FlowStatus.FAILED if second_failure else FlowStatus.COMPLETED)
    assert result.transition_attempts == (('monster_wave.acknowledge_clear', 2, 2 if second_failure else 1),)
    assert [a for a, _ in actions.calls] == [AcknowledgeMonsterWaveClear()] * 2
    assert 58335 in observer.polls
    retries = [fields for name, fields in events.records if name == 'transition.retry']
    assert len(retries) == 1 and retries[0]['transition'] == 'monster_wave.acknowledge_clear'


def test_late_exposed_controls_complete_without_second_ack():
    activity, before, _, actions, _ = setup(late=True)
    result = activity.finish_pass(before)
    assert result.succeeded
    assert result.transition_attempts[0][1] == 1
    assert [a for a, _ in actions.calls] == [AcknowledgeMonsterWaveClear()]


def test_timer_expiry_still_verifies_exposed_screen_without_activation():
    activity, before, _, actions, _ = setup(needs=True)
    assert activity.finish_pass(before).succeeded
    assert [a for a, _ in actions.calls] == [AcknowledgeMonsterWaveClear()] * 2


@pytest.mark.parametrize('bad', ['unknown', 'ambiguous', 'foreign', 'overlay', 'miss',
                                 'stale', 'future', 'pre_input', 'old_sequence', 'cancelled'])
def test_retry_requires_positive_fresh_post_input_clear_and_no_cancellation(bad):
    activity, before, _, actions, _ = setup(bad=bad)
    result = activity.finish_pass(before)
    assert result.status is (FlowStatus.CANCELLED if bad == 'cancelled' else FlowStatus.FAILED)
    assert [a for a, _ in actions.calls] == [AcknowledgeMonsterWaveClear()]


def test_executor_failure_never_retries_ack():
    activity, before, _, actions, _ = setup()
    actions.error = RuntimeError('dispatch failed')
    assert activity.finish_pass(before).status is FlowStatus.FAILED
    assert [a for a, _ in actions.calls] == [AcknowledgeMonsterWaveClear()]


def test_normal_dismissal_still_uses_one_ack():
    activity, before, observer, actions, _ = setup()
    observer.waits = [[frame(58319, 10.7, names=READY), frame(58324, 11.3, names=READY)]]
    result = activity.finish_pass(before)
    assert result.succeeded
    assert result.transition_attempts == (('monster_wave.acknowledge_clear', 1, 0),)
    assert [a for a, _ in actions.calls] == [AcknowledgeMonsterWaveClear()]


def test_cancellation_before_ack_sends_no_input():
    activity, before, observer, actions, _ = setup()
    observer.cancelled[0] = True
    assert activity.finish_pass(before).status is FlowStatus.CANCELLED
    assert actions.calls == []


def test_uncertain_clear_close_never_repeats_skip_or_accounts_consumption():
    from tests.test_monster_wave import Device, ACTIVE
    class LostClearOk(Device):
        def execute(self, action, geometry):
            if isinstance(action, AcknowledgeMonsterWaveClear):
                self.intents.append(type(action).__name__)
                return  # CLEAR remains physically represented by the fixture.
            return super().execute(action, geometry)
    device = LostClearOk(ACTIVE)
    activity = device.activity()
    activity.clock = lambda: device.sequence + .1
    result = activity.run()
    assert result.status is FlowStatus.FAILED
    assert device.intents.count('StartMonsterWaveSkip') == 1
    assert device.intents.count('AcknowledgeMonsterWaveClear') == 2
    assert device.intents.count('SelectMonsterWaveMax') == 1
    assert 'ExitMonsterWave' not in device.intents
    assert result.sapphires_consumed == 0
