"""Arena A/B1/B2 contracts. No farming policy or historical win counts."""
from dataclasses import dataclass
from enum import Enum
import math

SCREEN_ARENA = "screen.arena"
SCREEN_ARENA_SELECT_MODE = "screen.arena_select_mode"
SCREEN_ARENA_BATTLE = "screen.arena_battle"
ARENA_SINGLE_RESULT = "landmark.arena_single_result"
OVERLAY_ARENA_SINGLE_RESULT = "overlay.arena_single_result"
ARENA_BATTLE = "landmark.arena_battle"
ARENA_MODE_SELECT = "landmark.arena_mode_select"
ARENA_SELECT = "landmark.arena_select"
ARENA_CHALLENGE = "landmark.arena_challenge"
ARENA_CONFIG = "landmark.arena_auto_config"
ARENA_RESULT = "landmark.arena_batch_result"
ARENA_INSUFFICIENT = "landmark.arena_insufficient_badge"
ARENA_RANKING = "landmark.arena_new_ranking"
ARENA_ACTIVE = "activity.arena_auto_repeat_active"
ARENA_MODAL_PAIRS = (
    ("popup.arena_auto_config", ARENA_CONFIG),
    ("popup.arena_batch_result", ARENA_RESULT),
    ("popup.arena_insufficient_badge", ARENA_INSUFFICIENT),
    ("popup.arena_new_ranking", ARENA_RANKING),
)
ARENA_OBSERVATIONS = ("landmark.arena_base", ARENA_SELECT, ARENA_CHALLENGE, ARENA_CONFIG, ARENA_RESULT,
                      ARENA_INSUFFICIENT, ARENA_RANKING, ARENA_ACTIVE,
                      "fact.arena_difficulty", "fact.arena_x8", "fact.arena_buff1",
                      "fact.arena_buff2", "fact.arena_buff3", "fact.arena_upon_defeat",
                      ARENA_SINGLE_RESULT, ARENA_BATTLE, ARENA_MODE_SELECT)


class ArenaDifficulty(str, Enum):
    EASY = "EASY"
    NORMAL = "NORMAL"
    HARD = "HARD"


@dataclass(frozen=True)
class ArenaPreparationFacts:
    difficulty: ArenaDifficulty | None
    buffs: tuple[bool | None, bool | None, bool | None]
    x8: bool | None


@dataclass(frozen=True)
class ArenaEconomyFacts:
    """Free counters from ONE native, fresh Challenge observation."""
    available_badges: int
    free_buffs: tuple[int | None, int | None, int | None]
    preparation: ArenaPreparationFacts
    sequence: int
    observed_at: float

    @property
    def planned_consumption(self):
        return planned_badges_consumption(self.available_badges)


@dataclass(frozen=True)
class ArenaBatchExecution:
    """Caller receipt of ONE effective green-button start, never inferred from final.

    The ArenaFlow execution owner supplies known configuration, effective input time,
    source lifetime and pre-input sequence. It must invalidate this receipt upon
    another start, source discontinuity, cancellation or foreign navigation.
    ``start_verified`` means an effective input and positive post-start evidence,
    not an attempted tap or the absence of Auto Repeat. Phase A executes no input;
    the B1 owner invalidates the reading receipt when its observation is stopped.
    Explicit caller-owned handoff may create a NEW source-segment receipt from
    the historical verified Start and uninterrupted physical ownership; it must
    retain run/start/configuration and credit fresh positive activity or terminal.
    """
    run_id: str
    source_id: str
    difficulty: ArenaDifficulty | None
    multiplier: int | None
    started_at: float
    after_sequence: int
    start_verified: bool = False

    def __post_init__(self):
        if not self.run_id or not self.source_id:
            raise ValueError("execution and source lifetime identities required")
        if not math.isfinite(self.started_at) or self.started_at < 0:
            raise ValueError("invalid start time")
        if type(self.after_sequence) is not int or self.after_sequence < 0:
            raise ValueError("invalid sequence barrier")


@dataclass(frozen=True)
class ArenaSingleExecution:
    """One Challenge Start with fresh balances; never an Auto Repeat receipt."""
    run_id: str
    source_id: str
    difficulty: ArenaDifficulty
    multiplier: int
    started_at: float
    after_sequence: int
    start_verified: bool
    start_badges: int
    start_karats: int

    def __post_init__(self):
        if not self.run_id or not self.source_id or not isinstance(self.difficulty,ArenaDifficulty) or self.multiplier!=8:
            raise ValueError('known Single execution/configuration required')
        if (not math.isfinite(self.started_at) or self.started_at<0 or type(self.after_sequence) is not int
                or self.after_sequence<0 or type(self.start_verified) is not bool):
            raise ValueError('invalid Single input barrier')
        if type(self.start_badges) is not int or self.start_badges<8 or type(self.start_karats) is not int or self.start_karats<0:
            raise ValueError('fresh Single starting balances required')


