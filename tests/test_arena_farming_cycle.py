"""Resource routing, attribution, bounded repetition and Session contracts."""
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from bot.arena_config import ArenaConfig, ArenaMode as M
from bot.arena_farming_cycle import ArenaFarmingCycle, FarmingTermination as T
from bot.arena_farming_resources import ArenaFarmingResources
from bot.arena_flow import ArenaFlowResult
from bot.arena_semantics import ArenaDifficulty as D
from bot.flow_contracts import FlowResult, FlowStatus as S, FlowEvent
from bot.monster_wave_activity import MonsterWaveResult
from bot.manual_stages import ManualStagesResult,ManualStageOutcome
from test_arena_adaptive import batch


def resources(badges, sapphires, sequence=1):
    return ArenaFarmingResources(badges, sapphires, sequence, 100. + sequence, 'a' * 64)


class World:
    def __init__(self, balances, *, config=None, max_operations=32):
        self.balances = iter(balances); self.trace = []; self.sequence = 0; self.now = 100.
        self.cancel = False; self.arena_results = []; self.mw_results = []; self.manual_results = []
        self.cycle = ArenaFarmingCycle(self, self.arena, NS(run_resource_pass=self.mw), ensure_lobby=self.lobby,
            config=config or ArenaConfig(M.FARMING_CYCLE), clock=lambda: self.now,
            cancel_requested=lambda: self.cancel, max_operations=max_operations)
    def read(self):
        self.sequence += 1; self.now = 100. + self.sequence
        self.trace.append('read')
        value = next(self.balances)
        return resources(*value, self.sequence) if isinstance(value, tuple) else value
    def arena(self, difficulty):
        self.trace.append(difficulty)
        return NS(run=lambda: self.arena_results.pop(0)(difficulty))
    def mw(self):
        self.trace.append('mw'); return self.mw_results.pop(0)
    def manual(self):
        self.trace.append('manual'); return self.manual_results.pop(0)
    def lobby(self): self.trace.append('lobby')


def arena_result(used=40, won=40, run='arena'):
    return lambda d: ArenaFlowResult(S.COMPLETED, batch_result=batch(d, used, won, run), mode=M.AUTO_REPEAT)


def mw_result(completed=True):
    return MonsterWaveResult(S.COMPLETED, events=(FlowEvent('monster_wave.completed'),) if completed else ())


def test_report_instrumentation_uses_the_same_credited_batch_and_owner_duration():
    w = World([(80, 0), (0, 0)])
    w.arena_results = [lambda difficulty: replace(arena_result(80, 40, 'credited')(difficulty),
                                                metrics={'flow_wall_seconds': 12.5})]
    result = w.cycle.run()
    event = next(event for event in result.events if event.kind == 'arena.farming.difficulty')
    assert (event.fields['batch_id'], event.fields['operation_index'], event.fields['multiplier'],
            event.fields['duration']) == ('credited', 1, 8, 12.5)
    terminal = result.events[-1].fields
    assert result.duration == terminal['duration'] == 2
    assert terminal['manual_entries'] == terminal['monster_wave_passes'] == 0


@pytest.mark.parametrize('badges,sapphires,activity', [
    (40, 100, 'arena'), (41, 999, 'arena'), (39, 100, 'monster_wave'),
    (0, 101, 'monster_wave'), (39, 99, 'manual_stages'), (0, 0, 'manual_stages')])
def test_exact_routing_boundaries_and_arena_priority(badges, sapphires, activity):
    w = World([])
    assert w.cycle.activity(resources(badges, sapphires)) == activity


def test_initial_refresh_then_arena_mw_arena_and_pending_dependency():
    w = World([(40, 100), (0, 100), (40, 0), (0, 0)])
    w.arena_results = [arena_result(run='one'), arena_result(run='two')]
    w.mw_results = [mw_result()]
    r = w.cycle.run()
    assert r.succeeded and r.termination is T.MANUAL_STAGES_NOT_IMPLEMENTED
    assert w.trace == ['read', D.HARD, 'lobby', 'read', 'mw', 'lobby', 'read', D.HARD, 'lobby', 'read']
    assert len(r.operations) == 3 and r.resources.badges == 0
    assert r.event_count('arena.farming.resources') == 4
    mw_event = next(e for e in r.events if e.kind == 'monster_wave.completed')
    assert mw_event.fields['activity_id'] == 'monster_wave'
    assert mw_event.fields['attempt_index'] == 2 and mw_event.fields['activity_role'] == 'investment'


