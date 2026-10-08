"""Individual verified Meteorites operations, no shared preparation algorithm.

The input owner carries selected candidate, page, set, frame and lineage. One
fresh slot transition proves the effect. Readiness is checked separately.
Timeout, Loading and unknown pixels never authorize another operation tap.
"""
from dataclasses import dataclass, field
import time

from bot.action_executor import FrameGeometry
from bot.event_log import record_best_effort
from bot.meteorites_actions import (
    OpenMeteorites, SelectQuickMenuMeteorites, SelectMeteoritesSet,
    SelectMeteoritesBagCell, SelectMeteoritesSlot, NextMeteoritesPage,
    PreviousMeteoritesPage, EquipMeteorite, UnequipMeteorite, CloseMeteoriteDetail,
)
from bot.meteorites_reader import normalize, core, correlation, sprite_score
from bot.meteorites_semantics import (
    SCREEN_METEORITES, SLOT_POINTS, BAG_POINTS, SlotState, MeteoriteAction,
    bag_location,
)


@dataclass(frozen=True)
class MeteoriteResult:
    outcome: str
    reason: str
    slot: int | None = None
    item: object = None
    before: object = None
    after: object = None
    action_inputs: int = 0
    metrics: dict = field(default_factory=dict)
    effect: object = None

    @property
    def succeeded(self): return self.outcome == 'success'


@dataclass(frozen=True)
class MeteoritesBounds:
    # Configurable observation budgets, not physical completion estimates.
    selection_timeout: float = 3.
    effect_timeout: float = 5.
    readiness_timeout: float = 3.
    no_effect_stable_for: float = .5
    max_frame_age: float = .75
    poll_interval: float = .03
    max_samples: int = 256

    def __post_init__(self):
        import math
        for name in ('selection_timeout','effect_timeout','readiness_timeout',
                     'no_effect_stable_for','max_frame_age','poll_interval'):
            value=getattr(self,name)
            if isinstance(value,bool) or not math.isfinite(value) or value<=0:
                raise ValueError('invalid Meteorites observation bounds')
        if type(self.max_samples) is not int or self.max_samples<1:
            raise ValueError('max_samples must be positive')


