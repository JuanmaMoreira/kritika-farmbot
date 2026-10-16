"""Invocation-local reuse preserves evidence, validation and analysis isolation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.monster_wave_board_perception import MonsterWaveBoardPerception
from bot.perception.engine import PerceptionEngine
from bot.perception.local_cv import LocalCvDetector, _measurements
from bot.perception.specs import LinearGapCalibration, LocalCvSpec


@pytest.fixture
def scene(tmp_path):
    rng = np.random.default_rng(716)
    frame = rng.integers(0, 256, (40, 80, 3), dtype=np.uint8)
    template = cv2.cvtColor(frame[10:16, 20:28], cv2.COLOR_BGR2GRAY)
    for name in ('first.png', 'second.png'):
        assert cv2.imwrite(str(tmp_path / name), template)
    spec = LocalCvSpec('landmark.reuse_test', tmp_path / 'first.png',
                       (0., 0., 1., 1.), LinearGapCalibration(.2, .9))
    return frame, spec, tmp_path


@pytest.fixture
def matches(monkeypatch):
    calls = []
    native = cv2.matchTemplate

    def match(*args, **kwargs):
        calls.append(args[0].shape)
        return native(*args, **kwargs)

    monkeypatch.setattr(cv2, 'matchTemplate', match)
    return calls


def snap(frame, sequence=1):
    return FrameSnapshot(frame, 17.25, sequence, source_id='source-for-reuse-test')


def action(callback):
    return SimpleNamespace(detect=lambda f: callback(f) or ())


def test_exact_shared_spec_reuses_measurements_but_never_batches(scene, matches):
    frame, spec, _ = scene
    a, b = LocalCvDetector(spec), LocalCvDetector(spec)
    expected = (*a.detect(frame), *b.detect(frame))
    matches.clear()
    engine = PerceptionEngine((a, b))
    for seq, f in enumerate((frame, frame.copy(), frame ^ np.uint8(1)), 1):
        batch = engine.analyze(snap(f, seq))
        assert batch.observations == (*a.detect(f), *b.detect(f))
        assert batch.sequence == seq and batch.timestamp == 17.25
        assert batch.coverage is None
        # One in analyze; two independent reference calls outside it.
        assert len(matches) == 3 * seq
        assert _measurements.get() is None
    assert engine.analyze(snap(frame)).observations == expected


@pytest.mark.parametrize('difference', ['name', 'region', 'calibration', 'asset', 'variant'])
def test_similar_specs_do_not_share(scene, matches, difference):
    frame, spec, root = scene
    other = dict(name=replace(spec, name='landmark.another'),
                 region=replace(spec, region=(0., 0., .99, 1.)),
                 calibration=replace(spec, calibration=LinearGapCalibration(.1, .8)),
                 asset=replace(spec, asset_path=root / 'second.png'),
                 variant=replace(spec, variant_asset_paths=(root / 'second.png',)))[difference]
    a, b = LocalCvDetector(spec), LocalCvDetector(other)
    PerceptionEngine((a, b)).analyze(snap(frame))
    assert len(matches) == (3 if difference == 'variant' else 2)


def test_same_asset_with_different_loaded_pixels_does_not_share(scene, matches):
    frame, spec, _ = scene
    a = LocalCvDetector(spec)
    b = LocalCvDetector(spec, template_loader=lambda *_: 255 - a._templates[0])
    expected = (*a.detect(frame), *b.detect(frame)); matches.clear()
    assert PerceptionEngine((a, b)).analyze(snap(frame)).observations == expected
    assert len(matches) == 2


def test_variant_order_and_geometry_are_part_of_identity(scene, matches):
    frame, spec, root = scene
    a = LocalCvDetector(replace(spec, variant_asset_paths=(root / 'second.png',)))
    b = LocalCvDetector(replace(spec, asset_path=root / 'second.png',
                                variant_asset_paths=(spec.asset_path,)))
    PerceptionEngine((a, b)).analyze(snap(frame))
    assert len(matches) == 4
    # Same bytes in differently shaped templates must also miss.
    b.spec = a.spec; b.asset_paths = a.asset_paths
    b._templates = tuple(t.reshape(8, 6) for t in a._templates)
    matches.clear()
    PerceptionEngine((a, b)).analyze(snap(frame))
    assert len(matches) == 4


@pytest.mark.parametrize('target', ['frame', 'template', 'spec'])
def test_mutation_between_consumers_is_measured_again(scene, matches, target):
    frame, spec, _ = scene
    d = LocalCvDetector(spec)
    before = d.detect(frame)

    def mutate(f):
        if target == 'frame': f[:] = 128
        elif target == 'template': d._templates[0][:] = 0
        else: d.spec = replace(spec, calibration=LinearGapCalibration(.99, 1.))

    batch = PerceptionEngine((d, action(mutate), d)).analyze(snap(frame))
    assert len(matches) == 3  # reference + both real measurements
    assert batch.observations == (*before, *d.detect(frame))


def test_different_frame_inside_analysis_cannot_borrow_memo(scene, matches):
    frame, spec, _ = scene
    d = LocalCvDetector(spec); other = frame.copy()

    def foreign(_):
        d.measure(other); d.measure(other)

    PerceptionEngine((d, action(foreign), d)).analyze(snap(frame))
    assert len(matches) == 3


@pytest.mark.parametrize('frame', [None, [], np.zeros((2, 3), np.uint8),
    np.zeros((0, 3, 3), np.uint8), np.zeros((3, 3, 4), np.uint8),
    np.zeros((3, 3, 3), np.float32), np.zeros((1, 1, 3), np.uint8)])
def test_invalid_frames_preserve_error_type_and_message(scene, frame):
    _, spec, _ = scene
    d = LocalCvDetector(spec)
    with pytest.raises(Exception) as original:
        d.measure(frame)
    with pytest.raises(type(original.value)) as scoped:
        PerceptionEngine((d, d)).analyze(snap(frame))
    assert scoped.value.args == original.value.args
    assert _measurements.get() is None


def test_failed_measurement_is_not_cached(scene, monkeypatch):
    frame, spec, root = scene
    d = LocalCvDetector(replace(spec, variant_asset_paths=(root / 'second.png',)))
    import bot.perception.local_cv as module
    native = module.template_match_score; calls = []

    def measure(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2: raise ValueError('failed second variant')
        return native(*args, **kwargs)

    monkeypatch.setattr(module, 'template_match_score', measure)

    def retry(f):
        with pytest.raises(ValueError, match='failed second variant'): d.measure(f)
        return d.detect(f)

    PerceptionEngine((SimpleNamespace(detect=retry), d)).analyze(snap(frame))
    assert len(calls) == 4  # failure's partial result never stored
    assert _measurements.get() is None


@pytest.mark.parametrize('error', [RuntimeError, KeyboardInterrupt])
def test_exception_or_cancellation_always_cleans_state(scene, matches, error):
    frame, spec, _ = scene; d = LocalCvDetector(spec)

    def fail(_): raise error('stop')

    with pytest.raises(error):
        PerceptionEngine((d, action(fail))).analyze(snap(frame))
    assert _measurements.get() is None
    PerceptionEngine((d, d)).analyze(snap(frame))
    assert len(matches) == 2


def test_invalid_emission_also_cleans_state(scene):
    frame, spec, _ = scene; d = LocalCvDetector(spec)
    with pytest.raises(ValueError, match='Observation'):
        PerceptionEngine((d, SimpleNamespace(detect=lambda f: ('invalid',)))).analyze(snap(frame))
    assert _measurements.get() is None


def test_nested_analysis_same_engine_has_own_memo_and_restores_outer(scene, matches):
    frame, spec, _ = scene; d = LocalCvDetector(spec); entered = False

    def nested(f):
        nonlocal entered
        if not entered:
            entered = True
            engine.analyze(snap(f, 2))

    engine = PerceptionEngine((d, action(nested), d))
    engine.analyze(snap(frame))
    assert len(matches) == 2
    assert _measurements.get() is None


def test_nested_exception_and_different_scope_restore_outer(scene, matches):
    frame, spec, _ = scene; d = LocalCvDetector(spec)

    def fail(_): raise RuntimeError('nested')

    inner = PerceptionEngine((d, action(fail)))

    def nested(f):
        with pytest.raises(RuntimeError, match='nested'): inner.analyze(snap(f))

    PerceptionEngine((d, action(nested), d)).analyze(snap(frame))
    assert len(matches) == 2
    assert _measurements.get() is None


def test_engines_in_parallel_do_not_share_scope(scene, matches):
    frame, spec, _ = scene; barrier = Barrier(2)

    def run(_):
        d = LocalCvDetector(spec)
        def wait(f): barrier.wait(timeout=5)
        result = PerceptionEngine((d, action(wait), d)).analyze(snap(frame))
        assert _measurements.get() is None
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(run, range(2)))
    assert a == b and len(matches) == 2


def test_a1_cold_and_hot_keep_existing_pixel_memo(scene, matches):
    frame, spec, _ = scene; d = LocalCvDetector(spec)
    specialized = SimpleNamespace(detect=lambda f: d.detect(f))
    engine = MonsterWaveBoardPerception(PerceptionEngine((d, d, specialized)))
    cold = engine.analyze(snap(frame))
    assert engine.last_cached_count == 0 and len(matches) == 3
    hot = engine.analyze(snap(frame.copy(), 2))
    assert engine.last_cached_count == 2 and len(matches) == 4
    assert cold.observations == hot.observations
    changed = frame ^ np.uint8(1)
    engine.analyze(snap(changed, 3))
    assert engine.last_cached_count == 0 and len(matches) == 7
    assert _measurements.get() is None


def test_custom_calibration_is_not_assumed_pure(scene, matches):
    frame, spec, _ = scene

    class StatefulCalibration(LinearGapCalibration):
        def confidence(self, score):
            object.__setattr__(self, 'count', getattr(self, 'count', 0) + 1)
            return .8

    calibration = StatefulCalibration(.2, .9)
    d = LocalCvDetector(replace(spec, calibration=calibration))
    PerceptionEngine((d, d)).analyze(snap(frame))
    assert calibration.count == 2 and len(matches) == 2


def test_detector_subclass_is_not_assumed_pure(scene, matches):
    frame, spec, _ = scene

    class StatefulDetector(LocalCvDetector):
        def _measure_uncached(self, frame):
            self.count = getattr(self, 'count', 0) + 1
            return super()._measure_uncached(frame)

    d = StatefulDetector(spec)
    PerceptionEngine((d, d)).analyze(snap(frame))
    assert d.count == 2 and len(matches) == 2

@pytest.mark.parametrize('view', ['reversed', 'strided'])
def test_noncontiguous_frames_preserve_exact_order_and_values(scene, matches, view):
    frame, spec, _ = scene
    frame = frame[:, ::-1] if view == 'reversed' else frame[::2, ::2]
    d = LocalCvDetector(spec)
    expected = (*d.detect(frame), *d.detect(frame)); matches.clear()
    assert PerceptionEngine((d, d)).analyze(snap(frame)).observations == expected
    assert len(matches) == 1


def test_escaped_context_cannot_retain_or_reuse_completed_scope(scene, matches):
    from contextvars import copy_context
    frame, spec, _ = scene; d = LocalCvDetector(spec); contexts = []

    def capture(_): contexts.append(copy_context())

    PerceptionEngine((d, action(capture), d)).analyze(snap(frame))
    escaped = contexts[0].get(_measurements)
    assert escaped[0] is None and escaped[1] == {}
    contexts[0].run(d.measure, frame)
    contexts[0].run(d.measure, frame)
    assert len(matches) == 3


def test_nested_a1_suspends_outer_measurements(scene, matches):
    frame, spec, _ = scene; d = LocalCvDetector(spec)
    a1 = MonsterWaveBoardPerception(PerceptionEngine((d, d)))
    PerceptionEngine((d, action(lambda f: a1.analyze(snap(f)) and None), d)).analyze(snap(frame))
    assert len(matches) == 3
    assert _measurements.get() is None

@pytest.mark.parametrize('target', ['frame', 'template'])
def test_array_subclasses_keep_original_behavior_without_calling_custom_bytes(scene, matches, target):
    frame, spec, _ = scene

    class CustomArray(np.ndarray):
        def tobytes(self, *args, **kwargs):
            raise RuntimeError('custom array byte conversion')

    if target == 'frame':
        frame = frame.view(CustomArray)
        d = LocalCvDetector(spec)
    else:
        template = cv2.cvtColor(frame[10:16, 20:28], cv2.COLOR_BGR2GRAY).view(CustomArray)
        d = LocalCvDetector(spec, template_loader=lambda *_: template)
    expected = (*d.detect(frame), *d.detect(frame)); matches.clear()
    assert PerceptionEngine((d, d)).analyze(snap(frame)).observations == expected
    assert len(matches) == 2
    assert _measurements.get() is None
