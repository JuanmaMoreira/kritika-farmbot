"""Explicit observations scoped to one session character, never predicted balances."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

@dataclass
class CharacterResourceKnowledge:
    stage_ads_exhausted: bool = False
    stage_ads_epoch: str | None = None

_knowledge = ContextVar("character_resource_knowledge", default=None)

def character_resource_knowledge():
    return _knowledge.get()

@contextmanager
def character_resource_scope():
    token = _knowledge.set(CharacterResourceKnowledge())
    try:
        yield _knowledge.get()
    finally:
        _knowledge.reset(token)
