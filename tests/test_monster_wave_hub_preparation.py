"""Equivalent MW entry permissions against 5aaf8fd, with a simulated clock.

Real observer, resolver, transition, executor and Sapphire consensus; only pixels,
OCR text, the clock and transport are deterministic doubles. No device is used.
"""
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import ActionExecutor
from bot.battle_mode_zone import BattleModeZone, is_battle_mode_select, is_lobby
from bot.capture import FrameSnapshot
from bot.catalog import (build_default_resolver, LANDMARK_BATTLE_MODE_SELECT_HEADER,
                         LANDMARK_LOBBY_TRADING_CENTER_LABEL)
from bot.fact_reader import RuntimeFactReader
from bot.flow_contracts import FlowStatus
from bot.monster_wave_activity import MonsterWaveActivity
from bot.monster_wave_semantics import (MW_SCREEN, MW_TIMER, MW_SKIP_START, MW_MAX,
                                       MW_CONTROLS_CLEAR)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.ocr import OcrResult
from bot.ocr_extractors import build_battle_mode_sapphires_extractor
from bot.operation_control import OperationControl, control_scope
from bot.runtime_observer import RuntimeObserver
from bot.verified_transition import VerifiedTransition


BASELINE = '5aaf8fdeb10c7e3866401d4d5bf3b5336e03cf81'


@pytest.fixture(scope='module')
def baseline_activity():
    name = 'bot._hub_preparation_baseline'
    module = ModuleType(name)
    sys.modules[name] = module
    source = subprocess.check_output(
        ['git', 'show', f'{BASELINE}:bot/monster_wave_activity.py'],
        cwd=Path(__file__).resolve().parents[1], text=True, encoding='utf-8')
    exec(compile(source, f'bot/monster_wave_activity.py@{BASELINE}', 'exec'), module.__dict__)
    yield module.MonsterWaveActivity
    del sys.modules[name]


