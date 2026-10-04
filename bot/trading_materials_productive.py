"""MW's one established General target; bounded scrolling and fresh C3/C4."""
from pathlib import Path
from dataclasses import replace
from numbers import Integral
from time import monotonic, perf_counter
import cv2
import numpy as np

from bot.directed_list_scroll import DirectedScrollOutcome, DirectedScrollResult
from bot.directed_list_scroll import navigate_to_target, ViewportReading, KnownListScrollProfile, PlannedGesture, ScrollDirection, SwipeResponse
from bot.trading_list_anchors import TradingListAnchors, ORDERED_MATERIAL_SUFFIX
from bot.event_log import record_best_effort
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import Swipe
from bot.trading_center import is_materials_content_ready
from bot.trading_materials_runtime import FreshMaterialFact
from bot.trading_materials_scroll import TRADING_MATERIALS_SCROLL_PROFILE
from bot.trading_operation import TradeRequest, TradePreconditionContext, execute_verified_trade
from bot.trading_productive_operation import execute_productive_trade
from bot.trading_row_facts import RowSample, MATERIALS_SECTION, consensus_row_samples

TARGET = 'hero_weapon_crafting_material'
TARGETED_PROFILE = KnownListScrollProfile(
    row_pitch=.1418, visible_rows=4, lane_x=.33, top_y=.02, bottom_y=.94,
    forward_start_y=.94, backward_start_y=.36, safe_window=(.43,.87),
    travel_limit=.92, row_tolerance=.015,
    forward_response=(
        SwipeResponse(.04,250,.005328,.008607,.029095),
        SwipeResponse(.14,250,.167616,.173766,.191387),
        SwipeResponse(.34,250,.443021,.455320,.484003),
        SwipeResponse(.59,250,.838915,.841374,.868010),
        SwipeResponse(.84,250,1.124564,1.127843,1.198334),
        SwipeResponse(.92,250,1.226200,1.229889,1.270052)),
    backward_response=(
        SwipeResponse(.14,250,.149997,.181964,.187292),
        SwipeResponse(.34,250,.457367,.463515,.479498),
        SwipeResponse(.58,250,.772938,.800052,.825051)))
# Acquired coarse response is deliberately independent of directed calibration.
MAX_ROBUST_FORWARD_SWIPE = PlannedGesture(ScrollDirection.FORWARD,9,.92,.33,.94,.02,250)


