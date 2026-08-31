from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.auto_battle import AutoBattleState, EnsureAutoBattleStatus
from bot.capture import FrameSnapshot
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
)
from bot.controlled_wait import ControlledWait, ControlledWaitOutcome
from bot.equipment_combine_relief import (
    EquipmentCombineReliefOutcome,
    EquipmentCombineReliefResult,
)
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_facts import (
    FactEvidence,
    FactQuality,
    FactReadResult,
    FactReadStatus,
    RuntimeFact,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import (
    AcceptSocketInventoryFull,
    DismissWorldBossBagFull,
    ExitCombine,
    ExitSocket,
    OpenEquipmentCombine,
    RejectSocketInventoryFull,
)
from bot.socket_inventory_relief import (
    SocketReliefOutcome,
    SocketReliefResult,
    SocketStrategyOutcome,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import (
    VerifiedTransitionOutcome,
    VerifiedTransitionResult,
)
from bot.world_boss_flow import (
    WORLD_BOSS_INSUFFICIENT_SAPPHIRES,
    WORLD_BOSS_PREVIOUS_REWARDS,
    WORLD_BOSS_INVENTORY_FULL,
    WORLD_BOSS_BAG_FULL,
    WorldBossFlow,
    WorldBossWaitPolicy,
)


def snapshot(
    sequence,
    *,
    base=None,
    overlays=(),
    status=None,
    semantic_observations=(),
):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    timestamp = float(sequence)
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, tuple(semantic_observations)),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=overlays,
            base_candidates=(
                (SCREEN_LOBBY, SCREEN_WORLD_BOSS)
                if status is ResolutionStatus.AMBIGUOUS else ()
            ),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def fact_result(name, value, sequence, context):
    evidence = FactEvidence(sequence, float(sequence), str(value), 0.99)
    return FactReadResult(
        FactReadStatus.CONFIRMED,
        fact=RuntimeFact(
            name,
            value,
            0.99,
            FactQuality.VALIDATED_SINGLE,
            ObservationSource.OCR,
            context,
            (evidence,),
        ),
        evidence=(evidence,),
    )


class Facts:
    def __init__(self, sapphires, timer=None, trace=None):
        self.sapphires = sapphires
        self.timer = timer
        self.trace = trace if trace is not None else []

    def read_sapphires(self, **kwargs):
        self.trace.append(("sapphires", kwargs))
        return self.sapphires

    def read_timer_remaining(self, **kwargs):
        self.trace.append(("timer", kwargs))
        return self.timer


class Observer:
    def __init__(self, waits=(), observes=(), trace=None):
        self.waits = list(waits)
        self.observes = list(observes)
        self.trace = trace if trace is not None else []

    def wait_until(self, condition, *, after_sequence, timeout, abort_if=None,
                   stable_for=0.0, cancel_requested=None):
        self.trace.append(("wait", after_sequence))
        item = self.waits.pop(0)
        assert condition(item)
        return item

    def observe(self):
        self.trace.append(("observe", None))
        return self.observes.pop(0)


class Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


class SocketRelief:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, return_plan, cancel_requested=None):
        self.calls.append((return_plan, cancel_requested))
        assert self.results, "unexpected Socket relief call"
        return self.results.pop(0)


class EquipmentCombineRelief:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, return_plan, cancel_requested=None):
        self.calls.append((return_plan, cancel_requested))
        assert self.results, "unexpected Equipment relief call"
        return self.results.pop(0)


class Transitions:
    def __init__(self, snapshots, outcomes=None):
        self.snapshots = list(snapshots)
        self.outcomes = list(outcomes or [])
        self.calls = []

    def execute(self, name, action, before, **kwargs):
        self.calls.append((name, action, before, kwargs))
        final = self.snapshots.pop(0)
        assert kwargs["precondition"](before)
        outcome = (
            self.outcomes.pop(0) if self.outcomes
            else VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
        )
        if outcome in {
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE,
            VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY,
        }:
            assert kwargs["expected"](final)
        return VerifiedTransitionResult(
            name, outcome, 1, int(outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE),
            final, None if outcome.value.startswith("success") else "scripted failure",
        )


class FakeTime:
    def __init__(self):
        self.current = 0.0

    def clock(self):
        return self.current

    def sleep(self, duration):
        self.current += duration


def auto_result(state=AutoBattleState.ON, taps=0, sequence=8,
                status=EnsureAutoBattleStatus.SUCCESS):
    observation = fact_result("setting.auto_battle", state, sequence,
                              SCREEN_WORLD_BOSS_BATTLE).fact
    return SimpleNamespace(
        status=status,
        observations=(observation,),
        tap_count=taps,
        detail=None,
    )


