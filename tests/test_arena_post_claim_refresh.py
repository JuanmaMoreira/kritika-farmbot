"""Post-Claim resource refresh: passive recovery, diagnosis, safety."""
from types import SimpleNamespace as NS

import pytest

from bot.arena_farming_cycle import FarmingTermination as T
from bot.arena_farming_resources import ArenaFarmingResources
from bot.flow_contracts import FlowStatus as S
from bot.manual_stages import ManualStagesResult, ManualStageOutcome as O
from bot.runtime_observer import RuntimeWaitCancelled
from bot.state import ResolutionStatus as R
from bot.capture import FrameSnapshot
import numpy as np


def resources(badges, sapphires, sequence=1):
    return ArenaFarmingResources(badges, sapphires, sequence, 100. + sequence, 'a' * 64)

def test_post_claim_late_confirmation_is_rejected_and_capture_has_remaining_bound():
    reader=reader_world_for_recovery([(10,20),(10,20)])
    now=[100.]
    reader.clock=lambda:now[0]
    refresh=reader.observer.source.refresh_native
    bounds=[]
    def slow(**kwargs):
        bounds.append(kwargs['timeout']);now[0]+=7.
        return refresh()
    reader.observer.source.refresh_native=slow
    assert reader.read_post_claim() is None
    assert bounds==[12.,5.]
    assert reader.last_diagnosis['counters']['deadline_expired']==1


def reader_world_for_recovery(parse_sequence, *, cancel=False):
    """Scripted parse results with fresh native frames; warmup stubbed."""
    seqs = iter(range(2, 30))
    results = iter(parse_sequence)

    def refresh(**kwargs):
        seq = next(seqs)
        return NS(sequence=seq, timestamp=100. + seq,
                  image=np.zeros((90, 160, 3), dtype=np.uint8))

    frame0 = FrameSnapshot(np.zeros((90, 160, 3), dtype=np.uint8), 100., 1)
    resolved = NS(status=R.RESOLVED, overlays=(), base_context='screen.lobby')
    observer = NS(
        perception=NS(analyze=lambda f: f),
        resolver=NS(resolve=lambda _: resolved),
        observe=lambda: NS(frame=frame0, state=resolved, sequence=1, timestamp=100.),
        source=NS(refresh_native=refresh),
    )
    from bot.arena_farming_resources import ArenaFarmingResourceReader
    reader = ArenaFarmingResourceReader(
        observer, None, clock=lambda: 100.,
        visuals=NS(lobby=lambda _: True),
        cancel_requested=lambda: cancel,
    )
    # Warmup OCR init must not touch a real engine in unit tests.
    reader._pair = lambda *a: 0

    def fake_parse_detail(frame):
        if cancel:
            raise RuntimeWaitCancelled('cancelled')
        item = next(results)
        if item is None:
            return None, 'badges_unreadable'
        badges, sapphires = item
        return (ArenaFarmingResources(badges, sapphires, frame.sequence,
                                      frame.timestamp, 'a' * 64), None)

    # _read_inner prefers _parse_detail when `parse` is not stubbed.
    # Stub _parse_detail directly for scripted motives.
    reader._parse_detail = fake_parse_detail
    return reader


def test_post_claim_extra_frame_recovers_after_initial_ambiguity():
    # 3-frame read sees [None, X, X]: two valid consecutive -> success.
    # To prove the extra frame matters, use [None, None, X] (fail) vs
    # [None, None, X, X] (post-claim success).
    reader = reader_world_for_recovery([None, (10, 20), (10, 20)])
    reading = reader.read()
    assert reading is not None and (reading.badges, reading.sapphires) == (10, 20)

    reader_fail = reader_world_for_recovery([None, None, (10, 20)])
    assert reader_fail.read() is None
    assert reader_fail.last_diagnosis['counters'].get('badges_unreadable') == 2
    assert reader_fail.last_diagnosis['counters'].get('no_consensus') == 1

    reader_recover = reader_world_for_recovery([None, None, (10, 20), (10, 20)])
    assert reader_recover.read() is None  # 3 frames: only one valid at the end
    reader_recover2 = reader_world_for_recovery([None, None, (10, 20), (10, 20)])
    reading = reader_recover2.read_post_claim()
    assert reading is not None and (reading.badges, reading.sapphires) == (10, 20)
    assert reader_recover2.last_diagnosis['confirmed']
    assert reader_recover2.last_diagnosis['attempts'] == 4


