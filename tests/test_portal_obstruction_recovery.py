"""Regression for the transversal portal-notification recovery seam."""

from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import ActionExecutor, FrameGeometry
from bot.capture import FrameSnapshot
from bot.geometry import relative_point_to_pixel
from bot.obstruction_recovery import (
    ObstructionRecoveryPolicy,
    PortalObstructionRecovery,
)
from bot.observations import ObservationBatch
from bot.portal_notification import PortalNotificationProbe, PortalProbeOutcome
from bot.runtime_observer import (
    RuntimeFacts,
    RuntimeSnapshot,
    RuntimeWaitCancelled,
    RuntimeWaitAborted,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import DismissPortalNotification, OpenQuickMenu, SelectPetSummon
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionOutcome,
    VerifiedTransitionPolicy,
)

BEFORE = "screen.combine"
EXPECTED = "screen.socket"
OTHER = "screen.other"


def _snapshot(sequence, base, status=ResolutionStatus.RESOLVED):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    timestamp = float(sequence)
    return RuntimeSnapshot(
        frame=FrameSnapshot(image=image, timestamp=timestamp, sequence=sequence),
        observations=ObservationBatch(sequence=sequence, timestamp=timestamp),
        state=ResolvedState(
            status=status,
            sequence=sequence,
            timestamp=timestamp,
            base_context=base if status is ResolutionStatus.RESOLVED else None,
            base_candidates=("screen.pets_manage", "screen.guild")
                if status is ResolutionStatus.AMBIGUOUS else (),
        ),
        facts=RuntimeFacts(),
        geometry=FrameGeometry.from_frame(image),
    )


def _timeout(after_sequence, last_snapshot, timeout=6.0):
    return RuntimeWaitTimeout(
        after_sequence=after_sequence,
        timeout=timeout,
        last_snapshot=last_snapshot,
    )


class ScriptedObserver:
    def __init__(self, waits, observes=()):
        self.waits = list(waits)
        self.observes = list(observes)

    def wait_until(
        self,
        condition,
        *,
        after_sequence,
        timeout,
        abort_if=None,
        stable_for=0.0,
        cancel_requested=None,
    ):
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        if abort_if is not None and abort_if(item):
            raise RuntimeWaitAborted(item)
        assert condition(item)
        return item

    def observe(self):
        return self.observes.pop(0)


class Actions:
    def __init__(self):
        self.calls = []
        self.geometries = []

    def target_for(self, action):
        from types import SimpleNamespace
        return ActionExecutor(SimpleNamespace(tap=lambda *args: None)).target_for(action)

    def execute(self, action, geometry):
        self.calls.append(action)
        self.geometries.append(geometry)
        return None


class ScriptedProbe:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def probe(self, frame_image):
        self.calls += 1
        return self.outcomes.pop(0)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleeper(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _transition(observer, actions, probe, policy=None, clock=None):
    shared = clock or FakeClock()
    recovery = PortalObstructionRecovery(
        observer,
        actions,
        probe,
        policy=policy or ObstructionRecoveryPolicy(),
        clock=shared.clock,
        sleeper=shared.sleeper,
    )
    return VerifiedTransition(
        observer, actions, obstruction_recovery=recovery
    )


def _productive_calls(actions):
    return [call for call in actions.calls if isinstance(call, OpenQuickMenu)]


def _dismiss_calls(actions):
    return [
        call for call in actions.calls if isinstance(call, DismissPortalNotification)
    ]


INSIDE = (0.20, 0.12, 0.30, 0.24)
OUTSIDE = (0.60, 0.60, 0.80, 0.80)


@pytest.mark.parametrize("region,should_recover", [(INSIDE, True), (OUTSIDE, False)])
def test_failed_necessary_signal_only_recovers_when_its_roi_intersects(region, should_recover):
    from dataclasses import replace
    from bot.observations import Observation, ObservationSource

    blocked = _snapshot(1, BEFORE)
    fresh = _snapshot(2, BEFORE)
    fresh = replace(fresh, observations=ObservationBatch(2, 2.0, (
        Observation("landmark.required", 1.0, ObservationSource.LOCAL_CV, region=region),
    )))
    observer = ScriptedObserver([_snapshot(3, EXPECTED)], [fresh])
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    result = _transition(observer, actions, probe).execute(
        "test.signal", OpenQuickMenu(), blocked,
        precondition=lambda s: bool(s.observations.find("landmark.required")),
        precondition_regions=(region,),
        expected=lambda s: s.state.base_context == EXPECTED,
        policy=VerifiedTransitionPolicy(),
    )
    assert result.succeeded is should_recover
    assert probe.calls == (2 if should_recover else 0)
    assert len(_dismiss_calls(actions)) == int(should_recover)
    assert len(_productive_calls(actions)) == int(should_recover)
    if should_recover:
        assert result.action_source_snapshot is fresh


def test_failed_postcondition_recovers_same_intention_without_productive_retry():
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        [_snapshot(4, BEFORE), _snapshot(5, EXPECTED)],
    )
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    result = _transition(observer, actions, probe).execute(
        "test.postcondition", OpenQuickMenu(), _snapshot(1, BEFORE),
        expected=lambda s: s.state.base_context == EXPECTED,
        expected_regions=(INSIDE,), policy=VerifiedTransitionPolicy(),
    )
    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY
    assert result.recovery_after_action
    assert len(_productive_calls(actions)) == len(_dismiss_calls(actions)) == 1


