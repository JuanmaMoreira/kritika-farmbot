"""Shared Stages navigation and Mao preparation; callers own target and entry."""
import time
from bot.stages_actions import StageAction,StageControl as C
from bot.perception.stages import has,surface
from bot.catalog import SCREEN_LOBBY, POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL
from bot.state import ResolutionStatus
from bot.runtime_observer import RuntimeWaitCancelled,RuntimeWaitTimeout
from bot.event_log import record_best_effort
from bot.tap_through_animation import TapThroughAnimation,TapThroughPolicy,TapThroughOutcome
from types import SimpleNamespace

def lobby(s):return s.state.status is ResolutionStatus.RESOLVED and s.state.base_context==SCREEN_LOBBY and not s.state.overlays

def exposed(s):
    layer=surface(s)
    upper='overlay.manual_stage_clear' if layer=='clear' else 'popup.stages_'+str(layer)
    return s.state.status is not ResolutionStatus.AMBIGUOUS and all(
        overlay == upper for overlay in s.state.overlays) if layer else False

class StagesNavigation:
    def __init__(self,observer,actions,*,events=None,cancel_requested=lambda:False,clock=time.monotonic,sleeper=time.sleep):
        self.observer,self.actions=observer,actions
        self.events,self.cancel_requested,self.clock=events,cancel_requested,clock
        self.sleeper=sleeper;self.claim_observer=None
        self.results_observer=None
        self.cursor=0;self.dispatched_at=0.
        self.relief=None

    def wait(self,predicate,timeout=6.,*,observer=None):
        observer=observer or self.observer
        if self.cancel_requested():raise RuntimeWaitCancelled('stages cancelled')
        source=getattr(observer,'source',None)
        if callable(getattr(source,'refresh_native',None)):
            latest=source.get_frame()
            recent=lambda frame: (frame.sequence>self.cursor and frame.timestamp>self.dispatched_at
                and 0.<=self.clock()-frame.timestamp<=1.)
            if not recent(latest):
                # Allow the current stream to deliver the dispatched effect
                # before paying for another native acquisition. Static/stalled
                # streams still take the same real-capture fallback.
                deadline=self.clock()+.15
                for _ in range(8):
                    if self.cancel_requested():raise RuntimeWaitCancelled('stages cancelled')
                    remaining=deadline-self.clock()
                    if remaining<=0.:break
                    self.sleeper(min(.02,remaining))
                    latest=source.get_frame()
                    if recent(latest):break
            if not recent(latest):
                source.refresh_native()
        fresh_match=lambda s:s.timestamp>self.dispatched_at and 0.<=self.clock()-s.timestamp<2. and predicate(s)
        try:
            s=observer.wait_until(fresh_match,after_sequence=self.cursor,timeout=timeout,
                cancel_requested=self.cancel_requested)
        except RuntimeWaitTimeout as error:
            last=error.last_snapshot
            # A post-ad stream can show the requested surface with capture age
            # already outside the input guard. It authorizes observation only.
            # One real native acquisition re-verifies; never resend the action.
            if (last is None or self.clock()-last.timestamp<2. or
                    not callable(getattr(source,'refresh_native',None)) or not predicate(last)):
                raise
            if self.cancel_requested():raise RuntimeWaitCancelled('stages cancelled')
            record_best_effort(self.events,'stages.wait.native_reacquire',
                source_sequence=last.sequence,frame_age=self.clock()-last.timestamp,
                reason='stale_matching_surface',input_retries=0)
            source.refresh_native()
            s=observer.wait_until(fresh_match,after_sequence=last.sequence,timeout=2.,
                cancel_requested=self.cancel_requested)
        self.cursor=s.sequence
        return s

    def current(self):return self.wait(lambda s:lobby(s) or exposed(s))

    def act(self,action,snapshot):
        if self.cancel_requested():raise RuntimeWaitCancelled('stages cancelled')
        if self.clock()-snapshot.timestamp>2.:raise ValueError('stages action stale')
        self.actions.execute(action,snapshot.geometry,events=self.events,source_sequence=snapshot.sequence)
        self.cursor=snapshot.sequence;self.dispatched_at=self.clock()

    def tap(self,control,snapshot):
        if not (lobby(snapshot) or exposed(snapshot)):
            raise ValueError('stages control covered by upper layer')
        self.act(StageAction(control),snapshot)

    def change(self,control,snapshot,expected,timeout=6.):
        self.tap(control,snapshot)
        blockers={POPUP_EQUIPMENT_INVENTORY_FULL,POPUP_SOCKET_INVENTORY_FULL}
        # Only a verified Stages source bounds this modal family. Lobby entry
        # and foreign/unknown sources retain the full observer.
        panel=self.results_observer if snapshot.state.base_context=='screen.stages' else None
        predicate=lambda s:(exposed(s) and surface(s) in expected) or bool(blockers.intersection(s.state.overlays))
        result=self.wait(predicate,timeout,observer=panel) if panel is not None else self.wait(predicate,timeout)
        if blockers.intersection(result.state.overlays):
            if self.relief is None:raise ValueError('stages known relief not wired')
            return self.relief(control,result,expected)
        return result

    def stamina_increments(self,count,snapshot):
        """Bounded nonconsuming quantity setup; one final panel verification owns confirm."""
        if not 0<=count<=19:raise ValueError('stamina selector tap bound')
        if self.clock()-snapshot.timestamp>2.:raise ValueError('stamina selector stale')
        for _ in range(count):
            if self.cancel_requested():raise RuntimeWaitCancelled('stamina selection cancelled')
            self.actions.execute(StageAction(C.STAMINA_INCREMENT),snapshot.geometry,
                events=self.events,source_sequence=snapshot.sequence)
            self.cursor=snapshot.sequence;self.dispatched_at=self.clock()
            self.sleeper(.10)

    def claim_rewards(self,s):
        if has(s,'claim_inactive') and exposed(s) and surface(s)=='normal':return s
        cycles=0;started=self.clock();current=s
        def observe(predicate,**kwargs):
            nonlocal cycles,current
            cycles+=1
            current=self.wait(predicate,timeout=min(3.,kwargs['timeout']),observer=self.claim_observer)
            return current
        def tap(action,geometry):self.tap(C.CLAIM,current)
        valid=lambda item: item.state.status is ResolutionStatus.RESOLVED and item.state.base_context=='screen.stages' and exposed(item) and surface(item)=='normal' and self.clock()-item.timestamp<2.
        result=TapThroughAnimation(SimpleNamespace(wait_until=observe),SimpleNamespace(execute=tap),
            events=self.events,clock=self.clock,sleeper=self.sleeper).run(s,
            action=StageAction(C.CLAIM),expected=lambda item:valid(item) and has(item,'claim_inactive'),
            tappable=lambda item:valid(item) and has(item,'claim_active'),transient=lambda item:False,
            cancel_requested=self.cancel_requested,
            policy=TapThroughPolicy(tap_interval=.15,timeout=12.,max_taps=20))
        record_best_effort(self.events,'stages.claim_loop',taps=result.tap_count,
            perception_cycles=cycles,elapsed=self.clock()-started,outcome=result.outcome.value)
        if result.outcome is TapThroughOutcome.CANCELLED:raise RuntimeWaitCancelled('stages claim cancelled')
        if not result.succeeded:raise ValueError('stages claim '+result.outcome.value)
        return result.final_snapshot

    def enter_episode(self, episode='abyssal'):
        if episode not in {'abyssal','chaos'}:raise ValueError('unknown stages episode')
        s=self.wait(lobby)
        try:
            s=self.change(C.OPEN,s,{'normal','elite'})
        except RuntimeWaitTimeout as error:
            # OPEN is navigation only. A fresh, exposed Lobby proves that
            # this entry had no effect; unknown/covered/old pixels do not.
            last=error.last_snapshot
            if (last is None or not lobby(last) or last.sequence<=self.cursor
                    or last.timestamp<=self.dispatched_at
                    or not 0.<=self.clock()-last.timestamp<2.):
                raise
            s=self.wait(lobby)
            record_best_effort(self.events,'stages.entry.retry',reason='fresh_lobby_no_effect',
                source_sequence=s.sequence,input_retries=1)
            s=self.change(C.OPEN,s,{'normal','elite'})
        record_best_effort(self.events,'stages.mode',mode=surface(s))
        if surface(s)=='elite':s=self.change(C.NORMAL,s,{'normal'})
        # Verify the current episode on a fresh, exposed Normal frame before
        # deciding whether World Map is needed, including Elite -> Normal.
        s=self.wait(lambda s:exposed(s) and surface(s)=='normal')
        confirmed=has(s,episode)
        measured=s.observations.best('stages.'+episode+'_score')
        record_best_effort(self.events,'stages.episode_check',
            episode=('abyssal_rion' if episode=='abyssal' else episode) if confirmed else 'unconfirmed',world_map_required=not confirmed,
            score=measured.value if measured is not None else None,threshold=.94,
            source_sequence=s.sequence,frame_shape=s.frame.image.shape[:2],
            frame_age=self.clock()-s.timestamp,overlays=s.state.overlays)
        if not confirmed:
            s=self.change(C.WORLD_MAP,s,{'world_map'})
            s=self.change(C.ABYSSAL_TAIL if episode=='abyssal' else C.CHAOS,s,{'world_map','normal'})
            if surface(s)=='world_map':s=self.change(C.WORLD_MAP,s,{'normal'})
            s=self.wait(lambda s:surface(s)=='normal' and has(s,episode))
        record_best_effort(self.events,'stages.episode',episode='abyssal_rion' if episode=='abyssal' else episode)
        # Claims preserve the verified episode within this entry. Their toast
        # does not change context; no title recheck after generating it.
        s=self.claim_rewards(s)
        return s

    def enter_target(self):
        s=self.enter_episode()
        s=self.wait(lambda s:exposed(s) and surface(s)=='normal' and has(s,'stage8'))
        return self.change(C.STAGE8,s,{'config'})

    def prepare_ad(self,s):
        s=MaoSupport(self).ensure(s)
        if not has(s,'penance'):
            self.tap(C.PENANCE,s);s=self.wait(lambda s:surface(s)=='config' and has(s,'penance') and has(s,'support_active'))
        # Deliberately no x4 inputs. This Start only opens Select Striker.
        s=self.change(C.START,s,{'start'})
        s=self.change(C.AUTO,s,{'auto'})
        if not has(s,'max300'):
            self.tap(C.MAX300,s);s=self.wait(lambda s:surface(s)=='auto' and has(s,'max300'))
        if not has(s,'max300'):raise ValueError('stages max300 unverified')
        video=2 if has(s,'video2') else 1 if has(s,'video1') else 0 if has(s,'video0') else None
        record_best_effort(self.events,'stages.ad_selection',max_stamina=300,video_count=video)
        if video is None:raise ValueError('stages video count unverified')
        return s,video

    def exit_to_lobby(self,snapshot=None,*,observer=None):
        s=snapshot if snapshot is not None else self.current()
        for _ in range(5):
            layer=surface(s)
            if lobby(s):return s
            closes={'results':C.RESULTS_OK,'auto':C.CLOSE_AUTO,'start':C.CLOSE_START,'config':C.CLOSE_CONFIG,
                    'daily_exhausted':C.NO_ADS_OK,'no_ads':C.NO_ADS_OK}
            if layer in closes:
                self.tap(closes[layer],s);s=self.wait(lambda a:exposed(a) and surface(a)!=layer,
                    observer=observer)
            elif layer in {'normal','elite'}:
                self.tap(C.BACK,s);return self.wait(lobby,timeout=8.)
            else:raise ValueError('stages exit upper layer unverified')
        raise ValueError('stages exit bound')

    def acknowledge_results(self):
        s=self.wait(lambda s:exposed(s) and surface(s)=='results',timeout=4.,observer=self.results_observer)
        self.tap(C.RESULTS_OK,s)
        s=self.wait(lambda s:exposed(s) and surface(s)=='config',observer=self.results_observer)
        record_best_effort(self.events,'stages.results_acknowledged')
        return self.exit_to_lobby(s,observer=self.results_observer)

