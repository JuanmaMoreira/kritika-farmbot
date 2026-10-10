"""Passive post-CLEAR sapphire recovery after transient HUD occlusion.

Failure 3f422c40 (log 20261010T002611 session 2e449f28, attempt 18):
three UNREADABLE reads on clean screen.monster_wave because a global
chat toast crossed the sapphire ROI, then `mw_fresh_sapphire_effect_unavailable`.
The reader must wait out the toast passively (no inputs, no invented
balance, no consumptive retry) and only accept a really CONFIRMED fact.
"""
from pathlib import Path
from unittest.mock import Mock

import pytest

from bot.monster_wave_activity import MonsterWaveActivity
from bot.monster_wave_config import MonsterWaveConfig
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE, POPUP_MW_CLEAR
from bot.runtime_facts import FactEvidence, FactReadResult, FactReadStatus
from bot.runtime_observer import RuntimeWaitCancelled
from test_world_boss_flow import snapshot, fact_result

ROOT = Path(__file__).resolve().parents[1]
FAILURE_DIR = ROOT / 'artifacts/failure_evidence/failure_3f422c40cc4449b9bf09f9a8a72b7610'


def unreadable(sequence, raw='LA 31'):
    return FactReadResult(
        FactReadStatus.UNREADABLE,
        evidence=(FactEvidence(sequence, float(sequence), raw, 0.71),),
    )


class ScriptedFacts:
    """Serve scripted reads, repeating the last one (persistent occlusion)."""

    def __init__(self, reads):
        self._reads = list(reads)
        self.calls = []

    def read_sapphires(self, **kwargs):
        self.calls.append(kwargs)
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def make_activity(reads, *, base=SCREEN_MONSTER_WAVE, overlays=(), clock_value=15.0):
    before = snapshot(10, base=base, overlays=overlays)
    observer = Mock()
    observer.observe.return_value = before
    facts = ScriptedFacts(reads)
    cancelled = {'value': False}
    activity = MonsterWaveActivity(
        observer, Mock(), Mock(), config=MonsterWaveConfig(),
        cancel_requested=lambda: cancelled['value'], facts=facts,
        clock=lambda: clock_value, sleeper=lambda _: None)
    return activity, facts, before, cancelled


def test_three_unreadable_then_valid_confirms_without_input():
    reads = [unreadable(11), unreadable(12), unreadable(13),
             fact_result('resource.sapphires', 31, 15, SCREEN_MONSTER_WAVE)]
    activity, facts, before, _ = make_activity(reads)
    fact = activity.read_sapphires_after_clear()
    assert fact.value == 31
    assert len(facts.calls) == 4
    assert [c['after_sequence'] for c in facts.calls] == [10, 11, 12, 13]
    assert {c['context'] for c in facts.calls} == {SCREEN_MONSTER_WAVE}
    assert all(0 < c['timeout'] <= 6.0 for c in facts.calls)
    assert set(facts.calls[0]) == {'context', 'after_sequence', 'timeout', 'cancel_requested'}


def test_persistent_occlusion_fails_safe_without_invented_data():
    activity, facts, _, _ = make_activity([unreadable(11)], clock_value=100.0)
    with pytest.raises(ValueError, match='mw_fresh_sapphire_effect_unavailable'):
        activity.read_sapphires_after_clear()
    assert len(facts.calls) == MonsterWaveActivity.POST_CLEAR_SAPPHIRES_ROUNDS


def test_expired_window_stops_even_with_fewer_rounds():
    now = [100.0]

    def clock():
        return now[0]

    before = snapshot(10, base=SCREEN_MONSTER_WAVE)
    observer = Mock()
    observer.observe.return_value = before

    def read_sapphires(**kwargs):
        now[0] += 5.0
        return unreadable(11)

    activity = MonsterWaveActivity(
        observer, Mock(), Mock(), config=MonsterWaveConfig(),
        cancel_requested=lambda: False,
        facts=Mock(read_sapphires=read_sapphires),
        clock=clock, sleeper=lambda _: None)
    with pytest.raises(ValueError, match='mw_fresh_sapphire_effect_unavailable'):
        activity.read_sapphires_after_clear()

def test_confirmation_after_deadline_and_technical_failure_do_not_recover():
    activity,facts,_,_=make_activity([fact_result('resource.sapphires',31,15,SCREEN_MONSTER_WAVE)])
    now=[100.];activity.clock=lambda:now[0]
    original=facts.read_sapphires
    def late(**kwargs):
        result=original(**kwargs);now[0]+=13.;return result
    facts.read_sapphires=late
    with pytest.raises(ValueError,match='mw_fresh_sapphire_effect_unavailable'):
        activity.read_sapphires_after_clear()
    assert len(facts.calls)==1
    activity,facts,_,_=make_activity([FactReadResult(FactReadStatus.FAILURE,detail='backend failed')])
    with pytest.raises(RuntimeError,match='backend failed'):
        activity.read_sapphires_after_clear()
    assert len(facts.calls)==1


