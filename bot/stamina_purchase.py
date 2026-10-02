"""Only Currency's Stamina50/K Coin200 offer; single verified trades."""
from bot.stages_actions import StageAction,StageControl as C
from bot.semantic_actions import OpenTrading,CloseTrading,ConfirmTradingTrade
from bot.event_log import record_best_effort
from bot.catalog import SCREEN_LOBBY
from bot.stages_runtime import lobby

class StaminaPurchase:
    def __init__(self,navigation,balances,detector):self.nav,self.balances,self.detector=navigation,balances,detector
    def _act(self,action,s):
        self.nav.act(action,s)
    def ready(self,s):return all(self.detector.present(s.frame.image,k) for k in ('currency','stamina_row'))
    def ensure(self,before):
        n=self.nav
        for attempt in range(6):
            if before.stamina>=300:return before
            self._act(OpenTrading(),before.snapshot)
            s=n.wait(lambda s:self.detector.present(s.frame.image,'currency') or s.state.base_context=='screen.trading')
            self._act(StageAction(C.CURRENCY),s);s=n.wait(self.ready)
            self._act(StageAction(C.STAMINA_ROW),s)
            s=n.wait(lambda s:self.detector.present(s.frame.image,'stamina_panel') and self.detector.present(s.frame.image,'kcoin'))
            # USER_GT: K Coins are always available for this fixed offer.
            # No currency OCR. The acquired offer and single trade remain CV
            # guarded; only a fresh Lobby Stamina increase proves its effect.
            if not self.detector.present(s.frame.image,'trade_one'):
                raise ValueError('stamina trade quantity mismatch')
            self._act(ConfirmTradingTrade(),s)
            # No repeat on an inconclusive confirm, even if the old panel persists.
            s=n.wait(lambda s:self.ready(s) and not self.detector.present(s.frame.image,'stamina_panel'))
            self._act(CloseTrading(),s);n.wait(lobby)
            after=self.balances.read()
            if after.stamina<=before.stamina:raise ValueError('stamina effect unverified')
            record_best_effort(n.events,'stages.stamina_purchase',attempt=attempt+1,
                stamina_before=before.stamina,stamina_after=after.stamina,kcoin_cost=200)
            before=after
        if before.stamina<300:raise ValueError('stamina recovery bound')
        return before