@dataclass(frozen=True)
class ArenaBalances:
    badges: int
    gold: int
    karats: int
    sequence: int
    observed_at: float
    frame_sha256: str

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in (self.badges,self.gold,self.karats,self.sequence)):
            raise ValueError('nonnegative native balances and sequence required')
        if not math.isfinite(self.observed_at) or self.observed_at < 0:
            raise ValueError('native balance timestamp required')
        if len(self.frame_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.frame_sha256):
            raise ValueError('native balance pixel hash required')


class ArenaSingleOutcome(str, Enum):
    VICTORY = 'VICTORY'


@dataclass(frozen=True)
class ArenaSingleResult:
    """Positive victory overlay plus native balances after its acquired close.

    No won_tickets. Consumption and Karats delta are balance differences tied
    to one Start; terminal and balance observations have separate provenance.
    Defeat presentation remains UNKNOWN until natural evidence is acquired.
    """
    difficulty: ArenaDifficulty
    multiplier: int
    outcome: ArenaSingleOutcome
    badges_before: int
    balances_after: ArenaBalances
    karats_before: int
    run_id: str
    source_id: str
    terminal_sequence: int
    terminal_observed_at: float
    terminal_frame_sha256: str

    def __post_init__(self):
        if (not isinstance(self.difficulty,ArenaDifficulty) or type(self.multiplier) is not int or self.multiplier!=8
                or self.outcome is not ArenaSingleOutcome.VICTORY or not isinstance(self.balances_after,ArenaBalances)):
            raise ValueError('credited Single outcome/configuration required')
        if (type(self.badges_before) is not int or type(self.karats_before) is not int
                or self.used_tickets!=8 or self.karats_delta!=8):
            raise ValueError('Single x8 victory requires credited eight Badge/Karat deltas')
        if (not self.run_id or not self.source_id or self.balances_after.sequence<=self.terminal_sequence
                or self.balances_after.observed_at<=self.terminal_observed_at):
            raise ValueError('Single terminal/closing lineage required')
        if (type(self.terminal_sequence) is not int or self.terminal_sequence<0
                or not math.isfinite(self.terminal_observed_at) or self.terminal_observed_at<0
                or len(self.terminal_frame_sha256)!=64
                or any(c not in '0123456789abcdef' for c in self.terminal_frame_sha256)):
            raise ValueError('Single terminal provenance required')

    @property
    def used_tickets(self):
        return self.badges_before-self.balances_after.badges

    @property
    def karats_delta(self):
        return self.balances_after.karats-self.karats_before


@dataclass(frozen=True)
class ArenaResultProvenance:
    run_id: str
    source_id: str
    sequence: int
    frame_sha256: str
    used_confidence: float
    won_confidence: float
    authority: str = "USER_GT: Acquired Karats -> won_tickets; LOCAL_CV + focal OCR"

    def __post_init__(self):
        if not self.run_id or not self.source_id or type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("execution/source/sequence provenance required")
        if len(self.frame_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.frame_sha256):
            raise ValueError("frame pixel hash required")
        if any(not math.isfinite(c) or not .95 <= c <= 1 for c in (self.used_confidence,self.won_confidence)):
            raise ValueError("credited numeric confidences required")


@dataclass(frozen=True)
class ArenaBatchResult:
    difficulty: ArenaDifficulty
    multiplier: int
    used_tickets: int
    won_tickets: int
    observed_at: float
    provenance: ArenaResultProvenance

    def __post_init__(self):
        if not isinstance(self.difficulty, ArenaDifficulty) or type(self.multiplier) is not int or self.multiplier != 8:
            raise ValueError("known Arena difficulty and x8 required")
        if type(self.used_tickets) is not int or self.used_tickets <= 0:
            raise ValueError("used_tickets must be a positive integer")
        if type(self.won_tickets) is not int or not 0 <= self.won_tickets <= self.used_tickets:
            raise ValueError("won_tickets must be an integer in 0..used_tickets")
        if not math.isfinite(self.observed_at) or self.observed_at < 0:
            raise ValueError("invalid observation time")
        if not isinstance(self.provenance, ArenaResultProvenance):
            raise ValueError("result provenance required")

    @property
    def winrate(self) -> float:
        return self.won_tickets / self.used_tickets

    @property
    def lost_tickets(self) -> int:
        return self.used_tickets - self.won_tickets


def planned_badges_consumption(available_badges: int) -> int:
    """Candidate natural x8 consumption; blockers/interruptions can reduce it."""
    if type(available_badges) is not int or available_badges < 0:
        raise ValueError("known nonnegative Badge balance required")
    return (available_badges // 8) * 8


def double_points_covered(available: int | None, planned: int | None, *,
                          reserved: int | None = None) -> bool:
    """No spending permission. A selected free balance needs credited reservation.

    Pass reserved=0 for a known OFF balance. Unknown reservation stays false;
    the observed refund for buffs 1/2 does not establish a buff 3 refund.
    """
    return (all(type(v) is int and v >= 0 for v in (available, planned, reserved))
            and planned > 0 and available + reserved >= planned)
