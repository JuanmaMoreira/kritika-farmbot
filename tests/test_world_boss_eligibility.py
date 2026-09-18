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


def evaluator(frames, *, cancel_requested=lambda: False):
    observer = Mock()
    observer.observe.return_value = card(2)
    observed_predicates = []

    def wait_until(predicate, **kwargs):
        observed_predicates.append((predicate, kwargs))
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
    check = WorldBossDailyEligibility(observer, cancel_requested=cancel_requested)
    return check, observer, observed_predicates


@pytest.mark.parametrize("active", [True, False])
def test_daily_gate_uses_fresh_stable_badge_and_no_gameplay_inputs(active):
    check, observer, predicates = evaluator([card(i, active) for i in range(3, 7)])
    result = check.evaluate()
    assert result.status is (EligibilityStatus.ELIGIBLE if active else EligibilityStatus.NOT_ELIGIBLE)
    assert predicates[0][1]["after_sequence"] == 2
    assert predicates[0][1]["stable_for"] == .75
    assert [call[0] for call in observer.mock_calls] == ["observe", "wait_until"]


@pytest.mark.parametrize("frames", [
    [card(i, status=ResolutionStatus.UNKNOWN) for i in range(3, 8)],
    [card(i, status=ResolutionStatus.AMBIGUOUS) for i in range(3, 8)],
    [card(i, active=bool(i % 2)) for i in range(3, 8)],
    [card(2)] * 4,
])
def test_unknown_ambiguous_flicker_or_stale_never_skips_or_returns(frames):
    check, observer, _ = evaluator(frames)
    result = check.evaluate()
    assert result.status is EligibilityStatus.UNKNOWN
    assert result.failure.type == "eligibility_unknown"


def test_transient_absence_followed_by_stable_active_is_eligible():
    check, _, _ = evaluator([card(3), card(4), card(5, True), card(6, True), card(7, True)])
    assert check.evaluate().status is EligibilityStatus.ELIGIBLE


def test_capture_failure_keeps_technical_cause_and_no_cleanup_input():
    check, observer, _ = evaluator([OSError("decoder failed")])
    result = check.evaluate()
    assert result.status is EligibilityStatus.FAILED
    assert result.failure.exception_type == "OSError"


def test_cancelled_wait_does_not_return_or_report_not_eligible():
    check, observer, _ = evaluator([RuntimeWaitCancelled()])
    assert check.evaluate().status is EligibilityStatus.CANCELLED


def test_cancel_before_evaluation_does_not_navigate():
    check, observer, _ = evaluator([], cancel_requested=lambda: True)
    assert check.evaluate().status is EligibilityStatus.CANCELLED
    observer.observe.assert_not_called()
    observer.wait_until.assert_not_called()


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


def test_scoped_daily_decision_matches_global_on_curated_hub_and_foreign_frames():
    from pathlib import Path
    import cv2
    from bot.capture import FrameSnapshot
    from bot.catalog import build_default_resolver
    from bot.perception import (
        WORLD_BOSS_ELIGIBILITY_SCOPE, build_default_perception, select_detectors,
    )
    from tools.semantic_slice_evaluation import load_manifest

    root = Path(__file__).resolve().parents[1]
    global_engine = build_default_perception(root)
    scoped_engine = select_detectors(global_engine, WORLD_BOSS_ELIGIBILITY_SCOPE)
    resolver = build_default_resolver()
    assert len(global_engine.detectors) == 97
    assert len(scoped_engine.detectors) == 5

    daily = [entry for entry in load_manifest(root / "datasets/daily_activity_semantic_manifest.json")
             if "/world-boss/" in entry.path]
    returns = load_manifest(root / "datasets/world_boss_eligibility_return_manifest.json")
    selector = [entry for entry in load_manifest(root / "datasets/world_boss_semantic_manifest.json")
                if "/select_boss/" in entry.path]
    assert (len(daily), len(returns), len(selector)) == (6, 9, 4)
    for i, entry in enumerate((*daily, *returns, *selector), 1):
        frame = cv2.imread(str(root / entry.path))
        assert frame is not None, entry.path
        snapshot = FrameSnapshot(frame, float(i), i)
        global_state = resolver.resolve(global_engine.analyze(snapshot))
        scoped_state = resolver.resolve(scoped_engine.analyze(snapshot))
        global_decision = world_boss_daily_status(SimpleNamespace(state=global_state))
        scoped_decision = world_boss_daily_status(SimpleNamespace(state=scoped_state))
        assert scoped_decision is global_decision, entry.path
        if entry in daily:
            assert scoped_state.status is ResolutionStatus.RESOLVED, entry.path
            assert scoped_state.base_context == SCREEN_BATTLE_MODE_SELECT, entry.path
            assert set(scoped_state.overlays) == set(entry.overlays), entry.path
        elif entry in selector:
            assert scoped_decision is EligibilityStatus.UNKNOWN, entry.path
