from dataclasses import replace
import pytest
from bot.directed_list_scroll import (
    KnownListScrollProfile, ViewportReading, DirectedScrollOutcome as O,
    ScrollDirection as D, navigate_to_target,
    PlannedGesture, SwipeResponse,
)

P=KnownListScrollProfile(.10,4,.33,.30,.90,travel_limit=.54)
COARSE=PlannedGesture(D.FORWARD,8,.80,.33,.90,.10,250)

def reading(index, sequence, y=.5, *, target=False, **kw):
    return ViewportReading((index,),sequence,target_row_y=y if target else None,
                           row_centers=(y,),**kw)

def run(readings, target=9, **kw):
    observations=iter(readings);emits=[]
    result=navigate_to_target(catalog=tuple(range(20)),target=target,profile=kw.pop('profile',P),
        observe=lambda:next(observations),emit=kw.pop('emit',emits.append),
        max_gestures=kw.pop('max_gestures',4),**kw)
    return result,emits

def test_visible_target_zero_swipes_and_consensus():
    r,e=run([reading(9,1,target=True),reading(9,2,target=True)])
    assert r.outcome is O.TARGET_READY and not e and r.observations==2


@pytest.mark.parametrize('kw,outcome',[(dict(guard_ok=False),O.GUARD_LOST),
                                      (dict(readable=False),O.UNREADABLE)])
def test_coarse_requires_strong_clean_context(kw,outcome):
    r,e=run([ViewportReading((),1,**kw)],coarse=COARSE)
    assert r.outcome is outcome and not e


def test_coarse_needs_no_index_and_post_anchor_starts_same_directed_loop():
    r,e=run([ViewportReading((),1),reading(4,2),reading(9,3,target=True),
             reading(9,4,target=True)],coarse=COARSE)
    assert r.outcome is O.TARGET_READY and len(e)==2 and e[0] is COARSE
    assert r.observations==4 and r.corrections==0


def test_coarse_target_ready_does_not_emit_directed_gesture():
    r,e=run([ViewportReading((),1),reading(9,2,target=True),reading(9,3,target=True)],coarse=COARSE)
    assert r.outcome is O.TARGET_READY and e==[COARSE]


def test_coarse_post_capture_must_be_fresh():
    r,e=run([ViewportReading((),1),reading(4,1)],coarse=COARSE)
    assert r.reason=='stale_observation' and e==[COARSE]


def test_coarse_does_not_repeat_when_anchor_is_missing():
    r,e=run([ViewportReading((),1),ViewportReading((),2)],coarse=COARSE)
    assert r.outcome is O.UNREADABLE and e==[COARSE]


def test_total_budget_includes_coarse():
    r,e=run([ViewportReading((),1),reading(4,2)],coarse=COARSE,max_gestures=1)
    assert r.outcome is O.BUDGET_EXHAUSTED and e==[COARSE]


def test_coarse_revision_change_invalidates_even_visible_target():
    r,e=run([ViewportReading((),1),reading(9,2,target=True,revision=1)],coarse=COARSE)
    assert r.outcome is O.MUTATED and e==[COARSE]


def test_cancellation_after_coarse_prevents_next_observation_or_input():
    emitted=[]
    r,e=run([ViewportReading((),1)],coarse=COARSE,emit=emitted.append,
            cancel_requested=lambda:bool(emitted))
    assert r.outcome is O.CANCELLED and emitted==[COARSE]


def test_modal_after_coarse_stops_without_directed_input():
    r,e=run([ViewportReading((),1),reading(4,2,guard_ok=False)],coarse=COARSE)
    assert r.outcome is O.GUARD_LOST and e==[COARSE]


def test_coarse_inconsistent_post_anchors_never_authorize_directed():
    r,e=run([ViewportReading((),1),ViewportReading((3,4),2,row_centers=(.5,.8))],coarse=COARSE)
    assert r.reason=='geometry_mismatch' and e==[COARSE]


