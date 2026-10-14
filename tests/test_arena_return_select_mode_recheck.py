"""0feb44fb stopped after the second Back while awaiting Arena Select Mode."""
from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from bot.arena_actions import ArenaControl as C
from bot.arena_flow_reader import ArenaFlowVisuals
from bot.flow_contracts import FlowStatus
from tests.test_arena_b2 import ReturnWorld
from tests.test_arena_flow import flow


def setup(*, native='select_mode', cancel=False):
    world = ReturnWorld()
    operation = flow(world, return_context='screen.lobby')
    capture = world.get_frame
    refresh = world.refresh_native
    rechecks = []

    def stream():
        snapshot = capture()
        if world.inputs.count(C.BACK) == 2 and world.surface == 'select_mode':
            world.surface = 'unknown'
            image = world.image()
            world.surface = 'select_mode'
            return replace(snapshot, image=image)
        return snapshot

    def native_capture():
        if world.inputs.count(C.BACK) != 2:
            return refresh()
        rechecks.append(world.now)
        snapshot = capture()
        if native == 'pixels':
            path = Path(__file__).resolve().parent/'fixtures/arena_b2/select_mode_native.png'
            snapshot = replace(snapshot, image=cv2.imread(str(path)))
        elif native == 'stale':
            world.now += operation.reader.max_age + 1.
        elif native in ('pre_input', 'old_sequence', 'future'):
            snapshot = replace(snapshot, **{
                'pre_input': {'timestamp': operation._barrier},
                'old_sequence': {'sequence': operation._cursor},
                'future': {'timestamp': world.now + 3.},
            }[native])
        else:
            world.surface = native
            snapshot = replace(snapshot, image=world.image())
            world.surface = 'select_mode'
        if cancel:
            world.cancel = True
        return snapshot

    world.get_frame = stream
    world.refresh_native = native_capture
    if native == 'pixels':
        real = ArenaFlowVisuals()
        select_mode, back_visible = operation.v.select_mode, operation.v.back_visible
        operation.v.select_mode = lambda image: (real.select_mode(image)
            if image.shape[0] > 90 else select_mode(image))
        operation.v.back_visible = lambda image: (real.back_visible(image)
            if image.shape[0] > 90 else back_visible(image))
    return world, operation, rechecks


@pytest.mark.parametrize('native', ['select_mode', 'pixels'])
def test_return_stream_miss_uses_one_native_guard_before_final_back(native):
    world, operation, rechecks = setup(native=native)
    result = operation.run()
    assert result.succeeded and len(rechecks) == 1
    assert world.inputs[-3:] == [C.BACK]*3
    assert world.start_count == 1 and result.batch_result.used_tickets == 104
    assert result.final_snapshot.state.base_context == 'screen.lobby'
    assert 'return_select_mode_native_recheck' in result.evidence


@pytest.mark.parametrize('native', ['unknown', 'lobby', 'loading', 'selection',
                                   'stale', 'pre_input', 'old_sequence', 'future'])
def test_negative_or_nonfresh_native_stops_without_another_back_or_start(native):
    world, operation, rechecks = setup(native=native)
    result = operation.run()
    assert result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.error == ('source_sequence_or_timestamp_regressed'
                            if native == 'pre_input' else 'transition_unconfirmed')
    assert len(rechecks) == 1 and world.inputs.count(C.BACK) == 2
    assert world.start_count == 1 and result.batch_result is not None
    assert not result.physical_operation_may_be_active


def test_cancellation_during_native_return_does_not_send_final_back():
    world, operation, rechecks = setup(cancel=True)
    result = operation.run()
    assert result.status is FlowStatus.CANCELLED
    assert len(rechecks) == 1 and world.inputs.count(C.BACK) == 2
    assert world.start_count == 1 and not result.physical_operation_may_be_active


def test_native_unavailable_at_return_preserves_original_stop():
    world, operation, rechecks = setup()
    execute = world.execute

    def dispatch(action, geometry, **kwargs):
        execute(action, geometry, **kwargs)
        if world.inputs.count(C.BACK) == 2:
            world.refresh_native = None

    world.execute = dispatch
    result = operation.run()
    assert result.error == 'transition_unconfirmed' and not rechecks
    assert world.inputs.count(C.BACK) == 2 and world.start_count == 1


def test_positive_stream_return_does_not_add_native_recheck():
    world = ReturnWorld()
    result = flow(world, return_context='screen.lobby').run()
    assert result.succeeded
    assert 'return_select_mode_native_recheck' not in result.evidence