def build_flow(*, sapphire_read, timer_read=None, waits=(), observes=(),
               transitions=(), auto=None, trace=None, cancel=lambda: False,
               fake_time=None, wait_policy=None, socket_relief=None,
               equipment_combine_relief=None, transition_outcomes=None):
    trace = trace if trace is not None else []
    observer = Observer(waits, observes, trace)
    facts = Facts(sapphire_read, timer_read, trace)
    events = Events()
    transition_driver = Transitions(transitions, transition_outcomes)
    socket_relief = socket_relief or SocketRelief()
    equipment_combine_relief = equipment_combine_relief or EquipmentCombineRelief()
    auto = auto or Mock()
    if not hasattr(auto, "ensure_on"):
        auto.ensure_on = Mock(return_value=auto_result())
    fake_time = fake_time or FakeTime()
    policy = wait_policy or WorldBossWaitPolicy()
    kwargs = dict(
        wait_policy=policy,
        clock=fake_time.clock,
        initial_wait=ControlledWait(
            check_interval=1,
            clock=fake_time.clock,
            sleeper=fake_time.sleep,
        ),
        completion_wait=ControlledWait(
            check_interval=policy.completion_poll_interval,
            clock=fake_time.clock,
            sleeper=fake_time.sleep,
        ),
    )
    flow = WorldBossFlow(
        observer, Mock(), facts, auto, events,
        socket_relief=socket_relief,
        equipment_combine_relief=equipment_combine_relief,
        cancel_requested=cancel,
        verified_transition=transition_driver,
        stable_for=0,
        **kwargs,
    )
    return flow, observer, facts, auto, events, transition_driver


def happy_inputs(*, previous=False):
    lobby = snapshot(2, base=SCREEN_LOBBY)
    battle_modes = snapshot(3, base=SCREEN_BATTLE_MODE_SELECT)
    selector = snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,))
    entered = (
        snapshot(5, overlays=(POPUP_WORLD_BOSS_PREVIOUS_REWARDS,))
        if previous else snapshot(5, base=SCREEN_WORLD_BOSS)
    )
    main = snapshot(6 if not previous else 7, base=SCREEN_WORLD_BOSS)
    battle = snapshot(7 if not previous else 8, base=SCREEN_WORLD_BOSS_BATTLE)
    raid = snapshot(10, base=SCREEN_WORLD_BOSS_BATTLE,
                    overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,))
    returned = snapshot(11, base=SCREEN_WORLD_BOSS)
    transitions = [battle_modes, selector, entered]
    if previous:
        transitions.append(snapshot(6, base=SCREEN_WORLD_BOSS))
    transitions.extend([battle, returned])
    return [lobby, main], [raid], transitions


def test_insufficient_sapphires_completes_in_lobby_without_any_navigation_input():
    trace = []
    flow, observer, _, auto, events, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 4, 1, SCREEN_LOBBY),
        trace=trace,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.sapphires == 4
    assert result.event_count(WORLD_BOSS_INSUFFICIENT_SAPPHIRES) == 1
    assert trace[0][0] == "sapphires"
    assert observer.trace == trace
    assert len(driver.calls) == 0
    auto.ensure_on.assert_not_called()
    assert events.records[-1][0] == WORLD_BOSS_INSUFFICIENT_SAPPHIRES
    assert trace[0][1]["timeout"] == 15.0


@pytest.mark.parametrize("status", [
    FactReadStatus.UNCERTAIN,
    FactReadStatus.UNREADABLE,
    FactReadStatus.CONTEXT_MISMATCH,
    FactReadStatus.TIMEOUT,
    FactReadStatus.FAILURE,
])
def test_sapphires_fact_failure_fails_without_navigation(status):
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=FactReadResult(status, detail="bad read")
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert result.error.startswith("sapphires_fact_failed")
    assert driver.calls == []


@pytest.mark.parametrize("previous", [False, True])
def test_complete_flow_handles_optional_previous_rewards_and_finishes_world_boss(previous):
    waits, observes, transitions = happy_inputs(previous=previous)
    auto = Mock()
    auto.ensure_on.return_value = auto_result(
        AutoBattleState.OFF, taps=1, sequence=8 if not previous else 9
    )
    flow, _, facts, _, events, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 247, 1, SCREEN_LOBBY),
        timer_read=fact_result("battle.timer_remaining", 20, 9, SCREEN_WORLD_BOSS_BATTLE),
        waits=waits,
        observes=observes,
        transitions=transitions,
        auto=auto,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.previous_rewards is previous
    assert result.event_count(WORLD_BOSS_PREVIOUS_REWARDS) == int(previous)
    assert result.auto_battle_initial is AutoBattleState.OFF
    assert result.auto_battle_taps == 1
    assert result.initial_timer == 20
    assert result.raid_complete_detected
    assert driver.calls[-1][0] == "world_boss.continue_after_raid"
    assert [item[0] for item in facts.trace].count("timer") == 1
    assert any(name == "world_boss.previous_rewards" for name, _ in events.records) is previous


