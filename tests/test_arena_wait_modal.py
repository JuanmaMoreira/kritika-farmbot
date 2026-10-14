"""f1c7e36e: a single nonterminal modal signal stopped a running Auto Repeat."""
import pytest

from bot.arena_actions import ArenaControl as C
from bot.flow_contracts import FlowStatus
from tests.test_arena_flow import World, flow
from tests.test_arena_b2 import SingleWorld, single_flow


@pytest.mark.parametrize('modal',['ranking','insufficient'])
def test_transient_modal_during_batch_is_observed_until_positive_terminal(modal):
    w=World(); w.wait_states=['loading','battle',modal,'battle','terminal']
    result=flow(w).run()
    assert result.succeeded and result.batch_result is not None
    assert w.start_count==1 and C.RANKING_OK not in w.inputs
    assert w.inputs.count(C.BADGES_NO)==1  # Only after the credited batch result.
    assert result.metrics['wait_ocr_calls']==0
    assert 'unrecognized_wait_surface' in result.evidence


@pytest.mark.parametrize('modal',['ranking','insufficient'])
def test_modal_persistence_still_stops_without_any_acknowledgement(modal):
    w=World(); w.wait_states=['loading',modal]
    result=flow(w).run()
    assert result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.error=='nonterminal_modal_during_batch'
    assert result.metrics['wait_elapsed']>=3.
    assert result.physical_operation_may_be_active and not result.execution.start_verified
    assert w.start_count==1
    assert all(c not in w.inputs for c in (C.RANKING_OK,C.BADGES_NO,C.RESULT_OK))


def test_known_activity_between_modal_signals_resets_persistence():
    w=World(); w.wait_states=['loading','ranking','battle','ranking','battle','terminal']
    result=flow(w).run()
    assert result.succeeded and w.start_count==1


def test_auto_repeat_configuration_without_activity_band_is_a_known_wait_surface():
    w=World(); w.wait_states=['loading']+['config']*5+['battle','terminal']
    result=flow(w).run()
    assert result.succeeded and result.metrics['wait_elapsed']>3.
    assert w.start_count==1 and w.inputs.count(C.CONFIG)==1
    assert 'unrecognized_wait_surface' not in result.evidence
    assert result.metrics['wait_ocr_calls']==0


def test_auto_repeat_configuration_still_has_the_overall_batch_bound():
    w=World(); w.wait_states=['loading','config']
    result=flow(w).run()
    assert result.error=='batch_terminal_timeout'
    assert result.physical_operation_may_be_active and w.start_count==1
    assert all(c not in w.inputs for c in (C.RANKING_OK,C.BADGES_NO,C.RESULT_OK))


@pytest.mark.parametrize('modal',['ranking','insufficient'])
def test_single_battle_also_waits_past_transient_modal_signal(modal):
    w=SingleWorld(); w.single_wait_states=['loading',modal,'battle','single_result']
    result=single_flow(w).run()
    assert result.succeeded and w.start_count==1
    assert all(c not in w.inputs for c in (C.RANKING_OK,C.BADGES_NO,C.RESULT_OK))


def test_cancel_during_modal_wait_does_not_close_or_restart_game():
    w=World(); w.wait_states=['loading','ranking']
    original=w.get_frame
    def capture():
        snapshot=original()
        if w.surface=='ranking':w.cancel=True
        return snapshot
    w.get_frame=capture
    result=flow(w).run()
    assert result.status is FlowStatus.CANCELLED and result.physical_operation_may_be_active
    assert w.start_count==1
    assert all(c not in w.inputs for c in (C.RANKING_OK,C.BADGES_NO,C.RESULT_OK))
