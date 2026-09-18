"""Treasure Gold Keys capability: readiness, currency, open, budget, separation."""

import inspect
from pathlib import Path

import numpy as np
import pytest

from bot.action_executor import FrameGeometry
from bot.capture import FrameSnapshot
from bot.catalog import SCREEN_LOBBY
from bot.observations import Observation, ObservationBatch, ObservationSource
from bot.runtime_observer import RuntimeFacts, RuntimeSnapshot
from bot.state import ResolutionStatus, ResolvedState
from bot.treasure_center_semantics import (
    INDICATOR_TREASURE_GOLD_KEY_REPEAT,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR,
    INDICATOR_TREASURE_KARAT_BASE,
    INDICATOR_TREASURE_KARAT_REPEAT,
    SCREEN_TREASURE,
)
from bot.treasure_center import is_gold_keys_content_ready
from bot.treasure_keys import (
    GOLD_ALLOWED_CURRENCY_KINDS,
    GoldKeyOpenRequest,
    GoldKeyOpenResult,
    GoldKeyQuantity,
    GoldKeyQuantityMode,
    TreasureCurrencyFact,
    TreasureOpenTargets,
    TreasureOutcome,
    check_currency,
    check_fact_fresh,
    check_gold_ready,
    execute_gold_key_open,
    is_gold_ready,
)


def _observation(name, confidence=0.95):
    return Observation(name, confidence, ObservationSource.LOCAL_CV)


def _snapshot(sequence, *, base, observations=(), overlays=(), status=None,
              candidates=()):
    if status is None:
        status = ResolutionStatus.RESOLVED if base else ResolutionStatus.UNKNOWN
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return RuntimeSnapshot(
        FrameSnapshot(image, float(sequence), sequence),
        ObservationBatch(sequence, float(sequence), tuple(observations)),
        ResolvedState(
            status,
            sequence,
            float(sequence),
            base_context=base,
            overlays=tuple(overlays),
            base_candidates=tuple(candidates),
        ),
        RuntimeFacts(),
        FrameGeometry.from_frame(image),
    )


def _treasure_ready(sequence=10, gold=INDICATOR_TREASURE_GOLD_KEY_SELECTOR):
    return _snapshot(sequence, base=SCREEN_TREASURE,
                     observations=[_observation(gold)])


def _fact(currency="gold_key", amount=1, count=10, overlay="selector",
          sequence=10, observed_at=None):
    if observed_at is None:
        observed_at = float(sequence)
    return TreasureCurrencyFact(
        currency=currency,
        amount_offered=amount,
        count=count,
        overlay=overlay,
        sequence=sequence,
        observed_at=observed_at,
        evidence=(f"{currency}@{sequence}",),
    )


def _targets():
    return TreasureOpenTargets(
        open_single_point=(0.5, 0.5),
        open_repeat_point=(0.4, 0.8),
    )


def _request(quantity=None, max_actions=10, max_fact_age_s=2.0,
             post_action_timeout_s=4.0, post_action_max_polls=48):
    if quantity is None:
        quantity = GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE)
    return GoldKeyOpenRequest(
        quantity=quantity,
        allowed_currency_kinds=frozenset({"gold_key"}),
        targets=_targets(),
        max_actions=max_actions,
        max_fact_age_s=max_fact_age_s,
        post_action_timeout_s=post_action_timeout_s,
        post_action_max_polls=post_action_max_polls,
        source="lobby",
        return_to="lobby",
    )


class _Script:
    def __init__(self, states):
        self.states = list(states)
        self.taps = []
        self.reads = 0

    def tap(self, point):
        self.taps.append(tuple(point))

    def read_state(self):
        self.reads += 1
        if not self.states:
            return None
        return self.states.pop(0)


def _execute(snapshot=None, request=None, script=None, **overrides):
    snapshot = snapshot if snapshot is not None else _treasure_ready()
    request = request if request is not None else _request()
    script = script if script is not None else _Script([])
    values = {
        "snapshot": snapshot,
        "request": request,
        "tap": script.tap,
        "read_state": script.read_state,
    }
    values.update(overrides)
    return execute_gold_key_open(**values), script


# Context / readiness: positive Treasure gates, everything else fails closed.


def test_ready_selector_proceeds_to_open_once_success():
    before = _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5)
    after = _fact(amount=1, count=9, overlay="result", sequence=11)
    result, script = _execute(script=_Script([before, after]))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert script.taps == [(0.5, 0.5)]
    assert result.before is before
    assert result.after is after


