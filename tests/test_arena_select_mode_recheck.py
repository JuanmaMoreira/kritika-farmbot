"""8c4c6b01: USER_GT confirms Select Mode opened despite the stream miss."""
from dataclasses import replace

import cv2
import pytest

from bot.arena_actions import ArenaControl as C
from bot.arena_flow_reader import ArenaFlowVisuals
from bot.flow_contracts import FlowStatus
from tests.test_arena_flow import World, flow


def setup(*, native='select_mode', cancel=False):
    w=World(); f=flow(w)
    capture=w.get_frame
    refresh=w.refresh_native
    rechecks=[]
    def stream():
        snapshot=capture()
        if w.surface=='select_mode':
            w.surface='unknown'
            image=w.image()
            w.surface='select_mode'
            return replace(snapshot,image=image)
        return snapshot
    def native_capture():
        if w.surface!='select_mode':return refresh()
        rechecks.append(w.now)
        snapshot=capture()
        if native=='pixels':
            snapshot=replace(snapshot,image=cv2.imread(
                'tests/fixtures/arena_previous_rewards/select_mode_before_01.png'))
        elif native=='stale':
            w.now+=5.
        elif native in ('pre_input','old_sequence'):
            snapshot=replace(snapshot,**{
                'pre_input':{'timestamp':f._barrier},
                'old_sequence':{'sequence':f._cursor},
            }[native])
        else:
            w.surface=native
            snapshot=replace(snapshot,image=w.image())
            w.surface='select_mode'
        if cancel:w.cancel=True
        return snapshot
    w.get_frame=stream; w.refresh_native=native_capture
    if native=='pixels':f.v.select_mode=ArenaFlowVisuals().select_mode
    return w,f,rechecks


@pytest.mark.parametrize('native',['select_mode','pixels'])
def test_stream_miss_uses_one_positive_native_guard_without_repeating_battle(native):
    w,f,rechecks=setup(native=native)
    result=f.run()
    assert result.succeeded and len(rechecks)==1
    assert w.inputs.count(C.BATTLE)==w.inputs.count(C.ARENA)==w.start_count==1
    assert 'select_mode_native_recheck' in result.evidence


@pytest.mark.parametrize('native',['unknown','lobby','loading','selection',
                                  'stale','pre_input','old_sequence'])
def test_missing_or_stale_native_authority_stops_without_followup(native):
    w,f,rechecks=setup(native=native)
    result=f.run()
    assert result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.error==('source_sequence_or_timestamp_regressed'
                          if native=='pre_input' else 'transition_unconfirmed')
    assert len(rechecks)==1 and w.inputs==[C.BATTLE] and w.start_count==0
    assert not result.physical_operation_may_be_active


def test_cancel_during_native_recheck_sends_no_arena_input():
    w,f,rechecks=setup(cancel=True)
    result=f.run()
    assert result.status is FlowStatus.CANCELLED
    assert len(rechecks)==1 and w.inputs==[C.BATTLE]


def test_positive_stream_guard_does_not_add_native_recheck():
    w=World(); result=flow(w).run()
    assert result.succeeded
    assert 'select_mode_native_recheck' not in result.evidence


def test_source_without_native_capture_preserves_stop_without_second_input():
    w,f,rechecks=setup()
    w.refresh_native=None
    result=f.run()
    assert result.error=='transition_unconfirmed'
    assert not rechecks and w.inputs==[C.BATTLE]
