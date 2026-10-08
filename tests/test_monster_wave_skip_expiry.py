"""SKIP can expire during Equipment relief; retry uses fresh normal preparation."""
import pytest
from bot.flow_contracts import FlowStatus
from bot.monster_wave_actions import ActivateMonsterWaveSkip
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE,MW_MAX
from test_monster_wave import Device,MAX,NEEDS,READY

class PersistentMax(Device):
    def execute(self,action,geometry):
        super().execute(action,geometry)
        if isinstance(action,ActivateMonsterWaveSkip):self.names=MAX

@pytest.mark.parametrize('expired,expected',[
    (NEEDS,['OpenMonsterWaveTickets','FillMonsterWaveTickets','CloseMonsterWaveTickets','ActivateMonsterWaveSkip']),
    (READY,['ActivateMonsterWaveSkip']),
])
def test_retry_after_expiry_reprepares_then_resumes_without_reentry_or_max_retap(expired,expected):
    d=PersistentMax();a=d.activity()
    assert a.prepare().succeeded
    d.intents.clear();d.names=expired
    result=a.run_pass(resume_after_relief=True)
    assert result.succeeded
    assert d.intents==expected+['StartMonsterWaveSkip','AcknowledgeMonsterWaveClear']
    assert result.event_count('monster_wave.skip_reprepare')==1

def test_failed_fill_all_stops_without_activate_or_start():
    d=Device(base=SCREEN_MONSTER_WAVE,purchase_ok=False);d.names=NEEDS
    result=d.activity().run_pass(resume_after_relief=True)
    assert result.status is FlowStatus.FAILED
    assert d.intents==['OpenMonsterWaveTickets','FillMonsterWaveTickets']

def test_cancel_after_fill_all_stops_before_activation():
    d=Device(base=SCREEN_MONSTER_WAVE);d.names=NEEDS;d.cancel_after='FillMonsterWaveTickets'
    assert d.activity().run_pass(resume_after_relief=True).status is FlowStatus.CANCELLED
    assert d.intents==['OpenMonsterWaveTickets','FillMonsterWaveTickets']

def test_unrecognized_skip_or_occluded_max_does_not_authorize_preparation():
    for names in ((),(MW_MAX,)):
        d=Device(base=SCREEN_MONSTER_WAVE);d.names=names
        result=d.activity().run_pass(resume_after_relief=True)
        assert result.status is FlowStatus.FAILED and d.intents==[]