def test_missing_causal_roi_does_not_probe_even_after_timeouts():
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        [_snapshot(4, BEFORE)],
    )
    actions = Actions()
    probe = ScriptedProbe([])
    result = _transition(observer, actions, probe).execute(
        "test.no_cause", OpenQuickMenu(), _snapshot(1, BEFORE),
        expected=lambda s: False, policy=VerifiedTransitionPolicy(),
    )
    assert not result.succeeded
    assert probe.calls == 0
    assert _dismiss_calls(actions) == []


def test_successful_transition_recovers_only_covered_target_using_fresh_geometry():
    from dataclasses import replace
    before = _snapshot(1, "screen.pets_manage")
    fresh = _snapshot(2, "screen.pets_manage")
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    fresh = replace(fresh, frame=FrameSnapshot(image, 2.0, 2), geometry=FrameGeometry.from_frame(image))
    observer = ScriptedObserver([_snapshot(3, "screen.pet_summon")], [fresh])
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    result = _transition(observer, actions, probe).execute(
        "test.input", SelectPetSummon(), before,
        precondition=lambda s: s.state.base_context == "screen.pets_manage",
        expected=lambda s: s.state.base_context == "screen.pet_summon",
        policy=VerifiedTransitionPolicy(),
    )
    assert result.succeeded
    assert [type(a) for a in actions.calls] == [DismissPortalNotification, SelectPetSummon]
    assert actions.geometries == [before.geometry, fresh.geometry]
    assert result.action_source_snapshot is fresh
    assert not result.recovery_after_action


def test_unaffected_success_has_no_probe_or_extra_observation():
    observer = ScriptedObserver([_snapshot(2, EXPECTED)])
    actions = Actions()
    probe = ScriptedProbe([])
    result = _transition(observer, actions, probe).execute(
        "test.unaffected", OpenQuickMenu(), _snapshot(1, BEFORE),
        precondition=lambda s: True, expected=lambda s: True,
        policy=VerifiedTransitionPolicy(),
    )
    assert result.succeeded
    assert probe.calls == 0
    assert len(actions.calls) == 1


def test_satisfied_signal_with_intersecting_roi_never_probes():
    actions, probe = Actions(), ScriptedProbe([])
    recovery = _transition(ScriptedObserver([]), actions, probe).obstruction_recovery
    assert recovery.attempt(_snapshot(1, BEFORE), lambda s: True, regions=(INSIDE,)) is None
    assert probe.calls == 0 and actions.calls == []


def test_precondition_is_revalidated_after_dismiss_before_original_input():
    observer = ScriptedObserver([], [_snapshot(2, "screen.guild")])
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    result = _transition(observer, actions, probe).execute(
        "test.changed_base", SelectPetSummon(), _snapshot(1, "screen.pets_manage"),
        precondition=lambda s: s.state.base_context == "screen.pets_manage",
        expected=lambda s: True, policy=VerifiedTransitionPolicy(),
    )
    assert result.outcome is VerifiedTransitionOutcome.PRECONDITION_REJECTED
    assert [type(a) for a in actions.calls] == [DismissPortalNotification]


