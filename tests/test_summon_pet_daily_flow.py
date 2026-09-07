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
from bot.runtime_observer import RuntimeObserver
from bot.semantic_actions import (
    AcceptPetInventoryFull,
    ClosePetSummonResult,
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


def manage(sequence, daily):
    return snapshot(
        sequence,
        "screen.pets_manage",
        ("status.pet_summon_daily_active",) if daily else (),
    )


def combine(sequence):
    return snapshot(sequence, "screen.pet_combine")


def summon(sequence, epic, *, daily=False, resource="status.pet_premium_gold", popup=None):
    overlays = [epic, resource]
    if daily:
        overlays.append(STATUS_PET_SUMMON_DAILY_ACTIVE)
    if popup:
        overlays.append(popup)
    return snapshot(sequence, "screen.pet_summon", overlays)


def epic_selector(sequence, *, resource="status.pet_premium_gold"):
    return snapshot(
        sequence,
        "screen.pet_summon",
        ("overlay.pet_epic_selector", resource),
    )


def premium_selector(sequence, selector, resource):
    return snapshot(
        sequence,
        "screen.pet_summon",
        (selector, resource),
    )


def entry(sequence, epic, resource="status.pet_premium_gold"):
    """Pet Summon with Epic status resolved (AVAILABLE or UNAVAILABLE). No Daily overlay."""
    overlays = [epic, resource]
    return snapshot(
        sequence,
        "screen.pet_summon",
        overlays,
    )


def result(sequence):
    return snapshot(sequence, "screen.pet_summon_result")


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
        result = self.results.pop(0)
        if isinstance(result, tuple):
            from bot.pet_summon_space_relief import PetSummonSpaceReliefResult, PetSummonSpaceReliefOutcome
            outcome, final, error = result[0], result[1], result[2] if len(result) > 2 else None
            return PetSummonSpaceReliefResult(outcome, final, error=error)
        return result


def relief_result(outcome, final, error=None):
    return PetSummonSpaceReliefResult(outcome, final, error=error)


def build(scripted, *, initial=None, relief=(), cancel=lambda: False):
    observer = Observer(initial or manage(1, False), scripted)
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
    return {e.kind for e in result.events}


def test_contract_is_manage_to_manage_or_summon():
    from bot.catalog import SCREEN_PETS_MANAGE, SCREEN_PET_SUMMON
    assert SummonPetDailyFlow.contract.precondition.name == "screen.pets_manage"
    assert {
        requirement.name
        for requirement in SummonPetDailyFlow.contract.successful_postconditions
    } == {"screen.pets_manage", "screen.pet_summon"}


def test_daily_absent_is_successful_noop_without_entering_summon():
    flow, actions, _, relief, _ = build([])

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert result_value.no_op and result_value.daily_completed
    assert "summon_pet_daily.noop" in {e.kind for e in result_value.events}
    assert actions.calls == []
    assert not any(isinstance(action, SelectPetSummon) for action in actions.calls)
    assert relief.calls == []


def test_epic_available_uses_one_open_and_requires_result_then_clean_summon():
    flow, actions, _, _, observer = build(
        [
            entry(3, STATUS_PET_EPIC_AVAILABLE),  # Pet Summon, Epic available
            result(4),  # Result after 1(Open)
            summon(5, STATUS_PET_EPIC_AVAILABLE, daily=False),  # Back to Summon after closing result
        ],
        initial=manage(1, True),
    )

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert result_value.daily_completed and result_value.summons_completed == 1
    assert sum(isinstance(action, OpenEpicPetSummon) for action in actions.calls) == 1
    assert sum(isinstance(action, OpenSingleEpicPet) for action in actions.calls) == 1
    assert any(isinstance(action, ClosePetSummonResult) for action in actions.calls)


@pytest.mark.parametrize(
    ("selector", "resource"),
    (
        ("overlay.pet_premium_ticket_selector", "status.pet_premium_ticket_available"),
        ("overlay.pet_premium_gold_selector", "status.pet_premium_gold"),
    ),
)
def test_epic_unavailable_uses_same_premium_policy_for_ticket_or_gold(selector, resource):
    flow, actions, _, _, _ = build(
        [
            entry(3, STATUS_PET_EPIC_UNAVAILABLE, resource=resource),  # Pet Summon, Epic unavailable
            result(4),  # Result after 1(Open)
            summon(5, STATUS_PET_EPIC_UNAVAILABLE, resource=resource),  # Back to Summon
        ],
        initial=manage(1, True),
    )

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert sum(isinstance(action, OpenPremiumPetSummon) for action in actions.calls) == 1
    assert sum(isinstance(action, OpenSinglePremiumPet) for action in actions.calls) == 1
    assert not any(isinstance(action, OpenEpicPetSummon) for action in actions.calls)


def test_insufficient_gold_is_nonfatal_and_leaves_daily_pending():
    flow, actions, _, relief, _ = build(
        [
            entry(3, STATUS_PET_EPIC_UNAVAILABLE),  # Pet Summon, Epic unavailable
            summon(4, STATUS_PET_EPIC_UNAVAILABLE, popup="popup.insufficient_gold"),  # After 1(Open), insufficient gold
            summon(5, STATUS_PET_EPIC_UNAVAILABLE),  # Back to Summon after rejecting
        ],
        initial=manage(1, True),
    )

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert result_value.daily_pending and not result_value.daily_completed
    assert "summon_pet_daily.insufficient_gold" in {e.kind for e in result_value.events}
    assert any(isinstance(action, RejectInsufficientGold) for action in actions.calls)
    assert relief.calls == []


def test_insufficient_gold_dismiss_requires_popup_disappearance():
    flow, actions, _, _, _ = build(
        [entry(3, STATUS_PET_EPIC_UNAVAILABLE),
         summon(4, STATUS_PET_EPIC_UNAVAILABLE, popup=POPUP_INSUFFICIENT_GOLD),
         summon(5, STATUS_PET_EPIC_UNAVAILABLE, popup=POPUP_INSUFFICIENT_GOLD)],
        initial=manage(1, True),
    )
    result_value = flow.run()
    assert result_value.status is FlowStatus.FAILED
    assert actions.calls.count(RejectInsufficientGold()) == 1


def test_pet_full_accept_cannot_start_relief_under_combine_popup():
    flow, _, _, relief, _ = build(
        [entry(3, STATUS_PET_EPIC_AVAILABLE),
         summon(4, STATUS_PET_EPIC_AVAILABLE, popup=POPUP_PET_INVENTORY_FULL),
         snapshot(6, SCREEN_PET_COMBINE, ("popup.pet_combine_all_confirmation",)),
         entry(8, STATUS_PET_EPIC_AVAILABLE)],
        initial=manage(1, True),
        relief=[(PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE, combine(7))],
    )
    result_value = flow.run()
    assert result_value.status is FlowStatus.FAILED
    assert relief.calls == []


def test_pet_full_relief_success_retries_once_and_can_complete_daily():
    relief_final = combine(7)
    flow, actions, _, relief, _ = build(
        [
            entry(3, STATUS_PET_EPIC_AVAILABLE),  # Pet Summon, Epic available
            summon(4, STATUS_PET_EPIC_AVAILABLE, popup="popup.pet_inventory_full"),  # Pet Full after 1(Open)
            combine(6),
            entry(8, STATUS_PET_EPIC_UNAVAILABLE, resource="status.pet_premium_gold"),  # After relief, Epic unavailable
            result(9),
            summon(10, STATUS_PET_EPIC_UNAVAILABLE),  # Back to Summon after retry
            manage(11, False),  # Final state
        ],
        initial=manage(1, True),
        relief=[(PetSummonSpaceReliefOutcome.RELIEVED, relief_final)],
    )

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert result_value.relief_attempted and result_value.retry_attempted
    assert result_value.summons_completed == 1
    assert len(relief.calls) == 1
    assert sum(isinstance(action, AcceptPetInventoryFull) for action in actions.calls) == 1


def test_relief_unavailable_is_manual_resolution_not_technical_failure():
    relief_final = combine(7)
    flow, actions, _, relief, _ = build(
        [
            entry(3, STATUS_PET_EPIC_AVAILABLE),  # Pet Summon, Epic available
            summon(4, STATUS_PET_EPIC_AVAILABLE, popup="popup.pet_inventory_full"),  # Pet Full after 1(Open)
            combine(6),
            entry(8, STATUS_PET_EPIC_AVAILABLE, resource="status.pet_premium_gold"),  # After relief, Epic available again
            result(9),
            summon(10, STATUS_PET_EPIC_AVAILABLE, daily=False),  # Back to Summon after retry
            manage(11, False),  # Final state
        ],
        initial=manage(1, True),
        relief=[
            (PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE, relief_final)
        ],
    )

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert result_value.daily_pending and result_value.relief_attempted
    assert "summon_pet_daily.space_relief_unavailable" in {e.kind for e in result_value.events}
    assert "summon_pet_daily.manual_resolution" in {e.kind for e in result_value.events}
    assert len(relief.calls) == 1
    assert isinstance(actions.calls[-1], SelectPetSummon)


def test_retry_pet_full_never_invokes_second_relief():
    relief_final = combine(7)
    flow, actions, _, relief, _ = build(
        [
            entry(3, STATUS_PET_EPIC_AVAILABLE),  # Pet Summon, Epic available
            summon(4, STATUS_PET_EPIC_AVAILABLE, popup="popup.pet_inventory_full"),  # Pet Full after 1(Open)
            combine(6),
            entry(8, STATUS_PET_EPIC_AVAILABLE, resource="status.pet_premium_gold"),  # After relief, Epic available again
            summon(9, STATUS_PET_EPIC_AVAILABLE, popup="popup.pet_inventory_full"),  # Pet Full again
            summon(10, STATUS_PET_EPIC_AVAILABLE),  # Back to Summon
            manage(11, False),  # Final state
        ],
        initial=manage(1, True),
        relief=[
            (PetSummonSpaceReliefOutcome.RELIEVED, relief_final)
        ],
    )

    result_value = flow.run()

    assert result_value.status == FlowStatus.COMPLETED
    assert result_value.daily_pending and result_value.retry_attempted
    assert len(relief.calls) == 1
    assert sum(isinstance(action, RejectPetInventoryFull) for action in actions.calls) == 1
    assert "summon_pet_daily.manual_resolution" in {e.kind for e in result_value.events}


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
            entry(3, STATUS_PET_EPIC_AVAILABLE),  # Pet Summon, Epic available
            summon(4, STATUS_PET_EPIC_AVAILABLE, popup="popup.pet_inventory_full"),  # Pet Full after 1(Open)
            combine(6),
        ],
        initial=manage(1, True),
        relief=[
            (outcome, combine(7), "relief failed" if outcome == PetSummonSpaceReliefOutcome.FAILED else None)
        ],
    )

    result_value = flow.run()

    assert result_value.status == expected_status
    assert len(relief.calls) == 1


