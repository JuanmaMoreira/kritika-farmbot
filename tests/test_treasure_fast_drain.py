"""E2.2 Gold Key fast drain: right-button semantics, loop, watchdog, safety."""

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.treasure_center import (
    has_right_button_contradiction,
    has_right_gold_open_max,
    has_right_karat_open,
)
from bot.treasure_center_semantics import (
    INDICATOR_TREASURE_GOLD_KEY_REPEAT,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    INDICATOR_TREASURE_KARAT_BASE,
    INDICATOR_TREASURE_KARAT_REPEAT,
    INDICATOR_TREASURE_RESULT,
    INDICATOR_TREASURE_SELECTOR_POPUP,
    LANDMARK_TREASURE_TITLE,
    SCREEN_TREASURE,
)
from bot.treasure_fast_drain import (
    BAR_REPEAT_POINT,
    SELECTOR_REPEAT_POINT,
    GoldKeyDrainConfig,
    GoldKeyDrainOutcome,
    check_fast_drain_entry,
    drain_gold_keys_fast,
    local_karat_boundary,
    local_reward_side,
    resolve_right_button_target,
)

GEOMETRY = FrameGeometry(width=2712, height=1220)
SINGLE_POINT = (0.618, 0.548)


def _observation(name, confidence=0.95):
    return Observation(name, confidence, ObservationSource.LOCAL_CV)


def _snapshot(sequence, *, base, observations=(), overlays=(), status=None,
              timestamp=None, candidates=()):
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


def _popup(sequence, timestamp=None):
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


def _result(sequence, timestamp=None):
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


def _single_only(sequence):
    # Left 1(Open) alone: single gold, popup, but NO repeat signal.
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
        ],
    )


def _karat(sequence, timestamp=None):
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_KARAT_REPEAT),
        ],
        timestamp=timestamp,
    )


def _contradiction(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_TREASURE,
        observations=[
            _observation(LANDMARK_TREASURE_TITLE),
            _observation(INDICATOR_TREASURE_SELECTOR_POPUP),
            _observation(INDICATOR_TREASURE_GOLD_KEY_REPEAT),
            _observation(INDICATOR_TREASURE_KARAT_REPEAT),
        ],
    )


def _foreign(sequence):
    return _snapshot(
        sequence,
        base=SCREEN_LOBBY,
        observations=[_observation("landmark.lobby_trading_center_label")],
    )


def _unknown(sequence):
    return _snapshot(sequence, base=None, status=ResolutionStatus.UNKNOWN)


def _ambiguous(sequence):
    return _snapshot(
        sequence,
        base=None,
        status=ResolutionStatus.AMBIGUOUS,
        candidates=(SCREEN_LOBBY, SCREEN_TREASURE),
    )


class _Clock:
    def __init__(self, start=1000.0):
        self.now_value = float(start)
        self.sleeps = []

    def now(self):
        return self.now_value

    def sleep(self, seconds):
        self.sleeps.append(float(seconds))
        self.now_value += float(seconds)


class _Script:
    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self.taps = []

    def observe(self):
        if len(self._snapshots) > 1:
            return self._snapshots.pop(0)
        return self._snapshots[0]

    def tap(self, point):
        self.taps.append(tuple(point))


def _drain(script, initial, *, config=None, clock=None, **kwargs):
    clock = clock or _Clock()
    kwargs.setdefault("fingerprint", lambda snap: ("seq", snap.sequence))
    result = drain_gold_keys_fast(
        initial_snapshot=initial,
        observe=script.observe,
        tap=script.tap,
        config=config or GoldKeyDrainConfig(),
        initial_open_verified=True,
        clock=clock.now,
        sleeper=clock.sleep,
        **kwargs,
    )
    return result, clock