def test_ready_repeat_signal_proceeds():
    snapshot = _treasure_ready(gold=INDICATOR_TREASURE_GOLD_KEY_REPEAT)
    assert check_gold_ready(snapshot) is None
    assert is_gold_ready(snapshot)
    assert is_gold_keys_content_ready(snapshot)
    before = _fact(amount=10, count=20, overlay="result", sequence=10,
                   observed_at=10.5)
    after = _fact(amount=10, count=10, overlay="result", sequence=11)
    result, script = _execute(snapshot=snapshot,
                              script=_Script([before, after]))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 10
    assert script.taps == [(0.4, 0.8)]


def test_wrong_context_does_zero_input():
    foreign = _snapshot(10, base=SCREEN_LOBBY,
                        observations=[_observation(
                            INDICATOR_TREASURE_GOLD_KEY_SELECTOR)])
    assert check_gold_ready(foreign) == "not_treasure"
    assert not is_gold_ready(foreign)
    script = _Script([_fact(sequence=10)])
    result, _ = _execute(snapshot=foreign, script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == "not_treasure"
    assert script.taps == []
    assert script.reads == 0


def test_overlays_break_readiness_without_input():
    covered = _snapshot(10, base=SCREEN_TREASURE,
                        observations=[_observation(
                            INDICATOR_TREASURE_GOLD_KEY_SELECTOR)],
                        overlays=("popup.unacquired",))
    assert check_gold_ready(covered) == "overlays_present"
    script = _Script([])
    result, _ = _execute(snapshot=covered, script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert script.taps == []
    assert script.reads == 0


def test_contradictory_gold_and_karat_authorizes_nothing():
    both = _snapshot(10, base=SCREEN_TREASURE,
                     observations=[_observation(
                         INDICATOR_TREASURE_GOLD_KEY_SELECTOR),
                         _observation(INDICATOR_TREASURE_KARAT_BASE)])
    assert check_gold_ready(both) == "contradictory_state"
    script = _Script([])
    result, _ = _execute(snapshot=both, script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert script.taps == []


def test_treasure_without_gold_signal_is_not_ready():
    bare = _snapshot(10, base=SCREEN_TREASURE, observations=[])
    assert check_gold_ready(bare) == "gold_not_ready"
    script = _Script([])
    result, _ = _execute(snapshot=bare, script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert script.taps == []
    assert script.reads == 0


@pytest.mark.parametrize("status,reason", [
    (ResolutionStatus.UNKNOWN, "unknown_state"),
    (ResolutionStatus.AMBIGUOUS, "ambiguous_state"),
])
def test_unknown_and_ambiguous_never_authorize(status, reason):
    if status is ResolutionStatus.AMBIGUOUS:
        snapshot = _snapshot(10, base=None, status=status,
                             candidates=(SCREEN_LOBBY, SCREEN_TREASURE),
                             observations=[_observation(
                                 INDICATOR_TREASURE_GOLD_KEY_SELECTOR)])
    else:
        snapshot = _snapshot(10, base=None, status=status,
                             observations=[_observation(
                                 INDICATOR_TREASURE_GOLD_KEY_SELECTOR)])
    assert check_gold_ready(snapshot) == reason
    assert not is_gold_ready(snapshot)
    script = _Script([])
    result, _ = _execute(snapshot=snapshot, script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == reason
    assert script.taps == []
    assert script.reads == 0


# Currency boundary: fresh Gold allows, premium/empty/unreadable never confirm.


def test_gold_currency_allows_action():
    fact = _fact(currency="gold_key", amount=1, sequence=10)
    assert check_currency(fact, GOLD_ALLOWED_CURRENCY_KINDS) is None


def test_karat_stops_before_confirm_with_zero_taps():
    before = _fact(currency="karat", amount=None, count=None,
                   overlay="selector", sequence=10, observed_at=10.5)
    script = _Script([before])
    result, _ = _execute(script=script)
    assert result.outcome is TreasureOutcome.PREMIUM_CURRENCY_BOUNDARY
    assert result.boundary == "premium_currency"
    assert result.opened == 0
    assert script.taps == []
    assert script.reads == 1


def test_other_premium_kind_stops_before_confirm():
    before = _fact(currency="diamonds", amount=None, count=None,
                   overlay="selector", sequence=10, observed_at=10.5)
    # Bypass dataclass gold-only amount rule via object construction:
    # currency "diamonds" already forces amount None, valid here.
    script = _Script([before])
    result, _ = _execute(script=script)
    assert result.outcome is TreasureOutcome.PREMIUM_CURRENCY_BOUNDARY
    assert script.taps == []


def test_empty_reports_no_keys_without_input():
    before = _fact(currency="empty", amount=None, count=0,
                   overlay="selector", sequence=10, observed_at=10.5)
    script = _Script([before])
    result, _ = _execute(script=script)
    assert result.outcome is TreasureOutcome.NO_KEYS
    assert result.boundary == "no_keys"
    assert script.taps == []


def test_unknown_currency_fails_closed_without_input():
    before = _fact(currency="unknown", amount=None, count=None,
                   overlay=None, sequence=10, observed_at=10.5)
    script = _Script([before])
    result, _ = _execute(script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == "unreadable_currency"
    assert script.taps == []


def test_stale_first_fact_fails_closed_without_input():
    before = _fact(sequence=5)
    script = _Script([before])
    result, _ = _execute(snapshot=_treasure_ready(sequence=10),
                         script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == "stale_fact"
    assert script.taps == []


# Physical freshness: frame capture time behind a causal barrier
# (HIL 2026-09-18 Smoke B: the decode counter advances at video rate
# while reads sample at analyze cadence, so a sequence gap measures
# pipeline latency, not content age).


def test_check_fact_fresh_accepts_posterior_frame_within_age():
    assert check_fact_fresh(
        _fact(sequence=70, observed_at=10.3), 10.0, 2.0) is None


def test_check_fact_fresh_rejects_frame_at_barrier():
    assert check_fact_fresh(
        _fact(sequence=10, observed_at=10.0), 10.0, 2.0) == "stale_fact"


def test_check_fact_fresh_rejects_older_frame_despite_newer_sequence():
    # New sequence with an older capture time must never authorize:
    # sequence orders reads, only observed_at proves physical freshness.
    assert check_fact_fresh(
        _fact(sequence=11, observed_at=9.0), 10.0, 2.0) == "stale_fact"


def test_check_fact_fresh_rejects_posterior_but_too_old_frame():
    assert check_fact_fresh(
        _fact(sequence=200, observed_at=12.5), 10.0, 2.0) == "stale_fact"


def test_check_fact_fresh_rejects_missing_observed_at():
    bare = TreasureCurrencyFact(
        currency="gold_key", amount_offered=1, count=None,
        overlay="selector", sequence=10, observed_at=None, evidence=(),
    )
    assert check_fact_fresh(bare, 10.0, 2.0) == "stale_fact"
    assert check_fact_fresh(None, 10.0, 2.0) == "stale_fact"


def test_check_fact_fresh_rejects_invalid_contract():
    with pytest.raises(ValueError):
        check_fact_fresh(_fact(), -1.0, 2.0)
    with pytest.raises(ValueError):
        check_fact_fresh(_fact(), 10.0, -1.0)
    with pytest.raises(ValueError):
        GoldKeyOpenRequest(
            quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE),
            allowed_currency_kinds=frozenset({"gold_key"}),
            targets=_targets(),
            max_fact_age_s=-0.5,
        )
    with pytest.raises(ValueError):
        GoldKeyOpenRequest(
            quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE),
            allowed_currency_kinds=frozenset({"gold_key"}),
            targets=_targets(),
            post_action_timeout_s=-1.0,
        )
    with pytest.raises(ValueError):
        GoldKeyOpenRequest(
            quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE),
            allowed_currency_kinds=frozenset({"gold_key"}),
            targets=_targets(),
            post_action_max_polls=0,
        )


def test_same_sequence_posterior_frame_authorizes_open():
    # Same decode counter with a strictly newer capture time is a
    # physically newer frame: sequence alone never vetoes freshness.
    snapshot = _treasure_ready(sequence=10)
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10,
              observed_at=10.4),
        _fact(amount=1, count=9, overlay="result", sequence=11,
              observed_at=10.8),
    ]
    result, script = _execute(snapshot=snapshot, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert script.taps == [(0.5, 0.5)]


def test_newer_sequence_older_frame_fails_closed_without_input():
    snapshot = _treasure_ready(sequence=10)
    before = _fact(amount=1, count=10, overlay="selector", sequence=60,
                   observed_at=9.5)
    result, script = _execute(snapshot=snapshot, script=_Script([before]))
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == "stale_fact"
    assert script.taps == []


def test_smoke_b_regression_huge_sequence_gap_fresh_popup_authorizes():
    # Exact Smoke B shape: the popup frame arrived ~60 decode frames
    # after the authorizing snapshot but 0.3s later in capture time.
    snapshot = _treasure_ready(sequence=10)
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=70,
              observed_at=10.3),
        _fact(amount=1, count=None, overlay="result", sequence=71,
              observed_at=10.6),
    ]
    result, script = _execute(snapshot=snapshot, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert result.inputs == ("tap_open_single",)


def test_builders_propagate_snapshot_capture_time():
    from bot.treasure_facts import fact_for_single
    snapshot = _treasure_ready(sequence=10)
    assert snapshot.timestamp == 10.0
    fact = fact_for_single(snapshot)
    assert fact is not None
    assert fact.observed_at == 10.0
    # An explicitly older capture time is preserved, never refreshed.
    aged = fact_for_single(snapshot, observed_at=9.0)
    assert aged is not None
    assert aged.observed_at == 9.0


def test_fact_builders_use_no_clock():
    # No-fake-freshness: builders copy the frame time; they must not
    # stamp "now" from any clock.
    import re
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_facts.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines)
    assert re.search(r"\bmonotonic\b", joined) is None
    assert re.search(r"\bperf_counter\b", joined) is None
    assert re.search(r"\bdatetime\b", joined) is None
    assert re.search(r"^import time$", joined, re.MULTILINE) is None
    assert re.search(r"from time import", joined) is None


def test_unreadable_first_state_fails_closed():
    script = _Script([None])
    result, _ = _execute(script=script)
    assert result.outcome is TreasureOutcome.FAILED
    assert script.taps == []


# Open semantics: success, batch, no-effect, stale postcondition.


def test_batch_exact_eleven_uses_repeat_then_single():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.EXACT, amount=11),
        max_actions=5,
    )
    states = [
        _fact(amount=10, count=20, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=10, count=10, overlay="result", sequence=11),
        _fact(amount=1, count=10, overlay="result", sequence=12),
        _fact(amount=1, count=9, overlay="result", sequence=13),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 11
    assert script.taps == [(0.4, 0.8), (0.5, 0.5)]

def test_no_effect_on_unchanged_count_stops_without_retry():
    request = _request(post_action_max_polls=3)
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(amount=1, count=10, overlay="result", sequence=11),
        _fact(amount=1, count=10, overlay="result", sequence=12),
        _fact(amount=1, count=10, overlay="result", sequence=13),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.reason == "no_evidence"
    assert result.opened == 0
    assert len(script.taps) == 1
    assert script.reads == 4

def test_no_effect_on_unchanged_state_without_counts():
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(amount=1, count=None, overlay="selector", sequence=11),
    ]
    result, script = _execute(request=_request(post_action_max_polls=3),
                              script=_Script(states))
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.reason == "state_unchanged"
    assert len(script.taps) == 1