def test_manual_stages_seam_is_independent_and_only_both_insufficient():
    w = World([(0, 0), (0, 100), (40, 0), (0, 0)])
    w.cycle.manual_stages = NS(run=w.manual)
    w.manual_results = [ManualStagesResult(S.COMPLETED,stamina_consumed=60), ManualStagesResult(S.COMPLETED,
        events=(FlowEvent('manual_stages.no_productive_route'),))]
    w.mw_results = [mw_result()]; w.arena_results = [arena_result()]
    # Fourth operation has a fresh no-route observation.
    w.balances = iter([(0, 0), (0, 100), (40, 0), (0, 0), (0, 0)])
    r = w.cycle.run()
    assert r.termination is T.NO_PRODUCTIVE_ROUTE
    assert w.trace.count('manual') == 2
    assert [e.fields['activity'] for e in r.events if e.kind == 'arena.farming.routing'] == [
        'manual_stages', 'monster_wave', 'arena', 'manual_stages']

@pytest.mark.parametrize('outcome,termination', [('stamina_insufficient',T.STAMINA_INSUFFICIENT),
    ('sapphire_capacity_full',T.SAPPHIRE_CAPACITY_FULL),
    ('defeated',T.MANUAL_STAGE_DEFEATED),('no_progress',T.NO_PROGRESS)])
def test_typed_manual_functional_end_never_retries(outcome,termination):
    from bot.manual_stages import ManualStagesResult,ManualStageOutcome
    w=World([(0,0),(0,0)])
    w.cycle.manual_stages=NS(run=w.manual)
    w.manual_results=[ManualStagesResult(S.COMPLETED,outcome=ManualStageOutcome(outcome))]
    r=w.cycle.run()
    assert r.succeeded and r.termination is termination and w.trace.count('manual')==1

def test_manual_badge_gain_without_sapphires_is_not_generation_progress():
    w=World([(0,0),(39,0)])
    w.cycle.manual_stages=NS(run=w.manual);w.manual_results=[ManualStagesResult(S.COMPLETED,stamina_consumed=60)]
    assert w.cycle.run().termination is T.NO_PROGRESS

def test_manual_functional_stop_continues_session_before_meteorites_cleanup():
    from test_meteorites_session import integration
    from bot.manual_stages import ManualStagesResult,ManualStageOutcome
    runner,trace,*_=integration()
    w=World([(0,0)])
    w.cycle.manual_stages=NS(run=w.manual)
    w.manual_results=[ManualStagesResult(S.COMPLETED,outcome=ManualStageOutcome.STAMINA_INSUFFICIENT)]
    run=w.cycle.run
    w.cycle.run=lambda:trace.append('arena.run') or run()
    runner.plan=replace(runner.plan,flows=(w.cycle,runner.plan.flows[1]))
    r=runner.run()
    assert r.status.value=='completed'
    assert trace.index('arena.run')<trace.index('last.run')<trace.index('cleanup')<trace.index('rotation.advance')


@pytest.mark.parametrize('balances,completed', [([(0, 100), (0, 100)], True),
    ([(0, 100), (0, 0)], True), ([(0, 100), (40, 0)], False)])
def test_no_progress_or_missing_causal_mw_completion_never_repeats(balances, completed):
    w = World(balances); w.mw_results = [mw_result(completed)]
    r = w.cycle.run()
    assert r.succeeded and r.termination is T.NO_PROGRESS and w.trace.count('mw') == 1


def test_safety_limit_even_with_valid_progress():
    w = World([(40, 100), (0, 100), (40, 0)], max_operations=2)
    w.arena_results = [arena_result()]; w.mw_results = [mw_result()]
    assert w.cycle.run().termination is T.SAFETY_LIMIT


def test_replenishment_cannot_buy_an_endless_sequence_of_zero_yield_samples():
    balances = [(40, 100)]
    for _ in range(6): balances.extend([(0, 100), (40, 100)])
    w = World(balances)
    w.arena_results = [arena_result(40, 0, f'batch-{n}') for n in range(6)]
    w.mw_results = [mw_result() for _ in range(5)]
    r = w.cycle.run()
    assert r.succeeded and r.termination is T.NO_PROGRESS
    assert len(r.operations) == 11 and w.trace.count('mw') == 5
    assert [v for v in w.trace if isinstance(v, D)] == [D.HARD, D.HARD, D.NORMAL, D.NORMAL, D.EASY, D.EASY]


@pytest.mark.parametrize('post', [None, resources(0, 100, 1)])
def test_post_operation_refresh_cannot_reuse_balance_or_authorize_mw(post):
    w = World([(40, 100), post]); w.arena_results = [arena_result()]
    r = w.cycle.run()
    assert r.status is S.MANUAL_RESOLUTION and r.termination is T.AMBIGUOUS
    assert w.trace == ['read', D.HARD, 'lobby', 'read']


def test_credited_batch_is_authority_without_inventing_a_predicted_post_balance():
    w = World([(40, 0), (1, 0)]); w.arena_results = [arena_result()]
    r = w.cycle.run()
    assert r.succeeded and r.termination is T.MANUAL_STAGES_NOT_IMPLEMENTED
    assert r.resources.badges == 1 and w.cycle.controller.batches == 1


