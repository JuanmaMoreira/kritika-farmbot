"""Standalone Lobby composition of the reusable World Boss activity."""

from dataclasses import replace

from bot.battle_mode_zone import BattleModeZone, is_lobby, is_battle_mode_select
from bot.catalog import SCREEN_LOBBY, SCREEN_BATTLE_MODE_SELECT
from bot.component_contracts import ComponentRequirement
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowContract, FlowEvent, FlowScope, FlowStatus
from bot.prepared_activity import PreparedActivity
from bot.runtime_facts import FactReadStatus
from bot.runtime_observer import RuntimeWaitCancelled
from bot.world_boss_activity import (
    WORLD_BOSS_BAG_FULL, WORLD_BOSS_INSUFFICIENT_SAPPHIRES,
    WORLD_BOSS_INVENTORY_FULL, WORLD_BOSS_METEOR_FULL, WORLD_BOSS_PREVIOUS_REWARDS,
    WorldBossActivity, WorldBossFlowResult, WorldBossParticipationPolicy, WorldBossWaitPolicy,
)


class WorldBossFlow:
    name = "world_boss"
    scope = FlowScope.PER_CHARACTER
    participation_policy = WorldBossParticipationPolicy.ALWAYS_PARTICIPATE
    contract = FlowContract(
        ComponentRequirement.exact_state(SCREEN_LOBBY),
        (ComponentRequirement.exact_state(SCREEN_LOBBY),),
    )

    def __init__(self, *args, **kwargs):
        lobby_transition = kwargs.pop("lobby_transition", None)
        self.eligibility_policy = kwargs.pop('eligibility_policy', None)
        self.activity = WorldBossActivity(*args, **kwargs)
        self.activity.eligibility_policy = self.eligibility_policy
        self.zone = BattleModeZone(
            self.activity.observer, self.activity.verified_transition,
            lobby_transition=lobby_transition,
            cancel_requested=self.activity.cancel_requested,
        )
        # Diagnostic observation, consumed once; never a running resource balance.
        self._sapphires_hint = None

    def precheck(self, *, context=None):
        """Read Lobby resources; the caller decides when a terminal result applies.

        Standalone consumes it immediately. Daily holds it until after Eligibility;
        creating a candidate result here neither publishes events nor blocks a zone.
        """
        self._sapphires_hint = None
        no_work = self.routing_no_work()
        if no_work is not None:
            return no_work
        try:
            if self.activity.cancel_requested():
                return WorldBossFlowResult(FlowStatus.CANCELLED)
            read = self.activity.facts.read_sapphires(
                **({'context': context} if context is not None else {}),
                after_sequence=0, timeout=self.activity.fact_timeout,
                cancel_requested=self.activity.cancel_requested,
            )
            if read.status is FactReadStatus.CANCELLED:
                return WorldBossFlowResult(FlowStatus.CANCELLED)
            if (read.status is not FactReadStatus.CONFIRMED or read.fact is None
                    or (context is not None and read.fact.context != context)):
                return WorldBossFlowResult(FlowStatus.FAILED, error=(
                    f"sapphires_fact_failed: {read.status.value}: {read.detail or 'no detail'}"))
            value = read.fact.value
            self.activity._record_best_effort("world_boss.sapphires_read", value=value)
            if value < 5:
                return WorldBossFlowResult(FlowStatus.COMPLETED, sapphires=value, events=(
                    FlowEvent(WORLD_BOSS_INSUFFICIENT_SAPPHIRES, fields=dict(sapphires=value)),))
            self._sapphires_hint = value
            return None
        except RuntimeWaitCancelled:
            return WorldBossFlowResult(FlowStatus.CANCELLED)
        except Exception as error:
            return WorldBossFlowResult(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                                       failure=FailureCause.from_error(error, kind="exception"))

    def run_activity(self):
        sapphires, self._sapphires_hint = self._sapphires_hint, None
        return self.activity.run(sapphires=sapphires)

    def prepared_precheck(self):
        """Same >=5 readiness at the verified selected entry, including shared hub."""
        no_work = self.routing_no_work()
        if no_work is not None:
            return no_work
        before = self.activity.observer.observe()
        if is_lobby(before):
            return self.precheck(context=SCREEN_LOBBY)
        if is_battle_mode_select(before):
            return self.precheck(context=SCREEN_BATTLE_MODE_SELECT)
        self._sapphires_hint = None
        return WorldBossFlowResult(FlowStatus.FAILED, error='world_boss_readiness_entry_unconfirmed')

    def prepared(self, zone):
        return PreparedActivity(self.name, zone, self.run_activity, self.prepared_precheck,
                                routing_no_work=self.routing_no_work)

    def routing_no_work(self):
        policy = getattr(self,'eligibility_policy',None)
        reason = policy.known_no_work() if policy else None
        if reason:
            return WorldBossFlowResult(FlowStatus.COMPLETED, events=(
                FlowEvent('world_boss.current_cycle_no_work', fields={'reason':reason}),))
        return None

    def run(self):
        result = self.precheck()
        if result is not None:
            return result
        entered = self.zone.enter()
        if not entered.succeeded:
            self._sapphires_hint = None
            return WorldBossFlowResult(entered.status, error=entered.error, failure=entered.failure,
                transition_outcomes=entered.transition_outcomes,
                transition_attempts=entered.transition_attempts)
        result = self.run_activity()
        result = replace(result,
                         transition_outcomes=entered.transition_outcomes + result.transition_outcomes,
                         transition_attempts=entered.transition_attempts + result.transition_attempts)
        if not result.succeeded:
            return result
        closed = self.zone.leave()
        result = replace(result,
                         transition_outcomes=result.transition_outcomes + closed.transition_outcomes,
                         transition_attempts=result.transition_attempts + closed.transition_attempts)
        if not closed.succeeded:
            return replace(result, status=closed.status, error=closed.error, failure=closed.failure)
        return result