def test_resampled_after_waits_for_evidence_then_no_effect():
    # Same decode counter as the authorizing read is a resample, not a
    # failure: the window waits for a strictly newer frame, then closes
    # as NO_EFFECT without a second tap.
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.8),
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=11.0),
    ]
    result, script = _execute(request=_request(post_action_max_polls=2),
                              script=_Script(states))
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.reason == "no_evidence"
    assert result.opened == 0
    assert len(script.taps) == 1
    assert script.reads == 3


def test_unreadable_after_waits_then_no_effect():
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        None,
        None,
    ]
    result, script = _execute(request=_request(post_action_max_polls=2),
                              script=_Script(states))
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.reason == "no_evidence"
    assert result.opened == 0
    assert len(script.taps) == 1
    assert script.reads == 3


def test_late_result_after_unchanged_polls_is_success():
    # Exact HIL E2.1 shape: first polls still show the popup, the
    # result arrives later inside the bounded window. One tap total.
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(amount=1, count=None, overlay="selector", sequence=11,
              observed_at=10.8),
        _fact(amount=1, count=None, overlay="selector", sequence=12,
              observed_at=11.0),
        _fact(amount=1, count=None, overlay="result", sequence=13,
              observed_at=11.5),
    ]
    result, script = _execute(request=_request(post_action_max_polls=4),
                              script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert result.inputs == ("tap_open_single",)
    assert len(script.taps) == 1
    assert script.reads == 4


def test_post_action_deadline_expiry_is_no_effect():
    # The deadline governs even with polls remaining: a fake clock jumps
    # past it after the first unchanged poll.
    times = iter([100.0, 100.1, 200.0])
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(amount=1, count=None, overlay="selector", sequence=11,
              observed_at=10.8),
    ]
    result, script = _execute(
        request=_request(post_action_max_polls=48),
        script=_Script(states),
        clock=lambda: next(times),
    )
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.opened == 0
    assert len(script.taps) == 1
    assert script.reads == 2


