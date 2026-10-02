import numpy as np

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import (
    ACTIVITY_COMBINE_ANIMATION_TAPPABLE,
    MODE_COMBINE_FUSE,
    MODE_COMBINE_TRANSMUTE,
    PANEL_COMBINE_AWAKENED_TRANSMUTE,
    PANEL_COMBINE_ETHEREAL_RANDOM_PART,
    POPUP_COMBINE_ALL,
    POPUP_ETHEREAL_MASS_COMBINE,
    POPUP_ETHEREAL_NO_MATERIAL,
    SCREEN_COMBINE,
    SCREEN_WORLD_BOSS,
    STATUS_COMBINE_ETHEREAL_AVAILABLE,
    STATUS_COMBINE_FUSE_AVAILABLE,
    STATUS_COMBINE_TRANSMUTE_AVAILABLE,
)
from bot.equipment_combine_relief import (
    EquipmentCombineRelief,
    EquipmentCombineReliefOutcome,
    EquipmentCombineReturnPlan,
    EquipmentCombineStrategyOutcome,
    _ethereal_animation_tap,
    _is_combine_animation_transient,
    _is_ethereal_result_animation,
    _is_random_part_panel,
    _is_tappable_animation,
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import (
    ExitCombine,
    SelectCombineFuse,
    SelectCombineTransmute,
    TapCombineAnimation,
    TapEtherealResultAnimation,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.tap_through_animation import (
    TapThroughAnimation,
    TapThroughOutcome,
    TapThroughPolicy,
    TapThroughResult,
)
from bot.verified_transition import VerifiedTransitionOutcome, VerifiedTransitionResult
from bot.runtime_observer import RuntimeWaitTimeout


def snapshot(sequence, *, base=SCREEN_COMBINE, overlays=(), tappable=False):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    # Stable snapshots have bright, unveiled Back chrome.
    h, w = image.shape[:2]
    image[int(.048*h):int(.095*h), int(.792*w):int(.812*w)] = (190, 150, 30)
    observations = (
        (Observation(ACTIVITY_COMBINE_ANIMATION_TAPPABLE, 1.0, ObservationSource.LOCAL_CV),)
        if tappable else ()
    )
    status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(status, sequence, float(sequence), base_context=base, overlays=overlays),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def mode(sequence, active, *statuses):
    return snapshot(sequence, overlays=(active, *statuses))


def panel(sequence, name, popup=None):
    overlays = [MODE_COMBINE_TRANSMUTE, name]
    if popup:
        overlays.append(popup)
    return snapshot(sequence, overlays=tuple(overlays))


class Observer:
    def __init__(self, initial, wait_until_results=None, wait_until_exception=None):
        self.initial = initial
        self.wait_until_results = wait_until_results or []
        self.wait_until_index = 0
        self.wait_until_exception = wait_until_exception

    def observe(self):
        return self.initial

    def wait_until(self, condition, **kwargs):
        if self.wait_until_exception is not None:
            raise self.wait_until_exception
        if self.wait_until_index < len(self.wait_until_results):
            result = self.wait_until_results[self.wait_until_index]
            self.wait_until_index += 1
            assert result.sequence > kwargs["after_sequence"]
            assert condition(result)
            return result
        raise AssertionError("unexpected wait_until call")


class Actions:
    def execute(self, action, geometry):
        pass


class Events:
    def __init__(self):
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))


class Transitions:
    def __init__(self, finals):
        self.finals = list(finals)
        self.calls = []

    def execute(self, name, action, before, **kwargs):
        self.calls.append((name, action, before, kwargs))
        assert kwargs["precondition"](before)
        final = self.finals.pop(0)
        succeeded = final is not None and kwargs["expected"](final)
        return VerifiedTransitionResult(
            name,
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT if succeeded else VerifiedTransitionOutcome.TIMEOUT,
            1,
            0,
            final or before,
            None if succeeded else "scripted failure",
        )


class TapThrough:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, initial, **kwargs):
        self.calls.append((initial, kwargs))
        result = self.results.pop(0)
        if result.outcome is TapThroughOutcome.COMPLETED:
            assert kwargs["expected"](result.final_snapshot)
        return result