def test_cycle_post_claim_recovery_continues_without_new_claim():
    from test_arena_farming_cycle import World, mw_result
    from bot.stamina_purchase import StaminaSupplyResult
    # Initial manual, Claim makes MW eligible: no purchase, MW continues.

    def prepare(required, *, still_manual):
        w.trace.append('supply')
        still_manual()
        return StaminaSupplyResult(NS(stamina=0), required, outcome='routing_changed')

    w = World([(0, 0), (0, 100), (40, 0)])
    w.cycle.manual_stages = NS(
        balances=NS(read=lambda: NS(stamina=0)),
        prepare_stamina=prepare,
    )
    w.mw_results = [mw_result()]
    w.cycle.max_operations = 1
    result = w.cycle.run()
    assert result.succeeded
    assert w.trace.count('supply') == 1  # single Claim path, no retry
    assert 'mw' in w.trace
    assert result.event_count('arena.farming.resources') == 3


def test_persistent_ambiguity_keeps_manual_resolution_with_diagnosis():
    from test_arena_farming_cycle import World
    w = World([None])
    w.cycle.reader = NS(read=lambda: None,
                        last_diagnosis={'summary': 'attempts=3 confirmed=0 badges_unreadable=2 no_consensus=1 last_seq=5 age=1.10s',
                                        'counters': {'badges_unreadable': 2, 'no_consensus': 1},
                                        'attempts': 3, 'confirmed': False,
                                        'last_sequence': 5, 'last_age': 1.1})
    result = w.cycle.run()
    assert result.status is S.MANUAL_RESOLUTION and result.termination is T.AMBIGUOUS
    terminated = result.events[-1]
    assert terminated.kind == 'arena.farming.terminated'
    assert terminated.detail is not None and 'attempts=3' in terminated.detail
    assert 'badges_unreadable' in (terminated.detail + (result.error or ''))
    assert result.error is not None
    assert not result.succeeded