@pytest.mark.parametrize("outcome", [PortalProbeOutcome.INCONCLUSIVE, PortalProbeOutcome.ABSENT, None])
def test_unconfirmed_probe_never_authorizes_dismiss(outcome):
    observer, actions = ScriptedObserver([]), Actions()
    probe = ScriptedProbe([outcome])
    recovery = _transition(observer, actions, probe).obstruction_recovery
    assert recovery.attempt(_snapshot(1, BEFORE), lambda s: False, regions=(INSIDE,)) is None
    assert actions.calls == []


@pytest.mark.parametrize("base,status,overlays", [
    (None, ResolutionStatus.UNKNOWN, ()),
    ("screen.world_boss_battle", ResolutionStatus.RESOLVED, ()),
    ("screen.character_select", ResolutionStatus.RESOLVED, ()),
    ("screen.quests", ResolutionStatus.RESOLVED, ()),
    ("screen.pet_summon_result", ResolutionStatus.RESOLVED, ()),
    (BEFORE, ResolutionStatus.RESOLVED, ("menu.quick",)),
    (BEFORE, ResolutionStatus.RESOLVED, ("popup.combine_all",)),
])
def test_invalid_physical_context_never_probes_or_dismisses(base, status, overlays):
    from dataclasses import replace
    before = _snapshot(1, base, status)
    before = replace(before, state=replace(before.state, overlays=overlays))
    actions, probe = Actions(), ScriptedProbe([])
    recovery = _transition(ScriptedObserver([]), actions, probe).obstruction_recovery
    assert recovery.attempt(before, lambda s: False, regions=(INSIDE,)) is None
    assert probe.calls == 0
    assert actions.calls == []


@pytest.mark.parametrize("outcome", [PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.INCONCLUSIVE])
def test_persistent_or_uncertain_portal_fails_after_one_dismiss(outcome):
    observer = ScriptedObserver([], [_snapshot(i, BEFORE) for i in range(2, 6)])
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED] + [outcome] * 4)
    recovery = _transition(observer, actions, probe,
        policy=ObstructionRecoveryPolicy(settle_timeout=1.0)).obstruction_recovery
    with pytest.raises(RuntimeWaitTimeout):
        recovery.attempt(_snapshot(1, BEFORE), lambda s: False, regions=(INSIDE,))
    assert len(_dismiss_calls(actions)) == 1


def test_fade_wait_is_passive_and_stops_on_fresh_absence():
    observer = ScriptedObserver([], [_snapshot(i, BEFORE) for i in range(2, 5)])
    actions, clock = Actions(), FakeClock()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED] * 3 + [PortalProbeOutcome.ABSENT])
    recovery = _transition(observer, actions, probe, clock=clock).obstruction_recovery
    result = recovery.attempt(_snapshot(1, BEFORE), lambda s: False, regions=(INSIDE,))
    assert result.sequence == 4
    assert len(_dismiss_calls(actions)) == 1
    assert clock.now == 1.0


def test_stale_post_dismiss_frame_cannot_be_reused():
    before = _snapshot(1, BEFORE)
    actions = Actions()
    recovery = _transition(ScriptedObserver([], [before]), actions,
        ScriptedProbe([PortalProbeOutcome.CONFIRMED])).obstruction_recovery
    with pytest.raises(RuntimeWaitTimeout):
        recovery.attempt(before, lambda s: False, regions=(INSIDE,))
    assert len(_dismiss_calls(actions)) == 1


def test_cancellation_during_settle_propagates_without_more_input():
    clock, actions = FakeClock(), Actions()
    recovery = PortalObstructionRecovery(
        ScriptedObserver([], [_snapshot(2, BEFORE)]), actions,
        ScriptedProbe([PortalProbeOutcome.CONFIRMED] * 2),
        clock=clock.clock, sleeper=clock.sleeper,
        cancel_requested=lambda: clock.now >= 0.5,
    )
    with pytest.raises(RuntimeWaitCancelled):
        recovery.attempt(_snapshot(1, BEFORE), lambda s: False, regions=(INSIDE,))
    assert len(_dismiss_calls(actions)) == 1


