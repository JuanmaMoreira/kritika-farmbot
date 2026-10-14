"""bf1f0b48: a lost Character Mail tab tap cannot repeat mail operations."""
from dataclasses import replace

import pytest

from bot.catalog import MODE_MAILBOX_CHARACTER_MAIL, SCREEN_LOBBY, SCREEN_MAILBOX, STATUS_MAILBOX_CLAIMABLE
from bot.flow_contracts import FlowStatus
from bot.mailbox_flow import MailboxFlow
from bot.runtime_observer import RuntimeWaitTimeout
from bot.semantic_actions import ClaimAllCharacterMail, CloseMailbox, OpenMailbox, SelectCharacterMail
from bot.state import ResolutionStatus
from tests.test_mailbox_flow import Actions, Events, ScriptedObserver, snapshot


def selection(*, fresh=None, second_failure=False, cancel_requested=lambda: False):
    account = snapshot(2815, 1., base=SCREEN_MAILBOX)
    retained = snapshot(2877, 7., base=SCREEN_MAILBOX)
    fresh = fresh or snapshot(2878, 7.2, base=SCREEN_MAILBOX)
    character = snapshot(2879, 7.4, base=SCREEN_MAILBOX,
                         overlays=(MODE_MAILBOX_CHARACTER_MAIL,))
    timeout = RuntimeWaitTimeout(after_sequence=2815, timeout=6., last_snapshot=retained)
    scripts = [timeout, [fresh], [character]]
    if second_failure:
        scripts[-1] = RuntimeWaitTimeout(after_sequence=fresh.sequence, timeout=6.,
                                        last_snapshot=retained)
    observer = ScriptedObserver(account, scripts)
    actions, events = Actions(), Events()
    times = iter((1.5, 7.3))
    flow = MailboxFlow(observer, actions, events, navigation_stable_for=0.,
                       cancel_requested=cancel_requested, clock=lambda: next(times))
    return flow, account, actions, events, observer


@pytest.mark.parametrize('second_failure', [False, True])
def test_lost_tab_tap_has_only_one_retry(second_failure):
    flow, account, actions, events, observer = selection(second_failure=second_failure)
    if second_failure:
        with pytest.raises(RuntimeWaitTimeout):
            flow._select_character_mail(account)
    else:
        assert flow._select_character_mail(account).sequence == 2879
    assert actions.items == [SelectCharacterMail(), SelectCharacterMail()]
    assert observer.calls[1].after_sequence == 2877
    assert observer.calls[2].after_sequence == 2878
    assert ('mailbox.character_mail_retry', {'source_sequence': 2878}) in events.items


def test_late_character_mail_needs_no_retry():
    fresh = snapshot(2878, 7.2, base=SCREEN_MAILBOX,
                     overlays=(MODE_MAILBOX_CHARACTER_MAIL,))
    flow, account, actions, events, _ = selection(fresh=fresh)
    assert flow._select_character_mail(account) is fresh
    assert actions.items == [SelectCharacterMail()]
    assert not events.items


@pytest.mark.parametrize('bad', ['unknown', 'ambiguous', 'foreign', 'overlay',
                                 'processing', 'stale', 'future', 'pre_input'])
def test_retry_requires_fresh_exposed_idle_mailbox(bad):
    options = dict(base=SCREEN_MAILBOX)
    timestamp = 7.2
    if bad == 'unknown': options.update(base=None)
    if bad == 'ambiguous': options.update(base=None)
    if bad == 'foreign': options.update(base=SCREEN_LOBBY)
    if bad == 'overlay': options.update(overlays=('popup.foreign',))
    if bad == 'processing': options.update(activity=True)
    if bad == 'stale': timestamp = 4.
    if bad == 'future': timestamp = 8.
    if bad == 'pre_input': timestamp = 1.5
    fresh = snapshot(2878, timestamp, **options)
    if bad == 'ambiguous':
        fresh = replace(fresh, state=replace(fresh.state, status=ResolutionStatus.AMBIGUOUS,
                                            base_candidates=(SCREEN_LOBBY, SCREEN_MAILBOX)))
    flow, account, actions, _, _ = selection(fresh=fresh)
    with pytest.raises((RuntimeWaitTimeout, RuntimeError)):
        flow._select_character_mail(account)
    assert actions.items == [SelectCharacterMail()]


