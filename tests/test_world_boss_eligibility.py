from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot.catalog import (
    SCREEN_BATTLE_MODE_SELECT, SCREEN_LOBBY, SCREEN_WORLD_BOSS,
    STATUS_WORLD_BOSS_DAILY_ACTIVE,
)
from bot.eligibility import EligibilityStatus
from bot.failure_cause import FailureCause
from bot.runtime_observer import RuntimeWaitCancelled, RuntimeWaitTimeout
from bot.state import ResolutionStatus
from bot.world_boss_eligibility import WorldBossDailyEligibility, world_boss_daily_status
from test_world_boss_flow import snapshot


def card(seq, active=False, **kwargs):
    base = (SCREEN_BATTLE_MODE_SELECT if kwargs.get("status", ResolutionStatus.RESOLVED)
            is ResolutionStatus.RESOLVED else None)
    return snapshot(seq, base=base,
                    overlays=(STATUS_WORLD_BOSS_DAILY_ACTIVE,) if active else (), **kwargs)


@pytest.mark.parametrize("active", [True, False])
def test_only_resolved_unobstructed_world_boss_card_can_decide(active):
    expected = EligibilityStatus.ELIGIBLE if active else EligibilityStatus.NOT_ELIGIBLE
    assert world_boss_daily_status(card(1, active)) is expected
    for status in (ResolutionStatus.UNKNOWN, ResolutionStatus.AMBIGUOUS):
        assert world_boss_daily_status(card(1, active, status=status)) is EligibilityStatus.UNKNOWN
    for base in (SCREEN_LOBBY, SCREEN_WORLD_BOSS):
        assert world_boss_daily_status(snapshot(1, base=base)) is EligibilityStatus.UNKNOWN
    assert world_boss_daily_status(snapshot(
        1, base=SCREEN_BATTLE_MODE_SELECT, overlays=("menu.quick",))) is EligibilityStatus.UNKNOWN


def evaluator(frames, *, opening=None, returned=None, cancel_requested=lambda: False):
    observer = Mock()
    observed_predicates = []

    def wait_until(predicate, **kwargs):
        observed_predicates.append((predicate, kwargs))
        if len(observed_predicates) == 1:
            value = snapshot(1, base=SCREEN_LOBBY)
            assert predicate(value)
            return value
        # Test adapter requires consecutive fresh matches and the requested
        # stability span, including resets on badge changes or UNKNOWN.
        since = None
        for value in frames:
            if isinstance(value, Exception):
                raise value
            if value.sequence <= kwargs["after_sequence"]:
                continue
            if predicate(value):
                since = value.timestamp if since is None else since
                if value.timestamp - since >= kwargs["stable_for"]:
                    return value
            else:
                since = None
        raise RuntimeWaitTimeout(after_sequence=2, timeout=6, last_snapshot=frames[-1])

    observer.wait_until.side_effect = wait_until
    transition = Mock()
    transition.execute.return_value = opening or SimpleNamespace(
        succeeded=True, final_snapshot=card(2))
    close = Mock(return_value=returned or SimpleNamespace(
        succeeded=True, final_snapshot=snapshot(20, base=SCREEN_LOBBY)))
    check = WorldBossDailyEligibility(observer, transition, close,
                                     cancel_requested=cancel_requested)
    return check, transition, close, observed_predicates


@pytest.mark.parametrize("active", [True, False])
def test_daily_gate_uses_fresh_stable_badge_and_no_gameplay_inputs(active):
    check, transition, close, predicates = evaluator([card(i, active) for i in range(3, 7)])
    result = check.evaluate()
    assert result.status is (EligibilityStatus.ELIGIBLE if active else EligibilityStatus.NOT_ELIGIBLE)
    assert transition.execute.call_count == close.call_count == 1
    action = transition.execute.call_args.args[1]
    assert type(action).__name__ == "OpenBattleModeSelect"
    assert predicates[1][1]["after_sequence"] == 2
    assert predicates[1][1]["stable_for"] == .75
    guards = transition.execute.call_args.kwargs
    assert guards["precondition"](snapshot(1, base=SCREEN_LOBBY))
    assert not guards["precondition"](snapshot(1))
    assert not guards["retryable_from"](snapshot(1))


