"""Occurrence settings only; economic policy and x8 remain mandatory."""
from dataclasses import dataclass
from enum import Enum

from bot.arena_semantics import ArenaDifficulty


class ArenaMode(str, Enum):
    SINGLE_BATTLE = 'SINGLE_BATTLE'
    AUTO_REPEAT = 'AUTO_REPEAT'
    FARMING_CYCLE = 'FARMING_CYCLE'


@dataclass(frozen=True)
class ArenaConfig:
    mode: ArenaMode = ArenaMode.SINGLE_BATTLE
    difficulty: ArenaDifficulty = ArenaDifficulty.EASY
    min_badges_for_arena: int = 40
    min_sapphires_for_mw: int = 100
    zero_win_threshold: int = 80
    maximum_stamina_consumption: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'mode', ArenaMode(self.mode))
        object.__setattr__(self, 'difficulty', ArenaDifficulty(self.difficulty))
        limit = self.maximum_stamina_consumption
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError('maximum_stamina_consumption must be an integer >= 0 or empty')
        for name in ('min_badges_for_arena', 'min_sapphires_for_mw', 'zero_win_threshold'):
            value = getattr(self, name)
            minimum = 8 if name == 'min_badges_for_arena' else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f'{name} must be an integer >= {minimum}')
        if self.mode is ArenaMode.FARMING_CYCLE:
            object.__setattr__(self, 'difficulty', ArenaDifficulty.HARD)

    def to_dict(self):
        if self.mode is ArenaMode.FARMING_CYCLE:
            settings = dict(mode=self.mode.value, min_badges_for_arena=self.min_badges_for_arena,
                        min_sapphires_for_mw=self.min_sapphires_for_mw,
                        zero_win_threshold=self.zero_win_threshold)
            if self.maximum_stamina_consumption is not None:
                settings['maximum_stamina_consumption'] = self.maximum_stamina_consumption
            return settings
        return dict(mode=self.mode.value, difficulty=self.difficulty.value)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {
                'mode', 'difficulty', 'min_badges_for_arena', 'min_sapphires_for_mw', 'zero_win_threshold',
                'maximum_stamina_consumption'}:
            raise ValueError('Invalid Arena settings')
        return cls(**value)
