"""MW's one established General target; bounded scrolling and fresh C3/C4."""
from pathlib import Path
from time import monotonic, perf_counter
import cv2
import numpy as np

from bot.directed_list_scroll import DirectedScrollOutcome, DirectedScrollResult
from bot.event_log import record_best_effort
from bot.perception.trading_center import row_bands
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import Swipe
from bot.trading_center import is_materials_content_ready
from bot.trading_materials_runtime import FreshMaterialFact
from bot.trading_materials_scroll import TRADING_MATERIALS_SCROLL_PROFILE
from bot.trading_operation import TradeRequest, TradePreconditionContext, execute_verified_trade
from bot.trading_productive_operation import execute_productive_trade
from bot.trading_row_facts import RowSample, MATERIALS_SECTION, consensus_row_samples

TARGET = 'hero_weapon_crafting_material'


class ProductiveMaterialsAdapter:
    """Only Weapon -> Hero; no inferred catalog index or premium cost."""

    def __init__(self, observer, actions, reader, panel_reader, *,
                 cancel_requested=lambda: False, events=None, clock=monotonic):
        self.observer, self.actions = observer, actions
        self.reader, self.panel_reader = reader, panel_reader
        self.cancel_requested, self.events, self.clock = cancel_requested, events, clock
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
        if confidence < .90:
            return None
        title_top = (int(.35*h) + pos[1]) / h
        title_bottom = title_top + template.shape[0] / h
        for top, bottom, center, complete in row_bands(frame):
            if complete and top <= title_top and title_bottom <= bottom:
                return top, center
        return None

    def _fresh(self, barrier, *, settled_after=0):
        if self.cancel_requested():
            raise RuntimeWaitCancelled('cancelled')
        return self.observer.wait_until(
            lambda s: is_materials_content_ready(s) and s.timestamp > settled_after,
            after_sequence=barrier, timeout=6., cancel_requested=self.cancel_requested)

    def locate(self, *, target, after_sequence, max_gestures=12):
        if target != TARGET:
            return DirectedScrollResult(DirectedScrollOutcome.TARGET_UNKNOWN, reason='unsupported_material')
        barrier, settled_after, previous = after_sequence, 0, None
        direction, reversed_once, gestures = 1, False, 0
        for _ in range(max_gestures + 1):
            s = self._fresh(barrier, settled_after=settled_after); barrier = s.sequence
            geometry = self.target_geometry(s.frame.image)
            if geometry is not None:
                confirm = self._fresh(barrier); barrier = confirm.sequence
                other = self.target_geometry(confirm.frame.image)
                if other is not None and abs(other[1] - geometry[1]) <= .015:
                    record_best_effort(self.events, 'trading.materials.located', target=target,
                                       source_sequence=barrier, gestures=gestures, row_y=other[1])
                    return DirectedScrollResult(DirectedScrollOutcome.TARGET_READY,
                        stable_row_y=other[1], stable_sequence=s.sequence, last_sequence=barrier)
                s = confirm
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
            profile = TRADING_MATERIALS_SCROLL_PROFILE
            delta = profile.max_delta
            start = profile.bottom_y if direction == 1 else profile.top_y
            end = start - direction * delta
            self.actions.execute(Swipe((profile.lane_x,start),(profile.lane_x,end),900),
                                 s.geometry,source_sequence=s.sequence,events=self.events)
            gestures += 1
            settled_after = self.clock() + 1.5
            record_best_effort(self.events, 'trading.materials.scroll', target=target,
                source_sequence=s.sequence, gesture_count=gestures, direction=direction)
        return DirectedScrollResult(DirectedScrollOutcome.NO_PROGRESS,
                                    last_sequence=barrier, reason='material_scan_exhausted')

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