def test_stale_and_contradictory_values_rejected():
    reader = reader_world_for_recovery([(10, 20), (11, 21), (12, 22)])
    calls = {'n': 0}
    base_refresh = reader.observer.source.refresh_native

    def flaky_refresh(**kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            return NS(sequence=1, timestamp=100.,
                      image=np.zeros((90, 160, 3), dtype=np.uint8))
        return base_refresh()

    reader.observer.source.refresh_native = flaky_refresh
    assert reader.read() is None
    assert reader.last_diagnosis['counters'].get('stale_frame') == 1
    assert reader.last_diagnosis['counters'].get('no_consensus') == 1
    assert not reader.last_diagnosis['confirmed']

    from test_arena_farming_cycle import World
    from test_arena_farming_cycle import arena_result
    w = World([(40, 100), resources(40, 100, 1)])
    w.arena_results = [arena_result()]
    result = w.cycle.run()
    assert result.status is S.MANUAL_RESOLUTION and result.termination is T.AMBIGUOUS
    assert result.event_count('arena.farming.resources') == 1


def _reader_world_with_state(initial_state, initial_overlays, initial_context,
                             frame_state=None, frame_overlays=(), frame_context='screen.lobby'):
    from bot.arena_farming_resources import ArenaFarmingResourceReader
    frame = FrameSnapshot(np.zeros((90, 160, 3), dtype=np.uint8), 100., 1)
    initial = NS(status=initial_state, overlays=initial_overlays, base_context=initial_context)
    resolved_frame = NS(status=frame_state or R.RESOLVED, overlays=frame_overlays,
                        base_context=frame_context)
    seqs = iter(range(2, 30))

    def refresh(**kwargs):
        seq = next(seqs)
        # Fresh timestamps just above the fixed clock (101.5).
        return NS(sequence=seq, timestamp=101. + seq * 0.01,
                  image=np.zeros((90, 160, 3), dtype=np.uint8))

    observer = NS(perception=NS(analyze=lambda f: f),
                  resolver=NS(resolve=lambda _: resolved_frame),
                  observe=lambda: NS(frame=frame, state=initial, sequence=1, timestamp=100.),
                  source=NS(refresh_native=refresh))
    reader = ArenaFarmingResourceReader(observer, None, clock=lambda: 101.5,
                                        visuals=NS(lobby=lambda _: True))
    reader._pair = lambda *args: 40
    return reader, frame


def test_incompatible_context_authorizes_no_inputs():
    reader, frame = _reader_world_with_state(
        R.RESOLVED, (), 'screen.lobby',
        frame_state=R.UNKNOWN, frame_overlays=(), frame_context='screen.lobby')
    assert reader.parse(frame) is None
    # Initial UNKNOWN lobby blocks the whole read without gameplay inputs.
    reader2, _ = _reader_world_with_state(R.RESOLVED, ('unknown.modal',), 'screen.lobby')
    assert reader2.read() is None
    assert reader2.last_diagnosis['counters'].get('initial_not_lobby') == 1
    # Per-frame overlay is also rejected with its own motive.
    reader3, _ = _reader_world_with_state(
        R.RESOLVED, (), 'screen.lobby',
        frame_state=R.RESOLVED, frame_overlays=('unknown.modal',))
    assert reader3.read() is None
    assert reader3.last_diagnosis['counters'].get('overlay_incompatible', 0) >= 1

    from test_arena_farming_cycle import World
    w = World([None])
    result = w.cycle.run()
    assert result.status is S.MANUAL_RESOLUTION
    assert w.trace == ['read']


def test_cancellation_during_post_claim_refresh():
    reader = reader_world_for_recovery([(10, 20), (10, 20)], cancel=True)
    with pytest.raises(RuntimeWaitCancelled):
        reader.read_post_claim()

    from test_arena_farming_cycle import World
    w = World([(40, 100)])
    w.cancel = True
    result = w.cycle.run()
    assert result.status is S.CANCELLED
    assert result.termination is T.CANCELLED


def test_no_duplicate_claim_trade_or_start_on_refresh_failure():
    from test_arena_farming_cycle import World
    from bot.stamina_purchase import StaminaSupplyResult
    w = World([(0, 0), None])
    counts = {'supply': 0, 'manual': 0}

    def prepare2(required, *, still_manual):
        counts['supply'] += 1
        still_manual()
        return StaminaSupplyResult(NS(stamina=0), required, outcome='routing_changed')

    w.cycle.manual_stages = NS(
        run=lambda: (counts.__setitem__('manual', counts['manual'] + 1), ManualStagesResult(
            S.COMPLETED, outcome=O.REWARDED, stamina_consumed=60))[1],
        balances=NS(read=lambda: NS(stamina=0)),
        prepare_stamina=prepare2,
    )
    result = w.cycle.run()
    assert result.status is S.MANUAL_RESOLUTION and result.termination is T.AMBIGUOUS
    assert counts['supply'] == 1
    assert counts['manual'] == 0
    assert 'manual' not in w.trace
    assert result.stamina_consumed == 0
    assert 'post-claim resources ambiguous' in (result.error or '')


def test_session_report_keeps_ambiguous_without_success():
    from bot.arena_farming_report import project_arena_farming
    from bot.session_report import build_session_report, ReportStatus
    from test_session_report import session, character, accepted_arena_flow
    from dataclasses import replace
    raw = accepted_arena_flow()
    events = tuple(replace(event, fields={**event.fields, 'reason': 'ambiguous'})
                   if event.kind == 'arena.farming.terminated' else event
                   for event in raw.events)
    events = tuple(replace(event, detail='attempts=4 confirmed=0 badges_unreadable=3 last_seq=9 age=1.20s')
                   if event.kind == 'arena.farming.terminated' else event
                   for event in events)
    ambiguous = replace(raw, status=S.MANUAL_RESOLUTION, events=events)
    report = build_session_report(session(character(1, ambiguous), names=('arena',)))
    # MANUAL_RESOLUTION never becomes COMPLETE; diagnostic detail is not success.
    assert report.status is ReportStatus.BUSINESS_INCOMPLETE
    summary = project_arena_farming(ambiguous)
    assert summary.termination == 'ambiguous' and summary.status == 'MANUAL_RESOLUTION'


def test_normal_path_immediate_read_has_no_extra_penalty():
    reader = reader_world_for_recovery([(10, 20), (10, 20), (99, 99)])
    reading = reader.read()
    assert reading is not None and (reading.badges, reading.sapphires) == (10, 20)
    assert reader.last_diagnosis['attempts'] == 2
    assert reader.last_diagnosis['confirmed']

    from test_arena_farming_cycle import World, arena_result, mw_result
    w = World([(40, 100), (0, 100), (40, 0), (0, 0)])
    w.arena_results = [arena_result(run='one'), arena_result(run='two')]
    w.mw_results = [mw_result()]
    result = w.cycle.run()
    assert result.succeeded
    assert w.trace.count('read') == 4
    assert result.event_count('arena.farming.resources') == 4
