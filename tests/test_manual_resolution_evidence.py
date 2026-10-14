"""Persist actual owner pixels at technical manual stops, without hardware."""
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from bot.adb import AdbClient
from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot, ScrcpyFrameSource
from bot.failure_cause import FailureCause
from bot.failure_evidence import publish_failure
from bot.flow_contracts import FlowResult, FlowStatus
from bot.session import SessionStatus
from tests.test_arena_b2 import ReturnWorld
from tests.test_arena_flow import flow, C
from tests.test_failure_evidence import setup_stream, bundle_path, fail
from tests.test_productive_runtime import _runtime
from tests.test_session import Flow, Rotation, _runner
from tests.test_daily_quests_flow import snapshot


def test_native_owner_pixels_survive_stale_observer_and_mutation(tmp_path):
    evidence, stream, records = setup_stream(tmp_path)
    evidence.observe(snapshot(1, 1., base='screen.lobby'))
    original = np.random.default_rng(4).integers(0, 256, (1220, 2712, 3), dtype=np.uint8)
    adb = Mock(spec=AdbClient)
    source = ScrcpyFrameSource(adb, 'unused', clock=lambda: 10., frame_consumer=evidence.observe_frame)
    source._publish(np.zeros_like(original), timestamp=2.)
    source.get_frame()
    adb.capture_png.return_value = cv2.imencode('.png', original)[1].tobytes()
    native = source.refresh_native()
    # A cached get_frame cannot relabel native provenance or evict its pixels.
    source.get_frame()
    native.image[:] = 0
    failure = publish_failure(stream, 'flow.manual_resolution', None, error='transition_unconfirmed')
    path = bundle_path(failure.evidence_ref)
    bundle = json.loads(path.read_text())
    entry = bundle['snapshots'][-1]
    assert entry['sequence'] == native.sequence
    metadata = json.loads((path.parent/entry['snapshot']).read_text())
    assert metadata['capture'] == {'source': 'native', 'original_shape': [1220, 2712, 3]}
    assert 'state' not in metadata  # Do not attach the previous Lobby resolution.
    assert np.array_equal(cv2.imread(str(path.parent/entry['frame'])), original)
    assert records[-1].fields['failure']['evidence_ref'] == failure.evidence_ref
    assert native.timestamp == 10. and source.get_frame().sequence == native.sequence
    evidence.close()
    assert evidence.retained_bytes == 0


def test_same_frame_resolution_keeps_full_pixels_and_semantics(tmp_path):
    evidence, stream, _ = setup_stream(tmp_path)
    image = np.full((1100, 2200, 3), 140, np.uint8)
    semantic = snapshot(3, 3., base='screen.lobby')
    semantic = replace(semantic, frame=FrameSnapshot(image, 3., 3),
                       geometry=FrameGeometry.from_frame(image))
    evidence.observe_frame(FrameSnapshot(image, 3., 3), 'stream')
    evidence.observe(semantic)
    failure = publish_failure(stream, 'flow.failed', FailureCause('failed', 'miss'))
    path = bundle_path(failure.evidence_ref)
    data = json.loads((path.parent/'snapshot_3.json').read_text())
    assert data['state']['base_context'] == 'screen.lobby'
    assert data['frame']['width'] == 2200
    assert cv2.imread(str(path.parent/'frame_3.png')).shape == image.shape


def test_capture_memory_bound_and_closed_collector_do_not_affect_source(tmp_path, monkeypatch):
    import bot.failure_evidence as module
    monkeypatch.setattr(module, 'MAX_CAPTURE_BYTES', 1024)
    evidence, stream, _ = setup_stream(tmp_path)
    source = ScrcpyFrameSource(Mock(spec=AdbClient), 'unused', clock=lambda: 4.,
                               frame_consumer=evidence.observe_frame)
    image = np.full((80, 160, 3), 150, np.uint8)
    source._publish(image, timestamp=3.)
    assert source.get_frame().image.shape == image.shape
    assert evidence.retained_bytes < 2048
    failure = publish_failure(stream, 'flow.manual_resolution', None, error='miss')
    path = bundle_path(failure.evidence_ref)
    metadata = json.loads((path.parent/'snapshot_1.json').read_text())
    assert metadata['capture']['original_shape'] == list(image.shape)
    assert cv2.imread(str(path.parent/'frame_1.png')).nbytes <= 1024
    evidence.close()
    source._publish(image, timestamp=4.)
    assert np.array_equal(source.get_frame().image, image)
    assert evidence.retained_bytes == 0