def test_complete_flow_treats_unknown_as_transit_and_never_rechecks_auto_battle():
    waits, _, transitions = happy_inputs()
    unknown_a = snapshot(100)
    unknown_b = snapshot(101)
    raid = snapshot(
        102,
        overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,),
    )
    auto = Mock()
    auto.ensure_on.return_value = auto_result(AutoBattleState.ON, sequence=8)
    fake = FakeTime()
    flow, observer, _, _, _, _ = build_flow(
        sapphire_read=fact_result("resource.sapphires", 20, 1, SCREEN_LOBBY),
        timer_read=fact_result(
            "battle.timer_remaining", 60, 9, SCREEN_WORLD_BOSS_BATTLE
        ),
        waits=waits,
        observes=[unknown_a, unknown_b, raid],
        transitions=transitions,
        auto=auto,
        fake_time=fake,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.wait_elapsed == pytest.approx(67)
    assert result.wait_checks == 3
    assert [item[0] for item in observer.trace].count("observe") == 3
    auto.ensure_on.assert_called_once()
    flow.actions.execute.assert_not_called()


def test_raid_complete_during_auto_battle_skips_timer_and_continues():
    waits, _, transitions = happy_inputs()
    raid = snapshot(
        9,
        base=SCREEN_WORLD_BOSS_BATTLE,
        overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,),
    )
    auto = Mock()
    auto.ensure_on.return_value = auto_result(
        sequence=8,
        status=EnsureAutoBattleStatus.INTERRUPTED,
    )
    auto.ensure_on.return_value.detail = (
        "observation interrupted by overlay.world_boss_raid_complete"
    )
    flow, observer, facts, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 20, 1, SCREEN_LOBBY),
        waits=[*waits, raid],
        transitions=transitions,
        auto=auto,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.raid_complete_detected
    assert result.initial_timer is None
    assert result.wait_elapsed == 0
    assert result.wait_checks == 0
    assert all(item[0] != "timer" for item in facts.trace)
    assert observer.observes == []
    assert driver.calls[-1][0] == "world_boss.continue_after_raid"


def test_previous_rewards_may_arrive_after_transient_world_boss_main():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    transient_main = snapshot(5, base=SCREEN_WORLD_BOSS)
    delayed_rewards = snapshot(
        6, overlays=(POPUP_WORLD_BOSS_PREVIOUS_REWARDS,)
    )
    stable_main = snapshot(8, base=SCREEN_WORLD_BOSS)
    battle = snapshot(9, base=SCREEN_WORLD_BOSS_BATTLE)
    raid = snapshot(
        11,
        base=SCREEN_WORLD_BOSS_BATTLE,
        overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,),
    )
    returned = snapshot(12, base=SCREEN_WORLD_BOSS)
    transitions = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        transient_main,
        snapshot(7, base=SCREEN_WORLD_BOSS),
        battle,
        returned,
    ]
    auto = Mock()
    auto.ensure_on.return_value = auto_result(sequence=9)
    flow, _, _, _, events, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        timer_read=fact_result(
            "battle.timer_remaining", 20, 10, SCREEN_WORLD_BOSS_BATTLE
        ),
        waits=[lobby, delayed_rewards, stable_main],
        observes=[raid],
        transitions=transitions,
        auto=auto,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.previous_rewards
    assert result.event_count(WORLD_BOSS_PREVIOUS_REWARDS) == 1
    assert [call[0] for call in driver.calls][3] == (
        "world_boss.ack_previous_rewards"
    )
    assert any(
        name == WORLD_BOSS_PREVIOUS_REWARDS for name, _ in events.records
    )


def test_inventory_full_uses_one_positive_relief_then_no_and_completes_nonfatally():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    main = snapshot(6, base=SCREEN_WORLD_BOSS)
    inventory = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_SOCKET_INVENTORY_FULL,),
    )
    socket = snapshot(8, base=SCREEN_SOCKET)
    after_relief = snapshot(9, base=SCREEN_WORLD_BOSS)
    inventory_again = snapshot(
        10,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_SOCKET_INVENTORY_FULL,),
    )
    returned = snapshot(11, base=SCREEN_WORLD_BOSS)
    transitions = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        snapshot(5, base=SCREEN_WORLD_BOSS),
        inventory,
        socket,
        inventory_again,
        returned,
    ]
    auto = Mock()
    relief = SocketRelief((
        SocketReliefResult(
            SocketReliefOutcome.NO_RELIEF_AVAILABLE,
            enhance=SocketStrategyOutcome.NO_EFFECT,
            sell=SocketStrategyOutcome.NO_EFFECT,
            final_snapshot=after_relief,
        ),
    ))
    flow, observer, facts, _, events, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[lobby, main],
        transitions=transitions,
        auto=auto,
        socket_relief=relief,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.inventory_full
    assert result.event_count(WORLD_BOSS_INVENTORY_FULL) == 1
    names = [call[0] for call in driver.calls]
    assert names.count("world_boss.accept_inventory_full") == 1
    assert names.count("world_boss.reject_inventory_full") == 1
    assert isinstance(driver.calls[4][1], AcceptSocketInventoryFull)
    assert isinstance(driver.calls[-1][1], RejectSocketInventoryFull)
    accept_abort = driver.calls[4][3]["abort_if"]
    assert not accept_abort(snapshot(70, base=SCREEN_WORLD_BOSS))
    assert accept_abort(snapshot(71, base=SCREEN_LOBBY))
    assert len(relief.calls) == 1
    plan, cancel_requested = relief.calls[0]
    assert isinstance(plan.action, ExitSocket)
    assert plan.expected_return_state == SCREEN_WORLD_BOSS
    assert cancel_requested is flow.cancel_requested
    assert all(item[0] != "timer" for item in facts.trace)
    assert observer.observes == []
    auto.ensure_on.assert_not_called()
    assert any(name == WORLD_BOSS_INVENTORY_FULL for name, _ in events.records)


