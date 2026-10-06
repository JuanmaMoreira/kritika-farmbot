"""USER_GT: short ads are real; strong terminal evidence has no minimum age.

These tests protect terminal authority and time bounds, without hardware.
"""
from types import SimpleNamespace as S
import time

import pytest

from bot.ads_manager import AdObservation, AdsManager, AdsOutcome, AndroidAdsObserver


class Clock:
    now = 0.

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.mark.parametrize('authority', ['reward_granted', 'strong_chrome_close'])
@pytest.mark.parametrize('terminal_at', [5., 8., 12.])
def test_strong_terminal_authority_acts_immediately_even_in_short_ad(authority, terminal_at):
    clock = Clock()
    inputs = []

    def observe():
        if inputs:
            return AdObservation(clock.now, game_present=True, returned=True)
        terminal = clock.now >= terminal_at
        return AdObservation(clock.now, active=True,
            back_ready=terminal and authority == 'reward_granted',
            close_point=(.95,.05) if terminal and authority == 'strong_chrome_close' else None,
            close_key=authority if terminal else None)

    manager = AdsManager(observe,
        lambda snapshot, point: inputs.append(('close', clock.now)),
        lambda snapshot: pytest.fail('ticket input'),
        lambda snapshot: inputs.append(('back', clock.now)),
        clock=clock, sleeper=clock.sleep)
    result = manager.complete_requested_launch()
    assert result.outcome is AdsOutcome.RETURNED
    assert inputs == [('back' if authority == 'reward_granted' else 'close', terminal_at)]
    assert result.elapsed_seconds <= terminal_at + manager.poll_interval


def test_five_seconds_without_terminal_continues_observing_without_input():
    clock = Clock()
    observed = []

    def observe():
        observed.append(clock.now)
        return AdObservation(clock.now, active=True)

    manager = AdsManager(observe, lambda *args: pytest.fail('uncredited close'),
        lambda *args: pytest.fail('ticket'), lambda *args: pytest.fail('early Back'),
        clock=clock, sleeper=clock.sleep, cancel_requested=lambda: clock.now >= 10.)
    assert manager.complete_requested_launch().outcome is AdsOutcome.CANCELLED
    assert 5. in observed and max(observed) > 5.


def test_content_or_unaccredited_x_is_not_a_terminal_authority():
    snapshot = S(timestamp=time.monotonic(), frame=S(image=None))
    package = 'game.package'
    activity = 'com.google.android.gms.ads.AdActivity'
    # Only the acquired chrome detector can publish terminal authority; content
    # remains opaque even while Android positively owns the ad activity.
    def shell(*args):
        label = 'topResumedActivity=ActivityRecord{a u0 ' if args[1]=='activity' else 'mCurrentFocus=Window{a u0 '
        return S(stdout=label+package+'/'+activity+'}')

    observer = AndroidAdsObserver(S(observe=lambda:snapshot), S(shell=shell), package,
        S(present=lambda frame, name:False), returned=lambda s:False,
        unavailable=lambda s:False, skip_ticket=lambda s:False, game_visible=lambda s:False)
    result = observer()
    assert result.active and not result.back_ready
    assert result.close_point is None and result.close_key is None


def test_early_multipart_reset_and_missing_bar_are_not_terminal():
    clock = Clock()
    inputs = []

    def observe():
        if inputs:
            return AdObservation(clock.now, game_present=True, returned=True)
        # First part ends at 5 s, then bar is absent before the next part resets.
        progress = clock.now/6 if clock.now<5 else None if clock.now<7 else (clock.now-7)/6
        return AdObservation(clock.now, active=True, progress=progress,
            back_ready=clock.now >= 12., close_key='reward_granted' if clock.now>=12 else None)

    manager = AdsManager(observe, lambda *args:pytest.fail('content tap'),
        lambda *args:pytest.fail('ticket'), lambda snapshot:inputs.append(clock.now),
        clock=clock, sleeper=clock.sleep)
    assert manager.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert inputs == [12.]


def test_sdk_progress_past_sixty_seconds_does_not_force_global_timeout():
    clock = Clock()
    inputs = []

    def observe():
        if inputs:
            return AdObservation(clock.now, game_present=True, returned=True)
        return AdObservation(clock.now, active=True, progress=(clock.now % 20)/20,
            back_ready=clock.now >= 75.)

    manager = AdsManager(observe, lambda *args:pytest.fail('content tap'),
        lambda *args:pytest.fail('ticket'), lambda snapshot:inputs.append(clock.now),
        clock=clock, sleeper=clock.sleep)
    assert manager.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert inputs == [75.]


@pytest.mark.parametrize('terminal', [False, True])
def test_absolute_bound_never_closes_without_reward_authority(terminal):
    clock = Clock()
    inputs = []
    def observe():
        if inputs:
            return AdObservation(clock.now, game_present=True, returned=True)
        return AdObservation(clock.now, active=True, progress=(clock.now % 4)/4,
            close_point=(.922,.059) if terminal and clock.now >= 180. else None,
            close_key='sdk_round_close' if terminal and clock.now >= 180. else None)
    manager = AdsManager(observe, lambda snapshot, point: inputs.append(clock.now),
        lambda *args:pytest.fail('ticket'), lambda *args:pytest.fail('uncredited Back'),
        clock=clock, sleeper=clock.sleep)
    result = manager.complete_requested_launch()
    assert result.outcome is (AdsOutcome.RETURNED if terminal else AdsOutcome.RECOVERY_FAILED)
    assert inputs == ([180.] if terminal else [])
    assert result.elapsed_seconds <= 180.5
