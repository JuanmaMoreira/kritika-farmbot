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
)
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import ExitCombine, SelectCombineFuse, SelectCombineTransmute
from bot.state import ResolutionStatus, ResolvedState
from bot.tap_through_animation import TapThroughOutcome, TapThroughResult
from bot.verified_transition import VerifiedTransitionOutcome, VerifiedTransitionResult


def snapshot(sequence, *, base=SCREEN_COMBINE, overlays=(), tappable=False):
    image = np.zeros((40, 80, 3), dtype=np.uint8)
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
    def __init__(self, initial):
        self.initial = initial

    def observe(self):
        return self.initial

    def wait_until(self, condition, **kwargs):
        raise AssertionError("scripted tap driver should own animation waits")


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


def build(initial, transitions, taps=()):
    observer = Observer(initial)
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
            mode(9, MODE_COMBINE_FUSE),
            snapshot(10, base=SCREEN_WORLD_BOSS),
        ],
        [completed(3, panel(7, PANEL_COMBINE_ETHEREAL_RANDOM_PART))],
    )

    result = operation.run(plan())

    assert result.outcome is EquipmentCombineReliefOutcome.RELIEVED
    assert result.ethereal is EquipmentCombineStrategyOutcome.EFFECT
    assert [call[0] for call in driver.calls].index("equipment_combine_relief.ethereal.return_transmute") < [call[0] for call in driver.calls].index("equipment_combine_relief.select_fuse")


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
