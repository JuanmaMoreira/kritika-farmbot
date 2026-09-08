"""Daily routine eligibility from the acquired World Boss card badge."""

from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, STATUS_WORLD_BOSS_DAILY_ACTIVE,
)
from bot.eligibility import EligibilityResult, EligibilityStatus
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.semantic_actions import OpenBattleModeSelect
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionPolicy


def world_boss_daily_status(snapshot) -> EligibilityStatus:
    state = snapshot.state
    if (state.status is not ResolutionStatus.RESOLVED
            or state.base_context != SCREEN_BATTLE_MODE_SELECT
            or not set(state.overlays) <= {STATUS_WORLD_BOSS_DAILY_ACTIVE}):
        return EligibilityStatus.UNKNOWN
    return (EligibilityStatus.ELIGIBLE if STATUS_WORLD_BOSS_DAILY_ACTIVE in state.overlays
            else EligibilityStatus.NOT_ELIGIBLE)


def _lobby(snapshot):
    return (snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_LOBBY
            and not snapshot.state.overlays)


class WorldBossDailyEligibility:
    """Read the badge, restore Lobby, then hand control back to the routine.

    No sapphires, selector, rewards, Start or gameplay calls. The acquired
    return operation is injected; inconclusive reads never invoke that return.
    """

    def __init__(self, observer, transition, return_to_lobby, *, cancel_requested):
        self.observer = observer
        self.transition = transition
        self.return_to_lobby = return_to_lobby
        self.cancel_requested = cancel_requested

    def evaluate(self) -> EligibilityResult:
        try:
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            lobby = self.observer.wait_until(
                _lobby, after_sequence=0, timeout=6.0, stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            opened = self.transition.execute(
                "eligibility.world_boss.open_battle_mode_select",
                OpenBattleModeSelect(), lobby,
                expected=lambda item: world_boss_daily_status(item) is not EligibilityStatus.UNKNOWN,
                precondition=_lobby, retryable_from=_lobby,
                stable_for=0.25,
                policy=VerifiedTransitionPolicy(max_attempts=2),
            )
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            if not opened.succeeded:
                return EligibilityResult(
                    EligibilityStatus.FAILED, opened.error or "eligibility_navigation_failed",
                    opened.failure,
                )
            candidate = EligibilityStatus.UNKNOWN

            def consistent_badge(item):
                nonlocal candidate
                current = world_boss_daily_status(item)
                consistent = current is candidate and current is not EligibilityStatus.UNKNOWN
                candidate = current
                return consistent

            observed = self.observer.wait_until(
                consistent_badge, after_sequence=opened.final_snapshot.sequence,
                timeout=6.0, stable_for=0.75,
                cancel_requested=self.cancel_requested,
            )
            decision = world_boss_daily_status(observed)
            if decision is EligibilityStatus.UNKNOWN:
                return EligibilityResult(EligibilityStatus.UNKNOWN, "world_boss_daily_unconfirmed")
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            returned = self.return_to_lobby(observed)
            if self.cancel_requested():
                return EligibilityResult(EligibilityStatus.CANCELLED, "eligibility_cancelled")
            if not returned.succeeded:
                return EligibilityResult(
                    EligibilityStatus.FAILED, returned.error or "eligibility_return_failed",
                    returned.failure,
                )
            if not _lobby(returned.final_snapshot):
                return EligibilityResult(EligibilityStatus.FAILED, "eligibility_return_postcondition_failed")
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
