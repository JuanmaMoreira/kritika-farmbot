from pathlib import Path

import pytest

from bot.controlled_wait import ControlledWait, ControlledWaitOutcome


class FakeTime:
    def __init__(self, current=0.0):
        self.current = float(current)
        self.sleeps = []

    def clock(self):
        return self.current

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.current += duration


def test_duration_uses_monotonic_bound_and_configurable_interval():
    fake = FakeTime(10.0)
    waiter = ControlledWait(
        check_interval=2.0,
        clock=fake.clock,
        sleeper=fake.sleep,
    )

    result = waiter.wait(expected_duration=5.0)

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert result.elapsed == pytest.approx(5.0)
    assert fake.sleeps == [2.0, 2.0, 1.0]


def test_completion_condition_can_finish_early_with_periodic_polling():
    fake = FakeTime()
    checks = []
    waiter = ControlledWait(
        check_interval=1.0,
        clock=fake.clock,
        sleeper=fake.sleep,
    )

    def completed():
        checks.append(fake.current)
        return fake.current >= 2.0

    result = waiter.wait(
        expected_duration=10.0,
        completion_condition=completed,
    )

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert result.elapsed == pytest.approx(2.0)
    assert result.poll_count == 3
    assert checks == [0.0, 1.0, 2.0]


def test_multiple_unobserved_checks_are_passive_until_late_completion():
    fake = FakeTime()
    observations = iter((False, False, False, True))
    waiter = ControlledWait(
        check_interval=1.0,
        clock=fake.clock,
        sleeper=fake.sleep,
    )

    result = waiter.wait(
        expected_duration=10.0,
        completion_condition=lambda: next(observations),
    )

    assert result.outcome is ControlledWaitOutcome.COMPLETED
    assert result.elapsed == pytest.approx(3.0)
    assert result.poll_count == 4


def test_cancellation_is_checked_on_each_wake():
    fake = FakeTime()
    waiter = ControlledWait(
        check_interval=1.0,
        clock=fake.clock,
        sleeper=fake.sleep,
    )

    result = waiter.wait(
        deadline=5.0,
        cancel_requested=lambda: fake.current >= 2.0,
    )

    assert result.outcome is ControlledWaitOutcome.CANCELLED
    assert fake.sleeps == [1.0, 1.0]


def test_unsatisfied_condition_times_out_at_deadline():
    fake = FakeTime(4.0)
    waiter = ControlledWait(
        check_interval=3.0,
        clock=fake.clock,
        sleeper=fake.sleep,
    )

    result = waiter.wait(deadline=9.0, completion_condition=lambda: False)

    assert result.outcome is ControlledWaitOutcome.TIMEOUT
    assert result.elapsed == pytest.approx(5.0)
    assert fake.sleeps == [3.0, 2.0]


def test_explicit_terminal_condition_has_distinct_outcome():
    fake = FakeTime()
    waiter = ControlledWait(
        check_interval=1.0,
        clock=fake.clock,
        sleeper=fake.sleep,
    )

    result = waiter.wait(
        expected_duration=10.0,
        completion_condition=lambda: False,
        terminal_condition=lambda: fake.current >= 2.0,
    )

    assert result.outcome is ControlledWaitOutcome.TERMINATED
    assert result.elapsed == pytest.approx(2.0)
    assert result.poll_count == 3


def test_zero_duration_is_immediate_and_does_not_busy_loop():
    fake = FakeTime()
    waiter = ControlledWait(clock=fake.clock, sleeper=fake.sleep)

    elapsed = waiter.wait(expected_duration=0.0)
    timed_out = waiter.wait(
        expected_duration=0.0,
        completion_condition=lambda: False,
    )

    assert elapsed.outcome is ControlledWaitOutcome.COMPLETED
    assert timed_out.outcome is ControlledWaitOutcome.TIMEOUT
    assert fake.sleeps == []


def test_callback_failure_is_structured():
    fake = FakeTime()
    waiter = ControlledWait(clock=fake.clock, sleeper=fake.sleep)

    def fail():
        raise RuntimeError("observer failed")

    result = waiter.wait(expected_duration=1.0, completion_condition=fail)

    assert result.outcome is ControlledWaitOutcome.FAILED
    assert result.error == "RuntimeError: observer failed"


def test_controlled_wait_has_no_physical_input_dependency():
    source = Path("bot/controlled_wait.py").read_text(encoding="utf-8")

    assert "ActionExecutor" not in source
    assert "AdbClient" not in source
