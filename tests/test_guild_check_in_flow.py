from dataclasses import dataclass

import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_GUILD_ATTENDANCE_ACTIVE,
    STATUS_GUILD_ATTENDANCE_COMPLETED,
    STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
)
from bot.flow_contracts import FlowScope, FlowStatus
from bot.guild_check_in_flow import (
    GUILD_CHECK_IN_COMPLETED,
    GUILD_CHECK_IN_NOOP,
    GUILD_CHECK_IN_TAP_EXECUTED,
    GuildCheckInFlow,
)
from bot.observations import ObservationBatch
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import CheckInGuildAttendance
from bot.state import ResolutionStatus, ResolvedState


@dataclass
class WaitCall:
    after_sequence: int
    timeout: float
    stable_for: float


class ScriptedObserver:
    def __init__(self, initial, script=()):
        self.initial = initial
        self.script = script
        self.calls = []

    def observe(self):
        return self.initial

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        cancel_requested=None,
        stable_for=0.0,
    ):
        self.calls.append(WaitCall(after_sequence, timeout, stable_for))
        if isinstance(self.script, BaseException):
            raise self.script
        stable_since = None
        last = None
        for item in self.script:
            last = item
            assert item.sequence > after_sequence
            if cancel_requested is not None and cancel_requested():
                raise RuntimeWaitCancelled("cancelled")
            if abort_if is not None and abort_if(item):
                raise RuntimeWaitAborted(item)
            if condition(item):
                if stable_since is None:
                    stable_since = item.timestamp
                if item.timestamp - stable_since >= stable_for:
                    return item
            else:
                stable_since = None
        raise RuntimeWaitTimeout(
            after_sequence=after_sequence,
            timeout=timeout,
            last_snapshot=last,
        )


class Actions:
    def __init__(self):
        self.items = []

    def execute(self, action, geometry):
        self.items.append(action)


class Events:
    def __init__(self):
        self.items = []

    def record(self, event, **fields):
        self.items.append((event, fields))


def snapshot(sequence, timestamp, *, base=SCREEN_GUILD, overlays=(), status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def run_flow(initial, script=(), **kwargs):
    observer = ScriptedObserver(initial, script)
    actions = Actions()
    events = Events()
    result = GuildCheckInFlow(observer, actions, events, **kwargs).run()
    return result, actions.items, events.items, observer


def test_contract_is_guild_to_guild_per_character():
    assert GuildCheckInFlow.scope is FlowScope.PER_CHARACTER
    assert GuildCheckInFlow.contract.precondition.name == SCREEN_GUILD
    assert tuple(
        item.name for item in GuildCheckInFlow.contract.successful_postconditions
    ) == (SCREEN_GUILD,)


def test_already_completed_is_successful_noop_without_input():
    completed = snapshot(
        1,
        1.0,
        overlays=(STATUS_GUILD_ATTENDANCE_COMPLETED,),
    )

    result, actions, _, observer = run_flow(completed)

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert result.attendance_completed
    assert result.event_count(GUILD_CHECK_IN_NOOP) == 1
    assert actions == []
    assert observer.calls == []


def test_active_attendance_taps_once_and_requires_stable_completed_state():
    active = snapshot(
        1,
        1.0,
        overlays=(
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        ),
    )
    completed_a = snapshot(
        2,
        2.0,
        overlays=(
            STATUS_GUILD_ATTENDANCE_COMPLETED,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        ),
    )
    completed_b = snapshot(
        3,
        2.8,
        overlays=(
            STATUS_GUILD_ATTENDANCE_COMPLETED,
            STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,
        ),
    )

    result, actions, _, observer = run_flow(active, (completed_a, completed_b))

    assert result.status is FlowStatus.COMPLETED
    assert result.tap_executed
    assert result.attendance_completed
    assert actions == [CheckInGuildAttendance()]
    assert result.event_count(GUILD_CHECK_IN_TAP_EXECUTED) == 1
    assert result.event_count(GUILD_CHECK_IN_COMPLETED) == 1
    assert observer.calls == [WaitCall(1, 10.0, 0.75)]


def test_daily_badge_without_attendance_never_authorizes_input():
    daily_only = snapshot(
        1,
        1.0,
        overlays=(STATUS_GUILD_ATTENDANCE_DAILY_ACTIVE,),
    )

    result, actions, _, _ = run_flow(daily_only)

    assert result.status is FlowStatus.FAILED
    assert actions == []


def test_completion_timeout_fails_without_second_tap_or_success_event():
    active = snapshot(1, 1.0, overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,))
    still_active = snapshot(2, 9.0, overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,))

    result, actions, _, _ = run_flow(active, (still_active,))

    assert result.status is FlowStatus.FAILED
    assert result.tap_executed
    assert actions == [CheckInGuildAttendance()]
    assert result.event_count(GUILD_CHECK_IN_COMPLETED) == 0


def test_cancellation_during_completion_wait_propagates_without_retry():
    active = snapshot(1, 1.0, overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,))
    cancelled = RuntimeWaitCancelled("cancelled")

    result, actions, _, _ = run_flow(active, cancelled)

    assert result.status is FlowStatus.CANCELLED
    assert result.tap_executed
    assert actions == [CheckInGuildAttendance()]


def test_cancellation_after_observation_prevents_attendance_input():
    active = snapshot(1, 1.0, overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,))
    cancellations = iter((False, True))

    result, actions, _, _ = run_flow(
        active,
        cancel_requested=lambda: next(cancellations),
    )

    assert result.status is FlowStatus.CANCELLED
    assert actions == []


def test_incompatible_initial_or_transition_state_fails_conservatively():
    contradictory = snapshot(
        1,
        1.0,
        overlays=(
            STATUS_GUILD_ATTENDANCE_ACTIVE,
            STATUS_GUILD_ATTENDANCE_COMPLETED,
        ),
    )
    initial_result, initial_actions, _, _ = run_flow(contradictory)

    active = snapshot(2, 2.0, overlays=(STATUS_GUILD_ATTENDANCE_ACTIVE,))
    lobby = snapshot(3, 3.0, base=SCREEN_LOBBY)
    transition_result, transition_actions, _, _ = run_flow(active, (lobby,))

    assert initial_result.status is FlowStatus.FAILED
    assert initial_actions == []
    assert transition_result.status is FlowStatus.FAILED
    assert transition_actions == [CheckInGuildAttendance()]
    assert transition_result.event_count(GUILD_CHECK_IN_COMPLETED) == 0


def test_non_guild_precondition_never_authorizes_attendance_input():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(lobby)

    assert result.status is FlowStatus.FAILED
    assert actions == []
