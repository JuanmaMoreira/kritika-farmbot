"""One occurrence owns the loop; subordinate flows own every physical input."""
from dataclasses import dataclass, replace
from enum import Enum
import time
from typing import Protocol

from bot.arena_adaptive import ArenaAdaptiveController
from bot.arena_config import ArenaConfig, ArenaMode
from bot.arena_flow import ArenaFlow
from bot.arena_farming_resources import ArenaFarmingResources
from bot.event_context import event_scope
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.runtime_observer import RuntimeWaitCancelled,RuntimeWaitTimeout

MAX_ZERO_YIELD_BATCHES = 6  # Two samples at each of three levels, at most.


class ManualStagesOperation(Protocol):
    """One verified manual entry; caller refreshes resources for routing."""
    def run(self) -> FlowResult: ...


class FarmingTermination(str, Enum):
    EASY_ZERO_WINS = 'easy_zero_wins'
    NO_PROGRESS = 'no_progress'
    NO_PRODUCTIVE_ROUTE = 'no_productive_route'
    MANUAL_STAGES_NOT_IMPLEMENTED = 'manual_stages_not_implemented'
    SAFETY_LIMIT = 'safety_limit'
    AMBIGUOUS = 'ambiguous'
    SUBORDINATE_STOP = 'subordinate_stop'
    TECHNICAL_FAILURE = 'technical_failure'
    CANCELLED = 'cancelled'
    STAMINA_INSUFFICIENT = 'stamina_insufficient'
    SAPPHIRE_CAPACITY_FULL = 'sapphire_capacity_full'
    MANUAL_STAGE_DEFEATED = 'manual_stage_defeated'
    STAMINA_BUDGET_REACHED = 'stamina_budget_reached'
    STAMINA_SUPPLY_UNAVAILABLE = 'stamina_supply_unavailable'


@dataclass(frozen=True)
class ArenaFarmingResult(FlowResult):
    termination: FarmingTermination | None = None
    operations: tuple[FlowResult, ...] = ()
    resources: ArenaFarmingResources | None = None
    physical_operation_may_be_active: bool = False
    stamina_consumed: int = 0
    remaining_stamina_budget: int | None = None
    stamina_prepared: bool = False
    stamina_consumption_pending: bool = False
    duration: float | None = None
    maximum_stamina_consumption: int | None = None