@pytest.mark.parametrize('problem', ['stale', 'old_timestamp'])
def test_stale_or_unconfirmed_confirmation_is_rejected(problem):
    read = fact_result('resource.sapphires', 31, 12, SCREEN_MONSTER_WAVE)
    if problem == 'stale':
        evidence = tuple(e for e in read.fact.evidence)
        stale = tuple(
            FactEvidence(10, e.timestamp, e.raw_text, e.ocr_confidence)
            for e in evidence)
        from dataclasses import replace
        read = replace(read, fact=replace(read.fact, evidence=stale), evidence=stale)
    else:
        from dataclasses import replace
        evidence = tuple(
            FactEvidence(e.sequence, 1.0, e.raw_text, e.ocr_confidence)
            for e in read.fact.evidence)
        read = replace(read, fact=replace(read.fact, evidence=evidence), evidence=evidence)
    activity, facts, _, _ = make_activity([read])
    with pytest.raises(ValueError, match='mw_fresh_sapphire_effect_unavailable'):
        activity.read_sapphires_after_clear()
    assert len(facts.calls) == 1


def test_contradictory_context_during_wait_stops_as_not_clean():
    mismatch = FactReadResult(FactReadStatus.CONTEXT_MISMATCH, evidence=())
    activity, facts, _, _ = make_activity([unreadable(11), mismatch])
    with pytest.raises(ValueError, match='mw_effect_requires_clean_context'):
        activity.read_sapphires_after_clear()
    assert len(facts.calls) == 2


def test_dirty_initial_context_sends_no_read():
    mismatch = FactReadResult(FactReadStatus.CONTEXT_MISMATCH, evidence=())
    activity, facts, _, _ = make_activity(
        [mismatch], overlays=(POPUP_MW_CLEAR,))
    with pytest.raises(ValueError, match='mw_effect_requires_clean_context'):
        activity.read_sapphires_after_clear()
    assert facts.calls == []


def test_cancel_before_and_during_wait():
    activity, _, _, cancelled = make_activity([unreadable(11)])
    cancelled['value'] = True
    with pytest.raises(RuntimeWaitCancelled):
        activity.read_sapphires_after_clear()

    activity, facts, _, cancelled = make_activity(
        [unreadable(11), fact_result('resource.sapphires', 31, 15, SCREEN_MONSTER_WAVE)])
    original = facts.read_sapphires

    def cancelling_read(**kwargs):
        result = original(**kwargs)
        cancelled['value'] = True
        return result

    facts.read_sapphires = cancelling_read
    with pytest.raises(RuntimeWaitCancelled):
        activity.read_sapphires_after_clear()


def test_recovery_sends_zero_gameplay_inputs_and_no_consumptive_retry():
    reads = [unreadable(11), unreadable(12),
             fact_result('resource.sapphires', 31, 15, SCREEN_MONSTER_WAVE)]
    activity, facts, _, _ = make_activity(reads)
    activity.read_sapphires_after_clear()
    assert activity.observer.observe.call_count == 1
    actions = activity.actions
    assert actions.method_calls == []
    assert all(set(c) == {'context', 'after_sequence', 'timeout', 'cancel_requested'}
               for c in facts.calls)


def test_failure_frames_are_transient_negatives_never_zero_or_confirmed():
    pytest.importorskip('cv2')
    import cv2
    from bot.action_executor import FrameGeometry
    from bot.capture import FrameSnapshot
    from bot.observations import ObservationBatch
    from bot.ocr import RapidOcrEngine
    from bot.ocr_extractors import build_monster_wave_sapphires_extractor
    from bot.runtime_observer import RuntimeSnapshot, RuntimeFacts
    from bot.state import ResolutionStatus, ResolvedState

    paths = [FAILURE_DIR / f'frame_{sequence}.png' for sequence in (34335, 34342, 34348)]
    if not all(p.is_file() for p in paths):
        pytest.skip('failure evidence frames are not present')
    extractor = build_monster_wave_sapphires_extractor(RapidOcrEngine())
    for sequence, path in zip((34335, 34342, 34348), paths):
        image = cv2.imread(str(path))
        state = ResolvedState(ResolutionStatus.RESOLVED, sequence, float(sequence),
                              base_context=SCREEN_MONSTER_WAVE)
        frame = RuntimeSnapshot(FrameSnapshot(image, float(sequence), sequence),
                                ObservationBatch(sequence, float(sequence)),
                                state, RuntimeFacts(), FrameGeometry.from_frame(image))
        extracted = extractor.extract(frame)
        from bot.ocr_extractors import ExtractionStatus
        assert extracted.status is ExtractionStatus.UNREADABLE
        assert extracted.value is None
        # The true digits are visible under the toast: occlusion, not preprocessing.
        assert '31' in extracted.evidence.raw_text
