"""Runtime ``TreasureCurrencyFact`` construction from real observations.

Pure builders in the E idiom: no navigation, no input, no policy
beyond refusing to manufacture currency. A fact always describes one
control (single = ``1(Open)``, repeat = ``10(Open)``) because the
popup offers both amounts at once and each tap spends exactly one of
them. Selecting which demonstrated amount to encode is the caller's
already-decided quantity, not a new decision: the fact stays
truthful (the encoded amount IS offered with a Gold icon and no
Karat contradiction on a fresh Treasure snapshot).

Currency mapping per control:

- ``"gold_key"`` only when that control's Gold signal is present
  (grid gold for single; popup label plus icon gold for either;
  result bottom-bar icon gold for either) and NO Karat signal
  anywhere on the snapshot;
- ``"karat"`` when any Karat signal is present (fail-closed even
  when Gold is also present: simultaneous Gold+Karat is the
  documented contradiction and never authorizes a tap);
- ``"unknown"`` when Treasure resolves but neither Gold for that
  control nor Karat is demonstrated. Absence of Gold never
  authorizes input.

``None`` (not a fact) only for structural unusability: foreign
base, UNKNOWN/AMBIGUOUS status. ``"empty"`` (positively observed
no-keys) and ``count`` have no reliable signal in E2 v1 (tile
counts need an OCR campaign, explicitly not forced): depleted gold
presents as missing Gold (``gold_not_ready``, fail closed) or as a
Karat boundary when the premium UI appears. Overlay is
``"selector"`` for popup state, ``"result"`` for result state
(result wins when both somehow present), else None.
"""

from __future__ import annotations

from bot.state import ResolutionStatus
from bot.treasure_center import (
    has,
    has_karat_signal,
    has_result,
    has_selector_popup,
    is_treasure_screen,
)
from bot.treasure_center_semantics import (
    INDICATOR_TREASURE_GOLD_KEY_REPEAT as _REPEAT,
    INDICATOR_TREASURE_GOLD_KEY_SELECTOR as _SELECTOR,
)
from bot.treasure_keys import TreasureCurrencyFact


def _usable(snapshot) -> bool:
    status = getattr(getattr(snapshot, "state", None), "status", None)
    if status is not ResolutionStatus.RESOLVED:
        return False
    return is_treasure_screen(snapshot)


def _overlay(snapshot) -> str | None:
    if has_result(snapshot):
        return "result"
    if has_selector_popup(snapshot):
        return "selector"
    return None


def _currency(snapshot, gold_name: str) -> str:
    if has_karat_signal(snapshot):
        return "karat"
    if has(snapshot, gold_name):
        return "gold_key"
    return "unknown"


def fact_for_single(snapshot, *, sequence=None, evidence=()):
    """Build the ``1(Open)`` fact from a fresh Treasure snapshot."""
    return _fact(snapshot, _SELECTOR, 1, sequence=sequence, evidence=evidence)


def fact_for_repeat(snapshot, *, sequence=None, evidence=()):
    """Build the ``10(Open)`` fact from a fresh Treasure snapshot."""
    return _fact(snapshot, _REPEAT, 10, sequence=sequence, evidence=evidence)


def _fact(snapshot, gold_name: str, amount: int, *, sequence, evidence):
    if not _usable(snapshot):
        return None
    if sequence is None:
        try:
            sequence = int(snapshot.sequence)
        except (AttributeError, TypeError, ValueError):
            return None
    try:
        sequence = int(sequence)
    except (TypeError, ValueError):
        return None
    if isinstance(sequence, bool):
        return None
    currency = _currency(snapshot, gold_name)
    if currency == "gold_key":
        amount_offered: int | None = amount
    else:
        amount_offered = None
    return TreasureCurrencyFact(
        currency=currency,
        amount_offered=amount_offered,
        count=None,
        overlay=_overlay(snapshot),
        sequence=sequence,
        evidence=tuple(evidence),
    )


__all__ = (
    "fact_for_repeat",
    "fact_for_single",
)
