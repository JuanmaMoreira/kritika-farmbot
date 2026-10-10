"""Ice Warlock/Eilla: Combine NO_RELIEF -> direct Lobby Inventory."""
from types import SimpleNamespace as NS
from bot.stages_reliefs import StagesReliefs
from bot.stages_actions import StageControl, StageAction, POINTS
from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL as FULL
from bot.state import ResolutionStatus
from bot.equipment_relief import EquipmentReliefResult, EquipmentReliefOutcome

def test_sell_fallback_uses_lobby_direct_inventory_without_qm_or_new_start():
    calls=[]
    s=NS(sequence=12,state=NS(status=ResolutionStatus.RESOLVED,base_context='screen.lobby',overlays=()))
    def wait(predicate,**kwargs):
        assert predicate(s)
        calls.append('fresh_lobby');return s
    nav=NS(events=None,exit_to_lobby=lambda:calls.append('lobby'),wait=wait,
        act=lambda action,s:calls.append(action),clock=lambda:100.,cancel_requested=lambda:False)
    runtime=NS(_after_sequence=0,_not_before=0.)
    def run(request):
        # Real composer selects this callback after Combine yields no relief.
        request.sell_plan.enter_inventory(None)
        return EquipmentReliefResult(EquipmentReliefOutcome.CALLER_RESULT,'caller.result_after_sell',caller_result=s)
    equipment=NS(run=run,sell_runtime=runtime)
    deps=NS()  # default coordinator policy, no physical owners invoked here
    result=StagesReliefs(nav,deps,equipment)(StageControl.START,
        NS(state=NS(overlays=(FULL,))),{'start'})
    assert result is s
    assert calls==['lobby','fresh_lobby',StageAction(StageControl.LOBBY_INVENTORY)]
    assert runtime._after_sequence==12 and runtime._not_before==100.
    assert POINTS[StageControl.LOBBY_INVENTORY]==(.655,.75)
