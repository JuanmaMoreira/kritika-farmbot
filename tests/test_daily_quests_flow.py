from dataclasses import dataclass

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    MODE_DAILY_QUESTS,
    SCREEN_LOBBY,
    SCREEN_QUESTS,
    STATUS_DAILY_QUESTS_CLAIMABLE,
)
from bot.daily_quests_flow import (
    DAILY_QUESTS_CLAIM_ALL_COMPLETED,
    DAILY_QUESTS_CLAIM_ALL_EXECUTED,
    DAILY_QUESTS_NOOP,
    DailyQuestsFlow,
)
from bot.flow_contracts import FlowStatus
from bot.observations import ObservationBatch
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import ClaimAllDailyQuests, CloseDailyQuests, OpenDailyQuests
from bot.state import ResolutionStatus, ResolvedState


@dataclass
class WaitCall:
    after_sequence: int
    stable_for: float


class ScriptedObserver:
    def __init__(self, initial, scripts):
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
        self.calls.append(WaitCall(after_sequence, stable_for))
        script = self.scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        stable_since = None
        last = None
        for snapshot in script:
            last = snapshot
            assert snapshot.sequence > after_sequence
            if cancel_requested is not None and cancel_requested():
                raise RuntimeWaitCancelled("cancelled")
            if abort_if is not None and abort_if(snapshot):
                raise RuntimeWaitAborted(snapshot)
            if condition(snapshot):
                if stable_since is None:
                    stable_since = snapshot.timestamp
                if snapshot.timestamp - stable_since >= stable_for:
                    return snapshot
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


def run_flow(initial, scripts, **kwargs):
    observer = ScriptedObserver(initial, scripts)
    actions = Actions()
    events = Events()
    result = DailyQuestsFlow(observer, actions, events, **kwargs).run()
    return result, actions.items, events.items, observer


def stable_pair(first, second):
    return [first, second]


def test_noop_without_claims_never_touches_claim_all_or_karats():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    daily_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,))
    daily_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,))
    returned_a = snapshot(4, 3.0, base=SCREEN_LOBBY)
    returned_b = snapshot(5, 3.3, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(
        lobby,
        [stable_pair(daily_a, daily_b), stable_pair(returned_a, returned_b)],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert result.event_count(DAILY_QUESTS_NOOP) == 1
    assert actions == [OpenDailyQuests(), CloseDailyQuests()]


def test_claim_all_runs_once_and_requires_stable_status_disappearance():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    daily_a = snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable)
    daily_b = snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable)
    absent_once = snapshot(4, 3.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,))
    claim_reappears = snapshot(5, 3.2, base=SCREEN_QUESTS, overlays=claimable)
    settled_a = snapshot(6, 3.4, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,))
    settled_b = snapshot(7, 4.0, base=SCREEN_QUESTS, overlays=(MODE_DAILY_QUESTS,))
    lobby_a = snapshot(8, 5.0, base=SCREEN_LOBBY)
    lobby_b = snapshot(9, 5.3, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            stable_pair(daily_a, daily_b),
            [absent_once, claim_reappears, settled_a, settled_b],
            stable_pair(lobby_a, lobby_b),
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.claim_all_executed and result.claim_all_completed
    assert result.event_count(DAILY_QUESTS_CLAIM_ALL_EXECUTED) == 1
    assert result.event_count(DAILY_QUESTS_CLAIM_ALL_COMPLETED) == 1
    assert actions == [OpenDailyQuests(), ClaimAllDailyQuests(), CloseDailyQuests()]
    assert actions.count(ClaimAllDailyQuests()) == 1
    assert observer.calls[1].stable_for == pytest.approx(0.5)


@pytest.mark.parametrize(
    "claim_script",
    (
        RuntimeWaitTimeout(after_sequence=3, timeout=8.0, last_snapshot=None),
        [[snapshot(4, 4.0, base=SCREEN_LOBBY)]],
    ),
)
def test_claim_timeout_or_incompatible_state_fails_conservatively(claim_script):
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    opened = [
        snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable),
        snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable),
    ]
    script = claim_script[0] if isinstance(claim_script, list) else claim_script
    result, actions, events, _ = run_flow(lobby, [opened, script])

    assert result.status is FlowStatus.FAILED
    assert actions.count(ClaimAllDailyQuests()) == 1
    assert CloseDailyQuests() not in actions
    assert any(event == "daily_quests.failed" for event, _ in events)


def test_cancellation_during_claim_wait_returns_cancelled_without_close():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    claimable = (MODE_DAILY_QUESTS, STATUS_DAILY_QUESTS_CLAIMABLE)
    opened = [
        snapshot(2, 2.0, base=SCREEN_QUESTS, overlays=claimable),
        snapshot(3, 2.3, base=SCREEN_QUESTS, overlays=claimable),
    ]
    result, actions, events, _ = run_flow(
        lobby,
        [opened, RuntimeWaitCancelled("cancelled")],
    )

    assert result.status is FlowStatus.CANCELLED
    assert actions == [OpenDailyQuests(), ClaimAllDailyQuests()]
    assert any(event == "daily_quests.cancelled" for event, _ in events)