def test_successful_socket_relief_returns_and_world_boss_continues_normally():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    main = snapshot(6, base=SCREEN_WORLD_BOSS)
    inventory = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_SOCKET_INVENTORY_FULL,),
    )
    socket = snapshot(8, base=SCREEN_SOCKET)
    after_relief = snapshot(9, base=SCREEN_WORLD_BOSS)
    battle = snapshot(10, base=SCREEN_WORLD_BOSS_BATTLE)
    raid = snapshot(
        12,
        base=SCREEN_WORLD_BOSS_BATTLE,
        overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,),
    )
    returned = snapshot(13, base=SCREEN_WORLD_BOSS)
    relief = SocketRelief((
        SocketReliefResult(
            SocketReliefOutcome.RELIEVED,
            enhance=SocketStrategyOutcome.EFFECT,
            animation_taps=2,
            final_snapshot=after_relief,
        ),
    ))
    auto = Mock(ensure_on=Mock(return_value=auto_result(sequence=10)))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        timer_read=fact_result(
            "battle.timer_remaining", 20, 11, SCREEN_WORLD_BOSS_BATTLE
        ),
        waits=[lobby, main],
        observes=[raid],
        transitions=[
            snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
            snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
            snapshot(5, base=SCREEN_WORLD_BOSS),
            inventory,
            socket,
            battle,
            returned,
        ],
        auto=auto,
        socket_relief=relief,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.raid_complete_detected
    assert not result.inventory_full
    names = [call[0] for call in driver.calls]
    assert names.count("world_boss.accept_inventory_full") == 1
    assert names.count("world_boss.start") == 2
    assert "world_boss.reject_inventory_full" not in names


def test_positive_allowance_is_not_consumed_when_socket_entry_is_unverified():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    main = snapshot(6, base=SCREEN_WORLD_BOSS)
    inventory = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_SOCKET_INVENTORY_FULL,),
    )
    relief = SocketRelief()
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[lobby, main],
        transitions=[
            snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
            snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
            snapshot(5, base=SCREEN_WORLD_BOSS),
            inventory,
            inventory,
        ],
        socket_relief=relief,
        transition_outcomes=(
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,
        ),
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert "world_boss.accept_inventory_full_failed" in result.error
    assert relief.calls == []
    assert [call[0] for call in driver.calls].count(
        "world_boss.accept_inventory_full"
    ) == 1


@pytest.mark.parametrize(
    ("relief_result", "expected_status", "error_text"),
    (
        (
            SocketReliefResult(SocketReliefOutcome.CANCELLED),
            FlowStatus.CANCELLED,
            None,
        ),
        (
            SocketReliefResult(
                SocketReliefOutcome.FAILED,
                error="scripted support failure",
            ),
            FlowStatus.FAILED,
            "socket_inventory_relief_failed",
        ),
    ),
)
def test_socket_relief_cancel_and_failure_stop_before_another_world_boss_start(
    relief_result, expected_status, error_text
):
    inventory = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_SOCKET_INVENTORY_FULL,),
    )
    relief = SocketRelief((relief_result,))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[snapshot(2, base=SCREEN_LOBBY), snapshot(6, base=SCREEN_WORLD_BOSS)],
        transitions=[
            snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
            snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
            snapshot(5, base=SCREEN_WORLD_BOSS),
            inventory,
            snapshot(8, base=SCREEN_SOCKET),
        ],
        socket_relief=relief,
    )

    result = flow.run()

    assert result.status is expected_status
    assert (error_text is None) or error_text in result.error
    assert [call[0] for call in driver.calls].count("world_boss.start") == 1


def test_positive_socket_allowance_is_fresh_for_each_run():
    inventory = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_SOCKET_INVENTORY_FULL,),
    )
    transition_cycle = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        snapshot(5, base=SCREEN_WORLD_BOSS),
        inventory,
        snapshot(8, base=SCREEN_SOCKET),
        snapshot(10, base=SCREEN_WORLD_BOSS, overlays=(POPUP_SOCKET_INVENTORY_FULL,)),
        snapshot(11, base=SCREEN_WORLD_BOSS),
    ]
    relief = SocketRelief((
        SocketReliefResult(
            SocketReliefOutcome.NO_RELIEF_AVAILABLE,
            final_snapshot=snapshot(9, base=SCREEN_WORLD_BOSS),
        ),
        SocketReliefResult(
            SocketReliefOutcome.NO_RELIEF_AVAILABLE,
            final_snapshot=snapshot(19, base=SCREEN_WORLD_BOSS),
        ),
    ))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[
            snapshot(2, base=SCREEN_LOBBY),
            snapshot(6, base=SCREEN_WORLD_BOSS),
            snapshot(12, base=SCREEN_LOBBY),
            snapshot(16, base=SCREEN_WORLD_BOSS),
        ],
        transitions=transition_cycle + transition_cycle,
        socket_relief=relief,
    )

    first = flow.run()
    second = flow.run()

    assert first.status is second.status is FlowStatus.COMPLETED
    names = [call[0] for call in driver.calls]
    assert names.count("world_boss.accept_inventory_full") == 2
    assert names.count("world_boss.reject_inventory_full") == 2
    assert len(relief.calls) == 2


