from dataclasses import dataclass

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    SCREEN_FRIENDS,
    SCREEN_GUILD,
    SCREEN_LOBBY,
    STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,
)
from bot.flow_contracts import FlowScope, FlowStatus
from bot.observations import ObservationBatch
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    CloseFriends,
    OpenFriends,
    SendStaminaToAllFriends,
)
from bot.send_stamina_flow import (
    SEND_STAMINA_ALL_EXECUTED,
    SEND_STAMINA_COMPLETED,
    SEND_STAMINA_NOOP,
    SendStaminaFlow,
)
from bot.state import ResolutionStatus, ResolvedState


@dataclass
class WaitCall:
    after_sequence: int
    timeout: float
    stable_for: float


class ScriptedObserver:
    def __init__(self, initial, scripts=()):
        self.initial = initial
        self.scripts = list(scripts)
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
        script = self.scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        stable_since = None
        last = None
        for item in script:
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


def snapshot(sequence, timestamp, *, base, overlays=(), status=None):
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


def run_flow(initial, scripts=(), **kwargs):
    observer = ScriptedObserver(initial, scripts)
    actions = Actions()
    events = Events()
    result = SendStaminaFlow(observer, actions, events, **kwargs).run()
    return result, actions.items, events.items, observer


def stable_pair(first, second):
    return [first, second]


def friends(sequence, timestamp, *, daily_active):
    overlays = (
        (STATUS_FRIENDS_SEND_STAMINA_DAILY_ACTIVE,)
        if daily_active
        else ()
    )
    return snapshot(sequence, timestamp, base=SCREEN_FRIENDS, overlays=overlays)


def test_contract_is_lobby_to_lobby_per_character():
    assert SendStaminaFlow.scope is FlowScope.PER_CHARACTER
    assert SendStaminaFlow.contract.precondition.name == SCREEN_LOBBY
    assert tuple(
        item.name for item in SendStaminaFlow.contract.successful_postconditions
    ) == (SCREEN_LOBBY,)


def test_daily_absent_is_noop_without_all_and_closes_to_verified_lobby():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    opened_a = friends(2, 2.0, daily_active=False)
    opened_b = friends(3, 2.3, daily_active=False)
    returned_a = snapshot(4, 3.0, base=SCREEN_LOBBY)
    returned_b = snapshot(5, 3.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [stable_pair(opened_a, opened_b), stable_pair(returned_a, returned_b)],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op and result.daily_completed
    assert not result.all_executed
    assert result.event_count(SEND_STAMINA_NOOP) == 1
    assert actions == [OpenFriends(), CloseFriends()]
    assert observer.calls[-1] == WaitCall(3, 6.0, 0.25)


def test_daily_active_taps_all_once_and_requires_stable_disappearance():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    opened_a = friends(2, 2.0, daily_active=True)
    opened_b = friends(3, 2.3, daily_active=True)
    absent_once = friends(4, 2.5, daily_active=False)
    reappeared = friends(5, 2.7, daily_active=True)
    settled_a = friends(6, 2.9, daily_active=False)
    settled_b = friends(7, 3.7, daily_active=False)
    returned_a = snapshot(8, 4.0, base=SCREEN_LOBBY)
    returned_b = snapshot(9, 4.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            stable_pair(opened_a, opened_b),
            [absent_once, reappeared, settled_a, settled_b],
            stable_pair(returned_a, returned_b),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.all_executed and result.daily_completed
    assert not result.no_op
    assert actions == [
        OpenFriends(),
        SendStaminaToAllFriends(),
        CloseFriends(),
    ]
    assert actions.count(SendStaminaToAllFriends()) == 1
    assert result.event_count(SEND_STAMINA_ALL_EXECUTED) == 1
    assert result.event_count(SEND_STAMINA_COMPLETED) == 1
    assert observer.calls[1] == WaitCall(3, 3.0, 0.75)


def test_completion_timeout_fails_without_retry_or_close():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    opened = stable_pair(
        friends(2, 2.0, daily_active=True),
        friends(3, 2.3, daily_active=True),
    )
    still_active = [friends(4, 4.0, daily_active=True)]

    result, actions, events, _ = run_flow(lobby, [opened, still_active])

    assert result.status is FlowStatus.FAILED
    assert result.all_executed
    assert actions == [OpenFriends(), SendStaminaToAllFriends()]
    assert actions.count(SendStaminaToAllFriends()) == 1
    assert result.event_count(SEND_STAMINA_COMPLETED) == 0
    assert any(event == "send_stamina.failed" for event, _ in events)


def test_incompatible_precondition_or_completion_state_fails_conservatively():
    guild = snapshot(1, 1.0, base=SCREEN_GUILD)
    initial_result, initial_actions, _, _ = run_flow(guild)

    lobby = snapshot(2, 2.0, base=SCREEN_LOBBY)
    opened = stable_pair(
        friends(3, 3.0, daily_active=True),
        friends(4, 3.3, daily_active=True),
    )
    incompatible = [snapshot(5, 4.0, base=SCREEN_LOBBY)]
    transition_result, transition_actions, _, _ = run_flow(
        lobby,
        [opened, incompatible],
    )

    assert initial_result.status is FlowStatus.FAILED
    assert initial_actions == []
    assert transition_result.status is FlowStatus.FAILED
    assert transition_actions == [OpenFriends(), SendStaminaToAllFriends()]
    assert transition_result.event_count(SEND_STAMINA_COMPLETED) == 0


def test_cancellation_during_completion_wait_propagates_without_retry():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    opened = stable_pair(
        friends(2, 2.0, daily_active=True),
        friends(3, 2.3, daily_active=True),
    )

    result, actions, events, _ = run_flow(
        lobby,
        [opened, RuntimeWaitCancelled("cancelled")],
    )

    assert result.status is FlowStatus.CANCELLED
    assert result.all_executed
    assert actions == [OpenFriends(), SendStaminaToAllFriends()]
    assert any(event == "send_stamina.cancelled" for event, _ in events)


def test_cancelled_before_start_never_opens_friends():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        cancel_requested=lambda: True,
    )

    assert result.status is FlowStatus.CANCELLED
    assert actions == []
    assert observer.calls == []


def test_close_timeout_fails_instead_of_accepting_unverified_postcondition():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    opened = stable_pair(
        friends(2, 2.0, daily_active=False),
        friends(3, 2.3, daily_active=False),
    )
    result, actions, _, _ = run_flow(
        lobby,
        [
            opened,
            RuntimeWaitTimeout(
                after_sequence=3,
                timeout=6.0,
                last_snapshot=None,
            ),
        ],
    )

    assert result.status is FlowStatus.FAILED
    assert actions == [OpenFriends(), CloseFriends()]


def test_daily_reappearance_during_close_is_contradictory_and_fails():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    opened = stable_pair(
        friends(2, 2.0, daily_active=False),
        friends(3, 2.3, daily_active=False),
    )

    result, actions, _, _ = run_flow(
        lobby,
        [opened, [friends(4, 3.0, daily_active=True)]],
    )

    assert result.status is FlowStatus.FAILED
    assert actions == [OpenFriends(), CloseFriends()]
