"""The generation caller requests one MW pass, independent of pressure102."""
from types import SimpleNamespace as NS
import pytest
from bot.flow_contracts import FlowStatus as S, FlowEvent
from bot.monster_wave_activity import MonsterWaveResult
from bot.monster_wave_flow import MonsterWaveFlow
from test_monster_wave_productive import _Harness, _context


def generation(before=100, after=0, first=None):
    clear = MonsterWaveResult(S.COMPLETED, events=(FlowEvent('monster_wave.completed'),))
    harness = _Harness(first=first or clear)
    flow = harness.flow(); gates = []
    flow.inner.entry_readiness = lambda **kw: gates.append(('readiness', kw['pressure_relief']))
    flow.zone.enter = lambda: MonsterWaveResult(S.COMPLETED)
    def prepare(**kw):
        gates.append(('prepare', kw['pressure_relief']))
        return MonsterWaveResult(S.COMPLETED, sapphires_initial=before)
    flow.activity.prepare = prepare
    flow.activity.cancel_requested = lambda: False
    flow.activity.observer = NS(observe=lambda: _context(100))
    def refresh(): gates.append(('refresh',)); return NS(value=after, sequence=100)
    flow.activity.read_sapphires_after_clear = refresh
    return flow, harness, gates


@pytest.mark.parametrize('before,after', [(100, 0), (101, 1), (102, 2), (250, 150)])
def test_one_pass_at_threshold_or_large_balance_never_drains_pressure(before, after):
    flow, harness, gates = generation(before, after)
    r = flow.run_resource_pass()
    assert r.succeeded and r.sapphires_consumed == before - after
    assert gates == [('readiness', False), ('prepare', False), ('refresh',)]
    assert [c for c in harness.calls if c[0] == 'pass'] == [('pass', True, False)]
    assert r.final_snapshot.state.base_context == 'screen.monster_wave'


@pytest.mark.parametrize('after', [100, 101])
def test_no_verified_consumption_is_technical_stop_without_second_pass(after):
    flow, harness, _ = generation(after=after)
    r = flow.run_resource_pass()
    assert r.status is S.FAILED and r.error == 'mw_pass_without_verified_sapphire_consumption'
    assert len([c for c in harness.calls if c[0] == 'pass']) == 1


@pytest.mark.parametrize('status', [S.FAILED, S.MANUAL_RESOLUTION, S.CANCELLED])
def test_subordinate_stop_never_refreshes_or_repeats(status):
    events = (FlowEvent('monster_wave.manual_resolution', fields={'blocker': 'popup.socket_inventory_full'}),) if status is S.MANUAL_RESOLUTION else ()
    flow, harness, gates = generation(first=MonsterWaveResult(status, events=events,
        error='stop' if status is S.FAILED else None))
    r = flow.run_resource_pass()
    assert r.status is status and ('refresh',) not in gates
    assert len([c for c in harness.calls if c[0] == 'pass']) == 1


def test_normal_mw_keeps_pressure_gate_and_bare_reuses_one_operation():
    flow, harness, gates = generation()
    flow.entry_readiness = lambda: MonsterWaveResult(S.COMPLETED,
        events=(FlowEvent('monster_wave.no_work'),))
    assert flow.run().event_count('monster_wave.no_work') == 1 and not harness.calls and not gates
    bare = MonsterWaveFlow.__new__(MonsterWaveFlow); calls = []
    result = MonsterWaveResult(S.COMPLETED)
    bare.run = lambda: calls.append('run') or result
    assert bare.run_resource_pass() is result and calls == ['run']
