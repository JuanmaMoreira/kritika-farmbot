"""Treasure autonomous runtime: entry, facts, open, exit, separation."""

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import (
    DEFAULT_TREASURE_ACTION_TARGETS,
    ActionExecutor,
    FrameGeometry,
)
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.flow_contracts import FlowStatus
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.semantic_actions import (
    ConfirmRepeatGoldOpen,
    ConfirmSingleGoldOpen,
    DismissTreasureResult,
    ExitTreasure,
    OpenTreasure,
    SelectGoldChest,
)
from bot.state import ResolutionStatus, ResolvedState
from bot.treasure_center_semantics import (
    INDICATOR_TREASURE_GOLD_KEY_REPEAT,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    INDICATOR_TREASURE_KARAT_BASE,
    INDICATOR_TREASURE_RESULT,
    INDICATOR_TREASURE_SELECTOR_POPUP,
    LANDMARK_TREASURE_TITLE,
    SCREEN_TREASURE,
)
from bot.treasure_facts import fact_for_repeat, fact_for_single
from bot.treasure_keys import (
    GoldKeyQuantity,
    GoldKeyQuantityMode,
    TreasureOutcome,
)
from bot.treasure_profile import TREASURE_PROFILE, open_targets
from bot.treasure_runtime import TreasureRuntime, is_clean_lobby
from bot.verified_transition import VerifiedTransitionOutcome


GEOMETRY = FrameGeometry(width=2712, height=1220)


def _observation(name, confidence=0.95):
    return Observation(name, confidence, ObservationSource.LOCAL_CV)


def _snapshot(sequence, *, base, observations=(), overlays=(), status=None,
              candidates=(), timestamp=None):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    if timestamp is None:
        timestamp = float(sequence)
    image = np.zeros((1220, 2712, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, timestamp, sequence),
        ObservationBatch(sequence, timestamp, tuple(observations)),
        ResolvedState(
            status,
            sequence,
            timestamp,
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(candidates),
        ),
        RuntimeFacts(),
        GEOMETRY,
    )


def _lobby(sequence=1):
    return _snapshot(
        sequence,
        base=SCREEN_LOBBY,
        observations=[_observation("landmark.lobby_trading_center_label")],
    )


def _treasure_grid(sequence=2):
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
        ],
    )


def _treasure_popup(sequence=3, timestamp=None):
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
            _observation(INDICATOR_TREASURE_GOLD_KEY_REPEAT),
        ],
        timestamp=timestamp,
    )


def _treasure_result(sequence=4, timestamp=None):
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_RESULT),
            _observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
            _observation(INDICATOR_TREASURE_GOLD_KEY_REPEAT),
        ],
        timestamp=timestamp,
    )


class _Timeout(Exception):
    pass


class FakeObserver:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)

    def observe(self):
        if not self._snapshots:
            raise _Timeout("no more snapshots")
        return self._snapshots.pop(0)

    def wait_until(
        self,
        condition,
        *,
        after_sequence=0,
        timeout=6.0,
        stable_for=0.0,
        abort_if=None,
        cancel_requested=None,
    ):
        for snapshot in list(self._snapshots):
            if snapshot.sequence <= after_sequence:
                continue
            if abort_if is not None and abort_if(snapshot):
                raise _Timeout("aborted")
            if condition(snapshot):
                self._snapshots.remove(snapshot)
                return snapshot
        raise _Timeout("expected_state_not_reached")


class FakeAdb:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((int(x), int(y)))


def _transition_result(name, outcome, final, error=None):
    return SimpleNamespace(
        name=name,
        outcome=outcome,
        attempt_count=1,
        grace_wait_count=0,
        final_snapshot=final,
        error=error,
        failure=None,
        action_source_snapshot=None,
        recovery_after_action=False,
        succeeded=outcome
        in {
            VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT,
            VerifiedTransitionOutcome.SUCCESS_AFTER_GRACE,
            VerifiedTransitionOutcome.SUCCESS_AFTER_RETRY,
            VerifiedTransitionOutcome.SUCCESS_AFTER_OBSTRUCTION_RECOVERY,
        },
    )


