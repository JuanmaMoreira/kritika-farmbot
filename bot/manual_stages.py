"""One manual x4 entry; equipment evidence belongs to Shared Meteorites."""
from dataclasses import dataclass
from enum import Enum
from bot.flow_contracts import FlowResult
import time
from bot.flow_contracts import FlowEvent, FlowStatus
from bot.stages_actions import StageAction, StageControl as C
from bot.stages_runtime import lobby, exposed, MaoSupport
from bot.perception.stages import has, surface
from bot.manual_stages_reader import flag, buff_stock, auto_window_state
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.action_executor import FrameGeometry
from bot.event_log import record_best_effort

STRONG_CHARACTERS = frozenset({'burst_breaker', 'berserker', 'demon_blade', 'kaiserin'})
MIN_STAMINA = 60

class ManualStageTarget(str, Enum):
    ABYSSAL_RION_09 = 'abyssal_rion_09'
    CHAOS_06 = 'chaos_06'

def select_manual_stage(character_id, meteorites=None):
    verified = (meteorites is not None and meteorites.full_set_equipped_verified(character_id))
    return (ManualStageTarget.ABYSSAL_RION_09 if character_id in STRONG_CHARACTERS or verified
        else ManualStageTarget.CHAOS_06)

class ManualStageOutcome(str, Enum):
    REWARDED = 'rewarded'
    NO_PROGRESS = 'no_progress'
    STAMINA_INSUFFICIENT = 'stamina_insufficient'
    SAPPHIRE_CAPACITY_FULL = 'sapphire_capacity_full'
    AMBIGUOUS = 'ambiguous'
    CANCELLED = 'cancelled'
    FAILED = 'failed'
    DEFEATED = 'defeated'

@dataclass(frozen=True)
class ManualStagesResult(FlowResult):
    outcome: ManualStageOutcome = ManualStageOutcome.AMBIGUOUS
    target: ManualStageTarget | None = None
    stamina_before: int | None = None
    stamina_after: int | None = None
    sapphires_before: int | None = None
    sapphires_after: int | None = None
    physical_operation_may_be_active: bool = False
    entry_id: int | None = None
    stamina_consumed: int | None = 0  # None: Start dispatched, effect unresolved.
    entry_reconciliation_pending: bool = False

def stamina_eligible(stamina):
    return type(stamina) is int and stamina >= MIN_STAMINA