def test_stale_result_after_tap_is_not_success():
    # A result frame older than the tap barrier never proves this open,
    # even with a newer decode counter.
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(amount=1, count=None, overlay="result", sequence=60,
              observed_at=9.0),
        _fact(amount=1, count=None, overlay="selector", sequence=61,
              observed_at=10.8),
    ]
    result, script = _execute(request=_request(post_action_max_polls=2),
                              script=_Script(states))
    assert result.outcome is TreasureOutcome.NO_EFFECT
    assert result.opened == 0
    assert len(script.taps) == 1


def test_premium_after_tap_keeps_existing_boundary_contract():
    # The tap already happened: a premium surface is reported as a
    # boundary on the proven open, with zero further taps.
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(currency="karat", amount=None, count=None,
              overlay="selector", sequence=11, observed_at=10.8),
    ]
    result, script = _execute(request=_request(post_action_max_polls=2),
                              script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.boundary == "premium_currency"
    assert len(script.taps) == 1


def test_cancel_during_post_action_window_exits_without_retry():
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10,
              observed_at=10.5),
        _fact(amount=1, count=None, overlay="selector", sequence=11,
              observed_at=10.8),
        _fact(amount=1, count=None, overlay="selector", sequence=12,
              observed_at=11.0),
    ]
    script = _Script(states)
    result, _ = _execute(request=_request(post_action_max_polls=5),
                         script=script,
                         cancel_requested=lambda: script.reads >= 2)
    assert result.outcome is TreasureOutcome.CANCELLED
    assert result.opened == 0
    assert len(script.taps) == 1


