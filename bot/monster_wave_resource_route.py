"""Execute one supplied resource prerequisite plan around a Monster Wave anchor.

This is the J boundary.  It does not plan, replan, execute Monster Wave battle
work, or route generically.  Craft and the single grouped Trading block are
serialized through the one physically verified Monster Wave anchor because
Quick Menu preserves only its immediate origin.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from numbers import Integral
import time

from bot.craft_operation import CraftOutcome
from bot.craft_policy import CraftQuantityMode, CraftRequest
from bot.craft_runtime import CraftRouteOutcome
from bot.craft_semantics import CraftFamily, CraftTier
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.keys_promotion_runtime import GoldCapacityRecoveryNavigation
from bot.monster_wave_activity import clean_mw, skip_state
from bot.monster_wave_board_snapshot import (
    BoardPopup,
    MonsterWaveBoardSnapshot,
    build_monster_wave_board_snapshot,
)
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.quick_menu import (
    QuickMenuHandoff,
    quick_menu_matches_origin,
    select_quick_menu_craft_action,
    select_quick_menu_trading_action,
    select_quick_menu_treasure_action,
)
from bot.resource_route_planner import (
    CraftStep,
    KeysPromotionStep,
    ResourceRoutePlan,
    ResourceRouteStatus,
    ResourceRouteStep,
    TradingMaterialsStep,
    TradingSessionStep,
)
from bot.runtime_observer import RuntimeSnapshot, RuntimeWaitCancelled
from bot.semantic_actions import CloseTrading, ExitTreasure, OpenQuickMenu
from bot.trading_center import clean_trading
from bot.treasure_center import clean_treasure
from bot.verified_transition import VerifiedTransitionPolicy


@dataclass(frozen=True)
class FreshMonsterWaveSnapshot:
    """One clean MW runtime frame and its same-frame descriptive snapshot."""

    context: RuntimeSnapshot
    snapshot: MonsterWaveBoardSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.context, RuntimeSnapshot):
            raise ValueError("context must be RuntimeSnapshot")
        if not isinstance(self.snapshot, MonsterWaveBoardSnapshot):
            raise ValueError("snapshot must be MonsterWaveBoardSnapshot")
        if not clean_mw(self.context) or skip_state(self.context) is None:
            raise ValueError("context must be a clean actionable Monster Wave frame")
        if self.snapshot.evidence.sequence != self.context.sequence:
            raise ValueError("snapshot must belong to context.sequence")
        if self.snapshot.board_popup is not BoardPopup.ABSENT:
            raise ValueError("Monster Wave anchor must not retain the board popup")


@dataclass(frozen=True)
class MonsterWaveSnapshotResult(FlowResult):
    fresh: FreshMonsterWaveSnapshot | None = None


class MonsterWaveSnapshotRuntime:
    """Read-only reacquisition of a fresh clean MW anchor snapshot."""

    def __init__(
        self,
        observer,
        *,
        cancel_requested=lambda: False,
        clock=time.monotonic,
        timeout: float = 6.0,
    ) -> None:
        if not callable(getattr(observer, "wait_until", None)):
            raise ValueError("observer must provide wait_until()")
        if not callable(cancel_requested) or not callable(clock):
            raise ValueError("runtime callbacks must be callable")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.observer = observer
        self.cancel_requested = cancel_requested
        self.clock = clock
        self.timeout = float(timeout)

    def acquire(self, *, after_sequence: int) -> MonsterWaveSnapshotResult:
        if (
            isinstance(after_sequence, bool)
            or not isinstance(after_sequence, Integral)
            or int(after_sequence) < 0
        ):
            raise ValueError("after_sequence must be non-negative")
        try:
            if self.cancel_requested():
                return MonsterWaveSnapshotResult(FlowStatus.CANCELLED)
            context = self.observer.wait_until(
                lambda item: clean_mw(item) and skip_state(item) is not None,
                after_sequence=int(after_sequence),
                timeout=self.timeout,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return MonsterWaveSnapshotResult(FlowStatus.CANCELLED)
            snapshot = build_monster_wave_board_snapshot(
                context,
                after_sequence=int(after_sequence),
                now=self.clock(),
            )
            if snapshot is None:
                return MonsterWaveSnapshotResult(
                    FlowStatus.FAILED,
                    error="fresh_monster_wave_snapshot_unavailable",
                )
            return MonsterWaveSnapshotResult(
                FlowStatus.COMPLETED,
                fresh=FreshMonsterWaveSnapshot(context, snapshot),
            )
        except RuntimeWaitCancelled:
            return MonsterWaveSnapshotResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveSnapshotResult(
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
                failure=FailureCause.from_error(error, kind="exception"),
            )


@dataclass(frozen=True)
class MonsterWaveNavigationResult(FlowResult):
    final_snapshot: RuntimeSnapshot | None = None
    after_sequence: int | None = None
    capability_result: object | None = None
    transition_outcomes: tuple[tuple[str, str], ...] = ()


def _single_attempt_policy() -> VerifiedTransitionPolicy:
    return VerifiedTransitionPolicy(
        normal_timeout=6.0,
        grace_timeout=2.0,
        retry_guard_timeout=0.0,
        max_attempts=1,
    )


class MonsterWavePrerequisiteNavigationRuntime:
    """Only the HIL-verified MW prerequisite hops; not a route graph."""

    def __init__(
        self,
        observer,
        transition,
        craft_runtime,
        *,
        cancel_requested=lambda: False,
    ) -> None:
        if not callable(getattr(observer, "wait_until", None)):
            raise ValueError("observer must provide wait_until()")
        if not callable(getattr(transition, "execute", None)):
            raise ValueError("transition must provide execute()")
        for name in ("enter_from_verified_quick_menu", "request_back_to_origin"):
            if not callable(getattr(craft_runtime, name, None)):
                raise ValueError(f"craft_runtime must provide {name}()")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.observer = observer
        self.transition = transition
        self.craft_runtime = craft_runtime
        self.cancel_requested = cancel_requested

    def enter_trading_from_mw(
        self, anchor: FreshMonsterWaveSnapshot
    ) -> MonsterWaveNavigationResult:
        return self._enter_from_mw(
            anchor,
            name="trading",
            action_factory=select_quick_menu_trading_action,
            expected=clean_trading,
        )

    def enter_treasure_from_mw(
        self, anchor: FreshMonsterWaveSnapshot
    ) -> MonsterWaveNavigationResult:
        return self._enter_from_mw(
            anchor,
            name="treasure",
            action_factory=select_quick_menu_treasure_action,
            expected=clean_treasure,
        )

    def enter_craft_from_mw(
        self,
        anchor: FreshMonsterWaveSnapshot,
        *,
        entry_capacity_proven: bool,
    ) -> MonsterWaveNavigationResult:
        transitions, handoff, failed = self._open_mw_menu(anchor)
        if failed is not None:
            return failed
        assert handoff is not None
        try:
            select_quick_menu_craft_action(handoff.origin)
            entered = self.craft_runtime.enter_from_verified_quick_menu(
                handoff,
                entry_capacity_proven=entry_capacity_proven,
            )
            if entered.outcome is CraftRouteOutcome.CANCELLED:
                return self._finish(transitions, FlowStatus.CANCELLED, entered)
            if entered.outcome is not CraftRouteOutcome.ENTERED:
                return self._finish(
                    transitions,
                    FlowStatus.FAILED,
                    entered,
                    error=f"craft_enter_failed:{entered.reason}",
                )
            return self._finish(transitions, FlowStatus.COMPLETED, entered)
        except Exception as error:
            return self._finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
            )

    def leave_trading_to_mw(self) -> MonsterWaveNavigationResult:
        return self._leave_to_mw(
            name="trading",
            action=CloseTrading(),
            precondition=clean_trading,
        )

    def leave_treasure_to_mw(self) -> MonsterWaveNavigationResult:
        return self._leave_to_mw(
            name="treasure",
            action=ExitTreasure(),
            precondition=clean_treasure,
        )

    def _enter_from_mw(self, anchor, *, name, action_factory, expected):
        transitions, handoff, failed = self._open_mw_menu(anchor)
        if failed is not None:
            return failed
        assert handoff is not None
        try:
            if self.cancel_requested():
                return self._finish(transitions, FlowStatus.CANCELLED)
            menu = transitions[-1].final_snapshot
            selected = self.transition.execute(
                f"monster_wave.prerequisite.select_{name}",
                action_factory(handoff.origin),
                menu,
                expected=expected,
                precondition=handoff.allows,
                retryable_from=None,
                on_recovery=handoff.invalidate,
                abort_if=lambda item: handoff.observe(item, expected),
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(selected)
            final = selected.final_snapshot
            if self.cancel_requested():
                return self._finish(
                    transitions, FlowStatus.CANCELLED, final_snapshot=final
                )
            if not selected.succeeded or not expected(final):
                return self._finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        f"mw_to_{name}_failed:"
                        f"{selected.outcome.value}:{selected.error}"
                    ),
                )
            return self._finish(
                transitions,
                FlowStatus.COMPLETED,
                final_snapshot=final,
                after_sequence=final.sequence,
            )
        except RuntimeWaitCancelled:
            return self._finish(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return self._finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
            )

    def _open_mw_menu(self, anchor):
        transitions = []
        if not isinstance(anchor, FreshMonsterWaveSnapshot):
            raise ValueError("anchor must be FreshMonsterWaveSnapshot")
        try:
            if self.cancel_requested():
                return transitions, None, self._finish(
                    transitions, FlowStatus.CANCELLED
                )
            opened = self.transition.execute(
                "monster_wave.prerequisite.open_quick_menu",
                OpenQuickMenu(),
                anchor.context,
                expected=lambda item: quick_menu_matches_origin(
                    item, SCREEN_MONSTER_WAVE
                ),
                precondition=lambda item: clean_mw(item)
                and skip_state(item) is not None,
                retryable_from=None,
                policy=_single_attempt_policy(),
            )
            transitions.append(opened)
            if not opened.succeeded:
                return transitions, None, self._finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=opened.final_snapshot,
                    error=(
                        "mw_quick_menu_open_failed:"
                        f"{opened.outcome.value}:{opened.error}"
                    ),
                )
            handoff = QuickMenuHandoff.from_open_result(
                opened,
                lambda item: clean_mw(item) and skip_state(item) is not None,
            )
            if handoff is None:
                return transitions, None, self._finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=opened.final_snapshot,
                    error="mw_quick_menu_handoff_invalid",
                )
            return transitions, handoff, None
        except RuntimeWaitCancelled:
            return transitions, None, self._finish(
                transitions, FlowStatus.CANCELLED
            )
        except Exception as error:
            return transitions, None, self._finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
            )

    def _leave_to_mw(self, *, name, action, precondition):
        transitions = []
        try:
            if self.cancel_requested():
                return self._finish(transitions, FlowStatus.CANCELLED)
            before = self.observer.wait_until(
                precondition,
                after_sequence=0,
                timeout=6.0,
                stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            result = self.transition.execute(
                f"monster_wave.prerequisite.leave_{name}",
                action,
                before,
                expected=lambda item: clean_mw(item)
                and skip_state(item) is not None,
                precondition=precondition,
                retryable_from=None,
                stable_for=0.25,
                policy=_single_attempt_policy(),
            )
            transitions.append(result)
            final = result.final_snapshot
            if self.cancel_requested():
                return self._finish(
                    transitions, FlowStatus.CANCELLED, final_snapshot=final
                )
            if (
                not result.succeeded
                or final.sequence <= before.sequence
                or not clean_mw(final)
                or skip_state(final) is None
            ):
                return self._finish(
                    transitions,
                    FlowStatus.FAILED,
                    final_snapshot=final,
                    error=(
                        f"{name}_return_to_mw_failed:"
                        f"{result.outcome.value}:{result.error}"
                    ),
                )
            return self._finish(
                transitions,
                FlowStatus.COMPLETED,
                final_snapshot=final,
                after_sequence=final.sequence,
            )
        except RuntimeWaitCancelled:
            return self._finish(transitions, FlowStatus.CANCELLED)
        except Exception as error:
            return self._finish(
                transitions,
                FlowStatus.FAILED,
                error=str(error) or type(error).__name__,
            )

    @staticmethod
    def _finish(
        transitions,
        status,
        capability_result=None,
        **kwargs,
    ) -> MonsterWaveNavigationResult:
        return MonsterWaveNavigationResult(
            status,
            capability_result=capability_result,
            transition_outcomes=tuple(
                (item.name, item.outcome.value) for item in transitions
            ),
            **kwargs,
        )


class MonsterWaveGoldCapacityRecovery:
    """State-local MW handoffs supplied to one C6b invocation."""

    def __init__(self, navigation, snapshots) -> None:
        self.navigation = navigation
        self.snapshots = snapshots
        self._anchor: FreshMonsterWaveSnapshot | None = None

    def as_navigation(self) -> GoldCapacityRecoveryNavigation:
        return GoldCapacityRecoveryNavigation(
            source="monster_wave",
            leave_trading=self.leave_trading,
            enter_treasure=self.enter_treasure,
            return_to_trading=self.return_to_trading,
            leave_step="trading.x_to_monster_wave",
            enter_step="monster_wave.quick_menu_to_treasure",
            return_step=(
                "treasure.back_to_monster_wave.quick_menu_to_trading"
            ),
        )

    def leave_trading(self):
        left = self.navigation.leave_trading_to_mw()
        if left.status is not FlowStatus.COMPLETED or left.final_snapshot is None:
            return left
        refreshed = self.snapshots.acquire(
            after_sequence=left.final_snapshot.sequence
        )
        if refreshed.status is FlowStatus.COMPLETED:
            self._anchor = refreshed.fresh
        return refreshed

    def enter_treasure(self):
        if self._anchor is None:
            return MonsterWaveNavigationResult(
                FlowStatus.FAILED,
                error="mw_anchor_missing_before_treasure",
            )
        return self.navigation.enter_treasure_from_mw(self._anchor)

    def return_to_trading(self):
        left = self.navigation.leave_treasure_to_mw()
        if left.status is not FlowStatus.COMPLETED or left.final_snapshot is None:
            return left
        refreshed = self.snapshots.acquire(
            after_sequence=left.final_snapshot.sequence
        )
        if refreshed.status is not FlowStatus.COMPLETED or refreshed.fresh is None:
            return refreshed
        self._anchor = refreshed.fresh
        return self.navigation.enter_trading_from_mw(self._anchor)


class ResourceRouteExecutionStatus(str, Enum):
    SUCCESS = "success"
    NON_EXECUTABLE_PLAN = "non_executable_plan"
    STEP_FAILED = "step_failed"
    CANCELLED = "cancelled"
    RETURN_TO_MW_FAILED = "return_to_mw_failed"
    POSTCONDITION_FAILED = "postcondition_failed"


@dataclass(frozen=True)
class ResourceRouteExecutionResult:
    status: ResourceRouteExecutionStatus
    executed_steps: tuple[ResourceRouteStep, ...] = ()
    failing_step: str | None = None
    capability_result: object | None = None
    evidence: tuple[str, ...] = ()
    final_snapshot: MonsterWaveBoardSnapshot | None = None
    final_context: RuntimeSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ResourceRouteExecutionStatus):
            raise ValueError("status must be ResourceRouteExecutionStatus")
        object.__setattr__(self, "executed_steps", tuple(self.executed_steps))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.status is ResourceRouteExecutionStatus.SUCCESS:
            if self.final_snapshot is None or self.final_context is None:
                raise ValueError("SUCCESS requires a fresh final MW snapshot")


class MonsterWaveResourceRouteRuntime:
    """Execute one immutable plan once, always anchoring top-level blocks on MW."""

    def __init__(
        self,
        navigation,
        snapshots,
        craft_runtime,
        keys_runtime,
        materials_runtime,
        *,
        keys_budget_remaining: int,
        cancel_requested=lambda: False,
    ) -> None:
        for owner, method in (
            (navigation, "enter_craft_from_mw"),
            (navigation, "enter_trading_from_mw"),
            (navigation, "leave_trading_to_mw"),
            (snapshots, "acquire"),
            (craft_runtime, "execute"),
            (craft_runtime, "request_back_to_origin"),
            (keys_runtime, "run"),
            (materials_runtime, "execute"),
        ):
            if not callable(getattr(owner, method, None)):
                raise ValueError(f"runtime must provide {method}()")
        if (
            isinstance(keys_budget_remaining, bool)
            or not isinstance(keys_budget_remaining, Integral)
            or int(keys_budget_remaining) < 1
        ):
            raise ValueError("keys_budget_remaining must be a positive integer")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.navigation = navigation
        self.snapshots = snapshots
        self.craft_runtime = craft_runtime
        self.keys_runtime = keys_runtime
        self.materials_runtime = materials_runtime
        self.keys_budget_remaining = int(keys_budget_remaining)
        self.cancel_requested = cancel_requested

    def execute_plan_once(
        self,
        plan: ResourceRoutePlan,
        initial: FreshMonsterWaveSnapshot,
    ) -> ResourceRouteExecutionResult:
        if not isinstance(plan, ResourceRoutePlan):
            raise ValueError("plan must be ResourceRoutePlan")
        executed: list[ResourceRouteStep] = []
        evidence: list[str] = []

        def finish(status, **kwargs):
            return ResourceRouteExecutionResult(
                status,
                executed_steps=tuple(executed),
                evidence=tuple(evidence),
                **kwargs,
            )

        if plan.status in {
            ResourceRouteStatus.INSUFFICIENT_OBSERVABILITY,
            ResourceRouteStatus.CONTRADICTORY,
        }:
            evidence.append(f"plan_status:{plan.status.value}")
            return finish(ResourceRouteExecutionStatus.NON_EXECUTABLE_PLAN)
        problem = self._validate_shape(plan)
        if problem is not None:
            return finish(
                ResourceRouteExecutionStatus.NON_EXECUTABLE_PLAN,
                failing_step=problem,
            )
        if not isinstance(initial, FreshMonsterWaveSnapshot):
            raise ValueError("initial must be FreshMonsterWaveSnapshot")
        if plan.status is ResourceRouteStatus.NO_PREREQUISITES:
            evidence.append("no_prerequisites:zero_input")
            return finish(
                ResourceRouteExecutionStatus.SUCCESS,
                final_snapshot=initial.snapshot,
                final_context=initial.context,
            )
        if self._cancelled():
            return finish(ResourceRouteExecutionStatus.CANCELLED)

        anchor = initial
        for step in plan.steps:
            if isinstance(step, CraftStep):
                entered = self.navigation.enter_craft_from_mw(
                    anchor,
                    entry_capacity_proven=True,
                )
                evidence.append("route:mw_quick_menu_craft")
                if entered.status is FlowStatus.CANCELLED:
                    return finish(
                        ResourceRouteExecutionStatus.CANCELLED,
                        failing_step=step.capability,
                        capability_result=entered,
                    )
                if entered.status is not FlowStatus.COMPLETED:
                    return finish(
                        ResourceRouteExecutionStatus.STEP_FAILED,
                        failing_step=step.capability,
                        capability_result=entered,
                    )
                request = CraftRequest(
                    family=CraftFamily(step.family),
                    tier=CraftTier(step.tier),
                    quantity_mode=CraftQuantityMode.ONE,
                )
                crafted = self.craft_runtime.execute(request)
                if crafted.outcome is CraftOutcome.CANCELLED:
                    return finish(
                        ResourceRouteExecutionStatus.CANCELLED,
                        failing_step=step.capability,
                        capability_result=crafted,
                    )
                if crafted.outcome is not CraftOutcome.SUCCESS:
                    return finish(
                        ResourceRouteExecutionStatus.STEP_FAILED,
                        failing_step=step.capability,
                        capability_result=crafted,
                    )
                returned = self.craft_runtime.request_back_to_origin()
                evidence.append("route:craft_back_to_mw")
                if returned.outcome is CraftRouteOutcome.CANCELLED:
                    return finish(
                        ResourceRouteExecutionStatus.CANCELLED,
                        failing_step=step.capability,
                        capability_result=returned,
                    )
                if (
                    returned.outcome is not CraftRouteOutcome.BACK_REQUESTED
                    or returned.craft_fact is None
                ):
                    return finish(
                        ResourceRouteExecutionStatus.RETURN_TO_MW_FAILED,
                        failing_step=step.capability,
                        capability_result=returned,
                    )
                refreshed = self.snapshots.acquire(
                    after_sequence=returned.craft_fact.sequence
                )
                if refreshed.status is FlowStatus.CANCELLED:
                    return finish(
                        ResourceRouteExecutionStatus.CANCELLED,
                        failing_step=step.capability,
                        capability_result=refreshed,
                    )
                if refreshed.status is not FlowStatus.COMPLETED or refreshed.fresh is None:
                    return finish(
                        ResourceRouteExecutionStatus.RETURN_TO_MW_FAILED,
                        failing_step=step.capability,
                        capability_result=refreshed,
                    )
                anchor = refreshed.fresh
                executed.append(step)
                evidence.append("freshness:craft_return_mw")
                continue

            assert isinstance(step, TradingSessionStep)
            entered = self.navigation.enter_trading_from_mw(anchor)
            evidence.append("route:mw_quick_menu_trading")
            if entered.status is FlowStatus.CANCELLED:
                return finish(
                    ResourceRouteExecutionStatus.CANCELLED,
                    failing_step=step.capability,
                    capability_result=entered,
                )
            if entered.status is not FlowStatus.COMPLETED:
                return finish(
                    ResourceRouteExecutionStatus.STEP_FAILED,
                    failing_step=step.capability,
                    capability_result=entered,
                )
            for operation in step.operations:
                if isinstance(operation, KeysPromotionStep):
                    recovery = MonsterWaveGoldCapacityRecovery(
                        self.navigation, self.snapshots
                    )
                    result = self.keys_runtime.run(
                        budget_remaining=self.keys_budget_remaining,
                        recovery_navigation=recovery.as_navigation(),
                    )
                    evidence.append("trading:keys")
                else:
                    assert isinstance(operation, TradingMaterialsStep)
                    result = self.materials_runtime.execute(operation)
                    evidence.append("trading:general_materials")
                if result.status is FlowStatus.CANCELLED:
                    return finish(
                        ResourceRouteExecutionStatus.CANCELLED,
                        failing_step=operation.capability,
                        capability_result=result,
                    )
                if result.status is not FlowStatus.COMPLETED:
                    return finish(
                        ResourceRouteExecutionStatus.STEP_FAILED,
                        failing_step=operation.capability,
                        capability_result=result,
                    )
            left = self.navigation.leave_trading_to_mw()
            evidence.append("route:trading_x_to_mw")
            if left.status is FlowStatus.CANCELLED:
                return finish(
                    ResourceRouteExecutionStatus.CANCELLED,
                    failing_step=step.capability,
                    capability_result=left,
                )
            if left.status is not FlowStatus.COMPLETED or left.final_snapshot is None:
                return finish(
                    ResourceRouteExecutionStatus.RETURN_TO_MW_FAILED,
                    failing_step=step.capability,
                    capability_result=left,
                )
            refreshed = self.snapshots.acquire(
                after_sequence=left.final_snapshot.sequence
            )
            if refreshed.status is FlowStatus.CANCELLED:
                return finish(
                    ResourceRouteExecutionStatus.CANCELLED,
                    failing_step=step.capability,
                    capability_result=refreshed,
                )
            if refreshed.status is not FlowStatus.COMPLETED or refreshed.fresh is None:
                return finish(
                    ResourceRouteExecutionStatus.POSTCONDITION_FAILED,
                    failing_step=step.capability,
                    capability_result=refreshed,
                )
            anchor = refreshed.fresh
            executed.append(step)
            evidence.append("freshness:final_mw_snapshot")

        return finish(
            ResourceRouteExecutionStatus.SUCCESS,
            final_snapshot=anchor.snapshot,
            final_context=anchor.context,
        )

    @staticmethod
    def _validate_shape(plan: ResourceRoutePlan) -> str | None:
        if plan.status is ResourceRouteStatus.NO_PREREQUISITES:
            return None
        if plan.status is not ResourceRouteStatus.READY:
            return "plan_status"
        if not 1 <= len(plan.steps) <= 2:
            return "top_level_shape"
        if len(plan.steps) == 2 and not (
            isinstance(plan.steps[0], CraftStep)
            and isinstance(plan.steps[1], TradingSessionStep)
        ):
            return "top_level_order"
        if len(plan.steps) == 1 and not isinstance(
            plan.steps[0], (CraftStep, TradingSessionStep)
        ):
            return "top_level_step"
        for step in plan.steps:
            if isinstance(step, CraftStep):
                if step.family not in {item.value for item in CraftFamily}:
                    return "craft_family"
                if step.tier != CraftTier.HERO.value or step.quantity != 1:
                    return "craft_request"
                continue
            operations = step.operations
            if any(
                isinstance(item, KeysPromotionStep)
                for item in operations[1:]
            ):
                return "trading_operation_order"
            if any(
                not isinstance(item, (KeysPromotionStep, TradingMaterialsStep))
                for item in operations
            ):
                return "trading_operation"
        return None

    def _cancelled(self) -> bool:
        try:
            return self.cancel_requested() is True
        except Exception:
            return False


__all__ = (
    "FreshMonsterWaveSnapshot",
    "MonsterWaveGoldCapacityRecovery",
    "MonsterWaveNavigationResult",
    "MonsterWavePrerequisiteNavigationRuntime",
    "MonsterWaveResourceRouteRuntime",
    "MonsterWaveSnapshotResult",
    "MonsterWaveSnapshotRuntime",
    "ResourceRouteExecutionResult",
    "ResourceRouteExecutionStatus",
)
