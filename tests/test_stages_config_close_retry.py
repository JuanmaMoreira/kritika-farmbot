"""ea2c845a: retry only the lost config X, never Results OK, Video or Start."""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from bot.observations import Observation, ObservationSource
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.stages_actions import StageControl as C
from bot.stages_runtime import StagesNavigation, lobby
from bot.state import ResolutionStatus
from tests.test_mailbox_flow import snapshot


def stage(sequence, timestamp, layer, *, base='screen.stages', status=None, extra=()):
    s = snapshot(sequence, timestamp, base=base,
                 overlays=('popup.stages_'+layer,) + extra if layer == 'config' else extra)
    observation = Observation('stages.surface', 1., ObservationSource.LOCAL_CV, value=layer)
    return replace(s, observations=replace(s.observations, observations=(observation,)),
                   state=replace(s.state, status=status or s.state.status,
                       base_candidates=('screen.stages', 'screen.lobby') if status is ResolutionStatus.AMBIGUOUS else ()))


def setup(*, bad=None, late=False, second_failure=False, cancel=False):
    results = stage(4175, 1., 'results')
    config = stage(4188, 1.4, 'config')
    retained = stage(4251, 7.8, 'config')
    fresh = stage(4252, 8.2, 'normal' if late else 'config')
    normal = stage(4256, 8.6, 'normal')
    done = snapshot(4260, 9., base='screen.lobby')
    if bad in ('unknown', 'ambiguous'):
        retained = stage(4251, 7.8, 'config', base=None,
                  status=ResolutionStatus.UNKNOWN if bad == 'unknown' else ResolutionStatus.AMBIGUOUS)
    if bad == 'foreign': retained = stage(4251, 7.8, 'config', base='screen.lobby')
    if bad == 'overlay': retained = stage(4251, 7.8, 'config', extra=('popup.foreign',))
    if bad == 'fresh_unknown': fresh = stage(4252, 8.2, 'config', base=None)
    if bad == 'fresh_overlay': fresh = stage(4252, 8.2, 'config', extra=('popup.foreign',))
    if bad == 'fresh_foreign': fresh = stage(4252, 8.2, 'config', base='screen.lobby')
    if bad in ('stale', 'future', 'pre_input', 'old_sequence'):
        retained = stage(4188 if bad == 'old_sequence' else 4251,
             {'stale':5., 'future':9., 'pre_input':1.5, 'old_sequence':7.8}[bad], 'config')
    timeout = RuntimeWaitTimeout(after_sequence=4188, timeout=6., last_snapshot=retained)
    if bad == 'missing': timeout.last_snapshot = None
    waits = [(results, 1.1), (config, 1.6), (timeout, 8.), (fresh, 8.3)]
    if not late:
        waits += [(RuntimeWaitTimeout(after_sequence=4252, timeout=6.,
                     last_snapshot=stage(4311, 14.2, 'config')), 14.3)] if second_failure else [(normal, 8.7)]
    waits += [(done, 9.1)]
    clock = NS(now=0., cancelled=False)
    calls, scopes, records = [], [], []
    class Observer:
        def wait_until(self, predicate, *, after_sequence, cancel_requested=None, **kwargs):
            value, clock.now = waits.pop(0)
            scopes.append(self)
            if isinstance(value, Exception): raise value
            assert value.sequence > after_sequence
            if not predicate(value):
                raise RuntimeWaitTimeout(after_sequence=after_sequence, timeout=kwargs['timeout'], last_snapshot=value)
            if cancel and value is fresh: clock.cancelled = True
            return value
    broad, narrow = Observer(), Observer()
    actions = NS(execute=lambda action, *a, **kw: calls.append(action.control))
    events = NS(record=lambda event, **fields: records.append((event, fields)))
    nav = StagesNavigation(broad, actions, events=events,
                clock=lambda: clock.now, cancel_requested=lambda: clock.cancelled)
    nav.results_observer = narrow
    return nav, calls, scopes, records, broad, narrow


@pytest.mark.parametrize('second_failure', [False, True])
def test_only_config_x_retries_once_and_lobby_verification_stays_broad(second_failure):
    nav, calls, scopes, records, broad, narrow = setup(second_failure=second_failure)
    if second_failure:
        with pytest.raises(RuntimeWaitTimeout): nav.acknowledge_results()
    else:
        assert lobby(nav.acknowledge_results())
        assert scopes[-1] is broad and all(s is narrow for s in scopes[:-1])
    assert calls == [C.RESULTS_OK, C.CLOSE_CONFIG, C.CLOSE_CONFIG] + ([] if second_failure else [C.BACK])
    retries = [fields for event, fields in records if event == 'stages.config_close.retry']
    assert retries == [dict(reason='fresh_config_no_effect', source_sequence=4252, input_retries=1)]


def test_late_close_continues_without_second_x():
    nav, calls, *_ = setup(late=True)
    assert lobby(nav.acknowledge_results())
    assert calls == [C.RESULTS_OK, C.CLOSE_CONFIG, C.BACK]


@pytest.mark.parametrize('bad', ['unknown', 'ambiguous', 'foreign', 'overlay', 'stale',
                                 'future', 'pre_input', 'old_sequence', 'missing',
                                 'fresh_unknown', 'fresh_overlay', 'fresh_foreign'])
def test_timeout_does_not_authorize_retry_without_positive_fresh_config(bad):
    nav, calls, *_ = setup(bad=bad)
    with pytest.raises(RuntimeWaitTimeout): nav.acknowledge_results()
    assert calls == [C.RESULTS_OK, C.CLOSE_CONFIG]


def test_cancel_between_readacquisition_and_second_x_stops_without_back():
    nav, calls, *_ = setup(cancel=True)
    with pytest.raises(RuntimeWaitCancelled): nav.acknowledge_results()
    assert calls == [C.RESULTS_OK, C.CLOSE_CONFIG]