def build(initial, transitions, taps=(), wait_until_results=None, wait_until_exception=None):
    observer = Observer(initial, wait_until_results, wait_until_exception)
    driver = Transitions(transitions)
    tapper = TapThrough(taps)
    operation = EquipmentCombineRelief(
        observer,
        Actions(),
        Events(),
        verified_transition=driver,
        tap_through=tapper,
        stable_for=0,
    )
    return operation, driver, tapper


def plan():
    return EquipmentCombineReturnPlan(ExitCombine(), SCREEN_WORLD_BOSS)


def completed(taps, final):
    return TapThroughResult(TapThroughOutcome.COMPLETED, taps, final)


def test_all_three_absent_statuses_skip_and_return_no_relief():
    initial = mode(1, MODE_COMBINE_FUSE)
    operation, driver, tapper = build(
        initial,
        [
            mode(2, MODE_COMBINE_TRANSMUTE),
            mode(3, MODE_COMBINE_FUSE),
            snapshot(4, base=SCREEN_WORLD_BOSS),
        ],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.NO_RELIEF_AVAILABLE
    assert (result.transmute, result.ethereal, result.fuse) == (
        EquipmentCombineStrategyOutcome.SKIPPED,
        EquipmentCombineStrategyOutcome.SKIPPED,
        EquipmentCombineStrategyOutcome.SKIPPED,
    )
    assert [type(call[1]) for call in driver.calls] == [
        SelectCombineTransmute,
        SelectCombineFuse,
        ExitCombine,
    ]
    names = [name for name, _ in operation.events.records]
    assert "equipment_combine_relief.started" in names
    assert "equipment_combine_relief.finished" in names
    assert tapper.calls == []


def test_transmute_effect_is_verified_and_fuse_is_still_evaluated():
    initial = mode(1, MODE_COMBINE_FUSE)
    transmute = mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE)
    animation = snapshot(4, tappable=True)
    cleared = mode(5, MODE_COMBINE_TRANSMUTE)
    operation, _, tapper = build(
        initial,
        [
            transmute,
            snapshot(3, overlays=(MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE, POPUP_COMBINE_ALL)),
            animation,
            mode(6, MODE_COMBINE_FUSE),
            snapshot(7, base=SCREEN_WORLD_BOSS),
        ],
        [completed(2, cleared)],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.RELIEVED
    assert result.transmute is EquipmentCombineStrategyOutcome.EFFECT
    assert result.ethereal is result.fuse is EquipmentCombineStrategyOutcome.SKIPPED
    assert result.animation_taps == 2
    assert len(tapper.calls) == 1


def test_ethereal_effect_returns_to_transmute_and_clears_guard():
    initial = mode(1, MODE_COMBINE_FUSE)
    transmute = mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE)
    random_part = panel(4, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
    animation = snapshot(6, overlays=(MODE_COMBINE_TRANSMUTE,), tappable=True)
    operation, driver, _ = build(
        initial,
        [
            transmute,
            panel(3, PANEL_COMBINE_AWAKENED_TRANSMUTE),
            random_part,
            panel(5, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
            animation,
            mode(8, MODE_COMBINE_TRANSMUTE),
            mode(10, MODE_COMBINE_FUSE),
            snapshot(11, base=SCREEN_WORLD_BOSS),
        ],
        [completed(3, panel(7, PANEL_COMBINE_ETHEREAL_RANDOM_PART))],
        wait_until_results=[mode(9, MODE_COMBINE_TRANSMUTE)],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.RELIEVED
    assert result.ethereal is EquipmentCombineStrategyOutcome.EFFECT
    assert [call[0] for call in driver.calls].index("equipment_combine_relief.ethereal.return_transmute") < [call[0] for call in driver.calls].index("equipment_combine_relief.select_fuse")


def test_ethereal_direct_completion_still_requires_cleared_guard():
    direct_completion = panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
    transmute_cleared = mode(7, MODE_COMBINE_TRANSMUTE)
    operation, driver, tapper = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
            panel(3, PANEL_COMBINE_AWAKENED_TRANSMUTE),
            panel(4, PANEL_COMBINE_ETHEREAL_RANDOM_PART),
            panel(5, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
            direct_completion,
            transmute_cleared,
            mode(9, MODE_COMBINE_FUSE),
            snapshot(10, base=SCREEN_WORLD_BOSS),
        ],
        wait_until_results=[mode(8, MODE_COMBINE_TRANSMUTE)],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.RELIEVED
    assert result.ethereal is EquipmentCombineStrategyOutcome.EFFECT
    assert result.animation_taps == 0
    assert tapper.calls == []
    assert "equipment_combine_relief.ethereal_animation_completed_before_tappable" in {
        name for name, _ in operation.events.records
    }
    assert driver.calls[5][0] == "equipment_combine_relief.ethereal.return_transmute"


def test_ethereal_direct_popup_close_is_not_effect_when_guard_remains():
    operation, _, tapper = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
            panel(3, PANEL_COMBINE_AWAKENED_TRANSMUTE),
            panel(4, PANEL_COMBINE_ETHEREAL_RANDOM_PART),
            panel(5, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
            panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART),
            mode(7, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
        ],
        wait_until_exception=RuntimeWaitTimeout(after_sequence=7, timeout=15.0, last_snapshot=mode(7, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE)),
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.FAILED
    assert result.ethereal is EquipmentCombineStrategyOutcome.FAILED
    assert tapper.calls == []


def test_fuse_effect_is_evaluated_fresh_after_transmute():
    initial = mode(1, MODE_COMBINE_FUSE)
    operation, _, _ = build(
        initial,
        [
            mode(2, MODE_COMBINE_TRANSMUTE),
            mode(3, MODE_COMBINE_FUSE, STATUS_COMBINE_FUSE_AVAILABLE),
            snapshot(4, overlays=(MODE_COMBINE_FUSE, STATUS_COMBINE_FUSE_AVAILABLE, POPUP_COMBINE_ALL)),
            snapshot(5, overlays=(MODE_COMBINE_FUSE,), tappable=True),
            snapshot(7, base=SCREEN_WORLD_BOSS),
        ],
        [completed(1, mode(6, MODE_COMBINE_FUSE))],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.RELIEVED
    assert result.fuse is EquipmentCombineStrategyOutcome.EFFECT


def test_transmute_can_generate_fresh_fuse_availability():
    initial = mode(1, MODE_COMBINE_FUSE)
    cleared_transmute = mode(5, MODE_COMBINE_TRANSMUTE)
    operation, _, _ = build(
        initial,
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE),
            snapshot(3, overlays=(MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE, POPUP_COMBINE_ALL)),
            snapshot(4, tappable=True),
            mode(6, MODE_COMBINE_FUSE, STATUS_COMBINE_FUSE_AVAILABLE),
            snapshot(7, overlays=(MODE_COMBINE_FUSE, STATUS_COMBINE_FUSE_AVAILABLE, POPUP_COMBINE_ALL)),
            snapshot(8, overlays=(MODE_COMBINE_FUSE,), tappable=True),
            snapshot(10, base=SCREEN_WORLD_BOSS),
        ],
        [completed(2, cleared_transmute), completed(4, mode(9, MODE_COMBINE_FUSE))],
    )

    result = operation.run(plan())

    assert result.transmute is result.fuse is EquipmentCombineStrategyOutcome.EFFECT
    assert result.animation_taps == 6


def test_present_status_without_animation_is_bounded_failure_not_no_relief():
    operation, _, _ = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE),
            snapshot(3, overlays=(MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE, POPUP_COMBINE_ALL)),
            None,
        ],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.FAILED
    assert result.transmute is EquipmentCombineStrategyOutcome.FAILED


