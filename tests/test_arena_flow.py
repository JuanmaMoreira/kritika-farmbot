"""Software orchestration scenarios are synthetic; portable replays own physical GT."""
from types import SimpleNamespace as NS
import hashlib
import cv2
import numpy as np
import pytest

from bot.arena_actions import ArenaAction, ArenaControl as C, POINTS
from bot.arena_flow import ArenaFlow
from bot.arena_flow_reader import ArenaFlowReader
from bot.arena_semantics import (ArenaDifficulty as D, ArenaPreparationFacts, ArenaEconomyFacts,
                                ArenaBatchResult, ArenaResultProvenance, ArenaBatchExecution)
from bot.capture import FrameSnapshot
from bot.flow_contracts import FlowStatus
from bot.ocr import RapidOcrEngine
from bot.state import ResolutionStatus
from bot.action_executor import ActionExecutor, FrameGeometry


class World:
    states=('lobby','select_mode','selection','challenge','config','loading','battle','win','terminal','insufficient','ranking','blocker','unknown','socket')
    def __init__(self):
        self.now=100.; self.seq=0; self.surface='lobby'; self.difficulty=D.HARD
        self.buffs=[False,False,False]; self.stock=[923,999,999]; self.badges=106
        self.x8=True; self.upon=False; self.inputs=[]; self.queue=[]; self.cancel=False
        self.cancel_on=None; self.start_count=0; self.no_effect=None; self.ambiguous=False
        self.block=False; self.start_error=False; self.native_calls=0; self.reservation=8
        self.entry_ranking=False
        self.wait_states=['loading','battle','challenge','win','battle','terminal']
    def clock(self): return self.now
    def sleep(self,seconds): self.now+=seconds
    def image(self): return np.full((90,160,3),self.states.index(self.surface),dtype=np.uint8)
    def get_frame(self):
        if self.queue: self.surface=self.queue.pop(0)
        self.now+=.001; self.seq+=1
        return FrameSnapshot(self.image(),self.now,self.seq)
    def refresh_native(self):
        self.native_calls+=1
        return self.get_frame()
    def observe(self):
        frame=self.get_frame()
        base='screen.socket' if self.surface=='socket' else 'screen.lobby' if self.surface=='lobby' else 'screen.arena'
        overlays=('popup.socket_inventory_full',) if self.surface=='blocker' else ()
        return NS(frame=frame,state=NS(status=ResolutionStatus.RESOLVED,base_context=base,overlays=overlays))
    def execute(self,action,geometry,**kw):
        control=action.control; self.inputs.append(control)
        if control is C.START:
            self.start_count+=1
            if self.start_error: raise RuntimeError('ADB reply lost')
        if self.cancel_on is control: self.cancel=True
        if self.no_effect is control: return
        if control is C.BATTLE: self.surface='select_mode'
        elif control is C.ARENA: self.surface='ranking' if self.entry_ranking else 'selection'
        elif control in (C.EASY,C.NORMAL,C.HARD): self.difficulty=D[control.name]; self.surface='challenge'
        elif control is C.BACK: self.surface='selection'
        elif control in (C.BUFF1,C.BUFF2,C.BUFF3):
            i=(C.BUFF1,C.BUFF2,C.BUFF3).index(control)
            self.buffs[i]=not self.buffs[i]; self.stock[i]+=(-self.reservation if self.buffs[i] else self.reservation)
        elif control is C.X8: self.x8=True
        elif control is C.CONFIG: self.surface='config'
        elif control is C.UPON_DEFEAT: self.upon=False
        elif control is C.START:
            if self.block: self.surface='blocker'
            else: self.queue=list(self.wait_states)
        elif control is C.RESULT_OK: self.surface='insufficient'; self.badges=2
        elif control is C.BADGES_NO: self.surface='challenge'
        elif control is C.RANKING_OK: self.surface='selection' if self.entry_ranking else 'challenge'; self.entry_ranking=False


