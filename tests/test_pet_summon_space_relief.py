import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    CANDIDATE_PET_LOW_TIER,
    POPUP_PET_COMBINE_ALL,
    POPUP_PET_COMBINE_NO_MATERIAL,
    POPUP_PET_EPIC_RUNES_FULL,
    SCREEN_PET_COMBINE,
    SCREEN_PET_COMBINE_RESULT,
    SCREEN_PET_SUMMON,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.pet_summon_space_relief import (
    PetSummonSpaceRelief,
    PetSummonSpaceReliefOutcome,
    PetSummonSpaceReliefPolicy,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitTimeout
from bot.semantic_actions import (
    AcknowledgePetCombineNoMaterial,
    ConfirmPetCombineAll,
    OpenPetCombineAll,
    RejectPetEpicRunesFull,
    TapCombineAnimation,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.tap_through_animation import TapThroughOutcome, TapThroughPolicy, TapThroughResult


def snapshot(sequence, *, base=SCREEN_PET_COMBINE, overlays=(), observations=()):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), tuple(observations)),
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


def combine(sequence, *, with_low_tier_candidate=False):
    observations = ()
    if with_low_tier_candidate:
        observations = (
            Observation(
                CANDIDATE_PET_LOW_TIER,
                1.0,
                ObservationSource.LOCAL_CV,
                value="normal",
                region=(0.55, 0.33, 0.61, 0.44),
            ),
        )
    return snapshot(sequence, observations=observations)


def popup(sequence, name):
    return snapshot(sequence, overlays=(name,))


def combine_result(sequence):
    return snapshot(
        sequence,
        base=SCREEN_PET_COMBINE_RESULT,
        observations=(
            Observation(
                ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
                1.0,
                ObservationSource.LOCAL_CV,
            ),
        ),
    )


class Observer:
    def __init__(self, initial, scripted):
        self.initial = initial
        self.scripted = list(scripted)

    def observe(self):
        return self.initial

    def wait_until(self, condition, **kwargs):
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


class TapThrough:
    def __init__(self, final, outcome=TapThroughOutcome.COMPLETED):
        self.final = final
        self.outcome = outcome
        self.calls = []

    def run(self, initial, **kwargs):
        self.calls.append((initial, kwargs))
        assert kwargs["tappable"](initial)
        assert isinstance(kwargs["action"], TapCombineAnimation)
        if self.outcome is TapThroughOutcome.COMPLETED:
            assert kwargs["expected"](self.final)
        return TapThroughResult(self.outcome, 1, self.final, "tap failed")


def build(initial, scripted, *, tap_final=None, tap_outcome=TapThroughOutcome.COMPLETED):
    observer = Observer(initial, scripted)
    actions = Actions()
    events = Events()
    tapper = TapThrough(tap_final or initial, tap_outcome)
    operation = PetSummonSpaceRelief(
        observer,
        actions,
        events,
        tap_through=tapper,
        policy=PetSummonSpaceReliefPolicy(
            state_timeout=1,
            stable_for=0,
            animation=TapThroughPolicy(tap_interval=0.01, timeout=1, max_taps=2),
        ),
    )
    return operation, actions, events, tapper


def test_one_combine_all_with_verified_effect_is_relieved():
    final = combine(4)
    operation, actions, events, tapper = build(
        combine(1),
        [popup(2, POPUP_PET_COMBINE_ALL), combine_result(3)],
        tap_final=final,
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.RELIEVED
    assert result.final_snapshot is final
    assert result.combine_attempts == 1
    assert result.animation_taps == 1
    assert [type(action) for action in actions.calls] == [
        OpenPetCombineAll,
        ConfirmPetCombineAll,
    ]
    assert len(tapper.calls) == 1
    assert events.records[-1][1]["outcome"] == "relieved"


@pytest.mark.parametrize(
    ("safe_popup", "dismiss_action"),
    (
        (POPUP_PET_COMBINE_NO_MATERIAL, AcknowledgePetCombineNoMaterial),
        (POPUP_PET_EPIC_RUNES_FULL, RejectPetEpicRunesFull),
    ),
)
def test_safe_no_progress_after_confirmation_is_no_relief(safe_popup, dismiss_action):
    final = combine(4)
    operation, actions, _, tapper = build(
        combine(1, with_low_tier_candidate=True),
        [popup(2, POPUP_PET_COMBINE_ALL), popup(3, safe_popup), final],
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.final_snapshot is final
    assert result.combine_attempts == 1
    assert [type(action) for action in actions.calls] == [
        OpenPetCombineAll,
        ConfirmPetCombineAll,
        dismiss_action,
    ]
    assert tapper.calls == []


@pytest.mark.parametrize(
    ("safe_popup", "dismiss_action"),
    (
        (POPUP_PET_COMBINE_NO_MATERIAL, AcknowledgePetCombineNoMaterial),
        (POPUP_PET_EPIC_RUNES_FULL, RejectPetEpicRunesFull),
    ),
)
def test_safe_no_progress_directly_from_combine_all_is_no_relief(
    safe_popup, dismiss_action
):
    operation, actions, _, _ = build(
        combine(1), [popup(2, safe_popup), combine(3)]
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert [type(action) for action in actions.calls] == [
        OpenPetCombineAll,
        dismiss_action,
    ]


def test_stable_combine_return_without_result_is_safe_no_relief():
    final = combine(3)
    operation, actions, _, tapper = build(
        combine(1), [popup(2, POPUP_PET_COMBINE_ALL), final]
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.final_snapshot is final
    assert [type(action) for action in actions.calls] == [
        OpenPetCombineAll,
        ConfirmPetCombineAll,
    ]
    assert tapper.calls == []


def test_incompatible_transition_is_failed_without_followup_input():
    incompatible = snapshot(2, base=SCREEN_PET_SUMMON)
    operation, actions, _, tapper = build(combine(1), [incompatible])

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.FAILED
    assert result.final_snapshot is incompatible
    assert "state_wait_failed" in result.error
    assert [type(action) for action in actions.calls] == [OpenPetCombineAll]
    assert tapper.calls == []


@pytest.mark.parametrize(
    ("tap_outcome", "expected"),
    (
        (TapThroughOutcome.CANCELLED, PetSummonSpaceReliefOutcome.CANCELLED),
        (TapThroughOutcome.INCOMPATIBLE_STATE, PetSummonSpaceReliefOutcome.FAILED),
    ),
)
def test_tap_through_cancellation_and_invalid_state_propagate(tap_outcome, expected):
    operation, _, _, _ = build(
        combine(1),
        [popup(2, POPUP_PET_COMBINE_ALL), combine_result(3)],
        tap_final=combine_result(4),
        tap_outcome=tap_outcome,
    )

    result = operation.run()

    assert result.outcome is expected


def test_initial_cancellation_and_contradictory_precondition_send_no_input():
    operation, actions, _, _ = build(combine(1), [])
    cancelled = operation.run(lambda: True)

    wrong, wrong_actions, _, _ = build(snapshot(1, base=SCREEN_PET_SUMMON), [])
    failed = wrong.run()

    assert cancelled.outcome is PetSummonSpaceReliefOutcome.CANCELLED
    assert failed.outcome is PetSummonSpaceReliefOutcome.FAILED
    assert actions.calls == []
    assert wrong_actions.calls == []