def test_cached_retry_frame_before_wait_barrier_cannot_authorize_input():
    flow, account, actions, _, observer = selection()
    original_wait = observer.wait_until
    calls = 0
    def wait(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            return snapshot(2877, 7.2, base=SCREEN_MAILBOX)
        return original_wait(*args, **kwargs)
    observer.wait_until = wait
    with pytest.raises(RuntimeWaitTimeout):
        flow._select_character_mail(account)
    assert actions.items == [SelectCharacterMail()]


@pytest.mark.parametrize('cancel_at', [2, 3])
def test_cancel_during_reacquisition_or_before_retry_blocks_input(cancel_at):
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        return checks >= cancel_at
    flow, account, actions, _, _ = selection(cancel_requested=cancel)
    with pytest.raises(RuntimeError):
        flow._select_character_mail(account)
    assert actions.items == [SelectCharacterMail()]


@pytest.mark.parametrize('claimable', [False, True])
@pytest.mark.parametrize('in_session', [False, True])
def test_full_flow_continues_after_lost_tab_without_repeating_mail_operations(claimable, in_session):
    lobby = snapshot(1, 0., base=SCREEN_LOBBY)
    account = snapshot(2, 1., base=SCREEN_MAILBOX)
    retained = snapshot(3, 7., base=SCREEN_MAILBOX)
    fresh = snapshot(4, 7.2, base=SCREEN_MAILBOX)
    overlays = (MODE_MAILBOX_CHARACTER_MAIL, STATUS_MAILBOX_CLAIMABLE) if claimable else (MODE_MAILBOX_CHARACTER_MAIL,)
    character = snapshot(5, 7.4, base=SCREEN_MAILBOX, overlays=overlays)
    returned = snapshot(9, 9.1, base=SCREEN_LOBBY)
    timeout = RuntimeWaitTimeout(after_sequence=2, timeout=6., last_snapshot=retained)
    scripts = [[account], timeout, [fresh], [character]]
    if claimable:
        idle = snapshot(6, 7.6, base=SCREEN_MAILBOX, overlays=overlays)
        onset = RuntimeWaitTimeout(after_sequence=5, timeout=2., last_snapshot=idle)
        scripts += [onset, [snapshot(7, 8.1, base=SCREEN_MAILBOX, overlays=overlays),
                            snapshot(8, 8.9, base=SCREEN_MAILBOX, overlays=overlays)]]
    scripts += [[returned]]
    observer = ScriptedObserver(lobby, scripts)
    actions = Actions()
    times = iter((1.5, 7.3))
    operation = MailboxFlow(observer, actions, Events(), navigation_stable_for=0.,
                            clock=lambda: next(times))
    if in_session:
        from tests.test_session import Flow, Rotation, _runner
        from bot.flow_contracts import FlowResult
        from bot.session import SessionStatus
        trace = []
        following = Flow('following', [FlowResult(FlowStatus.COMPLETED)], trace)
        runner, _ = _runner(1, [operation, following], Rotation(1, trace))
        session = runner.run()
        assert session.status is SessionStatus.COMPLETED
        assert 'following.run' in trace
        result = session.character_results[0].flow_results[0]
    else:
        result = operation.run()
    assert result.status is FlowStatus.COMPLETED
    assert result.no_op is (not claimable)
    expected = [OpenMailbox(), SelectCharacterMail(), SelectCharacterMail()]
    if claimable:
        expected += [ClaimAllCharacterMail()]
        assert result.claim_all_no_effect and result.claims_leftover
    assert actions.items == expected + [CloseMailbox()]
