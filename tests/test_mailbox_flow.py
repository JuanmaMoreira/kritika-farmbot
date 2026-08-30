from dataclasses import dataclass

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_MAILBOX_CLAIM_PROCESSING,
    MODE_MAILBOX_CHARACTER_MAIL,
    SCREEN_LOBBY,
    SCREEN_MAILBOX,
    STATUS_MAILBOX_CLAIMABLE,
    STATUS_MAILBOX_READ_MAIL_PRESENT,
)
from bot.flow_contracts import FlowStatus
from bot.mailbox_flow import (
    MAILBOX_CLAIMS_LEFTOVER,
    MAILBOX_CLAIM_ALL_NO_EFFECT,
    MAILBOX_CLAIM_PROCESSING_COMPLETED,
    MAILBOX_CLAIM_PROCESSING_OBSERVED,
    MAILBOX_DELETE_READ_EXECUTED,
    MAILBOX_DELETE_READ_SKIPPED,
    MAILBOX_NOOP,
    MailboxFlow,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    ClaimAllCharacterMail,
    CloseMailbox,
    DeleteReadCharacterMail,
    OpenMailbox,
    SelectCharacterMail,
)
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


def snapshot(sequence, timestamp, *, base, overlays=(), activity=False, status=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    observations = ()
    if activity:
        observations = (
            Observation(
                ACTIVITY_MAILBOX_CLAIM_PROCESSING,
                1.0,
                ObservationSource.LOCAL_CV,
            ),
        )
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, observations),
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
    flow = MailboxFlow(
        observer,
        actions,
        events,
        navigation_stable_for=0.0,
        no_effect_stable_for=0.5,
        processing_stable_for=0.75,
        delete_stable_for=0.5,
        **kwargs,
    )
    return flow.run(), actions.items, events.items, observer


def character_overlays(*statuses):
    return (MODE_MAILBOX_CHARACTER_MAIL, *statuses)


