"""Productive single-character World Boss flow over semantic runtime APIs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.auto_battle import AutoBattleState, EnsureAutoBattleStatus
from bot.catalog import (
    OVERLAY_WORLD_BOSS_RAID_COMPLETE,
    OVERLAY_WORLD_BOSS_SELECT_BOSS,
    POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
    POPUP_WORLD_BOSS_INVENTORY_FULL,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_LOBBY,
    SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE,
)
from bot.component_contracts import ComponentRequirement
from bot.controlled_wait import ControlledWait, ControlledWaitOutcome
from bot.event_log import EventSink
from bot.flow_contracts import (
    FlowContract,
    FlowEvent,
    FlowResult,
    FlowScope,
    FlowStatus,
)
from bot.runtime_facts import FactReadStatus
from bot.runtime_observer import RuntimeObserver, RuntimeSnapshot
from bot.semantic_actions import (
    AcknowledgeWorldBossPreviousRewards,
    ContinueAfterWorldBossRaid,
    OpenBattleModeSelect,
    OpenWorldBossSelector,
    SelectAvailableWorldBoss,
    StartWorldBossBattle,
    RejectWorldBossInventoryFull,
)
from bot.state import ResolutionStatus
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionPolicy,
    VerifiedTransitionResult,
)


WORLD_BOSS_INSUFFICIENT_SAPPHIRES = "world_boss.insufficient_sapphires"
WORLD_BOSS_PREVIOUS_REWARDS = "world_boss.previous_rewards"
WORLD_BOSS_INVENTORY_FULL = "world_boss.inventory_full"


class WorldBossParticipationPolicy(str, Enum):
    ALWAYS_PARTICIPATE = "always_participate"


@dataclass(frozen=True)
class WorldBossWaitPolicy:
    """Sparse early observation followed by an active bounded final window."""

    active_window: float = 12.0
    final_margin: float = 15.0
    early_check_interval: float = 8.0
    final_check_interval: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "active_window",
            "final_margin",
            "early_check_interval",
            "final_check_interval",
        ):
            value = float(getattr(self, name))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class WorldBossFlowResult(FlowResult):
    sapphires: int | None = None
    previous_rewards: bool = False
    inventory_full: bool = False
    auto_battle_initial: AutoBattleState | None = None
    auto_battle_taps: int = 0
    initial_timer: int | None = None
    wait_elapsed: float = 0.0
    wait_checks: int = 0
    raid_complete_detected: bool = False
    transition_outcomes: tuple[tuple[str, str], ...] = ()
    transition_attempts: tuple[tuple[str, int, int], ...] = ()


class _FactReader(Protocol):
    def read_sapphires(self, **kwargs): ...

    def read_timer_remaining(self, **kwargs): ...


class _AutoBattleEnsurer(Protocol):
    def ensure_on(self, *, after_sequence: int, cancel_requested=None): ...


class _RaidStateError(RuntimeError):
    pass


class WorldBossFlow:
    """Attempt exactly one World Boss participation, starting at Lobby."""

    name = "world_boss"
    scope = FlowScope.PER_CHARACTER
    participation_policy = WorldBossParticipationPolicy.ALWAYS_PARTICIPATE
    contract = FlowContract(
        precondition=ComponentRequirement.exact_state(SCREEN_LOBBY),
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
            ComponentRequirement.exact_state(SCREEN_WORLD_BOSS),
        ),
    )

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        facts: _FactReader,
        auto_battle: _AutoBattleEnsurer,
        events: EventSink,
        *,
        cancel_requested: Callable[[], bool] = lambda: False,
        fact_timeout: float = 15.0,
        transition_timeout: float = 6.0,
        transition_grace_timeout: float = 2.0,
        transition_max_attempts: int = 2,
        stable_for: float = 0.25,
        entry_settle_for: float = 1.0,
        wait_policy: WorldBossWaitPolicy = WorldBossWaitPolicy(),
        early_wait: ControlledWait | None = None,
        final_wait: ControlledWait | None = None,
        clock: Callable[[], float] = time.monotonic,
        verified_transition: VerifiedTransition | None = None,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(facts, "read_sapphires", None)) or not callable(
            getattr(facts, "read_timer_remaining", None)
        ):
            raise ValueError("facts must provide typed runtime fact reads")
        if not callable(getattr(auto_battle, "ensure_on", None)):
            raise ValueError("auto_battle must provide ensure_on()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if (
            fact_timeout <= 0
            or transition_timeout <= 0
            or stable_for < 0
            or entry_settle_for < 0
        ):
            raise ValueError("timeouts must be positive and stability non-negative")
        self.observer = observer
        self.actions = actions
        self.facts = facts
        self.auto_battle = auto_battle
        self.events = events
        self.cancel_requested = cancel_requested
        self.fact_timeout = float(fact_timeout)
        self.stable_for = float(stable_for)
        self.entry_settle_for = float(entry_settle_for)
        self.wait_policy = wait_policy
        self.clock = clock
        self.early_wait = early_wait or ControlledWait(
            check_interval=wait_policy.early_check_interval,
            clock=clock,
        )
        self.final_wait = final_wait or ControlledWait(
            check_interval=wait_policy.final_check_interval,
            clock=clock,
        )
        self.transition_policy = VerifiedTransitionPolicy(
            normal_timeout=transition_timeout,
            grace_timeout=transition_grace_timeout,
            max_attempts=transition_max_attempts,
        )
        self.verified_transition = verified_transition or VerifiedTransition(
            observer, actions
        )

    def run(self) -> WorldBossFlowResult:
        try:
            return self._run()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(f"{type(error).__name__}: {error}")

    def _run(self) -> WorldBossFlowResult:
        # Deliberately the first runtime operation: no observation or input precedes it.
        sapphire_read = self.facts.read_sapphires(
            after_sequence=0,
            timeout=self.fact_timeout,
            cancel_requested=self.cancel_requested,
        )
        if sapphire_read.status is FactReadStatus.CANCELLED:
            return WorldBossFlowResult(status=FlowStatus.CANCELLED)
        if sapphire_read.status is not FactReadStatus.CONFIRMED:
            return self._failed(
                f"sapphires_fact_failed: {sapphire_read.status.value}: "
                f"{sapphire_read.detail or 'no detail'}"
            )
        sapphire_fact = sapphire_read.fact
        assert sapphire_fact is not None
        sapphires = sapphire_fact.value
        self._record_best_effort("world_boss.sapphires_read", value=sapphires)
        if sapphires < 5:
            event = FlowEvent(WORLD_BOSS_INSUFFICIENT_SAPPHIRES)
            self._record_best_effort(event.kind, sapphires=sapphires)
            return WorldBossFlowResult(
                status=FlowStatus.COMPLETED,
                events=(event,),
                sapphires=sapphires,
            )

        transitions: list[VerifiedTransitionResult] = []
        lobby = self.observer.wait_until(
            lambda item: _is_clean_base(item, SCREEN_LOBBY),
            after_sequence=sapphire_fact.sequence,
            timeout=self.fact_timeout,
            stable_for=self.stable_for,
        )
        battle_modes = self._transition(
            transitions,
            "world_boss.open_battle_mode_select",
            OpenBattleModeSelect(),
            lobby,
            expected=lambda item: _is_clean_base(item, SCREEN_BATTLE_MODE_SELECT),
            precondition=lambda item: _is_clean_base(item, SCREEN_LOBBY),
            retryable_from=lambda item: _is_clean_base(item, SCREEN_LOBBY),
        )
        if battle_modes is None:
            return self._transition_failure(transitions, sapphires)

        selector = self._transition(
            transitions,
            "world_boss.open_selector",
            OpenWorldBossSelector(),
            battle_modes,
            expected=_is_select_boss,
            precondition=lambda item: _is_clean_base(item, SCREEN_BATTLE_MODE_SELECT),
            retryable_from=lambda item: _is_clean_base(item, SCREEN_BATTLE_MODE_SELECT),
        )
        if selector is None:
            return self._transition_failure(transitions, sapphires)

        entered = self._transition(
            transitions,
            "world_boss.select_available",
            SelectAvailableWorldBoss(),
            selector,
            expected=lambda item: _is_previous_rewards(item)
            or _is_clean_base(item, SCREEN_WORLD_BOSS),
            precondition=_is_select_boss,
            retryable_from=_is_select_boss,
        )
        if entered is None:
            return self._transition_failure(transitions, sapphires)

        flow_events: list[FlowEvent] = []
        if not _is_previous_rewards(entered):
            # The World Boss base can resolve briefly before Previous Rewards is
            # presented.  Treat both as outcomes of selecting the boss and wait
            # for that entry branch to settle before Start is eligible.
            entered = self.observer.wait_until(
                lambda item: _is_previous_rewards(item)
                or _is_clean_base(item, SCREEN_WORLD_BOSS),
                after_sequence=entered.sequence,
                timeout=self.fact_timeout,
                stable_for=self.entry_settle_for,
                cancel_requested=self.cancel_requested,
            )

        previous_rewards = _is_previous_rewards(entered)
        if previous_rewards:
            event = FlowEvent(WORLD_BOSS_PREVIOUS_REWARDS)
            flow_events.append(event)
            self._record_best_effort(event.kind)
            entered = self._transition(
                transitions,
                "world_boss.ack_previous_rewards",
                AcknowledgeWorldBossPreviousRewards(),
                entered,
                expected=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                precondition=_is_previous_rewards,
                retryable_from=_is_previous_rewards,
            )
            if entered is None:
                return self._transition_failure(
                    transitions, sapphires, flow_events, previous_rewards=True
                )

        if previous_rewards:
            main = self.observer.wait_until(
                lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                after_sequence=entered.sequence,
                timeout=self.fact_timeout,
                stable_for=self.stable_for,
                cancel_requested=self.cancel_requested,
            )
        else:
            main = entered
        battle = self._transition(
            transitions,
            "world_boss.start",
            StartWorldBossBattle(),
            main,
            expected=lambda item: (
                _is_clean_base(item, SCREEN_WORLD_BOSS_BATTLE)
                or _is_world_boss_inventory_full(item)
            ),
            precondition=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
            retryable_from=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
        )
        if battle is None:
            return self._transition_failure(
                transitions, sapphires, flow_events, previous_rewards
            )

        if _is_world_boss_inventory_full(battle):
            event = FlowEvent(WORLD_BOSS_INVENTORY_FULL)
            flow_events.append(event)
            self._record_best_effort(event.kind)
            returned = self._transition(
                transitions,
                "world_boss.reject_inventory_full",
                RejectWorldBossInventoryFull(),
                battle,
                expected=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                precondition=_is_world_boss_inventory_full,
                retryable_from=_is_world_boss_inventory_full,
            )
            if returned is None:
                return self._transition_failure(
                    transitions, sapphires, flow_events, previous_rewards
                )
            self._record_best_effort(
                "world_boss.completed", postcondition=SCREEN_WORLD_BOSS
            )
            return WorldBossFlowResult(
                status=FlowStatus.COMPLETED,
                events=tuple(flow_events),
                sapphires=sapphires,
                previous_rewards=previous_rewards,
                inventory_full=True,
                transition_outcomes=_transition_outcomes(transitions),
                transition_attempts=_transition_attempts(transitions),
            )

        ensured = self.auto_battle.ensure_on(
            after_sequence=battle.sequence,
            cancel_requested=self.cancel_requested,
        )
        initial_auto = (
            ensured.observations[0].value if ensured.observations else None
        )
        self._record_best_effort(
            "world_boss.auto_battle",
            initial=(initial_auto.value if initial_auto else None),
            taps=ensured.tap_count,
            status=ensured.status.value,
        )
        if ensured.status is EnsureAutoBattleStatus.CANCELLED:
            return self._cancelled(
                sapphires, flow_events, previous_rewards, initial_auto,
                ensured.tap_count, transitions,
            )
        if ensured.status is not EnsureAutoBattleStatus.SUCCESS:
            return self._failed(
                f"auto_battle_failed: {ensured.status.value}: "
                f"{ensured.detail or 'no detail'}",
                sapphires=sapphires,
                flow_events=flow_events,
                previous_rewards=previous_rewards,
                auto_battle_initial=initial_auto,
                auto_battle_taps=ensured.tap_count,
                transitions=transitions,
            )

        timer_after = (
            ensured.observations[-1].sequence
            if ensured.observations
            else battle.sequence
        )
        timer_read = self.facts.read_timer_remaining(
            after_sequence=timer_after,
            timeout=self.fact_timeout,
            cancel_requested=self.cancel_requested,
        )
        if timer_read.status is FactReadStatus.CANCELLED:
            return self._cancelled(
                sapphires, flow_events, previous_rewards, initial_auto,
                ensured.tap_count, transitions,
            )
        if timer_read.status is not FactReadStatus.CONFIRMED:
            return self._failed(
                f"timer_fact_failed: {timer_read.status.value}: "
                f"{timer_read.detail or 'no detail'}",
                sapphires=sapphires,
                flow_events=flow_events,
                previous_rewards=previous_rewards,
                auto_battle_initial=initial_auto,
                auto_battle_taps=ensured.tap_count,
                transitions=transitions,
            )
        timer_fact = timer_read.fact
        assert timer_fact is not None
        timer = timer_fact.value
        self._record_best_effort("world_boss.timer_read", seconds=timer)

        wait_result, raid = self._wait_for_raid_complete(timer)
        self._record_best_effort(
            "world_boss.controlled_wait",
            outcome=wait_result.outcome.value,
            elapsed=wait_result.elapsed,
            checks=wait_result.poll_count,
        )
        common = dict(
            sapphires=sapphires,
            flow_events=flow_events,
            previous_rewards=previous_rewards,
            auto_battle_initial=initial_auto,
            auto_battle_taps=ensured.tap_count,
            initial_timer=timer,
            wait_elapsed=wait_result.elapsed,
            wait_checks=wait_result.poll_count,
            transitions=transitions,
        )
        if wait_result.outcome is ControlledWaitOutcome.CANCELLED:
            return self._cancelled(**common)
        if wait_result.outcome is not ControlledWaitOutcome.COMPLETED or raid is None:
            return self._failed(
                f"raid_complete_wait_{wait_result.outcome.value}: "
                f"{wait_result.error or 'overlay not observed'}",
                **common,
            )

        returned = self._transition(
            transitions,
            "world_boss.continue_after_raid",
            ContinueAfterWorldBossRaid(),
            raid,
            expected=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
            precondition=_is_raid_complete,
            retryable_from=_is_raid_complete,
        )
        if returned is None:
            return self._transition_failure(
                transitions,
                sapphires,
                flow_events,
                previous_rewards,
                initial_auto,
                ensured.tap_count,
                timer,
                wait_result.elapsed,
                wait_result.poll_count,
                True,
            )
        self._record_best_effort("world_boss.completed", postcondition=SCREEN_WORLD_BOSS)
        return WorldBossFlowResult(
            status=FlowStatus.COMPLETED,
            events=tuple(flow_events),
            sapphires=sapphires,
            previous_rewards=previous_rewards,
            auto_battle_initial=initial_auto,
            auto_battle_taps=ensured.tap_count,
            initial_timer=timer,
            wait_elapsed=wait_result.elapsed,
            wait_checks=wait_result.poll_count,
            raid_complete_detected=True,
            transition_outcomes=_transition_outcomes(transitions),
            transition_attempts=_transition_attempts(transitions),
        )

    def _transition(
        self,
        transitions: list[VerifiedTransitionResult],
        name: str,
        action,
        before: RuntimeSnapshot,
        *,
        expected,
        precondition,
        retryable_from,
    ) -> RuntimeSnapshot | None:
        result = self.verified_transition.execute(
            name,
            action,
            before,
            expected=expected,
            precondition=precondition,
            retryable_from=retryable_from,
            abort_if=lambda item: _is_known_incompatible(
                item, expected, retryable_from
            ),
            stable_for=self.stable_for,
            policy=self.transition_policy,
        )
        transitions.append(result)
        self._record_best_effort(
            "world_boss.transition",
            name=name,
            outcome=result.outcome.value,
            attempts=result.attempt_count,
            grace=result.grace_wait_count,
        )
        return result.final_snapshot if result.succeeded else None

    def _wait_for_raid_complete(self, timer: int):
        latest: RuntimeSnapshot | None = None

        def check() -> bool:
            nonlocal latest
            latest = self.observer.observe()
            if _is_raid_complete(latest):
                return True
            if not _is_clean_base(latest, SCREEN_WORLD_BOSS_BATTLE):
                raise _RaidStateError(
                    f"unexpected battle state: {latest.state.status.value} "
                    f"{latest.state.base_context} {latest.state.overlays}"
                )
            return False

        early_duration = max(0.0, float(timer) - self.wait_policy.active_window)
        elapsed = 0.0
        polls = 0
        if early_duration > 0:
            early = self.early_wait.wait(
                expected_duration=early_duration,
                completion_condition=check,
                cancel_requested=self.cancel_requested,
            )
            elapsed += early.elapsed
            polls += early.poll_count
            if early.outcome is not ControlledWaitOutcome.TIMEOUT:
                return _combined_wait(early, elapsed, polls), latest

        final_duration = min(float(timer), self.wait_policy.active_window)
        final_duration += self.wait_policy.final_margin
        final = self.final_wait.wait(
            expected_duration=final_duration,
            completion_condition=check,
            cancel_requested=self.cancel_requested,
        )
        elapsed += final.elapsed
        polls += final.poll_count
        return _combined_wait(final, elapsed, polls), latest

    def _transition_failure(
        self,
        transitions,
        sapphires,
        flow_events=(),
        previous_rewards=False,
        auto_battle_initial=None,
        auto_battle_taps=0,
        initial_timer=None,
        wait_elapsed=0.0,
        wait_checks=0,
        raid_complete_detected=False,
    ):
        last = transitions[-1]
        return self._failed(
            f"{last.name}_failed: {last.outcome.value}: {last.error or 'no detail'}",
            sapphires=sapphires,
            flow_events=flow_events,
            previous_rewards=previous_rewards,
            auto_battle_initial=auto_battle_initial,
            auto_battle_taps=auto_battle_taps,
            initial_timer=initial_timer,
            wait_elapsed=wait_elapsed,
            wait_checks=wait_checks,
            raid_complete_detected=raid_complete_detected,
            transitions=transitions,
        )

    def _cancelled(self, sapphires=None, flow_events=(), previous_rewards=False,
                   auto_battle_initial=None, auto_battle_taps=0,
                   transitions=(), initial_timer=None, wait_elapsed=0.0,
                   wait_checks=0, **_):
        return WorldBossFlowResult(
            status=FlowStatus.CANCELLED,
            events=tuple(flow_events),
            sapphires=sapphires,
            previous_rewards=previous_rewards,
            auto_battle_initial=auto_battle_initial,
            auto_battle_taps=auto_battle_taps,
            initial_timer=initial_timer,
            wait_elapsed=wait_elapsed,
            wait_checks=wait_checks,
            transition_outcomes=_transition_outcomes(transitions),
            transition_attempts=_transition_attempts(transitions),
        )

    def _failed(self, error, *, sapphires=None, flow_events=(),
                previous_rewards=False, auto_battle_initial=None,
                auto_battle_taps=0, initial_timer=None, wait_elapsed=0.0,
                wait_checks=0, raid_complete_detected=False, transitions=()):
        return WorldBossFlowResult(
            status=FlowStatus.FAILED,
            events=tuple(flow_events),
            error=error,
            sapphires=sapphires,
            previous_rewards=previous_rewards,
            auto_battle_initial=auto_battle_initial,
            auto_battle_taps=auto_battle_taps,
            initial_timer=initial_timer,
            wait_elapsed=wait_elapsed,
            wait_checks=wait_checks,
            raid_complete_detected=raid_complete_detected,
            transition_outcomes=_transition_outcomes(transitions),
            transition_attempts=_transition_attempts(transitions),
        )

    def _record_best_effort(self, event: str, **fields) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass


def _combined_wait(result, elapsed, polls):
    from bot.controlled_wait import ControlledWaitResult

    return ControlledWaitResult(result.outcome, elapsed, polls, result.error)


def _transition_outcomes(transitions):
    return tuple((item.name, item.outcome.value) for item in transitions)


def _transition_attempts(transitions):
    return tuple(
        (item.name, item.attempt_count, item.grace_wait_count)
        for item in transitions
    )


def _is_clean_base(snapshot: RuntimeSnapshot, context: str) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == context
        and not snapshot.state.overlays
    )


def _has_only_overlay(snapshot: RuntimeSnapshot, overlay: str) -> bool:
    return set(snapshot.state.overlays) == {overlay}


def _is_select_boss(snapshot: RuntimeSnapshot) -> bool:
    return _has_only_overlay(snapshot, OVERLAY_WORLD_BOSS_SELECT_BOSS)


def _is_previous_rewards(snapshot: RuntimeSnapshot) -> bool:
    return _has_only_overlay(snapshot, POPUP_WORLD_BOSS_PREVIOUS_REWARDS)


def _is_raid_complete(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_WORLD_BOSS_BATTLE
        and set(snapshot.state.overlays) == {OVERLAY_WORLD_BOSS_RAID_COMPLETE}
    )


def _is_world_boss_inventory_full(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_WORLD_BOSS
        and set(snapshot.state.overlays) == {POPUP_WORLD_BOSS_INVENTORY_FULL}
    )


def _is_known_incompatible(snapshot, expected, retryable_from) -> bool:
    if expected(snapshot) or retryable_from(snapshot):
        return False
    return snapshot.state.status in {
        ResolutionStatus.RESOLVED,
        ResolutionStatus.AMBIGUOUS,
    }


__all__ = (
    "WORLD_BOSS_INSUFFICIENT_SAPPHIRES",
    "WORLD_BOSS_PREVIOUS_REWARDS",
    "WORLD_BOSS_INVENTORY_FULL",
    "WorldBossFlow",
    "WorldBossFlowResult",
    "WorldBossParticipationPolicy",
    "WorldBossWaitPolicy",
)
