"""32cd6472: lost Battle tap after Socket relief must not repeat Back or SKIP."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from bot.flow_contracts import FlowStatus
from bot.monster_wave_actions import ExitMonsterWave
from bot.monster_wave_standalone import MonsterWaveStandaloneNavigationRuntime
from bot.runtime_observer import RuntimeWaitTimeout
from bot.semantic_actions import OpenBattleModeSelect
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransition, VerifiedTransitionOutcome
from tests.test_monster_wave_standalone import anchor, context
from tests.test_verified_transition import Actions, Events, ScriptedObserver


def setup(*, bad=None, second_failure=False, late_hub=False):
    lobby = context(30785, base='screen.lobby', timestamp=12.)
    nominal = context(30848, base='screen.lobby', timestamp=18.)
    grace = context(30873, base='screen.lobby', timestamp=20.)
    fresh = context(30879, base='screen.lobby', timestamp=20.1)
    hub = context(30885, base='screen.battle_mode_select', timestamp=20.7)
    if bad in ('unknown', 'ambiguous'):
        status = ResolutionStatus.UNKNOWN if bad == 'unknown' else ResolutionStatus.AMBIGUOUS
        fresh = replace(fresh, state=replace(fresh.state, status=status, base_context=None,
                          base_candidates=() if bad == 'unknown' else ('screen.lobby', 'screen.socket')))
    if bad == 'foreign': fresh = context(30879, base='screen.socket', timestamp=20.1)
    if bad == 'overlay': fresh = replace(fresh, state=replace(fresh.state, overlays=('popup.foreign',)))
    if bad in ('stale', 'future', 'pre_input'):
        fresh = context(30879, base='screen.lobby', timestamp={'stale':16., 'future':22., 'pre_input':12.1}[bad])
    if bad == 'old_sequence': fresh = context(30785, base='screen.lobby', timestamp=20.1)
    if late_hub: fresh = context(30879, base='screen.battle_mode_select', timestamp=20.1)
    def timeout(after, last, seconds=6.):
        return RuntimeWaitTimeout(after_sequence=after, last_snapshot=last, timeout=seconds)
    waits = [lobby, timeout(lobby.sequence, nominal), timeout(nominal.sequence, grace, 2.), hub]
    observes = [fresh]
    if bad == 'old_sequence': waits[-1] = timeout(grace.sequence, grace, 2.)
    if second_failure:
        last = context(30899, base='screen.lobby', timestamp=26.)
        final = context(30920, base='screen.lobby', timestamp=28.)
        waits[-1:] = [timeout(fresh.sequence, last), timeout(last.sequence, final, 2.)]
        observes += [context(30921, base='screen.lobby', timestamp=28.1)]
    cancelled = [False]
    class TimedObserver(ScriptedObserver):
        now = 10.1
        def wait_until(self, *args, **kwargs):
            try:
                result = super().wait_until(*args, **kwargs)
            except RuntimeWaitTimeout as error:
                self.now = error.last_snapshot.timestamp + .1
                raise
            self.now = result.timestamp + .1
            return result
        def observe(self):
            self.now += .1
            if bad == 'cancelled': cancelled[0] = True
            return super().observe()
    observer = TimedObserver(waits, observes=observes)
    actions, events = Actions(), Events()
    transition = VerifiedTransition(observer, actions, events)
    snapshots = SimpleNamespace(acquire=lambda **_: SimpleNamespace(status=FlowStatus.COMPLETED,
                                                                    fresh=anchor(30765)))
    navigation = MonsterWaveStandaloneNavigationRuntime(transition, snapshots,
                           clock=lambda: observer.now, cancel_requested=lambda: cancelled[0])
    return navigation, actions, events


@pytest.mark.parametrize('second_failure', [False, True])
def test_only_battle_tap_retries_once_and_second_miss_is_terminal(second_failure):
    nav, actions, events = setup(second_failure=second_failure)
    status, result = nav.exit_to_battle_mode(anchor(30760))
    assert status is (FlowStatus.FAILED if second_failure else FlowStatus.COMPLETED)
    assert result.attempt_count == 2
    assert result.outcome is (VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED if second_failure
                              else VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY)
    assert [a for a, _ in actions.calls] == [ExitMonsterWave(), OpenBattleModeSelect(), OpenBattleModeSelect()]
    retries = [fields for name, fields in events.records if name == 'transition.retry']
    assert len(retries) == 1 and retries[0]['transition'].endswith('open_hub_from_lobby')


def test_hub_appearing_after_grace_continues_without_second_battle_tap():
    nav, actions, _ = setup(late_hub=True)
    status, result = nav.exit_to_battle_mode(anchor(30760))
    assert status is FlowStatus.COMPLETED and result.attempt_count == 1
    assert [a for a, _ in actions.calls] == [ExitMonsterWave(), OpenBattleModeSelect()]


@pytest.mark.parametrize('bad', ['unknown', 'ambiguous', 'foreign', 'overlay', 'stale',
                                 'future', 'pre_input', 'old_sequence', 'cancelled'])
def test_second_input_needs_fresh_post_input_lobby_and_no_cancellation(bad):
    nav, actions, _ = setup(bad=bad)
    status, _ = nav.exit_to_battle_mode(anchor(30760))
    assert status is (FlowStatus.CANCELLED if bad == 'cancelled' else FlowStatus.FAILED)
    assert [a for a, _ in actions.calls] == [ExitMonsterWave(), OpenBattleModeSelect()]


def test_cancellation_during_anchor_refresh_prevents_back():
    nav, actions, _ = setup()
    cancelled = [False]
    nav.cancel_requested = lambda: cancelled[0]
    acquire = nav.snapshots.acquire
    def cancelling_acquire(**kwargs):
        result = acquire(**kwargs)
        cancelled[0] = True
        return result
    nav.snapshots.acquire = cancelling_acquire
    status, _ = nav.exit_to_battle_mode(anchor(30760))
    assert status is FlowStatus.CANCELLED
    assert actions.calls == []


def test_cancellation_during_direct_hub_return_does_not_complete():
    nav, actions, _ = setup()
    cancelled = [False]
    nav.cancel_requested = lambda: cancelled[0]
    observer = nav.transition.observer
    observer.waits = [context(30785, base='screen.battle_mode_select', timestamp=12.)]
    wait = observer.wait_until
    def cancelling_wait(*args, **kwargs):
        result = wait(*args, **kwargs)
        cancelled[0] = True
        return result
    observer.wait_until = cancelling_wait
    status, _ = nav.exit_to_battle_mode(anchor(30760))
    assert status is FlowStatus.CANCELLED
    assert [a for a, _ in actions.calls] == [ExitMonsterWave()]
