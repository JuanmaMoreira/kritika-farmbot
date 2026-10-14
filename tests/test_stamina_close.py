"""Lost Trading X after Stamina purchase must never repeat the payment."""
from copy import deepcopy
from types import SimpleNamespace as S

import pytest

from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import CloseTrading, ConfirmTradingTrade
from bot.stages_runtime import lobby
from bot.state import ResolutionStatus
from tests.test_stamina_batch import purchase


@pytest.mark.parametrize('second_failure', [False, True])
def test_lost_close_retries_once_without_repeating_stamina_purchase(second_failure):
    op, before, after, actions, _ = purchase(294)
    nav = op.nav
    original_act, original_wait = nav.act, nav.wait
    closes = 0

    def act(action, snapshot):
        nonlocal closes
        original_act(action, snapshot)
        nav.cursor, nav.dispatched_at = snapshot.sequence, 8.
        if isinstance(action, CloseTrading):
            closes += 1
            if closes == 1 or second_failure:
                before.snapshot.state.base_context = 'screen.trading'

    def wait(predicate):
        if predicate is lobby and before.snapshot.state.base_context == 'screen.trading':
            last = deepcopy(before.snapshot)
            last.sequence, last.timestamp = nav.cursor + 1, 9.5
            raise RuntimeWaitTimeout(after_sequence=nav.cursor, timeout=6., last_snapshot=last)
        return original_wait(predicate)

    nav.act, nav.wait = act, wait
    if second_failure:
        with pytest.raises(RuntimeWaitTimeout):
            op.ensure(before)
    else:
        assert op.ensure(before) is after
    assert closes == 2
    assert sum(isinstance(a, ConfirmTradingTrade) for a in actions) == 1


@pytest.mark.parametrize('bad', [
    'unknown', 'ambiguous', 'foreign', 'overlay', 'old_sequence', 'before_input',
    'stale', 'future', 'missing_currency', 'missing_row', 'item_trade', 'item_trade_partial', 'missing',
])
def test_close_retry_requires_fresh_post_input_exposed_currency(bad):
    op, before, _, actions, _ = purchase(294)
    last = S(sequence=9, timestamp=9.5,
        state=S(status=ResolutionStatus.RESOLVED, base_context='screen.trading', overlays=()),
        flags={'currency', 'stamina_row'})
    last.frame = S(image=last)
    if bad == 'unknown': last.state.status = ResolutionStatus.UNKNOWN
    if bad == 'ambiguous': last.state.status = ResolutionStatus.AMBIGUOUS
    if bad == 'foreign': last.state.base_context = 'screen.craft'
    if bad == 'overlay': last.state.overlays = ('popup.trading_item_trade',)
    if bad == 'old_sequence': last.sequence = 4
    if bad == 'before_input': last.timestamp = 8.
    if bad == 'stale': last.timestamp = 7.
    if bad == 'future': last.timestamp = 11.
    if bad == 'missing_currency': last.flags.remove('currency')
    if bad == 'missing_row': last.flags.remove('stamina_row')
    if bad == 'item_trade': last.flags |= {'stamina_panel', 'kcoin'}
    if bad == 'item_trade_partial': last.flags.add('stamina_panel')
    if bad == 'missing': last = None
    op.nav.cursor, op.nav.dispatched_at = 4, 8.

    def wait(predicate):
        raise RuntimeWaitTimeout(after_sequence=4, timeout=6., last_snapshot=last)

    op.nav.wait = wait
    with pytest.raises(RuntimeWaitTimeout):
        op._close_to_lobby(before.snapshot)
    assert len(actions) == 1 and isinstance(actions[0], CloseTrading)


def test_cancelled_close_does_not_retry():
    op, before, _, actions, _ = purchase(294)

    def wait(predicate):
        raise RuntimeWaitCancelled('stop')

    op.nav.wait = wait
    with pytest.raises(RuntimeWaitCancelled):
        op._close_to_lobby(before.snapshot)
    assert len(actions) == 1 and isinstance(actions[0], CloseTrading)