def test_initial_cancellation_and_incompatible_outcome_send_no_unsafe_followup():
    cancelled_flow, cancelled_actions, _, _, _ = build([], cancel=lambda: True)
    cancelled = cancelled_flow.run()

    failed_flow, failed_actions, _, _, _ = build(
        [
            entry(3, STATUS_PET_EPIC_AVAILABLE),  # Pet Summon, Epic available
            snapshot(4, "screen.pets_manage"),  # Incompatible state
        ],
        initial=manage(1, True),
    )
    failed = failed_flow.run()

    assert cancelled.status == FlowStatus.CANCELLED
    assert cancelled_actions.calls == []
    assert failed.status == FlowStatus.FAILED
    # Flow executes SelectPetSummon then OpenEpicPetSummon then OpenSingleEpicPet before hitting incompatible state
    assert len(failed_actions.calls) == 3


def test_hil_double_tap_then_real_wait_tolerates_selector_and_checks_clean_return(monkeypatch):
    timeline = []
    frames = iter([
        manage(1, True),
        snapshot(2, SCREEN_PET_SUMMON),  # shell before availability resolves
        entry(3, STATUS_PET_EPIC_AVAILABLE),
        entry(4, STATUS_PET_EPIC_AVAILABLE),
        snapshot(5, SCREEN_PET_SUMMON, (OVERLAY_PET_EPIC_SELECTOR,)),
        result(6), result(7),
        summon(8, STATUS_PET_EPIC_AVAILABLE, daily=True),
        summon(9, STATUS_PET_EPIC_AVAILABLE, daily=True),
    ])
    now = [0.0]
    observer = object.__new__(RuntimeObserver)
    observer.poll_interval = 0.02
    observer._clock = lambda: now[0]
    observer._sleeper = lambda seconds: now.__setitem__(0, now[0] + seconds)

    def observe():
        current = next(frames)
        timeline.append(("observe", current.sequence))
        return current

    observer.observe = observe
    actions = Actions()
    original_execute = actions.execute

    def execute(action, geometry):
        timeline.append(type(action).__name__)
        original_execute(action, geometry)

    actions.execute = execute
    monkeypatch.setattr("bot.summon_pet_daily_flow.time.sleep", lambda seconds: timeline.append(("settle", seconds)))
    value = SummonPetDailyFlow(observer, actions, Events(), Relief()).run()
    assert value.status is FlowStatus.COMPLETED
    assert value.summons_completed == 1
    selector_index = timeline.index("OpenEpicPetSummon")
    assert timeline[selector_index:selector_index + 3] == [
        "OpenEpicPetSummon", ("settle", 0.25), "OpenSingleEpicPet",
    ]
    assert len(actions.calls) == 4