class Visuals:
    def __init__(self,w): self.w=w
    def state(self,f): return self.w.states[int(f[0,0,0])]
    def lobby(self,f): return self.state(f)=='lobby'
    def select_mode(self,f): return self.state(f)=='select_mode'
    def selection(self,f): return self.state(f)=='selection'
    def clean_challenge(self,f): return self.state(f)=='challenge'
    challenge=clean_challenge
    def config(self,f): return self.state(f)=='config'
    def terminal(self,f): return self.state(f)=='terminal'
    def ranking(self,f): return self.state(f)=='ranking'
    def insufficient(self,f): return self.state(f)=='insufficient'
    def loading(self,f): return self.state(f)=='loading'
    def active(self,f): return self.state(f)=='battle'
    def back_visible(self,f): return self.state(f) in ('challenge','selection','select_mode')
    def has(self,f,n):
        return self.state(f)=={'bag_full':'blocker','config_start':'blocker','insufficient':'insufficient'}.get(n,'!')
    def preparation(self,f): return ArenaPreparationFacts(self.w.difficulty,tuple(self.w.buffs),self.w.x8)
    def upon_defeat(self,f): return self.w.upon


class Reader:
    max_age=2.
    def __init__(self,w): self.w=w; self.visuals=Visuals(w); self.ocr_calls=0
    def prewarm(self,s): self.ocr_calls+=1
    def economy(self,s,**kw):
        self.ocr_calls+=8
        return ArenaEconomyFacts(self.w.badges,tuple(self.w.stock),self.visuals.preparation(s.image),s.sequence,s.timestamp)
    def _integer(self,*args): self.ocr_calls+=2; return self.w.badges,1.
    def terminal(self,s,execution,**kw): return self.visuals.terminal(s.image) and s.sequence>execution.after_sequence
    def read(self,s,execution,**kw):
        self.ocr_calls+=4
        if self.w.ambiguous or not self.visuals.terminal(s.image): return None
        used=(self.w.badges//8)*8
        return ArenaBatchResult(execution.difficulty,8,used,getattr(self.w,'won',used),s.timestamp,
            ArenaResultProvenance(execution.run_id,execution.source_id,s.sequence,hashlib.sha256(s.image.tobytes()).hexdigest(),1.,1.))


def flow(w,**kw):
    return ArenaFlow(NS(source=w,observe=w.observe),w,Reader(w),D.EASY,
        clock=w.clock,sleeper=w.sleep,cancel_requested=lambda:w.cancel,transition_timeout=1.,
        batch_timeout=30.,unknown_grace=3.,**kw)


def test_one_batch_real_route_transients_and_return():
    w=World(); r=flow(w).run()
    assert r.succeeded and r.phase=='returned' and not r.physical_operation_may_be_active
    assert r.batch_result.used_tickets==r.batch_result.won_tickets==104
    assert w.inputs==[C.BATTLE,C.ARENA,C.EASY,C.BUFF1,C.BUFF2,C.BUFF3,C.CONFIG,C.START,C.RESULT_OK,C.BADGES_NO]
    assert w.start_count==1 and r.execution.start_verified
    assert r.metrics['wait_ocr_calls']==0
    assert r.metrics['wait_captures']==5 and r.metrics['terminal_detections']==1
    assert r.metrics['double_points_reserved']==8 and w.native_calls>=5


def test_new_ranking_at_arena_entry_is_closed_once_without_start_confusion():
    w=World(); w.entry_ranking=True
    r=flow(w).run()
    assert r.succeeded and w.inputs.count(C.RANKING_OK)==1 and w.start_count==1
    assert w.inputs.index(C.RANKING_OK)<w.inputs.index(C.EASY)<w.inputs.index(C.START)


def test_own_configuration_fades_during_start_without_second_input():
    w=World(); w.wait_states=['loading','config','loading','battle','terminal']
    r=flow(w).run()
    assert r.succeeded and w.start_count==1 and r.metrics['wait_ocr_calls']==0


def test_explicit_existing_batch_segment_observes_and_closes_without_start():
    w=World(); w.surface='battle'; w.queue=['battle','battle','terminal']
    receipt=ArenaBatchExecution('original-run','new-source-segment',D.EASY,8,90.,0,True)
    r=flow(w).observe_started_batch(receipt,106)
    assert r.succeeded and r.execution.run_id=='original-run'
    assert w.inputs==[C.RESULT_OK,C.BADGES_NO] and w.start_count==0


def test_existing_batch_cancellation_preserves_physical_active_status():
    w=World(); w.surface='battle'; w.cancel=True
    receipt=ArenaBatchExecution('original-run','new-source-segment',D.EASY,8,90.,0,True)
    r=flow(w).observe_started_batch(receipt,106)
    assert r.status is FlowStatus.CANCELLED and not w.inputs
    assert r.physical_operation_may_be_active


def test_unverified_existing_batch_is_rejected_without_input():
    w=World(); receipt=ArenaBatchExecution('run','segment',D.EASY,8,90.,0,False)
    with pytest.raises(ValueError): flow(w).observe_started_batch(receipt,106)
    assert not w.inputs


def test_terminal_exceeding_explicit_authorization_is_not_acknowledged():
    from dataclasses import replace
    w=World(); f=flow(w,authorized_badge_ceiling=104); original=f.reader.read
    def read(*args,**kw):
        return replace(original(*args,**kw),used_tickets=105,won_tickets=100)
    f.reader.read=read
    r=f.run()
    assert r.error=='result_exceeds_badge_authorization' and r.phase=='result_ambiguous'
    assert w.start_count==1 and C.RESULT_OK not in w.inputs


def test_insufficient_arrives_after_challenge_during_final_base_observation():
    w=World(); original_execute=w.execute; original_observe=w.observe
    def execute(action,geometry,**kw):
        original_execute(action,geometry,**kw)
        if action.control is C.RESULT_OK: w.surface='challenge'
    late=[True]
    def observe():
        if C.RESULT_OK in w.inputs and late[0]:
            late[0]=False; w.surface='insufficient'
        return original_observe()
    w.execute=execute; w.observe=observe
    r=flow(w).run()
    assert r.succeeded and w.inputs.count(C.RESULT_OK)==w.inputs.count(C.BADGES_NO)==1


@pytest.mark.parametrize('difficulty',list(D))
def test_explicit_difficulty(difficulty):
    w=World(); f=flow(w); f.difficulty=difficulty
    assert f.run().succeeded and w.difficulty is difficulty
    assert C[difficulty.value] in w.inputs


@pytest.mark.parametrize('initial',[(True,True,False),(True,True,True),(False,True,False)])
def test_selected_mandatory_buffs_are_not_touched(initial):
    w=World(); w.buffs=list(initial); w.stock[2]=10
    assert flow(w).run().succeeded
    for i,control in enumerate((C.BUFF1,C.BUFF2)):
        assert (control in w.inputs)==(not initial[i])
    assert w.buffs[2] is False


@pytest.mark.parametrize('stock,selected,expected_taps',[(104,False,1),(103,False,0),(None,False,0),(96,True,1),(104,True,0),(None,True,1)])
def test_double_points_coverage_and_unknown_reserve(stock,selected,expected_taps):
    w=World(); w.buffs[2]=selected; w.stock[2]=stock
    # Unknown stock has no proven refund; an OFF result can retain unreadable count.
    original=w.execute
    if stock is None:
        def execute(a,g,**kw):
            if a.control is C.BUFF3:
                w.inputs.append(C.BUFF3); w.buffs[2]=False
            else: original(a,g,**kw)
        w.execute=execute
    r=flow(w).run()
    assert r.succeeded and w.inputs.count(C.BUFF3)==expected_taps
    assert r.metrics['double_points_reserved']==(8 if stock==104 and not selected else 0)
    assert all(isinstance(c,C) for c in w.inputs)  # no purchase vocabulary exists


def test_bad_reservation_never_starts():
    w=World(); w.reservation=7
    r=flow(w).run()
    assert r.error=='buff_reservation_uncredited' and w.start_count==0


@pytest.mark.parametrize('badges',[0,2,7])
def test_insufficient_badges_no_config_no_start(badges):
    w=World(); w.badges=badges; r=flow(w).run()
    assert r.error=='fewer_than_eight_badges' and C.CONFIG not in w.inputs and C.START not in w.inputs


@pytest.mark.parametrize('stock',[0,7,103,None])
def test_gold_economic_branch_stops_without_purchase(stock):
    w=World(); w.stock[0]=stock; r=flow(w).run()
    assert r.error=='gold_buff_purchase_requires_acquisition' and w.start_count==0
    assert C.BUFF1 not in w.inputs


def test_x8_from_off_only_once():
    w=World(); w.x8=False
    assert flow(w).run().succeeded and w.inputs.count(C.X8)==1


def test_unknown_x8_no_tap():
    w=World(); w.x8=None
    assert flow(w).run().error=='x8_unknown' and C.X8 not in w.inputs


@pytest.mark.parametrize('upon,expected',[(False,0),(True,1),(None,0)])
def test_upon_defeat_positive_states(upon,expected):
    w=World(); w.upon=upon; r=flow(w).run()
    assert w.inputs.count(C.UPON_DEFEAT)==expected
    assert r.succeeded if upon is not None else (r.error=='upon_defeat_unknown' and w.start_count==0)


def test_unknown_stream_checkbox_refreshes_natively_before_start():
    w=World(); f=flow(w); original=w.refresh_native
    def native():
        frame=original()
        if w.surface=='config': w.upon=False
        return frame
    w.refresh_native=native
    w.upon=None
    assert f.run().succeeded and C.UPON_DEFEAT not in w.inputs and w.start_count==1


def test_start_uncertainty_never_retries_or_allows_same_owner_restart():
    w=World(); w.start_error=True; f=flow(w); r=f.run()
    assert r.physical_operation_may_be_active and r.phase=='start_uncertain'
    assert f.run().error=='previous_physical_operation_unresolved' and w.start_count==1


def test_blocker_without_relief_is_known_not_started():
    w=World(); w.block=True; r=flow(w).run()
    assert r.error=='socket_relief_unavailable' and not r.physical_operation_may_be_active
    assert w.start_count==1 and C.RESULT_OK not in w.inputs


def test_blocker_relief_revalidates_and_restarts_only_known_failed_entry():
    from bot.socket_inventory_relief import SocketReliefOutcome
    from bot.relief_policy import ReliefCoordinator
    w=World(); w.block=True
    class Transition:
        def execute(self,name,action,before,**kw):
            assert kw['precondition'](before)
            w.surface='socket'; after=w.observe()
            assert kw['expected'](after)
            return NS(succeeded=True)
    class Relief:
        def run(self,plan,cancel_requested,*,policy):
            assert plan.expected_return_state=='screen.arena'
            w.surface='challenge'; w.block=False
            w.badges=98
            return NS(outcome=SocketReliefOutcome.RELIEVED)
    r=flow(w,socket_relief=Relief(),reliefs=ReliefCoordinator(),transition=Transition()).run()
    assert r.succeeded and w.start_count==2 and r.metrics['planned_consumption']==96


@pytest.mark.parametrize('control',[C.BATTLE,C.ARENA,C.EASY,C.BUFF1,C.BUFF2,C.BUFF3,C.X8,
                                 C.CONFIG,C.UPON_DEFEAT,C.START,C.RESULT_OK,C.BADGES_NO])
def test_cancel_after_inputs_never_sends_followup(control):
    w=World(); w.cancel_on=control; w.upon=True; w.x8=False
    r=flow(w).run()
    assert control in w.inputs
    assert r.status is FlowStatus.CANCELLED and w.inputs[-1] is control
    assert r.physical_operation_may_be_active==(control is C.START)


def test_cancel_before_observation():
    w=World(); w.cancel=True; r=flow(w).run()
    assert r.status is FlowStatus.CANCELLED and not w.inputs and w.seq==0


@pytest.mark.parametrize('mode',['cancel','timeout','unknown','ambiguous'])
def test_active_failure_never_acknowledges_or_restarts(mode):
    w=World(); f=flow(w)
    if mode=='ambiguous': w.ambiguous=True
    elif mode=='timeout': w.wait_states=['loading','challenge']
    elif mode=='unknown': w.wait_states=['loading','unknown']
    else:
        original=w.get_frame
        def capture():
            s=original()
            if w.surface=='battle': w.cancel=True
            return s
        w.get_frame=capture
    r=f.run()
    assert not r.succeeded and w.start_count==1 and C.RESULT_OK not in w.inputs
    assert r.physical_operation_may_be_active==(mode!='ambiguous')
    if mode=='ambiguous': assert r.phase=='result_ambiguous'


@pytest.mark.parametrize('control',[C.CONFIG,C.START,C.RESULT_OK,C.BADGES_NO,C.X8])
def test_unconfirmed_input_is_not_repeated(control):
    w=World(); w.no_effect=control; w.x8=control is not C.X8
    r=flow(w).run()
    assert not r.succeeded and w.inputs.count(control)==1


def test_action_executor_double_tap_uses_actual_geometry():
    taps=[]; executor=ActionExecutor(NS(tap=lambda x,y:taps.append((x,y))))
    geometry=FrameGeometry(800,400)
    executor.execute(ArenaAction(C.X8),geometry)
    assert taps==[(628,292),(628,292)]
    executor.execute(ArenaAction(C.START),geometry)
    assert taps[-1]==(400,350) and len(taps)==3
    assert POINTS[C.CONFIG]!=POINTS[C.START]


@pytest.mark.parametrize('fixture,badges,buffs',[
    ('off',106,(923,999,999)),('buff1',106,(915,999,999)),
    ('buff12',106,(915,991,999)),('after',2,(819,895,999))])
def test_portable_economy_real_ocr(fixture,badges,buffs):
    reader=ArenaFlowReader(RapidOcrEngine(),clock=lambda:100.)
    image=cv2.imread(f'tests/fixtures/arena_b1/{fixture}.png')
    facts=reader.economy(FrameSnapshot(image,100.,2))
    assert facts.available_badges==badges and facts.free_buffs==buffs


def test_portable_navigation_loading_and_modal_occlusion():
    reader=ArenaFlowReader(RapidOcrEngine()); v=reader.visuals
    load=lambda name:cv2.imread(f'tests/fixtures/arena_b1/{name}.png')
    assert v.lobby(load('lobby')) and v.select_mode(load('select_mode')) and v.loading(load('loading'))
    assert v.lobby(load('lobby_variant'))
    assert v.clear(load('select_mode'),'flow_back_button')
    assert v.clear(load('prepared_live'),'flow_challenge_back_button')
    assert not v.clean_challenge(load('loading'))
    dimmed=(load('off')*.5).astype(np.uint8)
    assert not v.clean_challenge(dimmed)
    ranking=load('ranking_entry')
    assert v.ranking(ranking) and not v.terminal(ranking) and not v.selection(ranking)
    config=load('config_variant')
    assert v.config(config) and v.upon_defeat(config) is False and not v.terminal(config)
    assert v.upon_defeat(load('config_native_full')) is False
    insufficient=load('insufficient_live')
    assert v.insufficient(insufficient) and not v.clean_challenge(insufficient) and not v.terminal(insufficient)
    assert v.terminal(load('terminal_48')) and not v.clean_challenge(load('terminal_48'))
    # Synthetic contamination is a contract negative, not acquired ON artwork.
    h,w=config.shape[:2]
    config[round(.759*h):round(.778*h),round(.656*w):round(.666*w)]=(0,220,255)
    assert v.upon_defeat(config) is None


def test_portable_live_result_48_uses_same_frame_focal_karats():
    reader=ArenaFlowReader(RapidOcrEngine(),clock=lambda:100.)
    image=cv2.imread('tests/fixtures/arena_b1/terminal_48.png')
    receipt=ArenaBatchExecution('single-live-replay','portable-source',D.EASY,8,90.,1,True)
    result=reader.read(FrameSnapshot(image,100.,2),receipt,run_id=receipt.run_id,source_id=receipt.source_id)
    assert result is not None and result.used_tickets==result.won_tickets==48
    assert reader.ocr_calls==4


@pytest.mark.parametrize('won',[0,72,104,105])
def test_flow_delivers_typed_wins_or_leaves_invalid_terminal_open(won):
    w=World(); w.won=won; r=flow(w).run()
    if won<=104:
        assert r.succeeded and r.batch_result.won_tickets==won
    else:
        assert not r.succeeded and not r.physical_operation_may_be_active and C.RESULT_OK not in w.inputs


def test_config_does_not_start_with_expired_economy():
    w=World(); original=w.execute
    def execute(a,g,**kw):
        original(a,g,**kw)
        if a.control is C.CONFIG: w.now+=3.
    w.execute=execute
    r=flow(w).run()
    assert r.error=='prepared_economy_expired' and w.start_count==0 and not r.physical_operation_may_be_active


def test_stale_economic_ocr_stops_before_config():
    w=World(); f=flow(w); original=f.reader.economy
    def economy(s,**kw):
        facts=original(s,**kw); w.now+=3.; return facts
    f.reader.economy=economy
    r=f.run()
    assert r.error=='economy_unknown' and C.CONFIG not in w.inputs


def test_source_discontinuity_during_batch_preserves_possible_operation():
    w=World(); original=w.get_frame
    def get_frame():
        s=original()
        if w.surface=='battle': return FrameSnapshot(s.image,s.timestamp,0)
        return s
    w.get_frame=get_frame
    r=flow(w).run()
    assert r.physical_operation_may_be_active and not r.succeeded and w.start_count==1
    assert 'source_discontinuity' in r.evidence and C.RESULT_OK not in w.inputs
    assert not r.execution.start_verified


def test_cancel_during_terminal_ocr_does_not_close_or_cancel_game():
    w=World(); f=flow(w)
    def read(*a,**kw): w.cancel=True; return None
    f.reader.read=read
    r=f.run()
    assert r.status is FlowStatus.CANCELLED and not r.physical_operation_may_be_active
    assert C.RESULT_OK not in w.inputs and w.start_count==1


def test_prewarm_precedes_fresh_economy():
    w=World(); f=flow(w); original=f.reader.prewarm
    def warm(s): original(s); w.now+=4.
    f.reader.prewarm=warm
    assert f.run().succeeded


def test_challenge_alone_cannot_authorize_a_new_batch():
    w=World(); w.surface='challenge'; r=flow(w).run()
    assert not r.succeeded and not w.inputs


def test_authorized_badges_bound_rejects_a_larger_natural_batch():
    w=World(); r=flow(w,authorized_badge_ceiling=96).run()
    assert r.error=='batch_exceeds_badge_authorization' and w.start_count==0
    assert C.BUFF1 not in w.inputs


def test_runtime_builder_reuses_shared_dependencies_without_observation(monkeypatch):
    from bot.productive_runtime import ProductiveRuntime
    from bot.relief_policy import ReliefCoordinator
    w=World(); engine=RapidOcrEngine(); reliefs=ReliefCoordinator(); transition=object()
    runtime=ProductiveRuntime(NS(),NS(source=w,observe=w.observe),w,object(),object(),
        object(),object(),object(),None,NS(is_requested=lambda:False),ocr_engine=engine,reliefs=reliefs)
    monkeypatch.setattr(runtime,'build_verified_transition',lambda:transition)
    f=runtime.build_arena_flow(D.NORMAL,authorized_badge_ceiling=104)
    assert f.reader.engine is engine and f.source is w and f.actions is w and f.reliefs is reliefs
    assert f.transition is transition and f.difficulty is D.NORMAL and f.authorized_badge_ceiling==104
    assert not w.inputs and w.seq==0