class ManualStagesOperation:
    def __init__(self, navigation, balances, visuals, *, character=lambda:None,
                 meteorites=lambda:None, evidence_sink=lambda name,frame:None,
                 clock=time.monotonic, sleeper=time.sleep, stamina_purchase=None):
        self.nav,self.balances,self.visuals=navigation,balances,visuals
        self.character,self.meteorites=character,meteorites
        self.evidence_sink,self.clock,self.sleeper=evidence_sink,clock,sleeper
        self._unsafe_to_restart=False
        self.stamina_purchase=stamina_purchase
        self._entry=None;self._entry_serial=0
        self.target=None
        # Reuse transversal relief policy/execution, with caller-owned revalidation.
        self.nav.manual_restore_config=self.restore_config
        self.nav.resume_after_relief=self.resume_after_relief
        self.nav.target_entry=self.enter_target

    def _emit(self,kind,**fields):
        record_best_effort(self.nav.events,'manual_stages.'+kind,**fields)

    def _cancel(self):
        if self.nav.cancel_requested():raise RuntimeWaitCancelled('Manual Stages cancelled')

    def _pause(self,seconds):
        deadline=self.clock()+seconds
        while self.clock()<deadline:
            self._cancel();self.sleeper(min(.2,deadline-self.clock()))

    def configure_x4(self,s):
        if not exposed(s) or surface(s)!='normal':raise ValueError('x4 requires exposed BASE')
        state=flag(s,'x4')
        if state is None:raise ValueError('x4 unknown; no input')
        if state is False:
            # Acquired two-tap gesture, one authorization and one final effect.
            self.nav.tap(C.X4,s);self._pause(.10)
            self._cancel()
            self.nav.actions.execute(StageAction(C.X4),s.geometry,events=self.nav.events,
                source_sequence=s.sequence)
            self.nav.dispatched_at=self.clock()
            s=self.nav.wait(lambda s:exposed(s) and surface(s)=='normal' and flag(s,'x4') is True)
        self._emit('x4',point='base',selected=True,source_sequence=s.sequence)
        return s

    def open_target(self,s):
        s=self.configure_x4(s)
        control=C.STAGE9 if self.target is ManualStageTarget.ABYSSAL_RION_09 else C.STAGE6
        marker='stage9' if control is C.STAGE9 else 'stage6'
        if not has(s,marker):s=self.nav.wait(lambda s:exposed(s) and surface(s)=='normal' and has(s,marker))
        return self.nav.change(control,s,{'config'})

    def enter_target(self):
        episode='abyssal' if self.target is ManualStageTarget.ABYSSAL_RION_09 else 'chaos'
        return self.open_target(self.nav.enter_episode(episode))

    def prepare_config(self,s):
        n=self.nav
        if not exposed(s) or self.visuals.config_target(s.frame.image)!=self.target.value:
            raise ValueError('manual target MODAL unverified')
        s=MaoSupport(n).ensure(s)
        name='penance' if self.target is ManualStageTarget.ABYSSAL_RION_09 else 'hell'
        value=flag(s,name)
        if value is None:
            # Target chrome can resolve during the opening animation before
            # difficulty controls stabilize. Observe only; UNKNOWN is no input.
            s=n.wait(lambda s:exposed(s) and surface(s)=='config' and flag(s,name) is not None)
            value=flag(s,name)
        if value is False:
            n.tap(C.PENANCE if name=='penance' else C.HELL,s)
            s=n.wait(lambda s:exposed(s) and surface(s)=='config' and flag(s,name) is True)
        for index in range(1,5):
            state=flag(s,f'buff{index}')
            if state is None:raise ValueError('buff state unknown; no input')
            stock=(buff_stock(self.balances.engine,s.frame.image,index,n.cancel_requested)
                if index==4 else None)
            # x4 reserves one ticket on selection; no extra Start debit was
            # acquired (buff4 97 -> selected96 -> post-entry96). An existing
            # ON selection is already paid, even with zero remaining tickets.
            desired=(stock is not None and (state or stock>=1)) if index==4 else True
            if state != desired:
                # OCR may exhaust input freshness; reacquire state + count before
                # a purchase-sensitive OFF->ON action, never use the old image.
                s=n.wait(lambda s:exposed(s) and surface(s)=='config')
                if flag(s,f'buff{index}') is not state:raise ValueError('buff state changed')
                if desired and index==4 and buff_stock(self.balances.engine,s.frame.image,index,n.cancel_requested)!=stock:
                    raise ValueError('buff stock changed')
                n.tap(getattr(C,f'BUFF{index}'),s)
                s=n.wait(lambda s:exposed(s) and surface(s)=='config' and flag(s,f'buff{index}') is desired)
            self._emit('buff',index=index,selected=desired,stock=stock,karats_purchase=False)
        # Fresh complete readiness before the nonconsumptive first Start.
        s=n.wait(lambda s:exposed(s) and surface(s)=='config')
        if (self.visuals.config_target(s.frame.image)!=self.target.value or not has(s,'support_active')
                or flag(s,name) is not True
                or any(flag(s,f'buff{i}') is not True for i in (1,2,3))
                or flag(s,'buff4') is None):raise ValueError('manual readiness changed')
        self.evidence_sink('prepared',s.frame)
        return s

    def restore_config(self,s):
        n=self.nav
        if lobby(s):return self.enter_target()
        if surface(s)=='start':s=n.change(C.CLOSE_START,s,{'config'})
        if surface(s)=='config':s=n.change(C.CLOSE_CONFIG,s,{'normal'})
        episode='abyssal' if self.target is ManualStageTarget.ABYSSAL_RION_09 else 'chaos'
        if surface(s)!='normal' or not has(s,episode):
            raise ValueError('relief episode return unverified')
        return self.open_target(s)

    def resume_after_relief(self,control,s,expected):
        # A fresh inventory blocker proved rejection. Only this branch permits
        # another Start, after caller return, quantity and config revalidation.
        s=self.prepare_config(s)
        s=self.nav.change(C.START,s,{'start'})
        if control is C.START:return s
        if control is not C.STRIKER_START:raise ValueError('manual relief control unknown')
        return self.nav.change(C.STRIKER_START,s,expected)

    def _fresh_frame(self,after=0,not_before=0.,timeout=5.):
        source=self.nav.observer.source;deadline=self.clock()+timeout
        while self.clock()<deadline:
            self._cancel();f=source.get_frame()
            if f.sequence>after and f.timestamp>not_before and 0<=self.clock()-f.timestamp<=1.:
                return f
            self._pause(.10)
        raise ValueError('manual fresh frame unavailable')

    def _input(self,control,frame,guard):
        self._cancel()
        if not 0<=self.clock()-frame.timestamp<2. or not guard(frame.image):
            raise ValueError('manual input guard invalid')
        self.nav.actions.execute(StageAction(control),FrameGeometry.from_frame(frame.image),
            events=self.nav.events,source_sequence=frame.sequence)
        self.nav.cursor=frame.sequence;self.nav.dispatched_at=self.clock()

    def auto_state(self,after=0):
        samples=[];f=None;started=self.clock()
        while self.clock()-started<4.:
            f=self._fresh_frame(after);after=f.sequence
            if self.visuals.terminal(f.image):return None,f
            samples.append((f.timestamp,self.visuals.auto_glow(f.image)))
            state=auto_window_state(samples)
            if state is not None:
                self._emit('auto_window',state=state,samples=len(samples),peak=max(v for _,v in samples))
                self.evidence_sink('auto_on' if state else 'auto_off',f)
                return state,f
            self._pause(.10)
        return None,f

    def ensure_auto(self,after=0):
        state,f=self.auto_state(after)
        if state is False:
            self._input(C.BATTLE_AUTO,f,self.visuals.battle)
            state,f=self.auto_state(f.sequence)
        if state is not True:raise ValueError('Auto ON unverified; no normal battle wait')
        self._emit('auto_verified',selected=True,source_sequence=f.sequence)
        return f

    def wait_terminal(self,after):
        self._pause(30.)
        deadline=self.clock()+120.;polls=0;started=self.clock()
        while self.clock()<deadline:
            f=self._fresh_frame(after);after=f.sequence;polls+=1
            terminal=self.visuals.terminal(f.image)
            if terminal in {'clear','death','death_guide'}:
                self.evidence_sink(terminal,f)
                self._emit('terminal',terminal=terminal,polls=polls,elapsed=self.clock()-started+30.,ocr_calls=0)
                return terminal,f
            self._pause(1.5)
        raise ValueError('manual terminal unverified at bound')

    def return_home(self,terminal,f):
        if terminal in {'death','death_guide'}:
            if terminal=='death':
                self._input(C.DEATH_ABANDON,f,lambda image:self.visuals.terminal(image)=='death')
                deadline=self.clock()+8.
                while self.clock()<deadline:
                    f=self._fresh_frame(f.sequence,self.nav.dispatched_at)
                    if self.visuals.terminal(f.image)=='death_guide':break
                    self._pause(.2)
                else:raise ValueError('death guide unverified')
            self.evidence_sink('death_guide',f)
            self._input(C.DEATH_GUIDE_CLOSE,f,lambda image:self.visuals.terminal(image)=='death_guide')
        else:
            self._input(C.CLEAR_HOME,f,lambda image:self.visuals.terminal(image)=='clear')
        try:
            s=self.nav.wait(lobby,timeout=12.)
        except RuntimeWaitTimeout:
            if terminal!='clear':raise
            # Home is nonconsumptive. A fresh, still exposed Clear Time overlay
            # proves the first exit had no effect; uncertainty never retries it.
            fresh=self._fresh_frame(f.sequence,self.nav.dispatched_at)
            if self.visuals.terminal(fresh.image)!='clear':raise
            self._emit('home_retry',reason='fresh_clear_no_effect',source_sequence=fresh.sequence)
            self._input(C.CLEAR_HOME,fresh,lambda image:self.visuals.terminal(image)=='clear')
            s=self.nav.wait(lobby,timeout=12.)
        self.evidence_sink('lobby',s.frame)
        return s

    def prepare_stamina(self,required,*,still_manual=lambda:True):
        """Normal episode Claim before demand calculation; purchase owns Trade."""
        if self._unsafe_to_restart:raise ValueError('previous entry unresolved')
        if self.stamina_purchase is None:raise ValueError('stamina purchase owner unavailable')
        if self.stamina_purchase.pending is not None:
            return self.stamina_purchase.supply(None,required)
        before=self.balances.read()
        from bot.stamina_purchase import StaminaSupplyResult
        if before.sapphires>=before.sapphire_limit:
            return StaminaSupplyResult(before,required,outcome='sapphire_capacity_full')
        target=select_manual_stage(self.character(),self.meteorites())
        s=self.nav.enter_episode('abyssal' if target is ManualStageTarget.ABYSSAL_RION_09 else 'chaos')
        self.nav.exit_to_lobby(s)
        eligible=still_manual()
        # Resource routing can perform OCR. Reacquire the balance/snapshot that
        # will authorize opening Trading, after that caller-owned work.
        before=self.balances.read()
        self._emit('supply_claim_balance',stamina=before.stamina,required=required)
        if not eligible:
            return StaminaSupplyResult(before,required,outcome='routing_changed')
        if before.sapphires>=before.sapphire_limit:
            return StaminaSupplyResult(before,required,outcome='sapphire_capacity_full')
        return self.stamina_purchase.supply(before,required)

    def resume(self):
        return self.run(resume=True)

    def run(self,*,resume=False):
        before=after=None;active=False;terminal=None;consumed=0;entry_id=None
        closed=False
        if not resume:self.target=None
        def finish(outcome,status=FlowStatus.COMPLETED,error=None,snapshot=None):
            pending=entry_id is not None and status is not FlowStatus.COMPLETED
            self._unsafe_to_restart |= active or pending
            if entry_id is not None:
                self._entry=(before,self.target,entry_id,consumed,terminal if closed else None)
            return ManualStagesResult(status,(FlowEvent('manual_stages.'+outcome.value,
                detail=error,fields={'physical_operation_may_be_active':active,
                    'entry_id':entry_id,'stamina_consumed':consumed}),),
                error=error,final_snapshot=snapshot,outcome=outcome,target=self.target,
                stamina_before=before.stamina if before else None,
                stamina_after=after.stamina if after else None,
                sapphires_before=before.sapphires if before else None,
                sapphires_after=after.sapphires if after else None,
                physical_operation_may_be_active=active,entry_id=entry_id,stamina_consumed=consumed,
                entry_reconciliation_pending=pending)
        if self._unsafe_to_restart and not resume:
            active=True
            return finish(ManualStageOutcome.AMBIGUOUS,FlowStatus.MANUAL_RESOLUTION,'previous_entry_unresolved')
        if resume and (not self._entry or not self._unsafe_to_restart):
            return finish(ManualStageOutcome.AMBIGUOUS,FlowStatus.MANUAL_RESOLUTION,'no_entry_to_reconcile')
        try:
            if resume:
                before,self.target,entry_id,consumed,terminal=self._entry
                closed=terminal is not None;active=not closed
                # Observe acquired entry effects only. Never another Start.
                s=self.nav.wait(lobby if closed else
                    lambda s:surface(s) in {'battle','death','death_guide','clear'},timeout=12.)
            else:
                if self.nav.relief is not None:self.nav.relief.reset()
                before=self.balances.read()
                if not stamina_eligible(before.stamina):
                    return finish(ManualStageOutcome.STAMINA_INSUFFICIENT,snapshot=before.snapshot)
                if before.sapphires >= before.sapphire_limit:
                    return finish(ManualStageOutcome.SAPPHIRE_CAPACITY_FULL,snapshot=before.snapshot)
                cid=self.character();scope=self.meteorites()
                self.target=select_manual_stage(cid,scope)
                self._emit('target',character_id=cid,target=self.target.value,
                    meteorites_verified=bool(scope and scope.full_set_equipped_verified(cid)))
                s=self.prepare_config(self.enter_target())
                s=self.nav.change(C.START,s,{'start'})
                self._emit('first_start',effect='select_striker')
                active=True;consumed=None  # preserve dispatch uncertainty
                self._entry_serial+=1;entry_id=self._entry_serial
                s=self.nav.change(C.STRIKER_START,s,{'battle','death','death_guide','clear'},timeout=12.)
                self._emit('second_start',effect=surface(s))
            if not closed:
                consumed=MIN_STAMINA  # Physical entry effect, independent of Claim/regen.
                if surface(s) in {'death','death_guide','clear'}:terminal,f=surface(s),s.frame
                else:
                    f=self.ensure_auto(s.sequence)
                    terminal,f=self.wait_terminal(f.sequence)
                s=self.return_home(terminal,f);active=False;closed=True
            self._unsafe_to_restart=False
            after=self.balances.read()
            if (after.snapshot.sequence<=before.snapshot.sequence or
                    after.snapshot.timestamp<=before.snapshot.timestamp):
                raise ValueError('post-stage balances not fresh')
            self._emit('resources',stamina_before=before.stamina,stamina_after=after.stamina,
                sapphires_before=before.sapphires,sapphires_after=after.sapphires)
            if terminal in {'death','death_guide'}:return finish(ManualStageOutcome.DEFEATED,snapshot=after.snapshot)
            return finish(ManualStageOutcome.REWARDED if after.sapphires>before.sapphires
                else ManualStageOutcome.NO_PROGRESS,snapshot=after.snapshot)
        except RuntimeWaitCancelled:
            return finish(ManualStageOutcome.CANCELLED,FlowStatus.CANCELLED)
        except (ValueError,RuntimeWaitTimeout) as error:
            return finish(ManualStageOutcome.AMBIGUOUS,FlowStatus.MANUAL_RESOLUTION,str(error))
        except Exception as error:
            return finish(ManualStageOutcome.FAILED,FlowStatus.FAILED,str(error) or type(error).__name__)
