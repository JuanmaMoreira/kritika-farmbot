"""MW gameplay wrapper; the caller owns navigation after completion."""
from dataclasses import replace
from functools import partial
from bot.battle_mode_zone import BattleModeZone
from bot.catalog import SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowContract, FlowEvent, FlowScope, FlowStatus
from bot.runtime_facts import FactReadStatus
from bot.ocr_extractors import RESOURCE_SAPPHIRES
from bot.runtime_observer import RuntimeWaitCancelled
from bot.event_log import record_best_effort
from bot.monster_wave_activity import MonsterWaveActivity, MonsterWaveResult
from bot.prepared_activity import PreparedActivity
from bot.sapphire_pressure import sapphire_pressure_passes


class MonsterWaveFlow:
    name = 'monster_wave'
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(ComponentRequirement.exact_state(SCREEN_LOBBY),
                            tuple(ComponentRequirement.exact_state(s) for s in
                                  (SCREEN_MONSTER_WAVE, SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY)))

    def __init__(self, *args, **kwargs):
        lobby_transition = kwargs.pop('lobby_transition', None)
        self.activity = MonsterWaveActivity(*args, **kwargs)
        self.zone = BattleModeZone(self.activity.observer, self.activity.verified_transition,
                                   lobby_transition=lobby_transition,
                                   cancel_requested=self.activity.cancel_requested)

    def entry_readiness(self, *, pressure_relief=False):
        """Fresh Lobby readiness terminates before navigation; never a balance cache."""
        a=self.activity
        try:
            if a.cancel_requested():return MonsterWaveResult(FlowStatus.CANCELLED)
            initial=a.observer.observe()
            read=a.facts.read_sapphires(context=SCREEN_LOBBY,after_sequence=initial.sequence,
                timeout=6,cancel_requested=a.cancel_requested)
            if a.cancel_requested() or read.status is FactReadStatus.CANCELLED:
                return MonsterWaveResult(FlowStatus.CANCELLED)
            fact=read.fact
            if (read.status is not FactReadStatus.CONFIRMED or fact is None or
                fact.name != RESOURCE_SAPPHIRES or fact.context != SCREEN_LOBBY or
                type(fact.value) is not int or fact.value<0 or not fact.evidence or
                any(e.sequence<=initial.sequence for e in fact.evidence) or
                not 0 <= a.clock()-fact.timestamp <= 2.):
                raise ValueError('fresh Lobby sapphires unavailable')
            no_work = sapphire_pressure_passes(fact.value) == 0 if pressure_relief else fact.value == 0
            record_best_effort(a.events,'monster_wave.entry_readiness',sapphires=fact.value,
                source_sequence=fact.sequence,decision='no_work' if no_work else 'enter')
            if no_work:
                return MonsterWaveResult(FlowStatus.COMPLETED,sapphires_initial=fact.value,
                    events=(FlowEvent('monster_wave.no_work',fields={'sapphires':fact.value,'navigation':False}),))
            return None
        except RuntimeWaitCancelled:return MonsterWaveResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveResult(FlowStatus.FAILED,error=str(error) or type(error).__name__)

    def prepared(self, zone, *, yield_resource_board=False):
        return PreparedActivity(self.name, zone, partial(
            self.activity.run,
            yield_resource_board=yield_resource_board, keep_current=True),
            entry_readiness=self.entry_readiness, exit_postconditions=self.contract.successful_postconditions)

    def run(self, *, yield_resource_board=False):
        ready=self.entry_readiness()
        if ready is not None:return ready
        entered = self.zone.enter()
        if not entered.succeeded:
            return MonsterWaveResult(entered.status, error=entered.error, failure=entered.failure,
                transition_outcomes=entered.transition_outcomes, transition_attempts=entered.transition_attempts)
        result = self.activity.run(yield_resource_board=yield_resource_board, keep_current=True)
        result = replace(result, transition_outcomes=entered.transition_outcomes+result.transition_outcomes,
                         transition_attempts=entered.transition_attempts+result.transition_attempts)
        if not result.succeeded:
            return result
        return result

    def run_resource_pass(self):
        """One ordinary verified pass, without a Gold Farming pressure target."""
        return self.run()