class MaoSupport:
    """Tickets complete is READY; activation is a separate one-shot action."""
    def __init__(self,navigation):self.nav=navigation
    def ensure(self,s):
        n=self.nav
        if surface(s)!='config':raise ValueError('mao requires exposed config')
        if not any(has(s,name) for name in ('support_active','support_ready','support_needs')):
            # Support Activated has a transient sparkle after relief/reentry.
            # Observe its existing state; a miss authorizes no purchase/tap.
            record_best_effort(n.events,'stages.mao_passive_recovery',source_sequence=s.sequence)
            s=n.wait(lambda a:exposed(a) and surface(a)=='config' and any(
                has(a,name) for name in ('support_active','support_ready','support_needs')))
        if has(s,'support_active'):
            record_best_effort(n.events,'stages.mao',state='active');return s
        if has(s,'support_needs'):
            record_best_effort(n.events,'stages.mao',state='needs_tickets')
            s=n.change(C.SUPPORT,s,{'support_purchase'})
            n.tap(C.FILL_SUPPORT,s)
            s=n.wait(lambda s:surface(s)=='support_purchase' and has(s,'support_full'))
            s=n.change(C.CLOSE_SUPPORT,s,{'config'})
        if not has(s,'support_ready'):raise ValueError('mao ready unverified; no repeated purchase')
        record_best_effort(n.events,'stages.mao',state='ready')
        n.tap(C.SUPPORT,s)
        s=n.wait(lambda s:surface(s)=='config' and has(s,'support_active'))
        record_best_effort(n.events,'stages.mao',state='active')
        return s
