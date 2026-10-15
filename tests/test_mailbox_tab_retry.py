"""bf1f0b48: a lost Character Mail tab tap cannot repeat mail operations."""
from dataclasses import replace

import pytest

from bot.catalog import MODE_MAILBOX_CHARACTER_MAIL, SCREEN_LOBBY, SCREEN_MAILBOX, STATUS_MAILBOX_CLAIMABLE
from bot.flow_contracts import FlowStatus
from bot.mailbox_flow import (
    MailboxFlow, _is_character_mail, _is_mailbox,
    _has_claim_processing_activity, _has_incompatible_character_mail_entry,
)
from bot.operation_control import OperationControl, control_scope
from bot.runtime_observer import RuntimeWaitTimeout, RuntimeWaitCancelled
from bot.semantic_actions import (
    ClaimAllCharacterMail, CloseMailbox, DeleteReadCharacterMail,
    OpenMailbox, SelectCharacterMail,
)
from bot.state import ResolutionStatus
from tests.test_mailbox_flow import Actions, Events, ScriptedObserver, snapshot


class ClockedObserver(ScriptedObserver):
    """Deliver scripted frames on a monotonic simulation, independent of age."""

    now = 1.5

    def __init__(self, *args):
        super().__init__(*args)
        self.seen = []
        self.observe_count = 0

    def observe(self):
        self.observe_count += 1
        return super().observe()

    def wait_until(self, condition, **kwargs):
        abort = kwargs.get('abort_if')
        def tracked(item):
            self.seen.append(item.sequence)
            return abort(item) if abort else False
        kwargs['abort_if'] = tracked
        try:
            item = super().wait_until(condition, **kwargs)
        except RuntimeWaitTimeout:
            self.now += kwargs['timeout']
            raise
        self.now += .1
        return item


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
    observer = ClockedObserver(account, scripts)
    actions, events = Actions(), Events()
    flow = MailboxFlow(observer, actions, events, navigation_stable_for=0.,
                       cancel_requested=cancel_requested, clock=lambda: observer.now)
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
    assert any(name == 'transition.retry' for name, _ in events.items)


def test_late_character_mail_needs_no_retry():
    fresh = snapshot(2878, 7.2, base=SCREEN_MAILBOX,
                     overlays=(MODE_MAILBOX_CHARACTER_MAIL,))
    flow, account, actions, events, _ = selection(fresh=fresh)
    assert flow._select_character_mail(account) is fresh
    assert actions.items == [SelectCharacterMail()]
    assert not any(name == 'transition.retry' for name, _ in events.items)


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


@pytest.mark.parametrize('cancel_at', ['reacquisition', 'retry'])
def test_cancel_during_reacquisition_or_before_retry_blocks_input(cancel_at):
    def cancel():
        return observer.now >= (7.5 if cancel_at == 'reacquisition' else 7.6)
    flow, account, actions, _, _ = selection(cancel_requested=cancel)
    observer = flow.claim_observer
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
    observer = ClockedObserver(lobby, scripts)
    actions = Actions()
    operation = MailboxFlow(observer, actions, Events(), navigation_stable_for=0.,
                            clock=lambda: observer.now)
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


def baseline_select(flow, mailbox):
    """Frozen selection algorithm from 0f85057, solely a comparison oracle."""
    started = flow.clock()
    for attempt in range(2):
        try:
            return flow._act_and_wait(
                SelectCharacterMail(), mailbox, expected=_is_character_mail,
                abort_if=_has_incompatible_character_mail_entry,
                timeout=flow.navigation_timeout,
                stable_for=flow.navigation_stable_for, observer=flow.claim_observer,
            )
        except RuntimeWaitTimeout as error:
            if attempt:
                raise
            anchor = error.last_snapshot or mailbox
            barrier = max(mailbox.sequence, anchor.sequence)
            fresh = flow.claim_observer.wait_until(
                lambda s: _is_mailbox(s) and not _has_claim_processing_activity(s),
                after_sequence=barrier, timeout=flow.navigation_timeout,
                abort_if=_has_incompatible_character_mail_entry,
                cancel_requested=flow.cancel_requested,
                stable_for=flow.navigation_stable_for,
            )
            if (fresh.sequence <= barrier or fresh.timestamp <= started or
                    not 0 <= flow.clock() - fresh.timestamp <= 2.0):
                raise error
            if _is_character_mail(fresh):
                return fresh
            flow._record('mailbox.character_mail_retry', source_sequence=fresh.sequence)
            mailbox = fresh
    raise AssertionError('bounded Character Mail selection exhausted')