def test_bag_full_after_start_closes_x_and_completes_for_character():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    main = snapshot(6, base=SCREEN_WORLD_BOSS)
    bag_full = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,),
    )
    combine = snapshot(8, base=SCREEN_COMBINE, overlays=(MODE_COMBINE_FUSE,))
    second_bag_full = snapshot(
        10,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,),
    )
    returned = snapshot(11, base=SCREEN_WORLD_BOSS)
    relief = EquipmentCombineRelief((EquipmentCombineReliefResult(
        EquipmentCombineReliefOutcome.NO_RELIEF_AVAILABLE,
        final_snapshot=snapshot(9, base=SCREEN_WORLD_BOSS),
    ),))
    transitions = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        snapshot(5, base=SCREEN_WORLD_BOSS),
        bag_full,
        combine,
        second_bag_full,
        returned,
    ]
    auto = Mock()
    flow, observer, facts, _, events, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[lobby, main],
        transitions=transitions,
        auto=auto,
        equipment_combine_relief=relief,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.bag_full
    assert result.event_count(WORLD_BOSS_BAG_FULL) == 1
    assert isinstance(driver.calls[4][1], OpenEquipmentCombine)
    assert driver.calls[-1][0] == "world_boss.dismiss_bag_full"
    assert isinstance(driver.calls[-1][1], DismissWorldBossBagFull)
    assert all(item[0] != "timer" for item in facts.trace)
    assert observer.observes == []
    auto.ensure_on.assert_not_called()
    assert any(name == WORLD_BOSS_BAG_FULL for name, _ in events.records)
    assert any(
        name == "world_boss.equipment_combine_relief.started"
        for name, _ in events.records
    )
    assert any(
        name == "world_boss.equipment_combine_relief.finished"
        for name, _ in events.records
    )
    assert len(relief.calls) == 1
    assert isinstance(relief.calls[0][0].action, ExitCombine)
    assert relief.calls[0][0].expected_return_state == SCREEN_WORLD_BOSS


def test_bag_full_close_failure_is_structured_and_does_not_claim_completion():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    main = snapshot(6, base=SCREEN_WORLD_BOSS)
    bag_full = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,),
    )
    transitions = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        snapshot(5, base=SCREEN_WORLD_BOSS),
        bag_full,
        snapshot(8, base=SCREEN_COMBINE, overlays=(MODE_COMBINE_FUSE,)),
        snapshot(10, base=SCREEN_WORLD_BOSS, overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,)),
        bag_full,
    ]
    outcomes = [
        VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
        VerifiedTransitionOutcome.RETRY_GUARD_REJECTED,
    ]
    driver = Transitions(transitions, outcomes)
    events = Events()
    flow = WorldBossFlow(
        Observer(waits=[lobby, main]),
        Mock(),
        Facts(fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY)),
        Mock(),
        events,
        socket_relief=SocketRelief(),
        equipment_combine_relief=EquipmentCombineRelief((EquipmentCombineReliefResult(
            EquipmentCombineReliefOutcome.RELIEVED,
            final_snapshot=snapshot(9, base=SCREEN_WORLD_BOSS),
        ),)),
        verified_transition=driver,
        stable_for=0,
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert "world_boss.dismiss_bag_full_failed" in result.error
    assert not any(name == "world_boss.completed" for name, _ in events.records)


def test_positive_equipment_allowance_is_fresh_for_each_run():
    bag_full = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,),
    )
    transition_cycle = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        snapshot(5, base=SCREEN_WORLD_BOSS),
        bag_full,
        snapshot(8, base=SCREEN_COMBINE, overlays=(MODE_COMBINE_FUSE,)),
        snapshot(10, base=SCREEN_WORLD_BOSS, overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,)),
        snapshot(11, base=SCREEN_WORLD_BOSS),
    ]
    relief = EquipmentCombineRelief((
        EquipmentCombineReliefResult(
            EquipmentCombineReliefOutcome.NO_RELIEF_AVAILABLE,
            final_snapshot=snapshot(9, base=SCREEN_WORLD_BOSS),
        ),
        EquipmentCombineReliefResult(
            EquipmentCombineReliefOutcome.RELIEVED,
            final_snapshot=snapshot(19, base=SCREEN_WORLD_BOSS),
        ),
    ))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[
            snapshot(2, base=SCREEN_LOBBY),
            snapshot(6, base=SCREEN_WORLD_BOSS),
            snapshot(12, base=SCREEN_LOBBY),
            snapshot(16, base=SCREEN_WORLD_BOSS),
        ],
        transitions=transition_cycle + transition_cycle,
        equipment_combine_relief=relief,
    )

    first = flow.run()
    second = flow.run()

    assert first.status is second.status is FlowStatus.COMPLETED
    names = [call[0] for call in driver.calls]
    assert names.count("world_boss.open_equipment_combine") == 2
    assert names.count("world_boss.dismiss_bag_full") == 2
    assert len(relief.calls) == 2


