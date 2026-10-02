"""USER_GT Equipment policy and state-changing tail restarts."""
from dataclasses import replace
import pytest
from bot.equipment_inventory_relief import (execute_inventory_relief, slot_candidate,
    EquipmentCapacityExpansionResult, EquipmentInventoryReliefResult)
from bot.equipment_sell_policy import EquipmentSellPolicy, DEFAULT_ETHEREAL_SELL_TYPES
from bot.equipment_sell_operation import EquipmentSellResult, EquipmentSellOutcome
from bot.equipment_sell_semantics import (EquipmentType as T, EquipmentGrade as G,
    EquipmentItemFact, EquipmentInventoryFact, CONFIGURABLE_EQUIPMENT_TYPES)


def item(grade=G.ETHEREAL, kind=T.CHEST, *, enhance=False, sequence=4, sell=True, visual=True):
    return EquipmentItemFact('Item '+kind.value,grade,kind,enhance,sequence,float(sequence),
                             (sequence-1,sequence),sell_available=sell,
                             grade_visual=grade if visual else None)


@pytest.mark.parametrize('kind',list(CONFIGURABLE_EQUIPMENT_TYPES))
def test_ethereal_defaults_and_both_configuration_directions(kind):
    fact=item(kind=kind)
    assert bool(EquipmentSellPolicy().authorize(fact)) == (kind in DEFAULT_ETHEREAL_SELL_TYPES)
    assert EquipmentSellPolicy(frozenset({kind})).authorize(fact)
    assert EquipmentSellPolicy(frozenset()).authorize(fact) is None


@pytest.mark.parametrize('grade',[G.LEGENDARY,G.EPIC,G.RARE,G.NORMAL,G.POOR])
@pytest.mark.parametrize('kind',list(CONFIGURABLE_EQUIPMENT_TYPES))
@pytest.mark.parametrize('enhance',[False,True])
def test_lower_tiers_all_types_ignore_ethereal_protections(grade,kind,enhance):
    assert EquipmentSellPolicy(frozenset(),False).authorize(item(grade,kind,enhance=enhance))


@pytest.mark.parametrize('kind',list(CONFIGURABLE_EQUIPMENT_TYPES))
@pytest.mark.parametrize('enhance',[False,True])
def test_ethereal_plus_permanently_protected(kind,enhance):
    assert EquipmentSellPolicy(CONFIGURABLE_EQUIPMENT_TYPES,True).authorize(
        item(G.ETHEREAL_PLUS,kind,enhance=enhance)) is None


def test_ethereal_enhance_is_independent_and_requires_positive_guards():
    fact=item(enhance=True)
    assert EquipmentSellPolicy(CONFIGURABLE_EQUIPMENT_TYPES,False).authorize(fact) is None
    assert EquipmentSellPolicy(frozenset(),True).authorize(fact)
    for bad in (replace(fact,sell_available=False),replace(fact,sell_available=None),
                replace(fact,grade_visual=None),replace(fact,contradictory=True),
                replace(fact,sample_sequences=(4,))):
        assert EquipmentSellPolicy(CONFIGURABLE_EQUIPMENT_TYPES,True).authorize(bad) is None


class PhysicalInventory:
    def __init__(self,items,capacity):
        self.items=list(items);self.capacity=capacity;self.sequence=0
        self.selected=[];self.sales=0;self.buys=0;self.reads=[]
        self.inconclusive_sale=False;self.inconclusive_purchase=False
    def inventory(self,after=0):
        assert self.sequence >= after
        self.reads.append(after);self.sequence+=2
        return EquipmentInventoryFact(len(self.items),self.capacity,1,22,self.sequence,
                                      float(self.sequence),(self.sequence-1,self.sequence))
    def inspect(self,candidate,inventory):
        index=(candidate.page-1)*16+candidate.slot
        assert index < self.capacity and index < len(self.items)
        self.selected.append(index);self.sequence+=2
        return replace(self.items[index],sequence=self.sequence,observed_at=float(self.sequence),
                       sample_sequences=(self.sequence-1,self.sequence))
    def bulk(self,candidate,authorization,fact):
        self.sales+=1;before=self.inventory()
        assert authorization.allows(fact)
        if not self.inconclusive_sale:
            self.items=[v for v in self.items if not (v.grade==fact.grade and v.enhance==fact.enhance
                and (fact.grade is not G.ETHEREAL or fact.enhance or v.equipment_type==fact.equipment_type))]
        after=self.inventory()
        return EquipmentSellResult(EquipmentSellOutcome.SUCCESS if not self.inconclusive_sale else
                                   EquipmentSellOutcome.FAILED,'effect',before=before,after=after,
                                   inputs=('confirm_bulk',))
    def expand(self,before):
        self.buys+=1
        if self.inconclusive_purchase:
            return EquipmentCapacityExpansionResult(before,None,180,1,'effect_inconclusive')
        self.capacity+=4
        return EquipmentCapacityExpansionResult(before,self.inventory(),180,1,'verified')
    def run(self,policy=EquipmentSellPolicy(),**kwargs):
        return execute_inventory_relief(policy,read_inventory=self.inventory,inspect=self.inspect,
                                        bulk_sell=self.bulk,expand=self.expand,**kwargs)


