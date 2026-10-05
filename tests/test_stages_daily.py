from types import SimpleNamespace as S
import pytest
from bot.ads_manager import AdsManager, AdObservation, AdsOutcome, AdsResult
from bot.stages_daily_flow import StagesDailyFlow
from bot.stages_balances import StageBalances
from bot.flow_contracts import FlowResult, FlowStatus
from bot.stages_actions import StageControl as C

class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now
    def sleep(self,t):self.now+=t

def manager(sequence,**kw):
    c=Clock();seen=[];items=iter(sequence);last=sequence[-1]
    def observe():
        nonlocal last
        last=next(items,last);return last
    m=AdsManager(observe,lambda s,p:seen.append(('close',p)),
        lambda s:seen.append(('refuse',s)),lambda s:seen.append(('back',s)),
        clock=c,sleeper=c.sleep,deadline=6,launch_deadline=2,poll_interval=.5,**kw)
    return m,seen

def test_ad_waits_for_safe_affordance_and_handles_two_steps():
    m,seen=manager([AdObservation(1,skip_ticket=True),AdObservation(2,active=True),
        AdObservation(3,active=True,close_point=(.9,.05),close_key='next'),
        AdObservation(4,active=True,close_point=(.9,.05),close_key='next'),
        AdObservation(5,active=True),
        AdObservation(6,active=True,close_point=(.95,.06),close_key='x'),
        AdObservation(7,returned=True)])
    r=m.complete_requested_launch()
    assert r.outcome is AdsOutcome.RETURNED
    assert seen==[('refuse',1),('close',(.9,.05)),('close',(.95,.06))]

def test_ad_unknown_layout_never_taps_or_calls_success():
    m,seen=manager([AdObservation(1,active=True),AdObservation(2,returned=False)])
    assert m.complete_requested_launch().outcome is AdsOutcome.RECOVERY_FAILED
    assert seen==[]