def test_exact_overshoot_offer_fails_closed_without_tap():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.EXACT, amount=5),
    )
    states = [_fact(amount=10, count=20, overlay="selector", sequence=10, observed_at=10.5)]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.FAILED
    assert result.reason == "impossible_amount"
    assert script.taps == []


def test_minimum_demonstrated_without_counts_uses_result_overlay():
    states = [
        _fact(amount=1, count=None, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=None, overlay="result", sequence=11),
    ]
    result, script = _execute(script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1


# Quantity modes.


def test_open_once_with_repeat_offer_opens_ten():
    states = [
        _fact(amount=10, count=30, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=10, count=20, overlay="result", sequence=11),
    ]
    result, script = _execute(script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 10
    assert len(script.taps) == 1


def test_up_to_partial_then_empty_returns_success_with_boundary():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.UP_TO, amount=10),
    )
    states = [
        _fact(amount=1, count=5, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=4, overlay="result", sequence=11),
        _fact(currency="empty", amount=None, count=0,
              overlay="result", sequence=12),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert result.boundary == "no_keys"
    assert len(script.taps) == 1


def test_up_to_stops_before_overshoot_with_verified_opened():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.UP_TO, amount=5),
    )
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
        _fact(amount=10, count=9, overlay="result", sequence=12),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert len(script.taps) == 1


def test_max_within_budget_uses_two_actions():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.MAX_WITHIN_BUDGET),
        max_actions=2,
    )
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
        _fact(amount=1, count=9, overlay="result", sequence=12),
        _fact(amount=1, count=8, overlay="result", sequence=13),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 2
    assert len(script.taps) == 2


# Budget: bounded, no input after exhausted, no hidden loop.


def test_budget_exhausted_when_exact_needs_more_than_max():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.EXACT, amount=3),
        max_actions=1,
    )
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.BUDGET_EXHAUSTED
    assert result.opened == 1
    assert len(script.taps) == 1
    assert script.reads == 2


