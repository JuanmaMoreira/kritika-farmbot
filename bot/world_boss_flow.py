"""Productive single-character World Boss flow over semantic runtime APIs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.auto_battle import AutoBattleState, EnsureAutoBattleStatus
from bot.catalog import (
    LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
    MODE_COMBINE_FUSE,
    OVERLAY_WORLD_BOSS_RAID_COMPLETE,
    OVERLAY_WORLD_BOSS_SELECT_BOSS,
    POPUP_EQUIPMENT_INVENTORY_FULL,
    POPUP_WORLD_BOSS_PREVIOUS_REWARDS,
    POPUP_SOCKET_INVENTORY_FULL,
    SCREEN_BATTLE_MODE_SELECT,
    SCREEN_COMBINE,
    SCREEN_LOBBY,
    SCREEN_SOCKET,
    SCREEN_WORLD_BOSS,
    SCREEN_WORLD_BOSS_BATTLE,
    SEMANTIC_CONFIDENCE_THRESHOLD,
    STATUS_COMBINE_FUSE_AVAILABLE,
)
from bot.component_contracts import ComponentRequirement
from bot.controlled_wait import ControlledWait, ControlledWaitOutcome
from bot.event_log import EventSink
from bot.equipment_combine_relief import (
    EquipmentCombineReliefOutcome,
    EquipmentCombineReturnPlan,
)
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
    AcceptSocketInventoryFull,
    AcknowledgeWorldBossPreviousRewards,
    ContinueAfterWorldBossRaid,
    DismissWorldBossBagFull,
    ExitCombine,
    ExitSocket,
    OpenEquipmentCombine,
    OpenBattleModeSelect,
    OpenWorldBossSelector,
    RejectSocketInventoryFull,
    SelectAvailableWorldBoss,
    StartWorldBossBattle,
)
from bot.socket_inventory_relief import SocketReliefOutcome, SocketReturnPlan
from bot.state import ResolutionStatus
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionPolicy,
    VerifiedTransitionResult,
)


WORLD_BOSS_INSUFFICIENT_SAPPHIRES = "world_boss.insufficient_sapphires"
WORLD_BOSS_PREVIOUS_REWARDS = "world_boss.previous_rewards"
WORLD_BOSS_INVENTORY_FULL = "world_boss.inventory_full"
WORLD_BOSS_BAG_FULL = "world_boss.bag_full"


class WorldBossParticipationPolicy(str, Enum):
    ALWAYS_PARTICIPATE = "always_participate"


@dataclass(frozen=True)
class WorldBossWaitPolicy:
    """Passive timer wait followed by a bounded Raid Complete poll."""

    post_timer_margin: float = 5.0
    completion_poll_interval: float = 1.0
    completion_timeout: float = 25.0

    def __post_init__(self) -> None:
        for name in (
            "post_timer_margin",
            "completion_poll_interval",
            "completion_timeout",
        ):
            value = float(getattr(self, name))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)

    @property
    def post_timer_completion_margin(self) -> float:
        return self.post_timer_margin

    @property
    def bounded_completion_timeout(self) -> float:
        return self.completion_timeout


@dataclass(frozen=True)
class WorldBossFlowResult(FlowResult):
    sapphires: int | None = None
    previous_rewards: bool = False
    inventory_full: bool = False
    bag_full: bool = False
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


class _SocketRelief(Protocol):
    def run(self, return_plan, cancel_requested=None): ...


class _EquipmentCombineRelief(Protocol):
    def run(self, return_plan, cancel_requested=None): ...


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
        socket_relief: _SocketRelief,
        equipment_combine_relief: _EquipmentCombineRelief,
        cancel_requested: Callable[[], bool] = lambda: False,
        fact_timeout: float = 15.0,
        transition_timeout: float = 6.0,
        transition_grace_timeout: float = 2.0,
        transition_max_attempts: int = 2,
        stable_for: float = 0.25,
        entry_settle_for: float = 1.0,
        wait_policy: WorldBossWaitPolicy = WorldBossWaitPolicy(),
        initial_wait: ControlledWait | None = None,
        completion_wait: ControlledWait | None = None,
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
        if not callable(getattr(socket_relief, "run", None)):
            raise ValueError("socket_relief must provide run()")
        if not callable(getattr(equipment_combine_relief, "run", None)):
            raise ValueError("equipment_combine_relief must provide run()")
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
        self.socket_relief = socket_relief
        self.equipment_combine_relief = equipment_combine_relief
        self.events = events
        self.cancel_requested = cancel_requested
        self.fact_timeout = float(fact_timeout)
        self.stable_for = float(stable_for)
        self.entry_settle_for = float(entry_settle_for)
        self.wait_policy = wait_policy
        self.clock = clock
        self.initial_wait = initial_wait or ControlledWait(
            check_interval=1.0,
            clock=clock,
            events=events,
            label="world_boss.initial_wait",
        )
        self.completion_wait = completion_wait or ControlledWait(
            check_interval=wait_policy.completion_poll_interval,
            clock=clock,
            events=events,
            label="world_boss.completion_poll",
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
        socket_relief_attempted = False
        equipment_combine_relief_attempted = False
        while True:
            battle = self._transition(
                transitions,
                "world_boss.start",
                StartWorldBossBattle(),
                main,
                expected=lambda item: (
                    _is_clean_base(item, SCREEN_WORLD_BOSS_BATTLE)
                    or _is_world_boss_inventory_full(item)
                    or _is_world_boss_bag_full(item)
                ),
                precondition=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                retryable_from=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
            )
            if battle is None:
                return self._transition_failure(
                    transitions, sapphires, flow_events, previous_rewards
                )

            if _is_world_boss_inventory_full(battle):
                if socket_relief_attempted:
                    event = FlowEvent(WORLD_BOSS_INVENTORY_FULL)
                    flow_events.append(event)
                    self._record_best_effort(event.kind, branch="negative_after_relief")
                    returned = self._transition(
                        transitions,
                        "world_boss.reject_inventory_full",
                        RejectSocketInventoryFull(),
                        battle,
                        expected=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                        precondition=_is_world_boss_inventory_full,
                        retryable_from=_is_world_boss_inventory_full,
                    )
                    if returned is None:
                        return self._transition_failure(transitions, sapphires, flow_events, previous_rewards)
                    self._record_best_effort("world_boss.completed", postcondition=SCREEN_WORLD_BOSS)
                    return WorldBossFlowResult(
                        status=FlowStatus.COMPLETED,
                        events=tuple(flow_events),
                        sapphires=sapphires,
                        previous_rewards=previous_rewards,
                        inventory_full=True,
                        transition_outcomes=_transition_outcomes(transitions),
                        transition_attempts=_transition_attempts(transitions),
                    )

                socket = self._transition(
                    transitions,
                    "world_boss.accept_inventory_full",
                    AcceptSocketInventoryFull(),
                    battle,
                    expected=lambda item: _is_clean_base(item, SCREEN_SOCKET),
                    precondition=_is_world_boss_inventory_full,
                    retryable_from=_is_world_boss_inventory_full,
                    tolerated=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                )
                if socket is None:
                    return self._transition_failure(transitions, sapphires, flow_events, previous_rewards)
                socket_relief_attempted = True
                self._record_best_effort("world_boss.socket_relief.started", sequence=socket.sequence)
                relief = self.socket_relief.run(
                    SocketReturnPlan(ExitSocket(), SCREEN_WORLD_BOSS),
                    cancel_requested=self.cancel_requested,
                )
                self._record_best_effort(
                    "world_boss.socket_relief.finished",
                    outcome=relief.outcome.value,
                    enhance=relief.enhance.value,
                    sell=relief.sell.value,
                    animation_taps=relief.animation_taps,
                    error=relief.error,
                )
                if relief.outcome is SocketReliefOutcome.CANCELLED:
                    return self._cancelled(sapphires, flow_events, previous_rewards, transitions=transitions)
                if relief.outcome is SocketReliefOutcome.FAILED:
                    return self._failed(
                        f"socket_inventory_relief_failed: {relief.error or 'no detail'}",
                        sapphires=sapphires,
                        flow_events=flow_events,
                        previous_rewards=previous_rewards,
                        transitions=transitions,
                    )
                main = relief.final_snapshot
                if main is None or not _is_clean_base(main, SCREEN_WORLD_BOSS):
                    return self._failed(
                        "socket_inventory_relief_return_state_invalid",
                        sapphires=sapphires,
                        flow_events=flow_events,
                        previous_rewards=previous_rewards,
                        transitions=transitions,
                    )
                continue

            if _is_world_boss_bag_full(battle):
                if equipment_combine_relief_attempted:
                    event = FlowEvent(WORLD_BOSS_BAG_FULL)
                    flow_events.append(event)
                    self._record_best_effort(event.kind, branch="negative_after_relief")
                    returned = self._transition(
                        transitions,
                        "world_boss.dismiss_bag_full",
                        DismissWorldBossBagFull(),
                        battle,
                        expected=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                        precondition=_is_world_boss_bag_full,
                        retryable_from=_is_world_boss_bag_full,
                    )
                    if returned is None:
                        return self._transition_failure(transitions, sapphires, flow_events, previous_rewards)
                    self._record_best_effort("world_boss.completed", postcondition=SCREEN_WORLD_BOSS)
                    return WorldBossFlowResult(
                        status=FlowStatus.COMPLETED,
                        events=tuple(flow_events),
                        sapphires=sapphires,
                        previous_rewards=previous_rewards,
                        bag_full=True,
                        transition_outcomes=_transition_outcomes(transitions),
                        transition_attempts=_transition_attempts(transitions),
                    )

                combine = self._transition(
                    transitions,
                    "world_boss.open_equipment_combine",
                    OpenEquipmentCombine(),
                    battle,
                    expected=_is_stable_combine_entry,
                    precondition=_is_world_boss_bag_full,
                    retryable_from=_is_world_boss_bag_full,
                    tolerated=lambda item: _is_clean_base(item, SCREEN_WORLD_BOSS),
                )
                if combine is None:
                    return self._transition_failure(transitions, sapphires, flow_events, previous_rewards)
                equipment_combine_relief_attempted = True
                self._record_best_effort("world_boss.equipment_combine_relief.started", sequence=combine.sequence)
                relief = self.equipment_combine_relief.run(
                    EquipmentCombineReturnPlan(ExitCombine(), SCREEN_WORLD_BOSS),
                    cancel_requested=self.cancel_requested,
                )
                self._record_best_effort(
                    "world_boss.equipment_combine_relief.finished",
                    outcome=relief.outcome.value,
                    transmute=relief.transmute.value,
                    ethereal=relief.ethereal.value,
                    fuse=relief.fuse.value,
                    animation_taps=relief.animation_taps,
                    error=relief.error,
                )
                if relief.outcome is EquipmentCombineReliefOutcome.CANCELLED:
                    return self._cancelled(sapphires, flow_events, previous_rewards, transitions=transitions)
                if relief.outcome is EquipmentCombineReliefOutcome.FAILED:
                    return self._failed(
                        f"equipment_combine_relief_failed: {relief.error or 'no detail'}",
                        sapphires=sapphires,
                        flow_events=flow_events,
                        previous_rewards=previous_rewards,
                        transitions=transitions,
                    )
                main = relief.final_snapshot
                if main is None or not _is_clean_base(main, SCREEN_WORLD_BOSS):
                    return self._failed(
                        "equipment_combine_relief_return_state_invalid",
                        sapphires=sapphires,
                        flow_events=flow_events,
                        previous_rewards=previous_rewards,
                        transitions=transitions,
                    )
                continue

            break

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
            poll_count=wait_result.poll_count,
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
        tolerated=lambda _: False,
    ) -> RuntimeSnapshot | None:
        result = self.verified_transition.execute(
            name,
            action,
            before,
            expected=expected,
            precondition=precondition,
            retryable_from=retryable_from,
            abort_if=lambda item: _is_known_incompatible(
                item, expected, retryable_from, tolerated
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
        detected_at: float | None = None
        unknown_count = 0
        poll_index = 0
        raid_complete_max_confidence = 0.0
        started_at = self.clock()
        initial_wait_duration = float(timer) + self.wait_policy.post_timer_margin
        polling_started_at: float | None = None
        self._record_best_effort(
            "world_boss.wait.started",
            timer_initial=timer,
            initial_wait=initial_wait_duration,
            post_timer_margin=self.wait_policy.post_timer_margin,
            completion_poll_interval=self.wait_policy.completion_poll_interval,
            completion_timeout=self.wait_policy.completion_timeout,
        )

        def check() -> bool:
            nonlocal latest, detected_at, unknown_count
            nonlocal poll_index, raid_complete_max_confidence
            poll_index += 1
            latest = self.observer.observe()
            raid_complete = _is_raid_complete(latest)
            landmark = latest.observations.best(
                LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE
            )
            confidence = landmark.confidence if landmark is not None else 0.0
            raid_complete_max_confidence = max(
                raid_complete_max_confidence, confidence
            )
            self._record_best_effort(
                "world_boss.wait.poll",
                poll_index=poll_index,
                sequence=latest.frame.sequence,
                resolution_status=latest.state.status.value,
                base_state=(
                    latest.state.base_context or latest.state.status.value
                ),
                overlays=latest.state.overlays,
                raid_complete_detected=raid_complete,
                raid_complete_confidence=confidence,
                semantic_confidence_threshold=SEMANTIC_CONFIDENCE_THRESHOLD,
            )
            if raid_complete:
                if detected_at is None:
                    detected_at = self.clock()
                return True
            if latest.state.status is ResolutionStatus.UNKNOWN:
                unknown_count += 1
            return False

        initial = self.initial_wait.wait(
            expected_duration=initial_wait_duration,
            cancel_requested=self.cancel_requested,
        )
        if initial.outcome is not ControlledWaitOutcome.COMPLETED:
            self._record_wait_finished(
                timer,
                initial_wait_duration,
                polling_started_at,
                detected_at,
                initial,
                unknown_count,
                latest,
                raid_complete_max_confidence,
            )
            return initial, latest

        polling_started_at = self.clock()
        self._record_best_effort(
            "world_boss.wait.polling_started",
            timer_initial=timer,
            polling_started_at=polling_started_at,
            elapsed=polling_started_at - started_at,
            completion_poll_interval=self.wait_policy.completion_poll_interval,
            completion_timeout=self.wait_policy.completion_timeout,
        )
        completion = self.completion_wait.wait(
            expected_duration=self.wait_policy.completion_timeout,
            completion_condition=check,
            cancel_requested=self.cancel_requested,
        )
        combined = _combined_wait(
            completion,
            initial.elapsed + completion.elapsed,
            completion.poll_count,
        )
        self._record_wait_finished(
            timer,
            initial_wait_duration,
            polling_started_at,
            detected_at,
            combined,
            unknown_count,
            latest,
            raid_complete_max_confidence,
        )
        return combined, latest

    def _record_wait_finished(
        self,
        timer,
        initial_wait_duration,
        polling_started_at,
        detected_at,
        result,
        unknown_count,
        latest,
        raid_complete_max_confidence,
    ):
        self._record_best_effort(
            "world_boss.wait.finished",
            timer_initial=timer,
            initial_wait=initial_wait_duration,
            post_timer_margin=self.wait_policy.post_timer_margin,
            polling_started_at=polling_started_at,
            completion_poll_interval=self.wait_policy.completion_poll_interval,
            completion_timeout=self.wait_policy.completion_timeout,
            raid_complete_detected_at=detected_at,
            actual_elapsed=result.elapsed,
            poll_count=result.poll_count,
            unknown_count=unknown_count,
            last_base_state=(
                latest.state.base_context or latest.state.status.value
                if latest is not None
                else None
            ),
            last_overlays=(latest.state.overlays if latest is not None else ()),
            last_sequence=(latest.frame.sequence if latest is not None else None),
            raid_complete_max_confidence=raid_complete_max_confidence,
            semantic_confidence_threshold=SEMANTIC_CONFIDENCE_THRESHOLD,
            outcome=result.outcome.value,
        )

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
    return OVERLAY_WORLD_BOSS_RAID_COMPLETE in snapshot.state.overlays


def _is_world_boss_inventory_full(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_WORLD_BOSS
        and set(snapshot.state.overlays) == {POPUP_SOCKET_INVENTORY_FULL}
    )


def _is_world_boss_bag_full(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_WORLD_BOSS
        and set(snapshot.state.overlays) == {POPUP_EQUIPMENT_INVENTORY_FULL}
    )


def _is_stable_combine_entry(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_COMBINE
        and set(snapshot.state.overlays)
        in (
            {MODE_COMBINE_FUSE},
            {MODE_COMBINE_FUSE, STATUS_COMBINE_FUSE_AVAILABLE},
        )
    )


def _is_known_incompatible(
    snapshot, expected, retryable_from, tolerated=lambda _: False
) -> bool:
    if expected(snapshot) or retryable_from(snapshot) or tolerated(snapshot):
        return False
    return snapshot.state.status in {
        ResolutionStatus.RESOLVED,
        ResolutionStatus.AMBIGUOUS,
    }


__all__ = (
    "WORLD_BOSS_INSUFFICIENT_SAPPHIRES",
    "WORLD_BOSS_PREVIOUS_REWARDS",
    "WORLD_BOSS_INVENTORY_FULL",
    "WORLD_BOSS_BAG_FULL",
    "WorldBossFlow",
    "WorldBossFlowResult",
    "WorldBossParticipationPolicy",
    "WorldBossWaitPolicy",
)
