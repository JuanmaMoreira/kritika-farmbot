"""Currency's fixed Stamina50/K Coin200 offer; one verified batch."""
from bot.stages_actions import StageAction,StageControl as C
from bot.semantic_actions import OpenTrading,CloseTrading,ConfirmTradingTrade,CancelTradingTrade
from dataclasses import dataclass
from bot.event_log import record_best_effort
from bot.stages_runtime import lobby
from bot.runtime_observer import RuntimeWaitTimeout

# Existing C4 Available Trades ROI, read by the existing pair reader.
QUANTITY_ROI=(.592,.78,.66,.84)
PAYMENT_ROI=(.54,.34,.65,.385)  # Existing Item Trade input HAVE / total cost.

@dataclass(frozen=True)
class StaminaSupplyResult:
    balances: object
    required: int
    purchased: int = 0
    outcome: str = 'sufficient'
    kcoin_cost: int | None = None

    @property
    def covered(self):return self.balances.stamina >= self.required

class StaminaPurchase:
    def __init__(self,navigation,balances,detector):
        self.nav,self.balances,self.detector=navigation,balances,detector
        self.pending=None
    def _act(self,action,s):self.nav.act(action,s)
    def ready(self,s):return all(self.detector.present(s.frame.image,k) for k in ('currency','stamina_row'))
    def panel(self,s):return all(self.detector.present(s.frame.image,k) for k in ('stamina_panel','kcoin'))
    def quantity(self,s,*,allow_empty=False):
        try:selected,cap=self.balances.pair(s,QUANTITY_ROI)
        except ValueError:
            # The general balance reader deliberately rejects zero capacity.
            # Only an explicit zero Available Trades in this known panel means
            # depletion; a reader miss still cannot authorize any input.
            if allow_empty and self.balances.text(s,QUANTITY_ROI).replace(' ','')=='0/0':return 0,0
            raise
        if allow_empty and (selected,cap)==(0,0):return 0,0
        if not 1<=selected<=cap:raise ValueError('stamina trade quantity invalid')
        return selected,cap
    def ensure(self,before):
        # USER_GT: every trade yields exactly 50; fresh HAVE comes from the
        # caller's Lobby balance consensus. K Coins are available, no coin OCR.
        return self._buy(before,300,manual=False).balances

    def supply(self,before,required):
        """One bounded visit for Manual Stages; Ads retains its 300 default."""
        if type(required) is not int or required<0:raise ValueError('invalid stamina demand')
        if self.pending is not None:
            # Reconcile the payment causally, rather than mistaking natural
            # regeneration for a successful purchase. Never another Trade.
            previous,trades,target,kcoins_before=self.pending
            n=self.nav
            s=n.wait(lambda s:lobby(s) or self.ready(s) or self.panel(s))
            if lobby(s):
                self._act(OpenTrading(),s)
                s=n.wait(lambda s:self.detector.present(s.frame.image,'currency') or s.state.base_context=='screen.trading')
                self._act(StageAction(C.CURRENCY),s);s=n.wait(self.ready)
            if self.ready(s) and not self.panel(s):
                self._act(StageAction(C.STAMINA_ROW),s);s=n.wait(self.panel)
            have,_=self.balances.pair(s,PAYMENT_ROI)
            if have!=kcoins_before-200*trades:
                raise ValueError('previous stamina payment unresolved')
            self._act(CancelTradingTrade(),s)
            s=n.wait(lambda s:self.ready(s) and not self.panel(s))
            self._act(CloseTrading(),s);n.wait(lobby)
            after=self.balances.read()
            if after.stamina < previous.stamina+50*trades:
                raise ValueError('previous stamina transaction unresolved')
            self.pending=None
            return StaminaSupplyResult(after,target,50*trades,
                'purchased' if after.stamina>=target else 'partial', kcoin_cost=200*trades)
        return self._buy(before,required,manual=True)

    def _buy(self,before,required,*,manual):
        trades_needed=(max(0,required-before.stamina)+49)//50
        if not trades_needed:return StaminaSupplyResult(before,required)
        n=self.nav;started=n.clock()
        self._act(OpenTrading(),before.snapshot)
        s=n.wait(lambda s:self.detector.present(s.frame.image,'currency') or s.state.base_context=='screen.trading')
        self._act(StageAction(C.CURRENCY),s);s=n.wait(self.ready)
        self._act(StageAction(C.STAMINA_ROW),s);s=n.wait(self.panel)
        selected,cap=self.quantity(s,allow_empty=manual)
        if manual and cap==0:
            self._act(CancelTradingTrade(),s)
            s=n.wait(lambda s:self.ready(s) and not self.panel(s))
            self._act(CloseTrading(),s);n.wait(lobby)
            return StaminaSupplyResult(self.balances.read(),required,outcome='trade_limit')
        if manual and cap>20:raise ValueError('stamina trade cap outside acquired bounds')
        if selected!=1:raise ValueError('stamina trade initial quantity mismatch')
        boundary=None
        if manual:
            have,cost=self.balances.pair(s,PAYMENT_ROI)
            if cost!=200:raise ValueError('stamina payment is not the acquired K Coin200 offer')
            allowed=min(trades_needed,cap,have//200)
            boundary='insufficient_kcoins' if have//200<min(trades_needed,cap) else 'trade_limit'
            if not allowed:
                # Known panel; acquired Cancel closes only Item Trade.
                self._act(CancelTradingTrade(),s)
                s=n.wait(lambda s:self.ready(s) and not self.panel(s))
                self._act(CloseTrading(),s);n.wait(lobby)
                return StaminaSupplyResult(self.balances.read(),required,outcome=boundary)
            trades_needed=allowed
        elif cap<trades_needed:
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
        if manual:
            # Fresh payment authority after quantity setup. No premium input,
            # changed price, or unresolved prior confirmation can authorize Trade.
            s=n.wait(self.panel)
            if self.quantity(s)!=(trades_needed,cap):raise ValueError('stamina quantity changed')
            have,cost=self.balances.pair(s,PAYMENT_ROI)
            if cost!=200*trades_needed or have<cost:
                raise ValueError('stamina payment coverage unverified')
            self.pending=(before,trades_needed,required,have)
        self._act(ConfirmTradingTrade(),s)
        # One consuming confirmation. Inconclusive effect never repeats it.
        s=n.wait(lambda s:self.ready(s) and not self.detector.present(s.frame.image,'stamina_panel'))
        self._act(CloseTrading(),s);n.wait(lobby)
        after=self.balances.read()
        minimum=before.stamina+50*trades_needed if manual else required
        if after.stamina<minimum:raise ValueError('stamina batch effect unverified: fresh stamina below demand')
        self.pending=None
        record_best_effort(n.events,'stages.stamina_purchase',
            stamina_before=before.stamina,stamina_after=after.stamina,
            trades=trades_needed,right_taps=right_taps,confirmations=1,kcoin_cost=200*trades_needed,
            elapsed=n.clock()-started)
        return StaminaSupplyResult(after,required,50*trades_needed,
            'purchased' if after.stamina>=required else boundary or 'partial', kcoin_cost=200*trades_needed)