class ArenaFarmingCycle:
    name = 'arena'
    scope = ArenaFlow.scope
    contract = ArenaFlow.routine_contract

    def __init__(self, resources, arena_factory, monster_wave, *, ensure_lobby,
                 config=ArenaConfig(ArenaMode.FARMING_CYCLE), manual_stages=None,
                 cancel_requested=lambda: False, clock=time.monotonic, max_operations=32):
        if config.mode is not ArenaMode.FARMING_CYCLE:
            raise ValueError('Farming Cycle occurrence required')
        if type(max_operations) is not int or max_operations < 1:
            raise ValueError('positive operation bound required')
        self.reader, self.arena_factory, self.monster_wave = resources, arena_factory, monster_wave
        self.ensure_lobby, self.config, self.manual_stages = ensure_lobby, config, manual_stages
        self.cancel_requested, self.clock, self.max_operations = cancel_requested, clock, max_operations
        self._unsafe_to_restart = False
        self._checkpoint=None
        self.stamina_consumed=0;self.stamina_prepared=False
        self._credited_entries=set();self._pending_manual=False;self._pending_supply=False
        self._started_at = None
        self._last_resource_diagnosis = None

    @property
    def remaining_stamina_budget(self):
        maximum=self.config.maximum_stamina_consumption
        return None if maximum is None else maximum-self.stamina_consumed

    def activity(self, resources):
        if resources.badges >= self.config.min_badges_for_arena:
            return 'arena'
        if resources.sapphires >= self.config.min_sapphires_for_mw:
            return 'monster_wave'
        return 'manual_stages'

    def run(self):
        events, operations, balances = [], [], None
        zero_batches=0;start_index=0
        activity = 'resource_refresh'
        self._last_resource_diagnosis = None
        if self._checkpoint is not None:
            events,operations,balances,zero_batches,start_index=self._checkpoint
            events=list(events);operations=list(operations)
        elif not self._unsafe_to_restart:
            self._started_at = self.clock()
            self.controller = ArenaAdaptiveController(self.config.zero_win_threshold)
            self.stamina_consumed=0;self.stamina_prepared=False
            self._credited_entries=set();self._pending_manual=False;self._pending_supply=False
            events.append(FlowEvent('arena.farming.started',fields={
                'min_badges_for_arena':self.config.min_badges_for_arena,
                'min_sapphires_for_mw':self.config.min_sapphires_for_mw,
                'zero_win_threshold':self.config.zero_win_threshold,
                'maximum_stamina_consumption':self.config.maximum_stamina_consumption}))

        def finish(reason, status=FlowStatus.COMPLETED, subordinate=None, error=None):
            prior=operations[-1] if self._pending_manual and operations else None
            active = bool(getattr(subordinate or prior,'physical_operation_may_be_active',False))
            self._unsafe_to_restart |= active
            self._checkpoint=(tuple(events),tuple(operations),balances,zero_batches,
                len(operations)-int(self._pending_manual)) if status is not FlowStatus.COMPLETED else None
            duration = None if self._started_at is None else max(0., self.clock()-self._started_at)
            terminated_detail = None
            if status is FlowStatus.MANUAL_RESOLUTION and error:
                text = str(error).strip()
                terminated_detail = text[:200] if text else None
            return ArenaFarmingResult(status, tuple(events) + (FlowEvent('arena.farming.terminated',
                detail=terminated_detail,
                fields={'reason': reason.value,'stamina_consumed':self.stamina_consumed,
                    'remaining_stamina_budget':self.remaining_stamina_budget,
                    'maximum_stamina_consumption':self.config.maximum_stamina_consumption,
                    'duration':duration,'initial_difficulty':'HARD',
                    'final_difficulty':getattr(getattr(self,'controller',None),'difficulty',None).value
                        if getattr(self,'controller',None) is not None else None,
                    'manual_entries':len(self._credited_entries),
                    'intervention_activity':activity,
                    'monster_wave_passes':sum(bool(op.event_count('monster_wave.completed'))
                        for op in operations if op.status is FlowStatus.COMPLETED)}),), error=error,
                failure=subordinate.failure if subordinate else None,
                final_snapshot=subordinate.final_snapshot if subordinate else None,
                termination=reason, operations=tuple(operations), resources=balances,
                physical_operation_may_be_active=active,
                stamina_consumed=self.stamina_consumed,remaining_stamina_budget=self.remaining_stamina_budget,
                stamina_prepared=self.stamina_prepared,stamina_consumption_pending=self._pending_manual,
                duration=duration,maximum_stamina_consumption=self.config.maximum_stamina_consumption)

        def _reader_diagnosis():
            diagnosis = getattr(self.reader, 'last_diagnosis', None)
            if isinstance(diagnosis, dict) and isinstance(diagnosis.get('summary'), str):
                return diagnosis['summary'][:200]
            return None

        def read(previous=None, *, post_claim=False):
            if self.cancel_requested():
                raise RuntimeWaitCancelled('Arena Farming Cycle cancelled')
            if post_claim:
                post_claim_read = getattr(self.reader, 'read_post_claim', None)
                value = post_claim_read() if callable(post_claim_read) else self.reader.read()
            else:
                value = self.reader.read()
            if self.cancel_requested():
                raise RuntimeWaitCancelled('Arena Farming Cycle cancelled')
            if (not isinstance(value, ArenaFarmingResources)
                    or not 0 <= self.clock() - value.observed_at <= 4.
                    or previous and (value.sequence <= previous.sequence or value.observed_at <= previous.observed_at)):
                if isinstance(value, ArenaFarmingResources):
                    if not 0 <= self.clock() - value.observed_at <= 4.:
                        self._last_resource_diagnosis = 'cycle_frame_not_fresh'
                    else:
                        self._last_resource_diagnosis = 'cycle_stale_or_pre_claim_reuse'
                else:
                    self._last_resource_diagnosis = _reader_diagnosis() or 'resource_refresh_unavailable'
                return None
            self._last_resource_diagnosis = None
            events.append(FlowEvent('arena.farming.resources', fields={
                'badges': value.badges, 'sapphires': value.sapphires, 'sequence': value.sequence}))
            return value

        if self._unsafe_to_restart and not self._pending_manual:
            return finish(FarmingTermination.SUBORDINATE_STOP,FlowStatus.MANUAL_RESOLUTION,
                subordinate=operations[-1] if operations else None,
                error='previous_operation_or_resource_refresh_unresolved')
        try:
            # An unresolved Stage must be reconciled before Lobby/resource reads
            # or any new economic action. Its owner alone can close that entry.
            if not self._pending_manual and not self._pending_supply:balances = read(balances)
            if balances is None:
                return finish(FarmingTermination.AMBIGUOUS, FlowStatus.MANUAL_RESOLUTION,
                    error=self._last_resource_diagnosis or 'initial resources ambiguous')
            for index in range(start_index,self.max_operations):
                if self.cancel_requested():
                    return finish(FarmingTermination.CANCELLED, FlowStatus.CANCELLED)
                activity = 'manual_stages' if self._pending_manual else self.activity(balances)
                events.append(FlowEvent('arena.farming.routing', fields={'activity': activity,
                    'resources_recoverable': activity != 'arena', 'operation_index': index + 1}))
                if activity == 'manual_stages' and self.manual_stages is None:
                    return finish(FarmingTermination.MANUAL_STAGES_NOT_IMPLEMENTED)
                if activity=='manual_stages' and not self._pending_manual:
                    remaining=self.remaining_stamina_budget
                    if remaining is not None and remaining<60:
                        return finish(FarmingTermination.STAMINA_BUDGET_REACHED)
                    # No purchases while Arena/MW are eligible. Claim and Trade
                    # belong to the existing Stages/Trading owners.
                    if hasattr(self.manual_stages,'prepare_stamina'):
                        required=(remaining//60)*60 if remaining is not None else 60
                        prepare=self._pending_supply or (not self.stamina_prepared if remaining is not None else
                            self.manual_stages.balances.read().stamina<60)
                        if prepare:
                            self._pending_supply=True
                            refreshed=False
                            def still_manual():
                                nonlocal balances,refreshed
                                # Passive post-Claim recovery: one extra fresh frame
                                # (4 vs 3), same gates, zero gameplay inputs, no
                                # reuse of pre-Claim balances, cancelable.
                                value=read(balances, post_claim=True)
                                if value is None:
                                    diagnosis = (self._last_resource_diagnosis
                                                 or 'post-claim resources ambiguous')
                                    raise ValueError(f'post-claim resources ambiguous: {diagnosis}'[:200])
                                balances=value;refreshed=True
                                return self.activity(balances)=='manual_stages'
                            supply=self.manual_stages.prepare_stamina(required,still_manual=still_manual)
                            self._pending_supply=False
                            if remaining is not None and supply.outcome!='routing_changed':self.stamina_prepared=True
                            events.append(FlowEvent('arena.farming.stamina_supply',fields={
                                'required':required,'purchased':supply.purchased,
                                'operation_index':index+1,'kcoin_cost':getattr(supply,'kcoin_cost',None),
                                'stamina':supply.balances.stamina,'covered':supply.covered,
                                'outcome':supply.outcome}))
                            if supply.outcome=='sapphire_capacity_full':
                                return finish(FarmingTermination.SAPPHIRE_CAPACITY_FULL)
                            if supply.purchased or not refreshed:still_manual()
                            activity=self.activity(balances)
                            if supply.balances.stamina<60 and activity=='manual_stages':
                                return finish(FarmingTermination.STAMINA_SUPPLY_UNAVAILABLE)
                role = 'requested' if activity == 'arena' else 'investment'
                with event_scope(activity_id=activity, attempt_index=index + 1, activity_role=role):
                    owner = (self.arena_factory(self.controller.difficulty) if activity == 'arena'
                             else self.monster_wave if activity == 'monster_wave' else self.manual_stages)
                    if self._pending_manual:
                        if not callable(getattr(owner,'resume',None)):
                            return finish(FarmingTermination.AMBIGUOUS,FlowStatus.MANUAL_RESOLUTION,
                                subordinate=operations[-1],error='manual_consumption_receipt_unresolved')
                        result=owner.resume()
                        operations.pop()  # Same physical entry, reconciled receipt.
                    else:
                        result = owner.run_resource_pass() if activity == 'monster_wave' else owner.run()
                operations.append(result)
                if activity=='manual_stages':
                    consumed=getattr(result,'stamina_consumed',None)
                    key=getattr(result,'entry_id',None) or ('operation',index)
                    self._pending_manual=(consumed is None or
                        bool(getattr(result,'entry_reconciliation_pending',False)) or
                        bool(getattr(result,'physical_operation_may_be_active',False)))
                    if consumed is not None and key not in self._credited_entries:
                        if type(consumed) is not int or consumed not in (0,60):
                            raise ValueError('manual stamina receipt invalid')
                        self.stamina_consumed+=consumed
                        if consumed:
                            self._credited_entries.add(key)
                            events.append(FlowEvent('arena.farming.manual_entry', fields={
                                'operation_index':index+1,'entry_id':key,'stamina_consumed':consumed}))
                    if not self._pending_manual:self._unsafe_to_restart=False
                    if result.status is FlowStatus.COMPLETED and consumed is None:
                        return finish(FarmingTermination.AMBIGUOUS,FlowStatus.MANUAL_RESOLUTION,
                            subordinate=result,error='manual_consumption_receipt_missing')
                events.extend(replace(event, fields={**event.fields, 'activity_id': activity,
                    'attempt_index': index + 1, 'activity_role': role}) for event in result.events)
                if result.status is not FlowStatus.COMPLETED:
                    reason = (FarmingTermination.CANCELLED if result.status is FlowStatus.CANCELLED
                        else FarmingTermination.TECHNICAL_FAILURE if result.status is FlowStatus.FAILED
                        else FarmingTermination.AMBIGUOUS if getattr(result, 'phase', None) == 'result_ambiguous'
                        else FarmingTermination.SUBORDINATE_STOP)
                    return finish(reason, result.status, result, result.error)
                if activity == 'manual_stages':
                    from bot.manual_stages import ManualStagesResult, ManualStageOutcome
                    if isinstance(result, ManualStagesResult) and result.outcome is ManualStageOutcome.STAMINA_INSUFFICIENT:
                        return finish(FarmingTermination.STAMINA_INSUFFICIENT,subordinate=result)
                    if isinstance(result, ManualStagesResult) and result.outcome is ManualStageOutcome.SAPPHIRE_CAPACITY_FULL:
                        return finish(FarmingTermination.SAPPHIRE_CAPACITY_FULL,subordinate=result)
                if self.cancel_requested():
                    return finish(FarmingTermination.CANCELLED, FlowStatus.CANCELLED, result)
                # Caller requests normal navigation only after an owner's verified success.
                self.ensure_lobby()
                after = read(balances)
                if after is None:
                    # An owner's terminal is known, but routing/progress is not.
                    # Preserve this execution; no fresh execution/reset/re-input.
                    self._unsafe_to_restart=True
                    return finish(FarmingTermination.AMBIGUOUS, FlowStatus.MANUAL_RESOLUTION, result,
                        error=self._last_resource_diagnosis or 'post-operation resources ambiguous')
                before, balances = balances, after
                if activity == 'manual_stages':
                    from bot.manual_stages import ManualStagesResult, ManualStageOutcome
                    if isinstance(result, ManualStagesResult) and result.outcome is ManualStageOutcome.DEFEATED:
                        return finish(FarmingTermination.MANUAL_STAGE_DEFEATED,subordinate=result)
                if activity == 'arena':
                    batch = getattr(result, 'batch_result', None)
                    if (getattr(result, 'mode', None) is not ArenaMode.AUTO_REPEAT or batch is None
                            or after.observed_at <= batch.observed_at):
                        return finish(FarmingTermination.AMBIGUOUS, FlowStatus.MANUAL_RESOLUTION, result,
                            error='Arena batch receipt missing or resources not observed after terminal')
                    try:
                        decision = self.controller.observe(batch)
                    except ValueError as error:
                        return finish(FarmingTermination.AMBIGUOUS, FlowStatus.MANUAL_RESOLUTION, result,
                            error=f'Arena controller rejected batch receipt: {error}')
                    events.append(FlowEvent('arena.farming.difficulty', fields={
                        'used_tickets': batch.used_tickets, 'won_tickets': batch.won_tickets,
                        'batch_id':batch.provenance.run_id,'operation_index':index+1,
                        'multiplier':batch.multiplier,
                        'duration':getattr(result,'metrics',{}).get('flow_wall_seconds'),
                        'difficulty': batch.difficulty.value, 'next': decision.difficulty.value,
                        'reason': decision.reason, 'productive': batch.won_tickets > 0}))
                    if decision.finish:
                        return finish(FarmingTermination.EASY_ZERO_WINS, subordinate=result)
                    zero_batches = zero_batches + 1 if batch.won_tickets == 0 else 0
                    # Finite exploration allowance: never buy endless samples yielding zero.
                    if zero_batches >= MAX_ZERO_YIELD_BATCHES:
                        return finish(FarmingTermination.NO_PROGRESS, subordinate=result)
                else:
                    # A verified terminal plus fresh resource gain establishes useful generation.
                    productive = (after.badges > before.badges if activity == 'monster_wave'
                                  else after.sapphires > before.sapphires)
                    if activity == 'monster_wave' and not result.event_count('monster_wave.completed'):
                        productive = False
                    if not productive:
                        return finish(FarmingTermination.NO_PRODUCTIVE_ROUTE if
                            result.event_count('manual_stages.no_productive_route') else FarmingTermination.NO_PROGRESS,
                            subordinate=result)
                    events.append(FlowEvent('arena.farming.progress', fields={'activity': activity,
                        'operation_index':index+1,
                        'badges_before': before.badges, 'badges_after': after.badges,
                        'sapphires_before': before.sapphires, 'sapphires_after': after.sapphires}))
            return finish(FarmingTermination.SAFETY_LIMIT)
        except RuntimeWaitCancelled:
            return finish(FarmingTermination.CANCELLED, FlowStatus.CANCELLED)
        except (ValueError,RuntimeWaitTimeout) as error:
            return finish(FarmingTermination.AMBIGUOUS,FlowStatus.MANUAL_RESOLUTION,
                error=str(error) or type(error).__name__)
        except Exception as error:
            return finish(FarmingTermination.TECHNICAL_FAILURE, FlowStatus.FAILED,
                          error=str(error) or type(error).__name__)
