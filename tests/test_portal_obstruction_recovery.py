"""Regression for the transversal portal-notification recovery seam."""

from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
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
    RuntimeWaitTimeout,
)
from bot.semantic_actions import DismissPortalNotification, OpenQuickMenu
from bot.state import ResolutionStatus, ResolvedState
from bot.verified_transition import (
    VerifiedTransition,
    VerifiedTransitionOutcome,
    VerifiedTransitionPolicy,
)

BEFORE = "screen.before"
EXPECTED = "screen.expected"
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
    ):
        item = self.waits.pop(0)
        if isinstance(item, BaseException):
            raise item
        assert item.sequence > after_sequence
        return item

    def observe(self):
        return self.observes.pop(0)


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, action, geometry):
        self.calls.append(action)
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


@pytest.mark.parametrize("failed_source", (False, True))
def test_settle_stalled_or_failing_source_never_authorizes_second_dismiss(failed_source):
    blocked = _snapshot(1, BEFORE)
    fresh = _snapshot(2, BEFORE)

    class StalledObserver:
        calls = 0

        def observe(self):
            self.calls += 1
            if failed_source and self.calls > 1:
                raise RuntimeError("capture failed during fade")
            return fresh

    actions = Actions()
    clock = FakeClock()
    recovery = PortalObstructionRecovery(
        StalledObserver(), actions,
        PortalNotificationProbe(scorer=lambda frame: 1.0),
        policy=ObstructionRecoveryPolicy(settle_timeout=1.0),
        clock=clock.clock, sleeper=clock.sleeper,
    )
    recovery.attempt(blocked, lambda item: False)
    assert len(_dismiss_calls(actions)) == 1


def test_cancellation_during_fade_propagates_without_a_second_tap():
    observer = ScriptedObserver([], observes=[_snapshot(2, BEFORE)])
    actions = Actions()
    clock = FakeClock()
    recovery = PortalObstructionRecovery(
        observer, actions, PortalNotificationProbe(scorer=lambda frame: 1.0),
        clock=clock.clock, sleeper=clock.sleeper,
        cancel_requested=lambda: clock.now >= 0.5,
    )
    transition = VerifiedTransition(observer, actions, obstruction_recovery=recovery)
    with pytest.raises(RuntimeWaitCancelled):
        transition.execute(
            "test.cancel_recovery", OpenQuickMenu(), _snapshot(1, BEFORE),
            precondition=lambda item: False, expected=lambda item: False,
            policy=VerifiedTransitionPolicy(),
        )
    assert len(_dismiss_calls(actions)) == 1
    assert _productive_calls(actions) == []


def test_blocked_postcondition_with_confirmed_portal_recovers_without_productive_retry():
    before = _snapshot(1, BEFORE)
    blocked_after_normal = _snapshot(2, BEFORE)
    blocked_after_grace = _snapshot(3, BEFORE)
    blocked_fresh = _snapshot(
        4, BEFORE, status=ResolutionStatus.UNKNOWN
    )
    cleared = _snapshot(5, EXPECTED)
    observer = ScriptedObserver(
        [_timeout(1, blocked_after_normal), _timeout(2, blocked_after_grace)],
        observes=[blocked_fresh, cleared],
    )
    actions = Actions()
    probe = ScriptedProbe(
        [PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT]
    )
    transition = _transition(observer, actions, probe)

    result = transition.execute(
        "test.portal_recovery",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.succeeded
    assert result.outcome is (
        VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY
    )
    assert result.attempt_count == 1
    assert result.final_snapshot.state.base_context == EXPECTED
    assert len(_productive_calls(actions)) == 1
    assert len(_dismiss_calls(actions)) == 1


def test_absent_portal_keeps_existing_behavior_without_extra_taps():
    before = _snapshot(1, BEFORE)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=[_snapshot(4, BEFORE)],
    )
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.ABSENT])
    transition = _transition(observer, actions, probe)

    result = transition.execute(
        "test.portal_absent",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert len(_productive_calls(actions)) == 1
    assert _dismiss_calls(actions) == []
    assert probe.calls == 1


def test_inconclusive_probe_never_authorizes_dismiss_tap():
    assert (
        PortalNotificationProbe(scorer=lambda crop: 0.7).probe(
            np.zeros((100, 200, 3), dtype=np.uint8)
        )
        is PortalProbeOutcome.INCONCLUSIVE
    )
    before = _snapshot(1, BEFORE)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=[_snapshot(4, BEFORE)],
    )
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.INCONCLUSIVE])
    transition = _transition(observer, actions, probe)

    result = transition.execute(
        "test.portal_inconclusive",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert _dismiss_calls(actions) == []
    assert len(_productive_calls(actions)) == 1


def test_recovery_clearing_without_expected_state_does_not_repeat_productive_action():
    before = _snapshot(1, BEFORE)
    cleared_still_before = _snapshot(5, BEFORE)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=[_snapshot(4, BEFORE), cleared_still_before],
    )
    actions = Actions()
    probe = ScriptedProbe(
        [PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT]
    )
    transition = _transition(observer, actions, probe)

    result = transition.execute(
        "test.portal_cleared_no_state",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert len(_productive_calls(actions)) == 1
    assert len(_dismiss_calls(actions)) == 1
    assert result.final_snapshot.sequence == 5


def test_dismissal_is_bounded_when_notification_persists():
    before = _snapshot(1, BEFORE)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=[_snapshot(sequence, BEFORE) for sequence in range(4, 27)],
    )
    actions = Actions()
    probe = ScriptedProbe(
        [PortalProbeOutcome.CONFIRMED] * 23
    )
    transition = _transition(
        observer, actions, probe, policy=ObstructionRecoveryPolicy(max_dismiss_attempts=2)
    )

    result = transition.execute(
        "test.portal_bounded",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert len(_dismiss_calls(actions)) == 2
    assert len(_productive_calls(actions)) == 1


def test_blocked_precondition_recovers_before_first_productive_input():
    blocked_before = _snapshot(
        1, BEFORE, status=ResolutionStatus.UNKNOWN
    )
    cleaned = _snapshot(2, BEFORE)
    arrived = _snapshot(3, EXPECTED)
    observer = ScriptedObserver([arrived], observes=[cleaned])
    actions = Actions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.ABSENT])
    transition = _transition(observer, actions, probe)

    result = transition.execute(
        "test.precondition_recovery",
        OpenQuickMenu(),
        blocked_before,
        expected=lambda item: item.state.base_context == EXPECTED,
        precondition=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(normal_timeout=6.0, grace_timeout=2.0),
    )

    assert result.outcome is VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT
    assert len(_productive_calls(actions)) == 1
    assert len(_dismiss_calls(actions)) == 1


