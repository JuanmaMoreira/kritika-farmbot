"""Execute one supplied resource prerequisite plan around a Monster Wave anchor.

This is the J boundary.  It does not plan, replan, execute Monster Wave battle
work, or route generically.  Craft and the single grouped Trading block are
serialized through MW or the verified modal Trading return to Craft.
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
from bot.equipment_combine_relief import EquipmentCombineReturnPlan
from bot.equipment_relief import (
    EquipmentReliefOutcome,
    EquipmentReliefRequest,
    FreshCallerContext,
)
from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.keys_promotion_runtime import GoldCapacityRecoveryNavigation
from bot.keys_promotion import PendingCausalOperation
from bot.monster_wave_activity import (clean_mw, skip_state, entry_ready,
    ENTRY_ACKNOWLEDGEMENTS, popup)
from bot.monster_wave_board_snapshot import (
    BoardPopup,
    MonsterWaveBoardSnapshot,
    build_monster_wave_board_snapshot,
)
from bot.monster_wave_semantics import SCREEN_MONSTER_WAVE
from bot.quick_menu import (
    QuickMenuHandoff,
    quick_menu_matches_origin,
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
from bot.semantic_actions import CloseTrading, ExitCombine, ExitTreasure, OpenQuickMenu
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
        resume_mw_from_lobby=None,
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
        if resume_mw_from_lobby is not None and not callable(resume_mw_from_lobby):
            raise ValueError("resume_mw_from_lobby must be callable")
        self.resume_mw_from_lobby = resume_mw_from_lobby
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

    def enter_craft_from_mw(self, anchor: FreshMonsterWaveSnapshot) -> MonsterWaveNavigationResult:
        transitions, handoff, failed = self._open_mw_menu(anchor)
        if failed is not None:
            return failed
        assert handoff is not None
        try:
            entered = self.craft_runtime.enter_from_verified_quick_menu(
                handoff, transitions[-1].final_snapshot,
            )
            if entered.outcome is CraftRouteOutcome.CANCELLED:
                return self._finish(transitions, FlowStatus.CANCELLED, entered)
            if entered.outcome is not CraftRouteOutcome.ENTERED:
                return self._finish(transitions, FlowStatus.FAILED, entered,
                                    error=f"craft_enter_failed:{entered.reason}")
            return self._finish(transitions, FlowStatus.COMPLETED, entered)
        except Exception as error:
            return self._finish(transitions, FlowStatus.FAILED,
                                error=str(error) or type(error).__name__)

    def enter_combine_from_craft(self, capacity):
        """One established Equipment Full -> Combine hop from this Craft visit."""
        from bot.catalog import POPUP_EQUIPMENT_INVENTORY_FULL, SCREEN_COMBINE
        from bot.semantic_actions import OpenHeroCraft, OpenEquipmentCombine
        from bot.state import ResolutionStatus
        def full(item):
            return (item.state.status is not ResolutionStatus.AMBIGUOUS
                    and set(item.state.overlays) == {POPUP_EQUIPMENT_INVENTORY_FULL})
        popup = self.observer.observe()
        if not full(popup):
            observed = self.craft_runtime.observe_context(after_sequence=capacity.craft_fact.sequence)
            if observed.outcome is CraftRouteOutcome.CANCELLED:
                raise RuntimeWaitCancelled()
            if observed.outcome is not CraftRouteOutcome.ENTERED or observed.craft_fact is None:
                raise ValueError("craft_context_not_fresh_before_full_popup")
            if self.cancel_requested():
                raise RuntimeWaitCancelled()
            family = getattr(capacity, "work_family", None) or CraftFamily.WEAPON
            self.craft_runtime._tap(OpenHeroCraft(family))
            popup = self.observer.wait_until(
                full, after_sequence=observed.craft_fact.sequence, timeout=6.0,
                stable_for=.25, cancel_requested=self.cancel_requested,
            )
        if self.cancel_requested():
            raise RuntimeWaitCancelled()
        result = self.transition.execute(
            "craft.equipment_full_to_combine", OpenEquipmentCombine(), popup,
            precondition=full,
            expected=lambda item: item.state.status is ResolutionStatus.RESOLVED
                and item.state.base_context == SCREEN_COMBINE,
            policy=_single_attempt_policy(), stable_for=.25,
        )
        if not result.succeeded or result.final_snapshot.sequence <= popup.sequence:
            raise ValueError("craft_full_to_combine_failed")
        return result.final_snapshot

    def continue_from_craft_lobby(self, *, after_sequence: int):
        """Normal continuation after Craft -> Inventory -> Craft -> Back."""
        from bot.battle_mode_zone import is_lobby
        try:
            lobby = self.observer.wait_until(
                is_lobby, after_sequence=after_sequence, timeout=6.0,
                stable_for=.25, cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return MonsterWaveNavigationResult(FlowStatus.CANCELLED)
            if self.resume_mw_from_lobby is None:
                return MonsterWaveNavigationResult(FlowStatus.FAILED,
                                                  error="craft_lobby_continuation_not_wired")
            result = self.resume_mw_from_lobby()
            return MonsterWaveNavigationResult(result.status, error=result.error,
                                              after_sequence=lobby.sequence,
                                              capability_result=result)
        except RuntimeWaitCancelled:
            return MonsterWaveNavigationResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveNavigationResult(FlowStatus.FAILED, error=str(error))

    def leave_trading_to_mw(self) -> MonsterWaveNavigationResult:
        return self._leave_to_mw(
            name="trading",
            action=CloseTrading(),
            precondition=clean_trading,
        )

    def enter_trading_from_craft(self) -> MonsterWaveNavigationResult:
        """Craft's verified Quick Menu opens modal Trading."""
        opened = self.craft_runtime.open_quick_menu_or_handoff()
        if opened.outcome is CraftRouteOutcome.CANCELLED:
            return MonsterWaveNavigationResult(FlowStatus.CANCELLED, capability_result=opened)
        if opened.outcome is not CraftRouteOutcome.QUICK_MENU_OPEN or opened.quick_menu_fact is None:
            return MonsterWaveNavigationResult(
                FlowStatus.FAILED, error="craft_quick_menu_failed", capability_result=opened,
            )
        selected = self.craft_runtime.select_trading_from_open_menu(
            after_sequence=opened.quick_menu_fact.sequence,
        )
        if selected.outcome is CraftRouteOutcome.CANCELLED:
            return MonsterWaveNavigationResult(FlowStatus.CANCELLED, capability_result=selected)
        if selected.outcome is not CraftRouteOutcome.TRADING_REQUESTED or selected.quick_menu_fact is None:
            return MonsterWaveNavigationResult(
                FlowStatus.FAILED, error="craft_trading_selection_failed",
                capability_result=selected,
            )
        try:
            trading = self.observer.wait_until(
                clean_trading,
                after_sequence=selected.quick_menu_fact.sequence,
                timeout=6.0, stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            return MonsterWaveNavigationResult(
                FlowStatus.COMPLETED, final_snapshot=trading,
                after_sequence=trading.sequence,
            )
        except RuntimeWaitCancelled:
            return MonsterWaveNavigationResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveNavigationResult(FlowStatus.FAILED, error=str(error))

    def leave_trading_to_craft(self) -> MonsterWaveNavigationResult:
        """One X from clean Trading, followed by a fresh local Craft fact."""
        try:
            before = self.observer.wait_until(
                clean_trading, after_sequence=0, timeout=6.0, stable_for=0.25,
                cancel_requested=self.cancel_requested,
            )
            if self.cancel_requested():
                return MonsterWaveNavigationResult(FlowStatus.CANCELLED)
            self.transition.actions.execute(CloseTrading(), before.geometry)
            restored = self.craft_runtime.observe_context(after_sequence=before.sequence)
            if restored.outcome is CraftRouteOutcome.CANCELLED:
                return MonsterWaveNavigationResult(FlowStatus.CANCELLED, capability_result=restored)
            if restored.outcome is not CraftRouteOutcome.ENTERED or restored.craft_fact is None:
                return MonsterWaveNavigationResult(
                    FlowStatus.FAILED, error="trading_x_craft_not_verified",
                    capability_result=restored,
                )
            return MonsterWaveNavigationResult(
                FlowStatus.COMPLETED, after_sequence=restored.craft_fact.sequence,
                capability_result=restored,
            )
        except RuntimeWaitCancelled:
            return MonsterWaveNavigationResult(FlowStatus.CANCELLED)
        except Exception as error:
            return MonsterWaveNavigationResult(FlowStatus.FAILED, error=str(error))

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
        from bot.battle_mode_zone import is_lobby
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
                expected=lambda item: entry_ready(item) or is_lobby(item),
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
            # Returning from a relief may expose MW's existing Ranking/Weekly
            # modal. Resolve that owner before demanding a clean actionable MW.
            if result.succeeded and final.sequence > before.sequence:
                for _ in range(2):
                    modal = next((name for name in ENTRY_ACKNOWLEDGEMENTS
                                  if popup(name)(final)), None)
                    if modal is None:
                        break
                    if self.cancel_requested():
                        return self._finish(transitions, FlowStatus.CANCELLED, final_snapshot=final)
                    modal_source = final
                    acknowledged = self.transition.execute(
                        "monster_wave.prerequisite.acknowledge_return_modal",
                        ENTRY_ACKNOWLEDGEMENTS[modal](), modal_source,
                        expected=entry_ready, precondition=popup(modal),
                        retryable_from=None, stable_for=.25,
                        policy=_single_attempt_policy(),
                    )
                    transitions.append(acknowledged)
                    final = acknowledged.final_snapshot
                    if not acknowledged.succeeded or final.sequence <= modal_source.sequence:
                        return self._finish(transitions, FlowStatus.FAILED, final_snapshot=final,
                                            error=f"{name}_return_modal_failed:{modal}")
            if result.succeeded and final.sequence>before.sequence and is_lobby(final):
                # Close is the modal transition. Only a fresh concrete Lobby
                # destination can authorize the existing bounded MW reentry.
                if self.resume_mw_from_lobby is None:
                    return self._finish(transitions,FlowStatus.FAILED,
                        final_snapshot=final,error=f"{name}_lobby_continuation_not_wired")
                resumed=self.resume_mw_from_lobby()
                if resumed.status is not FlowStatus.COMPLETED:
                    return self._finish(transitions,resumed.status,resumed,error=resumed.error)
                final=self.observer.wait_until(
                    lambda item: clean_mw(item) and skip_state(item) is not None,
                    after_sequence=final.sequence,timeout=6.,stable_for=.25,
                    cancel_requested=self.cancel_requested)
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
        self._deferred = False

    def start_from_mw(self, anchor: FreshMonsterWaveSnapshot) -> None:
        self._anchor = anchor
        self._deferred = True

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
        if self._deferred:
            self._deferred = False
            assert self._anchor is not None
            return MonsterWaveNavigationResult(
                FlowStatus.COMPLETED, final_snapshot=self._anchor.context,
            )
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
    EQUIPMENT_CAPACITY_BLOCKED = "equipment_capacity_blocked"
    CANCELLED = "cancelled"
    RETURN_TO_MW_FAILED = "return_to_mw_failed"
    POSTCONDITION_FAILED = "postcondition_failed"


@dataclass(frozen=True)
class ResourceRouteExecutionResult:
    status: ResourceRouteExecutionStatus
    executed_steps: tuple[ResourceRouteStep, ...] = ()
    failing_step: str | None = None
    capability_result: object | None = None
    pending: PendingCausalOperation | None = None
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
        keys_budget_remaining: int | None = None,
        equipment_relief=None,
        equipment_sell_plan=None,
        cancel_requested=lambda: False,
    ) -> None:
        for owner, method in (
            (navigation, "enter_craft_from_mw"),
            (navigation, "enter_trading_from_mw"),
            (navigation, "leave_trading_to_mw"),
            (snapshots, "acquire"),
            (craft_runtime, "drain_hero_materials"),
            (craft_runtime, "probe_equipment_capacity"),
            (craft_runtime, "request_back_to_origin"),
            (keys_runtime, "run"),
            (materials_runtime, "execute"),
        ):
            if not callable(getattr(owner, method, None)):
                raise ValueError(f"runtime must provide {method}()")
        if keys_budget_remaining is not None and (
            isinstance(keys_budget_remaining, bool)
            or not isinstance(keys_budget_remaining, Integral)
            or int(keys_budget_remaining) < 1
        ):
            raise ValueError("keys_budget_remaining must be a positive integer")
        if equipment_relief is not None and not callable(
            getattr(equipment_relief, "run", None)
        ):
            raise ValueError("equipment_relief must provide run() or be None")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.navigation = navigation
        self.snapshots = snapshots
        self.craft_runtime = craft_runtime
        self.keys_runtime = keys_runtime
        self.materials_runtime = materials_runtime
        self.keys_budget_remaining = (
            int(keys_budget_remaining) if keys_budget_remaining is not None else None
        )
        self.equipment_relief = equipment_relief
        self.equipment_sell_plan = equipment_sell_plan
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
        pending: PendingCausalOperation | None = None

        def finish(status, **kwargs):
            return ResourceRouteExecutionResult(
                status,
                executed_steps=tuple(executed),
                evidence=tuple(evidence),
                pending=pending,
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
        craft = next((s for s in plan.steps if isinstance(s, CraftStep)), None)
        trading = next((s for s in plan.steps if isinstance(s, TradingSessionStep)), None)
        has_materials = trading is not None and any(
            isinstance(op, TradingMaterialsStep) for op in trading.operations
        )
        craft_open = False
        keys_budget_left = self.keys_budget_remaining

        def failed(result, step_name, *, returning=False):
            if getattr(result, "status", None) is FlowStatus.CANCELLED or (
                getattr(result, "outcome", None) is CraftOutcome.CANCELLED
            ) or getattr(result, "outcome", None) is CraftRouteOutcome.CANCELLED:
                status = ResourceRouteExecutionStatus.CANCELLED
            elif returning:
                status = ResourceRouteExecutionStatus.RETURN_TO_MW_FAILED
            else:
                status = ResourceRouteExecutionStatus.STEP_FAILED
            return finish(status, failing_step=step_name, capability_result=result)

        def fresh_mw(after_sequence, step_name):
            result = self.snapshots.acquire(after_sequence=after_sequence)
            if result.status is not FlowStatus.COMPLETED or result.fresh is None:
                return None, failed(result, step_name, returning=True)
            return result.fresh, None

        def continue_after_craft(returned):
            from bot.catalog import SCREEN_LOBBY
            after_sequence = returned.craft_fact.sequence
            if returned.return_base == SCREEN_LOBBY:
                continued = self.navigation.continue_from_craft_lobby(after_sequence=after_sequence)
                evidence.append("route:craft_inventory_back_to_lobby_then_mw")
                if continued.status is not FlowStatus.COMPLETED:
                    return None, failed(continued, craft.capability, returning=True)
                after_sequence = continued.after_sequence
            else:
                evidence.append("route:craft_back_to_mw")
            return fresh_mw(after_sequence, craft.capability)

        if craft is not None:
            entered = self.navigation.enter_craft_from_mw(anchor)
            evidence.append("route:mw_quick_menu_craft")
            if entered.status is not FlowStatus.COMPLETED:
                return failed(entered, craft.capability)
            craft_open = True
            capacity = self.craft_runtime.probe_equipment_capacity()
            evidence.append("craft:required_equipment_capacity")
            if capacity.outcome is CraftRouteOutcome.CAPACITY_BLOCKED:
                if self.equipment_relief is None:
                    return finish(ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED,
                                  failing_step=craft.capability, capability_result=capacity)
                relieved = self._relieve_craft_capacity_once(
                    craft, capacity, evidence, finish,
                )
                if relieved is not None:
                    return relieved
                # Relief success: retry already drained this CraftStep.
                # Continue the SAME execute_plan_once (no replan, no second J).
            elif capacity.outcome is not CraftRouteOutcome.ENTERED:
                return failed(capacity, craft.capability)
            else:
                drained = self.craft_runtime.drain_hero_materials(max_batches=32)
                evidence.append("craft:drain_eligible_hero_families")
                if drained.outcome is not CraftOutcome.SUCCESS:
                    return failed(drained, craft.capability)

        if trading is not None:
            if craft_open and has_materials:
                entered = self.navigation.enter_trading_from_craft()
                evidence.append("route:craft_quick_menu_trading_modal")
            else:
                if craft_open:
                    returned = self.craft_runtime.request_back_to_origin()
                    if returned.outcome is not CraftRouteOutcome.BACK_REQUESTED or returned.craft_fact is None:
                        return failed(returned, craft.capability, returning=True)
                    anchor, problem = continue_after_craft(returned)
                    if problem is not None:
                        return problem
                    craft_open = False
                entered = self.navigation.enter_trading_from_mw(anchor)
                evidence.append("route:mw_quick_menu_trading")
            if entered.status is not FlowStatus.COMPLETED:
                return failed(entered, trading.capability)
            for operation in trading.operations:
                if isinstance(operation, KeysPromotionStep):
                    result = self.keys_runtime.run(
                        budget_remaining=self.keys_budget_remaining,
                        defer_recovery=True,
                    )
                    evidence.append("trading:keys_first")
                    pending = getattr(result, "pending", None)
                    keys_budget_left = (
                        result.remaining_budget
                        if self.keys_budget_remaining is None
                        else max(0, self.keys_budget_remaining - len(getattr(result, "trade_attempts", ())))
                    )
                else:
                    result = self.materials_runtime.execute(operation, max_batches=32)
                    evidence.append("trading:drain_weapon_until_below_40")
                if result.status is not FlowStatus.COMPLETED:
                    return failed(result, operation.capability)
            if craft_open and has_materials:
                left = self.navigation.leave_trading_to_craft()
                evidence.append("route:trading_x_restores_craft")
                if left.status is not FlowStatus.COMPLETED:
                    return failed(left, trading.capability, returning=True)
                drained = self.craft_runtime.drain_hero_materials(max_batches=32)
                evidence.append("craft:drain_new_eligible_hero_families")
                if drained.outcome is not CraftOutcome.SUCCESS:
                    return failed(drained, craft.capability)
                returned = self.craft_runtime.request_back_to_origin()
                if returned.outcome is not CraftRouteOutcome.BACK_REQUESTED or returned.craft_fact is None:
                    return failed(returned, craft.capability, returning=True)
                anchor, problem = continue_after_craft(returned)
                if problem is not None:
                    return problem
                craft_open = False
            else:
                left = self.navigation.leave_trading_to_mw()
                evidence.append("route:trading_x_to_mw")
                if left.status is not FlowStatus.COMPLETED or left.final_snapshot is None:
                    return failed(left, trading.capability, returning=True)
                anchor, problem = fresh_mw(left.final_snapshot.sequence, trading.capability)
                if problem is not None:
                    return problem

            if pending is not None:
                recovery = MonsterWaveGoldCapacityRecovery(self.navigation, self.snapshots)
                recovery.start_from_mw(anchor)
                resolved = self.keys_runtime.resolve_pending(
                    pending,
                    budget_remaining=keys_budget_left,
                    recovery_navigation=recovery.as_navigation(),
                )
                evidence.append("keys:deferred_gold_full_drain_and_exact_retry")
                if resolved.status is not FlowStatus.COMPLETED:
                    return failed(resolved, "keys_promotion")
                pending = None
                left = self.navigation.leave_trading_to_mw()
                evidence.append("route:trading_retry_x_to_mw")
                if left.status is not FlowStatus.COMPLETED or left.final_snapshot is None:
                    return failed(left, trading.capability, returning=True)
                anchor, problem = fresh_mw(left.final_snapshot.sequence, trading.capability)
                if problem is not None:
                    return problem
        elif craft_open:
            returned = self.craft_runtime.request_back_to_origin()
            if returned.outcome is not CraftRouteOutcome.BACK_REQUESTED or returned.craft_fact is None:
                return failed(returned, craft.capability, returning=True)
            anchor, problem = continue_after_craft(returned)
            if problem is not None:
                return problem

        executed.extend(plan.steps)
        return finish(
            ResourceRouteExecutionStatus.SUCCESS,
            final_snapshot=anchor.snapshot,
            final_context=anchor.context,
        )

    def _relieve_craft_capacity_once(self, craft, capacity, evidence, finish):
        """Bounded transversal relief for one CAPACITY_BLOCKED CraftStep.

        Runs EquipmentReliefComposer at most once, returns to Craft clean,
        retries ONLY this CraftStep (probe + drain) and lets the caller
        continue the SAME execute_plan_once. No replan, no second board,
        no second planner, no second complete J. No Sell plan: still-full
        after Combine fails closed as EQUIPMENT_CAPACITY_BLOCKED.
        Returns None on relief success (drain already done, continue),
        otherwise a finished ResourceRouteExecutionResult to return.
        """
        first_attempt = True
        cached = capacity

        def _cached_sequence() -> int:
            for fact in (
                getattr(cached, "craft_fact", None),
                getattr(cached, "inventory_fact", None),
            ):
                seq = getattr(fact, "sequence", None)
                if isinstance(seq, bool):
                    continue
                if isinstance(seq, Integral) and int(seq) >= 0:
                    return int(seq)
            return 0

        def acquire(after_sequence):
            if after_sequence is None:
                return FreshCallerContext(cached, _cached_sequence())
            observed = self.craft_runtime.observe_context(
                after_sequence=int(after_sequence),
            )
            if (
                getattr(observed, "outcome", None) is not CraftRouteOutcome.ENTERED
                or getattr(observed, "craft_fact", None) is None
            ):
                raise ValueError("craft_context_not_fresh_after_relief")
            seq = observed.craft_fact.sequence
            if isinstance(seq, bool) or not isinstance(seq, Integral) or int(seq) <= int(after_sequence):
                raise ValueError("craft_context_not_fresh_after_relief")
            return FreshCallerContext(observed.craft_fact, int(seq))

        def execute(_request, _context):
            nonlocal first_attempt
            if first_attempt:
                first_attempt = False
                return cached
            # Retry ONLY this CraftStep: fresh probe + drain, no trading.
            probed = self.craft_runtime.probe_equipment_capacity()
            if getattr(probed, "outcome", None) is not CraftRouteOutcome.ENTERED:
                return probed
            return self.craft_runtime.drain_hero_materials(max_batches=32)

        def is_full(result) -> bool:
            return (
                getattr(result, "outcome", None) is CraftRouteOutcome.CAPACITY_BLOCKED
            )

        def enter_combine(caller_result):
            return self.navigation.enter_combine_from_craft(caller_result)

        def returned_to_craft(snapshot):
            # Craft is read locally; the global resolver has no Craft BASE.
            from bot.state import ResolutionStatus
            if snapshot.state.status is ResolutionStatus.AMBIGUOUS or snapshot.state.overlays:
                return False
            fact = self.craft_runtime.craft_reader.context_sample(
                snapshot.frame.image, sequence=snapshot.sequence,
                observed_at=snapshot.timestamp,
            )
            return (fact is not None and fact.complete
                    and 0 <= self.craft_runtime.clock() - fact.observed_at <= 5.0)

        request = EquipmentReliefRequest(
            operation_request=craft,
            acquire_context=acquire,
            execute_operation=execute,
            is_equipment_full=is_full,
            enter_combine=enter_combine,
            combine_return_plan=EquipmentCombineReturnPlan(
                ExitCombine(), "screen.craft", expected_return=returned_to_craft,
            ),
            sell_plan=self.equipment_sell_plan,
            cancel_requested=self.cancel_requested,
        )
        evidence.append("craft:equipment_relief_once")
        try:
            relief = self.equipment_relief.run(request)
        except Exception as error:
            return finish(
                ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED,
                failing_step=craft.capability,
                capability_result=capacity,
            )
        if relief.outcome in {
            EquipmentReliefOutcome.CANCELLED,
            EquipmentReliefOutcome.COMBINE_CANCELLED,
            EquipmentReliefOutcome.SELL_CANCELLED,
        }:
            return finish(ResourceRouteExecutionStatus.CANCELLED)
        if relief.outcome is EquipmentReliefOutcome.CALLER_RESULT:
            caller_result = relief.caller_result
            if is_full(caller_result):
                # Still full after Combine, no Sell plan: fail closed.
                return finish(
                    ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED,
                    failing_step=craft.capability,
                    capability_result=caller_result,
                )
            if getattr(caller_result, "outcome", None) is CraftOutcome.SUCCESS:
                evidence.append("craft:equipment_relief_retry_drain_success")
                return None
            # Probe unreadable or drain failed: preserve causal step,
            # degrade to STEP_FAILED (not capacity) with detail.
            if getattr(caller_result, "outcome", None) is CraftOutcome.CANCELLED or getattr(
                caller_result, "outcome", None
            ) is CraftRouteOutcome.CANCELLED:
                return finish(ResourceRouteExecutionStatus.CANCELLED)
            return finish(
                ResourceRouteExecutionStatus.STEP_FAILED,
                failing_step=craft.capability,
                capability_result=caller_result,
            )
        # COMBINE_FAILED, NAVIGATION_FAILED, context/execution failures,
        # SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE, SELL_*, FULL_AFTER_SELL:
        # preserve the original capacity blocker, no more input, no Sell.
        return finish(
            ResourceRouteExecutionStatus.EQUIPMENT_CAPACITY_BLOCKED,
            failing_step=craft.capability,
            capability_result=capacity,
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
                if step.tier != CraftTier.HERO.value or step.quantity is not None:
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
            if not isinstance(operations[0], KeysPromotionStep):
                return "keys_first"
            for item in operations:
                if isinstance(item, TradingMaterialsStep) and any(
                    operation.quantity is not None for operation in item.operations
                ):
                    return "materials_must_drain"
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