class FakeTransition:
    def __init__(self, adb, posts):
        self.actions = SimpleNamespace(adb=adb)
        self._posts = list(posts)
        self.calls = []

    def execute(
        self,
        name,
        action,
        before,
        *,
        expected,
        precondition=None,
        retryable_from=None,
        abort_if=None,
        stable_for=0.0,
        policy=None,
        on_recovery=None,
    ):
        self.calls.append((name, action))
        if precondition is not None and not precondition(before):
            return _transition_result(
                name,
                VerifiedTransitionOutcome.PRECONDITION_REJECTED,
                before,
                "precondition_rejected",
            )
        geometry = before.geometry
        pixel = (
            int(action_point(action)[0] * geometry.width),
            int(action_point(action)[1] * geometry.height),
        )
        self.actions.adb.tap(*pixel)
        post = self._posts.pop(0) if self._posts else before
        if abort_if is not None and abort_if(post):
            return _transition_result(
                name,
                VerifiedTransitionOutcome.UNEXPECTED_STATE,
                post,
                "unexpected_state",
            )
        if expected(post):
            return _transition_result(
                name, VerifiedTransitionOutcome.SUCCESS_FIRST_ATTEMPT, post
            )
        return _transition_result(
            name,
            VerifiedTransitionOutcome.TIMEOUT,
            post,
            "expected_state_not_reached",
        )


def action_point(action):
    targets = DEFAULT_TREASURE_ACTION_TARGETS
    if isinstance(action, OpenTreasure):
        return targets.open_treasure
    if isinstance(action, SelectGoldChest):
        return targets.select_gold_chest
    if isinstance(action, ConfirmSingleGoldOpen):
        return targets.confirm_single_gold_open
    if isinstance(action, ConfirmRepeatGoldOpen):
        return targets.confirm_repeat_gold_open
    if isinstance(action, DismissTreasureResult):
        return targets.dismiss_treasure_result
    if isinstance(action, ExitTreasure):
        return targets.exit_treasure
    raise ValueError("not a treasure action")


def _runtime(observer_snaps, transition_posts, cancel=False):
    adb = FakeAdb()
    runtime = TreasureRuntime(
        FakeObserver(observer_snaps),
        FakeTransition(adb, transition_posts),
        cancel_requested=(lambda: True) if cancel else (lambda: False),
    )
    return runtime, adb


def _open_once():
    return GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE)


# Entry.


def test_entry_clean_lobby_taps_entry_point_and_verifies_treasure():
    runtime, adb = _runtime([_lobby(1)], [_treasure_grid(2)])
    result = runtime.enter_treasure_from_lobby()
    assert result.status is FlowStatus.COMPLETED
    assert adb.taps == [
        (
            int(TREASURE_PROFILE.entry_point[0] * 2712),
            int(TREASURE_PROFILE.entry_point[1] * 1220),
        )
    ]
    assert len(runtime.transition.calls) == 1
    assert isinstance(runtime.transition.calls[0][1], OpenTreasure)


def test_entry_wrong_source_does_zero_input():
    foreign = _snapshot(
        1,
        base="screen.trading",
        observations=[_observation("landmark.trading_center_title")],
    )
    runtime, adb = _runtime([foreign], [])
    result = runtime.enter_treasure_from_lobby()
    assert result.status is FlowStatus.FAILED
    assert adb.taps == []
    assert runtime.transition.calls == []


def test_entry_failed_arrival_reports_failure_without_further_input():
    runtime, adb = _runtime([_lobby(1)], [_lobby(2)])
    result = runtime.enter_treasure_from_lobby()
    assert result.status is FlowStatus.FAILED
    assert len(adb.taps) == 1


def test_entry_cancel_before_input_does_zero_taps():
    runtime, adb = _runtime([_lobby(1)], [_treasure_grid(2)], cancel=True)
    result = runtime.enter_treasure_from_lobby()
    assert result.status is FlowStatus.CANCELLED
    assert adb.taps == []


# Readiness / currency.


def test_execute_requires_gold_readiness_without_input():
    bare = _snapshot(2, base=SCREEN_TREASURE, observations=[])
    runtime, adb = _runtime([bare], [])
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.FAILED
    assert adb.taps == []


def test_execute_contradictory_gold_and_karat_does_zero_input():
    both = _snapshot(
        2,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
            _observation(INDICATOR_TREASURE_KARAT_BASE),
        ],
    )
    runtime, adb = _runtime([both], [])
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.FAILED
    assert adb.taps == []