def test_open_once_ignores_extra_budget_without_hidden_loop():
    request = _request(
        quantity=GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE),
        max_actions=10,
    )
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
    ]
    result, script = _execute(request=request, script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert len(script.taps) == 1
    assert script.reads == 2


def test_cancel_before_input_does_zero_reads_and_taps():
    script = _Script([_fact(sequence=10)])
    result, _ = _execute(script=script, cancel_requested=lambda: True)
    assert result.outcome is TreasureOutcome.CANCELLED
    assert script.taps == []
    assert script.reads == 0


# Equipment separation: full never blocks by itself; no imports/callbacks.


def test_equipment_full_state_does_not_block_by_itself():
    # The capability takes no equipment parameter: even a hypothetical
    # "equipment full 180/128" cannot change the outcome.
    equipment_full = {"have": 180, "cap": 128, "full": True}
    assert equipment_full["full"]
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
    ]
    result, script = _execute(script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert result.opened == 1
    assert script.taps == [(0.5, 0.5)]


def test_module_has_no_equipment_relief_inventory_imports():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_keys.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("equipment", "combine", "relief", "inventory",
                      "craft", "sell"):
        assert forbidden not in joined, forbidden
    signature = inspect.signature(execute_gold_key_open)
    params = " ".join(signature.parameters).casefold()
    for forbidden in ("equipment", "combine", "relief", "inventory",
                      "craft"):
        assert forbidden not in params, forbidden


# Routing separation: no Trading, no OUTPUT_FULL, no planner/MW/stage, no scroll.


def test_module_has_no_trading_routing_planner_scroll_imports():
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_keys.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined = "\n".join(import_lines).casefold()
    for forbidden in ("trading", "directed_list_scroll",
                      "trading_materials_scroll", "observed_scroll",
                      "character_select_scroll", "swipe", "gesture",
                      "route", "planner", "monster_wave", "stage",
                      "sink", "relief"):
        assert forbidden not in joined, forbidden
    # Structural separation: no forbidden identifiers defined as code.
    # Historical Astra words may appear in docstrings; they must never
    # become outcomes, functions, classes or parameters.
    import bot.treasure_keys as _tk

    assert not hasattr(_tk, "OUTPUT_FULL")
    assert "output_full" not in [m.value for m in TreasureOutcome]
    for name in ("should_open", "should_return_to_trading",
                 "retry_silver_to_gold", "route", "planner",
                 "relief", "craft", "trading"):
        assert not hasattr(_tk, name), name
    assert "output_full" not in set(_tk.__all__)


def test_outcomes_never_report_output_full():
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
    ]
    result, _ = _execute(script=_Script(states))
    assert result.boundary != "output_full"
    assert "output_full" not in " ".join(result.evidence).casefold()


def test_allowed_currency_is_gold_key_only():
    assert GOLD_ALLOWED_CURRENCY_KINDS == frozenset({"gold_key"})
    bad = GoldKeyQuantity(mode=GoldKeyQuantityMode.OPEN_ONCE)
    with pytest.raises(ValueError):
        GoldKeyOpenRequest(
            quantity=bad,
            allowed_currency_kinds=frozenset({"gold"}),
            targets=_targets(),
        )
    with pytest.raises(ValueError):
        GoldKeyOpenRequest(
            quantity=bad,
            allowed_currency_kinds=frozenset({"gold_key", "karats"}),
            targets=_targets(),
        )


# Return contract: capability never navigates; after is explicit.


def test_capability_owns_no_return_navigation():
    # Targets expose only open points (no back/dismiss/leave navigation);
    # historical Astra names may appear in docs but never as code.
    fields = set(TreasureOpenTargets.__dataclass_fields__)
    assert fields == {"open_single_point", "open_repeat_point"}
    source = (Path(__file__).resolve().parent.parent
              / "bot" / "treasure_keys.py").read_text(encoding="utf-8")
    import_lines = [line for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    assert "back" not in "\n".join(import_lines).casefold()
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
    ]
    result, script = _execute(script=_Script(states))
    assert result.outcome is TreasureOutcome.SUCCESS
    assert set(script.taps) <= {(0.5, 0.5), (0.4, 0.8)}
    assert result.after is not None
    assert result.after.sequence > result.before.sequence
    assert result.after.overlay == "result"


def test_no_scroll_vocabulary_in_taps():
    states = [
        _fact(amount=1, count=10, overlay="selector", sequence=10, observed_at=10.5),
        _fact(amount=1, count=9, overlay="result", sequence=11),
    ]
    result, script = _execute(script=_Script(states))
    assert result.inputs == ("tap_open_single",)
    for entry in result.inputs:
        assert "scroll" not in entry.casefold()
        assert "swipe" not in entry.casefold()