def test_direct_pet_navigation_uses_shared_transition_for_covered_target():
    from types import SimpleNamespace
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    observer = ScriptedObserver([_snapshot(3, "screen.pet_summon")], [_snapshot(2, "screen.pets_manage")])
    actions = Actions()
    transition = _transition(observer, actions,
        ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT]))
    flow = SummonPetDailyFlow(observer, actions, SimpleNamespace(record=lambda *a, **k: None),
        SimpleNamespace(run=lambda: None), verified_transition=transition)
    result = flow._act_and_wait(SelectPetSummon(), lambda s: s.state.base_context == "screen.pet_summon",
        _snapshot(1, "screen.pets_manage"), flow._is_clean_manage, 6.0, 0.0)
    assert result.sequence == 3
    assert [type(a) for a in actions.calls] == [DismissPortalNotification, SelectPetSummon]


def test_declared_missing_mode_recovers_an_aborted_wait_without_repeating_action():
    from dataclasses import replace
    from bot.equipment_combine_relief import _missing_mode_region
    from bot.perception.specs import COMBINE_FUSE_ACTIVE_SPEC
    before = _snapshot(1, BEFORE)
    missing = _snapshot(2, BEFORE)
    fresh = _snapshot(3, BEFORE)
    fresh = replace(fresh, state=replace(fresh.state, overlays=("mode.combine_fuse",)))
    observer = ScriptedObserver([missing], [fresh])
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    result = _transition(observer, actions, probe).execute(
        "test.missing_mode", OpenQuickMenu(), before,
        expected=lambda s: "mode.combine_fuse" in s.state.overlays,
        expected_regions=lambda s: _missing_mode_region(s, COMBINE_FUSE_ACTIVE_SPEC),
        abort_if=lambda s: not s.state.overlays,
        policy=VerifiedTransitionPolicy(),
    )
    assert result.succeeded
    assert result.recovery_after_action
    assert result.final_snapshot is fresh
    assert len(_productive_calls(actions)) == len(_dismiss_calls(actions)) == 1


def test_present_mode_or_foreign_base_does_not_declare_an_occluded_signal():
    from dataclasses import replace
    from bot.equipment_combine_relief import _missing_mode_region
    from bot.observations import Observation, ObservationSource
    from bot.perception.specs import COMBINE_FUSE_ACTIVE_SPEC as spec
    current = _snapshot(1, BEFORE)
    current = replace(current, observations=ObservationBatch(1, 1.0, (
        Observation(spec.name, 1.0, ObservationSource.LOCAL_CV, region=spec.region),
    )))
    assert _missing_mode_region(current, spec) == ()
    assert _missing_mode_region(_snapshot(2, "screen.guild"), spec) == ()


def test_executor_dismiss_uses_existing_target_and_never_opens_quick_menu():
    from types import SimpleNamespace
    from bot.action_executor import DEFAULT_PORTAL_ACTION_TARGETS, DEFAULT_ROTATION_ACTION_TARGETS
    taps = []
    actions = ActionExecutor(SimpleNamespace(tap=lambda *xy: taps.append(xy)))
    before, fresh = _snapshot(1, BEFORE), _snapshot(2, BEFORE)
    recovery = PortalObstructionRecovery(ScriptedObserver([], [fresh]), actions,
        ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT]))
    assert recovery.attempt(before, lambda s: False, regions=(INSIDE,)) is fresh
    assert taps == [relative_point_to_pixel(DEFAULT_PORTAL_ACTION_TARGETS.dismiss_portal_notification, 200, 100)]
    assert taps[0] != relative_point_to_pixel(DEFAULT_ROTATION_ACTION_TARGETS.open_quick_menu, 200, 100)