class HubScenario:
    def __init__(self, cls=MonsterWaveActivity, *, entry='normal', readings=('200', '200'),
                 analysis_seconds=.4, capture_seconds=0.):
        self.now = 100.
        self.analysis_seconds = analysis_seconds
        self.surface = 'lobby'
        self.source_id = 'stream-1'
        self.effect_at = None
        self.entry = entry
        self.readings = iter(readings)
        self.cancelled = False
        self.disturbance = None
        self.count = 0
        self.capture_count = 0
        self.inputs = []
        self.tap_count = 0
        self.records = []
        self.last_snapshot = None
        self.on_analysis = None
        self.on_capture = None
        self.fact_after = None
        self.fact_times = []
        self.open_cost = None

        def get_frame():
            self.capture_count += 1
            self.now += capture_seconds
            if self.effect_at is not None and self.now >= self.effect_at:
                self.surface, self.effect_at = 'hub', None
            if self.on_capture:
                self.on_capture()
            return FrameSnapshot(np.zeros((120, 240, 3), np.uint8), self.now-.001,
                                 int(round(self.now*1000)), source_id=self.source_id)

        def analyze(frame):
            self.count += 1
            names = {
                'lobby': (LANDMARK_LOBBY_TRADING_CENTER_LABEL,),
                'hub': (LANDMARK_BATTLE_MODE_SELECT_HEADER,),
                'mw': (MW_SCREEN, MW_TIMER, MW_SKIP_START, MW_MAX, MW_CONTROLS_CLEAR),
                'blocked': (LANDMARK_BATTLE_MODE_SELECT_HEADER,
                            'landmark.equipment_inventory_full_prompt'),
                'foreign': ('landmark.trading_center_title',),
                'ambiguous': (LANDMARK_BATTLE_MODE_SELECT_HEADER, 'landmark.trading_center_title'),
                'unknown': (),
            }[self.surface]
            self.now += self.analysis_seconds
            if self.on_analysis:
                self.on_analysis()
            return ObservationBatch(frame.sequence, frame.timestamp, tuple(
                Observation(n, 1., ObservationSource.LOCAL_CV) for n in names))

        def consumed(snapshot):
            self.last_snapshot = snapshot

        self.events = SimpleNamespace(record=lambda e, **f: self.records.append((e, f)))
        self.observer = RuntimeObserver(SimpleNamespace(get_frame=get_frame),
            SimpleNamespace(analyze=analyze), build_default_resolver(),
            clock=lambda: self.now, sleeper=self.sleep, events=self.events,
            snapshot_consumer=consumed)
        physical = ActionExecutor(SimpleNamespace(tap=self.tap))

        def execute(action, geometry):
            kind = type(action).__name__
            # Actual transition guard and actual physical executor both run.
            assert (is_lobby(self.last_snapshot) if kind == 'OpenBattleModeSelect'
                    else is_battle_mode_select(self.last_snapshot))
            if kind == 'OpenMonsterWave':
                self.open_cost = (self.count, self.now)
                assert self.last_snapshot.sequence > self.fact_after
                assert self.fact_times[-1] < self.last_snapshot.timestamp
            result = physical.execute(action, geometry)
            self.inputs.append(kind)
            if kind == 'OpenBattleModeSelect':
                delay = 7. if self.entry == 'late' else 0.
                if self.entry != 'retry' or self.inputs.count(kind) == 2:
                    self.effect_at = self.now + delay
            elif kind == 'OpenMonsterWave':
                self.surface = 'mw'
            else:
                raise AssertionError(kind)
            return result

        self.actions = SimpleNamespace(execute=execute)
        self.transition = VerifiedTransition(self.observer, self.actions, self.events,
            clock=lambda: self.now, cancel_requested=lambda: self.cancelled)
        self.zone = BattleModeZone(self.observer, self.transition,
                                   cancel_requested=lambda: self.cancelled)

        def recognize(image):
            self.fact_times.append(self.now)
            return OcrResult(next(self.readings, ''), 1.)

        self.facts = RuntimeFactReader(self.observer,
            [build_battle_mode_sapphires_extractor(SimpleNamespace(recognize=recognize))],
            clock=lambda: self.now, events=self.events)
        original_read = self.facts.read_sapphires

        def read(**kwargs):
            self.fact_after = kwargs['after_sequence']
            result = original_read(**kwargs)
            if self.disturbance:
                self.surface = self.disturbance
            return result

        self.facts.read_sapphires = read
        self.activity = cls(self.observer, self.actions, self.events, facts=self.facts,
            clock=lambda: self.now, sleeper=self.sleep, verified_transition=self.transition,
            cancel_requested=lambda: self.cancelled)

    def tap(self, *args, **kwargs):
        self.tap_count += 1
        self.now += .05

    def sleep(self, seconds):
        self.now += seconds

    def enter(self):
        result = self.zone.enter()
        assert result.succeeded, result
        return result.hub_entry

    def prepare(self, entry, *, baseline=False, deadline=None):
        self.records.clear()
        count, started, inputs = self.count, self.now, len(self.inputs)
        captures = self.capture_count
        control = OperationControl(clock=lambda: self.now, deadline=deadline)
        with control_scope(control):
            result = self.activity.prepare(**({} if baseline else {'hub_entry': entry}))
        return result, dict(analyses=self.count-count, seconds=round(self.now-started, 7),
                            capture_calls=self.capture_count-captures,
                            inputs=self.inputs[inputs:], taps=self.tap_count,
                            before_open_analyses=self.open_cost[0]-count if self.open_cost else None,
                            before_open_seconds=round(self.open_cost[1]-started, 7) if self.open_cost else None)


@pytest.mark.parametrize('entry', ['normal', 'retry', 'late'])
def test_baseline_equivalence_and_three_analyses_removed(baseline_activity, entry):
    rows = []
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls, entry=entry)
        proof = h.enter()
        assert proof.attempt_count == (2 if entry == 'retry' else 1)
        assert proof.grace_wait_count == (1 if entry in {'retry', 'late'} else 0)
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity)
        assert result.succeeded, result
        assert result.sapphires_initial == 200
        assert metrics['inputs'] == ['OpenMonsterWave']
        assert len(h.fact_times) == 2 and h.fact_after >= proof.final_snapshot.sequence
        assert result.transition_attempts == (('monster_wave.open', 1, 0),)
        rows.append(metrics)
    assert rows[0]['analyses'] - rows[1]['analyses'] == 3
    assert rows[0]['before_open_analyses'] == 7
    assert rows[1]['before_open_analyses'] == 4
    assert rows[0]['seconds'] - rows[1]['seconds'] == pytest.approx(1.22)
    assert rows[0]['before_open_seconds'] - rows[1]['before_open_seconds'] == pytest.approx(1.22)
    assert rows[0]['taps'] == rows[1]['taps']