def test_calibrated_directed_aims_safe_window_center_and_uses_duration():
    profile=replace(P,safe_window=(.4,.8),forward_response=(SwipeResponse(.5,250,.49,.5,.51),))
    log=[]
    r,e=run([reading(5,1),reading(9,2,target=True),reading(9,3,target=True)],
            profile=profile,telemetry=lambda **kw:log.append(kw))
    plan=next(v for v in log if v['phase']=='plan')
    assert plan['desired_y']==pytest.approx(.6)
    assert plan['target_expected_y']==pytest.approx(.6,abs=.006)
    assert e[0].duration_ms==250 and r.outcome is O.TARGET_READY


@pytest.mark.parametrize('post,directions',[(5,[D.FORWARD,D.FORWARD]),
                                          (14,[D.FORWARD,D.BACKWARD])])
def test_after_coarse_residual_and_overshoot_use_same_loop(post,directions):
    r,e=run([ViewportReading((),1),reading(0,2),reading(post,3),reading(9,4,target=True),
             reading(9,5,target=True)],coarse=COARSE)
    assert r.outcome is O.TARGET_READY and len(e)==3
    assert [v.direction for v in e[1:]]==directions


def test_directed_stuck_after_coarse_stops_at_two_inputs():
    r,e=run([ViewportReading((),1),reading(4,2),reading(4,3)],coarse=COARSE)
    assert r.reason=='stuck' and len(e)==2


def test_strong_target_evidence_still_required_after_coarse():
    r,e=run([ViewportReading((),1),reading(9,2)],coarse=COARSE)
    assert r.reason=='target_row_missing' and e==[COARSE]


def test_directed_choice_is_independent_of_gesture_number():
    profile=replace(P,safe_window=(.4,.8),forward_response=(SwipeResponse(.5,250,.49,.5,.51),))
    _,plain=run([reading(4,1),reading(9,2,target=True),reading(9,3,target=True)],profile=profile)
    _,acquired=run([ViewportReading((),1),reading(4,2),reading(9,3,target=True),
                    reading(9,4,target=True)],profile=profile,coarse=COARSE)
    assert acquired[1:]==plain


def test_visible_target_with_contradictory_anchors_is_not_ready():
    r,e=run([ViewportReading((8,9),1,target_row_y=.7,row_centers=(.5,.7))])
    assert r.reason=='geometry_mismatch' and not e


def test_complete_strong_target_need_not_be_at_desired_center():
    profile=replace(P,safe_window=(.4,.8))
    r,e=run([reading(9,1,y=.85,target=True),reading(9,2,y=.85,target=True)],profile=profile)
    assert r.outcome is O.TARGET_READY and not e


def test_cancelled_reversal_plan_is_not_counted_as_dispatched():
    cancel=[False]
    def log(**event):
        if event['phase']=='plan' and event['direction']=='backward':cancel[0]=True
    r,e=run([reading(0,1),reading(14,2)],telemetry=log,cancel_requested=lambda:cancel[0])
    assert r.outcome is O.CANCELLED and len(e)==1
    assert r.direction_reversals==r.corrections==0

@pytest.mark.parametrize('target,anchor,direction',[(9,0,D.FORWARD),(0,9,D.BACKWARD)])
def test_direction_and_large_initial_travel(target,anchor,direction):
    r,e=run([reading(anchor,1),reading(target,2,target=True),reading(target,3,target=True)],target)
    assert r.outcome is O.TARGET_READY and len(e)==1
    assert e[0].direction is direction and e[0].delta==pytest.approx(.54)

def test_residual_and_post_reading_reused():
    r,e=run([reading(0,1),reading(4,2),reading(9,3,target=True),reading(9,4,target=True)])
    assert r.outcome is O.TARGET_READY and len(e)==2 and r.observations==4
    assert e[1].delta<e[0].delta and r.corrections==1

def test_overshoot_corrects_opposite_direction():
    r,e=run([reading(0,1),reading(14,2),reading(9,3,target=True),reading(9,4,target=True)])
    assert r.outcome is O.TARGET_READY and r.direction_reversals==1
    assert [g.direction for g in e]==[D.FORWARD,D.BACKWARD]

@pytest.mark.parametrize('anchor,target,edge',[(9,0,'at_top'),(0,9,'at_bottom')])
def test_boundary_veto(anchor,target,edge):
    r,e=run([reading(anchor,1,**{edge:True})],target)
    assert r.reason=='boundary' and not e

