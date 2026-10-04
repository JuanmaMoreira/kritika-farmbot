"""Daily orchestration: resources→concrete Stage8 ads path→fresh effect."""
from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowContract,FlowEvent,FlowResult,FlowScope,FlowStatus,publish_flow_events
from bot.ads_manager import AdsOutcome
from bot.stages_actions import StageControl as C
from bot.stages_runtime import lobby
from bot.perception.stages import surface
from bot.runtime_observer import RuntimeWaitCancelled
from bot.event_log import record_best_effort
from bot.event_context import event_scope
from bot.character_resources import character_resource_knowledge

class StagesDailyFlow:
    name='stages_daily';scope=FlowScope.PER_CHARACTER
    contract=FlowContract(ComponentRequirement.exact_state('screen.lobby'),
                          (ComponentRequirement.exact_state('screen.lobby'),))
    def __init__(self,navigation,balances,stamina,ads,*,monster_wave,reenter_same_character,ensure_lobby=None):
        self.nav,self.balances,self.stamina,self.ads=navigation,balances,stamina,ads
        self.monster_wave,self.reenter_same_character=monster_wave,reenter_same_character
        self.ensure_lobby = ensure_lobby or (lambda: self.nav.wait(lobby))

    def run(self):
        n=self.nav
        try:
            # Session reuses each occurrence binding across characters. Only
            # reset its invocation bound here; retries within this run stay bounded.
            if getattr(n,"relief",None) is not None:n.relief.reset()
            knowledge=character_resource_knowledge()
            if knowledge is not None and knowledge.stage_ads_exhausted:
                return FlowResult(FlowStatus.COMPLETED,(FlowEvent('stages_daily.ads_exhausted',
                    fields={'known':True,'navigation':False}),))
            before=self.balances.read()
            record_best_effort(n.events,'stages.entry_preconditions',stamina=before.stamina,
                sapphires=before.sapphires,sapphire_limit=before.sapphire_limit)
            if before.needs_monster_wave:
                record_best_effort(n.events,'stages.prerequisite',flow='monster_wave')
                with event_scope(activity_id='monster_wave',activity_role='prerequisite'):
                    dependency=self.monster_wave.run()
                    record_best_effort(n.events,'stages.prerequisite.result',result=dependency.status.value,
                        decision='continue' if dependency.succeeded else 'stop')
                    publish_flow_events(n.events,'monster_wave',dependency.events,prerequisite='stages_daily')
                if dependency.status is not FlowStatus.COMPLETED:return dependency
                self.ensure_lobby()
                before=self.balances.read()
                if before.needs_monster_wave:
                    return FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.mw_required'),))
            before=self.stamina.ensure(before)
            if before.stamina<300 or before.needs_monster_wave:raise ValueError('stages preconditions invalid')
            # Fresh Sapphire baseline is reacquired after all prerequisites.
            before=self.balances.read()
            if before.stamina<300 or before.needs_monster_wave:
                return FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.preconditions_changed'),))
            initial=before.sapphires
            s,count=n.prepare_ad(n.enter_target())
            if count==0:
                n.exit_to_lobby()
                return self._exhausted_result()
            # Initial + two temporal retries, then one same-character reset +
            # one final attempt. Only explicit No Ads permits another Video intent.
            aborted_retries=0
            for reset in range(2):
                attempts=3 if reset==0 else 1
                for attempt in range(attempts):
                    record_best_effort(n.events,'stages.video_attempt',reset=reset,attempt=attempt+1)
                    n.tap(C.VIDEO,s)
                    result=self.ads.complete_requested_launch()
                    while result.outcome is AdsOutcome.ABORTED_RECOVERED:
                        record_best_effort(n.events,'stages.ad_aborted_recovered',retry=aborted_retries)
                        # Back has already stopped at the game. Recover with
                        # acquired game controls, never infer an ad/reward debit.
                        n.cursor=result.snapshot.sequence
                        n.exit_to_lobby()
                        if aborted_retries>=1:
                            return self._aborted_result()
                        fresh=self.balances.read()
                        if fresh.stamina<300 or fresh.needs_monster_wave:
                            return self._aborted_result()
                        aborted_retries+=1
                        initial=fresh.sapphires
                        s,count=n.prepare_ad(n.enter_target())
                        if count==0:
                            n.exit_to_lobby()
                            return self._exhausted_result()
                        n.tap(C.VIDEO,s)
                        result=self.ads.complete_requested_launch()
                    if result.outcome is AdsOutcome.CANCELLED:return FlowResult(FlowStatus.CANCELLED)
                    if result.outcome is AdsOutcome.RETURNED:
                        n.cursor=result.snapshot.sequence
                        n.acknowledge_results()
                        after=self.balances.read()
                        record_best_effort(n.events,'stages.sapphire_effect',before=initial,after=after.sapphires)
                        if after.sapphires<=initial:raise ValueError('stages sapphire effect unverified')
                        return FlowResult(FlowStatus.COMPLETED,(FlowEvent('stages_daily.completed',fields={
                            'sapphires_before':initial,'sapphires_after':after.sapphires,
                            'ads':1,'stamina_after':after.stamina}),))
                    if result.outcome is AdsOutcome.RECOVERY_FAILED:
                        raise ValueError('AD_RECOVERY_FAILED: unable to recover Kritika')
                    if result.outcome is AdsOutcome.EXHAUSTED:
                        n.change(C.NO_ADS_OK,result.snapshot,{'auto'})
                        n.exit_to_lobby()
                        return self._exhausted_result()
                    if result.outcome is not AdsOutcome.UNAVAILABLE:
                        raise ValueError('stages unsupported ad outcome')
                    s=n.change(C.NO_ADS_OK,result.snapshot,{'auto'})
                    if attempt+1<attempts:
                        self._retry_delay();s=n.wait(lambda s:surface(s)=='auto')
                n.exit_to_lobby()
                if reset==0:
                    self.reenter_same_character()
                    fresh=self.balances.read()
                    if fresh.stamina<300 or fresh.needs_monster_wave:
                        return FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.preconditions_changed'),))
                    s,count=n.prepare_ad(n.enter_target())
                    if count==0:
                        n.exit_to_lobby()
                        return self._exhausted_result()
            return FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.ads_unavailable',
                detail='ADS_UNAVAILABLE: two temporal retries and same-character reentry exhausted; no manual entry.',
                fields={'temporal_retries':2,'same_character_reentries':1,'launches':4}),))
        except RuntimeWaitCancelled:return FlowResult(FlowStatus.CANCELLED)
        except Exception as e:return FlowResult(FlowStatus.FAILED,error=f'{type(e).__name__}: {e}')

    @staticmethod
    def _exhausted_result():
        knowledge=character_resource_knowledge()
        if knowledge is not None:knowledge.stage_ads_exhausted=True
        return FlowResult(FlowStatus.COMPLETED,(FlowEvent('stages_daily.ads_exhausted'),))

    @staticmethod
    def _aborted_result():
        return FlowResult(FlowStatus.MANUAL_RESOLUTION,(FlowEvent('stages_daily.ad_aborted_recovered',
            detail='AD_ABORTED_RECOVERED: no verified reward or attempt consumption; bounded retry exhausted or preconditions changed.'),))

    def _retry_delay(self):
        n=self.nav;until=n.clock()+5.
        record_best_effort(n.events,"stages.ads_retry_wait",seconds=5.)
        while n.clock()<until:
            if n.cancel_requested():raise RuntimeWaitCancelled('stages cancelled')
            n.observer._sleeper(min(.25,until-n.clock()))