class ProductiveMaterialsAdapter:
    """Only Weapon -> Hero; row navigation never authorizes a trade."""

    def __init__(self, observer, actions, reader, panel_reader, *,
                 cancel_requested=lambda: False, events=None, clock=monotonic):
        self.observer, self.actions = observer, actions
        self.reader, self.panel_reader = reader, panel_reader
        self.cancel_requested, self.events, self.clock = cancel_requested, events, clock
        self.anchors = TradingListAnchors()
        self.template = cv2.imread(str(Path(__file__).resolve().parents[1] /
            'assets/ui/landmarks/trading-center/hero_weapon_material_title.png'),
            cv2.IMREAD_GRAYSCALE)
        if self.template is None:
            raise ValueError('Material title asset unavailable')

    def target_geometry(self, frame):
        h, w = frame.shape[:2]
        template = cv2.resize(self.template, (round(430 / 2712 * w), round(85 / 1220 * h)))
        roi = cv2.cvtColor(frame[int(.35*h):int(.94*h), int(.30*w):int(.47*w)], cv2.COLOR_BGR2GRAY)
        _, confidence, _, pos = cv2.minMaxLoc(cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED))
        if not np.isfinite(confidence) or confidence < .90:
            return None
        title_top = (int(.35*h) + pos[1]) / h
        # The acquired title origin is .014 below row top. Separator fitting
        # can choose a wrong phase in compressed frames; identity must not move.
        top = title_top-.014
        if .35 <= top and top+TARGETED_PROFILE.row_pitch <= .95:
            return top, top+TARGETED_PROFILE.row_pitch/2
        return None

    def _fresh(self, barrier, *, settled_after=0):
        if self.cancel_requested():
            raise RuntimeWaitCancelled('cancelled')
        return self.observer.wait_until(
            lambda s: is_materials_content_ready(s) and s.timestamp > settled_after,
            after_sequence=barrier, timeout=6., cancel_requested=self.cancel_requested)

    def _swipe(self, snapshot, swipe):
        if self.cancel_requested():
            raise RuntimeWaitCancelled('cancelled')
        if not is_materials_content_ready(snapshot) or not 0<=self.clock()-snapshot.timestamp<=2.:
            raise ValueError('targeted scroll context stale or lost')
        self.actions.execute(swipe,snapshot.geometry,
                             source_sequence=snapshot.sequence,events=self.events)

    def locate(self, *, target, after_sequence, max_gestures=12, use_targeted=True):
        if target != TARGET:
            return DirectedScrollResult(DirectedScrollOutcome.TARGET_UNKNOWN, reason='unsupported_material')
        if isinstance(max_gestures,bool) or not isinstance(max_gestures,Integral) or max_gestures<1:
            raise ValueError('max_gestures must be a positive integer')
        barrier, settled_after, previous = after_sequence, 0, None
        direction, reversed_once, gestures = 1, False, 0
        started = self.clock()
        captures, corrections, reversals, fallbacks = 0, 0, 0, 0
        plans = []
        while True:
            s = self._fresh(barrier, settled_after=settled_after); barrier = s.sequence
            captures += 1
            geometry = self.target_geometry(s.frame.image)
            if geometry is not None:
                confirm = self._fresh(barrier); barrier = confirm.sequence
                captures += 1
                other = self.target_geometry(confirm.frame.image)
                if other is not None and abs(other[1] - geometry[1]) <= .015:
                    record_best_effort(self.events, 'trading.materials.located', target=target,
                        source_sequence=barrier, gestures=gestures, row_y=other[1],
                        observations=captures, corrections=corrections, direction_reversals=reversals,
                        elapsed=self.clock()-started, fallbacks=fallbacks)
                    return DirectedScrollResult(DirectedScrollOutcome.TARGET_READY,
                        gestures=tuple(plans), stable_row_y=other[1], stable_sequence=confirm.sequence,
                        last_sequence=barrier, observations=captures, corrections=corrections,
                        direction_reversals=reversals, elapsed=self.clock()-started,fallbacks=fallbacks)
                s = confirm
                geometry = other
            anchors = self.anchors.read(s.frame.image) if use_targeted else ()
            if use_targeted and gestures < max_gestures:
                pending = [(s, geometry, anchors)]
                latest = s
                acquired = False
                def observe():
                    nonlocal latest, barrier, captures, acquired
                    if pending:
                        latest, geometry, pairs = pending.pop()
                    else:
                        latest = self._fresh(barrier, settled_after=settled_after)
                        captures += 1
                        geometry = self.target_geometry(latest.frame.image)
                        pairs = self.anchors.read(latest.frame.image) if geometry is None else ((TARGET,geometry[1]),)
                    barrier = latest.sequence
                    if pairs and not acquired:
                        acquired = True
                        record_best_effort(self.events,'trading.materials.targeted.anchor',
                            source_sequence=barrier,anchors=tuple(name for name,_ in pairs),
                            row_centers=tuple(y for _,y in pairs),
                            acquisition_gestures=gestures,observations=captures,elapsed=self.clock()-started)
                    return ViewportReading(tuple(name for name,_ in pairs),barrier,
                        target_row_y=geometry[1] if geometry else None,
                        row_centers=tuple(y for _,y in pairs),
                        guard_ok=is_materials_content_ready(latest),
                        at_bottom=any(name=='guild_commodity' for name,_ in pairs))
                def emit(plan):
                    nonlocal gestures, settled_after
                    self._swipe(latest,Swipe((plan.lane_x,plan.start_y),(plan.lane_x,plan.end_y),plan.duration_ms))
                    gestures += 1
                    plans.append(plan)
                    settled_after = self.clock()+.35
                result = navigate_to_target(catalog=ORDERED_MATERIAL_SUFFIX,target=TARGET,
                    profile=TARGETED_PROFILE,observe=observe,emit=emit,
                    max_gestures=max_gestures-gestures,cancel_requested=self.cancel_requested,
                    coarse=MAX_ROBUST_FORWARD_SWIPE,
                    clock=self.clock,
                    telemetry=lambda **kw: record_best_effort(self.events,'trading.materials.targeted.step',**kw))
                corrections += result.corrections
                reversals += result.direction_reversals
                record_best_effort(self.events,'trading.materials.targeted.result',
                    target=target,outcome=result.outcome.value,reason=result.reason,
                    gestures=gestures,observations=captures,corrections=corrections,
                    direction_reversals=reversals,elapsed=self.clock()-started,fallbacks=fallbacks)
                if result.outcome is DirectedScrollOutcome.CANCELLED:
                    raise RuntimeWaitCancelled('cancelled')
                if result.outcome in (DirectedScrollOutcome.TARGET_READY,
                        DirectedScrollOutcome.GUARD_LOST,DirectedScrollOutcome.MUTATED):
                    return replace(result,gestures=tuple(plans),observations=captures,
                                   corrections=corrections,direction_reversals=reversals,
                                   elapsed=self.clock()-started,fallbacks=fallbacks)
                # Reacquire context before the existing safe incremental fallback;
                # never reset its gesture budget or keep the adaptive model.
                fallbacks += 1
                record_best_effort(self.events,'trading.materials.targeted.fallback',reason=result.reason)
                use_targeted = False
                previous = None
                continue
            h,w = s.frame.image.shape[:2]
            view = cv2.resize(cv2.cvtColor(s.frame.image[int(.36*h):int(.93*h),
                int(.30*w):int(.47*w)], cv2.COLOR_BGR2GRAY), (160,240))
            if previous is not None and np.abs(view.astype(float)-previous).mean() < 1.5:
                if reversed_once:
                    break
                direction, reversed_once = -1, True
            if gestures == max_gestures:
                break
            previous = view.astype(float)
            # Original safe incremental fallback, with the remaining total budget.
            profile = TRADING_MATERIALS_SCROLL_PROFILE
            duration = 900
            delta = profile.max_delta
            start = profile.bottom_y if direction == 1 else profile.top_y
            end = start - direction * delta
            self._swipe(s,Swipe((profile.lane_x,start),(profile.lane_x,end),duration))
            gestures += 1
            plan = PlannedGesture(ScrollDirection.FORWARD if direction==1 else ScrollDirection.BACKWARD,
                3,delta,profile.lane_x,start,end,duration)
            if plans and plans[-1].direction is not plan.direction:
                reversals += 1
                corrections += 1
            plans.append(plan)
            settled_after = self.clock() + 1.5
            record_best_effort(self.events, 'trading.materials.scroll', target=target,
                source_sequence=s.sequence, gesture_count=gestures, direction=direction,
                phase='incremental')
        return DirectedScrollResult(DirectedScrollOutcome.NO_PROGRESS,
                                    gestures=tuple(plans),last_sequence=barrier, reason='material_scan_exhausted',
                                    observations=captures,corrections=corrections,direction_reversals=reversals,
                                    elapsed=self.clock()-started,fallbacks=fallbacks)

    def read(self, *, target, after_sequence):
        if target != TARGET:
            return None
        samples=[]; barrier=after_sequence
        for _ in range(3):
            s=self._fresh(barrier); barrier=s.sequence
            geometry=self.target_geometry(s.frame.image)
            started=perf_counter(); diagnostics={}
            pair=(self.reader.read_pair(s.frame.image,geometry[0],diagnostics=diagnostics)
                  if geometry else None)
            record_best_effort(self.events,'trading.materials.facts.sample',target=target,
                source_sequence=barrier,pair=pair,geometry=geometry,
                reader_seconds=perf_counter()-started,diagnostics=diagnostics)
            if pair is None:
                samples.clear(); continue
            samples.append(RowSample(target,MATERIALS_SECTION,geometry[1],*pair,barrier))
            fact=consensus_row_samples(samples[-2:])
            if fact is not None:
                return FreshMaterialFact(s,fact)
        return None

    def trade(self, *, operation, snapshot, row_fact, quantity):
        def read_row(barrier):
            fresh=self.read(target=operation.trading_item_id,after_sequence=barrier)
            return fresh.row_fact if fresh is not None else None
        def execute(**callbacks):
            request=TradeRequest(row_fact,quantity,frozenset({'weapon_material'}),
                                 expected_item_id=TARGET)
            context=TradePreconditionContext(
                is_trading_screen=is_materials_content_ready(snapshot),
                section=MATERIALS_SECTION, clean=is_materials_content_ready(snapshot),
                sequence=snapshot.sequence)
            return execute_verified_trade(request=request,context=context,targets=None,tap=None,
                                          cancel_requested=self.cancel_requested,**callbacks)
        result=execute_productive_trade(
            snapshot=snapshot,row_fact=row_fact,quantity=quantity,observer=self.observer,
            actions=self.actions,panel_reader=self.panel_reader,read_row_fact=read_row,
            row_ready=is_materials_content_ready,execute=execute,
            cancel_requested=self.cancel_requested,events=self.events,clock=self.clock)
        record_best_effort(self.events,'trading.materials.trade.result',
            outcome=result.outcome.value,reason=result.reason,inputs=result.inputs,
            before_fact=vars(result.before_fact),
            after_fact=vars(result.after_fact) if result.after_fact else None)
        return result