def test_defensive_ethereal_no_material_is_explicit_failure_and_not_effect():
    operation, driver, _ = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
            panel(3, PANEL_COMBINE_AWAKENED_TRANSMUTE),
            panel(4, PANEL_COMBINE_ETHEREAL_RANDOM_PART),
            panel(5, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_NO_MATERIAL),
            panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART),
            mode(7, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
        ],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.FAILED
    assert result.ethereal is EquipmentCombineStrategyOutcome.FAILED
    assert driver.calls[-1][0] == "equipment_combine_relief.ethereal.restore_transmute"


def test_cancellation_is_distinct_and_sends_no_transition():
    operation, driver, _ = build(mode(1, MODE_COMBINE_FUSE), [])

    result = operation.run(plan(), lambda: True)

    assert result.outcome is EquipmentCombineReliefOutcome.CANCELLED
    assert driver.calls == []


def test_cancellation_from_shared_animation_primitive_is_propagated():
    animation = snapshot(4, tappable=True)
    operation, _, _ = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE),
            snapshot(3, overlays=(MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_TRANSMUTE_AVAILABLE, POPUP_COMBINE_ALL)),
            animation,
        ],
        [TapThroughResult(TapThroughOutcome.CANCELLED, 1, animation)],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.CANCELLED
    assert result.transmute is EquipmentCombineStrategyOutcome.CANCELLED
    assert result.animation_taps == 1


