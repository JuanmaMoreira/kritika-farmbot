import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    CANDIDATE_PET_LOW_TIER,
    LANDMARK_PET_MASS_EVOLVE_CONFIRMATION,
    MODE_PET_MASS_EVOLVE_SELECTION,
    OVERLAY_PET_EPIC_SELECTOR,
    POPUP_PET_COMBINE_ALL,
    POPUP_PET_COMBINE_NO_MATERIAL,
    POPUP_PET_EPIC_RUNES_FULL,
    POPUP_PET_INVENTORY_FULL,
    POPUP_PET_MASS_EVOLVE_CONFIRMATION,
    SCREEN_PET_COMBINE,
    SCREEN_PET_COMBINE_RESULT,
    SCREEN_PET_SUMMON,
    SCREEN_PET_SUMMON_RESULT,
    STATUS_PET_EPIC_AVAILABLE,
    STATUS_PET_EPIC_UNAVAILABLE,
    STATUS_PET_PREMIUM_GOLD,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.pet_summon_space_relief import (
    PetSummonSpaceRelief,
    PetSummonSpaceReliefOutcome,
    PetSummonSpaceReliefPolicy,
)
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot, RuntimeWaitTimeout
from bot.semantic_actions import (
    CancelPetMassEvolveSelection,
    ClosePetSummonResult,
    ConfirmPetMassEvolve,
    NextPetCombinePage,
    OpenEpicPetSummon,
    OpenPetCombineAll,
    OpenPetMassEvolve,
    OpenTenEpicPets,
    RejectPetInventoryFull,
    SelectPetLowTierCandidate,
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


def combine(sequence, *, candidate=None, value=None, region=(0.55, 0.33, 0.61, 0.44)):
    observations = ()
    if candidate:
        observations = (
            Observation(
                CANDIDATE_PET_LOW_TIER,
                1.0,
                ObservationSource.LOCAL_CV,
                value=value or candidate,
                region=region,
            ),
        )
    return snapshot(sequence, observations=observations)


def popup(sequence, name, *, selection=False, tier=None):
    overlays = ([MODE_PET_MASS_EVOLVE_SELECTION] if selection else []) + [name]
    observations = ()
    if tier is not None:
        observations = (
            Observation(
                LANDMARK_PET_MASS_EVOLVE_CONFIRMATION,
                1.0,
                ObservationSource.LOCAL_CV,
                value=tier,
            ),
        )
    return snapshot(sequence, overlays=overlays, observations=observations)


def selection(sequence):
    return snapshot(sequence, overlays=(MODE_PET_MASS_EVOLVE_SELECTION,))


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


def summon(sequence, epic, *extra):
    return snapshot(
        sequence,
        base=SCREEN_PET_SUMMON,
        overlays=(epic, *extra),
    )


def selector(sequence):
    return snapshot(
        sequence,
        base=SCREEN_PET_SUMMON,
        overlays=(OVERLAY_PET_EPIC_SELECTOR, STATUS_PET_PREMIUM_GOLD),
    )


def summon_result(sequence):
    return snapshot(sequence, base=SCREEN_PET_SUMMON_RESULT)


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
    def __init__(self, finals=()):
        self.finals = list(finals)
        self.calls = []

    def run(self, initial, **kwargs):
        self.calls.append((initial, kwargs))
        final = self.finals.pop(0)
        assert kwargs["tappable"](initial)
        assert kwargs["expected"](final)
        return TapThroughResult(TapThroughOutcome.COMPLETED, 1, final)


def build(initial, scripted, *, tap_finals=(), pages=1):
    observer = Observer(initial, scripted)
    actions = Actions()
    events = Events()
    tapper = TapThrough(tap_finals)
    operation = PetSummonSpaceRelief(
        observer,
        actions,
        events,
        tap_through=tapper,
        policy=PetSummonSpaceReliefPolicy(
            state_timeout=1,
            stable_for=0,
            max_candidate_pages=pages,
            animation=TapThroughPolicy(tap_interval=0.01, timeout=1, max_taps=2),
        ),
    )
    return operation, actions, events, tapper


def direct_no_effect(start=2, clean_snapshot=None):
    clean_snapshot = clean_snapshot or combine(start + 2)
    return [
        popup(start, POPUP_PET_COMBINE_ALL),
        popup(start + 1, POPUP_PET_COMBINE_NO_MATERIAL),
        clean_snapshot,
    ]


def second_effect(start):
    return [
        popup(start, POPUP_PET_COMBINE_ALL),
        combine_result(start + 1),
    ]


def test_direct_combine_all_effect_is_immediately_relieved():
    initial = combine(1)
    final = combine(4)
    operation, actions, events, tapper = build(
        initial,
        [popup(2, POPUP_PET_COMBINE_ALL), combine_result(3)],
        tap_finals=[final],
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.RELIEVED
    assert result.combine_attempts == 1
    assert result.animation_taps == 1
    assert isinstance(actions.calls[0], OpenPetCombineAll)
    assert len(tapper.calls) == 1
    assert events.records[-1][1]["outcome"] == "relieved"


def test_no_material_is_soft_no_relief_when_bounded_search_has_no_candidate():
    operation, actions, _, _ = build(combine(1), direct_no_effect(), pages=1)

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.candidate_pages_checked == 1
    assert not any(isinstance(action, OpenEpicPetSummon) for action in actions.calls)


def test_candidate_search_is_bounded_and_ignores_epic_or_ambiguous_values():
    invalid = combine(4, candidate="epic", value="epic")
    operation, actions, _, _ = build(
        combine(1),
        [*direct_no_effect(clean_snapshot=invalid), combine(5)],
        pages=2,
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.candidate_pages_checked == 2
    assert sum(isinstance(action, NextPetCombinePage) for action in actions.calls) == 1
    assert not any(isinstance(action, SelectPetLowTierCandidate) for action in actions.calls)


@pytest.mark.parametrize("tier", ("normal", "rare"))
def test_safe_candidate_mass_evolve_verifies_exact_tier_and_second_combine_relieves(tier):
    candidate = combine(4, candidate=tier)
    mass_result = combine_result(7)
    after_mass = selection(8)
    summon_unavailable = summon(11, STATUS_PET_EPIC_UNAVAILABLE, STATUS_PET_PREMIUM_GOLD)
    operation, actions, _, tapper = build(
        combine(1),
        [
            *direct_no_effect(clean_snapshot=candidate),
            selection(5),
            popup(6, POPUP_PET_MASS_EVOLVE_CONFIRMATION, selection=True, tier=tier),
            mass_result,
            combine(9),
            summon_unavailable,
            combine(12),
            *second_effect(13),
        ],
        tap_finals=[after_mass, combine(15)],
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.RELIEVED
    assert result.candidate_tier == tier
    assert result.combine_attempts == 2
    assert any(isinstance(action, ConfirmPetMassEvolve) for action in actions.calls)
    assert any(isinstance(action, CancelPetMassEvolveSelection) for action in actions.calls)
    assert len(tapper.calls) == 2


def test_mass_evolve_tier_mismatch_is_technical_failure_without_confirmation():
    candidate = combine(4, candidate="normal")
    operation, actions, _, _ = build(
        combine(1),
        [
            *direct_no_effect(clean_snapshot=candidate),
            selection(5),
            popup(6, POPUP_PET_MASS_EVOLVE_CONFIRMATION, selection=True, tier="rare"),
        ],
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.FAILED
    assert "tier_mismatch" in result.error
    assert not any(isinstance(action, ConfirmPetMassEvolve) for action in actions.calls)


def test_epic_available_opens_one_batch_of_ten_and_requires_result():
    candidate = combine(4, candidate="normal")
    operation, actions, _, _ = build(
        combine(1),
        [
            *direct_no_effect(clean_snapshot=candidate),
            selection(5),
            popup(6, POPUP_PET_MASS_EVOLVE_CONFIRMATION, selection=True, tier="normal"),
            combine_result(7),
            combine(9),
            summon(10, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            selector(11),
            summon_result(12),
            summon(13, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            combine(14),
            popup(15, POPUP_PET_COMBINE_ALL),
            popup(16, POPUP_PET_COMBINE_NO_MATERIAL),
            combine(17),
        ],
        tap_finals=[selection(8)],
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.epic_openings == 1
    assert sum(isinstance(action, OpenTenEpicPets) for action in actions.calls) == 1


def test_single_epic_batch_can_dismiss_multiple_sequential_result_screens():
    operation, actions, _, _ = build(
        combine(1),
        [
            popup(2, POPUP_PET_COMBINE_ALL),
            popup(3, POPUP_PET_EPIC_RUNES_FULL),
            combine(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            selector(6),
            summon_result(7),
            summon_result(8),
            summon_result(9),
            summon(10, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            combine(11),
            popup(12, POPUP_PET_COMBINE_ALL),
            popup(13, POPUP_PET_COMBINE_NO_MATERIAL),
            combine(14),
        ],
        pages=1,
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert sum(isinstance(action, OpenTenEpicPets) for action in actions.calls) == 1
    assert sum(isinstance(action, ClosePetSummonResult) for action in actions.calls) == 3


def test_epic_loop_stops_on_pet_full_and_second_combine_can_relieve():
    runes = popup(3, POPUP_PET_EPIC_RUNES_FULL)
    operation, actions, _, _ = build(
        combine(1),
        [
            popup(2, POPUP_PET_COMBINE_ALL),
            runes,
            combine(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            selector(6),
            summon(7, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD, POPUP_PET_INVENTORY_FULL),
            summon(8, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            combine(9),
            *second_effect(10),
        ],
        tap_finals=[combine(12)],
        pages=1,
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.RELIEVED
    assert result.epic_openings == 0
    assert any(isinstance(action, RejectPetInventoryFull) for action in actions.calls)


def test_rare_capacity_block_cancels_selection_before_changing_tab_and_soft_blocks():
    candidate = combine(4, candidate="rare")
    operation, actions, _, _ = build(
        combine(1),
        [
            *direct_no_effect(clean_snapshot=candidate),
            selection(5),
            popup(6, POPUP_PET_EPIC_RUNES_FULL, selection=True),
            selection(7),
            combine(8),
            summon(9, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            selector(10),
            summon(11, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD, POPUP_PET_INVENTORY_FULL),
            summon(12, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            combine(13),
            popup(14, POPUP_PET_COMBINE_ALL),
            popup(15, POPUP_PET_EPIC_RUNES_FULL),
            combine(16),
        ],
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    cancel_index = next(i for i, action in enumerate(actions.calls) if isinstance(action, CancelPetMassEvolveSelection))
    summon_index = next(i for i, action in enumerate(actions.calls) if isinstance(action, OpenEpicPetSummon))
    assert cancel_index < summon_index


def test_epic_batch_is_never_repeated_even_when_availability_remains():
    runes = popup(3, POPUP_PET_EPIC_RUNES_FULL)
    operation, actions, _, _ = build(
        combine(1),
        [
            popup(2, POPUP_PET_COMBINE_ALL),
            runes,
            combine(4),
            summon(5, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            selector(6),
            summon_result(7),
            summon(8, STATUS_PET_EPIC_AVAILABLE, STATUS_PET_PREMIUM_GOLD),
            combine(9),
            popup(10, POPUP_PET_COMBINE_ALL),
            popup(11, POPUP_PET_COMBINE_NO_MATERIAL),
            combine(12),
        ],
        pages=1,
    )

    result = operation.run()

    assert result.outcome is PetSummonSpaceReliefOutcome.NO_RELIEF_AVAILABLE
    assert result.epic_openings == 1
    assert sum(isinstance(action, OpenTenEpicPets) for action in actions.calls) == 1


def test_cancellation_and_contradictory_precondition_send_no_input():
    operation, actions, _, _ = build(combine(1), [])
    cancelled = operation.run(lambda: True)

    wrong, wrong_actions, _, _ = build(
        summon(1, STATUS_PET_EPIC_UNAVAILABLE), []
    )
    failed = wrong.run()

    assert cancelled.outcome is PetSummonSpaceReliefOutcome.CANCELLED
    assert failed.outcome is PetSummonSpaceReliefOutcome.FAILED
    assert actions.calls == []
    assert wrong_actions.calls == []