@pytest.mark.parametrize(
    ("relief_outcome", "expected_status", "error_text"),
    (
        (EquipmentCombineReliefOutcome.CANCELLED, FlowStatus.CANCELLED, None),
        (EquipmentCombineReliefOutcome.FAILED, FlowStatus.FAILED, "equipment_combine_relief_failed"),
    ),
)
def test_equipment_combine_relief_cancel_and_failure_stop_before_another_start(
    relief_outcome, expected_status, error_text
):
    bag_full = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_EQUIPMENT_INVENTORY_FULL,),
    )
    relief = EquipmentCombineRelief((EquipmentCombineReliefResult(
        relief_outcome,
        final_snapshot=snapshot(8, base=SCREEN_COMBINE, overlays=(MODE_COMBINE_FUSE,)),
        error="scripted" if relief_outcome is EquipmentCombineReliefOutcome.FAILED else None,
    ),))
    flow, _, _, _, _, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[snapshot(2, base=SCREEN_LOBBY), snapshot(6, base=SCREEN_WORLD_BOSS)],
        transitions=[
            snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
            snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
            snapshot(5, base=SCREEN_WORLD_BOSS),
            bag_full,
            snapshot(8, base=SCREEN_COMBINE, overlays=(MODE_COMBINE_FUSE,)),
        ],
        equipment_combine_relief=relief,
    )

    result = flow.run()

    assert result.status is expected_status
    assert error_text is None or error_text in result.error
    assert [call[0] for call in driver.calls].count("world_boss.start") == 1


@pytest.mark.parametrize(
    ("previous", "failure_index", "expected_name"),
    (
        (False, 0, "world_boss.open_battle_mode_select"),
        (False, 1, "world_boss.open_selector"),
        (False, 2, "world_boss.select_available"),
        (True, 3, "world_boss.ack_previous_rewards"),
        (False, 3, "world_boss.start"),
    ),
)
def test_each_navigation_or_ack_failure_aborts_without_later_input(
    previous, failure_index, expected_name
):
    waits, _, snapshots = happy_inputs(previous=previous)
    outcomes = [VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT] * len(snapshots)
    outcomes[failure_index] = VerifiedTransitionOutcome.RETRY_GUARD_REJECTED
    driver = Transitions(snapshots[: failure_index + 1], outcomes[: failure_index + 1])
    flow = WorldBossFlow(
        Observer(waits=waits), Mock(),
        Facts(fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY)),
        Mock(), Events(), socket_relief=SocketRelief(),
        equipment_combine_relief=EquipmentCombineRelief(),
        verified_transition=driver, stable_for=0,
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert expected_name in result.error
    assert len(driver.calls) == failure_index + 1


def test_raid_complete_ack_failure_is_structured_and_never_claims_world_boss():
    waits, observes, snapshots = happy_inputs()
    outcomes = [VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT] * len(snapshots)
    outcomes[-1] = VerifiedTransitionOutcome.RETRY_GUARD_REJECTED
    driver = Transitions(snapshots, outcomes)
    auto = Mock(ensure_on=Mock(return_value=auto_result()))
    fake = FakeTime()
    policy = WorldBossWaitPolicy()
    flow = WorldBossFlow(
        Observer(waits=waits, observes=observes), Mock(),
        Facts(
            fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY),
            fact_result("battle.timer_remaining", 20, 9, SCREEN_WORLD_BOSS_BATTLE),
        ),
        auto, Events(), socket_relief=SocketRelief(),
        equipment_combine_relief=EquipmentCombineRelief(),
        verified_transition=driver, stable_for=0,
        wait_policy=policy,
        clock=fake.clock,
        initial_wait=ControlledWait(
            check_interval=1, clock=fake.clock, sleeper=fake.sleep
        ),
        completion_wait=ControlledWait(
            check_interval=policy.completion_poll_interval,
            clock=fake.clock,
            sleeper=fake.sleep,
        ),
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert "world_boss.continue_after_raid_failed" in result.error
    assert result.raid_complete_detected


@pytest.mark.parametrize("status", [
    EnsureAutoBattleStatus.FAILURE,
    EnsureAutoBattleStatus.CONTEXT_MISMATCH,
    EnsureAutoBattleStatus.TIMEOUT,
])
def test_auto_battle_failure_stops_before_timer_and_long_wait(status):
    waits, _, transitions = happy_inputs()
    transitions = transitions[:-1]
    auto = Mock()
    auto.ensure_on.return_value = auto_result(status=status)
    flow, observer, facts, _, _, _ = build_flow(
        sapphire_read=fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY),
        waits=waits,
        transitions=transitions,
        auto=auto,
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert result.error.startswith("auto_battle_failed")
    assert all(item[0] != "timer" for item in facts.trace)
    assert observer.observes == []


def test_timer_failure_stops_before_controlled_wait():
    waits, _, transitions = happy_inputs()
    flow, observer, _, _, _, _ = build_flow(
        sapphire_read=fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY),
        timer_read=FactReadResult(FactReadStatus.UNREADABLE),
        waits=waits,
        transitions=transitions[:-1],
        auto=Mock(ensure_on=Mock(return_value=auto_result())),
    )

    result = flow.run()

    assert result.status is FlowStatus.FAILED
    assert result.error.startswith("timer_fact_failed")
    assert observer.observes == []