def test_exact_return_plan_failure_does_not_claim_success():
    operation, driver, _ = build(
        mode(1, MODE_COMBINE_FUSE),
        [mode(2, MODE_COMBINE_TRANSMUTE), mode(3, MODE_COMBINE_FUSE), None],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.FAILED
    assert result.error == "equipment_return_failed"
    assert isinstance(driver.calls[-1][1], ExitCombine)


# --- Ethereal result animation phase (USER_GT 2026-09-28) ---
#
# After the single effective Mass Combine confirm, a result animation appears
# whose concrete item is irrelevant and may vary. The live failure frames
# (wings + item card, no sword landmark) are UNKNOWN snapshots; the contract
# is to traverse them with safe taps until the Random Part BASE is recovered.


def custom_snapshot(sequence, status, base, overlays=(), observation_names=(), base_candidates=()):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    observations = tuple(
        Observation(name, 1.0, ObservationSource.LOCAL_CV)
        for name in observation_names
    )
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), observations),
        ResolvedState(status, sequence, float(sequence), base_context=base, overlays=overlays, base_candidates=base_candidates),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def result_phase(sequence, observation_names=()):
    return custom_snapshot(sequence, ResolutionStatus.UNKNOWN, None, (), observation_names)


def test_ethereal_result_animation_matches_unknown_phase_regardless_of_item():
    assert _is_ethereal_result_animation(result_phase(6))
    assert _is_ethereal_result_animation(snapshot(7, base=None))
    # Displayed item/result content never participates in the predicate.
    assert _is_ethereal_result_animation(result_phase(8, ("landmark.irrelevant_item_detail",)))