def test_execute_karat_first_fact_stops_before_confirm():
    grid = _treasure_grid(2)
    popup_ready = _treasure_popup(3)
    karat_popup = _snapshot(
        4,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_KARAT_BASE),
        ],
    )
    karat_after = _snapshot(
        5,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_KARAT_BASE),
        ],
    )
    runtime, adb = _runtime(
        [grid, karat_popup, karat_after], [popup_ready]
    )
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.PREMIUM_CURRENCY_BOUNDARY
    assert result.opened == 0
    assert len(adb.taps) == 1  # selector tap only; open never tapped


# Open semantics.


def _open_session_snaps():
    # Reads sample strictly newer frames than the authorizing snapshots
    # (same decode counter is fine: freshness is capture time).
    return [
        _treasure_grid(2),
        _treasure_popup(3, timestamp=3.4),
        _treasure_result(4, timestamp=3.8),
    ]


def test_execute_single_open_taps_single_point_once_with_success():
    runtime, adb = _runtime(
        _open_session_snaps(), [_treasure_popup(3)]
    )
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert result.inputs == ("tap_open_single",)
    single_pixel = (
        int(TREASURE_PROFILE.single_point[0] * 2712),
        int(TREASURE_PROFILE.single_point[1] * 1220),
    )
    assert adb.taps[-1] == single_pixel
    assert adb.taps.count(single_pixel) == 1


def test_execute_smoke_b_sequence_gap_with_fresh_frame_authorizes():
    # HIL 2026-09-18 Smoke B: the decode counter advanced ~60 frames
    # during analyze latency while the popup frame stayed 0.3s fresh.
    # Freshness is capture time behind the selector barrier, never the
    # counter gap (old contract failed this closed with zero spend).
    runtime, adb = _runtime(
        [
            _treasure_grid(2),
            _treasure_popup(70, timestamp=10.3),
            _treasure_result(71, timestamp=10.6),
        ],
        [_treasure_popup(10, timestamp=10.0)],
    )
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert result.inputs == ("tap_open_single",)
    assert result.before is not None
    assert result.before.sequence == 70
    assert result.before.observed_at == 10.3


def test_execute_selector_failure_does_no_capability_taps():
    runtime, adb = _runtime([_treasure_grid(2)], [_treasure_grid(3)])
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.FAILED
    assert "selector_failed" in (result.reason or "")
    assert len(adb.taps) == 1


def test_execute_unchanged_postcondition_is_no_effect_without_retry():
    reads = [
        _treasure_grid(2),
        _treasure_popup(3, timestamp=3.4),
        _treasure_popup(4, timestamp=3.8),
    ]
    runtime, adb = _runtime(reads, [_treasure_popup(3)])
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.opened == 0
    assert len([tap for tap in adb.taps]) == 2


def test_execute_stale_postcondition_is_not_success():
    reads = [
        _treasure_grid(2),
        _treasure_popup(3, timestamp=3.4),
        _treasure_popup(3, timestamp=3.6),
    ]
    runtime, adb = _runtime(reads, [_treasure_popup(3)])
    result = runtime.execute_gold_key_open(_open_once())
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == "stale_after_fact"


# Lifecycle is covered by the capability contract: departure plus a
# strictly fresher result proves the open; tested above through the
# runtime read_state/sequence plumbing.


# Exit.


def test_leave_result_dismisses_then_verifies_clean_lobby():
    grid = _snapshot(
        3,
        base=SCREEN_TREASURE,
        observations=[_observation(LANDMARK_TREASURE_TITLE)],
    )
    runtime, adb = _runtime(
        [_treasure_result(2)], [grid, _lobby(4)]
    )
    result = runtime.leave_treasure_to_lobby()
    assert result.status is FlowStatus.COMPLETED
    assert len(adb.taps) == 2
    assert isinstance(runtime.transition.calls[0][1], DismissTreasureResult)
    assert isinstance(runtime.transition.calls[1][1], ExitTreasure)


def test_leave_without_result_taps_back_only():
    runtime, adb = _runtime([_treasure_grid(2)], [_lobby(3)])
    result = runtime.leave_treasure_to_lobby()
    assert result.status is FlowStatus.COMPLETED
    assert len(adb.taps) == 1
    assert isinstance(runtime.transition.calls[0][1], ExitTreasure)


def test_leave_requires_strong_lobby_postcondition():
    still_there = _snapshot(
        3,
        base=SCREEN_TREASURE,
        observations=[_observation(LANDMARK_TREASURE_TITLE)],
    )
    runtime, adb = _runtime([_treasure_grid(2)], [still_there])
    result = runtime.leave_treasure_to_lobby()
    assert result.status is FlowStatus.FAILED
    assert len(adb.taps) == 1