def test_unaffected_direct_pet_navigation_preserves_wait_and_has_no_probe():
    from types import SimpleNamespace
    from bot.semantic_actions import SelectPetCombine
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    observer = ScriptedObserver([_snapshot(2, "screen.pet_combine")])
    actions, probe = Actions(), ScriptedProbe([])
    flow = SummonPetDailyFlow(observer, actions, SimpleNamespace(record=lambda *a, **k: None),
        SimpleNamespace(run=lambda: None), verified_transition=_transition(observer, actions, probe))
    flow._act_and_wait(SelectPetCombine(), lambda s: s.state.base_context == "screen.pet_combine",
        _snapshot(1, "screen.pets_manage"), flow._is_clean_manage, 6.0, 0.0)
    assert actions.calls == [SelectPetCombine()]
    assert probe.calls == 0


def test_productive_pet_builder_keeps_shared_recovery(monkeypatch):
    from types import SimpleNamespace
    from bot import flow_registry
    observer, actions = ScriptedObserver([]), Actions()
    transition = _transition(observer, actions, ScriptedProbe([]))
    events = SimpleNamespace(record=lambda *a, **k: None)
    dependencies = SimpleNamespace(
        observer=observer, actions=actions, events=events,
        build_verified_transition=lambda: transition,
        pet_summon_space_relief=SimpleNamespace(run=lambda: None),
        cancel_requested=lambda: False,
    )
    scoped = ScriptedObserver([])
    monkeypatch.setattr(flow_registry, "_summon_pet_observer_for", lambda *args: scoped)
    flow = flow_registry._build_summon_pet_daily(dependencies)
    assert flow.transition.obstruction_recovery is transition.obstruction_recovery
    assert flow.transition.obstruction_recovery.observer is observer
    assert flow.transition.observer is flow.summon_observer is scoped


@pytest.mark.parametrize("status,base", [
    (ResolutionStatus.UNKNOWN, None),
    (ResolutionStatus.AMBIGUOUS, None),
    (ResolutionStatus.RESOLVED, "screen.guild"),
])
@pytest.mark.parametrize("after_dismiss", [False, True])
def test_pet_navigation_rejects_uncertain_or_foreign_context(status, base, after_dismiss):
    from types import SimpleNamespace
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    invalid = _snapshot(2, base, status)
    observer = ScriptedObserver([], [invalid] if after_dismiss else [])
    actions, probe = Actions(), ScriptedProbe([
        PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT,
    ] if after_dismiss else [])
    flow = SummonPetDailyFlow(observer, actions, SimpleNamespace(record=lambda *a, **k: None),
        SimpleNamespace(run=lambda: None), verified_transition=_transition(observer, actions, probe))
    with pytest.raises(RuntimeError, match="summon_pet_navigation_guard_missing"):
        flow._act_and_wait(SelectPetSummon(), lambda s: False,
            _snapshot(1, "screen.pets_manage") if after_dismiss else invalid,
            flow._is_clean_manage, 6.0, 0.0)
    assert actions.calls == ([DismissPortalNotification()] if after_dismiss else [])
    assert probe.calls == (2 if after_dismiss else 0)


@pytest.mark.parametrize("settle_outcome", [PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.INCONCLUSIVE])
def test_pet_navigation_stops_after_bounded_failed_cleanup(settle_outcome):
    from types import SimpleNamespace
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    observer = ScriptedObserver([], [_snapshot(i, "screen.pets_manage") for i in range(2, 5)])
    actions, clock = Actions(), FakeClock()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED] + [settle_outcome] * 3)
    flow = SummonPetDailyFlow(observer, actions, SimpleNamespace(record=lambda *a, **k: None),
        SimpleNamespace(run=lambda: None), verified_transition=_transition(observer, actions, probe,
            policy=ObstructionRecoveryPolicy(settle_timeout=1.0), clock=clock))
    with pytest.raises(RuntimeWaitTimeout):
        flow._act_and_wait(SelectPetSummon(), lambda s: False,
            _snapshot(1, "screen.pets_manage"), flow._is_clean_manage, 6.0, 0.0)
    assert actions.calls == [DismissPortalNotification()]
    assert clock.now == 1.0