def test_stuck_no_second_input():
    r,e=run([reading(0,1),reading(0,2)])
    assert r.reason=='stuck' and len(e)==1

def test_wrong_direction_stops():
    r,e=run([reading(4,1),reading(3,2)])
    assert r.reason=='wrong_direction' and len(e)==1

def test_last_swipe_can_confirm_target_without_extra_input():
    r,e=run([reading(0,1),reading(9,2,target=True),reading(9,3,target=True)],max_gestures=1)
    assert r.outcome is O.TARGET_READY and len(e)==1

def test_max_swipe_bound():
    r,e=run([reading(0,1),reading(4,2)],max_gestures=1)
    assert r.outcome is O.BUDGET_EXHAUSTED and len(e)==1

def test_invalid_anchor_and_out_of_range_target():
    r,e=run([reading(30,1)])
    assert r.outcome is O.UNREADABLE and not e
    r,e=run([],target=30)
    assert r.outcome is O.TARGET_UNKNOWN and not e and r.observations==0

@pytest.mark.parametrize('kw',[dict(guard_ok=False),dict(readable=False)])
def test_modal_or_unknown_no_swipe(kw):
    r,e=run([reading(0,1,**kw)])
    assert r.outcome in (O.GUARD_LOST,O.UNREADABLE) and not e

def test_modal_during_swipe_no_fallback_input():
    r,e=run([reading(0,1),reading(4,2,guard_ok=False)])
    assert r.outcome is O.GUARD_LOST and len(e)==1

def test_cancellation_before_and_after_dispatch():
    r,e=run([],cancel_requested=lambda:True)
    assert r.outcome is O.CANCELLED and not e
    cancelled=[]
    r,_=run([reading(0,1)],cancel_requested=lambda:bool(cancelled),emit=cancelled.append)
    assert r.outcome is O.CANCELLED and len(cancelled)==1 and r.observations==1

def test_mutation_invalidates_even_visible_target():
    r,e=run([reading(0,1,revision='before'),reading(9,2,target=True,revision='after')])
    assert r.outcome is O.MUTATED and len(e)==1

def test_repeated_invocation_has_independent_model():
    for _ in range(2):
        r,e=run([reading(0,1),reading(9,2,target=True),reading(9,3,target=True)])
        assert r.outcome is O.TARGET_READY and e[0].delta==pytest.approx(.54)

def test_geometry_mismatch_safe_fallback_result():
    sample=ViewportReading((0,1),1,row_centers=(.4,.7))
    r,e=run([sample]);assert r.reason=='geometry_mismatch' and not e

def test_calibration_mismatch_after_motion():
    r,e=run([reading(19,1,.8),reading(1,2,.4)],target=0,profile=replace(P,travel_limit=.05))
    assert r.reason=='calibration_mismatch' and len(e)==1

def test_grid_uses_rows_not_item_distance():
    p=replace(P,columns=4)
    r,e=run([reading(0,1,.5),reading(16,2,target=True),reading(16,3,target=True)],target=16,profile=p)
    assert r.outcome is O.TARGET_READY and e[0].delta==pytest.approx(.3)

def test_stale_post_input_is_not_progress():
    r,e=run([reading(0,1),reading(4,1)])
    assert r.reason=='stale_observation' and len(e)==1

def test_predicted_visible_target_needs_strong_identity():
    r,e=run([reading(8,1)],target=9)
    assert r.reason=='target_expected_but_unverified' and not e


def test_reversal_budget_counts_only_dispatched_reversals():
    r,e=run([reading(0,1),reading(14,2)],max_reversals=0)
    assert r.reason=='reversal_bound' and len(e)==1 and r.direction_reversals==0


def test_observes_final_motion_even_when_target_enters_view():
    records=[]
    r,e=run([reading(0,1),reading(9,2,target=True),reading(9,3,target=True)],
            telemetry=lambda **fields:records.append(fields))
    motion=[s for s in records if s['phase']=='motion']
    assert r.outcome is O.TARGET_READY and len(motion)==1
    assert motion[0]['actual_rows']==9
