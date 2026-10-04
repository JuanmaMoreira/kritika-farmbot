"""Navigation-only ownership of one Battle Mode visit."""

from dataclasses import dataclass
from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
)
from bot.component_contracts import ComponentRequirement
from bot.flow_contracts import FlowResult, FlowStatus
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeWaitCancelled
from bot.semantic_actions import OpenBattleModeSelect, ExitBattleModeSelect
from bot.state import ResolutionStatus
from bot.verified_transition import VerifiedTransitionPolicy
from bot.monster_wave_semantics import STATUS_MONSTER_WAVE_DAILY_ACTIVE


def is_battle_mode_select(snapshot):
    state = snapshot.state
    return (state.status is ResolutionStatus.RESOLVED
            and state.base_context == SCREEN_BATTLE_MODE_SELECT
            and set(state.overlays) <= {STATUS_WORLD_BOSS_DAILY_ACTIVE, STATUS_MONSTER_WAVE_DAILY_ACTIVE})


def is_lobby(snapshot):
    return (snapshot.state.status is ResolutionStatus.RESOLVED
            and snapshot.state.base_context == SCREEN_LOBBY
            and not snapshot.state.overlays)


@dataclass(frozen=True)
class BattleModeZoneResult(FlowResult):
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


class BattleModeZone:
    """No activity selection, Daily policy, resource facts or relief decisions."""

    entry_requirement = ComponentRequirement.exact_state(SCREEN_LOBBY)
    hub_requirement = ComponentRequirement.exact_state(SCREEN_BATTLE_MODE_SELECT)

    def __init__(
        self,
        observer,
        transition,
        *,
        lobby_transition=None,
        cancel_requested=lambda: False,
    ):
        self.observer = observer
        self.transition = transition
        self.lobby_transition = transition if lobby_transition is None else lobby_transition
        self.cancel_requested = cancel_requested

    def enter(self):
        return self._navigate(False)

    def ensure_hub(self):
        """Reach the shared hub from a fresh known source, preserving Back guards."""
        from bot.monster_wave_activity import clean_mw
        from bot.monster_wave_actions import ExitMonsterWave
        if self.cancel_requested():
            return BattleModeZoneResult(FlowStatus.CANCELLED)
        try:
            before = self.observer.observe()
            if is_battle_mode_select(before):
                return BattleModeZoneResult(FlowStatus.COMPLETED)
            if clean_mw(before):
                exited = self.transition.execute(
                    'battle_mode.exit_monster_wave', ExitMonsterWave(), before,
                    precondition=clean_mw, retryable_from=clean_mw,
                    expected=lambda s: is_battle_mode_select(s) or is_lobby(s),
                    abort_if=lambda s: s.state.status is ResolutionStatus.AMBIGUOUS
                    or (s.state.status is ResolutionStatus.RESOLVED and not clean_mw(s)
                        and not is_battle_mode_select(s) and not is_lobby(s)),
                    stable_for=.25, policy=VerifiedTransitionPolicy(max_attempts=1),
                )
                if self.cancel_requested():
                    return BattleModeZoneResult(FlowStatus.CANCELLED)
                if not exited.succeeded:
                    return BattleModeZoneResult(FlowStatus.FAILED, error=exited.error or 'mw_handoff_failed', failure=exited.failure)
                if is_battle_mode_select(exited.final_snapshot):
                    return BattleModeZoneResult(FlowStatus.COMPLETED)
                if not is_lobby(exited.final_snapshot):
                    return BattleModeZoneResult(FlowStatus.FAILED, error='mw_handoff_surface_unconfirmed')
            elif not is_lobby(before):
                return BattleModeZoneResult(FlowStatus.FAILED, error='battle_mode_entry_surface_unknown')
            return self._navigate(False)
        except RuntimeWaitCancelled:
            return BattleModeZoneResult(FlowStatus.CANCELLED)
        except Exception as error:
            return BattleModeZoneResult(FlowStatus.FAILED, error=str(error) or type(error).__name__)

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
            # A standalone MW exit may already have reached the final Lobby.
            # Recognize that clean terminal destination before any zone input.
            before = self.observer.wait_until(
                (lambda s: origin(s) or is_lobby(s)) if leaving else origin, after_sequence=0, timeout=6.0, stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if leaving and is_lobby(before):
                return finish(FlowStatus.COMPLETED)
            steps = (
                (("back_to_lobby", ExitBattleModeSelect(), origin, is_lobby),)
                if leaving else
                (("open_battle_mode_select", OpenBattleModeSelect(), origin, is_battle_mode_select),)
            )
            for name, action, guard, expected in steps:
                if self.cancel_requested():
                    return finish(FlowStatus.CANCELLED)
                extra = {}
                if leaving:
                    extra['abort_if'] = lambda item: (
                        item.state.status is ResolutionStatus.AMBIGUOUS
                        or (item.state.status is ResolutionStatus.RESOLVED
                            and not is_battle_mode_select(item) and not is_lobby(item)))
                executor = self.lobby_transition if leaving else self.transition
                result = executor.execute(
                    f"battle_mode.{name}", action, before,
                    expected=expected, precondition=guard, retryable_from=guard,
                    stable_for=0.25, policy=VerifiedTransitionPolicy(max_attempts=1 if leaving else 2),
                    **extra,
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
