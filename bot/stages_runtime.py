"""Concrete Normal/Abyssal Rion/Stage8 navigation and Mao preparation."""
import time
import numpy as np
from bot.stages_actions import StageAction,StageControl as C
from bot.perception.stages import has,surface
from bot.catalog import SCREEN_LOBBY, POPUP_EQUIPMENT_INVENTORY_FULL, POPUP_SOCKET_INVENTORY_FULL
from bot.state import ResolutionStatus
from bot.runtime_observer import RuntimeWaitCancelled
from bot.event_log import record_best_effort

def lobby(s):return s.state.status is ResolutionStatus.RESOLVED and s.state.base_context==SCREEN_LOBBY and not s.state.overlays

def exposed(s):
    layer=surface(s)
    return s.state.status is not ResolutionStatus.AMBIGUOUS and all(
        overlay == 'popup.stages_'+layer for overlay in s.state.overlays) if layer else False

class StagesNavigation:
    def __init__(self,observer,actions,*,events=None,cancel_requested=lambda:False,clock=time.monotonic):
        self.observer,self.actions=observer,actions
        self.events,self.cancel_requested,self.clock=events,cancel_requested,clock
        self.cursor=0;self.dispatched_at=0.
        self.relief=None

    def wait(self,predicate,timeout=6.):
        if self.cancel_requested():raise RuntimeWaitCancelled('stages cancelled')
        source=getattr(self.observer,'source',None)
        if callable(getattr(source,'refresh_native',None)):
            latest=source.get_frame()
            if (latest.sequence<=self.cursor or latest.timestamp<=self.dispatched_at or
                    self.clock()-latest.timestamp>1.):
                source.refresh_native()
        s=self.observer.wait_until(lambda s:s.timestamp>self.dispatched_at and self.clock()-s.timestamp<2. and predicate(s),
            after_sequence=self.cursor,timeout=timeout,cancel_requested=self.cancel_requested)
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
        result=self.wait(lambda s:(exposed(s) and surface(s) in expected) or bool(blockers.intersection(s.state.overlays)),timeout)
        if blockers.intersection(result.state.overlays):
            if self.relief is None:raise ValueError('stages known relief not wired')
            return self.relief(control,result,expected)
        return result

    def enter_target(self):
        s=self.wait(lobby)
        s=self.change(C.OPEN,s,{'normal','elite'})
        record_best_effort(self.events,'stages.mode',mode=surface(s))
        if surface(s)=='elite':s=self.change(C.NORMAL,s,{'normal'})
        for count in range(20):
            if has(s,'claim_inactive'):break
            if not has(s,'claim_active'):raise ValueError('stages claim state unverified')
            h,w=s.frame.image.shape[:2]
            crop=s.frame.image[round(.895*h):round(.963*h),round(.230*w):round(.373*w)].copy()
            def claim_effect(after):
                if surface(after)!='normal':return False
                if has(after,'claim_inactive'):return True
                if not has(after,'claim_active'):return False
                other=after.frame.image[round(.895*h):round(.963*h),round(.230*w):round(.373*w)]
                return other.shape==crop.shape and np.abs(other.astype(float)-crop).mean()>2.
            self.tap(C.CLAIM,s);s=self.wait(claim_effect)
            record_best_effort(self.events,'stages.claim',number=count+1,active=has(s,'claim_active'))
        else:raise ValueError('stages claim bound')
        if not has(s,'abyssal'):
            s=self.change(C.WORLD_MAP,s,{'world_map'})
            s=self.change(C.ABYSSAL_TAIL,s,{'world_map','normal'})
            if surface(s)=='world_map':s=self.change(C.WORLD_MAP,s,{'normal'})
            s=self.wait(lambda s:surface(s)=='normal' and has(s,'abyssal'))
        record_best_effort(self.events,'stages.episode',episode='abyssal_rion')
        if not has(s,'stage8'):s=self.wait(lambda s:surface(s)=='normal' and has(s,'abyssal') and has(s,'stage8'))
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

    def exit_to_lobby(self):
        s=self.current()
        for _ in range(5):
            layer=surface(s)
            if lobby(s):return s
            closes={'results':C.RESULTS_OK,'auto':C.CLOSE_AUTO,'start':C.CLOSE_START,'config':C.CLOSE_CONFIG,
                    'daily_exhausted':C.NO_ADS_OK,'no_ads':C.NO_ADS_OK}
            if layer in closes:
                self.tap(closes[layer],s);s=self.wait(lambda a:surface(a)!=layer and surface(a) is not None)
            elif layer in {'normal','elite'}:
                self.tap(C.BACK,s);return self.wait(lobby,timeout=8.)
            else:raise ValueError('stages exit upper layer unverified')
        raise ValueError('stages exit bound')

    def acknowledge_results(self):
        s=self.wait(lambda s:surface(s)=='results',timeout=4.)
        self.tap(C.RESULTS_OK,s)
        s=self.wait(lambda s:surface(s)=='config')
        record_best_effort(self.events,'stages.results_acknowledged')
        return self.exit_to_lobby()

class MaoSupport:
    """Tickets complete is READY; activation is a separate one-shot action."""
    def __init__(self,navigation):self.nav=navigation
    def ensure(self,s):
        n=self.nav
        if surface(s)!='config':raise ValueError('mao requires exposed config')
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