def _reading(*, popup_gold=0.0, popup_karat=0.0, bar_gold=0.0, bar_karat=0.0):
    """Title-independent content double with detector-like attributes."""
    return SimpleNamespace(
        single_gold_confidence=popup_gold,
        repeat_gold_confidence=popup_gold,
        single_karat_confidence=popup_karat,
        repeat_karat_confidence=popup_karat,
        bar_single_gold_confidence=bar_gold,
        bar_repeat_gold_confidence=bar_gold,
        bar_single_karat_confidence=bar_karat,
        bar_repeat_karat_confidence=bar_karat,
    )


def _measure_script(readings):
    """Measure double replaying one reading per fresh frame."""
    state = {"calls": 0, "readings": list(readings)}

    def measure(_image):
        state["calls"] += 1
        if len(state["readings"]) > 1:
            return state["readings"].pop(0)
        return state["readings"][0]

    measure.state = state
    return measure


# Right-button semantics.


def test_right_gold_popup_and_result_both_tap_allowed():
    assert has_right_gold_open_max(_popup(3))
    assert has_right_gold_open_max(_result(4))


@pytest.mark.parametrize("amount", [10, 7, 1])
def test_amount_text_does_not_change_semantics(amount):
    # The predicate never reads the N(Open) number: the same snapshot
    # authorizes the drain regardless of the offered amount.
    snapshot = _popup(3)
    assert has_right_gold_open_max(snapshot) is True
    assert f"{amount}" not in str(snapshot.observations.observations)


def test_left_single_never_satisfies_right_gold():
    snapshot = _single_only(3)
    assert has_right_gold_open_max(snapshot) is False
    assert check_fast_drain_entry(snapshot, initial_open_verified=True) == (
        "right_gold_absent"
    )


def test_karat_right_is_boundary_not_gold():
    snapshot = _karat(9)
    assert has_right_gold_open_max(snapshot) is False
    assert has_right_karat_open(snapshot) is True


def test_gold_karat_simultaneous_is_contradiction():
    snapshot = _contradiction(9)
    assert has_right_button_contradiction(snapshot) is True
    assert check_fast_drain_entry(snapshot, initial_open_verified=True) == (
        "contradictory_state"
    )


def test_entry_requires_verified_initial_open():
    assert check_fast_drain_entry(
        _popup(3), initial_open_verified=False
    ) == "entry_not_verified"
    assert check_fast_drain_entry(
        _popup(3), initial_open_verified=True
    ) is None


def test_resolve_target_popup_vs_result():
    assert resolve_right_button_target(_popup(3)) == SELECTOR_REPEAT_POINT
    assert resolve_right_button_target(_result(4)) == BAR_REPEAT_POINT


# Fast loop.


def test_fresh_right_gold_emits_one_tap_then_karat_exhausts():
    script = _Script([_popup(11, timestamp=11.0), _karat(12, timestamp=12.0)])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 1
    assert script.taps == [SELECTOR_REPEAT_POINT]
    assert result.karat_boundary_seen is True


def test_repeated_fresh_frames_emit_repeated_taps():
    script = _Script([
        _popup(11, timestamp=11.0),
        _popup(12, timestamp=12.0),
        _popup(13, timestamp=13.0),
        _karat(14, timestamp=14.0),
    ])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.inputs_emitted == 3
    assert script.taps == [SELECTOR_REPEAT_POINT] * 3
    assert result.gold_button_observations == 4  # initial + 3 fresh


def test_same_observation_reused_emits_no_second_tap():
    initial = _popup(10, timestamp=10.0)
    script = _Script([
        _popup(10, timestamp=10.0),  # resample: same observed_at
        _popup(11, timestamp=11.0),
        _karat(12, timestamp=12.0),
    ])
    result, _ = _drain(script, initial)
    assert result.inputs_emitted == 1
    assert script.taps == [SELECTOR_REPEAT_POINT]


