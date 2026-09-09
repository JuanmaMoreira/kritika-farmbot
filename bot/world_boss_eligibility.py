"""Daily routine eligibility from the acquired World Boss card badge."""

from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT, STATUS_WORLD_BOSS_DAILY_ACTIVE,
)
from bot.eligibility import EligibilityResult, EligibilityStatus
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.state import ResolutionStatus
from bot.monster_wave_semantics import STATUS_MONSTER_WAVE_DAILY_ACTIVE


def world_boss_daily_status(snapshot) -> EligibilityStatus:
    state = snapshot.state
    if (state.status is not ResolutionStatus.RESOLVED
            or state.base_context != SCREEN_BATTLE_MODE_SELECT
            or not set(state.overlays) <= {STATUS_WORLD_BOSS_DAILY_ACTIVE, STATUS_MONSTER_WAVE_DAILY_ACTIVE}):
        return EligibilityStatus.UNKNOWN
    return (EligibilityStatus.ELIGIBLE if STATUS_WORLD_BOSS_DAILY_ACTIVE in state.overlays
            else EligibilityStatus.NOT_ELIGIBLE)


class WorldBossDailyEligibility:
    """Observe a prepared hub; all navigation belongs to the zone owner.

    Decisions remain valid for this selected position in the current visit.
    No resource reads, gameplay, cleanup input or cross-visit caching.
    """

    def __init__(self, observer, *, cancel_requested):
        self.observer = observer
        self.cancel_requested = cancel_requested

    def evaluate(self) -> EligibilityResult:
        try:
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            initial = self.observer.observe()
            candidate = EligibilityStatus.UNKNOWN

            def consistent_badge(item):
                nonlocal candidate
                current = world_boss_daily_status(item)
                consistent = current is candidate and current is not EligibilityStatus.UNKNOWN
                candidate = current
                return consistent

            observed = self.observer.wait_until(
                consistent_badge, after_sequence=initial.sequence,
                timeout=6.0, stable_for=0.75,
                cancel_requested=self.cancel_requested,
            )
            decision = world_boss_daily_status(observed)
            if decision is EligibilityStatus.UNKNOWN:
                return EligibilityResult(EligibilityStatus.UNKNOWN, "world_boss_daily_unconfirmed")
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            return EligibilityResult(
                decision,
                "World Boss Daily indicator active" if decision is EligibilityStatus.ELIGIBLE
                else "World Boss Daily indicator absent",
            )
        except RuntimeWaitCancelled:
            return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
        except RuntimeWaitTimeout as error:
            snapshot = error.last_snapshot
            return EligibilityResult(
                EligibilityStatus.UNKNOWN, "world_boss_daily_unconfirmed",
                FailureCause.from_error(error, kind="eligibility_unknown",
                                       sequence=snapshot.sequence if snapshot else None),
            )
        except Exception as error:
            return EligibilityResult(
                EligibilityStatus.FAILED, "world_boss_daily_evaluation_failed",
                FailureCause.from_error(error, kind="exception"),
            )