@pytest.mark.parametrize('enabled', [False, True, 'failed_writer'])
def test_arena_direct_capture_manual_stop_persists_and_does_not_change_inputs(tmp_path, enabled):
    evidence, stream, records = setup_stream(tmp_path)
    if enabled is False:
        stream.failure_evidence = None
    elif enabled == 'failed_writer':
        evidence._write = fail
    world = ReturnWorld()
    take = world.get_frame
    source = ScrcpyFrameSource(Mock(spec=AdbClient), 'unused', clock=world.clock,
                               frame_consumer=evidence.observe_frame)

    def get_frame():
        frame = take()
        source._publish(frame.image, timestamp=frame.timestamp)
        return source.get_frame()

    def refresh_native():
        frame = take()
        source.adb.capture_png.return_value = cv2.imencode('.png', frame.image)[1].tobytes()
        return source.refresh_native()

    world.get_frame, world.refresh_native = get_frame, refresh_native
    operation = flow(world, return_context='screen.lobby', events=stream)
    # Reproduce the reported cut: Back reaches Select Mode, but CV misses it.
    select_mode = operation.v.select_mode
    operation.v.select_mode = lambda image: select_mode(image) and world.inputs.count(C.BACK) < 2
    trace = []
    following = Flow('following', [FlowResult(FlowStatus.COMPLETED)], trace)
    rotation = Rotation(1, trace)
    runner, _ = _runner(1, [operation, following], rotation)
    runner.events = stream
    result = runner.run()
    stopped = result.character_results[0].flow_results[0]
    assert result.status is SessionStatus.MANUAL_RESOLUTION
    assert stopped.error == 'transition_unconfirmed' and stopped.phase == 'external_return'
    assert stopped.batch_result is not None and not stopped.physical_operation_may_be_active
    assert world.inputs[-2:] == [C.BACK, C.BACK] and world.start_count == 1
    assert world.inputs.count(C.BACK) == 2 and not trace and not rotation.calls
    assert bool(stopped.failure.evidence_ref) == (enabled is True)
    assert result.failure == stopped.failure
    if enabled is True:
        path = bundle_path(stopped.failure.evidence_ref)
        bundle = json.loads(path.read_text())
        entry = bundle['snapshots'][-1]
        assert entry['sequence'] == stopped.evidence['stopped'].sequence
        assert np.array_equal(cv2.imread(str(path.parent/entry['frame'])), stopped.evidence['stopped'].image)
        assert len(list(evidence.root.iterdir())) == 1
        terminals = [r for r in records if r.event in ('flow.manual_resolution', 'session.manual_resolution')]
        assert all(r.fields['failure']['evidence_ref'] == stopped.failure.evidence_ref for r in terminals)
        assert bundle['event']['flow'] == 'arena'
    elif enabled == 'failed_writer':
        assert any('evidence_error' in record.fields for record in records)


@pytest.mark.parametrize('name', ['mailbox', 'monster_wave', 'arena'])
def test_any_technical_manual_flow_gets_one_session_bundle(tmp_path, name):
    evidence, stream, _ = setup_stream(tmp_path)
    trace = []
    owner = Flow(name, [FlowResult(FlowStatus.MANUAL_RESOLUTION, error='readiness_uncredited')], trace)
    runner, _ = _runner(1, [owner], Rotation(1, trace))
    runner.events = stream
    result = runner.run()
    assert result.status is SessionStatus.MANUAL_RESOLUTION
    assert result.failure.evidence_ref
    assert len(list(evidence.root.iterdir())) == 1
    assert trace == [name+'.run']


@pytest.mark.parametrize('status', [FlowStatus.MANUAL_RESOLUTION, FlowStatus.CANCELLED,
                                  FlowStatus.COMPLETED])
def test_nontechnical_outcomes_do_not_create_bundle(tmp_path, status):
    evidence, stream, _ = setup_stream(tmp_path)
    trace = []
    runner, _ = _runner(1, [Flow('owner', [FlowResult(status)], trace)], Rotation(1, trace))
    runner.events = stream
    runner.run()
    assert not evidence.root.exists()


def test_standalone_manual_resolution_links_the_same_cause(tmp_path):
    evidence, stream, records = setup_stream(tmp_path)
    runtime = _runtime(object(), stream)
    runtime.build_flow = lambda _: Flow('owner', [FlowResult(FlowStatus.MANUAL_RESOLUTION, error='miss')], [])
    runtime.build_preconditions = lambda: SimpleNamespace(ensure=lambda _: SimpleNamespace(succeeded=True))
    result = runtime.run_flow(SimpleNamespace(id='owner'))
    assert result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.failure.evidence_ref == records[-1].fields['failure']['evidence_ref']
    assert len(list(evidence.root.iterdir())) == 1


