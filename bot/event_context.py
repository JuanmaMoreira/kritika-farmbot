"""Local execution correlation; scopes never carry gameplay state."""

from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4


CONTEXT_FIELDS = (
    "run_id", "session_id", "character_index", "flow", "operation_id",
    "parent_operation_id", "step",
)
_context: ContextVar[dict] = ContextVar("runtime_event_context", default={})


def event_context() -> dict:
    return {key: _context.get().get(key) for key in CONTEXT_FIELDS}


def new_correlation_id() -> str:
    return uuid4().hex


@contextmanager
def event_scope(**fields):
    token = _context.set({**_context.get(), **fields})
    try:
        yield event_context()
    finally:
        _context.reset(token)


@contextmanager
def operation_scope(step: str):
    with event_scope(
        operation_id=new_correlation_id(),
        parent_operation_id=_context.get().get("operation_id"), step=step,
    ) as context:
        yield context
