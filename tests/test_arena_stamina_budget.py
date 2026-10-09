"""Consumption receipts, deferred supply and safe continuation of one occurrence."""
from types import SimpleNamespace as NS
import pytest
from bot.arena_config import ArenaConfig,ArenaMode
from bot.arena_farming_cycle import ArenaFarmingCycle,FarmingTermination as T
from bot.manual_stages import ManualStagesResult,ManualStageOutcome as O
from bot.flow_contracts import FlowStatus as S
from bot.stamina_purchase import StaminaSupplyResult
from test_arena_farming_cycle import World,arena_result,mw_result

class BudgetWorld(World):
    def __init__(self,limit,have=180,*,claim=0,partial=None,max_operations=32):
        super().__init__([(0,i) for i in range(100)],
            config=ArenaConfig(ArenaMode.FARMING_CYCLE,maximum_stamina_consumption=limit),
            max_operations=max_operations)
        self.have=have;self.claim=claim;self.partial=partial;self.preparations=[];self.entries=0
        self.cycle.manual_stages=NS(run=self.stage,resume=self.resume_stage,
            balances=NS(read=lambda:NS(stamina=self.have)),prepare_stamina=self.prepare)
        self.stops=[];self.resumed=[]
    def prepare(self,required,*,still_manual):
        self.trace.append('supply');self.have+=self.claim;self.claim=0
        if not still_manual():return StaminaSupplyResult(NS(stamina=self.have),required,outcome='routing_changed')
        deficit=max(0,required-self.have)
        bought=((deficit+49)//50)*50 if self.partial is None else self.partial
        self.have+=bought;self.preparations.append((required,bought,self.have))
        return StaminaSupplyResult(NS(stamina=self.have),required,bought,
            'purchased' if self.have>=required else 'insufficient_kcoins')
    def stage(self):
        self.trace.append('manual');self.entries+=1
        if self.stops:return self.stops.pop(0)
        if self.have<60:return ManualStagesResult(S.COMPLETED,outcome=O.STAMINA_INSUFFICIENT)
        self.have-=60
        return ManualStagesResult(S.COMPLETED,outcome=O.REWARDED,entry_id=self.entries,stamina_consumed=60)
    def resume_stage(self):self.trace.append('reconcile');return self.resumed.pop(0)

@pytest.mark.parametrize('limit,entries,remaining',[(0,0,0),(59,0,59),(60,1,0),(500,8,20)])
def test_full_entries_only_without_rounding_up(limit,entries,remaining):
    w=BudgetWorld(limit,have=1000)
    r=w.cycle.run()
    assert r.succeeded and r.termination is T.STAMINA_BUDGET_REACHED
    assert w.entries==entries and r.stamina_consumed==entries*60
    assert r.remaining_stamina_budget==remaining
    assert len(w.preparations)==bool(entries)
    assert not any(bought for _,bought,_ in w.preparations)

def test_first_manual_supply_accounts_for_existing_balance_claim_and_packet_rounding():
    w=BudgetWorld(600,180,claim=30)
    r=w.cycle.run()
    assert w.preparations==[(600,400,610)]
    assert w.entries==10 and r.stamina_consumed==600 and w.have==10
    assert r.stamina_prepared

def test_no_budget_refills_only_below60_to_minimum():
    w=BudgetWorld(None,110,max_operations=3)
    r=w.cycle.run()
    assert w.preparations==[(60,50,100),(60,50,90)]
    assert w.entries==3 and r.stamina_consumed==180
    assert r.remaining_stamina_budget is None and not r.stamina_prepared

@pytest.mark.parametrize('partial,entries',[(0,1),(50,2),(0,0)])
def test_partial_or_impossible_supply_uses_only_real_balance(partial,entries):
    have=120 if entries==2 else 60 if entries==1 else 0
    w=BudgetWorld(600,have,partial=partial)
    r=w.cycle.run()
    assert r.succeeded and r.termination in {T.STAMINA_INSUFFICIENT,T.STAMINA_SUPPLY_UNAVAILABLE}
    assert r.stamina_consumed==entries*60 and len(w.preparations)==1
    assert not next(e for e in r.events if e.kind=='arena.farming.stamina_supply').fields['covered']

@pytest.mark.parametrize('known',[None,60])
def test_interrupted_entry_reconciles_before_resources_or_supply_and_counts_once(known):
    w=BudgetWorld(60,180)
    w.stops=[ManualStagesResult(S.MANUAL_RESOLUTION,outcome=O.AMBIGUOUS,
        entry_id=1,stamina_consumed=known,physical_operation_may_be_active=True)]
    first=w.cycle.run()
    assert first.stamina_consumed==(known or 0) and first.stamina_consumption_pending
    trace=len(w.trace)
    w.resumed=[ManualStagesResult(S.COMPLETED,outcome=O.REWARDED,entry_id=1,stamina_consumed=60)]
    resumed=w.cycle.run()
    assert w.trace[trace]=='reconcile'
    assert resumed.succeeded and resumed.stamina_consumed==60
    assert resumed.termination is T.STAMINA_BUDGET_REACHED
    assert len(w.preparations)==1 and w.entries==1
    assert resumed.events[-1].fields['manual_entries'] == 1
    assert resumed.event_count('arena.farming.manual_entry') == 1
    assert resumed.duration >= first.duration

def test_unknown_consumption_cannot_restart_or_reset_on_repeated_resume():
    w=BudgetWorld(500)
    unknown=ManualStagesResult(S.MANUAL_RESOLUTION,outcome=O.AMBIGUOUS,
        entry_id=1,stamina_consumed=None,physical_operation_may_be_active=True)
    w.stops=[unknown];w.resumed=[unknown,unknown]
    assert w.cycle.run().stamina_consumption_pending
    assert w.cycle.run().stamina_consumption_pending
    assert w.cycle.run().stamina_consumption_pending
    assert w.entries==1 and len(w.preparations)==1

def test_cancel_between_entries_preserves_counter_supply_and_controller():
    w=BudgetWorld(120,0);stage=w.cycle.manual_stages.run
    def stop_after_entry():
        r=stage();w.cancel=True;return r
    w.cycle.manual_stages.run=stop_after_entry
    first=w.cycle.run();controller=w.cycle.controller
    assert first.status is S.CANCELLED and first.stamina_consumed==60
    w.cancel=False;w.cycle.manual_stages.run=stage
    resumed=w.cycle.run()
    assert resumed.stamina_consumed==120 and resumed.termination is T.STAMINA_BUDGET_REACHED
    assert w.cycle.controller is controller and len(w.preparations)==1

def test_ambiguous_supply_blocks_stage_until_same_receipt_is_reconciled():
    w=BudgetWorld(60,0);attempts=[]
    def supply(required,*,still_manual):
        attempts.append(required)
        if len(attempts)==1:raise ValueError('purchase effect uncertain')
        w.have=100
        return StaminaSupplyResult(NS(stamina=100),required,100,'purchased')
    w.cycle.manual_stages.prepare_stamina=supply
    first=w.cycle.run()
    assert first.status is S.MANUAL_RESOLUTION and w.entries==0 and not first.stamina_prepared
    resumed=w.cycle.run()
    assert resumed.succeeded and resumed.stamina_consumed==60 and resumed.stamina_prepared
    assert attempts==[60,60] and w.entries==1

def test_defeated_entry_consumption_counts_even_with_regeneration_or_claim():
    w=BudgetWorld(500)
    w.stops=[ManualStagesResult(S.COMPLETED,outcome=O.DEFEATED,entry_id=1,
        stamina_consumed=60,stamina_before=180,stamina_after=190)]
    r=w.cycle.run()
    assert r.succeeded and r.termination is T.MANUAL_STAGE_DEFEATED and r.stamina_consumed==60

def test_post_operation_routing_ambiguity_preserves_budget_and_blocks_new_input():
    w=BudgetWorld(120,180)
    # Initial and post-Claim fresh, post-Stage authority unavailable.
    w.balances=iter([(0,0),(0,0),None])
    r=w.cycle.run()
    assert r.status is S.MANUAL_RESOLUTION and r.stamina_consumed==60
    trace=len(w.trace)
    again=w.cycle.run()
    assert again.status is S.MANUAL_RESOLUTION and again.stamina_consumed==60
    assert len(w.trace)==trace and len(w.preparations)==1

def test_missing_consumption_receipt_is_unknown_and_cannot_authorize_next_entry():
    from bot.flow_contracts import FlowResult
    w=World([(0,0)],config=ArenaConfig(ArenaMode.FARMING_CYCLE,maximum_stamina_consumption=60))
    w.cycle.manual_stages=NS(run=w.manual);w.manual_results=[FlowResult(S.COMPLETED)]
    first=w.cycle.run();trace=len(w.trace)
    assert first.status is S.MANUAL_RESOLUTION and first.stamina_consumption_pending
    assert w.cycle.run().status is S.MANUAL_RESOLUTION and len(w.trace)==trace

def test_fresh_completed_execution_starts_counter_zero():
    w=BudgetWorld(60,180)
    assert w.cycle.run().stamina_consumed==60
    assert w.cycle.run().stamina_consumed==60
    assert len(w.preparations)==2

def test_arena_and_mw_priority_never_prepare_stamina():
    w=BudgetWorld(600)
    w.balances=iter([(40,100),(0,100),(40,0)])
    w.arena_results=[arena_result()];w.mw_results=[mw_result()];w.cycle.max_operations=2
    assert w.cycle.run().succeeded and not w.preparations

def test_early_easy_zero_after_supply_keeps_remaining_stamina_and_completes():
    w=BudgetWorld(600,0)
    w.balances=iter([(0,0),(0,0),(0,0),(0,100),(80,0),(0,100),(80,0),(0,100),(80,0),(0,100)])
    w.mw_results=[mw_result(),mw_result(),mw_result()]
    w.arena_results=[arena_result(80,0,run='hard'),arena_result(80,0,run='normal'),arena_result(80,0,run='easy')]
    r=w.cycle.run()
    assert r.succeeded and r.termination is T.EASY_ZERO_WINS
    assert r.stamina_consumed==60 and w.have==540 and len(w.preparations)==1

def test_claim_makes_mw_eligible_no_anticipatory_purchase_or_stage():
    w=BudgetWorld(600,0);w.cycle.max_operations=1
    w.balances=iter([(0,0),(0,100),(40,0)]);w.mw_results=[mw_result()]
    r=w.cycle.run()
    assert r.succeeded and not w.preparations and w.entries==0
    assert not r.stamina_prepared and r.stamina_consumed==0