def test_standalone_controlled_resource_pending_does_not_create_bundle(tmp_path):
    evidence, stream, _ = setup_stream(tmp_path)
    runtime = _runtime(object(), stream)
    runtime.build_flow = lambda _: Flow('owner', [FlowResult(FlowStatus.RESOURCE_BOARD_PENDING,
                                                           error='resource_unavailable')], [])
    runtime.build_preconditions = lambda: SimpleNamespace(ensure=lambda _: SimpleNamespace(succeeded=True))
    result = runtime.run_flow(SimpleNamespace(id='owner'))
    assert result.status is FlowStatus.RESOURCE_BOARD_PENDING
    assert result.error == 'resource_unavailable' and result.failure.evidence_ref is None
    assert not evidence.root.exists()


@pytest.mark.parametrize('event', ['flow.manual_resolution', 'session.manual_resolution'])
@pytest.mark.parametrize('kind,exception', [
    ('cancelled', None), ('cancellation', None),
    ('exception', 'RuntimeWaitCancelled'), ('exception', 'KeyboardInterrupt'),
    ('exception', 'SystemExit'), ('exception', 'CancelledError'),
])
def test_manual_cancellation_causes_never_write(tmp_path, event, kind, exception):
    evidence, stream, records = setup_stream(tmp_path)
    cause = FailureCause(kind, 'original', exception_type=exception)
    assert publish_failure(stream, event, cause) is cause
    assert records[-1].fields['failure'] == cause.payload()
    assert not evidence.root.exists()


def test_manual_structured_cause_without_error_keeps_domain_fields(tmp_path):
    evidence, stream, _ = setup_stream(tmp_path)
    cause = FailureCause('transition', 'unconfirmed', flow='owner', step='return', sequence=7)
    trace = []
    runner, _ = _runner(1, [Flow('owner', [FlowResult(FlowStatus.MANUAL_RESOLUTION,
                                                  failure=cause)], trace)], Rotation(1, trace))
    runner.events = stream
    result = runner.run()
    stopped = result.character_results[0].flow_results[0]
    assert stopped.error is None and stopped.status is FlowStatus.MANUAL_RESOLUTION
    assert replace(result.failure, evidence_ref=None) == cause
    assert stopped.failure == result.failure
    assert len(list(evidence.root.iterdir())) == 1


def test_direct_capture_joins_window_without_stale_semantics_or_duplicate_files(tmp_path):
    evidence, stream, _ = setup_stream(tmp_path)
    for sequence in (1, 2, 3):
        evidence.observe(snapshot(sequence, float(sequence), base='screen.lobby'))
    image = np.full((10, 20, 3), 140, np.uint8)
    evidence.observe_frame(FrameSnapshot(image, 4., 4), 'native')
    evidence.observe_frame(FrameSnapshot(np.zeros_like(image), 3., 3), 'stream')
    evidence.observe_frame(FrameSnapshot(np.zeros_like(image), 4., 4), 'stream')
    failure = publish_failure(stream, 'flow.manual_resolution', None, error='miss')
    path = bundle_path(failure.evidence_ref)
    bundle = json.loads(path.read_text())
    assert [entry['sequence'] for entry in bundle['snapshots']] == [2, 3, 4]
    for entry in bundle['snapshots']:
        metadata = json.loads((path.parent/entry['snapshot']).read_text())
        frame = cv2.imread(str(path.parent/entry['frame']))
        assert metadata['frame']['file'] == entry['frame']
        assert frame.shape[:2] == (metadata['frame']['height'], metadata['frame']['width'])
    metadata = json.loads((path.parent/'snapshot_4.json').read_text())
    assert metadata['capture']['source'] == 'native' and 'state' not in metadata
    assert np.array_equal(cv2.imread(str(path.parent/'frame_4.png')), image)


def test_bad_capture_callback_does_not_change_frame_delivery():
    source = ScrcpyFrameSource(Mock(spec=AdbClient), 'unused', clock=lambda: 3., frame_consumer=fail)
    image = np.full((8, 16, 3), 60, np.uint8)
    source._publish(image, timestamp=2.)
    assert np.array_equal(source.get_frame().image, image)
    source.adb.capture_png.return_value = cv2.imencode('.png', image)[1].tobytes()
    assert source.refresh_native().timestamp == 3.
