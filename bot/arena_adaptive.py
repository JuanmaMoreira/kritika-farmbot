"""Recent, batch-weighted decisions confined to ONE Farming Cycle execution."""
from dataclasses import dataclass

from bot.arena_semantics import ArenaBatchResult, ArenaDifficulty as D

REWARDS = {D.EASY: 70, D.NORMAL: 120, D.HARD: 180}
LEVELS = (D.EASY, D.NORMAL, D.HARD)
# Policy bounds, not physical costs or statistical confidence intervals.
WINDOW = 3
MAX_AGE_BATCHES = 12
MIN_OBSERVATIONS = 2
MIN_DWELL = 2
EXPLORE_DWELL = 4
HYSTERESIS = .10


@dataclass(frozen=True)
class DifficultyDecision:
    difficulty: D
    reason: str
    finish: bool = False


class ArenaAdaptiveController:
    def __init__(self, zero_win_threshold=80):
        if type(zero_win_threshold) is not int or zero_win_threshold < 1:
            raise ValueError('positive zero-win threshold required')
        self.zero_win_threshold = zero_win_threshold
        self.difficulty = D.HARD
        self.observations = {d: [] for d in LEVELS}
        self.batches = self.dwell = 0
        self._runs = set()

    def recent(self, difficulty):
        return [(index, rate) for index, rate in self.observations[difficulty]
                if self.batches - index < MAX_AGE_BATCHES][-WINDOW:]

    def score(self, difficulty):
        samples = self.recent(difficulty)
        if not samples:
            return None  # Unobserved is not a zero winrate.
        return REWARDS[difficulty] * sum(rate for _, rate in samples) / len(samples)

    def observe(self, result):
        if (not isinstance(result, ArenaBatchResult) or result.difficulty is not self.difficulty
                or result.provenance.run_id in self._runs):
            raise ValueError('unique credited x8 batch at selected difficulty required')
        self._runs.add(result.provenance.run_id)
        self.batches += 1
        self.dwell += 1
        self.observations[self.difficulty].append((self.batches, result.winrate))
        self.observations[self.difficulty] = self.observations[self.difficulty][-WINDOW:]
        if result.used_tickets >= self.zero_win_threshold and result.won_tickets == 0:
            if self.difficulty is D.EASY:
                return DifficultyDecision(D.EASY, 'easy_zero_wins', True)
            if self.difficulty is D.HARD:
                return self._switch(D.EASY, 'hard_zero_wins')
        if self.dwell < MIN_DWELL:
            return DifficultyDecision(self.difficulty, 'collect_recent_batches')
        adjacent = [d for d in LEVELS if abs(LEVELS.index(d) - LEVELS.index(self.difficulty)) == 1]
        current = self.score(self.difficulty)
        if len(self.recent(self.difficulty)) >= MIN_OBSERVATIONS:
            better = [d for d in adjacent if len(self.recent(d)) >= MIN_OBSERVATIONS
                      and self.score(d) > current * (1 + HYSTERESIS)]
            if better:
                return self._switch(max(better, key=self.score), 'recent_reward_advantage')
        uncertain = [d for d in adjacent if len(self.recent(d)) < MIN_OBSERVATIONS]
        if uncertain:
            target = min(uncertain, key=lambda d: self.observations[d][-1][0] if self.observations[d] else -1)
            return self._switch(target, 'adjacent_uncertainty')
        if self.dwell >= EXPLORE_DWELL:
            target = min(adjacent, key=lambda d: self.observations[d][-1][0])
            return self._switch(target, 'adjacent_reconsideration')
        return DifficultyDecision(self.difficulty, 'hysteresis_hold')

    def _switch(self, target, reason):
        self.difficulty = target
        self.dwell = 0
        return DifficultyDecision(target, reason)