@pytest.mark.parametrize('invalid', [
    'absent', 'stale', 'future', 'pre_dispatch', 'old_sequence', 'source_changed',
    'source_missing', 'receipt_missing', 'receipt_time_missing', 'recovery',
    'not_ready', 'no_effect', 'blocked', 'foreign', 'ambiguous', 'unknown', 'rewound',
    'expires_during_capture',
    'operation_missing', 'receipt_other_operation', 'receipt_other_attempt',
    'coverage_lost', 'coverage_missing', 'receipt_time_nan', 'receipt_time_infinite',
    'receipt_time_negative',
])
def test_invalid_handoff_uses_unchanged_fallback(baseline_activity, invalid):
    rows = []
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls)
        proof = h.enter()
        final = proof.final_snapshot
        if invalid == 'absent': proof = None
        elif invalid == 'stale': h.now += 2.1
        elif invalid == 'future': h.now = final.timestamp-.1
        elif invalid == 'pre_dispatch':
            proof = replace(proof, dispatch_receipts=(replace(proof.dispatch_receipts[-1],
                                                             completed_at=final.timestamp),))
        elif invalid == 'old_sequence':
            sequence = proof.action_source_snapshot.sequence
            proof = replace(proof, final_snapshot=replace(final,
                frame=replace(final.frame, sequence=sequence),
                observations=replace(final.observations, sequence=sequence),
                state=replace(final.state, sequence=sequence)))
        elif invalid == 'source_changed': h.source_id = 'stream-2'
        elif invalid == 'source_missing':
            proof = replace(proof, final_snapshot=replace(final, frame=replace(final.frame, source_id=None)))
        elif invalid == 'receipt_missing': proof = replace(proof, dispatch_receipts=())
        elif invalid == 'receipt_time_missing':
            proof = replace(proof, dispatch_receipts=(replace(proof.dispatch_receipts[-1], completed_at=None),))
        elif invalid == 'operation_missing': proof = replace(proof, operation_id=None)
        elif invalid == 'receipt_other_operation':
            proof = replace(proof, dispatch_receipts=(replace(proof.dispatch_receipts[-1], operation_id='other'),))
        elif invalid == 'receipt_other_attempt':
            proof = replace(proof, dispatch_receipts=(replace(proof.dispatch_receipts[-1], attempt_index=0),))
        elif invalid in {'coverage_lost', 'coverage_missing'}:
            before = proof.action_source_snapshot
            proof = replace(proof,
                action_source_snapshot=replace(before, observations=replace(before.observations,
                    coverage=frozenset({'hub', 'blockers'}))),
                final_snapshot=replace(final, observations=replace(final.observations,
                    coverage=frozenset({'hub'}) if invalid == 'coverage_lost' else None)))
        elif invalid in {'receipt_time_nan', 'receipt_time_infinite', 'receipt_time_negative'}:
            value = {'receipt_time_nan': float('nan'), 'receipt_time_infinite': float('inf'),
                     'receipt_time_negative': -1.}[invalid]
            proof = replace(proof, dispatch_receipts=(replace(proof.dispatch_receipts[-1], completed_at=value),))
        elif invalid == 'recovery': proof = replace(proof, recovery_after_action=True)
        elif invalid == 'not_ready': proof = replace(proof, ready=False)
        elif invalid == 'no_effect': proof = replace(proof, effect_accredited=False)
        elif invalid == 'expires_during_capture':
            def slow_capture():
                h.now += 2.1
                h.on_capture = None
            h.on_capture = slow_capture
        elif invalid == 'rewound':
            h.observer.source.get_frame = lambda: replace(final.frame, sequence=final.sequence-1)
        else:
            h.surface = invalid
            changed = h.observer.observe()
            proof = replace(proof, final_snapshot=changed)
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity)
        rows.append((result.status, result.sapphires_initial, metrics['analyses'], metrics['inputs']))
    assert rows[0] == rows[1]


def test_declared_coverage_is_preserved_without_extra_analysis():
    h = HubScenario()
    proof = h.enter()
    before, final = proof.action_source_snapshot, proof.final_snapshot
    coverage = frozenset({'hub', 'blockers'})
    proof = replace(proof,
        action_source_snapshot=replace(before, observations=replace(before.observations, coverage=coverage)),
        final_snapshot=replace(final, observations=replace(final.observations, coverage=coverage)))
    result, metrics = h.prepare(proof)
    assert result.succeeded
    assert metrics['before_open_analyses'] == 4 and metrics['inputs'] == ['OpenMonsterWave']


