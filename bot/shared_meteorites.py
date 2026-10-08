"""B1 support procedure. Individual input/effect ownership stays in Phase A.

No session wiring, character switching or automatic cleanup after a failure.
The five USER_GT preconditions are a caller contract, not a new audit suite.
"""
from dataclasses import dataclass, field, replace

from bot.meteorites_semantics import SlotState, bag_location


def normal_anchor(first_normal_position):
    bag_location(first_normal_position)  # positive one-based contract
    return first_normal_position + 9


@dataclass
class SharedMeteoritesProgress:
    flare_position: int | None = None
    flare_item: object = None
    first_normal_position: int | None = None
    anchor: int | None = None
    anchor_page: int | None = None
    anchor_cell: int | None = None
    equipped: list = field(default_factory=list)
    released: list = field(default_factory=list)
    operations: list = field(default_factory=list)
    known_bag: object = None
    phase: str = 'new'
    reason: str = ''
    metrics: dict = field(default_factory=dict)
    reconciliations: int = 0
    pending: object = None


class SharedMeteoritesPreparation:
    def __init__(self, runtime, *, record=lambda name, result, progress: None,
                 retry_no_effect=True):
        self.rt = runtime
        self.progress = SharedMeteoritesProgress()
        self.record = record
        self.retry_no_effect = retry_no_effect

    def _stop(self, reason):
        self.progress.phase = 'cancelled' if self.rt.cancel_requested() else 'stopped'
        self.progress.reason = reason
        return self.progress

    def _bag_matches(self, bag, slots):
        return (bag is not None and bag.ready and bag.active_set == 2
                and bag.slots == tuple(slots))

    def _operation(self, slot, index=None):
        p, rt = self.progress, self.rt
        if rt.cancel_requested():
            self._stop('cancelled'); return False
        cleanup = index is None
        name = ('unequip' if cleanup else 'equip') + '_' + str(slot)
        before = p.known_bag
        result = (rt.unequip_slot(slot, retry_no_effect=self.retry_no_effect, required_set=2)
                  if cleanup else rt.equip(index, expected_slot=slot,
                       require_shared=True, retry_no_effect=self.retry_no_effect))
        target = SlotState.EMPTY if cleanup else SlotState.OCCUPIED
        expected = list(before.slots); expected[slot] = target
        valid_before = (result.before is not None and result.before.active_set == 2
                        and result.before.slots == before.slots and result.slot == slot)
        effect_bag = result.effect or result.after
        effect = (valid_before and effect_bag is not None
                  and effect_bag.active_set == 2 and effect_bag.slots == tuple(expected)
                  and not effect_bag.overlay)
        # A Phase A positive whose readiness expired already proves this slot.
        positive = effect
        if not positive and result.action_inputs and valid_before and not rt.cancel_requested():
            # Observe only. Never reselect or repeat a potentially completed tap.
            fresh = rt._wait(lambda b: self._bag_matches(b, expected))
            if fresh is not None:
                rt.evidence['effect'] = rt._latest
                rt.evidence['final'] = rt._latest
                result = replace(result, outcome='success', reason='reconciled_slot_effect', after=fresh, effect=fresh)
                p.reconciliations += 1
                positive = True
        if positive:
            (p.released if cleanup else p.equipped).append(slot)
        p.operations.append(dict(name=name, index=index, result=result,
                                 effect_verified=positive))
        if result.after is not None or result.effect is not None:
            p.known_bag = result.after or result.effect
        if not positive and result.action_inputs and result.outcome != 'no_effect':
            p.pending = dict(name=name, slot=slot, target=target, before=before)
        self.record(name, result, p)
        if not positive:
            self._stop(name + ':' + result.reason); return False
        if not self._bag_matches(result.after, expected):
            fresh = rt._wait(lambda b: self._bag_matches(b, expected))
            if fresh is None:
                self._stop(name + ':effect_verified_readiness_unverified'); return False
            p.known_bag = fresh
        return True

    def setup(self, observer, transition, *, via_quick_menu=False):
        p, rt = self.progress, self.rt
        if p.phase != 'new':
            raise ValueError('setup is single-use; unresolved progress cannot authorize replay')
        started = rt.clock()
        try:
            p.phase = 'setup'
            if rt.cancel_requested(): return self._stop('cancelled')
            _, entry_calls = rt._begin()
            if rt.enter(observer, transition, via_quick_menu=via_quick_menu) is None:
                return self._stop('entry_unverified')
            bag = rt.select_set(2)
            # This is the operation's empty destination guard, not an audit of
            # originals, identity, Set 3 or the complete inventory.
            if not self._bag_matches(bag, [SlotState.EMPTY]*11):
                return self._stop('Set_2_empty_unverified')
            p.known_bag = bag
            p.metrics['entry_set_seconds'] = rt.clock()-started
            p.metrics['entry_set_local'] = dict(rt.metrics)
            for name, value in getattr(rt.reader, 'calls', {}).items():
                p.metrics['entry_set_local'][name+'_calls'] = value-entry_calls.get(name, 0)
            self.record('set2', None, p)
            discovery_started = rt.clock()
            _, discovery_calls = rt._begin()
            for index in range(1, 13):
                candidate = rt.group_cell(index)
                if candidate is None: return self._stop('Flare_search_unverified:' + str(index))
                flare, tier = candidate
                if flare and tier == 'Ethereal+':
                    item = rt.inspect(index)
                    self.record('inspect_' + str(index), None, p)
                    if item is None: return self._stop('Flare_overlay_unverified:' + str(index))
                    if item.flare and item.tier == 'Ethereal+' and item.level > 0:
                        p.flare_position, p.flare_item = index, item
                        break
            if p.flare_position is None: return self._stop('shared_Flare_not_found')
            # Equipped prefix and shared Flare were passed. Walk only the Flare
            # suffix, bounded by the pager, stopping at the first normal.
            index = p.flare_position + 1
            total = p.known_bag.total_pages * 16
            while index <= total:
                candidate = rt.group_cell(index)
                if candidate is None: return self._stop('Flare_frontier_unverified:' + str(index))
                if not candidate[0]:
                    p.first_normal_position = index
                    p.anchor = normal_anchor(index)
                    p.anchor_page, p.anchor_cell = bag_location(p.anchor)
                    break
                index += 1
            if p.anchor is None: return self._stop('normal_frontier_not_found')
            p.metrics['discovery_seconds'] = rt.clock() - discovery_started
            p.metrics['discovery'] = dict(rt.metrics)
            for name, value in getattr(rt.reader, 'calls', {}).items():
                p.metrics['discovery'][name+'_calls'] = value-discovery_calls.get(name, 0)
            p.known_bag = rt.ready()
            if not self._bag_matches(p.known_bag, [SlotState.EMPTY]*11):
                return self._stop('discovery_destination_unverified')
            self.record('anchor', None, p)
            if not self._operation(0, p.flare_position): return p
            for slot in range(1, 11):
                if not self._operation(slot, p.anchor): return p
            p.phase = 'equipped'
            return p
        finally:
            p.metrics['setup_seconds'] = rt.clock() - started

    def cleanup(self):
        p, rt = self.progress, self.rt
        if p.phase != 'equipped' or p.equipped != list(range(11)) or p.pending:
            return self._stop('cleanup_requires_complete_credited_setup')
        started = rt.clock()
        try:
            p.phase = 'cleanup'
            for slot in (*range(10, 0, -1), 0):
                if not self._operation(slot): return p
            # Eleven individual effects prove empty; no repeated full sweep.
            if rt.cancel_requested(): return self._stop('cancelled_before_Set_1')
            final = rt.select_set(1)
            if final is not None:
                p.known_bag = final
            else:
                p.pending = dict(name='restore_set1', target_set=1, previous=p.known_bag)
            self.record('restored_set1', None, p)
            if final is None or not final.ready or final.active_set != 1:
                return self._stop('Set_1_ready_unverified')
            p.phase = 'complete'
            return p
        finally:
            p.metrics['cleanup_seconds'] = rt.clock() - started
