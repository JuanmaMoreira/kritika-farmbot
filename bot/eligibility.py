"""Routine-owned decisions made before a flow starts, never flow-global policy."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from bot.failure_cause import FailureCause


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    UNKNOWN = "unknown"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class EligibilityResult:
    status: EligibilityStatus
    reason: str
    failure: FailureCause | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, EligibilityStatus):
            raise ValueError("status must be EligibilityStatus")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        if self.status in {EligibilityStatus.UNKNOWN, EligibilityStatus.FAILED}:
            if self.failure is None:
                object.__setattr__(self, "failure", FailureCause.from_error(
                    self.reason, kind=f"eligibility_{self.status.value}",
                ))
        elif self.failure is not None:
            raise ValueError("only unknown or failed eligibility can contain failure")


class EligibilityCheck(Protocol):
    """Evaluate after the flow precondition; restore it before a definitive decision.

    Implementations own bounded semantic observation/navigation. An inconclusive
    evaluation stops safely; it never authorizes cleanup input from UNKNOWN.
    The runner owns result publication and never supplies actions or perception.
    """

    def evaluate(self) -> EligibilityResult: ...