@pytest.mark.parametrize(
    ("outcome", "expected_error"),
    (
        (VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE, None),
        (VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY, None),
        (VerifiedTransitionOutcome.RETRY_GUARD_REJECTED, "retry_guard_rejected"),
        (VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED, "attempts_exhausted"),
    ),
)
def test_navigation_transition_outcomes_are_preserved(outcome, expected_error):
    lobby = snapshot(2, base=SCREEN_LOBBY)
    battle_modes = snapshot(3, base=SCREEN_BATTLE_MODE_SELECT)
    unknown = snapshot(4)
    driver = Transitions(
        [battle_modes, unknown],
        outcomes=[outcome, VerifiedTransitionOutcome.RETRY_GUARD_REJECTED],
    )
    observer = Observer(waits=[lobby])
    flow = WorldBossFlow(
        observer, Mock(),
        Facts(fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY)),
        Mock(), Events(), socket_relief=SocketRelief(),
        equipment_combine_relief=EquipmentCombineRelief(),
        verified_transition=driver, stable_for=0,
    )

    result = flow.run()

    if expected_error is None:
        assert result.error is not None
        assert result.transition_outcomes[0][1] == outcome.value
    else:
        assert expected_error in result.error
        assert len(driver.calls) == 1


def test_unknown_is_not_a_retry_guard_for_any_world_boss_transition():
    unknown = snapshot(4)
    lobby = snapshot(2, base=SCREEN_LOBBY)
    battle_modes = snapshot(3, base=SCREEN_BATTLE_MODE_SELECT)
    driver = Transitions([battle_modes])
    flow = WorldBossFlow(
        Observer(waits=[lobby]), Mock(),
        Facts(fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY)),
        Mock(), Events(), socket_relief=SocketRelief(),
        equipment_combine_relief=EquipmentCombineRelief(),
        verified_transition=driver, stable_for=0,
    )
    flow.run()

    retryable = driver.calls[0][3]["retryable_from"]
    assert not retryable(unknown)


class TimedObserver:
    def __init__(
        self,
        fake,
        raid_at=None,
        unknown_until=None,
        always_unknown=False,
        raid_base=SCREEN_WORLD_BOSS_BATTLE,
    ):
        self.fake = fake
        self.raid_at = raid_at
        self.unknown_until = unknown_until
        self.always_unknown = always_unknown
        self.raid_base = raid_base
        self.observe_times = []

    def observe(self):
        self.observe_times.append(self.fake.current)
        sequence = int(self.fake.current * 10) + 1
        if self.raid_at is not None and self.fake.current >= self.raid_at:
            evidence = Observation(
                LANDMARK_WORLD_BOSS_RAID_COMPLETE_TITLE,
                0.95,
                ObservationSource.LOCAL_CV,
            )
            return snapshot(
                sequence,
                base=self.raid_base,
                overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,),
                semantic_observations=(evidence,),
            )
        if self.always_unknown or (
            self.unknown_until is not None and self.fake.current < self.unknown_until
        ):
            return snapshot(sequence)
        return snapshot(sequence, base=SCREEN_WORLD_BOSS_BATTLE)

    def wait_until(self, *args, **kwargs):
        raise AssertionError("not used")


def raid_wait_flow(*, raid_at=None, unknown_until=None, always_unknown=False,
                   cancel=lambda: False, policy=None,
                   raid_base=SCREEN_WORLD_BOSS_BATTLE):
    fake = FakeTime()
    policy = policy or WorldBossWaitPolicy()
    observer = TimedObserver(
        fake, raid_at, unknown_until, always_unknown, raid_base
    )
    actions = Mock()
    auto = Mock(ensure_on=Mock())
    flow = WorldBossFlow(
        observer, actions, Mock(read_sapphires=Mock(), read_timer_remaining=Mock()),
        auto, Events(), socket_relief=SocketRelief(),
        equipment_combine_relief=EquipmentCombineRelief(), cancel_requested=cancel,
        wait_policy=policy, clock=fake.clock,
        initial_wait=ControlledWait(
            check_interval=1, clock=fake.clock, sleeper=fake.sleep
        ),
        completion_wait=ControlledWait(
            check_interval=policy.completion_poll_interval,
            clock=fake.clock,
            sleeper=fake.sleep,
        ),
        verified_transition=Mock(execute=Mock()),
    )
    return flow, fake, observer, actions, auto


def test_timer_sixty_waits_sixty_five_without_perception_then_polls_once():
    flow, fake, observer, actions, auto = raid_wait_flow(raid_at=65)

    result, raid = flow._wait_for_raid_complete(60)

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert result.elapsed == pytest.approx(65)
    assert observer.observe_times == [65]
    assert raid is not None
    actions.execute.assert_not_called()
    auto.ensure_on.assert_not_called()


def test_final_polling_runs_each_second_and_accepts_late_raid_complete():
    flow, _, observer, actions, _ = raid_wait_flow(
        raid_at=68,
        unknown_until=68,
    )

    result, raid = flow._wait_for_raid_complete(60)

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert result.elapsed == pytest.approx(68)
    assert observer.observe_times == [65, 66, 67, 68]
    assert result.poll_count == 4
    assert raid is not None
    actions.execute.assert_not_called()


