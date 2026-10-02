"""Logical reuse only after a compatible ordered deletion; CV is discovery."""
from dataclasses import replace
from test_equipment_inventory_relief import PhysicalInventory, item, G, T
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_operation import EquipmentSellResult,EquipmentSellOutcome


class TrackedInventory(PhysicalInventory):
    def __init__(self,items,capacity):
        super().__init__(items,capacity);self.names=[]
    def inspect(self,candidate,inventory):
        fact=super().inspect(candidate,inventory)
        self.names.append(fact.name)
        return fact


def protected(name,kind=T.RING):
    return replace(item(kind=kind),name=name)


def test_verified_bulk_exposes_new_region_without_reopening_certified_successors():
    p=TrackedInventory([item(G.ETHEREAL_PLUS),item(kind=T.CHEST),item(kind=T.CHEST),
        item(G.RARE,T.GLOVES)] + [protected(f'old{i}') for i in range(4)] +
        [protected(f'new{i}') for i in range(4)],8)
    events=[]
    result=p.run(telemetry=lambda **kw:events.append(kw))
    assert result.succeeded and p.sales==2
    assert p.selected==[7,6,5,4,3,7,2,7,6,0]
    assert all(p.names.count(f'old{i}')==1 for i in range(4))
    first=next(e for e in events if e['phase']=='bulk_scan_transform')
    assert (first['sold_start'],first['sold_end'],first['delta'])==(3,3,1)
    assert first['protected_ranges']==((3,6),)
    assert (first['new_region_start'],first['next_unseen_index'])==(7,7)


def test_cv_skips_identical_protected_block_and_strong_panel_selects_distinct_candidate():
    p=TrackedInventory([item(G.ETHEREAL_PLUS),item(G.RARE,T.GLOVES)] +
                       [protected(f'old{i}') for i in range(6)] + [item(G.RARE,T.GLOVES)],8)
    calls=[]
    def discover(candidate,inventory,fact):
        calls.append(fact)
        return 1  # Six equivalent protected slots; first different is still unclassified.
    result=p.run(skip_protected=discover)
    assert result.succeeded and p.selected==[7,1] and p.sales==1
    assert len(calls)==1 and calls[0].equipment_type is T.RING


def test_cv_failure_and_false_candidate_fall_back_to_strong_panels_without_bulk():
    for broken in (lambda *a:None,lambda *a:(_ for _ in ()).throw(ValueError('CV'))):
        p=TrackedInventory([item(G.ETHEREAL_PLUS)]+[protected(f'r{i}') for i in range(7)],4)
        result=p.run(skip_protected=broken)
        assert result.succeeded and p.sales==0
        assert p.selected[:4]==[3,2,1,0]  # All protected candidates verified, E+ stop.


def test_cv_is_never_invoked_at_strong_ethereal_plus_boundary():
    p=PhysicalInventory([item(G.ETHEREAL_PLUS)]*5,4)
    def forbidden(*args):raise AssertionError('E+ may not be skipped')
    assert p.run(skip_protected=forbidden).succeeded
    assert p.selected==[3] and p.sales==0 and p.buys==1


def test_incompatible_delta_invalidates_logical_ranges_and_reopens_fresh_panels():
    class Contradiction(TrackedInventory):
        def bulk(self,candidate,authorization,fact):
            self.sales+=1;before=self.inventory()
            # Simulate live evidence contradicting the ordered sold-block model.
            self.items=self.items[3:]
            return EquipmentSellResult(EquipmentSellOutcome.SUCCESS,'effect',before=before,
                                       after=self.inventory(),inputs=('confirm_bulk',))
    p=Contradiction([item(G.RARE)]+[protected(f'r{i}') for i in range(7)],4)
    events=[];result=p.run(telemetry=lambda **kw:events.append(kw))
    assert result.succeeded
    transform=next(e for e in events if e['phase']=='bulk_scan_transform')
    assert not transform['compatible'] and transform['protected_ranges']==()
    assert p.selected[:5]==[3,2,1,0,3]


def test_capacity_success_after_bulk_never_scans_again():
    p=PhysicalInventory([item(G.RARE)]*8,8)
    assert p.run().succeeded
    assert p.selected==[7] and p.sales==1 and p.buys==0


def test_expansion_invalidates_logical_scan_and_uses_new_tail():
    p=PhysicalInventory([item(G.ETHEREAL_PLUS),protected('r1'),protected('r2'),protected('r3')]+
                       [item(G.RARE)]*4,4)
    assert p.run().succeeded
    assert p.selected==[3,2,1,0,7] and p.buys==1