def test_pet_navigation_cancellation_after_recovery_prevents_input():
    from types import SimpleNamespace
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    cancelled = False

    def recover(*args):
        nonlocal cancelled
        cancelled = True
        return _snapshot(2, "screen.pets_manage")

    actions = Actions()
    flow = SummonPetDailyFlow(ScriptedObserver([]), actions,
        SimpleNamespace(record=lambda *a, **k: None), SimpleNamespace(run=lambda: None),
        verified_transition=SimpleNamespace(recover_input=recover), cancel_requested=lambda: cancelled)
    with pytest.raises(RuntimeWaitCancelled):
        flow._act_and_wait(SelectPetSummon(), lambda s: False,
            _snapshot(1, "screen.pets_manage"), flow._is_clean_manage, 6.0, 0.0)
    assert actions.calls == []


@pytest.mark.parametrize("outcome", ["success", "lost_daily", "outcome_timeout"])
def test_pet_daily_recovery_preserves_eligibility_and_single_consumption(outcome, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from bot.flow_contracts import FlowStatus
    from bot.semantic_actions import OpenEpicPetSummon, OpenSingleEpicPet, ClosePetSummonResult
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    monkeypatch.setattr("bot.summon_pet_daily_flow.time.sleep", lambda seconds: None)
    before = _snapshot(1, "screen.pets_manage")
    before = replace(before, state=replace(before.state, overlays=("status.pet_summon_daily_active",)))
    clean = _snapshot(2, "screen.pets_manage")
    clean = replace(clean, state=replace(clean.state,
        overlays=() if outcome == "lost_daily" else before.state.overlays))
    ready = _snapshot(3, "screen.pet_summon")
    ready = replace(ready, state=replace(ready.state, overlays=("status.pet_epic_available",)))
    final = _snapshot(5, "screen.pet_summon")
    final = replace(final, state=replace(final.state, overlays=ready.state.overlays))
    waits = [ready, _snapshot(4, "screen.pet_summon_result"), final]
    if outcome == "outcome_timeout":
        waits = [ready, _timeout(ready.sequence, ready)]
    observer = ScriptedObserver(waits, [clean])
    actions, probe = Actions(), ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    flow = SummonPetDailyFlow(observer, actions, SimpleNamespace(record=lambda *a, **k: None),
        SimpleNamespace(run=lambda: pytest.fail("unexpected relief")),
        verified_transition=_transition(observer, actions, probe))
    result = flow.run_with_initial(before)
    if outcome == "lost_daily":
        assert result.status is FlowStatus.FAILED
        assert "guard_missing_after_recovery" in result.error
        assert actions.calls == [DismissPortalNotification()]
    elif outcome == "success":
        assert result.status is FlowStatus.COMPLETED
        assert result.daily_completed and result.summons_completed == 1
        assert actions.calls == [DismissPortalNotification(), SelectPetSummon(),
            OpenEpicPetSummon(), OpenSingleEpicPet(), ClosePetSummonResult()]
    else:
        assert result.status is FlowStatus.FAILED
        assert "state_wait_failed" in result.error
        assert actions.calls == [DismissPortalNotification(), SelectPetSummon(),
            OpenEpicPetSummon(), OpenSingleEpicPet()]


@pytest.mark.parametrize("probe_outcome", [PortalProbeOutcome.ABSENT, PortalProbeOutcome.INCONCLUSIVE])
def test_pet_navigation_timeout_never_repeats_input(probe_outcome):
    from types import SimpleNamespace
    from bot.summon_pet_daily_flow import SummonPetDailyFlow
    before = _snapshot(1, "screen.pets_manage")
    observer = ScriptedObserver([_timeout(1, before)])
    actions, probe = Actions(), ScriptedProbe([probe_outcome])
    flow = SummonPetDailyFlow(observer, actions, SimpleNamespace(record=lambda *a, **k: None),
        SimpleNamespace(run=lambda: None), verified_transition=_transition(observer, actions, probe))
    with pytest.raises(RuntimeWaitTimeout):
        flow._act_and_wait(SelectPetSummon(), lambda s: False, before, flow._is_clean_manage, 6.0, 0.0)
    assert actions.calls == [SelectPetSummon()]


@pytest.mark.parametrize("action_name,base,detail", [
    ("SelectCombineFuse", "screen.combine", "mode.combine_transmute"),
    ("SelectCombineTransmute", "screen.combine", "mode.combine_fuse"),
    ("OpenSocketEquipmentHome", "screen.socket", None),
])
def test_existing_covered_controls_recover_through_shared_transition(action_name, base, detail):
    from dataclasses import replace
    from bot import semantic_actions
    before, clean, after = [_snapshot(i, base) for i in range(1, 4)]
    if detail:
        before = replace(before, state=replace(before.state, overlays=(detail,)))
        clean = replace(clean, state=replace(clean.state, overlays=(detail,)))
    observer, actions = ScriptedObserver([after], [clean]), Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    action = getattr(semantic_actions, action_name)()
    result = _transition(observer, actions, probe).execute(
        "test.covered_control", action, before,
        precondition=lambda s: s.state.base_context == base,
        expected=lambda s: s.state.base_context == base,
        policy=VerifiedTransitionPolicy(),
    )
    assert result.succeeded
    assert actions.calls == [DismissPortalNotification(), action]


def test_cancellation_after_dismiss_observation_prevents_continuation():
    actions = Actions()
    cancelled = False

    class Observer:
        def observe(self):
            nonlocal cancelled
            cancelled = True
            return _snapshot(2, BEFORE)

    recovery = PortalObstructionRecovery(Observer(), actions,
        ScriptedProbe([PortalProbeOutcome.CONFIRMED]), cancel_requested=lambda: cancelled)
    with pytest.raises(RuntimeWaitCancelled):
        recovery.attempt(_snapshot(1, BEFORE), lambda s: False, regions=(INSIDE,))
    assert actions.calls == [DismissPortalNotification()]


def test_individual_flows_contain_no_portal_specific_logic():
    import re

    pattern = re.compile(r"\bheaven\b|\bhell\b|portal", re.IGNORECASE)
    offenders = []
    for path in sorted(Path("bot").glob("*_flow.py")):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)
    for name in (
        "bot/verified_transition.py",
        "bot/preconditions.py",
        "bot/rotation.py",
        "bot/session.py",
    ):
        text = Path(name).read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(name)
    assert offenders == []