def test_normal_processing_rejects_dark_spinner_phase_then_deletes_read_mail():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = snapshot(2, 2.0, base=SCREEN_MAILBOX)
    character = snapshot(
        3,
        3.0,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_CLAIMABLE),
    )
    active = snapshot(4, 4.0, base=SCREEN_MAILBOX, activity=True)
    dark_once = snapshot(
        5,
        4.2,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_READ_MAIL_PRESENT),
    )
    active_again = snapshot(6, 4.4, base=SCREEN_MAILBOX, activity=True)
    settled_a = snapshot(
        7,
        4.6,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_READ_MAIL_PRESENT),
    )
    settled_b = snapshot(
        8,
        5.4,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_READ_MAIL_PRESENT),
    )
    after_delete_a = snapshot(
        9, 6.0, base=SCREEN_MAILBOX, overlays=character_overlays()
    )
    after_delete_b = snapshot(
        10, 6.6, base=SCREEN_MAILBOX, overlays=character_overlays()
    )
    returned = snapshot(11, 7.0, base=SCREEN_LOBBY)

    result, actions, _, observer = run_flow(
        lobby,
        [
            [account],
            [character],
            [active],
            [dark_once, active_again, settled_a, settled_b],
            [after_delete_a, after_delete_b],
            [returned],
        ],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.processing_observed and result.processing_completed
    assert result.delete_read_executed
    assert result.event_count(MAILBOX_CLAIM_PROCESSING_OBSERVED) == 1
    assert result.event_count(MAILBOX_CLAIM_PROCESSING_COMPLETED) == 1
    assert result.event_count(MAILBOX_DELETE_READ_EXECUTED) == 1
    assert actions == [
        OpenMailbox(),
        SelectCharacterMail(),
        ClaimAllCharacterMail(),
        DeleteReadCharacterMail(),
        CloseMailbox(),
    ]
    assert observer.calls[3].stable_for == pytest.approx(0.75)


def test_claim_all_without_activity_is_single_attempt_and_leftovers_are_nonfatal():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = snapshot(2, 2.0, base=SCREEN_MAILBOX)
    claims = character_overlays(STATUS_MAILBOX_CLAIMABLE)
    character = snapshot(3, 3.0, base=SCREEN_MAILBOX, overlays=claims)
    still_claims = snapshot(4, 4.0, base=SCREEN_MAILBOX, overlays=claims)
    confirmed_a = snapshot(5, 5.0, base=SCREEN_MAILBOX, overlays=claims)
    confirmed_b = snapshot(6, 5.6, base=SCREEN_MAILBOX, overlays=claims)
    returned = snapshot(7, 6.0, base=SCREEN_LOBBY)
    onset_timeout = RuntimeWaitTimeout(
        after_sequence=3,
        timeout=2.0,
        last_snapshot=still_claims,
    )

    result, actions, _, _ = run_flow(
        lobby,
        [[account], [character], onset_timeout, [confirmed_a, confirmed_b], [returned]],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.claim_all_no_effect and result.claims_leftover
    assert result.event_count(MAILBOX_CLAIM_ALL_NO_EFFECT) == 1
    assert result.event_count(MAILBOX_CLAIMS_LEFTOVER) == 1
    assert result.event_count(MAILBOX_DELETE_READ_SKIPPED) == 1
    assert actions.count(ClaimAllCharacterMail()) == 1
    assert DeleteReadCharacterMail() not in actions


def test_no_claims_or_read_mail_is_mailbox_noop():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = snapshot(2, 2.0, base=SCREEN_MAILBOX)
    empty = snapshot(3, 3.0, base=SCREEN_MAILBOX, overlays=character_overlays())
    returned = snapshot(4, 4.0, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(lobby, [[account], [empty], [returned]])

    assert result.status is FlowStatus.COMPLETED
    assert result.no_op
    assert result.event_count(MAILBOX_NOOP) == 1
    assert result.event_count(MAILBOX_DELETE_READ_SKIPPED) == 1
    assert ClaimAllCharacterMail() not in actions
    assert DeleteReadCharacterMail() not in actions


def test_read_mail_without_claims_is_deleted_and_inbox_need_not_be_empty():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = snapshot(2, 2.0, base=SCREEN_MAILBOX)
    read = snapshot(
        3,
        3.0,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_READ_MAIL_PRESENT),
    )
    # Claims may legitimately remain after Delete Read; Inbox count is not a fact.
    leftover_a = snapshot(
        4,
        4.0,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_CLAIMABLE),
    )
    leftover_b = snapshot(
        5,
        4.6,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_CLAIMABLE),
    )
    returned = snapshot(6, 5.0, base=SCREEN_LOBBY)

    result, actions, _, _ = run_flow(
        lobby,
        [[account], [read], [leftover_a, leftover_b], [returned]],
    )

    assert result.status is FlowStatus.COMPLETED
    assert result.delete_read_executed
    assert result.claims_leftover
    assert result.event_count(MAILBOX_CLAIMS_LEFTOVER) == 1
    assert actions == [
        OpenMailbox(),
        SelectCharacterMail(),
        DeleteReadCharacterMail(),
        CloseMailbox(),
    ]


@pytest.mark.parametrize(
    ("terminal", "expected"),
    (
        (RuntimeWaitCancelled("cancelled"), FlowStatus.CANCELLED),
        ([snapshot(4, 4.0, base=SCREEN_LOBBY)], FlowStatus.FAILED),
    ),
)
def test_processing_cancellation_or_incompatible_state_is_terminal(
    terminal, expected
):
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = snapshot(2, 2.0, base=SCREEN_MAILBOX)
    claims = snapshot(
        3,
        3.0,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_CLAIMABLE),
    )
    result, actions, events, _ = run_flow(
        lobby, [[account], [claims], terminal]
    )

    assert result.status is expected
    assert actions.count(ClaimAllCharacterMail()) == 1
    assert CloseMailbox() not in actions
    terminal_event = (
        "mailbox.cancelled"
        if expected is FlowStatus.CANCELLED
        else "mailbox.failed"
    )
    assert any(event == terminal_event for event, _ in events)


def test_processing_completion_timeout_fails_without_delete_or_close():
    lobby = snapshot(1, 1.0, base=SCREEN_LOBBY)
    account = snapshot(2, 2.0, base=SCREEN_MAILBOX)
    claims = snapshot(
        3,
        3.0,
        base=SCREEN_MAILBOX,
        overlays=character_overlays(STATUS_MAILBOX_CLAIMABLE),
    )
    active = snapshot(4, 4.0, base=SCREEN_MAILBOX, activity=True)
    timeout = RuntimeWaitTimeout(
        after_sequence=4,
        timeout=20.0,
        last_snapshot=active,
    )

    result, actions, _, _ = run_flow(
        lobby, [[account], [claims], [active], timeout]
    )

    assert result.status is FlowStatus.FAILED
    assert actions.count(ClaimAllCharacterMail()) == 1
    assert DeleteReadCharacterMail() not in actions
    assert CloseMailbox() not in actions
