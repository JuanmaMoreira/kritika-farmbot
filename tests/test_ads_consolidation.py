"""Ads cancellation and reward proof across the existing Stages caller."""
from types import SimpleNamespace as S

import pytest

from bot.ads_manager import AdObservation, AdsManager, AdsOutcome
from bot.flow_contracts import FlowStatus
from bot.stages_actions import StageControl
from tests.test_ads_sdk_round import observe
from tests.test_ads_reward_pill import frame as right_pill
from tests.test_ads_reward_left_pill import frame as left_pill
from tests.test_stages_daily import Clock, balance, flow


@pytest.mark.parametrize('authority', [
    {'active': True, 'back_ready': True},
    {'active': True, 'close_point': (.922, .059), 'close_key': 'sdk_round_close'},
    {'external': True},
    {'skip_ticket': True},
])
@pytest.mark.parametrize('recovery', [False, True])
def test_cancellation_during_observation_prevents_input(authority, recovery):
    clock = Clock()
    cancelled = [False]
    calls = []
    observed = []
    def current():
        observed.append(clock.now)
        if recovery and len(observed) == 1:
            clock.now = 180.
            return AdObservation(clock.now, active=True)
        cancelled[0] = True
        return AdObservation(clock.now, **authority)
    manager = AdsManager(current, lambda *a:calls.append('close'),
        lambda *a:calls.append('ticket'), lambda *a:calls.append('back'),
        clock=clock, sleeper=clock.sleep, cancel_requested=lambda:cancelled[0])
    assert manager.complete_requested_launch().outcome is AdsOutcome.CANCELLED
    assert calls == []


@pytest.mark.parametrize('pill', [right_pill, left_pill])
@pytest.mark.parametrize('effect', [0, 378])
def test_pill_close_and_results_require_caller_effect_without_relaunch(pill, effect):
    terminal = observe(pill())
    clock = Clock()
    backs = []
    def current():
        if backs:
            return AdObservation(S(sequence=2), game_present=True, returned=True)
        return terminal
    manager = AdsManager(current, lambda *a:pytest.fail('creative tap'),
        lambda *a:pytest.fail('ticket'), lambda s:backs.append(clock.now),
        clock=clock, sleeper=clock.sleep)
    caller, nav, resets = flow([balance(), balance(), balance(effect)], [])
    caller.ads = manager
    result = caller.run()
    assert result.status is (FlowStatus.COMPLETED if effect else FlowStatus.FAILED)
    assert nav.calls.count(StageControl.VIDEO) == nav.calls.count('ack') == 1
    assert backs == [0.] and not resets
    assert bool(result.events) == bool(effect)


@pytest.mark.parametrize('pill', [right_pill, left_pill])
def test_pill_disappearing_to_unknown_never_repeats_back_or_claims_return(pill):
    terminal = observe(pill())
    clock = Clock()
    backs = []
    def current():
        return AdObservation(clock.now) if backs else terminal
    manager = AdsManager(current, lambda *a:pytest.fail('creative tap'),
        lambda *a:pytest.fail('ticket'), lambda s:backs.append(clock.now),
        clock=clock, sleeper=clock.sleep)
    assert manager.complete_requested_launch().outcome is AdsOutcome.RECOVERY_FAILED
    assert backs == [0.]