def test_zero_win_batch_jump_then_easy_functional_stop():
    w = World([(80, 100), (0, 100), (80, 0), (0, 0)])
    w.arena_results = [arena_result(80, 0, 'hard'), arena_result(80, 0, 'easy')]
    w.mw_results = [mw_result()]
    r = w.cycle.run()
    assert r.succeeded and r.termination is T.EASY_ZERO_WINS and not r.failure
    assert [v for v in w.trace if isinstance(v, D)] == [D.HARD, D.EASY]


def test_custom_thresholds_control_routing_and_zero_exception():
    config = ArenaConfig(M.FARMING_CYCLE, min_badges_for_arena=8,
        min_sapphires_for_mw=50, zero_win_threshold=8)
    w = World([(8, 50), (0, 50), (8, 0), (0, 0)], config=config)
    w.arena_results = [arena_result(8, 0, 'hard'), arena_result(8, 0, 'easy')]
    w.mw_results = [mw_result()]
    assert w.cycle.run().termination is T.EASY_ZERO_WINS


@pytest.mark.parametrize('bad', [None, replace(resources(40, 100), observed_at=90.), resources(40, 100, 500)])
def test_unknown_stale_or_future_resources_never_authorize_input(bad):
    w = World([bad]); r = w.cycle.run()
    assert r.status is S.MANUAL_RESOLUTION and r.termination is T.AMBIGUOUS
    assert w.trace == ['read']


@pytest.mark.parametrize('result', [ArenaFlowResult(S.FAILED, error='adb_lost'),
    ArenaFlowResult(S.MANUAL_RESOLUTION, error='unrecognized_modal'),
    ArenaFlowResult(S.MANUAL_RESOLUTION, error='result_unreadable', phase='result_ambiguous'),
    ArenaFlowResult(S.CANCELLED, physical_operation_may_be_active=True)])
def test_subordinate_errors_preserved_no_navigation_or_retry(result):
    w = World([(40, 100)]); w.arena_results = [lambda _: result]
    r = w.cycle.run()
    assert r.status is result.status and r.error == result.error and r.failure == result.failure
    if result.status is S.FAILED: assert r.termination is T.TECHNICAL_FAILURE
    if result.phase == 'result_ambiguous': assert r.termination is T.AMBIGUOUS
    assert w.trace == ['read', D.HARD]
    if r.physical_operation_may_be_active:
        again = w.cycle.run()
        assert again.physical_operation_may_be_active and w.trace == ['read', D.HARD]


def test_missing_batch_is_ambiguous_not_exhaustion_and_no_next_consumption():
    w = World([(40, 100), (0, 100)]); w.arena_results = [lambda _: ArenaFlowResult(S.COMPLETED)]
    r = w.cycle.run()
    assert r.status is S.MANUAL_RESOLUTION and r.termination is T.AMBIGUOUS
    assert 'mw' not in w.trace


def test_cancel_at_initial_read_or_after_flow_never_starts_another_activity():
    w = World([(40, 100)]); w.cancel = True
    assert w.cycle.run().status is S.CANCELLED and not w.trace
    w = World([(40, 100)])
    def cancelled(d):
        w.cancel = True
        return arena_result()(d)
    w.arena_results = [cancelled]
    assert w.cycle.run().status is S.CANCELLED
    assert w.trace == ['read', D.HARD]


def test_each_new_run_resets_controller_even_same_instance():
    w = World([(80, 0), (0, 0), (40, 0), (0, 0)])
    w.arena_results = [arena_result(80, 0, 'one'), arena_result(40, 40, 'two')]
    assert w.cycle.run().succeeded and w.cycle.controller.difficulty is D.EASY
    assert w.cycle.run().succeeded and w.cycle.controller.difficulty is D.HARD
    assert w.cycle.controller.batches == 1


def test_functional_end_continues_session_then_cleanup_then_rotation():
    from test_meteorites_session import integration
    runner, trace, _, _, _, _, _ = integration()
    w = World([(80, 100), (0, 100), (80, 0), (0, 0)])
    w.arena_results = [arena_result(80, 0, 'hard'), arena_result(80, 0, 'easy')]
    w.mw_results = [mw_result()]
    original = w.cycle.run
    def run(): trace.append('arena.run'); return original()
    w.cycle.run = run
    runner.plan = replace(runner.plan, flows=(w.cycle, runner.plan.flows[1]))
    r = runner.run()
    assert r.status.value == 'completed'
    assert trace.index('setup') < trace.index('arena.run') < trace.index('last.run') < trace.index('cleanup') < trace.index('rotation.advance')


def test_missing_dependency_is_distinct_and_session_continues():
    from test_session import Flow, Rotation, _runner
    w = World([(0, 0)]); trace = []
    runner, _ = _runner(1, [w.cycle, Flow('next', [FlowResult(S.COMPLETED)], trace)], Rotation(1, trace))
    r = runner.run()
    assert r.status.value == 'completed' and trace == ['next.run', 'rotation.advance']
    assert r.character_results[0].flow_results[0].termination is T.MANUAL_STAGES_NOT_IMPLEMENTED
