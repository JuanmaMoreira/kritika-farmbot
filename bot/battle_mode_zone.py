"""Navigation-only ownership of one Battle Mode visit."""

from dataclasses import dataclass
from bot.catalog import (
    MENU_QUICK, SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
)
from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowResult, FlowStatus
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import OpenBattleModeSelect, OpenQuickMenu, SelectQuickMenuLobby
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionPolicy


def is_battle_mode_select(snapshot):
    state = snapshot.state
    return (state.status is ResolutionStatus.RESOLVED
            and state.base_context == SCREEN_BATTLE_MODE_SELECT
            and set(state.overlays) <= {STATUS_WORLD_BOSS_DAILY_ACTIVE})


def is_lobby(snapshot):
    return (snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_LOBBY
            and not snapshot.state.overlays)


def _quick_menu(snapshot):
    return (snapshot.state.status in {ResolutionStatus.RESOLVED, ResolutionStatus.UNKNOWN}
            and set(snapshot.state.overlays) == {MENU_QUICK})


@dataclass(frozen=True)
class BattleModeZoneResult(FlowResult):
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


class BattleModeZone:
    """No activity selection, Daily policy, resource facts or relief decisions."""

    entry_requirement = ComponentRequirement.exact_state(SCREEN_LOBBY)
    hub_requirement = ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT)

    def __init__(self, observer, transition, *, cancel_requested=lambda: False):
        self.observer = observer
        self.transition = transition
        self.cancel_requested = cancel_requested

    def enter(self):
        return self._navigate(False)

    def leave(self):
        return self._navigate(True)

    def _navigate(self, leaving):
        transitions = []

        def finish(status, **kwargs):
            return BattleModeZoneResult(
                status, **kwargs,
                transition_outcomes=tuple((r.name, r.outcome.value) for r in transitions),
                transition_attempts=tuple((r.name, r.attempt_count, r.grace_wait_count)
                                          for r in transitions),
            )

        try:
            if self.cancel_requested():
                return finish(FlowStatus.CANCELLED)
            origin = is_battle_mode_select if leaving else is_lobby
            before = self.observer.wait_until(
                origin, after_sequence=0, timeout=6.0, stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            steps = (
                (("open_quick_menu", OpenQuickMenu(), origin, _quick_menu),
                 ("select_lobby", SelectQuickMenuLobby(), _quick_menu, is_lobby))
                if leaving else
                (("open_battle_mode_select", OpenBattleModeSelect(), origin, is_battle_mode_select),)
            )
            for name, action, guard, expected in steps:
                if self.cancel_requested():
                    return finish(FlowStatus.CANCELLED)
                result = self.transition.execute(
                    f"battle_mode.{name}", action, before,
                    expected=expected, precondition=guard, retryable_from=guard,
                    stable_for=0.25, policy=VerifiedTransitionPolicy(max_attempts=2),
                )
                transitions.append(result)
                if self.cancel_requested():
                    return finish(FlowStatus.CANCELLED)
                if not result.succeeded:
                    return finish(FlowStatus.FAILED,
                                  error=f"{result.name}_failed: {result.outcome.value}: {result.error}",
                                  failure=result.failure)
                before = result.final_snapshot
                if not expected(before):
                    return finish(FlowStatus.FAILED, error="zone_postcondition_failed")
            return finish(FlowStatus.COMPLETED)
        except RuntimeWaitCancelled:
            return finish(FlowStatus.CANCELLED)
        except Exception as error:
            return finish(FlowStatus.FAILED, error=str(error) or type(error).__name__,
                          failure=FailureCause.from_error(error, kind="exception"))