def test_target_absent_breaks_to_classify_without_taps():
    initial = _popup(10, timestamp=10.0)
    empty = _snapshot(11, base=SCREEN_TREASURE, observations=[
        _observation(LANDMARK_TREASURE_TITLE),
    ], timestamp=11.0)
    script = _Script([empty, _karat(12, timestamp=12.0)])
    config = GoldKeyDrainConfig(transient_wait_s=0.0)
    result, _ = _drain(script, initial, config=config)
    assert result.inputs_emitted == 0
    assert script.taps == []
    assert result.outcome is GoldKeyDrainOutcome.FAILED


# Watchdog.


def test_watchdog_runs_every_n_inputs():
    script = _Script(
        [_popup(seq, timestamp=float(seq)) for seq in range(11, 18)]
        + [_karat(18, timestamp=18.0)]
    )
    config = GoldKeyDrainConfig(watchdog_every=3)
    result, _ = _drain(script, _popup(10, timestamp=10.0), config=config)
    assert result.inputs_emitted == 7
    assert result.watchdogs_run == 2


def test_watchdog_healthy_progress_continues():
    script = _Script(
        [_popup(seq, timestamp=float(seq)) for seq in range(11, 22)]
        + [_karat(22, timestamp=22.0)]
    )
    config = GoldKeyDrainConfig(watchdog_every=10)
    result, _ = _drain(script, _popup(10, timestamp=10.0), config=config)
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.watchdogs_run == 1


def test_watchdog_visual_stall_stops_with_zero_further_input():
    script = _Script([_popup(seq, timestamp=float(seq)) for seq in range(11, 40)])
    config = GoldKeyDrainConfig(watchdog_every=2)
    result, _ = _drain(
        script,
        _popup(10, timestamp=10.0),
        config=config,
        fingerprint=lambda snap: "frozen",
    )
    assert result.outcome is GoldKeyDrainOutcome.STALL_SUSPECTED
    assert result.inputs_emitted == 2
    assert len(script.taps) == 2


def test_watchdog_state_churn_is_progress_not_stall():
    # Round A lesson: the chest ROI can look static while taps cycle
    # observed<->transient states. Same ROI mark but changing
    # observations must sustain the drain, never stall it.
    measure = _measure_script([_reading(bar_gold=1.0)] * 8)
    script = _Script([
        _popup(11, timestamp=11.0),
        _unknown(12),
        _popup(13, timestamp=13.0),
        _unknown(14),
        _karat(15, timestamp=15.0),
    ])
    config = GoldKeyDrainConfig(watchdog_every=2)
    result, _ = _drain(
        script,
        _popup(10, timestamp=10.0),
        config=config,
        measure_local=measure,
        fingerprint=lambda snap: "static-roi",
    )
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 4
    assert result.watchdogs_run == 2


def test_watchdog_context_lost_stops():
    script = _Script([_popup(11, timestamp=11.0), _foreign(12)])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.CONTEXT_LOST
    assert result.inputs_emitted == 1


def test_unknown_authorizes_zero_further_input():
    # Animation frames lose the anchor: no tap, bounded wait, then fail
    # closed when the repeat state never comes back.
    script = _Script([_unknown(11)])
    result, clock = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.reason == "unknown_state_timeout"
    assert script.taps == []
    assert clock.sleeps, "transient wait must poll, never spin"


def test_ambiguous_authorizes_zero_input():
    script = _Script([_ambiguous(11)])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.reason == "ambiguous_state_timeout"
    assert script.taps == []


def test_unknown_transient_recovers_to_fast_path():
    script = _Script([
        _unknown(11),
        _popup(12, timestamp=12.0),
        _karat(13, timestamp=13.0),
    ])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 1
    assert script.taps == [SELECTOR_REPEAT_POINT]


def test_contradiction_mid_loop_stops_without_extra_tap():
    script = _Script([
        _popup(11, timestamp=11.0),
        _contradiction(12),
    ])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.reason == "contradictory_state"
    assert result.inputs_emitted == 1
    assert len(script.taps) == 1


# Cadence.