def _policy(**overrides):
    values = {"max_dismiss_attempts": 2, "settle_timeout": 5.0}
    values.update(overrides)
    return ObstructionRecoveryPolicy(**values)


def test_fade_staying_confirmed_does_not_trigger_early_second_tap():
    before = _snapshot(1, BEFORE)
    blocked = _snapshot(4, BEFORE, status=ResolutionStatus.UNKNOWN)
    fade_one = _snapshot(5, BEFORE, status=ResolutionStatus.UNKNOWN)
    fade_two = _snapshot(6, BEFORE, status=ResolutionStatus.UNKNOWN)
    cleared = _snapshot(7, EXPECTED)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=[blocked, fade_one, fade_two, cleared],
    )
    actions = Actions()
    probe = ScriptedProbe(
        [
            PortalProbeOutcome.CONFIRMED,
            PortalProbeOutcome.CONFIRMED,
            PortalProbeOutcome.CONFIRMED,
            PortalProbeOutcome.ABSENT,
        ]
    )
    clock = FakeClock()
    transition = _transition(observer, actions, probe, clock=clock)

    result = transition.execute(
        "test.portal_settle_fade",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is (
        VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY
    )
    assert result.final_snapshot.sequence == 7
    assert len(_dismiss_calls(actions)) == 1
    assert len(_productive_calls(actions)) == 1
    assert clock.sleeps


def test_inconclusive_during_settle_authorizes_no_further_tap():
    before = _snapshot(1, BEFORE)
    blocked = _snapshot(4, BEFORE, status=ResolutionStatus.UNKNOWN)
    fading = _snapshot(5, BEFORE)
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=[blocked, fading],
    )
    actions = Actions()
    probe = ScriptedProbe(
        [PortalProbeOutcome.CONFIRMED, PortalProbeOutcome.INCONCLUSIVE]
    )
    transition = _transition(observer, actions, probe, clock=FakeClock())

    result = transition.execute(
        "test.portal_settle_inconclusive",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert len(_dismiss_calls(actions)) == 1
    assert len(_productive_calls(actions)) == 1


def test_confirmed_through_whole_settle_allows_exactly_one_second_tap():
    before = _snapshot(1, BEFORE)
    frames = [_snapshot(4, BEFORE, status=ResolutionStatus.UNKNOWN)]
    frames += [_snapshot(sequence, BEFORE) for sequence in range(5, 27)]
    observer = ScriptedObserver(
        [_timeout(1, _snapshot(2, BEFORE)), _timeout(2, _snapshot(3, BEFORE))],
        observes=list(frames),
    )
    actions = Actions()
    probe = ScriptedProbe(
        [PortalProbeOutcome.CONFIRMED] * (1 + 11 + 11)
    )
    transition = _transition(observer, actions, probe, clock=FakeClock())

    result = transition.execute(
        "test.portal_settle_second_tap",
        OpenQuickMenu(),
        before,
        expected=lambda item: item.state.base_context == EXPECTED,
        retryable_from=lambda item: item.state.base_context == BEFORE,
        policy=VerifiedTransitionPolicy(
            normal_timeout=6.0, grace_timeout=2.0, max_attempts=1
        ),
    )

    assert result.outcome is VerifiedTransitionOutcome.ATTEMPTS_EXHAUSTED
    assert len(_dismiss_calls(actions)) == 2
    assert len(_productive_calls(actions)) == 1


def test_second_tap_never_derives_a_third():
    blocked = _snapshot(4, BEFORE, status=ResolutionStatus.UNKNOWN)
    frames = [_snapshot(sequence, BEFORE) for sequence in range(5, 12)]
    observer = ScriptedObserver([], observes=list(frames))

    class CountingActions:
        def __init__(self):
            self.calls = []

        def execute(self, action, geometry):
            self.calls.append(action)

    actions = CountingActions()
    probe = ScriptedProbe([PortalProbeOutcome.CONFIRMED] * 12)
    clock = FakeClock()
    recovery = PortalObstructionRecovery(
        observer,
        actions,
        probe,
        policy=_policy(settle_timeout=1.0, settle_poll_interval=0.5),
        clock=clock.clock,
        sleeper=clock.sleeper,
    )

    fresh = recovery.attempt(blocked, lambda item: False)

    assert fresh is not None
    assert len(actions.calls) == 2
    assert all(
        isinstance(call, DismissPortalNotification) for call in actions.calls
    )


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