class MeteoritesRuntime:
    def __init__(self,source,reader,actions,*,bounds=None,cancel_requested=lambda:False,
                 clock=time.monotonic,sleeper=time.sleep,events=None):
        self.source=source; self.reader=reader; self.actions=actions
        self.bounds=bounds or MeteoritesBounds()
        self.cancel_requested=cancel_requested; self.clock=clock; self.sleeper=sleeper
        self.events=events
        self._cursor=0; self._barrier=0.; self._latest=None; self._lineage=0
        self.metrics={}
        self.evidence={}

    def _perceive(self,read):
        started=self.clock()
        try: return read()
        finally:
            self.metrics['perception_seconds']=self.metrics.get('perception_seconds',0.)+self.clock()-started

    def _capture(self):
        if self.cancel_requested(): return None
        start=self.clock(); frame=self.source.get_frame()
        self.metrics['captures']=self.metrics.get('captures',0)+1
        self.metrics['capture_seconds']=self.metrics.get('capture_seconds',0.)+self.clock()-start
        if (frame.sequence<=self._cursor or frame.timestamp<self._barrier
                or not 0<=self.clock()-frame.timestamp<=self.bounds.max_frame_age):
            self.metrics['freshness_rejects']=self.metrics.get('freshness_rejects',0)+1
            self.evidence['freshness_reject']=frame
            return None
        self._cursor=frame.sequence; self._latest=frame
        return frame

    def _sample(self,kind='bag',*,read_page=True):
        frame=self._capture()
        if frame is None: return None
        kw=dict(sequence=frame.sequence,observed_at=frame.timestamp)
        fact=self._perceive(lambda:(self.reader.bag_sample(frame.image,read_page=read_page,**kw) if kind=='bag'
              else self.reader.detail_sample(frame.image,**kw)))
        if fact is not None and (fact.sequence!=frame.sequence or fact.observed_at!=frame.timestamp):
            self.metrics['freshness_rejects']=self.metrics.get('freshness_rejects',0)+1
            return None
        if not self._fresh(frame):
            self.metrics['freshness_rejects']=self.metrics.get('freshness_rejects',0)+1
            return None
        return fact

    def _fresh(self,frame):
        return frame is not None and 0<=self.clock()-frame.timestamp<=self.bounds.max_frame_age

    def _wait(self,predicate,*,kind='bag',timeout=None,read_page=True):
        deadline=self.clock()+(timeout or self.bounds.readiness_timeout)
        for _ in range(self.bounds.max_samples):
            if self.cancel_requested() or self.clock()>=deadline: return None
            fact=self._sample(kind,read_page=read_page)
            if fact is not None and predicate(fact): return fact
            self.sleeper(min(self.bounds.poll_interval,max(0,deadline-self.clock())))
        return None

    def _tap(self,action):
        if self.cancel_requested(): return None
        if not self._fresh(self._latest):
            self.metrics['freshness_rejects']=self.metrics.get('freshness_rejects',0)+1
            return None
        start=self.clock()
        if isinstance(action,(EquipMeteorite,UnequipMeteorite)):
            self.evidence['action']=self._latest
        # Invalidate selection before dispatch, also when transport raises.
        self._lineage+=1
        self.actions.execute(action,FrameGeometry.from_frame(self._latest.image),
                             events=self.events,source_sequence=self._latest.sequence)
        self._barrier=self.clock()
        return start

    def ready(self): return self._wait(lambda b:b.ready)

    def enter(self,observer,transition,*,via_quick_menu=False):
        """Reuse existing navigation guards; shifted tile has no acquired geometry."""
        from bot.catalog import SCREEN_LOBBY
        from bot.state import ResolutionStatus
        from bot.quick_menu import open_quick_menu_destination
        from bot.verified_transition import VerifiedTransitionPolicy
        initial=observer.observe()
        def clean(s,base):
            return s.state.status is ResolutionStatus.RESOLVED and s.state.base_context==base and not s.state.overlays
        if clean(initial,SCREEN_METEORITES): return self.ready()
        if not clean(initial,SCREEN_LOBBY): return None
        policy=VerifiedTransitionPolicy(normal_timeout=6,grace_timeout=2,max_attempts=1)
        expected=lambda s:clean(s,SCREEN_METEORITES)
        if via_quick_menu:
            result=open_quick_menu_destination(initial,transition,policy,
                action=SelectQuickMenuMeteorites(),selection='meteorites',expected=expected,
                cancel_requested=self.cancel_requested,prefix='meteorites')
        else:
            result=transition.execute('meteorites.enter',OpenMeteorites(),initial,
                precondition=lambda s:clean(s,SCREEN_LOBBY),expected=expected,policy=policy)
        if not result.succeeded: return None
        self._cursor=result.final_snapshot.sequence; self._barrier=self.clock()
        return self._wait(lambda b:b.ready and b.page==1)

    def select_set(self,number):
        action=SelectMeteoritesSet(number)
        before=self.ready()
        if before is None: return None
        if before.active_set==number: return before
        if self._tap(action) is None: return None
        return self._wait(lambda b:b.ready and b.active_set==number and b.page==before.page)

    def navigate_page(self,page):
        if type(page) is not int or page<1: raise ValueError('invalid page')
        current=self.ready()
        if current is None or page>current.total_pages: return None
        active=current.active_set
        # The pager denominator is navigation capacity, not occupied pages.
        for _ in range(abs(current.page-page)):
            step=1 if page>current.page else -1
            next_page=current.page+step
            if self._tap(NextMeteoritesPage() if step==1 else PreviousMeteoritesPage()) is None: return None
            current=self._wait(lambda b:b.ready and b.page==next_page and b.active_set==active)
            if current is None: return None
        return current

    def equip(self,absolute_index,*,expected=None,retry_no_effect=False,
              expected_slot=None,require_shared=False):
        started,calls=self._begin()
        page,cell=bag_location(absolute_index)
        navigation_started=self.clock()
        before=self.navigate_page(page)
        self.metrics['bag_navigation_seconds']=self.clock()-navigation_started
        return self._operate(MeteoriteAction.EQUIP,before,cell=cell,expected=expected,expected_slot=expected_slot,require_shared=require_shared,
                             retry_no_effect=retry_no_effect,started=started,calls=calls)

    def unequip_slot(self,slot,*,expected=None,retry_no_effect=False,required_set=None):
        started,calls=self._begin()
        SelectMeteoritesSlot(slot)  # Validate before sampling.
        return self._operate(MeteoriteAction.UNEQUIP,self.ready(),slot=slot,expected=expected,required_set=required_set,
                             retry_no_effect=retry_no_effect,started=started,calls=calls)

    def unequip_bag(self,absolute_index,slot,*,expected=None,retry_no_effect=False):
        started,calls=self._begin()
        SelectMeteoritesSlot(slot)
        page,cell=bag_location(absolute_index)
        return self._operate(MeteoriteAction.UNEQUIP,self.navigate_page(page),slot=slot,
                             cell=cell,expected=expected,retry_no_effect=retry_no_effect,started=started,calls=calls)

    def group_cell(self,absolute_index):
        """Focal sprite walk; no OCR names for Bag and no lateral action."""
        page,cell=bag_location(absolute_index)
        started=self.clock()
        bag=self.navigate_page(page)
        self.metrics['bag_navigation_seconds']=self.metrics.get('bag_navigation_seconds',0.)+self.clock()-started
        if bag is None or bag.active_set!=2 or not self._fresh(self._latest): return None
        def read():
            frame=normalize(self._latest.image)
            flare=self.reader.flare(core(frame,BAG_POINTS[cell]))
            tier=self.reader.tier(frame,BAG_POINTS[cell]) if flare else None
            return (flare,tier) if flare is not None else None
        result=self._perceive(read)
        return result if self._fresh(self._latest) and not self.cancel_requested() else None

    def inspect(self,absolute_index):
        """Bind the existing overlay reader without emitting Equip/Unequip."""
        page,cell=bag_location(absolute_index)
        before=self.navigate_page(page)
        selected=self._select(before,MeteoriteAction.EQUIP,None,cell,None,required_set=2)
        if selected is None or not self._current_panel(selected): return None
        item=selected[1]
        if self._tap(CloseMeteoriteDetail()) is None: return None
        ready=self._wait(lambda b:b.ready and b.active_set==2 and b.page==page and b.slots==before.slots)
        return item if ready is not None else None

    def _begin(self):
        self.metrics=dict(captures=0,capture_seconds=0.,perception_seconds=0.,freshness_rejects=0,retries=0)
        self.evidence={}
        return self.clock(),dict(getattr(self.reader,'calls',{}))

    def _select(self,before,action,slot,cell,expected,*,expected_slot=None,require_shared=False,required_set=None):
        if before is None or not before.ready or not self._fresh(self._latest): return None
        if required_set is not None and before.active_set!=required_set: return None
        if require_shared and before.active_set!=2: return None
        self.evidence['before']=self._latest
        frame=normalize(self._latest.image)
        if cell is not None:
            candidate=self._perceive(lambda:self.reader.candidate(self._latest.image,cell))
            if candidate is None: return None
            sprite,flare,tier=candidate
            if action is MeteoriteAction.EQUIP:
                slot=before.equip_slot(flare)
                if slot is None or (expected_slot is not None and slot!=expected_slot): return None
                if require_shared and tier!='Ethereal+': return None
            else:
                if (before.slots[slot] is not SlotState.OCCUPIED
                    or not self.reader.equipped_badge(self._latest.image,cell)
                    or sprite_score(frame,SLOT_POINTS[slot],sprite)<.78): return None
                # A Bag fallback must identify one slot unambiguously.
                matches=[i for i,p in enumerate(SLOT_POINTS) if before.slots[i] is SlotState.OCCUPIED
                         and sprite_score(frame,p,sprite)>=.78]
                if matches != [slot]: return None
            selection=SelectMeteoritesBagCell(cell)
        else:
            if before.slots[slot] is not SlotState.OCCUPIED: return None
            sprite=core(frame,SLOT_POINTS[slot]); flare=(slot==0); tier=None
            selection=SelectMeteoritesSlot(slot)
        selected_at=self._tap(selection); lineage=self._lineage
        if selected_at is None: return None
        item=self._wait(lambda i:i.action is action and i.flare is flare
                        and (tier is None or i.tier==tier)
                        and (not require_shared or (i.tier=='Ethereal+' and i.level>0))
                        and (expected is None or (i.flare,i.tier,i.level)==expected),
                        kind='detail',timeout=self.bounds.selection_timeout)
        if item is None or self._lineage!=lineage: return None
        self.evidence['overlay']=self._latest
        self.metrics['selection_to_overlay_seconds']=self.clock()-selected_at
        if self._perceive(lambda:sprite_score(normalize(self._latest.image),(.306,.372),sprite))<.78: return None
        # Strong fresh overlay + owned input lineage credits the hidden set;
        # no set/page input is allowed between this ready Bag and this panel.
        from bot.meteorites_reader import crop, TITLE_ROI
        return slot,item,lineage,sprite,crop(normalize(self._latest.image),TITLE_ROI).copy()

    def _current_panel(self,selected):
        slot,item,lineage,sprite,title=selected
        deadline=self.clock()+self.bounds.selection_timeout
        for _ in range(self.bounds.max_samples):
            if self._lineage!=lineage or self.cancel_requested() or self.clock()>=deadline: return False
            frame=self._capture()
            if frame is not None:
                return self._perceive(lambda:self._panel_matches(frame,selected))
            # A stream can return its latest frame until the next video tick.
            # Wait passively for fresh evidence; never reuse the rejected frame.
            self.sleeper(min(self.bounds.poll_interval,max(0,deadline-self.clock())))
        return False

    def _panel_matches(self,frame,selected):
        slot,item,lineage,sprite,title=selected
        n=normalize(frame.image)
        # Fast continuity: unchanged semantic title, sprite and lateral action.
        from bot.meteorites_reader import crop, TITLE_ROI
        if (not self.reader.main(n) or not self.reader.detail(n) or self.reader.loading(n)
                or self.reader.action(n) is not item.action
                or sprite_score(n,(.306,.372),sprite)<.78): return False
        if correlation(crop(n,TITLE_ROI),title)>=.97 and self._fresh(frame):
            return self._lineage==lineage
        fresh=self.reader.detail_sample(frame.image,sequence=frame.sequence,observed_at=frame.timestamp)
        return (fresh is not None and fresh.sequence==frame.sequence and fresh.observed_at==frame.timestamp
                and fresh.key==item.key and self._fresh(frame) and self._lineage==lineage)

    def _effect(self,before,slot,target):
        deadline=self.clock()+self.bounds.effect_timeout
        last=None; changed=None; persistent_panel=True
        for _ in range(self.bounds.max_samples):
            if self.cancel_requested(): return 'cancelled',None
            if self.clock()>=deadline: break
            bag=self._sample(read_page=False)
            if bag is not None:
                last=bag
                if not bag.overlay: persistent_panel=False
                if (not bag.overlay and bag.active_set==before.active_set
                    and bag.slots[slot] is target
                    and all(bag.slots[i] is before.slots[i] for i in range(11) if i!=slot)):
                    changed=bag
                    self.evidence['effect']=self._latest
                    break
            else:
                persistent_panel=False
            self.sleeper(min(self.bounds.poll_interval,max(0,deadline-self.clock())))
        if changed is not None: return 'effect',changed
        if last is not None and last.loading: return 'in_progress',last
        # Retained original actionable overlay is explicit negative evidence;
        # closed/unknown/transient UI alone cannot authorize a retry.
        return ('retained_panel' if persistent_panel and last is not None and last.overlay else 'ambiguous'),last

    def _no_effect(self,before,selected,cell):
        if not self._current_panel(selected): return None
        if self._tap(CloseMeteoriteDetail()) is None: return None
        stable_since=None; last=None
        deadline=self.clock()+self.bounds.readiness_timeout
        for _ in range(self.bounds.max_samples):
            if self.cancel_requested() or self.clock()>=deadline: return None
            bag=self._sample()
            slot,item=selected[:2]
            target=SlotState.OCCUPIED if item.action is MeteoriteAction.EQUIP else SlotState.EMPTY
            if (bag is not None and bag.ready and bag.page==1 and bag.active_set==before.active_set
                and bag.slots[slot] is target
                and all(bag.slots[i] is before.slots[i] for i in range(11) if i!=slot)):
                self.evidence['effect']=self._latest
                return 'effect',bag
            unchanged=(bag is not None and bag.ready and bag.active_set==before.active_set
                       and bag.page==before.page and bag.slots==before.slots)
            if unchanged and cell is not None:
                candidate=self.reader.candidate(self._latest.image,cell)
                unchanged=(candidate is not None and correlation(candidate[0],selected[3])>=.78
                           and self.reader.equipped_badge(self._latest.image,cell)==
                               (selected[1].action is MeteoriteAction.UNEQUIP))
            if unchanged:
                stable_since=stable_since if stable_since is not None else bag.observed_at
                last=bag
                if bag.observed_at-stable_since>=self.bounds.no_effect_stable_for: return 'no_effect',last
            else: stable_since=None
            self.sleeper(self.bounds.poll_interval)
        return None

    def _operate(self,action,before,*,slot=None,cell=None,expected=None,retry_no_effect=False,
                 expected_slot=None,require_shared=False,required_set=None,started,calls):
        action_inputs=0; item=None; after=None; verified_effect=None
        def result(outcome,reason):
            self.metrics['wall_seconds']=self.clock()-started
            for name,value in getattr(self.reader,'calls',{}).items():
                self.metrics[name+'_calls']=value-calls.get(name,0)
            r=MeteoriteResult(outcome,reason,slot,item,before,after,action_inputs,dict(self.metrics),effect=verified_effect)
            self.evidence['final']=self._latest
            record_best_effort(self.events,'meteorites.operation',action=action.value,outcome=outcome,
                               reason=reason,slot=slot,action_inputs=action_inputs,**self.metrics)
            return r
        if self.cancel_requested(): return result('cancelled','cancelled')
        for attempt in range(2 if retry_no_effect else 1):
            selected=self._select(before,action,slot,cell,expected,expected_slot=expected_slot,
                                  require_shared=require_shared,required_set=required_set)
            if selected is None:
                return result('cancelled' if self.cancel_requested() else 'rejected','selection_unverified')
            slot,item=selected[:2]
            if not self._current_panel(selected):
                return result('cancelled' if self.cancel_requested() else 'rejected','panel_not_current')
            try:
                tapped=self._tap(EquipMeteorite() if action is MeteoriteAction.EQUIP else UnequipMeteorite())
            except Exception:
                action_inputs+=1
                return result('ambiguous','input_dispatch_uncertain')
            if tapped is None:
                return result('cancelled' if self.cancel_requested() else 'rejected','input_not_current')
            action_inputs+=1
            target=SlotState.OCCUPIED if action is MeteoriteAction.EQUIP else SlotState.EMPTY
            outcome,after=self._effect(before,slot,target)
            if outcome=='effect':
                verified_effect=after
                effect_at=self.clock()
                self.metrics['tap_to_effect_seconds']=effect_at-tapped
                prepared=lambda b:b.ready and b.page==1 and b.active_set==before.active_set and b.slots[slot] is target and all(b.slots[i] is before.slots[i] for i in range(11) if i!=slot)
                # The effect frame already carries fresh set/slots/Loading.
                # Read its pager once while it remains current. Re-capture only
                # when this stronger same-frame readiness proof is unavailable.
                frame=self._latest
                after=None
                if self._fresh(frame) and not self.cancel_requested():
                    current=self._perceive(lambda:self.reader.bag_sample(frame.image,
                        sequence=frame.sequence,observed_at=frame.timestamp))
                    if (current is not None and current.sequence==frame.sequence
                        and current.observed_at==frame.timestamp and prepared(current)
                        and self._fresh(frame) and not self.cancel_requested()):after=current
                if after is None:after=self._wait(prepared)
                self.metrics['effect_to_readiness_seconds']=self.clock()-effect_at
                return result('success' if after else ('cancelled' if self.cancel_requested() else 'effect_not_ready'),
                              'slot_effect_verified' if after else 'slot_effect_readiness_unverified')
            if outcome!='retained_panel': return result(outcome,'slot_effect_unverified')
            # _tap invalidated selection; restore only this owned action lineage
            # to revalidate the exact retained panel, never an arbitrary overlay.
            retained=(slot,item,self._lineage,*selected[3:])
            reconciled=self._no_effect(before,retained,cell)
            if reconciled is None:
                return result('cancelled' if self.cancel_requested() else 'ambiguous','no_effect_unverified')
            status,unchanged=reconciled
            after=unchanged
            if status=='effect':
                verified_effect=unchanged
                self.metrics['tap_to_effect_seconds']=self.clock()-tapped
                self.metrics['effect_to_readiness_seconds']=0.
                return result('success','late_slot_effect_verified')
            if attempt or not retry_no_effect: return result('no_effect','stable_unchanged_slot_and_item')
            before=unchanged
            self.metrics['retries']+=1
            # A full new selection, fresh overlay, set and action authorize the
            # sole retry. No select-other/return workaround is implemented.
        return result('no_effect','retry_exhausted')