def test_cadence_respects_minimum_interval():
    script = _Script([
        _popup(11, timestamp=11.0),
        _popup(12, timestamp=12.0),
        _karat(13, timestamp=13.0),
    ])
    config = GoldKeyDrainConfig(tap_interval_s=0.20)
    result, clock = _drain(script, _popup(10, timestamp=10.0), config=config)
    assert result.inputs_emitted == 2
    tap_sleeps = [s for s in clock.sleeps if s == pytest.approx(0.20)]
    assert len(tap_sleeps) == 2


def test_no_busy_loop_on_resample():
    initial = _popup(10, timestamp=10.0)
    script = _Script([
        _popup(10, timestamp=10.0),
        _popup(10, timestamp=10.0),
        _karat(11, timestamp=11.0),
    ])
    _, clock = _drain(script, initial)
    assert clock.sleeps, "resample path must sleep, never spin"
    assert all(s >= 0.0 for s in clock.sleeps)


# Safety.


def test_safety_deadline_fuse():
    script = _Script([_popup(seq, timestamp=float(seq)) for seq in range(11, 60)])
    config = GoldKeyDrainConfig(
        tap_interval_s=0.20, safety_deadline_s=0.5, max_inputs=10000
    )
    result, _ = _drain(script, _popup(10, timestamp=10.0), config=config)
    assert result.outcome is GoldKeyDrainOutcome.SAFETY_DEADLINE
    assert result.reason == "safety_deadline"


def test_max_inputs_high_fuse():
    script = _Script([_popup(seq, timestamp=float(seq)) for seq in range(11, 60)])
    config = GoldKeyDrainConfig(max_inputs=3, safety_deadline_s=300.0)
    result, _ = _drain(script, _popup(10, timestamp=10.0), config=config)
    assert result.outcome is GoldKeyDrainOutcome.SAFETY_DEADLINE
    assert result.reason == "max_inputs_fuse"
    assert result.inputs_emitted == 3


def test_cancellation_stops():
    script = _Script([_popup(seq, timestamp=float(seq)) for seq in range(11, 60)])
    calls = {"count": 0}

    def cancel():
        calls["count"] += 1
        return calls["count"] > 2

    clock = _Clock()
    result = drain_gold_keys_fast(
        initial_snapshot=_popup(10, timestamp=10.0),
        observe=script.observe,
        tap=script.tap,
        config=GoldKeyDrainConfig(),
        initial_open_verified=True,
        cancel_requested=cancel,
        clock=clock.now,
        sleeper=clock.sleep,
        fingerprint=lambda snap: ("seq", snap.sequence),
    )
    assert result.outcome is GoldKeyDrainOutcome.CANCELLED
    assert result.inputs_emitted <= 2


def test_config_validation():
    with pytest.raises(ValueError):
        GoldKeyDrainConfig(tap_interval_s=-0.1)
    with pytest.raises(ValueError):
        GoldKeyDrainConfig(watchdog_every=0)
    with pytest.raises(ValueError):
        GoldKeyDrainConfig(safety_deadline_s=0.0)
    with pytest.raises(ValueError):
        GoldKeyDrainConfig(max_inputs=0)


# Termination: remainder pattern through the right button only.


def test_remainder_pattern_ends_at_karat_with_right_button_only():
    # 10 -> 7 -> 1 -> Karat: amounts are symbolic here (semantics ignore
    # the number); the path stays on the right button throughout.
    script = _Script([
        _popup(11, timestamp=11.0),
        _result(12, timestamp=12.0),
        _result(13, timestamp=13.0),
        _karat(14, timestamp=14.0),
    ])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 3
    assert script.taps == [
        SELECTOR_REPEAT_POINT,
        BAR_REPEAT_POINT,
        BAR_REPEAT_POINT,
    ]
    assert SINGLE_POINT not in script.taps


def test_no_premium_tap():
    script = _Script([
        _popup(11, timestamp=11.0),
        _karat(12, timestamp=12.0),
        _popup(13, timestamp=13.0),
    ])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    taps_before_karat = len(script.taps)
    assert taps_before_karat == 1
    assert result.karat_boundary_seen is True