def test_leave_wrong_source_does_zero_input():
    runtime, adb = _runtime([_lobby(1)], [])
    result = runtime.leave_treasure_to_lobby()
    assert result.status is FlowStatus.FAILED
    assert adb.taps == []


# Facts.


def test_fact_single_is_gold_one_selector():
    fact = fact_for_single(_treasure_popup(3), sequence=3)
    assert fact is not None
    assert fact.currency == "gold_key"
    assert fact.amount_offered == 1
    assert fact.overlay == "selector"
    assert fact.count is None
    assert fact.sequence == 3


def test_fact_repeat_is_gold_ten():
    fact = fact_for_repeat(_treasure_popup(3), sequence=3)
    assert fact is not None
    assert fact.currency == "gold_key"
    assert fact.amount_offered == 10


def test_fact_result_overlay_from_result_state():
    fact = fact_for_single(_treasure_result(4), sequence=4)
    assert fact is not None
    assert fact.overlay == "result"
    assert fact.currency == "gold_key"


def test_fact_karat_is_boundary_shaped():
    karat = _snapshot(
        3,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_KARAT_BASE),
        ],
    )
    fact = fact_for_single(karat, sequence=3)
    assert fact is not None
    assert fact.currency == "karat"
    assert fact.amount_offered is None


def test_fact_unknown_when_no_currency_demonstrated():
    bare = _snapshot(
        2,
        base=SCREEN_TREASURE,
        observations=[_observation(LANDMARK_TREASURE_TITLE)],
    )
    fact = fact_for_single(bare, sequence=2)
    assert fact is not None
    assert fact.currency == "unknown"


def test_fact_none_on_foreign_or_unresolved():
    foreign = _snapshot(
        2,
        base=SCREEN_LOBBY,
        observations=[_observation("landmark.lobby_trading_center_label")],
    )
    assert fact_for_single(foreign, sequence=2) is None
    ambiguous = _snapshot(
        2,
        base=None,
        status=ResolutionStatus.AMBIGUOUS,
        candidates=(SCREEN_LOBBY, SCREEN_TREASURE),
        observations=[_observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR)],
    )
    assert fact_for_single(ambiguous, sequence=2) is None
    unknown = _snapshot(2, base=None, status=ResolutionStatus.UNKNOWN)
    assert fact_for_repeat(unknown, sequence=2) is None


# Profile / targets / wiring.


def test_profile_points_are_hil_single_and_inside_bboxes():
    profile = TREASURE_PROFILE
    assert profile.single_point == (0.618, 0.548)
    assert profile.single_exercised is True
    assert profile.repeat_exercised is False
    for point_name, bbox_name in (
        ("entry_point", "entry_bbox"),
        ("gold_chest_point", "gold_chest_bbox"),
        ("single_point", "single_bbox"),
        ("repeat_point", "repeat_bbox"),
        ("back_point", "back_bbox"),
    ):
        x, y = getattr(profile, point_name)
        x0, y0, x1, y1 = getattr(profile, bbox_name)
        assert x0 < x < x1 and y0 < y < y1
    assert profile.single_bbox[2] <= profile.repeat_bbox[0]


def test_executor_defaults_mirror_profile():
    targets = DEFAULT_TREASURE_ACTION_TARGETS
    assert targets.open_treasure == TREASURE_PROFILE.entry_point
    assert targets.select_gold_chest == TREASURE_PROFILE.gold_chest_point
    assert targets.confirm_single_gold_open == TREASURE_PROFILE.single_point
    assert targets.confirm_repeat_gold_open == TREASURE_PROFILE.repeat_point
    assert targets.dismiss_treasure_result == TREASURE_PROFILE.dismiss_point
    assert targets.exit_treasure == TREASURE_PROFILE.back_point


def test_executor_resolves_all_treasure_actions_without_state():
    adb = FakeAdb()
    executor = ActionExecutor(adb)
    actions = [
        OpenTreasure(),
        SelectGoldChest(),
        ConfirmSingleGoldOpen(),
        ConfirmRepeatGoldOpen(),
        DismissTreasureResult(),
        ExitTreasure(),
    ]
    for action in actions:
        executor.execute(action, GEOMETRY)
    assert len(adb.taps) == len(actions)


