"""Bounded Arena operation. Navigation, input lineage and evidence stay here."""
from dataclasses import dataclass, field, replace
import math
import time
from uuid import uuid4

from bot.arena_actions import ArenaAction, ArenaControl as C
from bot.arena_config import ArenaMode
from bot.arena_semantics import (ArenaBatchExecution, ArenaBatchResult, ArenaDifficulty, SCREEN_ARENA,
    ArenaSingleExecution, ArenaSingleResult, ArenaSingleOutcome)
import hashlib
from bot.catalog import SCREEN_SOCKET, POPUP_SOCKET_INVENTORY_FULL
from bot.component_contracts import ComponentRequirement
from bot.controlled_wait import ControlledWait, ControlledWaitOutcome
from bot.event_log import record_best_effort
from bot.flow_contracts import FlowContract, FlowResult, FlowScope, FlowStatus
from bot.action_executor import FrameGeometry
from bot.relief_policy import ReliefCapability
from bot.semantic_actions import AcceptSocketInventoryFull, ExitSocket
from bot.socket_inventory_relief import SocketReturnPlan, SocketReliefOutcome
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionPolicy


@dataclass(frozen=True)
class ArenaFlowResult(FlowResult):
    mode: ArenaMode = ArenaMode.AUTO_REPEAT
    return_context: str = SCREEN_ARENA
    batch_result: ArenaBatchResult | None = None
    single_result: ArenaSingleResult | None = None
    phase: str = 'not_started'
    physical_operation_may_be_active: bool = False
    execution: ArenaBatchExecution | ArenaSingleExecution | None = None
    metrics: dict = field(default_factory=dict, compare=False)
    evidence: dict = field(default_factory=dict, compare=False, repr=False)


class _Stop(Exception):
    pass


