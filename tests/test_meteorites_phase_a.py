"""Portable focal replay plus temporal/input boundaries; no hardware or raw."""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from bot.capture import FrameSnapshot
from bot.catalog import build_default_resolver
from bot.meteorites_actions import *
from bot.meteorites_reader import (
    MeteoritesReader, MeteoritesDetector, normalize, crop, parse_title,
    TITLE_ROI, LEVEL_ROI, PAGE_ROI, core, sprite_score,
)
from bot.meteorites_runtime import MeteoritesRuntime, MeteoritesBounds
from bot.meteorites_semantics import *
from bot.observations import ObservationBatch
from bot.ocr import OcrResult

FIXTURES=Path(__file__).parent/'fixtures/meteorites_phase_a'
MANIFEST=json.loads((FIXTURES/'manifest.json').read_text(encoding='utf8'))
IMAGES={s['id']:cv2.imread(str(FIXTURES/(s['id']+'.png'))) for s in MANIFEST['entries']}


def image(prefix):
    return next(v for k,v in IMAGES.items() if k.startswith(prefix))


class RecordedOcr:
    """OCR boundary replay keyed to pixels, not which method is invoked."""
    def __init__(self):
        self.reads={}
        for s in MANIFEST['entries']:
            f=normalize(IMAGES[s['id']]); sem=s['semantic']
            if sem.get('overlay') is True:
                typ=sem['type'] if sem['type'].startswith('Flare') else '('+sem['type']+')'
                title=sem['tier']+' Meteorite '+typ+(f" +{sem['level']}" if sem['level'] else '')
                self.add(f,TITLE_ROI,title)
                self.add(f,LEVEL_ROI,'+0' if sem['level']==0 else 'Max')
            else:
                page=sem.get('page',2 if s['id'].startswith(('10_','13_')) else 1)
                self.add(f,PAGE_ROI,f'{page}/40')

    def add(self,f,roi,text):
        img=cv2.resize(crop(f,roi),None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
        self.reads[hashlib.sha256(img.tobytes()).hexdigest()]=text

    def recognize(self,img):
        text=self.reads.get(hashlib.sha256(img.tobytes()).hexdigest(),'')
        return OcrResult(text,.99 if text else 0.)


@pytest.fixture
def reader(): return MeteoritesReader(RecordedOcr())


def test_fixture_and_runtime_asset_provenance():
    root=FIXTURES.parents[2]
    for s in MANIFEST['entries']:
        assert hashlib.sha256((FIXTURES/(s['id']+'.png')).read_bytes()).hexdigest()==s['sha256']
        assert s['source'].startswith('screencaps/semantic/meteorites/')
    assets=json.loads((root/'datasets/meteorites_visual_assets_manifest.json').read_text(encoding='utf8'))
    for entry in assets['assets']:
        assert hashlib.sha256((root/entry['asset']).read_bytes()).hexdigest()==entry['sha256']


@pytest.mark.parametrize('s',MANIFEST['entries'],ids=lambda s:s['id'])
def test_focal_fixture_replay(reader,s):
    frame=IMAGES[s['id']];sem=s['semantic']
    bag=reader.bag_sample(frame,sequence=1,observed_at=1)
    if sem.get('main_tab_negative'):
        assert bag is None
        assert reader.tab_sample(frame)==sem['tab']
    if sem.get('overlay') is True:
        detail=reader.detail_sample(frame,sequence=1,observed_at=1)
        assert detail is not None
        assert (detail.flare,detail.tier,detail.level,detail.action.value)==(
            sem['type'].startswith('Flare'),sem['tier'],sem['level'],sem['lateral_action'].lower())
    if 'occupied_slots' in sem:
        assert bag is not None and bag.ready
        assert bag.slots.count(SlotState.OCCUPIED)==sem['occupied_slots']
        assert bag.active_set==sem['active_set']
    if '_frame_0' in s['id'] and not sem.get('individual_effect'):
        assert bag is None or not bag.ready


@pytest.mark.parametrize('height',[1220,1224])
def test_source_shapes_use_relative_geometry(reader,height):
    f=cv2.resize(image('03_'),(2712,height))
    b=reader.bag_sample(f,sequence=1,observed_at=1,read_page=False)
    assert b.active_set==2 and b.slots==(SlotState.EMPTY,)*11
    assert reader.candidate(f,11)[1:]==(True,'Ethereal+')


def test_main_base_and_overlay_resolve(reader):
    detector=MeteoritesDetector()
    observations=detector.detect(image('08_'))
    state=build_default_resolver().resolve(ObservationBatch(1,1.,observations))
    assert state.base_context==SCREEN_METEORITES
    assert state.overlays==(OVERLAY_METEORITES_DETAIL,)
    state=build_default_resolver().resolve(ObservationBatch(2,2.,detector.detect(image('09_equip_flare_frame_017'))))
    assert METEORITES_LOADING in state.overlays


def test_grid_flare_tier_page_and_slot_binding(reader):
    bag=image('03_'); normal=image('10_')
    assert len(BAG_POINTS)==16 and bag_location(25)==(2,8)
    assert reader.candidate(bag,0)[1:]==(True,'Ethereal')
    assert reader.candidate(bag,11)[1:]==(True,'Ethereal+')
    assert reader.candidate(normal,8)[1:]==(False,'Ethereal+')
    assert sprite_score(normalize(image('20_')),(.306,.372),core(normalize(image('15_')),SLOT_POINTS[2]))>.90
    assert reader.equipped_badge(image('15_'),0)
    assert not reader.equipped_badge(bag,11)


def test_positive_zero_max_and_damaged_titles(reader):
    assert parse_title('Ethereal+ Meteorite (Shield) +21')[2]==21
    assert parse_title('Ethereal+ Meteorite Flare (ATK) MAX')[2]==30
    assert parse_title('Ethereal Meteorite Flare (ATK)')[2] is None
    assert parse_title('Ethereal+ Meteorite (Shield) +') is None
    assert parse_title('Ethereal Meteorite Flare (ATK) +99') is None
    f=image('36_').copy(); n=normalize(f)
    reader.engine.add(n,LEVEL_ROI,'unreadable')
    assert reader.detail_sample(f,sequence=1,observed_at=1) is None


def test_lock_never_authorizes_lateral_action(reader):
    f=image('08_').copy(); h,w=f.shape[:2]
    f[round(.26*h):round(.4*h),round(.19*w):round(.25*w)]=0
    assert reader.detail_sample(f,sequence=1,observed_at=1) is None


class Clock:
    def __init__(self): self.now=100.
    def __call__(self): return self.now
    def sleep(self,seconds): self.now+=seconds


class SceneSource:
    def __init__(self,clock,initial):
        self.clock=clock; self.scene=image(initial); self.queue=[]; self.sequence=0
        self.stale=0; self.duplicate=False
    def show(self,prefixes):
        self.queue=[image(p) for p in prefixes]
    def get_frame(self):
        self.clock.now+=.025
        if self.queue: self.scene=self.queue.pop(0)
        if not self.duplicate:self.sequence+=1
        age=3. if self.stale else 0.
        self.stale=max(0,self.stale-1)
        return FrameSnapshot(self.scene,self.clock.now-age,self.sequence)


class Actions:
    def __init__(self,source,overlay,initial,effects,*,no_effect=0):
        self.source=source; self.overlay=overlay; self.initial=initial;self.effects=effects
        self.inputs=[]; self.no_effect=no_effect; self.action_count=0;self.on_action=lambda:None
    def execute(self,action,geometry,**kwargs):
        self.inputs.append(action)
        if isinstance(action,(SelectMeteoritesBagCell,SelectMeteoritesSlot)):
            self.source.show([self.overlay])
        elif isinstance(action,(EquipMeteorite,UnequipMeteorite)):
            self.action_count+=1
            self.on_action()
            if self.action_count>self.no_effect:self.source.show(self.effects)
        elif isinstance(action,CloseMeteoriteDetail):self.source.show([self.initial])
        elif isinstance(action,SelectMeteoritesSet):
            self.source.show(['38_restore_set1_frame_017','38_restore_set1_last'] if action.number==1
                             else ['24_' if action.number==3 else '03_'])
        elif isinstance(action,NextMeteoritesPage):self.source.show(['10_'])
        elif isinstance(action,PreviousMeteoritesPage):self.source.show(['09_equip_flare_frame_018'])


def runtime(reader,*,initial='03_',overlay='08_',effects=None,no_effect=0):
    clock=Clock();source=SceneSource(clock,initial)
    actions=Actions(source,overlay,initial,effects or ['09_equip_flare_frame_002','09_equip_flare_frame_017','09_equip_flare_frame_018'],no_effect=no_effect)
    rt=MeteoritesRuntime(source,reader,actions,clock=clock,sleeper=clock.sleep,
        bounds=MeteoritesBounds(selection_timeout=.6,effect_timeout=.7,readiness_timeout=.7,
                               no_effect_stable_for=.15,poll_interval=.025))
    return rt,source,actions


@pytest.mark.parametrize('initial,overlay,effect,index,slot',[
    ('03_','08_','09_equip_flare_frame_018',12,0),
    ('10_','11_','12_',25,1),('13_','14_','15_',25,2)])
def test_equip_individual_effect(reader,initial,overlay,effect,index,slot):
    rt,source,actions=runtime(reader,initial=initial,overlay=overlay,effects=[effect])
    r=rt.equip(index)
    assert r.succeeded and r.slot==slot and r.action_inputs==1
    assert r.before.slots[slot] is SlotState.EMPTY and r.after.slots[slot] is SlotState.OCCUPIED
    assert r.after.page==1 and actions.action_count==1
    assert r.metrics['captures']>0 and r.metrics['ocr_calls']>0


@pytest.mark.parametrize('initial,overlay,effect,slot',[
    ('15_','18_','19_',0),('19_','20_','21_',2),('21_','22_','23_',1)])
def test_unequip_slot_individual_effect(reader,initial,overlay,effect,slot):
    rt,source,actions=runtime(reader,initial=initial,overlay=overlay,effects=[effect])
    r=rt.unequip_slot(slot)
    assert r.succeeded and r.action_inputs==1 and actions.action_count==1
    assert r.before.slots[slot] is SlotState.OCCUPIED and r.after.slots[slot] is SlotState.EMPTY


def test_bag_unequip_fallback(reader):
    rt,_,actions=runtime(reader,initial='15_',overlay='18_',effects=['19_'])
    assert rt.unequip_bag(1,0).succeeded
    assert isinstance(actions.inputs[0],SelectMeteoritesBagCell)


def test_set_change_requires_loaded_slots(reader):
    rt,_,actions=runtime(reader)
    b=rt.select_set(1)
    assert b.active_set==1 and b.slots==(SlotState.OCCUPIED,)*11
    assert len(actions.inputs)==1
    b=rt.select_set(3)
    assert b.active_set==3 and b.slots==(SlotState.EMPTY,)*11


def test_page_navigation_verifies_actual_pager(reader):
    rt,_,actions=runtime(reader,initial='09_equip_flare_frame_018')
    assert rt.navigate_page(2).page==2
    assert rt.navigate_page(1).page==1
    assert [type(a) for a in actions.inputs]==[NextMeteoritesPage,PreviousMeteoritesPage]


def test_retained_panel_stable_no_effect(reader):
    rt,_,actions=runtime(reader,no_effect=2)
    r=rt.equip(12)
    assert r.outcome=='no_effect' and r.after.ready and r.action_inputs==1
    assert actions.action_count==1


@pytest.mark.parametrize('no_effect,outcome,count',[(1,'success',2),(3,'no_effect',2)])
def test_retry_requires_full_new_selection_and_is_bounded(reader,no_effect,outcome,count):
    rt,_,actions=runtime(reader,no_effect=no_effect)
    r=rt.equip(12,retry_no_effect=True)
    assert r.outcome==outcome and r.action_inputs==count and actions.action_count==count
    assert sum(isinstance(a,SelectMeteoritesBagCell) for a in actions.inputs)==2
    assert r.metrics['retries']==1


def test_late_effect_waits_without_second_input(reader):
    rt,_,actions=runtime(reader,effects=['09_equip_flare_frame_017']*8+['09_equip_flare_frame_018'])
    assert rt.equip(12,retry_no_effect=True).succeeded
    assert actions.action_count==1


@pytest.mark.parametrize('effect,outcome',[
    ('09_equip_flare_frame_017','in_progress'),('03_','ambiguous'),('24_','ambiguous'),('07_','ambiguous')])
def test_ambiguous_or_transition_never_retries(reader,effect,outcome):
    rt,_,actions=runtime(reader,effects=[effect])
    r=rt.equip(12,retry_no_effect=True)
    assert r.outcome==outcome and actions.action_count==1


def test_cancellation_before_and_after_input(reader):
    rt,_,actions=runtime(reader)
    rt.cancel_requested=lambda:True
    assert rt.equip(12).outcome=='cancelled' and not actions.inputs
    rt,_,actions=runtime(reader); cancelled=[False]
    rt.cancel_requested=lambda:cancelled[0]
    actions.on_action=lambda:cancelled.__setitem__(0,True)
    assert rt.equip(12,retry_no_effect=True).outcome=='cancelled' and actions.action_count==1


def test_stale_selection_observations_do_not_authorize_input(reader):
    rt,source,actions=runtime(reader)
    source.stale=100
    r=rt.equip(12,retry_no_effect=True)
    assert r.outcome=='rejected' and not actions.inputs and r.metrics['freshness_rejects']>0


def test_duplicate_observations_after_action_do_not_authorize_retry(reader):
    rt,source,actions=runtime(reader)
    actions.on_action=lambda:setattr(source,'duplicate',True)
    r=rt.equip(12,retry_no_effect=True)
    assert r.outcome=='ambiguous' and actions.action_count==1


@pytest.mark.parametrize('duplicates',[1,4])
def test_panel_revalidation_waits_for_new_stream_tick(reader,duplicates):
    rt,source,actions=runtime(reader)
    before=rt.ready()
    selected=rt._select(before,MeteoriteAction.EQUIP,None,11,None)
    assert selected is not None
    original=source.get_frame
    remaining=[duplicates]
    def capture():
        source.duplicate=remaining[0]>0
        remaining[0]=max(0,remaining[0]-1)
        return original()
    source.get_frame=capture
    assert rt._current_panel(selected)
    assert rt.metrics['freshness_rejects']==duplicates and actions.action_count==0


@pytest.mark.parametrize('cancel',[False,True])
def test_panel_revalidation_duplicate_stream_is_bounded_and_cancelable(reader,cancel):
    rt,source,actions=runtime(reader)
    selected=rt._select(rt.ready(),MeteoriteAction.EQUIP,None,11,None)
    source.duplicate=True
    started=rt.clock()
    if cancel:rt.cancel_requested=lambda:rt.clock()-started>=.1
    assert not rt._current_panel(selected)
    assert rt.clock()-started<=rt.bounds.selection_timeout+.03
    assert actions.action_count==0


def test_wrong_overlay_cannot_bind_to_selected_candidate(reader):
    rt,_,actions=runtime(reader,overlay='14_')
    assert rt.equip(12).outcome=='rejected' and actions.action_count==0


def test_input_lineage_loss_invalidates_retained_panel(reader):
    rt,_,actions=runtime(reader)
    before=rt.ready()
    selected=rt._select(before,MeteoriteAction.EQUIP,None,11,None)
    assert selected is not None
    rt._lineage+=1
    assert not rt._current_panel(selected) and actions.action_count==0


def test_cancel_race_immediately_before_operation_tap(reader):
    rt,_,actions=runtime(reader)
    current=rt._current_panel
    def cancel_after_check(selected):
        ok=current(selected)
        rt.cancel_requested=lambda:True
        return ok
    rt._current_panel=cancel_after_check
    r=rt.equip(12)
    assert r.outcome=='cancelled' and r.action_inputs==0 and actions.action_count==0


def test_transport_uncertainty_never_repeats_input(reader):
    rt,_,actions=runtime(reader)
    execute=actions.execute
    def uncertain(action,*args,**kwargs):
        execute(action,*args,**kwargs)
        if isinstance(action,EquipMeteorite):raise RuntimeError('transport timed out')
    actions.execute=uncertain
    r=rt.equip(12,retry_no_effect=True)
    assert r.outcome=='ambiguous' and r.action_inputs==1 and actions.action_count==1


def test_verified_effect_waits_for_readiness_and_does_not_repeat(reader):
    rt,source,actions=runtime(reader,effects=['09_equip_flare_frame_018'])
    effect=rt._effect
    def verified_then_unreadable(*args):
        outcome,bag=effect(*args)
        source.show(['07_'])
        rt._latest=FrameSnapshot(image('07_'),rt._latest.timestamp,rt._latest.sequence)
        return outcome,bag
    rt._effect=verified_then_unreadable
    r=rt.equip(12,retry_no_effect=True)
    assert r.outcome=='effect_not_ready' and r.action_inputs==1 and actions.action_count==1


def test_acquired_action_targets_respect_source_geometry():
    from bot.action_executor import ActionExecutor,FrameGeometry
    class Adb:
        def __init__(self): self.taps=[]
        def tap(self,x,y): self.taps.append((x,y))
    adb=Adb(); executor=ActionExecutor(adb)
    assert executor.target_for(EquipMeteorite())==(.220,.310)
    assert executor.target_for(UnequipMeteorite())==(.220,.310)
    assert executor.target_for(SelectQuickMenuMeteorites())==(.076,.496)
    for height in (1220,1224):
        executor.execute(SelectMeteoritesSlot(2),FrameGeometry(2712,height))
    assert adb.taps[0]!=adb.taps[1]


@pytest.mark.parametrize('quick',[False,True])
def test_entry_uses_existing_verified_navigation(reader,quick):
    from bot.catalog import SCREEN_LOBBY,MENU_QUICK
    from bot.runtime_observer import RuntimeSnapshot,RuntimeFacts
    from bot.action_executor import FrameGeometry
    from bot.state import ResolutionStatus,ResolvedState
    from bot.verified_transition import VerifiedTransitionResult,VerifiedTransitionOutcome
    from bot.semantic_actions import OpenQuickMenu
    rt,source,actions=runtime(reader)
    def snapshot(base,overlays=()):
        frame=source.get_frame();batch=ObservationBatch(frame.sequence,frame.timestamp,())
        return RuntimeSnapshot(frame,batch,ResolvedState(ResolutionStatus.RESOLVED,frame.sequence,frame.timestamp,base,overlays),RuntimeFacts(),FrameGeometry.from_frame(frame.image))
    initial=snapshot(SCREEN_LOBBY)
    class Observer:
        def observe(self):return initial
    class Transition:
        def execute(self,name,action,before,**kwargs):
            assert kwargs['precondition'](before)
            actions.inputs.append(action)
            after=snapshot(SCREEN_LOBBY,(MENU_QUICK,)) if isinstance(action,OpenQuickMenu) else snapshot(SCREEN_METEORITES)
            assert kwargs['expected'](after)
            return VerifiedTransitionResult(name,VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,1,0,after,action_source_snapshot=before)
    assert rt.enter(Observer(),Transition(),via_quick_menu=quick).ready
    assert [type(a) for a in actions.inputs]==([OpenQuickMenu,SelectQuickMenuMeteorites] if quick else [OpenMeteorites])


def test_unknown_entry_never_opens_quick_menu(reader):
    from types import SimpleNamespace as S
    from bot.state import ResolutionStatus
    rt,_,actions=runtime(reader)
    initial=S(state=S(status=ResolutionStatus.UNKNOWN,base_context=None,overlays=()))
    observer=S(observe=lambda:initial)
    transition=S(execute=lambda *a,**k:pytest.fail('unknown source input'))
    assert rt.enter(observer,transition,via_quick_menu=True) is None
    assert not actions.inputs


def test_reader_cannot_reuse_a_stale_fact_on_a_new_frame(reader):
    from dataclasses import replace
    rt,_,actions=runtime(reader)
    read=reader.bag_sample
    reader.bag_sample=lambda *a,**kw:replace(read(*a,**kw),sequence=1,observed_at=1.)
    r=rt.equip(12)
    assert r.outcome=='rejected' and not actions.inputs and r.metrics['freshness_rejects']>0


def test_late_effect_during_negative_reconciliation_prevents_retry(reader):
    rt,source,actions=runtime(reader,no_effect=2)
    execute=actions.execute
    def late(action,*args,**kwargs):
        execute(action,*args,**kwargs)
        if isinstance(action,CloseMeteoriteDetail):source.show(['09_equip_flare_frame_018'])
    actions.execute=late
    r=rt.equip(12,retry_no_effect=True)
    assert r.succeeded and r.reason=='late_slot_effect_verified'
    assert r.action_inputs==1 and actions.action_count==1 and r.metrics['retries']==0


@pytest.mark.parametrize('slot,shared,expected_outcome',[(0,True,'success'),(1,True,'rejected')])
def test_b1_expected_slot_guard_precedes_lateral_input(reader,slot,shared,expected_outcome):
    rt,_,actions=runtime(reader)
    result=rt.equip(12,expected_slot=slot,require_shared=shared)
    assert result.outcome==expected_outcome
    assert actions.action_count==(1 if expected_outcome=='success' else 0)


def test_b1_shared_positive_level_guard_rejects_zero_before_lateral_input(reader):
    rt,_,actions=runtime(reader,overlay='36_')
    result=rt.equip(12,expected_slot=0,require_shared=True,retry_no_effect=True)
    assert not result.succeeded and actions.action_count==0


def test_b1_inspection_reuses_bound_overlay_without_equipping(reader):
    rt,_,actions=runtime(reader)
    item=rt.inspect(12)
    assert (item.flare,item.tier,item.level)==(True,'Ethereal+',30)
    assert actions.action_count==0
    assert [type(a) for a in actions.inputs]==[SelectMeteoritesBagCell,CloseMeteoriteDetail]


def test_b1_group_walk_uses_flare_sprite_without_bag_name_ocr(reader):
    rt,_,actions=runtime(reader)
    assert rt.group_cell(12)==(True,'Ethereal+')
    before=reader.calls['ocr']
    assert rt.group_cell(16)[0] is False
    # Only the pager was OCRed, never every Bag title.
    assert reader.calls['ocr']-before==1 and actions.action_count==0


def test_b1_cleanup_wrong_set_cannot_dispatch(reader):
    rt,_,actions=runtime(reader,initial='38_restore_set1_last')
    result=rt.unequip_slot(1,required_set=2)
    assert result.outcome=='rejected' and not actions.inputs


def test_b1_preserves_effect_fact_when_readiness_is_unreadable(reader):
    rt,source,actions=runtime(reader,effects=['09_equip_flare_frame_018'])
    effect=rt._effect
    def then_unreadable(*args):
        outcome,bag=effect(*args)
        source.show(['07_'])
        rt._latest=FrameSnapshot(image('07_'),rt._latest.timestamp,rt._latest.sequence)
        return outcome,bag
    rt._effect=then_unreadable
    result=rt.equip(12,expected_slot=0,require_shared=True)
    assert result.outcome=='effect_not_ready' and result.after is None
    assert result.effect.slots[0] is SlotState.OCCUPIED
    assert result.effect.slots[1:]==(SlotState.EMPTY,)*10 and actions.action_count==1