def test_no_opened_count_reported():
    script = _Script([_popup(11, timestamp=11.0), _karat(12, timestamp=12.0)])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert not hasattr(result, "opened")
    assert result.inputs_emitted == 1
    assert "opened" not in " ".join(result.evidence)


def test_transient_gold_recovers_to_fast_path():
    transient = _snapshot(11, base=SCREEN_TREASURE, observations=[
        _observation(LANDMARK_TREASURE_TITLE),
        _observation(INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
    ], timestamp=11.0)
    script = _Script([
        transient,
        _popup(12, timestamp=12.0),
        _karat(13, timestamp=13.0),
    ])
    result, _ = _drain(script, _popup(10, timestamp=10.0))
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 1


# Separation: Treasure-only, no neighbours.


def test_module_has_no_trading_craft_relief_routing_imports():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_fast_drain.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("trading", "craft", "relief", "inventory",
                      "monster_wave", "planner", "stage", "route",
                      "sink", "directed_list_scroll", "observed_scroll",
                      "swipe", "gesture", "keys_promotion", "combiner",
                      "combine", "sell", "equipment"):
        assert forbidden not in joined, forbidden


def test_module_has_no_capacity_routing_vocabulary():
    import bot.treasure_fast_drain as _fd

    assert not hasattr(_fd, "GOLD_CAPACITY_BLOCKED")
    assert not hasattr(_fd, "OUTPUT_FULL")
    assert "output_full" not in " ".join(_fd.__all__).casefold()
    assert "gold_capacity_blocked" not in " ".join(_fd.__all__).casefold()
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_fast_drain.py").read_text(encoding="utf-8")
    code_lines = [line for line in source.splitlines()
                  if not line.strip().startswith(('"""', "'''", "#", "-"))]
    joined = "\n".join(code_lines).casefold()
    assert "gold_capacity_blocked" not in joined
    assert "output_full" not in joined


def test_module_never_references_left_button():
    # No left-button USE: no single/left target identifier in code.
    # Prose may still name the left control to forbid it.
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_fast_drain.py").read_text(encoding="utf-8")
    import_lines = {line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))}
    code = "\n".join(
        line for line in source.splitlines() if line not in import_lines
    ).casefold()
    for forbidden in ("open_single_point", "single_point", "left_button",
                      "left_point", "tap_open_single", "confirm_single"):
        assert forbidden not in code, forbidden


def test_runtime_module_untouched_by_drain_imports():
    import bot.treasure_fast_drain as _fd

    signature = inspect.signature(_fd.drain_gold_keys_fast)
    params = " ".join(signature.parameters).casefold()
    for forbidden in ("trading", "craft", "relief", "planner", "stage",
                      "capacity", "silver", "output_full"):
        assert forbidden not in params, forbidden


# Reward transient: title hidden, right Gold stays actionable locally.


def test_local_reward_side_requires_pair_gold_without_karat():
    assert local_reward_side(_reading(bar_gold=1.0)) == "bar"
    assert local_reward_side(_reading(popup_gold=1.0)) == "popup"
    # Lone icon without its pair never authorizes.
    lone = _reading()
    lone.bar_repeat_gold_confidence = 1.0
    assert local_reward_side(lone) is None
    # Any Karat vetoes, even with Gold present.
    assert local_reward_side(_reading(bar_gold=1.0, bar_karat=1.0)) is None
    assert local_reward_side(_reading(popup_gold=1.0, popup_karat=1.0)) is None
    assert local_reward_side(_reading()) is None
    assert local_reward_side(object()) is None


def test_local_karat_boundary_needs_premium_without_gold():
    assert local_karat_boundary(_reading(bar_karat=1.0)) is True
    assert local_karat_boundary(_reading(popup_karat=1.0)) is True
    assert local_karat_boundary(_reading(bar_gold=1.0)) is False
    assert local_karat_boundary(_reading(bar_gold=1.0, bar_karat=1.0)) is False
    assert local_karat_boundary(_reading()) is False


