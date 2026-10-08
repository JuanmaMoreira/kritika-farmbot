"""B1 contracts, using a reordered inventory and independent slot effects."""
from dataclasses import replace
import pytest

from bot.meteorites_runtime import MeteoriteResult
from bot.meteorites_semantics import MeteoriteItem, MeteoriteAction, MeteoritesBag, SlotState, bag_location, SLOT_POINTS
from bot.shared_meteorites import SharedMeteoritesPreparation, normal_anchor


class Game:
    def __init__(self, originals=11, flares=4, failure=None, late=False):
        self.inventory = [('original', i) for i in range(originals)] + [('flare', i) for i in range(flares)] + [('normal', i) for i in range(10)] + [('tail', i) for i in range(40)]
        self.shared_flare = ('flare', 0)
        self.set = 1; self.slots = [None]*11; self.page = 1; self.time = 0
        self.failure = failure; self.late = late; self.cancel = False
        self.inputs = []; self.evidence = {}; self.metrics = {}; self.waits = 0; self._latest = None
        self.bounds = None; self.active_cancel_at = None
        self.reader = type('Reader', (), {'calls': {}})()
        self.before_set1 = None

    def clock(self): return self.time
    def cancel_requested(self): return self.cancel
    def bag(self):
        self.time += .01
        return MeteoritesBag(int(self.time*1000), self.time, self.set, self.page, 6,
            tuple(SlotState.OCCUPIED if item else SlotState.EMPTY for item in self.slots))
    def enter(self, *a, **kw): return None if self.cancel else self.bag()
    def select_set(self, number):
        if self.cancel: return None
        self.inputs.append(('set', number)); self.set = number
        if number == 1: self.before_set1 = list(self.slots)
        return self.bag()
    def ready(self): return None if self.cancel else self.bag()
    def _begin(self): self.metrics = {}; return self.time, {}
    def group_cell(self, index):
        if self.cancel: return None
        self.page, _ = bag_location(index)
        kind, _ = self.inventory[index-1]
        return kind == 'flare', 'Ethereal+' if self.inventory[index-1] == self.shared_flare else 'Ethereal'
    def inspect(self, index):
        if self.cancel: return None
        self.inputs.append(('inspect', index))
        return MeteoriteItem(True, 'Ethereal+', 30, MeteoriteAction.EQUIP, 1, self.time)
    def equip(self, index, *, expected_slot, require_shared, retry_no_effect):
        assert require_shared and self.set == 2
        self.page, _ = bag_location(index)
        item = self.inventory[index-1]
        assert item == self.shared_flare if expected_slot == 0 else item[0] == 'normal'
        return self.operation(expected_slot, item, False, index)
    def unequip_slot(self, slot, *, retry_no_effect, required_set=2):
        assert self.set == required_set == 2
        return self.operation(slot, self.slots[slot], True, None)
    def operation(self, slot, item, cleanup, index):
        before = self.bag(); name = ('unequip' if cleanup else 'equip', slot)
        self.inputs.append((*name, index)); self.time += .2
        fail = name == self.failure
        if not fail or self.late:
            self.slots[slot] = None if cleanup else item
            if not cleanup:
                self.inventory.remove(item)
                self.inventory.insert(0, item)
            self.page = 1
        after = before if fail else self.bag()
        if name == self.active_cancel_at: self.cancel = True
        return MeteoriteResult('ambiguous' if fail else 'success', 'simulated', slot,
            MeteoriteItem(slot == 0, 'Ethereal+', 30, MeteoriteAction.UNEQUIP if cleanup else MeteoriteAction.EQUIP, 2, self.time),
            before, after, 1, {'wall_seconds': .2, 'retries': 0})
    def _wait(self, predicate):
        self.waits += 1
        bag = self.bag()
        return bag if not self.cancel and predicate(bag) else None


@pytest.mark.parametrize('originals,flares', [(0,1), (0,12), (11,4), (10,6), (11,7), (8,26)])
def test_frontier_anchor_and_all_equip_positions_stay_initial(originals, flares):
    game = Game(originals, flares)
    flow = SharedMeteoritesPreparation(game)
    p = flow.setup(None, None)
    assert p.phase == 'equipped'
    assert p.flare_position == originals+1
    assert p.first_normal_position == originals+flares+1
    assert p.anchor == normal_anchor(p.first_normal_position)
    assert (p.anchor_page, p.anchor_cell) == bag_location(p.anchor)
    equips = [a for a in game.inputs if a[0] == 'equip']
    assert [a[1] for a in equips] == list(range(11))
    assert [a[2] for a in equips] == [p.flare_position]+[p.anchor]*10
    assert [game.slots[i][1] for i in range(1,11)] == list(range(9,-1,-1))


def test_cleanup_reverse_flare_last_and_restore_only_after_eleven_effects():
    game = Game(); flow = SharedMeteoritesPreparation(game)
    flow.setup(None, None); p = flow.cleanup()
    assert p.phase == 'complete' and len(p.operations) == 22
    assert p.released == list(range(10,0,-1))+[0]
    assert all(op['effect_verified'] for op in p.operations)
    assert game.before_set1 == [None]*11 and game.set == 1
    assert game.waits == 0  # no second full-slot postcondition sweep


