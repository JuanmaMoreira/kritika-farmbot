"""Daily MW badge check on a prepared Battle Mode hub; manual runs omit it."""
from bot.battle_mode_zone import is_battle_mode_select
from bot.eligibility import EligibilityResult, EligibilityStatus
from bot.failure_cause import FailureCause
from bot.monster_wave_semantics import STATUS_MONSTER_WAVE_DAILY_ACTIVE
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout


def monster_wave_daily_status(snapshot):
    if not is_battle_mode_select(snapshot):
        return EligibilityStatus.UNKNOWN
    return (EligibilityStatus.ELIGIBLE if STATUS_MONSTER_WAVE_DAILY_ACTIVE in snapshot.state.overlays
            else EligibilityStatus.NOT_ELIGIBLE)


class MonsterWaveDailyEligibility:
    def __init__(self, observer, *, cancel_requested):
        self.observer, self.cancel_requested = observer, cancel_requested

    def evaluate(self):
        try:
            if self.cancel_requested():
                raise RuntimeWaitCancelled()
            initial = self.observer.observe()
            candidate = EligibilityStatus.UNKNOWN

            def consistent_badge(snapshot):
                nonlocal candidate
                current = monster_wave_daily_status(snapshot)
                consistent = current is candidate and current is not EligibilityStatus.UNKNOWN
                candidate = current
                return consistent

            observed = self.observer.wait_until(consistent_badge,
                after_sequence=initial.sequence, timeout=6, stable_for=.75,
                cancel_requested=self.cancel_requested)
            if self.cancel_requested():
                raise RuntimeWaitCancelled()
            decision = monster_wave_daily_status(observed)
            return EligibilityResult(decision, 'Monster Wave Daily indicator active'
                if decision is EligibilityStatus.ELIGIBLE else 'Monster Wave Daily indicator absent')
        except RuntimeWaitCancelled:
            return EligibilityResult(EligibilityStatus.CANCELLED, 'eligibility_cancelled')
        except RuntimeWaitTimeout as error:
            return EligibilityResult(EligibilityStatus.UNKNOWN, 'monster_wave_daily_unconfirmed',
                FailureCause.from_error(error, kind='eligibility_unknown',
                    sequence=error.last_snapshot.sequence if error.last_snapshot else None))
        except Exception as error:
            return EligibilityResult(EligibilityStatus.FAILED, 'monster_wave_daily_evaluation_failed',
                FailureCause.from_error(error, kind='exception'))