def test_reward_grid_unknown_with_local_gold_stays_actionable():
    measure = _measure_script([_reading(bar_gold=1.0)] * 4)
    script = _Script([
        _unknown(11),
        _unknown(12),
        _unknown(13),
        _karat(14, timestamp=14.0),
    ])
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 3
    assert script.taps == [BAR_REPEAT_POINT] * 3
    assert SINGLE_POINT not in script.taps


def test_reward_grid_unknown_without_local_gold_is_zero_input():
    measure = _measure_script([_reading()])
    script = _Script([_unknown(11)])
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.inputs_emitted == 0
    assert script.taps == []


def test_strong_foreign_never_consults_local_measure():
    calls = []

    def measure(_image):
        calls.append(1)
        return _reading(bar_gold=1.0)

    script = _Script([_foreign(11)])
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert result.outcome is GoldKeyDrainOutcome.CONTEXT_LOST
    assert result.inputs_emitted == 0
    assert script.taps == []
    assert calls == []


def test_reward_transient_disabled_restores_strict_behavior():
    measure = _measure_script([_reading(bar_gold=1.0)])
    script = _Script([_unknown(11)])
    config = GoldKeyDrainConfig(reward_transient=False)
    result, _ = _drain(
        script, _popup(10, timestamp=10.0),
        config=config, measure_local=measure,
    )
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.reason == "unknown_state_timeout"
    assert script.taps == []
    with pytest.raises(ValueError):
        GoldKeyDrainConfig(reward_transient="yes")


# No-dismiss invariant: the only input is the right-button point.


def test_module_has_no_dismiss_or_outside_button_vocabulary():
    # Prose may name the forbidden behavior to forbid it; code must not
    # be able to express it: no dismiss/outside call identifiers.
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_fast_drain.py").read_text(encoding="utf-8")
    import_lines = {line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))}
    code = "\n".join(
        line for line in source.splitlines() if line not in import_lines
    )
    lowered = code.casefold()
    for forbidden in ("dismiss(", "DismissTreasure", "tap_outside",
                      "outside_tap", "outside_point", "dismiss_tap"):
        assert forbidden.casefold() not in lowered, forbidden


def test_every_tap_lands_on_a_right_button_point():
    measure = _measure_script(
        [_reading(bar_gold=1.0), _reading(popup_gold=1.0)]
    )
    script = _Script([
        _popup(11, timestamp=11.0),
        _unknown(12),
        _unknown(13),
        _karat(14, timestamp=14.0),
    ])
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert result.inputs_emitted == 3
    assert script.taps[0] == SELECTOR_REPEAT_POINT
    assert set(script.taps) <= {SELECTOR_REPEAT_POINT, BAR_REPEAT_POINT}


# Dual-role taps: cut animation or start next batch, never counted.


def test_repeated_local_taps_allowed_on_fresh_frames():
    measure = _measure_script([_reading(bar_gold=1.0)] * 6)
    script = _Script(
        [_unknown(seq) for seq in range(11, 15)]
        + [_karat(15, timestamp=15.0)]
    )
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 4


def test_taps_are_never_reported_as_batches():
    measure = _measure_script([_reading(bar_gold=1.0)] * 3)
    script = _Script([_unknown(11), _karat(12, timestamp=12.0)])
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert not hasattr(result, "opened")
    joined = " ".join(result.evidence)
    assert "consumed" not in joined
    assert "opened:" not in joined
    assert "batch" not in joined


# Corrected watchdog: reward transient is healthy, title never stalls.