@pytest.mark.parametrize('phase,slot', [('equip', i) for i in range(11)] + [('unequip', i) for i in range(11)])
def test_first_ambiguity_stops_with_exact_progress_no_repeated_input(phase, slot):
    game = Game(failure=(phase,slot)); flow = SharedMeteoritesPreparation(game)
    p = flow.setup(None,None)
    if phase == 'unequip': p = flow.cleanup()
    assert p.phase == 'stopped' and p.pending['slot'] == slot
    assert p.equipped == (list(range(slot)) if phase == 'equip' else list(range(11)))
    assert p.released == (list(range(10,slot,-1)) if phase == 'unequip' and slot else (list(range(10,0,-1)) if phase == 'unequip' else []))
    assert sum(a[:2] == (phase,slot) for a in game.inputs) == 1
    assert game.set == 2 and ('set',1) not in game.inputs
    before = list(game.inputs); flow.cleanup(); assert game.inputs == before


@pytest.mark.parametrize('failure', [('equip',5),('unequip',5)])
def test_late_effect_reconciles_passively_without_duplicate_action(failure):
    game = Game(failure=failure, late=True); flow = SharedMeteoritesPreparation(game)
    flow.setup(None,None); p = flow.cleanup()
    assert p.phase == 'complete' and p.reconciliations == 1
    assert sum(a[:2] == failure for a in game.inputs) == 1
    assert len([a for a in game.inputs if a[0] in ('equip','unequip')]) == 22


@pytest.mark.parametrize('phase,slot', [('equip',i) for i in range(11)]+[('unequip',i) for i in range(11)])
def test_cancel_after_any_input_prevents_all_next_inputs(phase,slot):
    game = Game(); game.active_cancel_at = (phase,slot)
    flow = SharedMeteoritesPreparation(game); p = flow.setup(None,None)
    if phase == 'unequip': p = flow.cleanup()
    # At the last setup input, setup may already be credited, but cleanup must
    # still observe cancellation before it can dispatch anything.
    before = list(game.inputs); flow.cleanup()
    assert game.inputs == before and game.set == 2


def test_cancel_before_entry_and_discovery():
    game = Game(); game.cancel = True
    flow = SharedMeteoritesPreparation(game)
    assert flow.setup(None,None).phase == 'cancelled' and game.inputs == []
    game = Game(); read = game.group_cell
    def cancelling(index):
        game.cancel = True
        return read(index)
    game.group_cell = cancelling
    p = SharedMeteoritesPreparation(game).setup(None,None)
    assert p.phase == 'cancelled' and not any(a[0]=='equip' for a in game.inputs)


def test_wrong_slot_cannot_advance_progress_or_restore_set1():
    game = Game(); operation = game.operation
    def wrong(slot,item,cleanup,index):
        r = operation(slot,item,cleanup,index)
        return replace(r, slot=7) if slot == 3 and not cleanup else r
    game.operation = wrong
    flow = SharedMeteoritesPreparation(game); p = flow.setup(None,None)
    assert p.phase == 'stopped' and p.equipped == [0,1,2]
    before = list(game.inputs); flow.cleanup(); assert game.inputs == before


def test_slot_points_follow_user_gt_order():
    assert SLOT_POINTS[0] == (.348,.604)
    assert SLOT_POINTS[1:4] == ((.306,.404),(.386,.404),(.467,.404))
    assert SLOT_POINTS[4:8] == ((.448,.604),(.467,.802),(.386,.802),(.306,.802))
    assert SLOT_POINTS[8:] == ((.227,.802),(.249,.604),(.227,.404))


@pytest.mark.parametrize('bad',[0,-1,1.5,True])
def test_anchor_rejects_non_positive_one_based_positions(bad):
    with pytest.raises(ValueError): normal_anchor(bad)


def test_setup_is_not_replayable_after_failure():
    flow = SharedMeteoritesPreparation(Game(failure=('equip',4)))
    flow.setup(None,None)
    with pytest.raises(ValueError): flow.setup(None,None)


@pytest.mark.parametrize('cleanup',[False,True])
def test_verified_effect_readiness_failure_preserves_exact_known_slots(cleanup):
    game=Game(); flow=SharedMeteoritesPreparation(game)
    if cleanup: flow.setup(None,None)
    operation=game.operation
    def effect_only(slot,item,releasing,index):
        result=operation(slot,item,releasing,index)
        if slot==(7 if releasing else 4):
            return replace(result,outcome='effect_not_ready',after=None,
                           effect=replace(result.after,page=None,loading=True))
        return result
    game.operation=effect_only
    game._wait=lambda predicate:None
    p=flow.cleanup() if cleanup else flow.setup(None,None)
    assert p.phase=='stopped' and not p.pending
    assert p.known_bag.loading
    assert p.known_bag.slots[7 if cleanup else 4] is (SlotState.EMPTY if cleanup else SlotState.OCCUPIED)
    assert (p.released if cleanup else p.equipped)[-1]==(7 if cleanup else 4)
    assert ('set',1) not in game.inputs



def test_stable_no_effect_is_known_negative_not_pending_ambiguity():
    game=Game(failure=('equip',5));operation=game.operation
    def negative(slot,item,cleanup,index):
        result=operation(slot,item,cleanup,index)
        return replace(result,outcome='no_effect') if slot==5 and not cleanup else result
    game.operation=negative
    p=SharedMeteoritesPreparation(game).setup(None,None)
    assert p.phase=='stopped' and p.pending is None
    assert p.equipped==list(range(5)) and p.known_bag.slots[5] is SlotState.EMPTY


def test_restore_set1_uncertainty_preserves_last_credited_empty_set2():
    game=Game();flow=SharedMeteoritesPreparation(game);flow.setup(None,None)
    select=game.select_set
    def uncertain(number):
        result=select(number)
        return None if number==1 else result
    game.select_set=uncertain
    p=flow.cleanup()
    assert p.phase=='stopped' and p.released==list(range(10,0,-1))+[0]
    assert p.pending['name']=='restore_set1'
    assert p.known_bag.active_set==2 and p.known_bag.slots==(SlotState.EMPTY,)*11
    assert game.set==1