def test_dismiss_target_sits_inside_live_measured_x_core():
    from bot.action_executor import (
        DEFAULT_PORTAL_ACTION_TARGETS,
        DEFAULT_ROTATION_ACTION_TARGETS,
    )

    target = DEFAULT_PORTAL_ACTION_TARGETS.dismiss_portal_notification
    # Live-measured bright-red core bbox on 2712x1224, stable over 10 positive
    # frames (Heaven Battle/Guild, Hell Battle, Pets): x 904-960, y 144-198.
    assert 904 / 2712 <= target[0] <= 960 / 2712
    assert 144 / 1224 <= target[1] <= 198 / 1224
    # The previous rim estimate (0.322, 0.129) is outside the core: taps fell
    # through to Quick Menu live.
    assert not (abs(target[0] - 0.322) < 0.005 and abs(target[1] - 0.129) < 0.005)
    # Far from the Quick Menu opener so a dismiss tap can never open it.
    quick_menu = DEFAULT_ROTATION_ACTION_TARGETS.open_quick_menu
    distance = (
        (target[0] - quick_menu[0]) ** 2 + (target[1] - quick_menu[1]) ** 2
    ) ** 0.5
    assert distance > 0.10
    pixel = relative_point_to_pixel(target, 2712, 1224)
    assert 904 <= pixel[0] <= 960
    assert 144 <= pixel[1] <= 198


def test_clean_context_path_reuses_the_shared_recovery_helper():
    runtime_source = Path("bot/productive_runtime.py").read_text(encoding="utf-8")
    assert "def build_obstruction_recovery" in runtime_source
    assert "def _shared_obstruction_recovery" in runtime_source
    assert "_recover_clean_context" in runtime_source
    assert runtime_source.count("_shared_obstruction_recovery()") >= 2
    registry_source = Path("bot/flow_registry.py").read_text(encoding="utf-8")
    assert "build_verified_transition" in registry_source
