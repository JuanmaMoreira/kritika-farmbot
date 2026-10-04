"""Stages caller adapters; inventory policy and relief execution stay global."""
from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL, SCREEN_COMBINE, SCREEN_SOCKET, MENU_QUICK
from bot.semantic_actions import (OpenEquipmentCombine, AcceptSocketInventoryFull,
    ExitCombine, ExitSocket, OpenQuickMenu, SelectQuickMenuInventory, ExitEquipmentInventory)
from bot.equipment_combine_relief import EquipmentCombineReturnPlan
from bot.equipment_relief import EquipmentReliefRequest, EquipmentReliefSellPlan, FreshCallerContext
from bot.socket_inventory_relief import SocketReturnPlan
from bot.stages_runtime import lobby, exposed
from bot.perception.stages import surface
from bot.runtime_observer import RuntimeWaitCancelled,RuntimeWaitTimeout
from bot.event_log import record_best_effort

class StagesReliefs:
    def __init__(self, nav, dependencies, equipment):
        self.nav,self.dependencies,self.equipment=nav,dependencies,equipment
        self.used=set()

    def reset(self):
        """The relief bound belongs to one run(), never the next character."""
        self.used.clear()

    def __call__(self, control, initial, expected):
        n=self.nav
        blockers={POPUP_EQUIPMENT_INVENTORY_FULL,POPUP_SOCKET_INVENTORY_FULL}.intersection(initial.state.overlays)
        if len(blockers)!=1:raise ValueError('stages relief upper layer ambiguous')
        blocker=next(iter(blockers))
        if blocker in self.used:raise ValueError('stages relief bound exhausted')
        self.used.add(blocker)
        record_best_effort(n.events,'stages.relief',blocker=blocker)
        def restored(s):return lobby(s) or (exposed(s) and surface(s) in {'normal','config'})
        def enter(action,destination):
            s=n.wait(lambda s:blocker in s.state.overlays)
            n.act(action,s)
            try:return n.wait(lambda s:s.state.base_context==destination,timeout=8.)
            except RuntimeWaitTimeout as error:
                recovery=self.dependencies.build_obstruction_recovery()
                recovered=recovery.attempt(error.last_snapshot,
                    lambda a:a.state.base_context==destination,
                    regions=((.165,.125,.36,.215),),stages_entry_source=s)
                if recovered is None:raise
                n.cursor=recovered.sequence
                return n.wait(lambda a:a.state.base_context==destination,timeout=6.)
        def config(after=None):
            if after is not None:n.cursor=max(n.cursor,after)
            s=n.wait(restored)
            if lobby(s):return n.enter_target()
            if surface(s)=='normal':
                from bot.stages_actions import StageControl as C
                return n.change(C.STAGE8,s,{'config'})
            return s
        if blocker==POPUP_SOCKET_INVENTORY_FULL:
            enter(AcceptSocketInventoryFull(),SCREEN_SOCKET)
            # Socket's existing return contract identifies Stages base after Back.
            result=self.dependencies.socket_relief.run(SocketReturnPlan(ExitSocket(),'screen.stages'),cancel_requested=n.cancel_requested)
            if result.outcome.value=='cancelled':raise RuntimeWaitCancelled('socket relief cancelled')
            if not result.succeeded:raise ValueError('stages socket relief: '+str(result.error))
            s=config(result.final_snapshot.sequence)
            return n.change(control,s,expected)
        first=True
        def acquire(after):
            if after is None:s=n.wait(lambda s:blocker in s.state.overlays)
            else:s=config(after)
            return FreshCallerContext(s,s.sequence)
        def execute(_,s):
            nonlocal first
            if first:first=False;return initial
            return n.change(control,s,expected)
        def enter_inventory(_):
            n.exit_to_lobby()
            s=n.wait(lobby);n.act(OpenQuickMenu(),s)
            s=n.wait(lambda s:set(s.state.overlays)=={MENU_QUICK})
            from bot.stages_actions import StageAction, StageControl
            # Lobby's menu is at the left edge; the existing Craft intent is
            # explicitly for its shifted menu and would open Socket here.
            n.act(StageAction(StageControl.LOBBY_INVENTORY),s)
            self.equipment.sell_runtime._after_sequence=s.sequence
            self.equipment.sell_runtime._not_before=n.clock()
        def return_inventory(result):
            # Reader verified the exposed inventory after all global reliefs.
            self.equipment.sell_runtime._tap(ExitEquipmentInventory())
            n.cursor=result.after.sequence;n.dispatched_at=n.clock()
            n.wait(lobby,timeout=8.)
            return n.enter_target().sequence
        request=EquipmentReliefRequest(control,acquire,execute,
            lambda s:blocker in s.state.overlays,
            lambda _:enter(OpenEquipmentCombine(),SCREEN_COMBINE),
            EquipmentCombineReturnPlan(ExitCombine(),'screen.stages',restored),
            EquipmentReliefSellPlan(self.dependencies.config.equipment_sell,enter_inventory,return_inventory),
            n.cancel_requested)
        result=self.equipment.run(request)
        if 'cancelled' in result.outcome.value:raise RuntimeWaitCancelled('equipment relief cancelled')
        if not result.returned_caller_result:raise ValueError('stages equipment relief: '+str(result.error or result.stage))
        return result.caller_result