def test_return_to_game_without_active_ad_is_not_success():
    m,seen=manager([AdObservation(1,returned=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.ABORTED_RECOVERED
    assert seen==[]

def test_ticket_refusal_not_repeated_when_effect_inconclusive():
    m,seen=manager([AdObservation(1,skip_ticket=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.RECOVERY_FAILED
    assert seen==[('refuse',1)]

def test_explicit_unavailable_is_not_technical_failure():
    m,seen=manager([AdObservation(1,unavailable=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.UNAVAILABLE
    assert seen==[]

def test_external_recovery_is_bounded_back_only():
    m,seen=manager([AdObservation(1,active=True),AdObservation(2,external=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.RECOVERY_FAILED
    assert seen==[('back',2)]*4  # two normal external + two terminal inputs

class Nav:
    def __init__(self):
        self.calls=[];self.events=None;self.cursor=0;self.cancel_requested=lambda:False
        c=Clock();self.clock=c;self.observer=S(_sleeper=c.sleep)
    def enter_target(self):self.calls.append('enter');return S(sequence=1)
    def prepare_ad(self,s):return s,1
    def exit_to_lobby(self):self.calls.append('exit')
    def tap(self,c,s):self.calls.append(c)
    def change(self,c,s,expected):self.calls.append(c);return s
    def wait(self,p):return S(sequence=1)
    def acknowledge_results(self):self.calls.append('ack');self.exit_to_lobby()

def flow(values,outcomes,mw=None):
    n=Nav();v=iter(values);a=iter(outcomes);resets=[]
    b=S(read=lambda:next(v))
    f=StagesDailyFlow(n,b,S(ensure=lambda b:b),
        S(complete_requested_launch=lambda:AdsResult(next(a),S(sequence=2))),
        monster_wave=S(run=mw or (lambda:FlowResult(FlowStatus.COMPLETED))),
        reenter_same_character=lambda:resets.append('same'))
    return f,n,resets

def balance(sapphire=0,stamina=300):return StageBalances(stamina,sapphire,102,S(sequence=1))

def test_high_sapphires_runs_existing_mw_before_stage_and_rechecks():
    calls=[]
    f,n,_=flow([balance(102),balance(),balance(),balance(378)], [AdsOutcome.RETURNED],
        lambda:calls.append('mw') or FlowResult(FlowStatus.COMPLETED))
    assert f.run().status is FlowStatus.COMPLETED
    assert calls==['mw'] and n.calls.count(C.VIDEO)==1

def test_mw_did_not_free_capacity_never_enters_stage():
    f,n,_=flow([balance(417),balance(102)],[])
    assert f.run().status is FlowStatus.MANUAL_RESOLUTION
    assert n.calls==[]

def test_ad_return_without_sapphire_increase_fails_without_second_ad():
    f,n,_=flow([balance(),balance(),balance()], [AdsOutcome.RETURNED])
    assert f.run().status is FlowStatus.FAILED
    assert n.calls.count(C.VIDEO)==1 and n.calls[-1]=='exit'

def test_unavailable_has_four_launches_two_delays_one_identity_reset_and_controlled_terminal():
    f,n,resets=flow([balance(),balance(),balance()], [AdsOutcome.UNAVAILABLE]*4)
    assert f.run().status is FlowStatus.MANUAL_RESOLUTION
    assert n.calls.count(C.VIDEO)==4 and n.calls.count(C.NO_ADS_OK)==4
    assert resets==['same'] and n.calls[-1]=='exit'
    assert n.clock.now==10.

def test_inconclusive_ad_never_relaunches_or_resets():
    f,n,resets=flow([balance(),balance()], [AdsOutcome.RECOVERY_FAILED])
    assert f.run().status is FlowStatus.FAILED
    assert n.calls.count(C.VIDEO)==1 and not resets


def test_stage_tap_rejects_global_modal_covering_configuration():
    from bot.stages_runtime import StagesNavigation
    from bot.observations import Observation, ObservationBatch, ObservationSource
    from bot.state import ResolutionStatus
    clock=Clock();actions=[]
    s=S(timestamp=0.,sequence=1,state=S(status=ResolutionStatus.RESOLVED,base_context='screen.stages',
        overlays=('popup.stages_config','popup.equipment_inventory_full')),
        observations=ObservationBatch(sequence=1,timestamp=0.,observations=(
            Observation('stages.surface',1.,ObservationSource.LOCAL_CV,value='config'),)),geometry=None)
    n=StagesNavigation(None,S(execute=lambda *a,**kw:actions.append(a)),clock=clock)
    with pytest.raises(ValueError,match='upper layer'):n.tap(C.START,s)
    assert actions==[]

def test_stage_guard_entry_portal_handoff_never_replays_start():
    from bot.obstruction_recovery import PortalObstructionRecovery
    from bot.portal_notification import PortalProbeOutcome
    from bot.semantic_actions import DismissPortalNotification
    from bot.state import ResolutionStatus
    clock=Clock();actions=[];outcomes=iter([PortalProbeOutcome.CONFIRMED,PortalProbeOutcome.ABSENT])
    source=S(sequence=1,state=S(base_context='screen.stages',overlays=('popup.stages_config','popup.socket_inventory_full')))
    hidden=S(sequence=2,state=S(status=ResolutionStatus.UNKNOWN,base_context=None,overlays=()),frame=S(image=None),geometry=None)
    fresh=S(sequence=3,state=S(status=ResolutionStatus.RESOLVED,base_context='screen.socket',overlays=()),frame=S(image=None),geometry=None)
    recovery=PortalObstructionRecovery(S(observe=lambda:fresh),
        S(execute=lambda a,g:actions.append(a)),S(probe=lambda f:next(outcomes)),
        clock=clock,sleeper=clock.sleep)
    assert recovery.attempt(hidden,lambda s:s.state.base_context=='screen.socket',
        regions=((.165,.125,.36,.215),),stages_entry_source=source) is fresh
    assert actions==[DismissPortalNotification()]

def test_stage_portal_handoff_without_guard_does_not_authorize_input():
    from bot.obstruction_recovery import PortalObstructionRecovery
    from bot.state import ResolutionStatus
    source=S(sequence=1,state=S(base_context='screen.stages',overlays=('popup.stages_config',)))
    hidden=S(sequence=2,state=S(status=ResolutionStatus.UNKNOWN,base_context=None,overlays=()))
    recovery=PortalObstructionRecovery(S(observe=lambda:None),S(execute=lambda *a:pytest.fail('input')))
    assert recovery.attempt(hidden,lambda s:False,regions=((.165,.125,.36,.215),),stages_entry_source=source) is None


@pytest.mark.parametrize('normal', [False, True])
def test_back_stops_at_game_even_without_result(normal):
    clock = Clock()
    backs = []
    def observe():
        return AdObservation(clock.now, active=not backs, game_present=bool(backs),
                             back_ready=normal and not backs)
    ads = AdsManager(observe, lambda *a: pytest.fail('pixel input'),
                     lambda *a: pytest.fail('ticket'),
                     lambda s: backs.append(clock.now),
                     clock=clock, sleeper=clock.sleep, deadline=60)
    result = ads.complete_requested_launch()
    assert result.outcome is AdsOutcome.ABORTED_RECOVERED
    assert backs == [0. if normal else 60.]


def test_terminal_second_back_requires_fresh_ad_and_can_return_results():
    clock = Clock()
    backs = []
    def observe():
        return AdObservation(clock.now, active=len(backs)<2,
                             game_present=len(backs)==2, returned=len(backs)==2)
    ads = AdsManager(observe, lambda *a: pytest.fail('pixel input'),
                     lambda *a: None, lambda s: backs.append(clock.now),
                     clock=clock, sleeper=clock.sleep, deadline=60)
    result = ads.complete_requested_launch()
    assert result.outcome is AdsOutcome.RETURNED
    assert backs == [60., 61.]


def test_unknown_embedded_terminal_back_stops_at_known_game():
    c=Clock();backs=[]
    def observe():
        return AdObservation(c.now,ad_compatible=not backs,game_present=bool(backs))
    ads=AdsManager(observe,lambda *a:pytest.fail('content'),lambda *a:None,
        lambda s:backs.append(c.now),clock=c,sleeper=c.sleep)
    assert ads.complete_requested_launch().outcome is AdsOutcome.ABORTED_RECOVERED
    assert backs==[60.]


def test_unknown_embedded_does_not_authorize_second_back_after_unclear_return():
    c=Clock();backs=[]
    ads=AdsManager(lambda:AdObservation(c.now,ad_compatible=True),lambda *a:None,
        lambda *a:None,lambda s:backs.append(c.now),clock=c,sleeper=c.sleep)
    assert ads.complete_requested_launch().outcome is AdsOutcome.RECOVERY_FAILED
    assert backs==[60.]


def test_results_can_arrive_after_return_without_more_back():
    clock = Clock()
    backs = []
    def observe():
        return AdObservation(clock.now, active=not backs, back_ready=not backs,
                             game_present=bool(backs), returned=bool(backs) and clock.now>=1.)
    ads = AdsManager(observe, lambda *a: None, lambda *a: None,
                     lambda s: backs.append(clock.now), clock=clock, sleeper=clock.sleep)
    assert ads.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert backs == [0.]


def test_aborted_recovered_retries_once_then_controlled_without_consumption_claim():
    f,n,resets=flow([balance(),balance(),balance()], [AdsOutcome.ABORTED_RECOVERED]*2)
    result=f.run()
    assert result.status is FlowStatus.MANUAL_RESOLUTION
    assert result.events[0].kind=='stages_daily.ad_aborted_recovered'
    assert n.calls.count(C.VIDEO)==2 and n.calls.count('exit')==2 and not resets


def test_aborted_with_changed_resources_does_not_retry_or_call_success():
    f,n,resets=flow([balance(),balance(),balance(299,140)], [AdsOutcome.ABORTED_RECOVERED])
    assert f.run().status is FlowStatus.MANUAL_RESOLUTION
    assert n.calls.count(C.VIDEO)==1 and n.calls[-1]=='exit' and not resets


def test_android_activity_and_window_must_agree_before_back():
    import time
    from bot.ads_manager import AndroidAdsObserver
    snapshot=S(timestamp=time.monotonic(),frame=S(image=None))
    pkg='game.package'
    texts=iter([
        'topResumedActivity=ActivityRecord{a u0 '+pkg+'/com.google.android.gms.ads.AdActivity t1}',
        'mCurrentFocus=Window{a u0 '+pkg+'/com.hive.HiveUnityPlayerActivity}',
    ])
    observer=AndroidAdsObserver(S(observe=lambda:snapshot),S(shell=lambda *a:S(stdout=next(texts))),
        pkg,S(present=lambda *a:True),returned=lambda s:True,
        unavailable=lambda s:False,skip_ticket=lambda s:False,game_visible=lambda s:True)
    observation=observer()
    assert not observation.active and not observation.back_ready and not observation.game_present


def test_android_uses_complete_window_dump_for_samsung_focus():
    import time
    from bot.ads_manager import AndroidAdsObserver
    pkg='game.package';calls=[]
    snapshot=S(timestamp=time.monotonic(),frame=S(image=None))
    def shell(*args):
        calls.append(args)
        if args==('dumpsys','activity','activities'):
            return S(stdout='topResumedActivity=ActivityRecord{a u0 '+pkg+'/com.hive.HiveUnityPlayerActivity t1}')
        assert args==('dumpsys','window')
        return S(stdout='mCurrentFocus=Window{a u0 '+pkg+'/com.hive.HiveUnityPlayerActivity}')
    observer=AndroidAdsObserver(S(observe=lambda:snapshot),S(shell=shell),pkg,
        S(present=lambda *a:False),returned=lambda s:False,unavailable=lambda s:False,
        skip_ticket=lambda s:True,game_visible=lambda s:True)
    o=observer()
    assert o.game_present and o.skip_ticket and not o.active
    assert calls[-1]==('dumpsys','window')


def test_stamina_purchase_uses_fixed_offer_cv_without_coin_ocr():
    from bot.stamina_purchase import StaminaPurchase
    from bot.semantic_actions import ConfirmTradingTrade
    panels=[S(flags={'currency','stamina_row'},state=S(base_context='screen.trading')),
            S(flags={'currency','stamina_row'},state=S(base_context='screen.trading')),
            S(flags={'stamina_panel','kcoin','trade_one'}),
            S(flags={'currency','stamina_row'}),
            S(state=S(status=__import__('bot.state',fromlist=['ResolutionStatus']).ResolutionStatus.RESOLVED,
                      base_context='screen.lobby',overlays=()))]
    for s in panels:s.frame=S(image=s)
    queue=iter(panels);actions=[]
    def wait(predicate):
        s=next(queue);assert predicate(s);return s
    nav=S(wait=wait,act=lambda a,s:actions.append(a),events=None,clock=lambda:10.)
    after=balance(10,300)
    balances=S(read=lambda:after,
               text=lambda *a:pytest.fail('coin OCR'),
               pair=lambda s,roi:(1,20) if roi==(.592,.78,.66,.84) else pytest.fail('coin OCR'))
    detector=S(present=lambda frame,key:key in frame.flags)
    result=StaminaPurchase(nav,balances,detector).ensure(balance(10,250))
    assert result is after
    assert sum(isinstance(a,ConfirmTradingTrade) for a in actions)==1


def test_daily_exhaustion_is_distinct_from_temporal_unavailable():
    m,seen=manager([AdObservation(1,exhausted=True,game_present=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.EXHAUSTED
    assert seen==[]
    f,n,resets=flow([balance(),balance()],[AdsOutcome.EXHAUSTED])
    result=f.run()
    assert result.status is FlowStatus.COMPLETED
    assert result.events[0].kind=='stages_daily.ads_exhausted'
    assert n.calls==['enter',C.VIDEO,C.NO_ADS_OK,'exit'] and not resets


def test_no_ads_after_sdk_initialization_still_uses_temporal_recovery():
    m,seen=manager([AdObservation(1,active=True),
                   AdObservation(2,game_present=True,unavailable=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.UNAVAILABLE
    assert seen==[]


@pytest.mark.parametrize('label,expected',[
    ('No Ads Available',True),
    ('No Ads Available. Please try again later.',True),
    ('You have used up all daily video watch attempts for this mode.',False),
    ('Would you like to trade?',False),
])
def test_provisional_no_ads_reader_is_exact_and_only_on_acquired_alert(label,expected):
    from bot.stages_wiring import is_no_ads_alert
    from bot.observations import Observation,ObservationBatch,ObservationSource
    def snapshot(layer):
        return S(observations=ObservationBatch(sequence=1,timestamp=0.,observations=(
            Observation('stages.surface',1.,ObservationSource.LOCAL_CV,value=layer),)))
    calls=[]
    reader=S(text=lambda s,r:calls.append(r) or label)
    assert is_no_ads_alert(snapshot('alert'),reader) is expected
    assert calls==[(.350,.385,.650,.565)]
    assert not is_no_ads_alert(snapshot('auto'),S(text=lambda *a:pytest.fail('OCR outside alert')))


def test_android_no_ads_reader_is_never_called_on_ad_or_external_content():
    import time
    from bot.ads_manager import AndroidAdsObserver
    pkg='game.package';activity='com.google.android.gms.ads.AdActivity'
    texts=iter(['topResumedActivity=ActivityRecord{a u0 '+pkg+'/'+activity+' t1}',
                'mCurrentFocus=Window{a u0 '+pkg+'/'+activity+'}'])
    observer=AndroidAdsObserver(S(observe=lambda:S(timestamp=time.monotonic(),frame=S(image=None))),
        S(shell=lambda *a:S(stdout=next(texts))),pkg,S(present=lambda *a:False),
        returned=lambda s:pytest.fail('game reader on ad'),
        unavailable=lambda s:pytest.fail('alert OCR on ad'),skip_ticket=lambda s:False,
        game_visible=lambda s:True)
    assert observer().active


def test_main_activity_with_sdk_pixels_cannot_authorize_second_back():
    import time
    from bot.ads_manager import AndroidAdsObserver
    pkg='game.package';a='com.hive.HiveUnityPlayerActivity'
    texts=iter(['topResumedActivity=ActivityRecord{a u0 '+pkg+'/'+a+' t1}',
                'mCurrentFocus=Window{a u0 '+pkg+'/'+a+'}'])
    observer=AndroidAdsObserver(S(observe=lambda:S(timestamp=time.monotonic(),frame=S(image=None))),
        S(shell=lambda *a:S(stdout=next(texts))),pkg,
        S(present=lambda frame,key:key.startswith('ad_reward')),returned=lambda s:False,
        unavailable=lambda s:False,skip_ticket=lambda s:False,game_visible=lambda s:False)
    result=observer()
    assert result.ad_compatible and not result.active and not result.back_ready


def test_every_ad_input_forces_native_capture_even_with_new_stream_timestamp():
    import time
    from bot.ads_manager import AndroidAdsObserver
    pkg='game.package';a='com.hive.HiveUnityPlayerActivity';captures=[]
    s=S(timestamp=time.monotonic()+1,frame=S(image=None))
    texts=iter(['topResumedActivity=ActivityRecord{a u0 '+pkg+'/'+a+' t1}',
                'mCurrentFocus=Window{a u0 '+pkg+'/'+a+'}'])
    observer=AndroidAdsObserver(S(observe=lambda:s,source=S(refresh_native=lambda:captures.append('native'))),
        S(shell=lambda *a:S(stdout=next(texts))),pkg,S(present=lambda *a:False),
        returned=lambda s:False,unavailable=lambda s:False,skip_ticket=lambda s:False,
        game_visible=lambda s:True)
    observer.input_dispatched()
    assert observer().game_present
    assert captures==['native']


def test_stage_balance_wait_refreshes_static_lobby_instead_of_reusing_last_sequence():
    from bot.stages_runtime import StagesNavigation
    clock=Clock();clock.now=10.;captures=[]
    cached=S(sequence=10,timestamp=9.9)
    fresh=S(sequence=11,timestamp=10.)
    source=S(get_frame=lambda:cached,refresh_native=lambda:captures.append('native'))
    def wait_until(predicate,**kw):
        assert captures==['native'] and kw['after_sequence']==10
        assert predicate(fresh);return fresh
    nav=StagesNavigation(S(source=source,wait_until=wait_until),None,clock=clock)
    nav.cursor=10
    assert nav.wait(lambda s:True) is fresh


def test_multipart_progress_extends_deadline_without_authorizing_input():
    c=Clock();seen=[]
    def observe():
        if c.now<9:return AdObservation(c.now,active=True,progress=(c.now%3)/3)
        if not seen:return AdObservation(c.now,active=True,back_ready=True)
        return AdObservation(c.now,returned=True,game_present=True)
    m=AdsManager(observe,lambda *a:pytest.fail('visual tap'),lambda *a:None,
        lambda s:seen.append(c.now),clock=c,sleeper=c.sleep,deadline=6,
        progress_grace=2,max_duration=12)
    assert m.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert seen==[9.]


def test_static_progress_does_not_disable_terminal_recovery():
    c=Clock();seen=[]
    def observe():
        return AdObservation(c.now,game_present=True) if seen else AdObservation(c.now,active=True,progress=.5)
    m=AdsManager(observe,lambda *a:None,lambda *a:None,lambda s:seen.append(c.now),
        clock=c,sleeper=c.sleep,deadline=6,max_duration=12)
    assert m.complete_requested_launch().outcome is AdsOutcome.ABORTED_RECOVERED
    assert seen==[6.]


def test_continuous_progress_is_still_bounded():
    c=Clock();seen=[]
    m=AdsManager(lambda:AdObservation(c.now,active=True,progress=(c.now%3)/3),
        lambda *a:None,lambda *a:None,lambda s:seen.append(c.now),
        clock=c,sleeper=c.sleep,deadline=6,max_duration=10,progress_grace=2)
    assert m.complete_requested_launch().outcome is AdsOutcome.RECOVERY_FAILED
    assert seen==[10.,11.]


def test_reused_stages_binding_resets_relief_bound_for_each_invocation():
    from bot.stages_reliefs import StagesReliefs
    f,n,_=flow([balance(),balance(),balance(300),balance(),balance(),balance(300)],
               [AdsOutcome.RETURNED,AdsOutcome.RETURNED])
    relief=StagesReliefs(n,None,None)
    n.relief=relief
    calls=[]
    def enter():
        assert not relief.used
        relief.used.add('popup.socket_inventory_full')
        calls.append('relief');return S(sequence=1)
    n.enter_target=enter
    assert f.run().status is FlowStatus.COMPLETED
    assert f.run().status is FlowStatus.COMPLETED
    assert calls==['relief','relief']


def test_relief_duplicate_still_stops_within_one_invocation():
    from bot.stages_reliefs import StagesReliefs
    relief=StagesReliefs(None,None,None)
    relief.used.add('popup.socket_inventory_full')
    with pytest.raises(ValueError,match='bound exhausted'):
        relief(C.START,S(state=S(overlays=('popup.socket_inventory_full',))),{'start'})


def test_explicit_unavailable_arriving_during_return_grace_preserves_identity():
    m,seen=manager([AdObservation(1,active=True),AdObservation(2,game_present=True),
                   AdObservation(3,game_present=True,unavailable=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.UNAVAILABLE
    assert seen==[]


def test_daily_exhaustion_arriving_during_return_grace_stays_distinct():
    m,seen=manager([AdObservation(1,active=True),AdObservation(2,game_present=True),
                   AdObservation(3,game_present=True,exhausted=True)])
    assert m.complete_requested_launch().outcome is AdsOutcome.EXHAUSTED
    assert seen==[]


@pytest.mark.parametrize('returned_at',[1,2,3,4])
def test_no_ads_retry_can_recover_at_each_authorized_launch(returned_at):
    outcomes=[AdsOutcome.UNAVAILABLE]*(returned_at-1)+[AdsOutcome.RETURNED]
    balances=[balance(),balance()]+([balance()] if returned_at==4 else [])+[balance(300)]
    f,n,resets=flow(balances,outcomes)
    assert f.run().succeeded
    assert n.calls.count(C.VIDEO)==returned_at
    assert n.clock.now==min(returned_at-1,2)*5.
    assert resets==(['same'] if returned_at==4 else [])


def test_part_progress_disappears_after_deadline_without_authorizing_early_back():
    c=Clock(); seen=[]
    def observe():
        if seen:return AdObservation(c.now,returned=True,game_present=True)
        if c.now<5:return AdObservation(c.now,active=True,progress=c.now/5)
        return AdObservation(c.now,active=True,back_ready=c.now>=9)
    m=AdsManager(observe,lambda *a:pytest.fail('visual tap'),lambda *a:None,
        lambda s:seen.append(c.now),clock=c,sleeper=c.sleep,deadline=6,
        progress_grace=2,max_duration=12)
    assert m.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert seen==[9.]


def test_three_sdk_parts_each_return_from_store_with_bounded_fresh_back():
    c=Clock(); seen=[]
    def observe():
        if len(seen)>=4:return AdObservation(c.now,returned=True,game_present=True)
        if len(seen)==3:return AdObservation(c.now,active=True,back_ready=True)
        # Each distinct SDK part advances before opening its own external activity.
        if c.now>=len(seen)*3+2:return AdObservation(c.now,external=True)
        return AdObservation(c.now,active=True,progress=(c.now%3)/3)
    m=AdsManager(observe,lambda *a:pytest.fail('visual tap'),lambda *a:None,
        lambda s:seen.append(c.now),clock=c,sleeper=c.sleep,deadline=6,max_duration=20,
        progress_grace=2)
    assert m.complete_requested_launch().outcome is AdsOutcome.RETURNED
    assert len(seen)==4 and seen[-1]<20


def test_existing_battle_hub_runs_prepared_mw_before_any_lobby_request():
    from unittest.mock import Mock
    from test_world_boss_flow import snapshot
    from bot.catalog import SCREEN_BATTLE_MODE_SELECT
    trace=[]
    f,n,_=flow([balance(),balance(),balance(378)],[AdsOutcome.RETURNED])
    f.entry_snapshot=lambda:snapshot(1,base=SCREEN_BATTLE_MODE_SELECT)
    prepared=S(run=lambda:trace.append('hub_mw') or FlowResult(FlowStatus.COMPLETED))
    f.monster_wave=S(zone=object(),prepared=Mock(return_value=prepared),
        run=lambda:pytest.fail('Lobby MW entry requested from existing hub'))
    f.ensure_lobby=lambda:trace.append('lobby')
    assert f.run().status is FlowStatus.COMPLETED
    assert trace==['hub_mw','lobby']
    f.monster_wave.prepared.assert_called_once_with(f.monster_wave.zone)
    assert n.calls.count(C.VIDEO)==1


def test_hub_mw_failure_preserves_failure_without_lobby_or_ad_input():
    from test_world_boss_flow import snapshot
    from bot.catalog import SCREEN_BATTLE_MODE_SELECT
    f,n,_=flow([],[])
    failed=FlowResult(FlowStatus.FAILED,error='board_failure')
    f.entry_snapshot=lambda:snapshot(1,base=SCREEN_BATTLE_MODE_SELECT)
    f.monster_wave=S(zone=object(),prepared=lambda zone:S(run=lambda:failed))
    f.ensure_lobby=lambda:pytest.fail('must not navigate after failure')
    assert f.run() is failed
    assert n.calls==[]