@pytest.mark.parametrize('scenario,inputs,terminal,waits,elapsed', [
    ('first', 1, 'ready', 1, .1),
    ('late', 1, 'ready', 2, 6.1),
    ('retry', 2, 'ready', 3, 6.2),
    ('second_miss', 2, 'timeout', 3, 12.1),
    ('unknown_transient', 2, 'ready', 3, 6.2),
    ('ambiguous_transient', 1, 'aborted', 2, 6.),
    ('stale_then_fresh', 1, 'timeout', 2, 6.1),
    ('lost_control', 1, 'aborted', 2, 6.),
    ('processing', 1, 'timeout', 2, 12.),
    ('cancel_before_retry', 1, 'cancelled', 2, 6.1),
])
def test_baseline_comparison_inputs_terminal_observations_and_latency(
    scenario, inputs, terminal, waits, elapsed,
):
    account = snapshot(1, 1., base=SCREEN_MAILBOX)
    retained = snapshot(2, 7., base=SCREEN_MAILBOX)
    fresh = snapshot(4, 7.2, base=SCREEN_MAILBOX)
    character = snapshot(5, 7.4, base=SCREEN_MAILBOX,
                         overlays=(MODE_MAILBOX_CHARACTER_MAIL,))
    unknown = snapshot(3, 7.1, base=None)
    timeout = RuntimeWaitTimeout(after_sequence=1, timeout=6., last_snapshot=retained)
    traces = []
    for migrated in (False, True):
        scripts = [timeout, [fresh], [character]]
        if scenario == 'first': scripts = [[character]]
        if scenario == 'late': scripts = [timeout, [character]]
        if scenario == 'second_miss':
            scripts[-1] = RuntimeWaitTimeout(after_sequence=4, timeout=6., last_snapshot=fresh)
        if scenario == 'unknown_transient': scripts[1] = [unknown, fresh]
        if scenario == 'ambiguous_transient':
            scripts[1] = [replace(unknown, state=replace(
                unknown.state, status=ResolutionStatus.AMBIGUOUS,
                base_candidates=(SCREEN_LOBBY, SCREEN_MAILBOX),
            )), fresh]
        if scenario == 'stale_then_fresh':
            scripts[1] = [snapshot(3, 4., base=SCREEN_MAILBOX), fresh]
        if scenario == 'lost_control':
            scripts[1] = [snapshot(3, 7.1, base=SCREEN_MAILBOX, overlays=('popup.foreign',)), fresh]
        if scenario == 'processing':
            scripts[1] = [snapshot(3, 7.1, base=SCREEN_MAILBOX, activity=True)]
        observer = ClockedObserver(account, scripts)
        actions = Actions()
        flow = MailboxFlow(
            observer, actions, Events(), navigation_stable_for=0., clock=lambda: observer.now,
            cancel_requested=lambda: scenario == 'cancel_before_retry' and observer.now >= 7.6,
        )
        try:
            result = flow._select_character_mail(account) if migrated else baseline_select(flow, account)
            outcome = 'ready'
            assert result is character
        except RuntimeWaitCancelled:
            outcome = 'cancelled'
        except RuntimeWaitTimeout:
            outcome = 'timeout'
        except RuntimeError:
            outcome = 'aborted'
        trace = (len(actions.items), outcome, observer.calls, observer.seen, observer.now - 1.5)
        assert trace[0:2] == (inputs, terminal)
        assert len(observer.calls) == waits
        assert observer.observe_count == 0
        assert trace[-1] == pytest.approx(elapsed)
        traces.append(trace)
    assert traces[0] == traces[1]


def test_source_rotation_invalidates_selection_before_any_replacement_authorization():
    flow, account, actions, _, observer = selection()
    rotated = snapshot(2878, 7.2, base=SCREEN_MAILBOX)
    rotated = replace(rotated, frame=replace(rotated.frame, source_id='replacement'))
    observer.scripts[1] = [rotated, snapshot(2879, 7.3, base=SCREEN_MAILBOX)]
    with pytest.raises(RuntimeError):
        flow._select_character_mail(account)
    assert actions.items == [SelectCharacterMail()]
    assert observer.seen == [2878]


def test_parent_deadline_prevents_retry_and_does_not_restart_budget():
    flow, account, actions, _, observer = selection()
    with control_scope(OperationControl(deadline=7.55, clock=lambda: observer.now)):
        with pytest.raises(RuntimeWaitTimeout):
            flow._select_character_mail(account)
    assert actions.items == [SelectCharacterMail()]
    assert [c.timeout for c in observer.calls] == pytest.approx([6., .05])


def test_stale_late_character_mail_cannot_continue_to_economic_actions():
    stale = snapshot(2878, 4., base=SCREEN_MAILBOX, overlays=(MODE_MAILBOX_CHARACTER_MAIL,))
    flow, account, actions, _, _ = selection(fresh=stale)
    with pytest.raises(RuntimeWaitTimeout):
        flow._select_character_mail(account)
    assert actions.items == [SelectCharacterMail()]


def test_retry_does_not_repeat_claim_or_delete_when_delete_has_no_effect():
    from bot.catalog import STATUS_MAILBOX_READ_MAIL_PRESENT
    lobby = snapshot(1, 0., base=SCREEN_LOBBY)
    account = snapshot(2, 1., base=SCREEN_MAILBOX)
    retained = snapshot(3, 7., base=SCREEN_MAILBOX)
    fresh = snapshot(4, 7.2, base=SCREEN_MAILBOX)
    character = snapshot(5, 7.4, base=SCREEN_MAILBOX, overlays=(
        MODE_MAILBOX_CHARACTER_MAIL, STATUS_MAILBOX_CLAIMABLE,
        STATUS_MAILBOX_READ_MAIL_PRESENT,
    ))
    observer = ClockedObserver(lobby, [
        [account], RuntimeWaitTimeout(after_sequence=2, timeout=6., last_snapshot=retained),
        [fresh], [character],
        RuntimeWaitTimeout(after_sequence=5, timeout=2., last_snapshot=character),
        [snapshot(6, 8., base=SCREEN_MAILBOX, overlays=character.state.overlays),
         snapshot(7, 8.8, base=SCREEN_MAILBOX, overlays=character.state.overlays)],
        RuntimeWaitTimeout(after_sequence=7, timeout=12., last_snapshot=character),
    ])
    actions = Actions()
    flow = MailboxFlow(observer, actions, Events(), navigation_stable_for=0., clock=lambda: observer.now)
    assert flow.run().status is FlowStatus.FAILED
    assert actions.items == [OpenMailbox(), SelectCharacterMail(), SelectCharacterMail(),
                             ClaimAllCharacterMail(), DeleteReadCharacterMail()]