def test_ethereal_result_animation_rejects_resolved_ambiguous_and_popup():
    assert not _is_ethereal_result_animation(panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART))
    assert not _is_ethereal_result_animation(snapshot(7, tappable=True))
    modal = snapshot(
        8,
        overlays=(MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
    )
    assert not _is_ethereal_result_animation(modal)
    assert not _is_ethereal_result_animation(
        custom_snapshot(9, ResolutionStatus.AMBIGUOUS, None, base_candidates=("screen.combine", "screen.lobby"))
    )
    assert not _is_ethereal_result_animation(
        custom_snapshot(10, ResolutionStatus.UNKNOWN, None, (POPUP_ETHEREAL_MASS_COMBINE,))
    )


def test_ethereal_animation_tap_selects_emblem_for_landmark_and_safe_tap_for_phase():
    assert isinstance(_ethereal_animation_tap(snapshot(6, tappable=True)), TapCombineAnimation)
    assert isinstance(_ethereal_animation_tap(result_phase(7)), TapEtherealResultAnimation)


def test_ethereal_result_animation_without_landmark_traverses_to_random_part():
    random_part = panel(4, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
    animation = result_phase(6)
    recovered = panel(7, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
    operation, driver, tapper = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
            panel(3, PANEL_COMBINE_AWAKENED_TRANSMUTE),
            random_part,
            panel(5, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
            animation,
            mode(8, MODE_COMBINE_TRANSMUTE),
            mode(9, MODE_COMBINE_FUSE),
            snapshot(10, base=SCREEN_WORLD_BOSS),
        ],
        [completed(3, recovered)],
        wait_until_results=[mode(9, MODE_COMBINE_TRANSMUTE)],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.RELIEVED
    assert result.ethereal is EquipmentCombineStrategyOutcome.EFFECT
    assert result.animation_taps == 3
    # Mass Combine and its consumptive confirm run exactly once each.
    names = [call[0] for call in driver.calls]
    assert names.count("equipment_combine_relief.ethereal.open_mass_combine") == 1
    assert names.count("equipment_combine_relief.ethereal.confirm_mass_combine") == 1
    assert names.index("equipment_combine_relief.ethereal.return_transmute") < names.index("equipment_combine_relief.select_fuse")
    # Unified drain contract installed for the animation phase.
    (drain_initial, kwargs), = tapper.calls
    assert drain_initial is animation
    assert kwargs["expected"](recovered)
    assert not kwargs["expected"](animation)
    assert kwargs["tappable"](animation)
    assert kwargs["tappable"](snapshot(20, tappable=True))
    assert not kwargs["tappable"](
        snapshot(21, overlays=(MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE))
    )
    assert isinstance(kwargs["action_for"](animation), TapEtherealResultAnimation)
    assert isinstance(kwargs["action_for"](snapshot(22, tappable=True)), TapCombineAnimation)


def test_ethereal_confirm_miss_without_verified_effect_stays_failed_without_drain():
    operation, driver, tapper = build(
        mode(1, MODE_COMBINE_FUSE),
        [
            mode(2, MODE_COMBINE_TRANSMUTE, STATUS_COMBINE_ETHEREAL_AVAILABLE),
            panel(3, PANEL_COMBINE_AWAKENED_TRANSMUTE),
            panel(4, PANEL_COMBINE_ETHEREAL_RANDOM_PART),
            panel(5, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
            panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
        ],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.FAILED
    assert result.ethereal is EquipmentCombineStrategyOutcome.FAILED
    assert tapper.calls == []
    assert [call[0] for call in driver.calls].count("equipment_combine_relief.ethereal.confirm_mass_combine") == 1


class DrainObserver:
    def __init__(self, following=(), timeout=False):
        self.following = list(following)
        self.timeout = timeout

    def wait_until(self, condition, **kwargs):
        if self.timeout:
            raise RuntimeWaitTimeout(
                after_sequence=kwargs["after_sequence"],
                timeout=kwargs["timeout"],
                last_snapshot=None,
            )
        value = self.following.pop(0)
        assert condition(value)
        return value


class DrainActions:
    def __init__(self):
        self.executed = []

    def execute(self, action, geometry):
        self.executed.append(action)


def drain(initial, following=(), *, timeout=False, max_taps=20, cancel=lambda: False):
    actions = DrainActions()
    primitive = TapThroughAnimation(
        DrainObserver(following, timeout=timeout),
        actions,
        events=None,
        clock=lambda: 0.0,
        sleeper=lambda duration: None,
    )
    result = primitive.run(
        initial,
        action=TapCombineAnimation(),
        action_for=_ethereal_animation_tap,
        expected=_is_random_part_panel,
        tappable=lambda item: _is_tappable_animation(item) or _is_ethereal_result_animation(item),
        transient=_is_combine_animation_transient,
        cancel_requested=cancel,
        policy=TapThroughPolicy(timeout=5, tap_interval=0.5, max_taps=max_taps),
    )
    return result, actions


def test_drain_traverses_mixed_landmark_and_result_phase_with_matching_taps():
    done = panel(8, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
    result, actions = drain(snapshot(6, tappable=True), [result_phase(7), done])

    assert result.outcome is TapThroughOutcome.COMPLETED
    assert result.tap_count == 2
    assert [type(action).__name__ for action in actions.executed] == [
        "TapCombineAnimation",
        "TapEtherealResultAnimation",
    ]
    assert result.final_snapshot is done


def test_drain_stops_on_modal_popup_without_input():
    modal = snapshot(
        6,
        overlays=(MODE_COMBINE_TRANSMUTE, PANEL_COMBINE_ETHEREAL_RANDOM_PART, POPUP_ETHEREAL_MASS_COMBINE),
    )
    result, actions = drain(modal)

    assert result.outcome is TapThroughOutcome.INCOMPATIBLE_STATE
    assert actions.executed == []


def test_drain_stops_on_foreign_or_ambiguous_surface_without_input():
    foreign, foreign_actions = drain(snapshot(6, base="screen.lobby"))
    assert foreign.outcome is TapThroughOutcome.INCOMPATIBLE_STATE
    assert foreign_actions.executed == []
    ambiguous, ambiguous_actions = drain(
        custom_snapshot(6, ResolutionStatus.AMBIGUOUS, None, base_candidates=("screen.combine", "screen.lobby"))
    )
    assert ambiguous.outcome is TapThroughOutcome.INCOMPATIBLE_STATE
    assert ambiguous_actions.executed == []


def test_drain_cancellation_stops_before_input():
    result, actions = drain(result_phase(6), cancel=lambda: True)

    assert result.outcome is TapThroughOutcome.CANCELLED
    assert actions.executed == []


def test_drain_loop_is_bounded():
    maximum, maximum_actions = drain(result_phase(6), [result_phase(7)], max_taps=1)
    assert maximum.outcome is TapThroughOutcome.MAX_TAPS
    assert maximum.tap_count == 1
    assert maximum_actions.executed != []
    timeout, _ = drain(result_phase(6), timeout=True)
    assert timeout.outcome is TapThroughOutcome.TIMEOUT


def test_ethereal_result_veil_over_resolved_random_part_blocks_completion():
    veiled = panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
    veiled.frame.image[:] = 40
    assert not _is_random_part_panel(veiled)
    assert _is_ethereal_result_animation(veiled)
    result, actions = drain(veiled, [panel(7, PANEL_COMBINE_ETHEREAL_RANDOM_PART)])
    assert result.succeeded and result.tap_count == 1
    assert isinstance(actions.executed[0], TapEtherealResultAnimation)


def test_native_ethereal_result_veil_and_clean_panel():
    import cv2
    from pathlib import Path
    from dataclasses import replace
    from bot.perception.combine import combine_controls_undimmed
    root = Path(__file__).resolve().parents[1]/"artifacts/mw_stabilization"
    for name, clean in [("ethereal_animation_before.png", False),
                        ("ethereal_animation_after_1.png", True)]:
        image = cv2.imread(str(root/name))
        assert image is not None
        assert combine_controls_undimmed(image) is clean
        original = panel(6, PANEL_COMBINE_ETHEREAL_RANDOM_PART)
        current = replace(original, frame=FrameSnapshot(image, 6., 6),
                          geometry=FrameGeometry.from_frame(image))
        assert _is_random_part_panel(current) is clean
        assert _is_ethereal_result_animation(current) is not clean


def test_native_fuse_result_resolves_tappable_without_lowering_confidence():
    import cv2
    from pathlib import Path
    from bot.catalog import build_default_resolver
    from bot.perception import build_default_perception
    from bot.runtime_observer import RuntimeObserver
    root = Path(__file__).resolve().parents[1]
    image = cv2.imread(str(root/"artifacts/mw_stabilization/fuse_animation_native.png"))
    assert image is not None
    class Source:
        def get_frame(self):
            return FrameSnapshot(image, 1., 1)
    current = RuntimeObserver(Source(), build_default_perception(root),
                              build_default_resolver()).observe()
    assert current.state.status is ResolutionStatus.RESOLVED
    assert current.state.base_context == SCREEN_COMBINE
    assert _is_tappable_animation(current)
    observation = current.observations.best(ACTIVITY_COMBINE_ANIMATION_TAPPABLE)
    assert observation.confidence >= .99
