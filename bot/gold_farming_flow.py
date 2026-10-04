"""User-selected economic capability; no planning of unrelated activities."""
from dataclasses import replace
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.event_context import event_scope
from bot.event_log import record_best_effort
from bot.stages_daily_flow import StagesDailyFlow
from bot.session import controlled_unavailable
from bot.runtime_observer import RuntimeWaitCancelled

class GoldFarmingFlow:
    name = "gold_farming"
    scope = StagesDailyFlow.scope
    contract = StagesDailyFlow.contract

    def __init__(self, stages, monster_wave, *, ensure_lobby, events=None,
                 cancel_requested=lambda: False, continue_on_unavailable=True):
        self.stages, self.monster_wave = stages, monster_wave
        self.ensure_lobby, self.events = ensure_lobby, events
        self.cancel_requested = cancel_requested
        self.continue_on_unavailable = continue_on_unavailable

    def run(self):
        events = []
        try:
            for attempt in (1, 2):
                if self.cancel_requested():
                    return FlowResult(FlowStatus.CANCELLED, tuple(events))
                with event_scope(attempt_index=attempt, activity_id="stages_daily", activity_role="requested"):
                    stage = self.stages.run()
                    allowed = frozenset({"stages_daily.ads_unavailable"}) if self.continue_on_unavailable else frozenset()
                    continuable = stage.succeeded or controlled_unavailable(stage, allowed)
                    events.extend(self._attributed(stage.events, attempt, "requested", "stages_daily"))
                    record_best_effort(self.events, "gold_farming.activity.result",
                        result=stage.status.value, decision="continue" if continuable else "stop")
                    if not continuable:
                        return replace(stage, events=tuple(events))
                    self.ensure_lobby()
                exhausted = stage.event_count("stages_daily.ads_exhausted") > 0
                recovery_exhausted = controlled_unavailable(stage, allowed)
                role = "final_investment" if exhausted or recovery_exhausted or attempt == 2 else "investment"
                with event_scope(attempt_index=attempt, activity_id="monster_wave", activity_role=role):
                    if self.cancel_requested():
                        return FlowResult(FlowStatus.CANCELLED, tuple(events))
                    invested = self.monster_wave.run()
                    events.extend(self._attributed(invested.events, attempt, role, "monster_wave"))
                    record_best_effort(self.events, "gold_farming.activity.result",
                        result=invested.status.value, decision="continue" if invested.succeeded else "stop")
                    if not invested.succeeded:
                        return replace(invested, events=tuple(events))
                    self.ensure_lobby()
                if exhausted or recovery_exhausted:
                    if attempt == 1:
                        skipped = FlowEvent("gold_farming.attempt.skipped", fields={
                            "attempt_index": 2, "activity_id": "stages_daily",
                            "activity_role": "requested", "reason": "daily_ads_exhausted" if exhausted else "ads_recovery_exhausted"})
                        events.append(skipped)
                        record_best_effort(self.events, skipped.kind, **skipped.fields)
                    break
            events.append(FlowEvent("gold_farming.completed"))
            return FlowResult(FlowStatus.COMPLETED, tuple(events))
        except RuntimeWaitCancelled:
            return FlowResult(FlowStatus.CANCELLED, tuple(events))
        except Exception as error:
            return FlowResult(FlowStatus.FAILED, tuple(events), error=str(error) or type(error).__name__)

    @staticmethod
    def _attributed(events, attempt, role, activity):
        return tuple(replace(event, fields={**event.fields, "attempt_index": attempt,
            "activity_id": activity, "activity_role": role}) for event in events)