def test_open_targets_come_from_profile_not_hardcode():
    targets = open_targets()
    assert targets.open_single_point == TREASURE_PROFILE.single_point
    assert targets.open_repeat_point == TREASURE_PROFILE.repeat_point


# Session.


def test_session_completes_enter_open_leave():
    runtime, adb = _runtime(
        [
            _lobby(1),
            _treasure_grid(2),
            _treasure_popup(3, timestamp=3.4),
            _treasure_result(4, timestamp=3.8),
            _treasure_grid(5),
        ],
        [_treasure_grid(2), _treasure_popup(3), _lobby(6)],
    )
    result = runtime.open_gold_keys_from_lobby(_open_once())
    assert result.status is FlowStatus.COMPLETED
    assert result.open is not None
    assert result.open.outcome is TreasureOutcome.SUCCESS
    assert result.enter is not None
    assert result.enter.status is FlowStatus.COMPLETED
    assert result.leave is not None
    assert result.leave.status is FlowStatus.COMPLETED


def test_session_enter_failure_does_no_further_input():
    foreign = _snapshot(
        1,
        base="screen.trading",
        observations=[_observation("landmark.trading_center_title")],
    )
    runtime, adb = _runtime([foreign], [])
    result = runtime.open_gold_keys_from_lobby(_open_once())
    assert result.status is FlowStatus.FAILED
    assert adb.taps == []
    assert result.open is None


def test_session_open_failure_still_restores_lobby():
    runtime, adb = _runtime(
        [_lobby(1), _treasure_grid(2), _treasure_grid(4)],
        [_treasure_grid(2), _treasure_grid(3), _lobby(5)],
    )
    result = runtime.open_gold_keys_from_lobby(_open_once())
    assert result.status is FlowStatus.FAILED
    assert result.leave is not None
    assert result.leave.status is FlowStatus.COMPLETED


# Separation.


def _module_sources():
    root = Path(__file__).resolve().parent.parent / "bot"
    return {
        name: (root / name).read_text(encoding="utf-8")
        for name in (
            "treasure_runtime.py",
            "treasure_facts.py",
            "treasure_profile.py",
            "treasure_center.py",
        )
    }


def test_runtime_has_no_trading_or_promotion_coupling():
    sources = _module_sources()
    for name, source in sources.items():
        import_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines).casefold()
        for forbidden in (
            "trading",
            "keys_promotion",
            "directed_list_scroll",
            "route",
            "planner",
            "monster_wave",
            "stage",
        ):
            assert forbidden not in joined, (name, forbidden)
    import bot.treasure_runtime as runtime_module

    for token in (
        "GOLD_CAPACITY_BLOCKED",
        "SILVER_TO_GOLD",
        "should_open",
        "should_return_to_trading",
        "retry_silver_to_gold",
        "route",
        "planner",
        "OUTPUT_FULL",
    ):
        assert not hasattr(runtime_module, token), token
    assert "output_full" not in set(
        getattr(runtime_module, "__all__", ())
    )


def test_runtime_has_no_craft_relief_inventory_coupling():
    sources = _module_sources()
    for name, source in sources.items():
        import_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines).casefold()
        for forbidden in (
            "craft",
            "relief",
            "inventory",
            "combine",
            "equipment",
            "sell",
        ):
            assert forbidden not in joined, (name, forbidden)
    signature = inspect.signature(TreasureRuntime.execute_gold_key_open)
    params = " ".join(signature.parameters).casefold()
    for forbidden in ("equipment", "trading", "relief", "craft"):
        assert forbidden not in params, forbidden


def test_runtime_has_no_scroll_or_swipe_vocabulary():
    sources = _module_sources()
    for name, source in sources.items():
        import_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines).casefold()
        for forbidden in ("swipe", "scroll", "gesture"):
            assert forbidden not in joined, (name, forbidden)
    import bot.treasure_runtime as runtime_module

    for token in ("swipe", "scroll", "gesture"):
        assert not hasattr(runtime_module, token), token


def test_clean_lobby_helper_matches_battle_mode_zone_contract():
    assert is_clean_lobby(_lobby(1))
    assert not is_clean_lobby(_treasure_grid(2))
    covered = _snapshot(
        1,
        base=SCREEN_LOBBY,
        observations=[_observation("landmark.lobby_trading_center_label")],
        overlays=("menu.quick",),
    )
    assert not is_clean_lobby(covered)
