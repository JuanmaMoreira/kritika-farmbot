"""Standalone Lobby -> Lobby wrapper for the same prepared MW activity."""
from dataclasses import replace
from functools import partial
from bot.battle_mode_zone import BattleModeZone
from bot.catalog import SCREEN_LOBBY
from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowContract, FlowScope
from bot.monster_wave_activity import MonsterWaveActivity, MonsterWaveResult
from bot.prepared_activity import PreparedActivity


class MonsterWaveFlow:
    name = 'monster_wave'
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(ComponentRequirement.exact_state(SCREEN_LOBBY),
                            (ComponentRequirement.exact_state(SCREEN_LOBBY),))

    def __init__(self, *args, **kwargs):
        self.activity = MonsterWaveActivity(*args, **kwargs)
        self.zone = BattleModeZone(self.activity.observer, self.activity.verified_transition,
                                   cancel_requested=self.activity.cancel_requested)

    def prepared(self, zone, *, daily=False):
        return PreparedActivity(self.name, zone, partial(self.activity.run, daily_sapphires=daily))

    def run(self):
        entered = self.zone.enter()
        if not entered.succeeded:
            return MonsterWaveResult(entered.status, error=entered.error, failure=entered.failure,
                transition_outcomes=entered.transition_outcomes, transition_attempts=entered.transition_attempts)
        result = self.activity.run()
        result = replace(result, transition_outcomes=entered.transition_outcomes+result.transition_outcomes,
                         transition_attempts=entered.transition_attempts+result.transition_attempts)
        if not result.succeeded:
            return result
        closed = self.zone.leave()
        return replace(result, status=closed.status, error=closed.error, failure=closed.failure,
            transition_outcomes=result.transition_outcomes+closed.transition_outcomes,
            transition_attempts=result.transition_attempts+closed.transition_attempts)