def test_watchdog_accepts_reward_transient_as_healthy():
    measure = _measure_script([_reading(bar_gold=1.0)] * 8)
    script = _Script(
        [_unknown(seq) for seq in range(11, 15)]
        + [_karat(15, timestamp=15.0)]
    )
    config = GoldKeyDrainConfig(watchdog_every=2)
    result, _ = _drain(
        script, _popup(10, timestamp=10.0),
        config=config, measure_local=measure,
    )
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 4
    assert result.watchdogs_run == 2


def test_watchdog_stalls_on_frozen_reward_grid():
    measure = _measure_script([_reading(bar_gold=1.0)] * 8)
    script = _Script([_unknown(seq) for seq in range(11, 30)])
    config = GoldKeyDrainConfig(watchdog_every=2)
    result, _ = _drain(
        script,
        _popup(10, timestamp=10.0),
        config=config,
        measure_local=measure,
        fingerprint=lambda snap: "frozen-grid",
    )
    assert result.outcome is GoldKeyDrainOutcome.STALL_SUSPECTED
    assert result.inputs_emitted == 2
    assert len(script.taps) == 2


# Termination through the local path.


def test_local_karat_terminates_without_premium_tap():
    measure = _measure_script([_reading(bar_karat=1.0)] * 6)
    script = _Script([
        _unknown(11),
        _unknown(12),
        _karat(13, timestamp=13.0),
    ])
    result, _ = _drain(
        script, _popup(10, timestamp=10.0), measure_local=measure
    )
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 0
    assert script.taps == []
    assert result.karat_boundary_seen is True


def test_local_karat_without_confirmation_fails_closed():
    measure = _measure_script([_reading(bar_karat=1.0)] * 200)
    script = _Script([_unknown(11)])
    config = GoldKeyDrainConfig(transient_wait_s=0.2)
    result, _ = _drain(
        script, _popup(10, timestamp=10.0),
        config=config, measure_local=measure,
    )
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.inputs_emitted == 0
    assert script.taps == []


# Reward-transient entry: verified open + local pair Gold suffices.


def test_entry_from_reward_transient_with_verified_open():
    measure = _measure_script([_reading(bar_gold=1.0)] * 4)
    script = _Script([
        _unknown(12),
        _karat(13, timestamp=13.0),
    ])
    clock = _Clock()
    result = drain_gold_keys_fast(
        initial_snapshot=_unknown(11),
        observe=script.observe,
        tap=script.tap,
        config=GoldKeyDrainConfig(),
        initial_open_verified=True,
        clock=clock.now,
        sleeper=clock.sleep,
        fingerprint=lambda snap: ("seq", snap.sequence),
        measure_local=measure,
    )
    assert result.outcome is GoldKeyDrainOutcome.GOLD_KEYS_EXHAUSTED
    assert result.inputs_emitted == 1
    assert script.taps == [BAR_REPEAT_POINT]
    assert "entry:reward_transient_local" in result.evidence


def test_entry_from_transient_refused_without_measure_or_verify():
    script = _Script([_karat(12, timestamp=12.0)])
    clock = _Clock()
    result = drain_gold_keys_fast(
        initial_snapshot=_unknown(11),
        observe=script.observe,
        tap=script.tap,
        config=GoldKeyDrainConfig(),
        initial_open_verified=True,
        clock=clock.now,
        sleeper=clock.sleep,
        fingerprint=lambda snap: ("seq", snap.sequence),
    )
    assert result.outcome is GoldKeyDrainOutcome.FAILED
    assert result.reason == "unknown_state"
    assert script.taps == []
    denied = drain_gold_keys_fast(
        initial_snapshot=_unknown(11),
        observe=script.observe,
        tap=script.tap,
        config=GoldKeyDrainConfig(),
        initial_open_verified=False,
        clock=clock.now,
        sleeper=clock.sleep,
        fingerprint=lambda snap: ("seq", snap.sequence),
        measure_local=_measure_script([_reading(bar_gold=1.0)]),
    )
    assert denied.outcome is GoldKeyDrainOutcome.FAILED
    assert denied.reason == "entry_not_verified"