@pytest.mark.parametrize("frames", [
    [card(i, status=ResolutionStatus.UNKNOWN) for i in range(3, 8)],
    [card(i, status=ResolutionStatus.AMBIGUOUS) for i in range(3, 8)],
    [card(i, active=bool(i % 2)) for i in range(3, 8)],
    [card(2)] * 4,
])
def test_unknown_ambiguous_flicker_or_stale_never_skips_or_returns(frames):
    check, _, close, _ = evaluator(frames)
    result = check.evaluate()
    assert result.status is EligibilityStatus.UNKNOWN
    assert result.failure.type == "eligibility_unknown"
    close.assert_not_called()


def test_transient_absence_followed_by_stable_active_is_eligible():
    check, _, _, _ = evaluator([card(3), card(4), card(5, True), card(6, True), card(7, True)])
    assert check.evaluate().status is EligibilityStatus.ELIGIBLE


def test_capture_failure_keeps_technical_cause_and_no_cleanup_input():
    check, _, close, _ = evaluator([OSError("decoder failed")])
    result = check.evaluate()
    assert result.status is EligibilityStatus.FAILED
    assert result.failure.exception_type == "OSError"
    close.assert_not_called()


@pytest.mark.parametrize("stage", ["open", "return"])
def test_transition_failure_preserves_cause(stage):
    failure = FailureCause("transition", "failed", evidence_ref="file:///evidence")
    failed = SimpleNamespace(succeeded=False, failure=failure, error="failed")
    check, _, close, _ = evaluator([card(i) for i in range(3, 7)], **{
        "opening" if stage == "open" else "returned": failed})
    result = check.evaluate()
    assert result.status is EligibilityStatus.FAILED
    assert result.failure is failure
    if stage == "open":
        close.assert_not_called()


def test_cancelled_wait_does_not_return_or_report_not_eligible():
    check, _, close, _ = evaluator([RuntimeWaitCancelled()])
    assert check.evaluate().status is EligibilityStatus.CANCELLED
    close.assert_not_called()


def test_cancel_before_evaluation_does_not_navigate():
    check, transition, close, _ = evaluator([], cancel_requested=lambda: True)
    assert check.evaluate().status is EligibilityStatus.CANCELLED
    transition.execute.assert_not_called()
    close.assert_not_called()


def test_bad_return_is_technical_even_when_badge_is_absent():
    check, _, _, _ = evaluator([card(i) for i in range(3, 7)], returned=SimpleNamespace(
        succeeded=True, final_snapshot=card(20)))
    assert check.evaluate().status is EligibilityStatus.FAILED


def test_acquired_return_frames_are_recognized_by_unchanged_production_detectors():
    from pathlib import Path
    import cv2
    from bot.capture import FrameSnapshot
    from bot.catalog import build_default_resolver
    from bot.perception import build_default_perception
    from tools.semantic_slice_evaluation import load_manifest
    root = Path(__file__).resolve().parents[1]
    entries = load_manifest(root / "datasets/world_boss_eligibility_return_manifest.json")
    engine, resolver = build_default_perception(root), build_default_resolver()
    assert len(entries) == 9
    for i, entry in enumerate(entries, 1):
        frame = cv2.imread(str(root / entry.path))
        assert frame is not None
        state = resolver.resolve(engine.analyze(FrameSnapshot(frame, float(i), i)))
        assert state.base_context == (None if entry.base_context == "unknown" else entry.base_context)
        assert state.status is (ResolutionStatus.UNKNOWN if entry.base_context == "unknown"
                                else ResolutionStatus.RESOLVED)
        assert set(state.overlays) == set(entry.overlays)
