import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    OVERLAY_PET_EPIC_SELECTOR,
    OVERLAY_PET_PREMIUM_GOLD_SELECTOR,
    OVERLAY_PET_PREMIUM_TICKET_SELECTOR,
    POPUP_INSUFFICIENT_GOLD,
    POPUP_PET_INVENTORY_FULL,
    SCREEN_LOBBY,
    SCREEN_PET_COMBINE,
    SCREEN_PET_SUMMON,
    SCREEN_PET_SUMMON_RESULT,
    SCREEN_PETS_MANAGE,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
    STATUS_PET_PREMIUM_TICKET_AVAILABLE,
    STATUS_PET_SUMMON_DAILY_ACTIVE,
)
from bot.flow_contracts import FlowStatus
from bot.observations import ObservationBatch
from bot.pet_summon_space_relief import (
    PetSummonSpaceReliefOutcome,
    PetSummonSpaceReliefResult,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitTimeout
from bot.semantic_actions import (
    AcceptPetInventoryFull,
    ClosePetSummonResult,
    ClosePets,
    OpenEpicPetSummon,
    OpenPremiumPetSummon,
    OpenSingleEpicPet,
    OpenSinglePremiumPet,
    RejectInsufficientGold,
    RejectPetInventoryFull,
    SelectPetSummon,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.summon_pet_daily_flow import (
    SUMMON_PET_DAILY_INSUFFICIENT_GOLD,
    SUMMON_PET_DAILY_MANUAL_RESOLUTION,
    SUMMON_PET_DAILY_NOOP,
    SUMMON_PET_DAILY_SPACE_RELIEF_UNAVAILABLE,
    SummonPetDailyFlow,
)


def snapshot(sequence, base, overlays=()):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence)),
        ResolvedState(
            ResolutionStatus.RESOLVED,
            sequence,
            float(sequence),
            base_context=base,
            overlays=tuple(overlays),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def lobby(sequence):
    return snapshot(sequence, SCREEN_LOBBY)


def manage(sequence, daily):
    return snapshot(
        sequence,
        SCREEN_PETS_MANAGE,
        (STATUS_PET_SUMMON_DAILY_ACTIVE,) if daily else (),
    )


def combine(sequence):
    return snapshot(sequence, SCREEN_PET_COMBINE)


def summon(sequence, epic, *, daily=True, resource=STATUS_PET_PREMIUM_GOLD, popup=None):
    overlays = [epic, resource]
    if daily:
        overlays.append(STATUS_PET_SUMMON_DAILY_ACTIVE)
    if popup:
        overlays.append(popup)
    return snapshot(sequence, SCREEN_PET_SUMMON, overlays)


def epic_selector(sequence, *, resource=STATUS_PET_PREMIUM_GOLD):
    return snapshot(
        sequence,
        SCREEN_PET_SUMMON,
        (OVERLAY_PET_EPIC_SELECTOR, resource, STATUS_PET_SUMMON_DAILY_ACTIVE),
    )


def premium_selector(sequence, selector, resource):
    return snapshot(
        sequence,
        SCREEN_PET_SUMMON,
        (selector, resource, STATUS_PET_SUMMON_DAILY_ACTIVE),
    )


def result(sequence):
    return snapshot(sequence, SCREEN_PET_SUMMON_RESULT)


class Observer:
    def __init__(self, initial, scripted):
        self.initial = initial
        self.scripted = list(scripted)
        self.calls = []

    def observe(self):
        return self.initial

    def wait_until(self, condition, **kwargs):
        self.calls.append(kwargs)
        if not self.scripted:
            raise RuntimeWaitTimeout(
                after_sequence=kwargs["after_sequence"],
                timeout=kwargs["timeout"],
                last_snapshot=None,
            )
        current = self.scripted.pop(0)
        if condition(current):
            return current
        abort_if = kwargs.get("abort_if")
        if abort_if is not None and abort_if(current):
            from bot.runtime_observer import RuntimeWaitAborted

            raise RuntimeWaitAborted(current)
        raise AssertionError(
            f"scripted snapshot {current.sequence} did not satisfy expected condition"
        )


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append(action)


class Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


class Relief:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, cancel_requested):
        self.calls.append(cancel_requested)
        return self.results.pop(0)


def relief_result(outcome, final, error=None):
    return PetSummonSpaceReliefResult(outcome, final, error=error)


def build(scripted, *, relief=(), cancel=lambda: False):
    observer = Observer(lobby(1), scripted)
    actions = Actions()
    events = Events()
    relief = Relief(relief)
    flow = SummonPetDailyFlow(
        observer,
        actions,
        events,
        relief,
        navigation_timeout=1,
        outcome_timeout=1,
        navigation_stable_for=0,
        outcome_stable_for=0,
        cancel_requested=cancel,
    )
    return flow, actions, events, relief, observer


def event_kinds(result):
    return {event.kind for event in result.events}


def test_daily_absent_is_successful_noop_without_entering_summon():
    flow, actions, _, relief, _ = build([manage(2, False), lobby(3)])

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert result_value.no_op and result_value.daily_completed
    assert SUMMON_PET_DAILY_NOOP in event_kinds(result_value)
    assert not any(isinstance(action, SelectPetSummon) for action in actions.calls)
    assert relief.calls == []


def test_epic_available_uses_one_open_and_requires_stable_result_then_daily_absence():
    flow, actions, _, _, observer = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(4),
            result(5),
            summon(6, STATUS_PET_EPIC_AVAILABLE, daily=False),
            lobby(7),
        ]
    )

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert result_value.daily_completed and result_value.summons_completed == 1
    assert sum(isinstance(action, OpenEpicPetSummon) for action in actions.calls) == 1
    assert sum(isinstance(action, OpenSingleEpicPet) for action in actions.calls) == 1
    assert any(isinstance(action, ClosePetSummonResult) for action in actions.calls)
    assert observer.calls[3]["stable_for"] == 0