class ArenaFlow:
    name = 'arena'
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(ComponentRequirement.exact_state('screen.lobby'),
                            (ComponentRequirement.exact_state(SCREEN_ARENA),))
    routine_contract = FlowContract(ComponentRequirement.exact_state('screen.lobby'),
                                   (ComponentRequirement.exact_state('screen.lobby'),))

    def __init__(self, observer, actions, reader, difficulty, *, socket_relief=None,
                 reliefs=None, transition=None, cancel_requested=lambda:False,
                 clock=time.monotonic, sleeper=time.sleep, events=None,
                 batch_timeout=1800., check_interval=3., transition_timeout=12.,
                 unknown_grace=30., evidence_sink=None, authorized_badge_ceiling=None,
                 mode=ArenaMode.AUTO_REPEAT, return_context=SCREEN_ARENA, victory_points=None):
        if not isinstance(difficulty,ArenaDifficulty):
            raise ValueError('explicit Arena difficulty required')
        if not isinstance(mode, ArenaMode) or mode not in (ArenaMode.SINGLE_BATTLE, ArenaMode.AUTO_REPEAT):
            raise ValueError('explicit Arena mode required')
        if return_context not in (SCREEN_ARENA, 'screen.lobby'):
            raise ValueError('Arena return requires Challenge or Lobby')
        self.mode=mode; self.return_context=return_context
        self.contract=type(self).routine_contract if return_context=='screen.lobby' else type(self).contract
        for value in (batch_timeout,check_interval,transition_timeout,unknown_grace):
            if isinstance(value,bool) or not math.isfinite(value) or value<=0:
                raise ValueError('finite positive Arena bounds required')
        self.observer=observer; self.source=observer.source; self.actions=actions
        self.reader=reader; self.v=reader.visuals; self.difficulty=difficulty
        self.socket_relief=socket_relief; self.reliefs=reliefs; self.transition=transition
        self.cancel_requested=cancel_requested; self.clock=clock; self.sleeper=sleeper
        self.events=events; self.batch_timeout=batch_timeout; self.interval=check_interval
        self.transition_timeout=transition_timeout; self.unknown_grace=unknown_grace
        self.evidence_sink=evidence_sink
        if authorized_badge_ceiling is not None and (type(authorized_badge_ceiling) is not int or authorized_badge_ceiling<8):
            raise ValueError('Badge authorization ceiling must permit at least eight')
        self.authorized_badge_ceiling=authorized_badge_ceiling
        self._unsafe_to_restart=False
        self.victory_points= victory_points

    def _cancel(self):
        if self.cancel_requested():
            raise _Stop('observer_cancelled')

    def _save(self, name, snapshot):
        self.evidence[name]=snapshot
        if self.evidence_sink is not None:
            try:
                self.evidence_sink(name,snapshot)
            except Exception as failure:
                self.metrics.setdefault('evidence_write_errors',[]).append(str(failure))

    def _sleep(self, seconds):
        start=time.perf_counter()
        self.sleeper(seconds)
        self.metrics['sleep_wall_seconds']+=time.perf_counter()-start

    def _cv(self, call):
        start=time.perf_counter()
        try:
            return call()
        finally:
            self.metrics['cv_seconds']+=time.perf_counter()-start

    def _fresh(self, snapshot):
        return (snapshot is not None and snapshot.timestamp>self._barrier
                and 0 <= self.clock()-snapshot.timestamp <= self.reader.max_age)

    def _capture(self, *, native=False):
        self._cancel()
        if self.observer.source is not self.source:
            raise _Stop('source_lifetime_changed')
        started=time.perf_counter()
        snapshot=self.source.get_frame()
        self.metrics['captures']+=1
        if native or snapshot.sequence<=self._cursor or not self._fresh(snapshot):
            refresh=getattr(self.source,'refresh_native',None)
            if refresh is None:
                if native:
                    raise _Stop('native_economy_capture_unavailable')
            elif native or self.clock()-self._last_native>=1.:
                snapshot=refresh(); self._last_native=self.clock()
                self.metrics['captures']+=1; self.metrics['native_captures']+=1
        self.metrics['capture_seconds']+=time.perf_counter()-started
        self._cancel()
        if snapshot.sequence<self._cursor or snapshot.timestamp<self._last_timestamp:
            self._save('source_discontinuity',snapshot)
            raise _Stop('source_sequence_or_timestamp_regressed')
        if snapshot.sequence==self._cursor or not self._fresh(snapshot):
            self.metrics['stale_rejects']+=1
            return None
        self._cursor=snapshot.sequence; self._last_timestamp=snapshot.timestamp
        self.metrics['observation_ages'].append(self.clock()-snapshot.timestamp)
        self._latest=snapshot
        return snapshot

    def _wait(self, predicate, *, timeout=None):
        bound=self.clock()+(timeout or self.transition_timeout)
        for _ in range(256):
            self._cancel()
            if self.clock()>=bound:
                break
            snapshot=self._capture()
            if snapshot is not None and self._cv(lambda:predicate(snapshot.image)):
                return snapshot
            self._sleep(min(.25,max(0.,bound-self.clock())))
        if self._latest is not None:
            self._save('unconfirmed_transition',self._latest)
        raise _Stop('transition_unconfirmed')

    def _tap(self, control, before):
        self._cancel()
        if not self._fresh(before) or before.sequence!=self._cursor:
            raise _Stop('action_source_stale')
        if control in (C.START,C.SINGLE_START):
            self.phase='start_uncertain'; self._unsafe_to_restart=True
        started=time.perf_counter()
        self.actions.execute(ArenaAction(control),FrameGeometry.from_frame(before.image),
                             events=self.events,source_sequence=before.sequence)
        self.metrics['action_seconds']+=time.perf_counter()-started
        self._barrier=self.clock()
        self.metrics['inputs'].append(control.value)

    def _effect(self, control, before, predicate):
        self._tap(control,before)
        return self._wait(predicate)

    def _challenge(self, image):
        return self.v.clean_challenge(image) and self.v.preparation(image).difficulty is self.difficulty

    def _navigate(self):
        self.phase='navigation'
        # Challenge alone cannot prove idle: it appears between Auto Repeat battles.
        # Caller supplies the contracted Lobby entry, including on subsequent calls.
        before=self._wait(self.v.lobby)
        entry=self.observer.observe()
        if not self._clean_base(entry,'screen.lobby') or not self.v.lobby(entry.frame.image) or not self._fresh(entry.frame):
            raise _Stop('lobby_entry_uncredited')
        self._cursor=entry.frame.sequence; self._last_timestamp=entry.frame.timestamp; before=entry.frame
        # Arena acquisition target differs from the existing Survival entry.
        before=self._effect(C.BATTLE,before,self.v.select_mode)
        before=self._effect(C.ARENA,before,lambda f:self.v.selection(f) or self.v.ranking(f))
        if self.v.ranking(before.image):
            before=self._effect(C.RANKING_OK,before,self.v.selection)
        return self._effect(C[self.difficulty.value],before,self._challenge)

    def _economy(self):
        snapshot=self._capture(native=True)
        if snapshot is None or not self._cv(lambda:self._challenge(snapshot.image)):
            raise _Stop('challenge_or_difficulty_uncredited')
        start=time.perf_counter()
        facts=self.reader.economy(snapshot,cancel_requested=self.cancel_requested)
        self.metrics['ocr_seconds']+=time.perf_counter()-start
        self._cancel()
        if facts is None or facts.sequence!=snapshot.sequence or facts.observed_at!=snapshot.timestamp or not self._fresh(snapshot):
            self._save('economy_unknown',snapshot)
            raise _Stop('economy_unknown')
        if facts.available_badges<8:
            raise _Stop('fewer_than_eight_badges')
        if self.authorized_badge_ceiling is not None and self._planned_consumption(facts)>self.authorized_badge_ceiling:
            raise _Stop('batch_exceeds_badge_authorization')
        return snapshot,facts

    def _planned_consumption(self, facts):
        return 8 if self.mode is ArenaMode.SINGLE_BATTLE else facts.planned_consumption

    def _prepare(self, before):
        self.phase='preparation'
        prep=self.v.preparation(before.image)
        if prep.x8 is False:
            before=self._effect(C.X8,before,lambda f:self._challenge(f) and self.v.preparation(f).x8 is True)
        elif prep.x8 is not True:
            raise _Stop('x8_unknown')
        before,facts=self._economy()
        for index,control in enumerate((C.BUFF1,C.BUFF2)):
            selected=facts.preparation.buffs[index]
            if selected is False:
                self._effect(control,before,lambda f,i=index:self._challenge(f) and self.v.preparation(f).buffs[i] is True)
                before,facts=self._economy()
            elif selected is not True:
                raise _Stop('mandatory_buff_unknown')
        # ON with unknown reservation is safe only if FREE stock itself covers all.
        selected=facts.preparation.buffs[2]; free=facts.free_buffs[2]
        reserved=0
        if selected is True and (free is None or free<self._planned_consumption(facts)):
            self._effect(C.BUFF3,before,lambda f:self._challenge(f) and self.v.preparation(f).buffs[2] is False)
            before,facts=self._economy()
            # No inferred refund; keep OFF for this batch after insufficiency.
        elif selected is False and free is not None and free>=self._planned_consumption(facts):
            old_free=free
            self._effect(C.BUFF3,before,lambda f:self._challenge(f) and self.v.preparation(f).buffs[2] is True)
            before,facts=self._economy()
            if facts.free_buffs[2]==old_free-8:
                reserved=8
            else:
                self._effect(C.BUFF3,before,lambda f:self._challenge(f) and self.v.preparation(f).buffs[2] is False)
                before,facts=self._economy()
        if (facts.preparation.buffs[:2]!=(True,True) or facts.preparation.x8 is not True
                or (facts.preparation.buffs[2] is not False and
                    (facts.preparation.buffs[2] is not True or facts.free_buffs[2] is None
                     or facts.free_buffs[2]+reserved<self._planned_consumption(facts)))):
            raise _Stop('prepared_economy_uncredited')
        self.metrics['planned_consumption']=self._planned_consumption(facts)
        self.metrics['double_points_reserved']=reserved
        self.metrics['prepared_resources']=dict(badges=facts.available_badges,free_buffs=facts.free_buffs,
                                                 selected_buffs=facts.preparation.buffs)
        self._save('prepared_native',before)
        return before,facts

    def _configure(self, before, facts):
        self.phase='configuration'
        before=self._effect(C.CONFIG,before,self.v.config)
        upon=self.v.upon_defeat(before.image)
        if upon is None:
            native=self._capture(native=True)
            if native is None or not self.v.config(native.image):
                raise _Stop('configuration_native_unknown')
            before=native; upon=self.v.upon_defeat(before.image)
        if upon is True:
            # Used only with positive ON evidence; default Phase A visuals return UNKNOWN.
            before=self._effect(C.UPON_DEFEAT,before,lambda f:self.v.config(f) and self.v.upon_defeat(f) is False)
        if self.v.upon_defeat(before.image) is not False:
            raise _Stop('upon_defeat_unknown')
        if not 0<=self.clock()-facts.observed_at<=self.reader.max_age:
            raise _Stop('prepared_economy_expired')
        return before

    def _blocked(self, image):
        return self.v.has(image,'bag_full') and self.v.has(image,'config_start') and not self.v.loading(image)

    def _relieve(self, blocker, facts, *, allow):
        self._save('socket_blocker',blocker)
        # Positive prompt plus unchanged native Badge balance certifies no entry consumed.
        native=self._capture(native=True)
        from bot.arena_flow_reader import ECONOMY_ROIS
        balance=self.reader._integer(native.image,ECONOMY_ROIS[0],self.cancel_requested)[0] if native else None
        if native is None or not self._blocked(native.image) or balance!=facts.available_badges or not self._fresh(native):
            raise _Stop('blocked_start_lineage_uncertain')
        self._unsafe_to_restart=False; self.phase='not_started'
        if not allow:
            raise _Stop('socket_blocker_recurred')
        if any(x is None for x in (self.socket_relief,self.reliefs,self.transition)):
            raise _Stop('socket_relief_unavailable')
        before=self.observer.observe()
        entered=self.transition.execute('arena.socket_blocker',AcceptSocketInventoryFull(),before,
            precondition=lambda s: POPUP_SOCKET_INVENTORY_FULL in s.state.overlays and self._blocked(s.frame.image),
            expected=lambda s:self._clean_base(s,SCREEN_SOCKET),
            abort_if=lambda s:self.cancel_requested(),
            policy=VerifiedTransitionPolicy(max_attempts=1))
        self._cancel()
        if not entered.succeeded:
            raise _Stop('socket_entry_unconfirmed')
        relieved=self.reliefs.handle(ReliefCapability.SOCKET,self.socket_relief.run,
            SocketReturnPlan(ExitSocket(),SCREEN_ARENA),self.cancel_requested)
        self._cancel()
        if relieved.outcome is not SocketReliefOutcome.RELIEVED:
            raise _Stop('socket_relief_or_return_unconfirmed')
        returned=self.observer.observe()
        if not self._clean_base(returned,SCREEN_ARENA) or not self.v.clean_challenge(returned.frame.image):
            raise _Stop('socket_return_not_clean_challenge')
        # External owner observed newer frames. Adopt a fresh barrier, never old readiness.
        self._barrier=self.clock(); self._cursor=max(self._cursor,returned.frame.sequence)
        return self._wait(self._challenge)

    def _start(self, config, facts, *, allow_relief):
        started_at=self.clock()
        self._tap(C.START,config)
        after=self._wait(lambda f:self.v.loading(f) or self.v.active(f) or self._blocked(f))
        if self._blocked(after.image):
            return None,self._relieve(after,facts,allow=allow_relief)
        self.execution=ArenaBatchExecution(self.run_id,self.source_id,self.difficulty,8,
                                           started_at,config.sequence,True)
        self._started_badges=facts.available_badges
        self.phase='active'; self._save('start_verified',after)
        return self.execution,after

    def _start_single(self):
        # Final native preparation and balances from the SAME snapshot.
        before,facts=self._economy()
        balances=self.reader.balances(before,cancel_requested=self.cancel_requested)
        self._cancel()
        if (balances is None or balances.badges!=facts.available_badges or not self._fresh(before)
                or facts.preparation.buffs[:2]!=(True,True) or facts.preparation.x8 is not True
                or facts.available_badges!=self.metrics['prepared_resources']['badges']
                or facts.free_buffs[2]!=self.metrics['prepared_resources']['free_buffs'][2]
                or facts.preparation.buffs!=self.metrics['prepared_resources']['selected_buffs']):
            raise _Stop('single_start_balances_or_preparation_uncredited')
        self._save('single_start_native',before)
        started_at=self.clock()
        self._tap(C.SINGLE_START,before)
        after=self._wait(lambda f:self.v.loading(f) or self.v.single_active(f))
        self.execution=ArenaSingleExecution(self.run_id,self.source_id,self.difficulty,8,
            started_at,before.sequence,True,balances.badges,balances.karats)
        self._started_badges=balances.badges
        self.phase='active'; self._save('start_verified',after)

    def _terminal_wait(self):
        self.phase='active'
        latest=None; unknown_image=None; unknown_since=None; boundary=None
        bound=min(self.clock()+self.batch_timeout,self.execution.started_at+self.batch_timeout)
        start=self.clock(); last_observed=None
        wait_ocr=self.reader.ocr_calls; wait_cv=self.metrics['cv_seconds']
        wait_captures=self.metrics['captures']; wait_sleep=self.metrics['sleep_wall_seconds']
        wait_wall=time.perf_counter()

        def complete():
            nonlocal latest,unknown_image,unknown_since,boundary,last_observed
            if self.clock()>=bound:
                return False
            snapshot=self._capture()
            if snapshot is None:
                return False
            self.metrics['wait_captures']+=1
            self.metrics['wait_times'].append(self.clock())
            terminal_reader=self.reader.single_terminal if self.mode is ArenaMode.SINGLE_BATTLE else self.reader.terminal
            positive=self._cv(lambda:terminal_reader(snapshot,self.execution,run_id=self.run_id,source_id=self.source_id))
            if positive:
                self.metrics['terminal_detections']+=1
                self.metrics['capture_to_terminal_seconds']=self.clock()-snapshot.timestamp
                # Onset is not observed continuously: record bracket, not a claimed latency.
                self.metrics['terminal_onset_observation_bracket']=(last_observed,snapshot.timestamp)
                latest=snapshot
                return True
            last_observed=snapshot.timestamp
            # Sparse checks for boundaries; no global resolver or OCR in this wait.
            known=self._cv(lambda:self.v.active(snapshot.image) or self.v.clean_challenge(snapshot.image) or self.v.loading(snapshot.image)
                           or (self.mode is ArenaMode.SINGLE_BATTLE and self.v.single_active(snapshot.image)))
            if known:
                unknown_image=None; unknown_since=None
            else:
                import cv2
                import numpy as np
                thumbnail=cv2.resize(snapshot.image,(64,36)).astype(float)
                if unknown_image is None or np.mean(np.abs(unknown_image-thumbnail))>2.:
                    unknown_image=thumbnail; unknown_since=self.clock()
                elif self.clock()-unknown_since>=self.unknown_grace:
                    boundary='unrecognized_persistent_surface'
                # Known foreign modals are immediate boundaries, never acknowledged here.
                # Our configuration may fade back in after credited Loading.
                # Observe it passively under the persistent-unknown bound.
                if self._cv(lambda:self.v.ranking(snapshot.image) or self.v.insufficient(snapshot.image)):
                    boundary='nonterminal_modal_during_batch'
                self._save('unrecognized_wait_surface',snapshot)
            return False

        waiter=ControlledWait(check_interval=self.interval,clock=self.clock,sleeper=self._sleep,
                              events=self.events,label='arena.batch_terminal')
        outcome=waiter.wait(deadline=bound,completion_condition=complete,
                            terminal_condition=lambda:boundary is not None,
                            cancel_requested=self.cancel_requested)
        self.metrics['wait_elapsed']=self.clock()-start
        self.metrics['wait_outcome']=outcome.outcome.value
        self.metrics['wait_error']=outcome.error
        self.metrics['wait_ocr_calls']=self.reader.ocr_calls-wait_ocr
        self.metrics['wait_cv_seconds']=self.metrics['cv_seconds']-wait_cv
        self.metrics['wait_capture_calls']=self.metrics['captures']-wait_captures
        self.metrics['wait_observer_work_wall_seconds']=max(0.,time.perf_counter()-wait_wall-
            (self.metrics['sleep_wall_seconds']-wait_sleep))
        if self.cancel_requested():
            raise _Stop('observer_cancelled')
        if not outcome.succeeded:
            raise _Stop(boundary or ('technical_wait_interruption' if outcome.outcome is ControlledWaitOutcome.FAILED else 'batch_terminal_timeout'))
        self.phase='terminal'; self._unsafe_to_restart=False
        self._save('terminal',latest)
        # Native terminal observation shares the source's actual sequence/time.
        # It also avoids accepting a plausible H264 prefix as economic authority.
        latest=self._capture(native=True)
        if latest is None:
            self.phase='result_ambiguous'
            raise _Stop('terminal_native_observation_unknown')
        if self.mode is ArenaMode.SINGLE_BATTLE:
            if not self.reader.single_terminal(latest,self.execution,run_id=self.run_id,source_id=self.source_id):
                raise _Stop('single_terminal_native_unknown')
            self._save('single_terminal_native',latest)
            return latest
        for _ in range(2):
            self._cancel()
            started=time.perf_counter()
            self.batch_result=self.reader.read(latest,self.execution,run_id=self.run_id,
                                              source_id=self.source_id,cancel_requested=self.cancel_requested)
            self.metrics['ocr_seconds']+=time.perf_counter()-started
            if self.batch_result is not None:
                if self.batch_result.used_tickets>self._started_badges:
                    self.phase='result_ambiguous'
                    raise _Stop('result_exceeds_credited_start_badges')
                if (self.authorized_badge_ceiling is not None
                        and self.batch_result.used_tickets>self.authorized_badge_ceiling):
                    self.phase='result_ambiguous'
                    raise _Stop('result_exceeds_badge_authorization')
                return latest
            latest=self._capture(native=True)
            if latest is None:
                break
        self.phase='result_ambiguous'
        raise _Stop('terminal_numbers_unknown')

    @staticmethod
    def _clean_base(snapshot, name):
        return (snapshot.state.status is ResolutionStatus.RESOLVED and snapshot.state.base_context==name
                and not snapshot.state.overlays)

    def _close(self, terminal):
        self.phase='closing'
        before=self._effect(C.RESULT_OK,terminal,lambda f:self.v.clean_challenge(f) or self.v.insufficient(f) or self.v.ranking(f))
        closed=set()
        for _ in range(3):
            self._cancel()
            if self.v.clean_challenge(before.image):
                final=self.observer.observe()
                self._cancel()
                if (self._clean_base(final,SCREEN_ARENA) and self.v.clean_challenge(final.frame.image)
                        and self._fresh(final.frame) and final.frame.sequence>=before.sequence):
                    self.phase='returned'; return final
                # Insufficient can appear just after the intermediate Challenge.
                # Adopt its fresh observation, without another result OK.
                if (self._fresh(final.frame) and final.frame.sequence>=before.sequence
                        and (self.v.insufficient(final.frame.image) or self.v.ranking(final.frame.image))):
                    self._cursor=final.frame.sequence; self._last_timestamp=final.frame.timestamp
                    before=final.frame
                else:
                    raise _Stop('return_base_uncredited')
            control=C.BADGES_NO if self.v.insufficient(before.image) else C.RANKING_OK if self.v.ranking(before.image) else None
            if control is None or control in closed:
                raise _Stop('post_result_modal_unrecognized_or_repeated')
            closed.add(control)
            before=self._effect(control,before,lambda f:self.v.clean_challenge(f) or self.v.insufficient(f) or self.v.ranking(f))
        raise _Stop('return_bound_exhausted')

    def run(self):
        return self._run()

    def _close_single(self, terminal):
        self.phase='closing'
        before=self._effect(C.SINGLE_RESULT_CLOSE,terminal,lambda f:self.v.selection(f) or self.v.ranking(f))
        if self.v.ranking(before.image):
            before=self._effect(C.RANKING_OK,before,self.v.selection)
        # Single returns to selection, unlike Auto Repeat's Challenge.
        final=self.observer.observe()
        self._cancel()
        if (not self._clean_base(final,SCREEN_ARENA) or not self.v.selection(final.frame.image)
                or not self._fresh(final.frame) or final.frame.sequence<before.sequence):
            raise _Stop('single_return_selection_uncredited')
        snapshot=self._capture(native=True)
        balances=self.reader.balances(snapshot,cancel_requested=self.cancel_requested) if snapshot else None
        self._cancel()
        if balances is None:
            raise _Stop('single_post_close_balances_unknown')
        self._save('single_balances_after',snapshot)
        try:
            self.single_result=ArenaSingleResult(self.difficulty,8,ArenaSingleOutcome.VICTORY,
                self.execution.start_badges,balances,self.execution.start_karats,self.run_id,self.source_id,
                terminal.sequence,terminal.timestamp,hashlib.sha256(terminal.image.tobytes()).hexdigest())
        except ValueError:
            raise _Stop('single_consumption_or_reward_uncredited')
        # Resolver proof must remain fresh at the return boundary.
        final=self.observer.observe()
        self._cancel()
        if (not self._clean_base(final,SCREEN_ARENA) or not self.v.selection(final.frame.image)
                or not self._fresh(final.frame) or final.frame.sequence<snapshot.sequence):
            raise _Stop('single_return_selection_uncredited')
        self.phase='returned'
        return final

    def _return_to_caller(self, challenge):
        """Acquired Back route after a typed result and clean Challenge/selection.

        This restores the contracted Lobby entry. Navigation to another BASE is
        caller-owned; no Quick Menu or Survival Select Mode route is assumed.
        """
        if self.return_context==SCREEN_ARENA:
            return challenge
        self.phase='external_return'
        before=challenge.frame
        if (not self._clean_base(challenge,SCREEN_ARENA) or not self._fresh(before)
                or not (self.v.clean_challenge(before.image) or self.v.selection(before.image))):
            raise _Stop('external_return_entry_uncredited')
        self._cursor=before.sequence; self._last_timestamp=before.timestamp
        if self.v.clean_challenge(before.image):
            before=self._back(before,lambda f:self.v.selection(f) or self.v.ranking(f))
            if self.v.ranking(before.image):
                before=self._effect(C.RANKING_OK,before,self.v.selection)
        self._save('return_selection',before)
        vp_frame=before
        before=self._back(before,self.v.select_mode)
        self._save('return_select_mode',before)
        before=self._back(before,self.v.lobby)
        final=self.observer.observe()
        self._cancel()
        if (not self._clean_base(final,'screen.lobby') or not self._fresh(final.frame)
                or final.frame.sequence<before.sequence or not self.v.lobby(final.frame.image)):
            raise _Stop('external_return_lobby_uncredited')
        self._save('return_lobby',final.frame)
        self.phase='returned'
        # Retain the normal selection frame, but complete all physical return
        # guards before optional OCR. Slow/failed informational work cannot
        # consume Back freshness or require another navigation observation.
        if self.mode is ArenaMode.AUTO_REPEAT and self.batch_result is not None and self.victory_points is not None:
            try:
                self.victory_points.observe_character(vp_frame,self.v,
                    cancel_requested=self.cancel_requested,events=self.events)
            except Exception as error:
                record_best_effort(self.events,'arena.vp_omitted',reason=type(error).__name__)
        return final

    def _back(self, before, predicate):
        if not self.v.back_visible(before.image):
            raise _Stop('back_control_uncredited')
        return self._effect(C.BACK,before,predicate)

    def observe_started_batch(self, execution, started_badges):
        """Continue a caller-credited batch on an explicitly rebound source segment.

        Caller must retain the single Start and positive post-start evidence,
        establish uninterrupted physical ownership, and supply a NEW segment
        receipt. This method never prepares, navigates or sends Start.
        """
        if (self.mode is not ArenaMode.AUTO_REPEAT
                or not isinstance(execution,ArenaBatchExecution) or not execution.start_verified
                or execution.difficulty is not self.difficulty or execution.multiplier!=8
                or type(started_badges) is not int or started_badges<8):
            raise ValueError('verified existing batch and credited start balance required')
        return self._run(execution,started_badges)

    def observe_started_single(self, execution):
        """Explicit source handoff of one independently credited physical Start.

        Like the B1 handoff, caller retains historical input/balances and must
        recredit positive activity/terminal in the new source lifetime. No inputs
        for navigation, preparation or Start are permitted by this entry point.
        """
        if (self.mode is not ArenaMode.SINGLE_BATTLE
                or not isinstance(execution,ArenaSingleExecution) or not execution.start_verified
                or execution.difficulty is not self.difficulty):
            raise ValueError('verified existing Single and starting balances required')
        return self._run(execution,execution.start_badges)

    def _run(self, existing=None, started_badges=None):
        if self._unsafe_to_restart:
            return ArenaFlowResult(FlowStatus.MANUAL_RESOLUTION,error='previous_physical_operation_unresolved',
                                   physical_operation_may_be_active=True,phase='start_uncertain',
                                   mode=self.mode,return_context=self.return_context)
        self.run_id=existing.run_id if existing else uuid4().hex
        self.source_id=existing.source_id if existing else uuid4().hex
        self._cursor=-1; self._last_timestamp=-1.; self._barrier=-1.; self._last_native=-math.inf
        self._latest=None; self.execution=None; self.batch_result=None; self.single_result=None; self.phase='not_started'
        if existing is not None:
            self.execution=existing; self._started_badges=started_badges
            self._unsafe_to_restart=True; self.phase='active'
        self.evidence={}; self.metrics=dict(captures=0,native_captures=0,capture_seconds=0.,cv_seconds=0.,
            ocr_seconds=0.,action_seconds=0.,sleep_wall_seconds=0.,stale_rejects=0,observation_ages=[],inputs=[],wait_captures=0,wait_times=[],terminal_detections=0)
        ocr_before=self.reader.ocr_calls; started=time.perf_counter(); final=None
        status=FlowStatus.MANUAL_RESOLUTION; error=None
        try:
            self._cancel()
            if existing is not None:
                self._cursor=existing.after_sequence
                before=self._wait(lambda f:self.v.loading(f) or
                    (self.v.single_active(f) or self.v.single_result(f) if self.mode is ArenaMode.SINGLE_BATTLE
                     else self.v.active(f) or self.v.terminal(f)))
                self._save('observation_handoff_verified',before)
            else:
                before=self._navigate()
            warm=time.perf_counter(); self.reader.prewarm(before)
            self.metrics['ocr_prewarm_seconds']=time.perf_counter()-warm
            self._cancel()
            if existing is None:
                before=self._wait(self._challenge)
                if self.mode is ArenaMode.SINGLE_BATTLE:
                    before,facts=self._prepare(before)
                    self._start_single()
                else:
                    for attempt in range(2):
                        before,facts=self._prepare(before)
                        config=self._configure(before,facts)
                        execution,before=self._start(config,facts,allow_relief=attempt==0)
                        if execution is not None:
                            break
                        if attempt==1:
                            raise _Stop('socket_blocker_recurred')
            terminal=self._terminal_wait()
            challenge=self._close_single(terminal) if self.mode is ArenaMode.SINGLE_BATTLE else self._close(terminal)
            final=self._return_to_caller(challenge)
            status=FlowStatus.COMPLETED
        except _Stop as stopped:
            error=str(stopped)
            if self.cancel_requested() or error=='observer_cancelled':
                status=FlowStatus.CANCELLED
        except Exception as failure:
            status=FlowStatus.CANCELLED if self.cancel_requested() else FlowStatus.FAILED
            error=f'{type(failure).__name__}: {failure}'
        finally:
            if status is not FlowStatus.COMPLETED and self._latest is not None:
                self._save('stopped',self._latest)
            self.metrics['ocr_calls']=self.reader.ocr_calls-ocr_before
            if status is not FlowStatus.COMPLETED and self.execution is not None:
                # Historical start evidence remains; this stopped observer no longer
                # authorizes a future reader to reuse its execution receipt.
                self.execution=replace(self.execution,start_verified=False)
                self.metrics['execution_lineage_invalidated']=True
            self.metrics['flow_wall_seconds']=time.perf_counter()-started
            self.metrics['observer_work_wall_seconds']=max(0.,self.metrics['flow_wall_seconds']-self.metrics['sleep_wall_seconds'])
            record_best_effort(self.events,'arena.finished',status=status.value,phase=self.phase,
                               physical_operation_may_be_active=self._unsafe_to_restart,error=error,metrics=self.metrics)
        return ArenaFlowResult(status,error=error,final_snapshot=final,batch_result=self.batch_result,
            phase=self.phase,physical_operation_may_be_active=self._unsafe_to_restart,
            execution=self.execution,metrics=self.metrics.copy(),evidence=self.evidence.copy(),
            mode=self.mode,return_context=self.return_context,single_result=self.single_result)
