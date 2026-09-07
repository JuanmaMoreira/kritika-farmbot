"""Additive failure metadata, independent of recovery and evidence acquisition."""

from dataclasses import asdict, dataclass

from bot.event_context import event_context


@dataclass(frozen=True)
class FailureCause:
    type: str
    message: str
    exception_type: str | None = None
    flow: str | None = None
    step: str | None = None
    sequence: int | None = None
    evidence_ref: str | None = None

    def payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_error(cls, error, *, kind="legacy_error", step=None, sequence=None):
        context = event_context()
        return cls(
            type=kind,
            message=str(error),
            exception_type=type(error).__name__ if isinstance(error, BaseException) else None,
            flow=context["flow"], step=step or context["step"], sequence=sequence,
        )