@pytest.mark.parametrize(
    ("selector", "resource"),
    (
        (OVERLAY_PET_PREMIUM_TICKET_SELECTOR, STATUS_PET_PREMIUM_TICKET_AVAILABLE),
        (OVERLAY_PET_PREMIUM_GOLD_SELECTOR, STATUS_PET_PREMIUM_GOLD),
    ),
)
def test_epic_unavailable_uses_same_premium_policy_for_ticket_or_gold(selector, resource):
    flow, actions, _, _, _ = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_UNAVAILABLE, resource=resource),
            premium_selector(4, selector, resource),
            result(5),
            summon(6, STATUS_PET_EPIC_UNAVAILABLE, daily=False, resource=resource),
            lobby(7),
        ]
    )

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert sum(isinstance(action, OpenPremiumPetSummon) for action in actions.calls) == 1
    assert sum(isinstance(action, OpenSinglePremiumPet) for action in actions.calls) == 1
    assert not any(isinstance(action, OpenEpicPetSummon) for action in actions.calls)


def test_insufficient_gold_is_nonfatal_and_leaves_daily_pending():
    active = summon(3, STATUS_PET_EPIC_UNAVAILABLE)
    flow, actions, _, relief, _ = build(
        [
            manage(2, True),
            active,
            premium_selector(4, OVERLAY_PET_PREMIUM_GOLD_SELECTOR, STATUS_PET_PREMIUM_GOLD),
            summon(5, STATUS_PET_EPIC_UNAVAILABLE, popup=POPUP_INSUFFICIENT_GOLD),
            summon(6, STATUS_PET_EPIC_UNAVAILABLE),
            lobby(7),
        ]
    )

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert result_value.daily_pending and not result_value.daily_completed
    assert SUMMON_PET_DAILY_INSUFFICIENT_GOLD in event_kinds(result_value)
    assert any(isinstance(action, RejectInsufficientGold) for action in actions.calls)
    assert relief.calls == []


def test_pet_full_relief_success_retries_once_and_can_complete_daily():
    relief_final = combine(7)
    flow, actions, _, relief, _ = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL),
            combine(6),
            summon(8, STATUS_PET_EPIC_UNAVAILABLE),
            premium_selector(9, OVERLAY_PET_PREMIUM_GOLD_SELECTOR, STATUS_PET_PREMIUM_GOLD),
            result(10),
            summon(11, STATUS_PET_EPIC_UNAVAILABLE, daily=False),
            lobby(12),
        ],
        relief=[relief_result(PetSummonSpaceReliefOutcome.RELIEVED, relief_final)],
    )

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert result_value.relief_attempted and result_value.retry_attempted
    assert result_value.summons_completed == 1
    assert len(relief.calls) == 1
    assert sum(isinstance(action, AcceptPetInventoryFull) for action in actions.calls) == 1


def test_relief_unavailable_is_manual_resolution_not_technical_failure():
    relief_final = combine(7)
    flow, _, _, relief, _ = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL),
            combine(6),
            lobby(8),
        ],
        relief=[
            relief_result(
                PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE, relief_final
            )
        ],
    )

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert result_value.daily_pending and result_value.relief_attempted
    assert SUMMON_PET_DAILY_SPACE_RELIEF_UNAVAILABLE in event_kinds(result_value)
    assert SUMMON_PET_DAILY_MANUAL_RESOLUTION in event_kinds(result_value)
    assert len(relief.calls) == 1


def test_retry_pet_full_never_invokes_second_relief():
    relief_final = combine(7)
    flow, actions, _, relief, _ = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL),
            combine(6),
            summon(8, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(9),
            summon(10, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL),
            summon(11, STATUS_PET_EPIC_AVAILABLE),
            lobby(12),
        ],
        relief=[relief_result(PetSummonSpaceReliefOutcome.RELIEVED, relief_final)],
    )

    result_value = flow.run()

    assert result_value.status is FlowStatus.COMPLETED
    assert result_value.daily_pending and result_value.retry_attempted
    assert len(relief.calls) == 1
    assert sum(isinstance(action, RejectPetInventoryFull) for action in actions.calls) == 1
    assert SUMMON_PET_DAILY_MANUAL_RESOLUTION in event_kinds(result_value)


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    (
        (PetSummonSpaceReliefOutcome.FAILED, FlowStatus.FAILED),
        (PetSummonSpaceReliefOutcome.CANCELLED, FlowStatus.CANCELLED),
    ),
)
def test_relief_failure_and_cancellation_propagate(outcome, expected_status):
    flow, _, _, relief, _ = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL),
            combine(6),
        ],
        relief=[relief_result(outcome, combine(7), error="relief failed" if outcome is PetSummonSpaceReliefOutcome.FAILED else None)],
    )

    result_value = flow.run()

    assert result_value.status is expected_status
    assert len(relief.calls) == 1


def test_initial_cancellation_and_incompatible_outcome_send_no_unsafe_followup():
    cancelled_flow, cancelled_actions, _, _, _ = build([], cancel=lambda: True)
    cancelled = cancelled_flow.run()

    failed_flow, failed_actions, _, _, _ = build(
        [
            manage(2, True),
            summon(3, STATUS_PET_EPIC_AVAILABLE),
            epic_selector(4),
            lobby(5),
        ]
    )
    failed = failed_flow.run()

    assert cancelled.status is FlowStatus.CANCELLED
    assert cancelled_actions.calls == []
    assert failed.status is FlowStatus.FAILED
    assert not any(isinstance(action, ClosePets) for action in failed_actions.calls)
