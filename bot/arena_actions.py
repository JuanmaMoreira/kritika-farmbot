"""Arena targets acquired independently of Survival; economic guards belong to the flow."""
from dataclasses import dataclass
from enum import Enum


class ArenaControl(str, Enum):
    BATTLE = 'battle'
    ARENA = 'arena'
    EASY = 'easy'
    NORMAL = 'normal'
    HARD = 'hard'
    BACK = 'back'
    BUFF1 = 'buff1'
    BUFF2 = 'buff2'
    BUFF3 = 'buff3'
    X8 = 'x8'
    CONFIG = 'config'
    CONFIG_CLOSE = 'config_close'
    UPON_DEFEAT = 'upon_defeat'
    START = 'start'
    RESULT_OK = 'result_ok'
    BADGES_NO = 'badges_no'
    RANKING_OK = 'ranking_ok'
    SINGLE_START = 'single_start'
    SINGLE_RESULT_CLOSE = 'single_result_close'


@dataclass(frozen=True)
class ArenaAction:
    control: ArenaControl

    def __post_init__(self):
        if not isinstance(self.control, ArenaControl):
            raise ValueError('typed Arena control required')


POINTS = dict(zip(ArenaControl, (
    (.825, .59), (.278, .389), (.277, .805), (.5, .805), (.716, .805),
    (.801, .061), (.555, .35), (.664, .35), (.773, .35), (.785, .73),
    (.769, .848), (.69, .09), (.659, .773), (.5, .875), (.5, .866),
    (.57, .623), (.5, .674),
)))
POINTS[ArenaControl.SINGLE_START] = (.769, .943)
POINTS[ArenaControl.SINGLE_RESULT_CLOSE] = (.5, .884)
