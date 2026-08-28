from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.auto_battle import AutoBattleState, EnsureAutoBattleStatus
from bot.capture import FrameSnapshot
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
from bot.controlled_wait import ControlledWait, ControlledWaitOutcome
from bot.flow_contracts import FlowStatus
from bot.observations import ObservationBatch, ObservationSource
from bot.runtime_facts import (
    FactEvidence,
    FactQuality,
    FactReadResult,
    FactReadStatus,
    RuntimeFact,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import (
    VerifiedTransitionOutcome,
    VerifiedTransitionResult,
)
from bot.world_boss_flow import (
    WORLD_BOSS_INSUFFICIENT_SAPPHIRES,
    WORLD_BOSS_PREVIOUS_REWARDS,
    WORLD_BOSS_INVENTORY_FULL,
    WorldBossFlow,
    WorldBossWaitPolicy,
)


def snapshot(sequence, *, base=None, overlays=(), status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    timestamp = float(sequence)
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp),
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
               fake_time=None, wait_policy=None):
    trace = trace if trace is not None else []
    observer = Observer(waits, observes, trace)
    facts = Facts(sapphire_read, timer_read, trace)
    events = Events()
    transition_driver = Transitions(transitions)
    auto = auto or Mock()
    if not hasattr(auto, "ensure_on"):
        auto.ensure_on = Mock(return_value=auto_result())
    kwargs = {}
    if fake_time is not None:
        policy = wait_policy or WorldBossWaitPolicy(
            active_window=3, final_margin=2,
            early_check_interval=2, final_check_interval=1,
        )
        kwargs.update(
            wait_policy=policy,
            clock=fake_time.clock,
            early_wait=ControlledWait(
                check_interval=policy.early_check_interval,
                clock=fake_time.clock,
                sleeper=fake_time.sleep,
            ),
            final_wait=ControlledWait(
                check_interval=policy.final_check_interval,
                clock=fake_time.clock,
                sleeper=fake_time.sleep,
            ),
        )
    flow = WorldBossFlow(
        observer, Mock(), facts, auto, events,
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


def test_inventory_full_after_start_rejects_no_and_completes_for_character():
    lobby = snapshot(2, base=SCREEN_LOBBY)
    main = snapshot(6, base=SCREEN_WORLD_BOSS)
    inventory = snapshot(
        7,
        base=SCREEN_WORLD_BOSS,
        overlays=(POPUP_WORLD_BOSS_INVENTORY_FULL,),
    )
    returned = snapshot(8, base=SCREEN_WORLD_BOSS)
    transitions = [
        snapshot(3, base=SCREEN_BATTLE_MODE_SELECT),
        snapshot(4, overlays=(OVERLAY_WORLD_BOSS_SELECT_BOSS,)),
        snapshot(5, base=SCREEN_WORLD_BOSS),
        inventory,
        returned,
    ]
    auto = Mock()
    flow, observer, facts, _, events, driver = build_flow(
        sapphire_read=fact_result("resource.sapphires", 10, 1, SCREEN_LOBBY),
        waits=[lobby, main],
        transitions=transitions,
        auto=auto,
    )

    result = flow.run()

    assert result.status is FlowStatus.COMPLETED
    assert result.inventory_full
    assert result.event_count(WORLD_BOSS_INVENTORY_FULL) == 1
    assert driver.calls[-1][0] == "world_boss.reject_inventory_full"
    assert all(item[0] != "timer" for item in facts.trace)
    assert observer.observes == []
    auto.ensure_on.assert_not_called()
    assert any(name == WORLD_BOSS_INVENTORY_FULL for name, _ in events.records)


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
        Mock(), Events(), verified_transition=driver, stable_for=0,
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
    flow = WorldBossFlow(
        Observer(waits=waits, observes=observes), Mock(),
        Facts(
            fact_result("resource.sapphires", 5, 1, SCREEN_LOBBY),
            fact_result("battle.timer_remaining", 20, 9, SCREEN_WORLD_BOSS_BATTLE),
        ),
        auto, Events(), verified_transition=driver, stable_for=0,
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
        Mock(), Events(), verified_transition=driver, stable_for=0,
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
        Mock(), Events(), verified_transition=driver, stable_for=0,
    )
    flow.run()

    retryable = driver.calls[0][3]["retryable_from"]
    assert not retryable(unknown)


class TimedObserver:
    def __init__(self, fake, raid_at=None, unexpected_at=None):
        self.fake = fake
        self.raid_at = raid_at
        self.unexpected_at = unexpected_at

    def observe(self):
        sequence = int(self.fake.current * 10) + 1
        if self.unexpected_at is not None and self.fake.current >= self.unexpected_at:
            return snapshot(sequence, base=SCREEN_LOBBY)
        if self.raid_at is not None and self.fake.current >= self.raid_at:
            return snapshot(sequence, base=SCREEN_WORLD_BOSS_BATTLE,
                            overlays=(OVERLAY_WORLD_BOSS_RAID_COMPLETE,))
        return snapshot(sequence, base=SCREEN_WORLD_BOSS_BATTLE)

    def wait_until(self, *args, **kwargs):
        raise AssertionError("not used")


def raid_wait_flow(*, raid_at=None, unexpected_at=None, cancel=lambda: False):
    fake = FakeTime()
    policy = WorldBossWaitPolicy(
        active_window=3, final_margin=2,
        early_check_interval=2, final_check_interval=1,
    )
    observer = TimedObserver(fake, raid_at, unexpected_at)
    flow = WorldBossFlow(
        observer, Mock(), Mock(read_sapphires=Mock(), read_timer_remaining=Mock()),
        Mock(ensure_on=Mock()), Events(), cancel_requested=cancel,
        wait_policy=policy, clock=fake.clock,
        early_wait=ControlledWait(check_interval=2, clock=fake.clock, sleeper=fake.sleep),
        final_wait=ControlledWait(check_interval=1, clock=fake.clock, sleeper=fake.sleep),
        verified_transition=Mock(execute=Mock()),
    )
    return flow, fake


@pytest.mark.parametrize(
    ("timer", "raid_at", "expected_elapsed"),
    ((10, 2, 2), (5, 5, 5), (5, 7, 7)),
)
def test_controlled_wait_detects_early_deadline_and_post_zero_completion(
    timer, raid_at, expected_elapsed
):
    flow, _ = raid_wait_flow(raid_at=raid_at)

    result, raid = flow._wait_for_raid_complete(timer)

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert result.elapsed == pytest.approx(expected_elapsed)
    assert raid is not None


def test_controlled_wait_times_out_after_final_margin():
    flow, _ = raid_wait_flow()

    result, raid = flow._wait_for_raid_complete(5)

    assert result.outcome is ControlledWaitOutcome.TIMEOUT
    assert result.elapsed == pytest.approx(7)
    assert raid is not None and raid.state.overlays == ()


def test_controlled_wait_propagates_cancellation_without_failure():
    fake = FakeTime()
    flow, _ = raid_wait_flow(cancel=lambda: fake.current >= 2)
    # Bind cancellation to the flow's actual injected clock.
    flow.cancel_requested = lambda: flow.clock() >= 2

    result, _ = flow._wait_for_raid_complete(10)

    assert result.outcome is ControlledWaitOutcome.CANCELLED


def test_controlled_wait_reports_inequivocally_unexpected_state():
    flow, _ = raid_wait_flow(unexpected_at=1)

    result, _ = flow._wait_for_raid_complete(5)

    assert result.outcome is ControlledWaitOutcome.FAILED
    assert "unexpected battle state" in result.error


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
