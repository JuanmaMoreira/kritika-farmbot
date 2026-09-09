"""Bounded semantic intents and acquired normalized targets for SKIP-only MW."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenMonsterWave: pass


@dataclass(frozen=True)
class ExitMonsterWave: pass


@dataclass(frozen=True)
class OpenMonsterWaveTickets: pass


@dataclass(frozen=True)
class FillMonsterWaveTickets: pass


@dataclass(frozen=True)
class CloseMonsterWaveTickets: pass


@dataclass(frozen=True)
class ActivateMonsterWaveSkip: pass


@dataclass(frozen=True)
class SelectMonsterWaveMax:
    """Exactly two consecutive taps; one intentional action, never a retry."""


@dataclass(frozen=True)
class StartMonsterWaveSkip: pass


@dataclass(frozen=True)
class RejectMonsterWaveSapphires: pass


@dataclass(frozen=True)
class DeclineMonsterWaveInventory: pass


@dataclass(frozen=True)
class AcceptMonsterWaveInventory: pass


@dataclass(frozen=True)
class AcknowledgeMonsterWaveClear: pass


@dataclass(frozen=True)
class AcknowledgeMonsterWaveWeekly: pass


@dataclass(frozen=True)
class AcknowledgeMonsterWaveRanking: pass


MonsterWaveAction = (
    OpenMonsterWave | ExitMonsterWave | OpenMonsterWaveTickets | FillMonsterWaveTickets
    | CloseMonsterWaveTickets | ActivateMonsterWaveSkip | SelectMonsterWaveMax
    | StartMonsterWaveSkip | RejectMonsterWaveSapphires | DeclineMonsterWaveInventory
    | AcceptMonsterWaveInventory | AcknowledgeMonsterWaveClear
    | AcknowledgeMonsterWaveWeekly | AcknowledgeMonsterWaveRanking
)

# Reviewed controls in the two acquisition manifests. No target for manual Start.
MONSTER_WAVE_TARGETS = {
    OpenMonsterWave: (.245, .385), ExitMonsterWave: (.81, .055),
    OpenMonsterWaveTickets: (.54, .703), FillMonsterWaveTickets: (.59, .848),
    CloseMonsterWaveTickets: (.736, .076), ActivateMonsterWaveSkip: (.766, .708),
    SelectMonsterWaveMax: (.792, .595), StartMonsterWaveSkip: (.766, .708),
    RejectMonsterWaveSapphires: (.568, .626),
    DeclineMonsterWaveInventory: (.568, .626), AcceptMonsterWaveInventory: (.431, .626),
    AcknowledgeMonsterWaveClear: (.499, .762),
    AcknowledgeMonsterWaveWeekly: (.5, .806),
    AcknowledgeMonsterWaveRanking: (.5, .674),
}
