"""Occurrence settings only; economic policy and x8 remain mandatory."""
from dataclasses import dataclass
from enum import Enum

from bot.arena_semantics import ArenaDifficulty


class ArenaMode(str, Enum):
    SINGLE_BATTLE = 'SINGLE_BATTLE'
    AUTO_REPEAT = 'AUTO_REPEAT'


@dataclass(frozen=True)
class ArenaConfig:
    mode: ArenaMode = ArenaMode.SINGLE_BATTLE
    difficulty: ArenaDifficulty = ArenaDifficulty.EASY

    def __post_init__(self):
        object.__setattr__(self, 'mode', ArenaMode(self.mode))
        object.__setattr__(self, 'difficulty', ArenaDifficulty(self.difficulty))

    def to_dict(self):
        return dict(mode=self.mode.value, difficulty=self.difficulty.value)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {'mode', 'difficulty'}:
            raise ValueError('Invalid Arena settings')
        return cls(**value)
