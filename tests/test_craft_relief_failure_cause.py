"""Do not report an old full-inventory fact after a later technical failure."""
from types import SimpleNamespace
import pytest
from bot.equipment_relief import EquipmentReliefOutcome, EquipmentReliefResult
from bot.monster_wave_resource_route import MonsterWaveResourceRouteRuntime, ResourceRouteExecutionStatus
from tests.test_monster_wave_resource_route import (
    FakeCraft,FakeNavigation,FakeSnapshots,FakeKeys,FakeMaterials,_blocked_craft_fact,_plan,_anchor,
)


def runtime(composer,trace):
    class FullCraft(FakeCraft):
        def probe_equipment_capacity(self):
            self.trace.append('probe_capacity')
            return _blocked_craft_fact(20)
    return MonsterWaveResourceRouteRuntime(FakeNavigation(trace),FakeSnapshots(trace),FullCraft(trace),
        FakeKeys(trace),FakeMaterials(trace),equipment_relief=composer)


@pytest.mark.parametrize('outcome', [EquipmentReliefOutcome.CALLER_CONTEXT_FAILED,
                                   EquipmentReliefOutcome.CALLER_EXECUTION_FAILED])
def test_later_technical_cause_survives_without_retry_or_back(outcome):
    trace=[]
    actual=EquipmentReliefResult(outcome,'caller.retry_after_sell',
        error='CaptureError: Scrcpy socket closed unexpectedly')
    result=runtime(SimpleNamespace(run=lambda _:actual),trace).execute_plan_once(_plan(craft=True,keys=False),_anchor(10))
    assert result.status is ResourceRouteExecutionStatus.STEP_FAILED
    assert result.capability_result is actual
    assert trace==['mw_qm_craft','probe_capacity']


def test_unexpected_composer_exception_is_not_replaced_by_capacity():
    trace=[]
    def fail(_): raise RuntimeError('capture lost after confirmed craft')
    with pytest.raises(RuntimeError,match='capture lost after confirmed craft'):
        runtime(SimpleNamespace(run=fail),trace).execute_plan_once(_plan(craft=True,keys=False),_anchor(10))
    assert trace==['mw_qm_craft','probe_capacity']


def test_productive_caller_reports_later_error_without_resuming_consumption():
    from bot.monster_wave_resource_route import ResourceRouteExecutionResult
    from tests.test_monster_wave_productive import _Harness,_pending,READY
    class Harness(_Harness):
        def execute_plan_once(self,plan,anchor):
            self.calls.append(('J',))
            return ResourceRouteExecutionResult(ResourceRouteExecutionStatus.STEP_FAILED,
                failing_step='craft',capability_result=EquipmentReliefResult(
                    EquipmentReliefOutcome.CALLER_EXECUTION_FAILED,'caller.retry_after_sell',
                    error='CaptureError: Scrcpy socket closed unexpectedly'))
    harness=Harness(first=_pending(),plan=READY)
    result=harness.flow()._run_activity_l1()
    assert result.error=='preparation_failed:step_failed:craft:CaptureError: Scrcpy socket closed unexpectedly'
    assert sum(call[0]=='J' for call in harness.calls)==1
    assert ('pass',False,True) not in harness.calls