def test_bulk_still_full_discards_scan_and_visits_new_tail_first():
    physical=PhysicalInventory([item(G.ETHEREAL_PLUS)]*4 +
        [item(kind=T.CHEST),item(kind=T.NECKLACE),item(kind=T.WEAPON),item(kind=T.RING)] +
        [item(G.RARE,kind) for kind in (T.GLOVES,T.CHEST,T.WEAPON,T.RING)],8)
    result=physical.run()
    assert result.succeeded and result.after.item_count==7
    assert physical.selected==[7,6,5,4,7]  # Never resume the previous scan at 3.
    assert physical.sales==2 and physical.buys==0
    assert result.sales[0].after.sequence in physical.reads


def test_expansion_exactly_one_row_exposes_tail_and_restarts_sell():
    physical=PhysicalInventory([item(G.ETHEREAL_PLUS)]*2 +
        [item(kind=T.WEAPON),item(kind=T.RING)] + [item(G.RARE)]*6,4)
    result=physical.run()
    assert result.succeeded and result.after.capacity==8 and result.after.item_count==4
    assert physical.selected==[3,2,1,7]  # Stop at E+, then inspect newly accessible tail.
    assert physical.buys==1 and physical.sales==1


def test_free_slot_stops_without_selection_or_consumption():
    p=PhysicalInventory([item()]*3,4);result=p.run()
    assert result.succeeded and p.selected==[] and p.buys==p.sales==0


@pytest.mark.parametrize('mutation',['sale','purchase'])
def test_inconclusive_consumption_is_never_repeated(mutation):
    p=PhysicalInventory([item(G.RARE)]*8 if mutation=='sale' else [item(G.ETHEREAL_PLUS)]*8,4)
    setattr(p,'inconclusive_'+mutation,True)
    result=p.run()
    assert result.outcome=='failed'
    assert (p.sales,p.buys)==((1,0) if mutation=='sale' else (0,1))


def test_missing_visual_guard_cannot_authorize_bulk_or_unnecessary_purchase():
    p=PhysicalInventory([item(G.ETHEREAL_PLUS)]*3+[item(G.RARE,visual=False)]*2,4)
    result=p.run()
    assert result.reason=='scan_identity_unreadable' and p.sales==p.buys==0


def test_capacity_math_tail_and_next_page_boundary():
    assert slot_candidate(127).page==8 and slot_candidate(127).slot==15
    assert slot_candidate(128).page==9 and slot_candidate(128).slot==0


def test_cancel_and_budget_bound_prevent_extra_consumptions():
    p=PhysicalInventory([item(G.ETHEREAL_PLUS)]*20,4)
    assert p.run(cancel_requested=lambda:True).outcome=='cancelled'
    assert p.selected==[] and p.buys==0
    result=p.run(max_cycles=1)
    assert result.reason=='relief_budget_exhausted' and p.buys==1


def test_productive_authorization_rechecks_visual_guards_at_consumptive_boundary():
    fact=item(G.RARE)
    authorization=EquipmentSellPolicy().authorize(fact)
    assert authorization and authorization.allows(fact)
    for changed in (replace(fact,grade_visual=None),replace(fact,sell_available=None),
                    replace(fact,grade_visual=G.ETHEREAL_PLUS)):
        assert not authorization.allows(changed)
