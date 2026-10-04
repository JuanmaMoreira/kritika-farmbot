"""Currency's fixed Stamina50/K Coin200 offer; one verified batch."""
from bot.stages_actions import StageAction,StageControl as C
from bot.semantic_actions import OpenTrading,CloseTrading,ConfirmTradingTrade
from bot.event_log import record_best_effort
from bot.stages_runtime import lobby
from bot.runtime_observer import RuntimeWaitTimeout

# Existing C4 Available Trades ROI, read by the existing pair reader.
QUANTITY_ROI=(.592,.78,.66,.84)

class StaminaPurchase:
    def __init__(self,navigation,balances,detector):self.nav,self.balances,self.detector=navigation,balances,detector
    def _act(self,action,s):self.nav.act(action,s)
    def ready(self,s):return all(self.detector.present(s.frame.image,k) for k in ('currency','stamina_row'))
    def panel(self,s):return all(self.detector.present(s.frame.image,k) for k in ('stamina_panel','kcoin'))
    def quantity(self,s):
        selected,cap=self.balances.pair(s,QUANTITY_ROI)
        if not 1<=selected<=cap:raise ValueError('stamina trade quantity invalid')
        return selected,cap
    def ensure(self,before):
        # USER_GT: every trade yields exactly 50; fresh HAVE comes from the
        # caller's Lobby balance consensus. K Coins are available, no coin OCR.
        trades_needed=(max(0,300-before.stamina)+49)//50
        if not trades_needed:return before
        n=self.nav;started=n.clock()
        self._act(OpenTrading(),before.snapshot)
        s=n.wait(lambda s:self.detector.present(s.frame.image,'currency') or s.state.base_context=='screen.trading')
        self._act(StageAction(C.CURRENCY),s);s=n.wait(self.ready)
        self._act(StageAction(C.STAMINA_ROW),s);s=n.wait(self.panel)
        selected,cap=self.quantity(s)
        if selected!=1:raise ValueError('stamina trade initial quantity mismatch')
        if cap<trades_needed:
            record_best_effort(n.events,'stages.stamina_purchase.limit',trades_needed=trades_needed,cap=cap)
            raise ValueError(f'stamina trade cap {cap} below requested {trades_needed}')
        right_taps=trades_needed-1
        if right_taps:
            n.stamina_increments(right_taps,s)
            # Like productive C4 post-MAX: a fresh frame may precede the UI
            # quantity update. Wait for the requested final selection, never
            # retransmit setup taps or confirm from an intermediate.
            def final_quantity(item):
                if not self.panel(item):return False
                try: observed=self.quantity(item)
                except ValueError:return False
                record_best_effort(n.events,'stages.stamina_purchase.quantity_sample',
                    selected=observed[0],cap=observed[1],requested=trades_needed,
                    source_sequence=item.sequence)
                return observed==(trades_needed,cap)
            try:s=n.wait(final_quantity)
            except (RuntimeWaitTimeout,TimeoutError) as error:
                raise ValueError('stamina trade selected quantity mismatch') from error
        elif self.quantity(s)!=(trades_needed,cap):
            raise ValueError('stamina trade selected quantity mismatch')
        record_best_effort(n.events,'stages.stamina_purchase.selected',
            stamina_before=before.stamina,trades_needed=trades_needed,selected=trades_needed,cap=cap,right_taps=right_taps)
        self._act(ConfirmTradingTrade(),s)
        # One consuming confirmation. Inconclusive effect never repeats it.
        s=n.wait(lambda s:self.ready(s) and not self.detector.present(s.frame.image,'stamina_panel'))
        self._act(CloseTrading(),s);n.wait(lobby)
        after=self.balances.read()
        if after.stamina<300:raise ValueError('stamina batch effect unverified: fresh stamina below 300')
        record_best_effort(n.events,'stages.stamina_purchase',
            stamina_before=before.stamina,stamina_after=after.stamina,
            trades=trades_needed,right_taps=right_taps,confirmations=1,kcoin_cost=200*trades_needed,
            elapsed=n.clock()-started)
        return after