@pytest.mark.parametrize("raid_base", [None, SCREEN_LOBBY])
def test_raid_complete_overlay_succeeds_independently_of_base_state(raid_base):
    flow, _, observer, actions, _ = raid_wait_flow(
        raid_at=65,
        raid_base=raid_base,
    )

    result, raid = flow._wait_for_raid_complete(60)

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert raid is not None
    assert OVERLAY_WORLD_BOSS_RAID_COMPLETE in raid.state.overlays
    assert observer.observe_times == [65]
    actions.execute.assert_not_called()


def test_persistent_unknown_times_out_without_input_or_recovery():
    flow, _, observer, actions, auto = raid_wait_flow(always_unknown=True)

    result, raid = flow._wait_for_raid_complete(60)

    assert result.outcome is ControlledWaitOutcome.TIMEOUT
    assert result.elapsed == pytest.approx(90)
    assert observer.observe_times[0] == 65
    assert observer.observe_times[-1] == 90
    assert raid is not None and raid.state.status is ResolutionStatus.UNKNOWN
    actions.execute.assert_not_called()
    auto.ensure_on.assert_not_called()

    finished = [
        fields
        for name, fields in flow.events.records
        if name == "world_boss.wait.finished"
    ][-1]
    assert finished["completion_timeout"] == 25
    assert finished["poll_count"] == len(observer.observe_times)
    assert finished["unknown_count"] == len(observer.observe_times)
    assert finished["last_base_state"] == ResolutionStatus.UNKNOWN.value
    assert finished["last_overlays"] == ()
    assert finished["last_sequence"] == 901
    assert finished["raid_complete_max_confidence"] == 0


def test_wait_policy_exposes_configurable_margin_poll_and_bounded_timeout():
    policy = WorldBossWaitPolicy()

    assert policy.post_timer_completion_margin == 5
    assert policy.completion_poll_interval == 1
    assert policy.bounded_completion_timeout == 25


def test_wait_telemetry_records_timer_margin_poll_start_detection_and_elapsed():
    policy = WorldBossWaitPolicy(post_timer_margin=2)
    flow, _, _, _, _ = raid_wait_flow(raid_at=8, policy=policy)

    result, _ = flow._wait_for_raid_complete(5)

    finished = [fields for name, fields in flow.events.records if name == "world_boss.wait.finished"][-1]
    assert result.succeeded
    assert finished["timer_initial"] == 5
    assert finished["initial_wait"] == 7
    assert finished["post_timer_margin"] == 2
    assert finished["polling_started_at"] == 7
    assert finished["completion_poll_interval"] == 1
    assert finished["completion_timeout"] == 25
    assert finished["raid_complete_detected_at"] == 8
    assert finished["actual_elapsed"] == 8
    assert finished["poll_count"] == 2
    assert finished["last_base_state"] == SCREEN_WORLD_BOSS_BATTLE
    assert finished["last_overlays"] == (OVERLAY_WORLD_BOSS_RAID_COMPLETE,)
    assert finished["raid_complete_max_confidence"] == pytest.approx(0.95)

    polls = [
        fields
        for name, fields in flow.events.records
        if name == "world_boss.wait.poll"
    ]
    assert [item["poll_index"] for item in polls] == [1, 2]
    assert polls[-1]["raid_complete_detected"] is True
    assert polls[-1]["raid_complete_confidence"] == pytest.approx(0.95)


def test_controlled_wait_propagates_cancellation_without_failure():
    flow, _, observer, actions, _ = raid_wait_flow()
    # Bind cancellation to the flow's actual injected clock.
    flow.cancel_requested = lambda: flow.clock() >= 2

    result, _ = flow._wait_for_raid_complete(10)

    assert result.outcome is ControlledWaitOutcome.CANCELLED
    assert observer.observe_times == []
    actions.execute.assert_not_called()


def test_known_non_completion_state_also_waits_until_timeout():
    flow, _, observer, actions, _ = raid_wait_flow()

    result, _ = flow._wait_for_raid_complete(5)

    assert result.outcome is ControlledWaitOutcome.TIMEOUT
    assert observer.observe_times[0] == 10
    assert observer.observe_times[-1] == 35
    actions.execute.assert_not_called()


def test_world_boss_contract_and_boundaries_are_explicit():
    contract = WorldBossFlow.contract
    assert contract.precondition.name == SCREEN_LOBBY
    assert {item.name for item in contract.successful_postconditions} == {
        SCREEN_LOBBY, SCREEN_WORLD_BOSS,
    }
    source = Path("bot/world_boss_flow.py").read_text(encoding="utf-8")
    assert "RuntimeFactReader" not in source
    assert "read_sapphires" in source and "read_timer_remaining" in source
    assert "ControlledWait" in source
    assert "VerifiedTransition" in source
    assert "ActionExecutor" in source
    assert "Ocr" not in source
    assert "AdbClient" not in source
    assert "time.sleep" not in source
    assert "AutoRepeat" not in source