@pytest.mark.parametrize('disturbance', ['blocked', 'foreign', 'ambiguous', 'unknown'])
def test_new_contradiction_after_consensus_still_blocks_open(baseline_activity, disturbance):
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls)
        proof = h.enter()
        h.disturbance = disturbance
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity)
        assert result.status is FlowStatus.FAILED
        assert metrics['inputs'] == []


@pytest.mark.parametrize('readings, expected', [
    (('', '', ''), FlowStatus.FAILED), (('200', '201', '202'), FlowStatus.FAILED),
    (('200', '', '200'), FlowStatus.COMPLETED), (('0', '0'), FlowStatus.COMPLETED),
])
def test_fresh_economic_consensus_is_unchanged(baseline_activity, readings, expected):
    rows = []
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls, readings=readings)
        proof = h.enter()
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity)
        assert result.status is expected
        rows.append((result.sapphires_initial, len(h.fact_times), metrics['inputs']))
    assert rows[0] == rows[1]


@pytest.mark.parametrize('when', ['before', 'capture', 'consensus', 'final'])
def test_cancellation_never_adds_an_input(baseline_activity, when):
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls)
        proof = h.enter()
        if when == 'before': h.cancelled = True
        if when == 'capture': h.on_capture = lambda: setattr(h, 'cancelled', True)
        if when == 'consensus':
            h.on_analysis = lambda: setattr(h, 'cancelled', bool(h.fact_times))
        if when == 'final':
            h.on_analysis = lambda: setattr(h, 'cancelled', len(h.fact_times) == 2)
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity)
        assert result.status is FlowStatus.CANCELLED
        assert metrics['inputs'] == []


@pytest.mark.parametrize('remaining', [0., .6, 1.3])
def test_shared_deadline_never_authorizes_open_after_expiry(baseline_activity, remaining):
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls)
        proof = h.enter()
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity,
                                    deadline=h.now+remaining)
        assert result.status is FlowStatus.FAILED
        assert metrics['inputs'] == []


@pytest.mark.parametrize('capture_seconds', [0., .005])
def test_fallback_adds_only_one_capture_metadata_read(baseline_activity, capture_seconds):
    rows = []
    for cls in (baseline_activity, MonsterWaveActivity):
        h = HubScenario(cls, capture_seconds=capture_seconds)
        proof = h.enter()
        h.source_id = 'stream-2'
        result, metrics = h.prepare(proof, baseline=cls is baseline_activity)
        assert result.succeeded
        rows.append(metrics)
    assert rows[0]['analyses'] == rows[1]['analyses'] == 9
    assert rows[1]['seconds'] - rows[0]['seconds'] == pytest.approx(capture_seconds)
    assert rows[1]['capture_calls'] == rows[0]['capture_calls'] + 1


def test_deadline_expiring_during_metadata_read_stops_without_analysis_or_input():
    h = HubScenario()
    proof = h.enter()
    deadline = h.now+.1
    h.on_capture = lambda: setattr(h, 'now', h.now+.2)
    result, metrics = h.prepare(proof, deadline=deadline)
    assert result.status is FlowStatus.FAILED
    assert metrics['analyses'] == 0 and metrics['inputs'] == []


@pytest.mark.parametrize('productive', [False, True])
def test_standalone_flow_forwards_the_exact_entry_without_caching(productive):
    from unittest.mock import Mock
    from bot.monster_wave_flow import MonsterWaveFlow
    from bot.monster_wave_productive import ProductiveMonsterWaveFlow
    from bot.monster_wave_activity import MonsterWaveResult
    h = HubScenario()
    entered = h.zone.enter()
    flow = object.__new__(ProductiveMonsterWaveFlow if productive else MonsterWaveFlow)
    flow.zone = SimpleNamespace(enter=lambda: entered)
    flow.entry_readiness = lambda: None
    success = MonsterWaveResult(FlowStatus.COMPLETED)
    if productive:
        flow._run_activity_l1 = Mock(return_value=success)
        method = flow._run_activity_l1
    else:
        flow.activity = SimpleNamespace(run=Mock(return_value=success))
        method = flow.activity.run
    assert flow.run().succeeded
    assert method.call_args.kwargs['hub_entry'] is entered.hub_entry
    assert method.call_args.kwargs['keep_current'] is True
    assert not hasattr(flow, 'hub_entry')
