"""Deterministic synthetic sequences, not physical matchmaking evidence."""
import pytest
from bot.arena_adaptive import ArenaAdaptiveController, REWARDS
from bot.arena_semantics import ArenaBatchResult, ArenaResultProvenance, ArenaDifficulty as D


def batch(difficulty, used=80, won=40, run='batch', timestamp=100.):
    return ArenaBatchResult(difficulty, 8, used, won, timestamp,
        ArenaResultProvenance(run, 'source', 1, 'a' * 64, 1., 1.))


def feed(controller, won, used=80):
    return controller.observe(batch(controller.difficulty, used, won, str(controller.batches), 100. + controller.batches))


def test_initial_hard_and_unknown_is_not_zero():
    c = ArenaAdaptiveController()
    assert c.difficulty is D.HARD
    assert all(c.score(d) is None for d in D)
    assert feed(c, 40).difficulty is D.HARD
    assert c.score(D.HARD) == 90 and c.score(D.NORMAL) is None


def test_reward_comparison_and_adjacent_exploration():
    c = ArenaAdaptiveController()
    # Hard 25% => 45; Normal 75% => 90. Easy remains unknown, not 0%.
    decisions = [feed(c, n).difficulty for n in (20, 20, 60, 60, 80, 80)]
    assert decisions == [D.HARD, D.NORMAL, D.NORMAL, D.EASY, D.EASY, D.NORMAL]
    assert c.score(D.NORMAL) == 90 and c.score(D.EASY) == 70
    assert feed(c, 60).difficulty is D.NORMAL
    assert feed(c, 60).reason == 'hysteresis_hold'


def test_no_reaction_to_one_small_batch_and_batch_weight_not_ticket_independence():
    c = ArenaAdaptiveController()
    feed(c, 0, used=8)
    assert c.difficulty is D.HARD
    feed(c, 160, used=160)
    assert c.score(D.HARD) == 90  # Mean of two batch rates, not 160/168.
    assert c.difficulty is D.NORMAL


def test_hysteresis_oscillation_and_bounded_reconsideration():
    c = ArenaAdaptiveController()
    # Hard ~90, Normal ~90: marginal changes hold until scheduled exploration.
    feed(c, 40); feed(c, 40)
    feed(c, 60); feed(c, 60)
    assert c.difficulty is D.EASY  # Acquiring unknown adjacent level.
    feed(c, 40); feed(c, 40)
    assert c.difficulty is D.NORMAL
    assert feed(c, 56).difficulty is D.NORMAL
    assert feed(c, 64).reason == 'hysteresis_hold'
    assert feed(c, 56).reason == 'hysteresis_hold'
    decision = feed(c, 64)
    assert decision.reason == 'adjacent_reconsideration'
    assert decision.difficulty is D.HARD


def test_discarded_level_can_be_revisited_and_old_evidence_expires():
    c = ArenaAdaptiveController()
    feed(c, 8); feed(c, 8)
    feed(c, 80); feed(c, 80)
    feed(c, 40); feed(c, 40)
    assert c.difficulty is D.NORMAL
    for _ in range(4): feed(c, 80)
    assert c.difficulty is D.HARD
    c.batches += 12  # Expired observations carry no estimated score.
    assert c.recent(D.HARD) == [] and c.score(D.HARD) is None
    feed(c, 80); feed(c, 80)
    assert c.score(D.HARD) == REWARDS[D.HARD]


@pytest.mark.parametrize('used,threshold,jump', [(72, 80, False), (80, 80, True), (80, 88, False), (88, 88, True)])
def test_hard_zero_exception_is_individual_batch_and_configurable(used, threshold, jump):
    c = ArenaAdaptiveController(threshold)
    decision = feed(c, 0, used)
    assert (decision.difficulty is D.EASY) == jump and not decision.finish


def test_small_zeros_never_sum_to_exception():
    c = ArenaAdaptiveController()
    feed(c, 0, 40)
    decision = feed(c, 0, 40)
    assert decision.difficulty is D.NORMAL and decision.reason == 'adjacent_uncertainty'


def test_easy_zero_exception_precedes_dwell_and_statistics():
    c = ArenaAdaptiveController()
    assert feed(c, 0).difficulty is D.EASY
    small = feed(c, 0, 72)
    assert not small.finish and small.difficulty is D.EASY
    assert feed(c, 0).finish


def test_history_is_never_shared_and_invalid_batch_does_not_mutate():
    c = ArenaAdaptiveController(); feed(c, 0)
    fresh = ArenaAdaptiveController()
    assert fresh.difficulty is D.HARD and fresh.batches == 0 and fresh.score(D.HARD) is None
    wrong = batch(D.NORMAL)
    with pytest.raises(ValueError): fresh.observe(wrong)
    with pytest.raises(ValueError): fresh.observe(None)
    valid = batch(D.HARD)
    fresh.observe(valid)
    with pytest.raises(ValueError): fresh.observe(valid)
    assert fresh.batches == 1
